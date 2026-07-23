import argparse
import datetime as dt
import json
import pathlib
import tempfile
import uuid
from typing import Any

from arthur_config import get_path


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
QUEUE_FILE = SCRATCH / "arthur_prompt_queue.jsonl"
RESPONSES_FILE = SCRATCH / "arthur_prompt_responses.jsonl"
WATCHDOG_LOG = SCRATCH / "arthur_queue_watchdog.log"
ARCHIVE_DIR = SCRATCH / "arthur_archive"

TERMINAL_STATUSES = {"completed", "blocked", "failed"}
ACTIVE_STATUSES = {"claimed", "running"}


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def iso_timestamp(value: dt.datetime | None = None) -> str:
    return (value or now()).isoformat()


def log(message: str) -> None:
    timestamp = now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with WATCHDOG_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def parse_timestamp(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now().tzinfo)
    return parsed.astimezone()


def age_seconds(value: Any) -> float | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return None
    return max(0.0, (now() - parsed).total_seconds())


def read_jsonl(path: pathlib.Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    entries: list[dict[str, Any]] = []
    invalid_lines: list[str] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines.append(line)
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
        else:
            invalid_lines.append(line)
    return entries, invalid_lines


def write_jsonl(path: pathlib.Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) for entry in entries)
    if payload:
        payload += "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), newline="\n") as handle:
        handle.write(payload)
        temp_name = handle.name
    pathlib.Path(temp_name).replace(path)


def append_jsonl(path: pathlib.Path, entries: list[dict[str, Any]]) -> None:
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")


def archive_blocked_path() -> pathlib.Path:
    return ARCHIVE_DIR / f"arthur_prompt_queue_blocked_auto_cleared_{now().strftime('%Y%m%d')}.jsonl"


def response_ids() -> set[str]:
    entries, _ = read_jsonl(RESPONSES_FILE)
    return {str(entry.get("id")) for entry in entries if entry.get("id")}


def append_response(prompt_id: str, response: str) -> None:
    if prompt_id in response_ids():
        return
    RESPONSES_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {"id": prompt_id, "completed_at": iso_timestamp(), "response": response}
    with RESPONSES_FILE.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")


def add_history(entry: dict[str, Any], action: str, reason: str) -> None:
    history = entry.get("watchdog_history")
    if not isinstance(history, list):
        history = []
        entry["watchdog_history"] = history
    history.append({"at": iso_timestamp(), "action": action, "reason": reason})
    if len(history) > 20:
        del history[:-20]


def normalize_entry(entry: dict[str, Any]) -> bool:
    changed = False
    if not entry.get("status"):
        entry["status"] = "pending"
        changed = True
    if not entry.get("created_at") and entry.get("timestamp"):
        entry["created_at"] = entry.get("timestamp")
        changed = True
    if "attempt_count" not in entry:
        entry["attempt_count"] = 0
        changed = True
    if "max_attempts" not in entry:
        entry["max_attempts"] = 2
        changed = True
    return changed


def block_entry(entry: dict[str, Any], reason: str, response: str) -> None:
    entry["status"] = "blocked"
    entry["block_reason"] = reason
    entry["completed_at"] = iso_timestamp()
    add_history(entry, "blocked", reason)
    prompt_id = str(entry.get("id") or "unknown")
    append_response(prompt_id, response)


