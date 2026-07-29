import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Any

from arthur_config import get_config, get_path, self_email


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
QUEUE_FILE = SCRATCH / "arthur_prompt_queue.jsonl"
RESPONSES_FILE = SCRATCH / "arthur_prompt_responses.jsonl"
WATCHDOG_SCRIPT = SCRATCH / "arthur_queue_watchdog.py"
WORKER_LOG = SCRATCH / "arthur_prompt_worker.log"
WORKER_HEARTBEAT_FILE = SCRATCH / "arthur_prompt_worker_heartbeat.json"
ESCALATIONS_FILE = SCRATCH / "arthur_prompt_escalations.jsonl"
EMAIL_HANDOFF_FILE = SCRATCH / "arthur_email_handoff.jsonl"
SCOUT_HANDOFF_FILE = SCRATCH / "arthur_scout_handoff.jsonl"
WORKIQ = get_path("runtime.workiqPath", str(pathlib.Path.home() / ".copilot" / "bin" / "workiq.cmd"))


@dataclass
class HandlerResult:
    status: str
    response: str
    reason: str | None = None


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def iso_timestamp() -> str:
    return now().isoformat()


def log(message: str) -> None:
    line = f"[{now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    with WORKER_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def write_json_atomic(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        temp_name = handle.name
    pathlib.Path(temp_name).replace(path)


def write_heartbeat(status: str, **extra: Any) -> None:
    payload = {"status": status, "timestamp": iso_timestamp(), "pid": os.getpid(), **extra}
    write_json_atomic(WORKER_HEARTBEAT_FILE, payload)


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            entries.append(value)
    return entries


def write_jsonl(path: pathlib.Path, entries: list[dict[str, Any]]) -> None:
    payload = "\n".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) for entry in entries)
    if payload:
        payload += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent), newline="\n") as handle:
        handle.write(payload)
        temp_name = handle.name
    pathlib.Path(temp_name).replace(path)


def append_jsonl(path: pathlib.Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")


def update_entry(prompt_id: str, **fields: Any) -> dict[str, Any] | None:
    entries = read_jsonl(QUEUE_FILE)
    updated: dict[str, Any] | None = None
    for entry in entries:
        if str(entry.get("id")) == prompt_id:
            for key, value in fields.items():
                if value is None:
                    entry.pop(key, None)
                else:
                    entry[key] = value
            updated = entry
            break
    if updated is not None:
        write_jsonl(QUEUE_FILE, entries)
    return updated


def append_response(prompt_id: str, response: str) -> None:
    entries = read_jsonl(RESPONSES_FILE)
    replacement = {"id": prompt_id, "completed_at": iso_timestamp(), "response": response}
    replaced = False
    for index, entry in enumerate(entries):
        if str(entry.get("id")) == prompt_id:
            entries[index] = replacement
            replaced = True
            break
    if replaced:
        write_jsonl(RESPONSES_FILE, entries)
    else:
        append_jsonl(RESPONSES_FILE, replacement)


def claim_next(runner_id: str) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(WATCHDOG_SCRIPT), "--claim-next", "--runner-id", runner_id],
        capture_output=True,
        text=True,
        timeout=60,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "claim-next failed").strip())
    output = (result.stdout or "").strip().splitlines()[-1]
    return json.loads(output)


def run_repair() -> None:
    subprocess.run(
        [sys.executable, str(WATCHDOG_SCRIPT), "--repair", "--quiet"],
        capture_output=True,
        text=True,
        timeout=60,
    )


def run_workiq(prompt: str, timeout: int = 240, max_chars: int = 900) -> HandlerResult:
    if not WORKIQ.exists():
        return HandlerResult("blocked", "Needs Scout/manual escalation: WorkIQ is not available locally.", "WorkIQ executable is missing.")
    command = [str(WORKIQ), "ask", "-q", prompt]
    if WORKIQ.suffix.lower() in {".cmd", ".bat"}:
        command = ["cmd.exe", "/c", *command]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or result.stderr or "").strip()
    if "accept the End User License Agreement" in output or "workiq accept-eula" in output:
        return HandlerResult("blocked", "Needs Scout/manual escalation: WorkIQ EULA must be accepted.", "WorkIQ EULA is not accepted.")
    if result.returncode != 0:
        return HandlerResult("failed", f"WorkIQ returned an error: {output[:500]}", output[:1000])
    return HandlerResult("completed", output[:max_chars] if output else "Done.")


