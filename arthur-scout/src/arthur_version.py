import argparse
import datetime as dt
import hashlib
import json
import pathlib
import subprocess
from typing import Any

from arthur_config import get_path


PACKAGE_VERSION = "0.4.0"
SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
VERSION_FILE = SCRATCH / "arthur.version.json"
CHECKSUM_PATTERNS = (
    "arthur_*.py",
    "Start-Arthur.ps1",
    "arthur.config.json",
)


def now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def live_files() -> list[pathlib.Path]:
    files: dict[str, pathlib.Path] = {}
    for pattern in CHECKSUM_PATTERNS:
        for path in SCRATCH.glob(pattern):
            if path.is_file():
                files[path.name] = path
    return [files[name] for name in sorted(files)]


def collect_checksums() -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in live_files():
        checksums[path.name] = sha256_file(path)
    return checksums


def read_existing() -> dict[str, Any]:
    if not VERSION_FILE.exists():
        return {}
    try:
        data = json.loads(VERSION_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def git_commit_sha(path: pathlib.Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def build_manifest(commit_sha: str | None = None, install_time: str | None = None) -> dict[str, Any]:
    existing = read_existing()
    commit = commit_sha or str(existing.get("commitSha") or "") or git_commit_sha(SCRATCH) or "unknown"
    installed = install_time or str(existing.get("installTime") or "") or now()
    return {
        "packageVersion": PACKAGE_VERSION,
        "commitSha": commit,
        "installTime": installed,
        "generatedAt": now(),
        "scratchpadPath": str(SCRATCH),
        "checksums": collect_checksums(),
    }


def write_manifest(commit_sha: str | None = None, install_time: str | None = None) -> dict[str, Any]:
    manifest = build_manifest(commit_sha=commit_sha, install_time=install_time)
    VERSION_FILE.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Arthur version manifest.")
    parser.add_argument("--write", action="store_true", help="Write arthur.version.json.")
    parser.add_argument("--commit-sha", default=None, help="Package git commit SHA to record.")
    parser.add_argument("--install-time", default=None, help="Install timestamp to record.")
    args = parser.parse_args()
    manifest = write_manifest(args.commit_sha, args.install_time) if args.write else build_manifest(args.commit_sha, args.install_time)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