def repair_queue(
    stale_running_seconds: int,
    stale_pending_seconds: int,
    max_pending_age_seconds: int,
    clear_blocked_after_seconds: int,
    quiet: bool,
) -> int:
    entries, invalid_lines = read_jsonl(QUEUE_FILE)
    changed = False
    keep_entries: list[dict[str, Any]] = []
    archived_blocked: list[dict[str, Any]] = []
    if invalid_lines and not quiet:
        log(f"Queue contains {len(invalid_lines)} invalid JSONL line(s); leaving them out of repaired queue.")
        changed = True

    for entry in entries:
        changed = normalize_entry(entry) or changed
        prompt_id = str(entry.get("id") or "unknown")
        status = str(entry.get("status") or "pending")
        attempts = int(entry.get("attempt_count") or 0)
        max_attempts = int(entry.get("max_attempts") or 2)

        if status in ACTIVE_STATUSES:
            heartbeat_age = age_seconds(entry.get("last_heartbeat_at") or entry.get("claimed_at"))
            if heartbeat_age is not None and heartbeat_age >= stale_running_seconds:
                reason = f"{status} heartbeat stale for {heartbeat_age:.0f}s"
                if attempts < max_attempts:
                    entry["status"] = "pending"
                    entry.pop("runner_id", None)
                    entry.pop("claimed_at", None)
                    entry.pop("last_heartbeat_at", None)
                    add_history(entry, "requeued", reason)
                    changed = True
                    if not quiet:
                        log(f"Requeued stale Arthur prompt {prompt_id}: {reason}.")
                else:
                    block_entry(
                        entry,
                        f"{reason}; max attempts reached",
                        "Arthur queue item blocked after repeated stale runs; moving on.",
                    )
                    changed = True
                    if not quiet:
                        log(f"Blocked Arthur prompt {prompt_id}: {reason}; max attempts reached.")

        elif status == "pending":
            pending_age = age_seconds(entry.get("created_at") or entry.get("timestamp"))
            if pending_age is not None and pending_age >= stale_pending_seconds:
                if entry.get("watchdog_state") != "stale_pending":
                    entry["watchdog_state"] = "stale_pending"
                    entry["stale_since"] = iso_timestamp()
                    add_history(entry, "stale_pending", f"pending for {pending_age:.0f}s")
                    changed = True
                if not quiet:
                    log(f"Arthur prompt {prompt_id} is pending for {pending_age:.0f}s.")
                if attempts >= max_attempts and pending_age >= max_pending_age_seconds:
                    block_entry(
                        entry,
                        f"pending for {pending_age:.0f}s after {attempts} attempt(s)",
                        "Arthur queue item blocked after repeated pending retries; moving on.",
                    )
                    changed = True
                    if not quiet:
                        log(f"Blocked Arthur prompt {prompt_id} after repeated pending retries.")

        elif status == "failed":
            reason = str(entry.get("failure_reason") or "failed without reason")
            if attempts < max_attempts:
                entry["status"] = "pending"
                add_history(entry, "requeued_failed", reason)
                changed = True
                if not quiet:
                    log(f"Requeued failed Arthur prompt {prompt_id}: {reason}.")
            else:
                block_entry(entry, f"{reason}; max attempts reached", "Arthur queue item failed repeatedly; moving on.")
                changed = True
                if not quiet:
                    log(f"Blocked failed Arthur prompt {prompt_id}: {reason}.")

        elif status == "blocked":
            blocked_age = age_seconds(entry.get("completed_at") or entry.get("last_heartbeat_at") or entry.get("claimed_at") or entry.get("timestamp"))
            if blocked_age is not None and blocked_age >= clear_blocked_after_seconds:
                entry["auto_cleared_at"] = iso_timestamp()
                add_history(entry, "auto_cleared_blocked", f"blocked for {blocked_age:.0f}s")
                archived_blocked.append(entry)
                changed = True
                if not quiet:
                    log(f"Auto-cleared blocked Arthur prompt {prompt_id} after {blocked_age:.0f}s.")
                continue

        keep_entries.append(entry)

    if changed:
        if archived_blocked:
            append_jsonl(archive_blocked_path(), archived_blocked)
        write_jsonl(QUEUE_FILE, keep_entries)
    return 0


def print_status() -> int:
    entries, invalid_lines = read_jsonl(QUEUE_FILE)
    counts: dict[str, int] = {}
    for entry in entries:
        status = str(entry.get("status") or "pending")
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps({"counts": counts, "invalid_lines": len(invalid_lines)}, indent=2))
    return 0


def claim_next(runner_id: str | None) -> int:
    entries, invalid_lines = read_jsonl(QUEUE_FILE)
    changed = False
    selected: dict[str, Any] | None = None
    runner = runner_id or f"arthur-responder-{uuid.uuid4().hex[:12]}"
    current_time = iso_timestamp()

    for entry in entries:
        changed = normalize_entry(entry) or changed
        if selected is not None:
            continue
        if str(entry.get("status") or "pending") != "pending":
            continue
        if entry.get("block_reason"):
            continue

        attempts = int(entry.get("attempt_count") or 0)
        entry["status"] = "claimed"
        entry["runner_id"] = runner
        entry["claimed_at"] = current_time
        entry["last_heartbeat_at"] = current_time
        entry["attempt_count"] = attempts + 1
        entry.setdefault("max_attempts", 2)
        add_history(entry, "claimed", f"claimed by {runner}")
        selected = entry
        changed = True

    if changed:
        write_jsonl(QUEUE_FILE, entries)

    if selected is None:
        print(
            json.dumps(
                {
                    "status": "no_runnable",
                    "message": "No runnable prompt found.",
                    "invalid_lines": len(invalid_lines),
                },
                ensure_ascii=False,
            )
        )
        return 0

    print(
        json.dumps(
            {
                "status": "claimed",
                "id": selected.get("id"),
                "runner_id": selected.get("runner_id"),
                "attempt_count": selected.get("attempt_count"),
                "timestamp": selected.get("timestamp"),
                "prompt": selected.get("prompt"),
                "spoken_prompt": selected.get("spoken_prompt"),
            },
            ensure_ascii=False,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair and report Arthur prompt queue state.")
    parser.add_argument("--repair", action="store_true", help="repair stale in-flight prompts and block exhausted retries")
    parser.add_argument("--status", action="store_true", help="print queue status counts")
    parser.add_argument("--claim-next", action="store_true", help="claim and print the oldest runnable pending prompt")
    parser.add_argument("--runner-id", default=None)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--stale-running-seconds", type=int, default=20 * 60)
    parser.add_argument("--stale-pending-seconds", type=int, default=10 * 60)
    parser.add_argument("--max-pending-age-seconds", type=int, default=60 * 60)
    parser.add_argument("--clear-blocked-after-seconds", type=int, default=30 * 60)
    args = parser.parse_args()

    if args.repair:
        return repair_queue(
            stale_running_seconds=args.stale_running_seconds,
            stale_pending_seconds=args.stale_pending_seconds,
            max_pending_age_seconds=args.max_pending_age_seconds,
            clear_blocked_after_seconds=args.clear_blocked_after_seconds,
            quiet=args.quiet,
        )
    if args.claim_next:
        return claim_next(args.runner_id)
    return print_status()


if __name__ == "__main__":
    raise SystemExit(main())
