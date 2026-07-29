import argparse
import json
import pathlib
import tempfile
from typing import Any

from arthur_config import get_path
from arthur_prompt_worker import iso_timestamp


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
HANDOFF_FILE = SCRATCH / "arthur_scout_handoff.jsonl"
RESPONSES_FILE = SCRATCH / "arthur_prompt_responses.jsonl"


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines() if line.strip()]


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


def next_pending() -> int:
    entries = read_jsonl(HANDOFF_FILE)
    for entry in entries:
        if entry.get("status") == "pending":
            print(json.dumps({"status": "pending", **entry}, ensure_ascii=False))
            return 0
    print(json.dumps({"status": "no_pending", "message": "No Arthur Scout handoff pending."}, ensure_ascii=False))
    return 0


def mark_done(handoff_id: str, response: str) -> int:
    entries = read_jsonl(HANDOFF_FILE)
    for entry in entries:
        if str(entry.get("id")) == handoff_id:
            entry["status"] = "completed"
            entry["completed_at"] = iso_timestamp()
            write_jsonl(HANDOFF_FILE, entries)
            if entry.get("prompt_id"):
                replace_response(str(entry["prompt_id"]), response)
            print(json.dumps({"status": "completed", "id": handoff_id, "response": response}, ensure_ascii=False))
            return 0
    print(json.dumps({"status": "not_found", "id": handoff_id}, ensure_ascii=False))
    return 1


def mark_failed(handoff_id: str, reason: str) -> int:
    entries = read_jsonl(HANDOFF_FILE)
    for entry in entries:
        if str(entry.get("id")) == handoff_id:
            entry["status"] = "failed"
            entry["failed_at"] = iso_timestamp()
            entry["failure_reason"] = reason
            write_jsonl(HANDOFF_FILE, entries)
            if entry.get("prompt_id"):
                replace_response(str(entry["prompt_id"]), f"Scout handoff failed: {reason}")
            print(json.dumps({"status": "failed", "id": handoff_id, "reason": reason}, ensure_ascii=False))
            return 0
    print(json.dumps({"status": "not_found", "id": handoff_id}, ensure_ascii=False))
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Arthur Scout task handoff helper.")
    parser.add_argument("--next", action="store_true")
    parser.add_argument("--mark-done")
    parser.add_argument("--mark-failed")
    parser.add_argument("--response", default="Done.")
    parser.add_argument("--reason", default="Unknown failure")
    args = parser.parse_args()
    if args.mark_done:
        return mark_done(args.mark_done, args.response)
    if args.mark_failed:
        return mark_failed(args.mark_failed, args.reason)
    return next_pending()


if __name__ == "__main__":
    raise SystemExit(main())