def run_local_command(args: list[str], timeout: int = 180) -> HandlerResult:
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    output = (result.stdout or result.stderr or "").strip()
    if result.returncode != 0:
        return HandlerResult("failed", f"Local command failed: {output[:500]}", output[:1000])
    return HandlerResult("completed", output[:900] if output else "Done.")


def has_only_self_email(prompt: str) -> bool:
    emails = {item.lower() for item in re.findall(r"[\w.\-+]+@[\w.\-]+\.\w+", prompt)}
    configured = self_email().lower()
    return bool(configured) and (not emails or emails == {configured})


def current_date_label() -> str:
    return now().strftime("%B %-d, %Y") if os.name != "nt" else now().strftime("%B %#d, %Y")


def strip_email_send_instruction(prompt: str) -> str:
    patterns = [
        r"\s+Send a Daily Briefing email addressed only to .*",
        r"\s+Send the completed report as an email .*",
        r"\s+After sending, .*",
    ]
    cleaned = prompt
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


def queue_self_email_handoff(prompt_id: str, subject: str, body: str, source_prompt: str) -> None:
    entry = {
        "id": f"email-{prompt_id}",
        "prompt_id": prompt_id,
        "created_at": iso_timestamp(),
        "status": "pending",
        "type": "self_email",
        "to": [self_email()],
        "subject": subject,
        "body": body,
        "is_html": False,
        "source": "arthur_prompt_worker",
        "source_prompt": source_prompt,
        "response_after_send": "Sent to your inbox.",
    }
    append_jsonl(EMAIL_HANDOFF_FILE, entry)


def queue_scout_self_email_prompt_handoff(prompt_id: str, subject: str, source_prompt: str) -> None:
    entry = {
        "id": f"email-{prompt_id}",
        "prompt_id": prompt_id,
        "created_at": iso_timestamp(),
        "status": "pending",
        "type": "scout_self_email_prompt",
        "to": [self_email()],
        "subject": subject,
        "source": "arthur_prompt_worker",
        "source_prompt": source_prompt,
        "response_after_send": "Sent to your inbox.",
    }
    append_jsonl(EMAIL_HANDOFF_FILE, entry)


def queue_scout_task_handoff(prompt_id: str, source_prompt: str, task_type: str, response_after_completion: str) -> None:
    entry = {
        "id": f"scout-{prompt_id}",
        "prompt_id": prompt_id,
        "created_at": iso_timestamp(),
        "status": "pending",
        "type": task_type,
        "source": "arthur_prompt_worker",
        "source_prompt": source_prompt,
        "response_after_completion": response_after_completion,
    }
    append_jsonl(SCOUT_HANDOFF_FILE, entry)


def handle_daily_briefing_split(prompt_id: str, prompt: str) -> HandlerResult:
    subject = f"Daily Briefing - {current_date_label()}"
    queue_scout_self_email_prompt_handoff(prompt_id, subject, prompt)
    return HandlerResult("completed", "Daily briefing queued for Scout email generation and delivery.")


def handle_action_tracker_handoff(prompt_id: str, prompt: str) -> HandlerResult:
    response = "Updated and sent to your Teams chat."
    queue_scout_task_handoff(prompt_id, prompt, "action_tracker", response)
    return HandlerResult("completed", "Action Tracker update queued for Scout processing.")


