import argparse
import json
import pathlib
import tempfile
from typing import Any

from arthur_config import get_path, self_email
from arthur_prompt_worker import iso_timestamp


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
HANDOFF_FILE = SCRATCH / "arthur_email_handoff.jsonl"
RESPONSES_FILE = SCRATCH / "arthur_prompt_responses.jsonl"


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


def replace_response(prompt_id: str, response: str) -> None:
    entries = read_jsonl(RESPONSES_FILE)
    replacement = {"id": prompt_id, "completed_at": iso_timestamp(), "response": response}
    for index, entry in enumerate(entries):
        if str(entry.get("id")) == prompt_id:
            entries[index] = replacement
            write_jsonl(RESPONSES_FILE, entries)
            return
    entries.append(replacement)
    write_jsonl(RESPONSES_FILE, entries)


def validate(entry: dict[str, Any]) -> str | None:
    handoff_type = entry.get("type")
    if handoff_type not in {"self_email", "scout_self_email_prompt"}:
        return "handoff type is not supported"
    allowed = self_email().lower()
    recipients = [str(item).lower() for item in entry.get("to", [])]
    if not allowed or recipients != [allowed]:
        return "handoff recipient does not match configured self-email"
    if entry.get("cc") or entry.get("bcc"):
        return "handoff contains cc or bcc recipients"
    if not entry.get("subject"):
        return "handoff is missing subject"
    if handoff_type == "self_email" and not entry.get("body"):
        return "handoff is missing subject or body"
    if handoff_type == "scout_self_email_prompt" and not entry.get("source_prompt"):
        return "handoff is missing source prompt"
    return None


def next_pending() -> int:
    entries = read_jsonl(HANDOFF_FILE)
    for entry in entries:
        if entry.get("status") == "pending":
            reason = validate(entry)
            if reason:
                entry["status"] = "blocked"
                entry["blocked_at"] = iso_timestamp()
                entry["block_reason"] = reason
                write_jsonl(HANDOFF_FILE, entries)
                if entry.get("prompt_id"):
                    replace_response(str(entry["prompt_id"]), f"Email handoff blocked: {reason}.")
                print(json.dumps({"status": "blocked", "id": entry.get("id"), "reason": reason}, ensure_ascii=False))
                return 0
            print(json.dumps({"status": "pending", **entry}, ensure_ascii=False))
            return 0
    print(json.dumps({"status": "no_pending", "message": "No Arthur email handoff pending."}, ensure_ascii=False))
    return 0


def mark_sent(handoff_id: str, response: str) -> int:
    entries = read_jsonl(HANDOFF_FILE)
    for entry in entries:
        if str(entry.get("id")) == handoff_id:
            spoken_response = response
            if not spoken_response.lower().startswith("arthur email handoff sender completed"):
                spoken_response = f"Arthur Email Handoff Sender completed. {spoken_response}"
            entry["status"] = "sent"
            entry["sent_at"] = iso_timestamp()
            write_jsonl(HANDOFF_FILE, entries)
            if entry.get("prompt_id"):
                replace_response(str(entry["prompt_id"]), spoken_response)
            print(json.dumps({"status": "sent", "id": handoff_id, "response": spoken_response}, ensure_ascii=False))
            return 0
    print(json.dumps({"status": "not_found", "id": handoff_id}, ensure_ascii=False))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Arthur email handoff helper.")
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--mark-sent")
    parser.add_argument("--response", default="Sent to your inbox.")
    args = parser.parse_args()
    if args.next:
        return next_pending()
    if args.mark_sent:
        return mark_sent(args.mark_sent, args.response)
    return next_pending()


if __name__ == "__main__":
    raise SystemExit(main())
