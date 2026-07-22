import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time

from arthur_config import get_config, get_path


SCRATCH = get_path("runtime.scratchpadPath", str(pathlib.Path(__file__).resolve().parent))
BRIDGE_SCRIPT = SCRATCH / "arthur_voice_bridge.py"
CLEANUP_SCRIPT = SCRATCH / "arthur_cleanup_recordings.py"
CHAT_CLEANUP_SCRIPT = SCRATCH / "arthur_cleanup_chats.py"
WATCHDOG_SCRIPT = SCRATCH / "arthur_queue_watchdog.py"
AUTOMATION_FILE = get_path("runtime.automationFile", str(pathlib.Path.home() / ".copilot" / "m-automations" / "automations.json"))
SUPERVISOR_LOG = SCRATCH / "arthur_supervisor.log"
HEARTBEAT_FILE = SCRATCH / "arthur_voice_bridge_heartbeat.json"
BROWSER_STATE_FILE = SCRATCH / "arthur_browser_state.json"
PROMPT_QUEUE_FILE = SCRATCH / "arthur_prompt_queue.jsonl"
STDOUT_LOG = SCRATCH / "arthur_voice_bridge_stdout.log"
STDERR_LOG = SCRATCH / "arthur_voice_bridge_stderr.log"

ENABLED_AUTOMATIONS = {
    "Arthur Copilot prompt responder",
}
DISABLED_AUTOMATIONS = {
    "Arthur recording cleanup",
    "Arthur prompt queue executor",
    "Arthur voice transcript polling",
    "Arthur Copilot response startup",
}