def classify_and_execute(prompt_id: str, prompt: str, spoken_prompt: str | None) -> HandlerResult:
    lowered = prompt.lower().strip()
    spoken = (spoken_prompt or "").strip()

    if len(lowered) < 8 or lowered in {"open", "even", "start", "run"}:
        return HandlerResult("blocked", "I need more detail to complete that request.", "Prompt was incomplete.")

    if any(term in lowered for term in ("queue status", "arthur queue", "watchdog status")):
        return run_local_command([sys.executable, str(WATCHDOG_SCRIPT), "--status"], timeout=60)

    if "cleanup" in lowered and "arthur" in lowered:
        return run_local_command([sys.executable, str(SCRATCH / "arthur_cleanup_chats.py"), "--max-age-hours", "4"], timeout=180)

    if any(term in lowered for term in ("action tracker", "azure devops", "ado work item", "work item")):
        return handle_action_tracker_handoff(prompt_id, prompt)

    if any(term in lowered for term in ("playwright", "browser automation", "coreidentity", "review all entitlements", "pending access approvals", "approve entitlement")):
        return HandlerResult("blocked", "Needs Scout/manual escalation: browser or approval automation is not supported by the local worker.", "Browser/risky approval flow.")

    if "daily briefing" in lowered and "send" in lowered and "email" in lowered and has_only_self_email(prompt):
        return handle_daily_briefing_split(prompt_id, prompt)

    if "send" in lowered and "email" in lowered:
        if not has_only_self_email(prompt):
            return HandlerResult("blocked", "Needs Scout/manual escalation: outbound email recipient is not the configured self-email.", "Outbound email recipient is not self-only.")
        return HandlerResult(
            "blocked",
            "Needs Scout/manual escalation: local worker cannot send email directly.",
            "Self-email send requires Scout/M365 tools rather than local WorkIQ.",
        )

    if any(term in lowered for term in ("email", "teams", "calendar", "meeting", "brief", "summary", "inbox", "workiq")):
        return run_workiq(prompt)

    append_jsonl(ESCALATIONS_FILE, {"id": None, "created_at": iso_timestamp(), "spoken_prompt": spoken, "prompt": prompt, "reason": "No local handler matched."})
    return HandlerResult("blocked", "Needs Scout/manual escalation: no local handler matched this request.", "No local handler matched.")


def process_once(runner_id: str) -> bool:
    run_repair()
    claim = claim_next(runner_id)
    if claim.get("status") == "no_runnable":
        write_heartbeat("idle", message=claim.get("message"))
        return False
    if claim.get("status") != "claimed":
        raise RuntimeError(f"Unexpected claim status: {claim}")

    prompt_id = str(claim["id"])
    prompt = str(claim.get("prompt") or "")
    spoken_prompt = str(claim.get("spoken_prompt") or "")
    log(f"Claimed prompt {prompt_id}: {spoken_prompt or prompt[:80]}")
    update_entry(prompt_id, status="running", last_heartbeat_at=iso_timestamp())
    write_heartbeat("running", prompt_id=prompt_id, spoken_prompt=spoken_prompt)

    try:
        result = classify_and_execute(prompt_id, prompt, spoken_prompt)
    except Exception as exc:  # Surface into queue state instead of crashing the worker loop.
        result = HandlerResult("failed", f"Local prompt worker failed: {type(exc).__name__}: {exc}", str(exc))

    completion_time = iso_timestamp()
    if result.status == "completed":
        update_entry(prompt_id, status="completed", completed_at=completion_time, last_heartbeat_at=completion_time)
        append_response(prompt_id, result.response)
        write_heartbeat("completed", prompt_id=prompt_id)
        log(f"Completed prompt {prompt_id}.")
        return True

    if result.status == "blocked":
        update_entry(
            prompt_id,
            status="blocked",
            completed_at=completion_time,
            last_heartbeat_at=completion_time,
            block_reason=result.reason or result.response,
        )
        append_response(prompt_id, result.response)
        write_heartbeat("blocked", prompt_id=prompt_id)
        log(f"Blocked prompt {prompt_id}: {result.reason or result.response}")
        return True

    update_entry(
        prompt_id,
        status="failed",
        completed_at=completion_time,
        last_heartbeat_at=completion_time,
        failure_reason=result.reason or result.response,
    )
    append_response(prompt_id, result.response)
    write_heartbeat("failed", prompt_id=prompt_id)
    log(f"Failed prompt {prompt_id}: {result.reason or result.response}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Arthur local prompt queue worker.")
    parser.add_argument("--interval-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    runner_id = f"arthur-local-worker-{os.getpid()}"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    log(f"Arthur prompt worker started: {runner_id}")
    while True:
        process_once(runner_id)
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
