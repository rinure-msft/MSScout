import argparse
import asyncio
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from arthur_config import DEFAULT_CONFIG_PATH, CONFIG, get_config, get_path, validate_config


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
PREFLIGHT_FILE = SCRATCH / "arthur_preflight_status.json"
REQUIRED_PACKAGES = (
    "edge_tts",
    "numpy",
    "pyttsx3",
    "pygame",
    "sounddevice",
    "faster_whisper",
    "scipy",
)


def check(name: str, ok: bool, detail: str, severity: str = "error") -> dict[str, Any]:
    return {"name": name, "ok": ok, "severity": severity, "detail": detail}


def run_command(command: list[str], timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    output = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, output[:500]


def check_python() -> dict[str, Any]:
    version = sys.version_info
    ok = version >= (3, 11)
    return check("Python version", ok, f"{version.major}.{version.minor}.{version.micro}; required >= 3.11")


def check_packages() -> list[dict[str, Any]]:
    results = []
    for package in REQUIRED_PACKAGES:
        found = importlib.util.find_spec(package) is not None
        results.append(check(f"Python package: {package}", found, "installed" if found else "missing"))
    return results


def check_config(strict: bool) -> list[dict[str, Any]]:
    path = pathlib.Path(str(get_config("configPath", DEFAULT_CONFIG_PATH)))
    errors = validate_config(CONFIG, DEFAULT_CONFIG_PATH)
    if not strict and errors:
        return [check("Arthur config", True, "Config-dependent checks skipped until arthur.config.json is filled.", "warning")]
    return [check("Arthur config", not errors, "; ".join(errors) if errors else f"valid: {path}")]


def check_mic(strict: bool) -> dict[str, Any]:
    try:
        import sounddevice as sd

        index = int(get_config("microphone.deviceIndex"))
        device = sd.query_devices(index)
        channels = int(device.get("max_input_channels", 0))
        ok = channels > 0
        return check("Microphone device", ok, f"index={index}; name={device.get('name')}; input_channels={channels}")
    except Exception as exc:
        return check("Microphone device", not strict, f"{type(exc).__name__}: {exc}", "warning" if not strict else "error")


async def save_edge_sample(path: pathlib.Path) -> None:
    import edge_tts

    voice = str(get_config("voice.edgeVoice", "en-US-BrianNeural"))
    await edge_tts.Communicate("Arthur preflight TTS check.", voice).save(str(path))


def check_edge_tts(strict: bool) -> dict[str, Any]:
    path = SCRATCH / "arthur_preflight_tts.mp3"
    try:
        asyncio.run(asyncio.wait_for(save_edge_sample(path), timeout=30))
        size = path.stat().st_size
        ok = size > 0
        return check("Edge TTS", ok, f"generated sample bytes={size}")
    except Exception as exc:
        return check("Edge TTS", not strict, f"{type(exc).__name__}: {exc}", "warning" if not strict else "error")
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def check_workiq(strict: bool) -> dict[str, Any]:
    path = pathlib.Path(str(get_config("runtime.workiqPath", "")))
    ok = path.exists()
    return check("WorkIQ path", ok or not strict, str(path) if ok else f"missing: {path}", "warning" if not strict and not ok else "error")


def check_tool(tool: str) -> dict[str, Any]:
    path = shutil.which(tool)
    if not path:
        return check(f"{tool} availability", False, "not found on PATH")
    ok, output = run_command([tool, "--version"])
    return check(f"{tool} availability", ok, output or path)


def check_write_access() -> dict[str, Any]:
    try:
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(SCRATCH), prefix="arthur_preflight_", suffix=".tmp") as handle:
            handle.write("ok")
            temp_name = handle.name
        pathlib.Path(temp_name).unlink(missing_ok=True)
        return check("Scratchpad write access", True, str(SCRATCH))
    except Exception as exc:
        return check("Scratchpad write access", False, f"{type(exc).__name__}: {exc}")


def run_preflight(strict: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(check_python())
    checks.extend(check_packages())
    checks.extend(check_config(strict))
    checks.append(check_mic(strict))
    checks.append(check_edge_tts(strict))
    checks.append(check_workiq(strict))
    checks.append(check_tool("git"))
    checks.append(check_tool("gh"))
    checks.append(check_write_access())
    failed = [item for item in checks if not item["ok"] and item["severity"] == "error"]
    warnings = [item for item in checks if (not item["ok"] or item["severity"] == "warning") and item["severity"] != "error"]
    return {
        "status": "failed" if failed else "passed",
        "strict": strict,
        "failed": len(failed),
        "warnings": len(warnings),
        "checks": checks,
    }


def write_status(status: dict[str, Any]) -> None:
    PREFLIGHT_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Arthur install/startup preflight checks.")
    parser.add_argument("--strict", action="store_true", help="Fail config-dependent checks instead of warning/skipping.")
    parser.add_argument("--write", action="store_true", help="Write arthur_preflight_status.json.")
    args = parser.parse_args()
    status = run_preflight(strict=args.strict)
    if args.write:
        write_status(status)
    print(json.dumps(status, indent=2))
    return 0 if status["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
