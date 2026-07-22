import argparse
import datetime as dt
import json
import pathlib
import shutil
import tempfile
from typing import Any

from arthur_config import get_path


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
ARCHIVE_DIR = SCRATCH / "arthur_archive"
CHAT_CLEANUP_LOG = SCRATCH / "arthur_chat_cleanup.log"
PROMPT_QUEUE_FILE = SCRATCH / "arthur_prompt_queue.jsonl"
PROMPT_RESPONSES_FILE = SCRATCH / "arthur_prompt_responses.jsonl"

ACTIVE_QUEUE_STATUSES = {"pending", "claimed", "running"}
REVIEW_QUEUE_STATUSES = {"blocked", "failed"}

DELETE_PATTERNS = [
    "arthur_bridge_utterance_*.wav",
    "arthur_live_instruction_*.wav",
    "arthur_edge_tts_*.mp3",
    "arthur_prompt_draft*.json",
    "arthur_prompt_draft*.jsonl",
    "arthur_prompt_draft*.md",
    "arthur_prompt_draft*.txt",
    "arthur_chat_scratch*.json",
    "arthur_chat_scratch*.jsonl",
    "arthur_chat_scratch*.md",
    "arthur_chat_scratch*.txt",
    "arthur_browser_state.json",
]

LOG_RETENTION_PATTERNS = [
    "arthur_*_cleanup.log",
    "arthur_queue_watchdog.log",
    "arthur_supervisor.log",
    "arthur_voice_bridge_stdout.log",
    "arthur_voice_bridge_stderr.log",
    "arthur_voice_bridge_commands.log",
    "arthur_voice_bridge_transcript.log",
    "arthur_voice_transcript.log",
]


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def log(message: str) -> None:
    timestamp = now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with CHAT_CLEANUP_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def file_age(path: pathlib.Path) -> dt.timedelta:
    return now() - dt.datetime.fromtimestamp(path.stat().st_mtime).astimezone()


def parse_timestamp(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=now().tzinfo)
    return parsed.astimezone()


def entry_age(entry: dict[str, Any]) -> dt.timedelta | None:
    for key in ("completed_at", "timestamp", "created_at"):
        parsed = parse_timestamp(entry.get(key))
        if parsed is not None:
            return now() - parsed
    return None


def read_jsonl(path: pathlib.Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], []
    entries: list[dict[str, Any]] = []
    invalid_lines: list[str] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines.append(line)
            continue
        if isinstance(value, dict):
            entries.append(value)
        else:
            invalid_lines.append(line)
    return entries, invalid_lines


def write_jsonl(path: pathlib.Path, entries: list[dict[str, Any]]) -> None:
    payload = "\n".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) for entry in entries)
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
            handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


def archive_path(prefix: str) -> pathlib.Path:
    date = now().strftime("%Y%m%d")
    return ARCHIVE_DIR / f"{prefix}_{date}.jsonl"


def delete_old_artifacts(max_age: dt.timedelta, dry_run: bool) -> int:
    deleted = 0
    for pattern in DELETE_PATTERNS:
        for path in SCRATCH.glob(pattern):
            if not path.is_file():
                continue
            if file_age(path) < max_age:
                continue
            if dry_run:
                log(f"Would delete old chat artifact {path.name}")
            else:
                try:
                    path.unlink()
                    log(f"Deleted old chat artifact {path.name}")
                    deleted += 1
                except OSError as exc:
                    log(f"Failed to delete {path.name}: {type(exc).__name__}: {exc}")
    return deleted


def archive_completed_queue(max_age: dt.timedelta, dry_run: bool) -> int:
    entries, invalid = read_jsonl(PROMPT_QUEUE_FILE)
    if not entries and not invalid:
        return 0

    keep: list[dict[str, Any]] = []
    archive: list[dict[str, Any]] = []
    for entry in entries:
        status = str(entry.get("status") or "pending")
        age = entry_age(entry)
        if status in ACTIVE_QUEUE_STATUSES or status in REVIEW_QUEUE_STATUSES:
            keep.append(entry)
        elif status == "completed" and age is not None and age >= max_age:
            archive.append(entry)
        else:
            keep.append(entry)

    removed = len(archive) + len(invalid)
    if removed and dry_run:
        log(f"Would archive {len(archive)} completed queue entries and drop {len(invalid)} invalid queue lines.")
    elif removed:
        append_jsonl(archive_path("arthur_prompt_queue_completed"), archive)
        if invalid:
            invalid_entries = [{"archived_at": now().isoformat(), "invalid_line": line} for line in invalid]
            append_jsonl(archive_path("arthur_prompt_queue_invalid"), invalid_entries)
        write_jsonl(PROMPT_QUEUE_FILE, keep)
        log(f"Archived {len(archive)} completed queue entries; kept {len(keep)} active/recent/review entries.")
    return removed


def archive_response_history(max_age: dt.timedelta, keep_latest: int, dry_run: bool) -> int:
    entries, invalid = read_jsonl(PROMPT_RESPONSES_FILE)
    if not entries and not invalid:
        return 0

    latest_ids = {id(entry) for entry in entries[-keep_latest:]} if keep_latest > 0 else set()
    keep: list[dict[str, Any]] = []
    archive: list[dict[str, Any]] = []
    for entry in entries:
        age = entry_age(entry)
        if id(entry) in latest_ids or age is None or age < max_age:
            keep.append(entry)
        else:
            archive.append(entry)

    removed = len(archive) + len(invalid)
    if removed and dry_run:
        log(f"Would archive {len(archive)} response entries and drop {len(invalid)} invalid response lines.")
    elif removed:
        append_jsonl(archive_path("arthur_prompt_responses"), archive)
        if invalid:
            invalid_entries = [{"archived_at": now().isoformat(), "invalid_line": line} for line in invalid]
            append_jsonl(archive_path("arthur_prompt_responses_invalid"), invalid_entries)
        write_jsonl(PROMPT_RESPONSES_FILE, keep)
        log(f"Archived {len(archive)} response entries; kept {len(keep)} recent/latest responses.")
    return removed


def prune_archive_logs(log_retention: dt.timedelta, dry_run: bool) -> int:
    if not ARCHIVE_DIR.exists():
        return 0
    deleted = 0
    for pattern in LOG_RETENTION_PATTERNS:
        for path in ARCHIVE_DIR.glob(pattern.replace(".log", "_*.log")):
            if path.is_file() and file_age(path) >= log_retention:
                if dry_run:
                    log(f"Would delete old archived log {path.name}")
                else:
                    path.unlink()
                    log(f"Deleted old archived log {path.name}")
                    deleted += 1
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean local Arthur/Scout chat artifacts while preserving durable queue state.")
    parser.add_argument("--max-age-hours", type=float, default=4.0)
    parser.add_argument("--keep-latest-responses", type=int, default=50)
    parser.add_argument("--log-retention-days", type=float, default=7.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    max_age = dt.timedelta(hours=args.max_age_hours)
    log_retention = dt.timedelta(days=args.log_retention_days)

    deleted = delete_old_artifacts(max_age, args.dry_run)
    archived_queue = archive_completed_queue(max_age, args.dry_run)
    archived_responses = archive_response_history(max_age, args.keep_latest_responses, args.dry_run)
    pruned_logs = prune_archive_logs(log_retention, args.dry_run)

    log(
        f"Chat cleanup complete: deleted artifacts={deleted}, archived queue entries={archived_queue}, "
        f"archived responses={archived_responses}, pruned archived logs={pruned_logs}, dry_run={args.dry_run}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