def log(message: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    with SUPERVISOR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def run_powershell(command: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def bridge_process_ids() -> list[int]:
    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*arthur_voice_bridge.py*' -and $_.Name -match 'python' } | "
        "ForEach-Object { $_.ProcessId }"
    )
    result = run_powershell(command)
    if result.returncode != 0:
        log(f"Bridge process lookup failed: {(result.stderr or result.stdout).strip()[:300]}")
        return []
    return [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]


def stop_processes(process_ids: list[int]) -> None:
    if not process_ids:
        return
    ids_literal = "@(" + ",".join(str(pid) for pid in process_ids) + ")"
    run_powershell(
        f"$Ids = {ids_literal}; foreach ($id in $Ids) {{ "
        "$p = Get-Process -Id $id -ErrorAction SilentlyContinue; "
        "if ($p) { Stop-Process -Id $id -Force } }"
    )


def start_bridge(mic_device: int, tts: str, threshold: int | None) -> None:
    if not BRIDGE_SCRIPT.exists():
        raise FileNotFoundError(f"Arthur bridge script not found: {BRIDGE_SCRIPT}")
    args = [str(BRIDGE_SCRIPT), "--device", str(mic_device), "--tts", tts]
    if threshold is not None:
        args.extend(["--threshold", str(threshold)])
    stdout = STDOUT_LOG.open("a", encoding="utf-8")
    stderr = STDERR_LOG.open("a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, *args],
        cwd=str(SCRATCH),
        stdout=stdout,
        stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    log(f"Started Arthur bridge on mic index {mic_device}.")


def read_heartbeat() -> dict | None:
    if not HEARTBEAT_FILE.exists():
        return None
    try:
        return json.loads(HEARTBEAT_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        log("Heartbeat file is unreadable.")
        return None


def heartbeat_age_seconds() -> float | None:
    heartbeat = read_heartbeat()
    if not heartbeat:
        return None
    timestamp = heartbeat.get("timestamp")
    if not timestamp:
        return None
    try:
        value = dt.datetime.fromisoformat(str(timestamp))
    except ValueError:
        return None
    return (dt.datetime.now() - value).total_seconds()


def ensure_bridge(mic_device: int, tts: str, stale_seconds: int, threshold: int | None) -> None:
    processes = bridge_process_ids()
    age = heartbeat_age_seconds()
    if len(processes) > 1:
        stop_processes(processes[1:])
        log(f"Stopped duplicate Arthur bridge processes: {processes[1:]}")
    if not processes:
        start_bridge(mic_device, tts, threshold)
        return
    if age is not None and age > stale_seconds:
        log(f"Bridge heartbeat stale for {age:.0f}s; restarting bridge.")
        stop_processes(processes)
        start_bridge(mic_device, tts, threshold)


def ensure_automation_ownership() -> None:
    if not AUTOMATION_FILE.exists():
        log(f"Automation file not found: {AUTOMATION_FILE}")
        return
    try:
        automations = json.loads(AUTOMATION_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        log(f"Automation file is unreadable: {exc}")
        return
    if isinstance(automations, dict):
        automations = [automations]
    if not isinstance(automations, list):
        log("Automation file root is not a list or object; skipping automation reconciliation.")
        return
    changed = False
    for automation in automations:
        if not isinstance(automation, dict):
            log("Automation file contains a non-object entry; skipping that entry.")
            continue
        name = automation.get("name")
        if name in ENABLED_AUTOMATIONS and not automation.get("enabled"):
            automation["enabled"] = True
            changed = True
        if name in DISABLED_AUTOMATIONS and automation.get("enabled"):
            automation["enabled"] = False
            changed = True
    if changed:
        AUTOMATION_FILE.write_text(json.dumps(automations, indent=2), encoding="utf-8")
        log("Reconciled Arthur automation ownership.")


def run_queue_watchdog() -> None:
    if not WATCHDOG_SCRIPT.exists():
        log(f"Arthur queue watchdog script not found: {WATCHDOG_SCRIPT}")
        return
    result = subprocess.run(
        [
            sys.executable,
            str(WATCHDOG_SCRIPT),
            "--repair",
            "--quiet",
            "--stale-running-seconds",
            "1200",
            "--stale-pending-seconds",
            "600",
            "--max-pending-age-seconds",
            "3600",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        log(f"Queue watchdog failed: {(result.stderr or result.stdout).strip()[:500]}")


def pending_prompt_ages() -> list[tuple[str, float]]:
    if not PROMPT_QUEUE_FILE.exists():
        return []
    now = dt.datetime.now()
    ages: list[tuple[str, float]] = []
    for line in PROMPT_QUEUE_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            ages.append(("invalid-json", 0.0))
            continue
        if entry.get("status") != "pending":
            continue
        timestamp = entry.get("timestamp")
        try:
            created = dt.datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            created = now
        ages.append((str(entry.get("id") or "pending"), (now - created).total_seconds()))
    return ages


def report_stale_prompts(stale_seconds: int) -> None:
    for prompt_id, age in pending_prompt_ages():
        if age >= stale_seconds:
            log(f"Pending prompt {prompt_id} has been waiting {age:.0f}s.")


def close_idle_browser(idle_minutes: int) -> None:
    if not BROWSER_STATE_FILE.exists():
        return
    try:
        state = json.loads(BROWSER_STATE_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    timestamp = state.get("last_used_at") or state.get("opened_at")
    if not timestamp:
        return
    try:
        opened = dt.datetime.strptime(str(timestamp), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return
    if dt.datetime.now() - opened < dt.timedelta(minutes=idle_minutes):
        return
    profile = str(state.get("profile_dir") or SCRATCH / "arthur_edge_profile").replace("'", "''")
    run_powershell(
        f"$profile = '{profile}'; "
        "Get-CimInstance Win32_Process -Filter \"Name = 'msedge.exe'\" | "
        "Where-Object { $_.CommandLine -like \"*$profile*\" } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
    )
    BROWSER_STATE_FILE.unlink(missing_ok=True)
    log("Closed idle Arthur browser session.")


def run_cleanup() -> None:
    if not CLEANUP_SCRIPT.exists():
        return
    result = subprocess.run(
        [sys.executable, str(CLEANUP_SCRIPT), "--min-age-minutes", "20", "--max-log-kb", "512"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        log(f"Cleanup failed: {(result.stderr or result.stdout).strip()[:500]}")


def run_chat_cleanup() -> None:
    if not CHAT_CLEANUP_SCRIPT.exists():
        log(f"Chat cleanup script not found: {CHAT_CLEANUP_SCRIPT}")
        return
    result = subprocess.run(
        [
            sys.executable,
            str(CHAT_CLEANUP_SCRIPT),
            "--max-age-hours",
            str(get_config("runtime.cleanupChatArtifactsOlderThanHours", 4)),
            "--keep-latest-responses",
            "50",
            "--log-retention-days",
            str(get_config("runtime.logRetentionDays", 7)),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        log(f"Chat cleanup failed: {(result.stderr or result.stdout).strip()[:500]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Arthur local runtime supervisor.")
    parser.add_argument("--mic-device", type=int, default=int(os.environ.get("ARTHUR_MIC_DEVICE", str(get_config("microphone.deviceIndex", 1)))))
    parser.add_argument("--tts", choices=("edge", "windows"), default=os.environ.get("ARTHUR_TTS", str(get_config("voice.tts", "edge"))))
    parser.add_argument("--threshold", type=int, default=int(os.environ["ARTHUR_THRESHOLD"]) if os.environ.get("ARTHUR_THRESHOLD") else int(get_config("microphone.threshold", 350)))
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--stale-heartbeat-seconds", type=int, default=180)
    parser.add_argument("--stale-prompt-seconds", type=int, default=300)
    parser.add_argument("--browser-idle-minutes", type=int, default=30)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    last_cleanup = 0.0
    last_chat_cleanup = 0.0
    last_watchdog = 0.0
    log("Arthur supervisor started.")
    while True:
        ensure_automation_ownership()
        ensure_bridge(args.mic_device, args.tts, args.stale_heartbeat_seconds, args.threshold)
        if time.monotonic() - last_watchdog > 2 * 60:
            run_queue_watchdog()
            last_watchdog = time.monotonic()
        report_stale_prompts(args.stale_prompt_seconds)
        close_idle_browser(args.browser_idle_minutes)
        if time.monotonic() - last_cleanup > 20 * 60:
            run_cleanup()
            last_cleanup = time.monotonic()
        if time.monotonic() - last_chat_cleanup > float(get_config("runtime.chatCleanupIntervalMinutes", 45)) * 60:
            run_chat_cleanup()
            last_chat_cleanup = time.monotonic()
        if args.once:
            return 0
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
