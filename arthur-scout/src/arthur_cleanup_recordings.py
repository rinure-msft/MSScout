import argparse
import csv
import datetime as dt
import pathlib
import re
import shutil


SCRATCH = pathlib.Path(r"C:\Users\riur\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad")
HISTORY_CSV = SCRATCH / "arthur_voice_command_history.csv"
HISTORY_MD = SCRATCH / "arthur_voice_command_history.md"
CLEANUP_LOG = SCRATCH / "arthur_recording_cleanup.log"
ARCHIVE_DIR = SCRATCH / "arthur_archive"

LOG_SOURCES = [
    SCRATCH / "arthur_voice_bridge_transcript.log",
    SCRATCH / "arthur_voice_bridge_commands.log",
    SCRATCH / "arthur_voice_transcript.log",
]

MEDIA_PATTERNS = [
    "arthur_bridge_utterance_*.wav",
    "arthur_live_instruction_*.wav",
    "arthur_edge_tts_*.mp3",
    "mic_validation*.wav",
    "recording_*.wav",
    "davis_test.mp3",
    "brian_test.mp3",
]

ROTATE_PATTERNS = [
    "arthur_voice_bridge_transcript.log",
    "arthur_voice_bridge_commands.log",
    "arthur_voice_bridge_stdout.log",
    "arthur_voice_bridge_stderr.log",
    "arthur_recording_cleanup.log",
]

QUEUE_FILES = [
    SCRATCH / "arthur_prompt_queue.jsonl",
    SCRATCH / "arthur_prompt_responses.jsonl",
]


def log(message: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with CLEANUP_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def classify(message: str) -> tuple[str, str] | None:
    prefixes = {
        "Heard: ": "Transcript",
        "Rin said: ": "Transcript",
        "Command: ": "Command",
        "Using pending wake word for: ": "Pending wake command",
        "Unrouted instruction for Copilot: ": "Unrouted command",
    }
    for prefix, kind in prefixes.items():
        if message.startswith(prefix):
            return kind, message[len(prefix) :].strip()
    return None


def read_existing_rows() -> list[dict[str, str]]:
    if not HISTORY_CSV.exists():
        return []
    with HISTORY_CSV.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def collect_rows() -> list[dict[str, str]]:
    rows = []
    pattern = re.compile(r"^\[(?P<timestamp>[^\]]+)\]\s+(?P<message>.*)$")
    for source in LOG_SOURCES:
        if not source.exists():
            continue
        for line in source.read_text(encoding="utf-8", errors="replace").splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            classified = classify(match.group("message"))
            if classified is None:
                continue
            kind, text = classified
            rows.append(
                {
                    "timestamp": match.group("timestamp"),
                    "type": kind,
                    "text": text,
                    "source": source.name,
                }
            )
    return rows


def write_history(rows: list[dict[str, str]]) -> None:
    rows = sorted(rows, key=lambda row: row["timestamp"])
    with HISTORY_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "type", "text", "source"])
        writer.writeheader()
        writer.writerows(rows)

    def cell(value: str) -> str:
        return value.replace("|", "\\|").replace("\n", " ").strip()

    lines = [
        "# Arthur Voice Command History",
        "",
        f"Updated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Timestamp | Type | Command / Transcript | Source |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append(f"| {cell(row['timestamp'])} | {cell(row['type'])} | {cell(row['text'])} | {cell(row['source'])} |")
    HISTORY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cleanup_media(min_age_minutes: int, dry_run: bool) -> int:
    cutoff = dt.datetime.now() - dt.timedelta(minutes=min_age_minutes)
    deleted = 0
    for pattern in MEDIA_PATTERNS:
        for path in SCRATCH.glob(pattern):
            if not path.is_file():
                continue
            modified = dt.datetime.fromtimestamp(path.stat().st_mtime)
            if modified > cutoff:
                continue
            if dry_run:
                log(f"Would delete {path.name}")
            else:
                path.unlink()
                deleted += 1
                log(f"Deleted {path.name}")
    return deleted


def rotate_large_logs(max_log_kb: int, dry_run: bool) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    rotated = 0
    max_bytes = max_log_kb * 1024
    for pattern in ROTATE_PATTERNS:
        for path in SCRATCH.glob(pattern):
            if not path.is_file() or path.stat().st_size <= max_bytes:
                continue
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive = ARCHIVE_DIR / f"{path.stem}_{stamp}{path.suffix}"
            if dry_run:
                log(f"Would rotate {path.name} to {archive.name}")
            else:
                shutil.copy2(path, archive)
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
                path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
                rotated += 1
                log(f"Rotated {path.name} to {archive.name}")
    return rotated


def compact_jsonl(path: pathlib.Path, keep_completed: int, dry_run: bool) -> tuple[int, int]:
    if not path.exists():
        return 0, 0
    entries = []
    invalid = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json_loads(line))
        except ValueError:
            invalid.append(line)
    pending = [entry for entry in entries if entry.get("status") == "pending"]
    completed = [entry for entry in entries if entry.get("status") != "pending"]
    kept = pending + completed[-keep_completed:]
    removed = max(0, len(entries) - len(kept)) + len(invalid)
    if removed and not dry_run:
        path.write_text("\n".join(json_dumps(entry) for entry in kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed, len(kept)


def json_loads(line: str) -> dict[str, str]:
    import json

    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("JSONL entry is not an object")
    return value


def json_dumps(entry: dict[str, str]) -> str:
    import json

    return json.dumps(entry, ensure_ascii=False, separators=(",", ":"))


def compact_queues(keep_completed: int, dry_run: bool) -> int:
    removed_total = 0
    for path in QUEUE_FILES:
        removed, kept = compact_jsonl(path, keep_completed, dry_run)
        removed_total += removed
        if removed:
            log(f"{'Would compact' if dry_run else 'Compacted'} {path.name}: removed {removed}, kept {kept}.")
    return removed_total


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive Arthur voice commands and clean up recording files.")
    parser.add_argument("--min-age-minutes", type=int, default=30)
    parser.add_argument("--max-log-kb", type=int, default=512)
    parser.add_argument("--keep-completed-jsonl", type=int, default=200)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    existing = read_existing_rows()
    seen = {(row["timestamp"], row["type"], row["text"], row["source"]) for row in existing}
    new_rows = []
    for row in collect_rows():
        key = (row["timestamp"], row["type"], row["text"], row["source"])
        if key not in seen:
            new_rows.append(row)
            seen.add(key)

    all_rows = existing + new_rows
    write_history(all_rows)
    deleted = cleanup_media(args.min_age_minutes, args.dry_run)
    rotated = rotate_large_logs(args.max_log_kb, args.dry_run)
    compacted = compact_queues(args.keep_completed_jsonl, args.dry_run)
    log(
        f"History rows: {len(all_rows)}; new rows: {len(new_rows)}; "
        f"{'would delete' if args.dry_run else 'deleted'} files: {deleted}; "
        f"rotated logs: {rotated}; compacted JSONL entries: {compacted}."
    )
    log(f"History table: {HISTORY_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
