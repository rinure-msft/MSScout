import argparse
import asyncio
from dataclasses import dataclass
import datetime as dt
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import edge_tts
import numpy as np
import pyttsx3
import pygame
import sounddevice as sd
from faster_whisper import WhisperModel
from scipy.io import wavfile


SCRATCH = pathlib.Path(r"C:\Users\riur\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad")
TRANSCRIPT_LOG = SCRATCH / "arthur_voice_bridge_transcript.log"
COMMAND_LOG = SCRATCH / "arthur_voice_bridge_commands.log"
NOTES_FILE = SCRATCH / "arthur_voice_notes.txt"
DAILY_TASKS_FILE = SCRATCH / "arthur_daily_tasks.md"
VOICE_COMMAND_INDEX_FILE = SCRATCH / "arthur_voice_command_index.md"
PROMPT_QUEUE_FILE = SCRATCH / "arthur_prompt_queue.jsonl"
PROMPT_RESPONSE_FILE = SCRATCH / "arthur_prompt_responses.jsonl"
PROMPT_RESPONSE_STATE_FILE = SCRATCH / "arthur_prompt_response_state.json"
SHUTDOWN_REQUEST_FILE = SCRATCH / "arthur_shutdown_request.json"
BROWSER_STATE_FILE = SCRATCH / "arthur_browser_state.json"
BROWSER_PROFILE_DIR = SCRATCH / "arthur_edge_profile"
HEARTBEAT_FILE = SCRATCH / "arthur_voice_bridge_heartbeat.json"
WORKIQ = pathlib.Path(r"C:\Users\riur\.copilot\bin\workiq.cmd")
EDGE_VOICE = "en-US-BrianNeural"
DEFAULT_TIMEZONE = "Mountain Standard Time"
MAX_SPEECH_CHUNK_CHARS = 420
MIN_TRANSCRIBE_RMS = 120.0
MIN_TRANSCRIBE_PEAK = 700
WINDOWS_TIMEZONE_ALIASES = {
    "Mountain Standard Time": "America/Denver",
}
EMAIL_FOLDERS = (
    "Tier 1 (Leadership)",
    "Tier 2 (Stakeholders)",
    "Tier 3 (Partners)",
    "My To Action",
    "My Informed (CC)",
)
LAST_HEARD = ""
LAST_RESPONSE = ""
PENDING_WAKE_UNTIL = 0.0
CONFIGURED_MICROPHONE_DEVICE = "the configured microphone device"


@dataclass(frozen=True)
class Command:
    name: str
    aliases: tuple[str, ...]
    handler: str
    description: str


class Speaker:
    def __init__(self, mode: str, edge_voice: str) -> None:
        self.mode = mode
        self.edge_voice = edge_voice
        self.pyttsx3_engine = pyttsx3.init()
        self.edge_count = 0
        self.lock = threading.Lock()
        if self.mode == "edge":
            pygame.mixer.init()

    async def _save_edge_tts(self, text: str, path: pathlib.Path) -> None:
        communicate = edge_tts.Communicate(text, self.edge_voice)
        await communicate.save(str(path))

    def say(self, text: str) -> None:
        with self.lock:
            text = sanitize_for_speech(text)
            print(f"Arthur: {text}", flush=True)
            if self.mode == "edge":
                for chunk in split_for_speech(text):
                    try:
                        self.edge_count += 1
                        path = SCRATCH / f"arthur_edge_tts_{self.edge_count:04d}.mp3"
                        asyncio.run(asyncio.wait_for(self._save_edge_tts(chunk, path), timeout=15))
                        pygame.mixer.music.load(str(path))
                        pygame.mixer.music.play()
                        playback_started = time.monotonic()
                        try:
                            playback_timeout = max(8.0, pygame.mixer.Sound(str(path)).get_length() + 5.0)
                        except Exception:
                            playback_timeout = max(30.0, min(120.0, len(chunk) * 0.25))
                        while pygame.mixer.music.get_busy():
                            if time.monotonic() - playback_started > playback_timeout:
                                pygame.mixer.music.stop()
                                raise TimeoutError(f"Edge TTS playback exceeded {playback_timeout:.1f}s")
                            time.sleep(0.05)
                    except Exception as exc:
                        log(COMMAND_LOG, f"Edge TTS chunk failed; falling back to Windows voice: {type(exc).__name__}: {exc}")
                        self.pyttsx3_engine.say(chunk)
                        self.pyttsx3_engine.runAndWait()
                log(COMMAND_LOG, f"Spoke response using Edge TTS: {text[:120]}")
                return

            self.pyttsx3_engine.say(text)
            self.pyttsx3_engine.runAndWait()
            log(COMMAND_LOG, f"Spoke response using Windows voice: {text[:120]}")


def log(path: pathlib.Path, message: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line, flush=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def split_for_speech(text: str, limit: int = MAX_SPEECH_CHUNK_CHARS) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts: list[str] = []
    while len(text) > limit:
        split_at = max(text.rfind(marker, 0, limit) for marker in (". ", "; ", ", ", " "))
        if split_at < limit // 2:
            split_at = limit
        parts.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        parts.append(text)
    return parts


def sanitize_for_speech(text: str) -> str:
    replacements = {
        "âœ…": "[completed]",
        "ðŸ”": "[priority]",
        "ðŸ””": "[priority]",
        "ðŸ“…": "[invite]",
        "â€”": "-",
        "â€“": "-",
        "â€™": "'",
        "â€œ": '"',
        "â€": '"',
        "\u00a0": " ",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("ascii", errors="replace").decode("ascii")


def write_json_atomic(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: OSError | None = None
    for attempt in range(5):
        temp = path.with_suffix(path.suffix + f".{os.getpid()}.{attempt}.{random.randint(1000, 9999)}.tmp")
        try:
            temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp.replace(path)
            return
        except OSError as exc:
            last_error = exc
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            time.sleep(0.1 * (attempt + 1))
    if last_error:
        raise last_error


def write_heartbeat(status: str, **extra: object) -> None:
    payload = {
        "status": status,
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "pid": os.getpid(),
        **extra,
    }
    try:
        write_json_atomic(HEARTBEAT_FILE, payload)
    except OSError as exc:
        log(COMMAND_LOG, f"Heartbeat write failed: {type(exc).__name__}: {exc}")


def speak(speaker: Speaker, text: str) -> None:
    global LAST_RESPONSE
    LAST_RESPONSE = text
    write_heartbeat("speaking", preview=text[:120])
    speaker.say(text)
    write_heartbeat("listening")


def clean_transcript(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(" .")


def normalize_command_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^\w\s*']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_wake_word(text: str, wake_word: str) -> str | None:
    stripped = text.strip()
    lowered = stripped.lower()
    wake = re.escape(wake_word.lower())
    if lowered == wake_word.lower():
        return ""
    match = re.match(rf"^{wake}[\s,.:;!-]+(?P<command>.*)$", lowered, flags=re.IGNORECASE)
    if not match:
        match = re.search(rf"(?<!\w){wake}[\s,.:;!-]+(?P<command>.*)$", lowered, flags=re.IGNORECASE)
    if not match:
        return None
    return stripped[match.start("command") :].strip(" ,.:;-")


def calibrate_noise(device: int, samplerate: int, seconds: float) -> float:
    print(f"Calibrating background noise for {seconds:.1f}s. Stay quiet.", flush=True)
    audio = sd.rec(int(seconds * samplerate), samplerate=samplerate, channels=1, dtype="int16", device=device)
    sd.wait()
    arr = audio.astype(np.float32).reshape(-1)
    rms = float(np.sqrt(np.mean(arr * arr)))
    return max(250.0, rms * 3.0)


def record_utterance(
    device: int,
    samplerate: int,
    threshold: float,
    max_seconds: float,
    silence_seconds: float,
    idle_seconds: float,
) -> np.ndarray:
    block_seconds = 0.20
    block_samples = int(samplerate * block_seconds)
    silence_blocks_needed = max(1, int(silence_seconds / block_seconds))
    idle_blocks_needed = max(1, int(idle_seconds / block_seconds))
    max_blocks = max(1, int(max_seconds / block_seconds))

    chunks: list[np.ndarray] = []
    speech_started = False
    quiet_blocks = 0
    idle_blocks = 0

    with sd.InputStream(
        samplerate=samplerate,
        channels=1,
        dtype="int16",
        device=device,
        blocksize=block_samples,
    ) as stream:
        while len(chunks) < max_blocks:
            block, _ = stream.read(block_samples)
            arr = block.astype(np.float32).reshape(-1)
            rms = float(np.sqrt(np.mean(arr * arr)))

            if rms >= threshold:
                speech_started = True
                quiet_blocks = 0
                idle_blocks = 0
                chunks.append(block.copy())
            elif speech_started:
                quiet_blocks += 1
                chunks.append(block.copy())
                if quiet_blocks >= silence_blocks_needed:
                    break
            else:
                idle_blocks += 1
                if idle_blocks >= idle_blocks_needed:
                    break

    if not chunks:
        return np.empty((0, 1), dtype=np.int16)
    return np.concatenate(chunks, axis=0)


def record_utterance_with_timeout(
    timeout_seconds: float,
    **kwargs,
) -> np.ndarray:
    result: dict[str, object] = {}

    def target() -> None:
        try:
            result["audio"] = record_utterance(**kwargs)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"Microphone read exceeded {timeout_seconds:.1f}s")
    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result.get("audio", np.empty((0, 1), dtype=np.int16))  # type: ignore[return-value]


def should_transcribe(audio: np.ndarray, threshold: float) -> bool:
    if audio.size == 0:
        return False
    arr = audio.astype(np.float32).reshape(-1)
    rms = float(np.sqrt(np.mean(arr * arr)))
    peak = int(np.max(np.abs(arr)))
    return rms >= min(MIN_TRANSCRIBE_RMS, threshold * 0.75) or peak >= MIN_TRANSCRIBE_PEAK


def transcribe_audio(model: WhisperModel, path: pathlib.Path) -> str:
    segments, _ = model.transcribe(str(path), beam_size=1, vad_filter=True)
    return clean_transcript(" ".join(segment.text.strip() for segment in segments))


def open_process(command: list[str]) -> None:
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def run_workiq(question: str) -> str:
    if not WORKIQ.exists():
        return "WorkIQ is not installed at the expected path."
    result = subprocess.run(
        [str(WORKIQ), "ask", "-q", question],
        capture_output=True,
        text=True,
        timeout=90,
        encoding="utf-8",
        errors="replace",
    )
    output = (result.stdout or result.stderr or "").strip()
    if "accept the End User License Agreement" in output or "workiq accept-eula" in output:
        return "WorkIQ needs its End User License Agreement accepted before I can use Microsoft 365 voice commands."
    if result.returncode != 0:
        return f"WorkIQ returned an error: {strip_html(output)[:500]}"
    output = strip_html(output)
    return output[:900] if output else "I did not find anything to read."


def email_folder_instruction() -> str:
    folders = ", ".join(f"'{folder}'" for folder in EMAIL_FOLDERS)
    return f"When reading email, use only these Outlook folders: {folders}. "


def take_note(note: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {note}\n")


def write_daily_tasks_table(content: str) -> None:
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    DAILY_TASKS_FILE.write_text(
        f"# Arthur Daily Tasks\n\nGenerated: {timestamp}\n\n{content.strip()}\n",
        encoding="utf-8",
    )


def expand_prompt(prompt: str) -> str:
    lowered = prompt.lower()
    is_tracker_refresh = (
        ("workstream tracker" in lowered or "work stream tracker" in lowered or "task tracker" in lowered)
        and any(action in lowered for action in ("refresh", "update", "scan", "build"))
    )
    if not is_tracker_refresh:
        return prompt
    return (
        "Refresh Arthur's workstream tracker for Rin. Scan recent Outlook email, Teams messages/chats, "
        "and any available meeting transcripts or meeting chats for asks and relevant updates. Look for "
        "new or changed workstreams tied to Shara, Jacinta, Fraud Ops, Vet Ops, PLTO, ROB/MOR, L1/L2/L3 "
        "metrics, Bluehawk, Vendor AI KPI, Project Nova, CI, SharePoint, Documentation, ARIS updates and "
        "workflows. Update `C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\"
        "arthur_workstream_tracker.md` using these columns exactly: Done | Title | Type | Owner | Status | "
        "Priority | Next Action | Next Due Date | Last Updated | Notes/Update. Add new rows for distinct "
        "new workstreams. Update existing rows when owner, action, deadline, status, priority, or notes "
        "change. Use month-day date format. Keep the digest concise and only for Rin's use. If the mail, "
        "Teams, or meeting-transcript scan fails, keep/send the last known tracker and clearly note which "
        "refresh source failed."
    )


def enqueue_prompt(prompt: str) -> None:
    prompt_id = f"prompt-{dt.datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    expanded_prompt = expand_prompt(prompt)
    entry = {
        "id": prompt_id,
        "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "pending",
        "prompt": expanded_prompt,
        "spoken_prompt": prompt,
    }
    with PROMPT_QUEUE_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def request_service_shutdown(reason: str) -> None:
    SHUTDOWN_REQUEST_FILE.write_text(
        json.dumps(
            {
                "status": "pending",
                "requested_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "reason": reason,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_spoken_response_ids() -> set[str]:
    if not PROMPT_RESPONSE_STATE_FILE.exists():
        return set()
    try:
        data = json.loads(PROMPT_RESPONSE_STATE_FILE.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return set()
    return set(data.get("spoken_response_ids", []))


def save_spoken_response_ids(ids: set[str]) -> None:
    PROMPT_RESPONSE_STATE_FILE.write_text(
        json.dumps({"spoken_response_ids": sorted(ids)}, indent=2),
        encoding="utf-8",
    )


def poll_copilot_responses(speaker: Speaker) -> None:
    if not PROMPT_RESPONSE_FILE.exists():
        return
    spoken = load_spoken_response_ids()
    changed = False
    for line in PROMPT_RESPONSE_FILE.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = line.lstrip("\ufeff").strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        response_id = str(entry.get("id") or entry.get("prompt_id") or "")
        if not response_id or response_id in spoken:
            continue
        response = str(entry.get("response") or "").strip()
        if not response:
            continue
        spoken_response = sanitize_for_speech(response)
        log(COMMAND_LOG, f"Copilot response for {response_id}: {spoken_response}")
        spoken.add(response_id)
        save_spoken_response_ids(spoken)
        changed = False
        speak(
            speaker,
            "Sorry for the interruption, I have completed the item you asked for. "
            f"{spoken_response}",
        )
    if changed:
        save_spoken_response_ids(spoken)


def watch_copilot_responses(speaker: Speaker, interval_seconds: float, stop_event: threading.Event) -> None:
    log(COMMAND_LOG, "Copilot response watcher started.")
    last_mtime = None
    while not stop_event.is_set():
        try:
            if PROMPT_RESPONSE_FILE.exists():
                mtime = PROMPT_RESPONSE_FILE.stat().st_mtime
                if last_mtime is None or mtime != last_mtime:
                    poll_copilot_responses(speaker)
                    last_mtime = mtime
        except Exception as exc:
            log(COMMAND_LOG, f"Copilot response watcher error: {type(exc).__name__}: {exc}")
        stop_event.wait(interval_seconds)


def open_folder(path: pathlib.Path) -> None:
    subprocess.Popen(["explorer.exe", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def powershell_single_quoted(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def find_tracked_browser_processes() -> list[int]:
    profile = powershell_single_quoted(str(BROWSER_PROFILE_DIR))
    command = (
        f"$profile = {profile}; "
        "Get-CimInstance Win32_Process -Filter \"Name = 'msedge.exe'\" | "
        "Where-Object { $_.CommandLine -like \"*$profile*\" } | "
        "ForEach-Object { $_.ProcessId }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        log(COMMAND_LOG, f"Tracked browser process lookup failed: {(result.stderr or result.stdout).strip()[:300]}")
        return []
    process_ids: list[int] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            process_ids.append(int(line))
    return process_ids


def find_edge_executable() -> str:
    candidates = [
        pathlib.Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        pathlib.Path(os.environ.get("ProgramFiles", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        pathlib.Path(os.environ.get("LocalAppData", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return "msedge.exe"


def open_tracked_browser(url: str) -> int:
    BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    existing = find_tracked_browser_processes()
    process = subprocess.Popen(
        [
            find_edge_executable(),
            f"--user-data-dir={BROWSER_PROFILE_DIR}",
            "--no-first-run",
            *(["--new-window"] if not existing else []),
            url,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    BROWSER_STATE_FILE.write_text(
        json.dumps(
            {
                "pid": process.pid,
                "known_pids": existing + [process.pid],
                "profile_dir": str(BROWSER_PROFILE_DIR),
                "url": url,
                "opened_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_used_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return process.pid


def close_tracked_browser() -> bool:
    process_ids = set(find_tracked_browser_processes())
    if BROWSER_STATE_FILE.exists():
        try:
            state = json.loads(BROWSER_STATE_FILE.read_text(encoding="utf-8-sig"))
            pid = int(state.get("pid") or 0)
            if pid > 0:
                process_ids.add(pid)
        except (json.JSONDecodeError, ValueError):
            log(COMMAND_LOG, "Browser state file was unreadable while closing browser.")
    if not process_ids:
        return False
    ids_literal = "@(" + ",".join(str(pid) for pid in sorted(process_ids)) + ")"
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            f"$Ids = {ids_literal}; foreach ($id in $Ids) {{ "
            "$p = Get-Process -Id $id -ErrorAction SilentlyContinue; "
            "if ($p) { Stop-Process -Id $id -Force } }",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if BROWSER_STATE_FILE.exists():
        BROWSER_STATE_FILE.unlink()
    return True


def command_matches(text: str, alias: str) -> bool:
    text = normalize_command_text(text)
    alias = normalize_command_text(alias)
    if alias.endswith(" *"):
        prefix = alias[:-2].strip()
        return text.startswith(prefix + " ")
    return text == alias or re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", text) is not None


def extract_after_alias(text: str, aliases: tuple[str, ...]) -> str:
    lowered = text.lower().strip()
    for alias in aliases:
        if not alias.endswith(" *"):
            continue
        prefix = alias[:-2].strip().lower()
        if lowered.startswith(prefix + " "):
            return text[len(prefix) :].strip(" :,-")
    return ""


def h_stop(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, "Stopping voice bridge.")
    return False


def h_good_night(text: str, speaker: Speaker, command: Command) -> bool:
    request_service_shutdown("good night voice command")
    speak(speaker, "Good night Rin.")
    return False


def h_help(text: str, speaker: Speaker, command: Command) -> bool:
    speak(
        speaker,
        "I can open apps, search the web, take notes, summarize Teams and email, check your calendar, repeat what I heard, or stop listening.",
    )
    return True


def h_voice_command_index(text: str, speaker: Speaker, command: Command) -> bool:
    write_voice_command_index()
    enqueue_prompt(
        "Read `C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\arthur_voice_command_index.md` "
        "and send the full contents to Rin in the Microsoft Scout Teams chat. Use the Microsoft Scout Teams relay/message tool "
        "if available. Rin explicitly requested this voice command to send Arthur's Voice Command Index to that chat. "
        "The content is Arthur's local command registry only; do not include private Microsoft 365 data, and do not send to anyone else. "
        "After sending, respond to Arthur with a short confirmation."
    )
    speak(speaker, "I am sending my Voice Command Index to Microsoft Scout in Teams.")
    return True


def h_how_are_you(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, "I am doing well, Rin. I can hear you and I am ready for instructions.")
    return True


def h_hello(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, "Hello Rin. I am listening.")
    return True


def h_thanks(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, "You're welcome.")
    return True


def h_open_process(text: str, speaker: Speaker, command: Command) -> bool:
    processes = {
        "open_calculator": (["calc.exe"], "Opening calculator."),
        "open_cmd": (["cmd.exe"], "Opening command prompt."),
        "open_powershell": (["powershell.exe"], "Opening PowerShell."),
        "open_notepad": (["notepad.exe"], "Opening notepad."),
    }
    process, response = processes[command.handler]
    open_process(process)
    speak(speaker, response)
    return True


def h_open_browser(text: str, speaker: Speaker, command: Command) -> bool:
    try:
        open_tracked_browser("https://www.bing.com")
    except OSError as exc:
        webbrowser.open("https://www.bing.com")
        speak(speaker, "Opening a browser, but I could not track it for closing.")
        log(COMMAND_LOG, f"Tracked browser launch failed: {type(exc).__name__}: {exc}")
        return True
    speak(speaker, "Opening a browser.")
    return True


def h_close_browser(text: str, speaker: Speaker, command: Command) -> bool:
    if not close_tracked_browser():
        speak(speaker, "I do not have a browser window to close.")
        return True
    speak(speaker, "Closed the browser I opened.")
    return True


def h_open_copilot(text: str, speaker: Speaker, command: Command) -> bool:
    webbrowser.open("https://copilot.microsoft.com/")
    speak(speaker, "Opening Copilot.")
    return True


def h_web_search(text: str, speaker: Speaker, command: Command) -> bool:
    query = extract_after_alias(text, command.aliases)
    if not query:
        speak(speaker, "What should I search for?")
        return True
    url = "https://www.bing.com/search?q=" + urllib.parse.quote_plus(query)
    try:
        open_tracked_browser(url)
    except OSError as exc:
        webbrowser.open(url)
        log(COMMAND_LOG, f"Tracked browser search launch failed: {type(exc).__name__}: {exc}")
    speak(speaker, f"Searching the web for {query}.")
    return True


def h_open_folder(text: str, speaker: Speaker, command: Command) -> bool:
    folders = {
        "open_scratchpad": (SCRATCH, "Opening Scratchpad."),
        "open_documents": (pathlib.Path.home() / "Documents", "Opening Documents."),
        "open_downloads": (pathlib.Path.home() / "Downloads", "Opening Downloads."),
    }
    folder, response = folders[command.handler]
    open_folder(folder)
    speak(speaker, response)
    return True


def h_take_note(text: str, speaker: Speaker, command: Command) -> bool:
    note = extract_after_alias(text, command.aliases)
    if not note:
        speak(speaker, "What should I note?")
        return True
    take_note(note)
    speak(speaker, "I noted that.")
    return True


def h_read_notes(text: str, speaker: Speaker, command: Command) -> bool:
    if not NOTES_FILE.exists() or not NOTES_FILE.read_text(encoding="utf-8").strip():
        speak(speaker, "I do not have any voice notes yet.")
        return True
    notes = NOTES_FILE.read_text(encoding="utf-8").strip().splitlines()[-3:]
    speak(speaker, "Your latest notes are: " + " ".join(notes))
    return True


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    zone_name = WINDOWS_TIMEZONE_ALIASES.get(timezone_name, timezone_name)
    return ZoneInfo(zone_name)


def current_time(timezone_name: str) -> dt.datetime:
    return dt.datetime.now(resolve_timezone(timezone_name))


def current_timestamp_protocol(window_days: int = 7) -> str:
    timezone_name = os.environ.get("ARTHUR_TIMEZONE", DEFAULT_TIMEZONE)
    now = current_time(timezone_name)
    start = now - dt.timedelta(days=window_days)
    return (
        f"Current timestamp protocol: Treat the current date/time as {now.strftime('%A, %B %d, %Y %I:%M %p %Z')} "
        f"({now.isoformat()}). Use this timestamp as authoritative for now/today, not any stale session date, "
        "cached transcript date, prior prompt date, or default date from another Scout session. "
        f"Unless the spoken command specifies another time range, search from {start.isoformat()} through {now.isoformat()}. "
        "For every included meeting, resolve the matching Outlook calendar event first and use that event's start/end "
        "time as the displayed Date/Time. Do not use an email-summary subject date, Teams chat date, transcript created "
        "date, recording modified date, or artifact modified date as the meeting occurrence date. If a transcript or "
        "recording cannot be matched to a calendar event, label the Date/Time as unverified and state the artifact date source."
    )


def h_time(text: str, speaker: Speaker, command: Command) -> bool:
    now = current_time(os.environ.get("ARTHUR_TIMEZONE", DEFAULT_TIMEZONE)).strftime("%I:%M %p").lstrip("0")
    speak(speaker, f"It is {now}.")
    return True


def h_date(text: str, speaker: Speaker, command: Command) -> bool:
    today = current_time(os.environ.get("ARTHUR_TIMEZONE", DEFAULT_TIMEZONE)).strftime("%A, %B %d, %Y")
    speak(speaker, f"Today is {today}.")
    return True


def h_list_mics(text: str, speaker: Speaker, command: Command) -> bool:
    devices = [f"{idx}: {dev['name']}" for idx, dev in enumerate(sd.query_devices()) if dev.get("max_input_channels", 0) > 0]
    log(COMMAND_LOG, "Input devices: " + " | ".join(devices))
    speak(speaker, f"I found {len(devices)} input devices. I wrote them to the command log.")
    return True


def h_status(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, f"I am running and listening on {CONFIGURED_MICROPHONE_DEVICE}.")
    return True


def h_repeat_heard(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, f"I heard: {LAST_HEARD}" if LAST_HEARD else "I have not heard a command yet.")
    return True


def h_repeat_response(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, LAST_RESPONSE if LAST_RESPONSE else "I do not have a previous response yet.")
    return True


def h_identity(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, "I am Arthur, your local voice assistant.")
    return True


def h_workiq(text: str, speaker: Speaker, command: Command) -> bool:
    email_scope = email_folder_instruction()
    prompts = {
        "unread_teams": (
            "Checking unread Teams messages.",
            "Find my unread Teams messages. Return only the two newest readable human messages. Include sender, chat name, and message text. Ignore system events.",
        ),
        "recent_email": (
            "Checking recent email.",
            email_scope
            + "Summarize my three newest unread or recent emails. Include sender, subject, and a one sentence preview. Do not include sensitive details beyond what is necessary.",
        ),
        "next_meeting": (
            "Checking your next meeting.",
            "What is my next calendar meeting? Return the title, start time, and whether it is online or in person. Keep it brief.",
        ),
        "calendar_summary": (
            "Checking your calendar.",
            "Summarize my remaining calendar events for today. Include times and titles only. Keep it brief.",
        ),
        "attention_summary": (
            "Checking what needs your attention.",
            email_scope
            + "Review my recent unread Teams messages, recent unread email, and next calendar event. Summarize only the top three items that likely need my attention. Keep it brief and do not read full message bodies.",
        ),
        "daily_briefing": (
            "Preparing your briefing.",
            email_scope
            + "For this Daily Briefing, read these Outlook folders: My To Action, My Informed (CC), "
            "Tier 1 (Leadership), Tier 2 (Stakeholders), and Tier 3 (Partners). "
            + "Generate a succinct, prioritized Catch Up list covering everything that happened from 6pm to 10am the following morning. "
            "Scope: Analyze all work signals during the outlined window: Emails involving me, my team, or key stakeholders. "
            "Tasks, mentions, approvals, and deadlines. Updates on active projects or recurring responsibilities. "
            "Decisions made in my absence. Work completed by others that affects me. New tasks, shifts in priorities, "
            "risks, escalations, or open questions. Output Format: One section titled Catch Up, grouped by themes: "
            "Decisions, Actions Needed, FYI Updates. Each bullet must include: Title; What happened: 1 sentence summary; "
            "Why it matters: 1 sentence impact on me/my team; Required action: next step or \"No action needed\"; "
            "Urgency: High / Medium / Low. Guidelines: Prioritize items requiring immediate action. De-dupe threads "
            "across emails. Synthesize insights; don't list raw activity. Assume I want full context fast with minimal noise.",
        ),
        "meeting_prep": (
            "Checking meeting prep.",
            email_scope
            + "Look at my next calendar meeting and summarize what I should know to prepare. Include title, time, attendees if available, and any recent related email or Teams context. Keep it brief.",
        ),
    }
    intro, prompt = prompts[command.handler]
    speak(speaker, intro)
    if command.handler == "daily_briefing":
        enqueue_prompt(
            prompt
            + " Send a Daily Briefing email addressed only to Rin.Ure@microsoft.com with subject "
            "\"Daily Briefing - <today's date>\". Put the Catch Up output in the email body. "
            "Rin has explicitly authorized automatic sending of this Daily Briefing to himself because he is the only recipient reading these private details. "
            "Because the only recipient is Rin.Ure@microsoft.com, send the completed email after generating it without an additional preview step. "
            "Do not send if there are any recipients other than Rin.Ure@microsoft.com. "
            "After sending, respond to Arthur with exactly: Sent to your inbox."
        )
        speak(speaker, "I am creating and sending your Daily Briefing email.")
        return True
    speak(speaker, run_workiq(prompt))
    return True


def h_daily_tasks(text: str, speaker: Speaker, command: Command) -> bool:
    speak(speaker, "Creating your daily task table.")
    table = run_workiq(
        email_folder_instruction()
        + "Create a concise daily task table from my daily briefing using only high-level, non-sensitive wording. "
        "Use this exact Markdown table format: | Done | Task | Source | Priority | Review note |. "
        "Each Done cell must be an unchecked checkbox '[ ]'. Include at most eight tasks. "
        "Prefer action items from upcoming meetings, unread Teams, and recent email. "
        "Do not include confidential details, message bodies, private personal details, or long excerpts."
    )
    write_daily_tasks_table(table)
    subprocess.Popen(["notepad.exe", str(DAILY_TASKS_FILE)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    speak(speaker, "I created the daily task table and opened it for review.")
    return True


def h_daily_briefing_task_list(text: str, speaker: Speaker, command: Command) -> bool:
    today = current_time(os.environ.get("ARTHUR_TIMEZONE", DEFAULT_TIMEZONE)).strftime("%Y-%m-%d")
    enqueue_prompt(
        "Create a Daily Briefing task list workbook for Rin. First find the latest Daily Briefing email sent to "
        "Rin.Ure@microsoft.com for today; if today's email is not available, use the most recent Daily Briefing email "
        "sent to Rin.Ure@microsoft.com. Pull the action items from the Catch Up list, especially Actions Needed, "
        "dedupe overlapping items, prioritize them by urgency and immediacy, and create an Excel workbook named "
        f"`C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\Daily Briefing Task List {today}.xlsx`. "
        "The workbook must contain one worksheet named `Task List` formatted as a table with these columns: "
        "Done, Priority Rank, Urgency, Title, Required Action, Why It Matters, Source Theme, Source Daily Briefing Email, Notes. "
        "For each task, include a hyperlink in `Source Daily Briefing Email` back to the Daily Briefing email used as the source. "
        "Use unchecked checkbox text `[ ]` in Done, rank High urgency before Medium before Low, use a professional font, freeze the "
        "header row, autofit column widths, and do not use formulas except hyperlinks if needed. After creating the workbook, email the Excel file "
        "with Rin.Ure@microsoft.com on the To line only, with subject `Daily Briefing Task List - <today's date>`. Rin has explicitly "
        "authorized automatic sending of this task-list workbook to himself because he is the only recipient. Do not "
        "send if there are any recipients other than Rin.Ure@microsoft.com. After sending, respond to Arthur with exactly: Sent to your inbox."
    )
    speak(speaker, "I am creating and sending your Daily Briefing Task List workbook.")
    return True


def h_missed_meeting_summary(text: str, speaker: Speaker, command: Command) -> bool:
    timestamp_protocol = current_timestamp_protocol()
    enqueue_prompt(
        timestamp_protocol
        + " "
        "Review meetings where Rin was invited but not in attendance and where a recording and transcript are available. "
        "Use calendar attendance/response status, Teams meeting chats, recordings, transcripts, and related meeting artifacts. "
        "Default to the timestamp-protocol search window unless the spoken command specifies another time range. "
        "For each relevant missed recorded/transcribed meeting, produce a succinct summary and a list of actions Rin needs "
        "to be aware of. Include meeting title, date/time, attendees/owners when available, key decisions, important updates, "
        "risks/escalations, open questions, and actions for Rin or Rin's team. De-dupe repeated points across transcript/chat/email. "
        "Add a brief Coverage Note at the top with the timestamp-protocol search window, count of eligible meetings included, "
        "and any calendar meetings skipped because no recording/transcript was available. "
        "Format the email body so each Meeting Title uses a larger font, and use bold font for these subsection labels under each meeting: "
        "`Key Decisions and Updates:`, `Risks/Escalations:`, `Open Questions:`, and `Actions for Rin/Team:`. "
        "Send an email addressed only to Rin.Ure@microsoft.com with subject `Missed Meeting Summary - <current date from the timestamp protocol>`. "
        "Put the summaries and action list in the email body, grouped by meeting. Rin has explicitly authorized automatic "
        "sending of this missed-meeting summary email to himself because he is the only recipient. Do not send if there are "
        "any recipients other than Rin.Ure@microsoft.com. After sending, respond to Arthur with exactly: Sent to your inbox."
    )
    speak(speaker, "I am reviewing missed recorded meetings and sending you a summary email.")
    return True


def h_meeting_summary_recap(text: str, speaker: Speaker, command: Command) -> bool:
    timestamp_protocol = current_timestamp_protocol()
    enqueue_prompt(
        timestamp_protocol
        + " "
        "Review meetings where Rin attended and where a recording and transcript are available. "
        "Use calendar attendance/response status, Teams meeting chats, recordings, transcripts, and related meeting artifacts. "
        "Default to the timestamp-protocol search window unless the spoken command specifies another time range. "
        "For each relevant attended recorded/transcribed meeting, produce a succinct recap and a list of actions Rin needs "
        "to be aware of. Include meeting title, date/time, attendees/owners when available, key decisions, important updates, "
        "risks/escalations, open questions, and actions for Rin or Rin's team. De-dupe repeated points across transcript/chat/email. "
        "Add a brief Coverage Note at the top with the timestamp-protocol search window, count of eligible meetings included, "
        "and any calendar meetings skipped because no recording/transcript was available. "
        "Format the email body so each Meeting Title uses a larger font, and use bold font for these subsection labels under each meeting: "
        "`Key Decisions and Updates:`, `Risks/Escalations:`, `Open Questions:`, and `Actions for Rin/Team:`. "
        "Send an email addressed only to Rin.Ure@microsoft.com with subject `Meetings Attended Summary - <current date from the timestamp protocol>`. "
        "Put the recaps and action list in the email body, grouped by meeting. Rin has explicitly authorized automatic "
        "sending of this attended-meeting summary email to himself because he is the only recipient. Do not send if there are "
        "any recipients other than Rin.Ure@microsoft.com. After sending, respond to Arthur with exactly: Sent to your inbox."
    )
    speak(speaker, "I am reviewing attended recorded meetings and sending you a summary email.")
    return True


def h_fast_mbr_review(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Find and review the latest FAST Cross Company Partnership MBR document from the CPXPMTeam SharePoint site: "
        "https://microsoft.sharepoint.com/teams/CPXPMTeam. Use this SharePoint site as the authoritative source for all FAST MBR documents going forward. "
        "The known July document URL is https://microsoft.sharepoint.com/:w:/t/CPXPMTeam/cQoBviK951hPRarERnVVwLTAEgUCD0l7RVnHvhSPPhg4VxTzXg. "
        "Prefer the newest MBR document on this site by the MBR date in the file name, title, header, cover page, or document content, using last-modified timestamp only as a tie-breaker. "
        "Before reviewing, verify and state the MBR date/version being used in the email. Do not use older FAST MBR documents from other locations. "
        "If the latest CPXPMTeam MBR document is inaccessible, send an email that clearly states the July/current MBR was inaccessible and do not silently substitute an older document. "
        "Inspect the document content and comments for Fraud Ops review items, asks, decisions, risks, open questions, "
        "and actions. Focus specifically on anything assigned to or mentioning Fraud Ops, Rin, Rin's team, FVO, fraud, "
        "vetting, investigations, partner risk, operational metrics, or related responsibilities. Compile the review into a formatted "
        "email addressed on the To line only to Rin.Ure@microsoft.com with subject `FAST Cross Company Partnership MBR - Fraud Ops Review`. "
        "Rin has explicitly authorized automatic sending of this FAST MBR review email to himself because he is the only recipient. "
        "Do not send if there are any recipients other than Rin.Ure@microsoft.com. Use this exact email body format: "
        "`Source Document Reviewed` with document title, MBR date/version, last-modified timestamp, and source link; "
        "`Fraud Ops Review Items`; `Asks / Actions`; `Risks or Escalations`; and `Open Questions`. "
        "For every item include: section/comment title, what changed or was asked, owner if known, recommended next action, urgency, and a link back to the relevant section/comment in the document. "
        "If an exact section/comment deep link is not available, include the document link and the section heading/comment text "
        "needed to find it quickly. Send the email after the review is complete; do not leave it as a draft. "
        "If sending fails, do not say it was sent; report the failure reason to Arthur. After sending, respond to Arthur with exactly: Sent to your inbox."
    )
    speak(speaker, "I am reviewing the FAST MBR document and sending you the review email.")
    return True


def h_coreidentity_entitlement_approvals(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Use Playwright/browser automation to open the Coreidentity Pending Access Approvals page at "
        "https://coreidentity.microsoft.com/manage/entitlement. Review pending Coreidentity entitlement requests. "
        "Approve only requests that do not contain the phrase `link to MSA` anywhere in the request title, details, "
        "justification, comments, entitlement name, or visible request metadata. Treat this check as case-insensitive. "
        "For each eligible request, approve it and enter exactly `Approved.` in the approval comments. Do not approve "
        "requests that contain `link to MSA`, are ambiguous, cannot be fully inspected, or produce an error. Track every "
        "request reviewed with status Approved, Skipped, or Error and a short reason. After processing, send a Coreidentity "
        "Entitlement Approval Report email addressed only to Rin.Ure@microsoft.com with subject "
        "`Coreidentity Entitlement Approval Report - <today's date>`. Include counts, approved requests, skipped requests, "
        "errors, and any follow-up needed. Rin has explicitly authorized automatic approval for requests matching this "
        "criteria and automatic sending of this report to himself because he is the only recipient. Do not send if there "
        "are any recipients other than Rin.Ure@microsoft.com. After the browser automation and email send are complete, close the Playwright browser. After sending, respond to Arthur with a short confirmation "
        "using second person, such as: Sent to your inbox with <approved/skipped/error counts>."
    )
    speak(speaker, "I am reviewing Coreidentity entitlement approvals and will send you a report.")
    return True


def h_review_all_entitlements(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Review all entitlement approval portals using Playwright/browser automation. Each URL is a different "
        "entitlement portal. Log in or complete existing Microsoft authentication where required. For each portal, "
        "find pending approvals or action items that Rin can approve, inspect enough visible request metadata to confirm "
        "the approval is unambiguous, approve eligible requests, and submit the approval message exactly as `Approved.`. "
        "Do not approve ambiguous requests, inaccessible requests, requests that error, or requests where the approval action "
        "cannot be verified. Track every portal with Portal Name, URL, Approved items, Skipped items with reasons, and Errors. "
        "Use safe parallel processing where the browser/tooling supports independent tabs without duplicate submits; otherwise "
        "process the portals sequentially. Refresh Arthur queue heartbeat metadata after each portal. "
        "Portal list: "
        "CoreIdentity: https://coreidentity.microsoft.com/manage/entitlement. In CoreIdentity, ignore and skip requests whose "
        "MSApprovals column or visible metadata contains `link to MSA`; those MSA-linked requests must be reviewed in UMS - M365 Pulse. "
        "GSAM RightCrowd: https://gsamportalps.corp.microsoft.com/rightcrowd. "
        "MyAccess request approvals: https://myaccess.microsoft.com/@microsoft.onmicrosoft.com#/request-approval. "
        "ServiceNow My Stuff approvals: https://microsoft.service-now.com/sp?id=my_stuff&it=app. "
        "UMS - M365 Pulse: https://m365pulse.microsoft.com/UMS/approvals?approvalRequesterFilter=&approvalResourceNameFilter=&approvalRequestTypeFilter=&approvalOnBehalfOfFilter=SPI%3BUser. "
        "WAccess approvals: https://waccess.microsoft.com/my-action-items?type=approvals. "
        "Personnel groups action center: https://personnel.microsoft.com/groups/actioncenter. "
        "OneVet access review: https://www.onevet.com/userAccessManagement/accessReview. "
        "After all portals have been attempted, compile a formatted Review All Entitlements report email addressed only to "
        "rin.ure@microsoft.com with subject `Review All Entitlements Report - <today's date>`. Include one section per portal "
        "with Portal Name, what was approved, what was skipped, what errored, and any follow-up needed. Rin has explicitly "
        "authorized automatic approval for eligible requests matching this command and automatic sending of this report to "
        "himself because he is the only recipient. Do not send if there are any To, CC, or BCC recipients other than "
        "rin.ure@microsoft.com. After the browser automation and email send are complete, close the Playwright browser. "
        "If any portal cannot be accessed, include that portal as an Error in the report and continue with the remaining portals. "
        "After sending, respond to Arthur with exactly: Sent to your inbox."
    )
    speak(speaker, "I am reviewing all entitlement portals and will send you a report.")
    return True


def h_evening_inbox_brief(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Create an executive and concise Evening Inbox Brief for Rin using emails from the last 8 hours only. "
        "Read only these Outlook folders: Rin to Review, Tier 1 (Leadership), Tier 2 (Stakeholders), Tier 3 (Partners), "
        "My To Action, and My Informed (CC). Exclude all other folders, bulk/marketing, system notifications, receipts, "
        "and blocked senders/keywords. Include meeting invites and flagged messages. Analyze sent/responded email activity, "
        "meeting invites triaged, and emails deleted/archived where available. Also review Azure DevOps Action Tracker items "
        "in `https://dev.azure.com/FraudOps/Fraud%20Ops%20AI%20Tracker` tagged `ArthurActionTracker`. Include completed ADO "
        "work items in Group 1 accomplishments. For Group 2 next-day work items, include only active ADO items with Priority 1; "
        "do not include Priority 2 or lower ADO items in tomorrow's focus section. Output exactly two optional groups: "
        "Group 1: What I accomplished today (emails sent/responded, meeting invites triaged, emails deleted/archived, and completed ADO work items). "
        "Group 2: Top 3 things to focus on tomorrow (based on urgency and importance, with ADO items limited to Priority 1 only). Start with two one-sentence roll-ups: "
        "Summary of accomplishments, including themes and number of invites handled; and Summary of top 3 priorities for tomorrow. "
        "For each group, list 3-5 bullets in this format: `[Sender] â€” Subject â€” one-line gist` with icons: âœ… for completed, "
        "ðŸ” for priority, and ðŸ“… for invite. If a group has no items, omit it entirely. End with a short motivational phrase "
        "acknowledging progress, such as `Great progress todayâ€”tomorrow's priorities are clear!`. Send the completed report "
        "as an email with Rin.Ure@microsoft.com on the To line only, with subject `Evening Inbox Brief - <today's date>`. "
        "Rin has explicitly authorized automatic sending of this evening inbox brief to himself because he is the only recipient. "
        "Do not send if there are any recipients other than Rin.Ure@microsoft.com. After sending, append this concise response for Arthur to speak: Sent to your inbox."
    )
    speak(speaker, "I am preparing and sending your evening inbox brief.")
    return True


def h_action_tracker(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Create or update Arthur's Action Tracker for Rin. Review all relevant Teams messages/chats, Outlook email, "
        "calendar events, meeting summaries, meeting chats, and available transcripts for items that need Rin's attention. "
        "Use Azure DevOps as the canonical tracker at `https://dev.azure.com/FraudOps/Fraud%20Ops%20AI%20Tracker`. Read tracker "
        "configuration from `C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\arthur_action_tracker_state.json`. "
        "Create or update ADO work items for distinct action items, using work item type `Task` unless that project does not support it; "
        "if `Task` is unavailable, use the closest available work item type and state that in the response. Tag every item with "
        "`ArthurActionTracker`. Assign every new work item and every updated active Action Tracker work item to Rin Ure (Rin.Ure@microsoft.com) "
        "unless Rin explicitly names a different assignee in the spoken command. Store Priority, Item to be completed, Description, Due Date, Next Action, Status, Owner, Source, and Last Updated "
        "in standard ADO fields where available and otherwise in the description/comments. Deduplicate existing items by normalized title/source "
        "before adding anything new. Active items should remain in an active/new state; completed items should move to the project's completed "
        "state such as Done, Closed, or Completed. After creating or updating ADO items, send Rin a Teams chat message at Rin.Ure@microsoft.com "
        "containing only a concise summary and the ADO tracker/work item links. Rin has explicitly requested this Teams message to himself. "
        "Do not send to anyone else. If Playwright/browser automation is used, close the Playwright browser after the ADO update and Teams message are complete. "
        "Respond to Arthur with a short second-person confirmation, such as: Updated and sent to your Teams chat."
    )
    speak(speaker, "I am creating your Azure DevOps Action Tracker and will send you the tracker link in Teams.")
    return True


def h_action_tracker_new_items(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Update Arthur's existing Azure DevOps Action Tracker with new items. Read the tracker configuration from "
        "`C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\arthur_action_tracker_state.json`. "
        "Review recent Teams messages/chats, Outlook email, calendar events, meeting summaries, meeting chats, and available transcripts "
        "for new action items that are not already in ADO. Use Azure DevOps at `https://dev.azure.com/FraudOps/Fraud%20Ops%20AI%20Tracker`. "
        "Add only distinct new work items tagged `ArthurActionTracker` and assign them to Rin Ure (Rin.Ure@microsoft.com) unless Rin explicitly names a different assignee, preserving Priority, Item to be completed, Description, Due Date, Next Action, "
        "Status, Owner, Source, and Last Updated in standard fields where available and otherwise in the description/comments. Deduplicate existing "
        "items by normalized title/source. After updating, send Rin a Teams chat message at Rin.Ure@microsoft.com with the count of new items added "
        "and the ADO tracker/work item links. Do not send to anyone else. If Playwright/browser automation is used, close the Playwright browser after "
        "the ADO update and Teams message are complete. Respond to Arthur with a short second-person confirmation."
    )
    speak(speaker, "I am updating your Action Tracker with new items.")
    return True


def h_action_tracker_completed_items(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Update Arthur's Azure DevOps Action Tracker for completed items. Read the tracker configuration from "
        "`C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\arthur_action_tracker_state.json`. "
        "Review the spoken command and recent context to identify items that Rin indicated are complete. Find matching ADO work items tagged "
        "`ArthurActionTracker` in `https://dev.azure.com/FraudOps/Fraud%20Ops%20AI%20Tracker`. Move matching items to the project's completed "
        "state such as Done, Closed, or Completed, keep or set Assigned To as Rin Ure (Rin.Ure@microsoft.com) unless Rin explicitly names a different assignee, and preserve Description, Due Date, Next Action, Owner, Source, and notes/comments. If the spoken "
        "command does not identify specific completed items, ask Rin which items to mark complete instead of guessing. After updating, send Rin a Teams "
        "chat message at Rin.Ure@microsoft.com with the count of items marked complete and the ADO tracker/work item links. Do not send to anyone else. "
        "If Playwright/browser automation is used, close the Playwright browser after the ADO update and Teams message are complete. Respond to Arthur with a short second-person confirmation."
    )
    speak(speaker, "I am updating your Action Tracker for completed items.")
    return True


def h_action_tracker_review_completed(text: str, speaker: Speaker, command: Command) -> bool:
    enqueue_prompt(
        "Review Arthur's completed Azure DevOps Action Tracker tasks. Read the tracker configuration from "
        "`C:\\Users\\riur\\OneDrive - Microsoft\\Documents\\Microsoft Scout\\Scratchpad\\arthur_action_tracker_state.json`. "
        "Use Azure DevOps at `https://dev.azure.com/FraudOps/Fraud%20Ops%20AI%20Tracker` to review completed work items tagged `ArthurActionTracker`. "
        "Summarize completed items by priority, completion date if available, and owner. Send Rin a Teams chat message at Rin.Ure@microsoft.com with "
        "a concise completed-task summary and ADO tracker/work item links. Do not send to anyone else. If Playwright/browser automation is used, close "
        "the Playwright browser after the review and Teams message are complete. Respond to Arthur with a short second-person confirmation that the completed tasks were reviewed."
    )
    speak(speaker, "I am reviewing your completed Action Tracker tasks.")
    return True


def h_prompt_window(text: str, speaker: Speaker, command: Command) -> bool:
    prompt = extract_after_alias(text, command.aliases)
    if not prompt:
        speak(speaker, "What should I send to this window?")
        return True
    enqueue_prompt(prompt)
    speak(speaker, "I sent that prompt to this window.")
    return True


def startup_greeting(name: str, timezone_name: str) -> str:
    try:
        now = current_time(timezone_name)
    except ZoneInfoNotFoundError:
        now = dt.datetime.now()
        log(COMMAND_LOG, f"Timezone not found: {timezone_name}; falling back to system local time.")
    hour = now.hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return f"{greeting} {name}, I am up and operational after applying the requested updates. I am ready to receive your instructions."


HANDLERS = {
    "stop": h_stop,
    "good_night": h_good_night,
    "help": h_help,
    "voice_command_index": h_voice_command_index,
    "how_are_you": h_how_are_you,
    "hello": h_hello,
    "thanks": h_thanks,
    "open_calculator": h_open_process,
    "open_cmd": h_open_process,
    "open_powershell": h_open_process,
    "open_notepad": h_open_process,
    "open_browser": h_open_browser,
    "close_browser": h_close_browser,
    "open_copilot": h_open_copilot,
    "web_search": h_web_search,
    "open_scratchpad": h_open_folder,
    "open_documents": h_open_folder,
    "open_downloads": h_open_folder,
    "take_note": h_take_note,
    "read_notes": h_read_notes,
    "time": h_time,
    "date": h_date,
    "list_mics": h_list_mics,
    "status": h_status,
    "repeat_heard": h_repeat_heard,
    "repeat_response": h_repeat_response,
    "identity": h_identity,
    "unread_teams": h_workiq,
    "recent_email": h_workiq,
    "next_meeting": h_workiq,
    "calendar_summary": h_workiq,
    "action_tracker": h_action_tracker,
    "daily_briefing": h_workiq,
    "meeting_prep": h_workiq,
    "daily_tasks": h_daily_tasks,
    "daily_briefing_task_list": h_daily_briefing_task_list,
    "missed_meeting_summary": h_missed_meeting_summary,
    "meeting_summary_recap": h_meeting_summary_recap,
    "fast_mbr_review": h_fast_mbr_review,
    "coreidentity_entitlement_approvals": h_coreidentity_entitlement_approvals,
    "review_all_entitlements": h_review_all_entitlements,
    "evening_inbox_brief": h_evening_inbox_brief,
    "action_tracker_new_items": h_action_tracker_new_items,
    "action_tracker_completed_items": h_action_tracker_completed_items,
    "action_tracker_review_completed": h_action_tracker_review_completed,
    "prompt_window": h_prompt_window,
}


COMMANDS = [
    Command("stop listening", ("stop", "quit", "exit", "go to sleep", "stop listening"), "stop", "Stop the bridge."),
    Command("good night", ("good night", "goodnight"), "good_night", "Say good night and stop the bridge."),
    Command("help", ("help", "what can you do"), "help", "List available commands."),
    Command(
        "Voice Command Index",
        (
            "list voice commands",
            "list your voice commands",
            "show voice commands",
            "show your voice commands",
            "what are your voice commands",
            "send voice command index",
            "send voice commands",
            "voice command index",
        ),
        "voice_command_index",
        "Send Arthur's indexed voice command list to the Microsoft Scout Teams chat.",
    ),
    Command(
        "prompt window",
        (
            "ask copilot *",
            "ask copilot to *",
            "ask this window *",
            "prompt copilot *",
            "prompt copilot to *",
            "send to copilot *",
            "send to copilot to *",
            "send to this window *",
            "tell copilot *",
            "tell copilot to *",
            "have copilot *",
            "have copilot do *",
            "use copilot to *",
            "execute prompt *",
            "execute prompt to *",
        ),
        "prompt_window",
        "Queue a spoken prompt for this Scout window.",
    ),
    Command(
        "FAST MBR review",
        (
            "fast mbr review",
            "review fast mbr",
            "review fast partnership mbr",
            "review fast cross company partnership mbr",
            "review fast cross company partnership mbr document",
            "fast cross company partnership mbr",
            "fast cross company partnership mbr document",
            "fast partnership review",
        ),
        "fast_mbr_review",
        "Draft a Fraud Ops review email from the FAST Cross Company Partnership MBR document.",
    ),
    Command(
        "Coreidentity entitlement approvals",
        (
            "coreidentity entitlement approvals",
            "approve coreidentity entitlements",
            "review coreidentity entitlements",
            "core identity entitlement approvals",
            "approve core identity entitlements",
            "review core identity entitlements",
            "pending access approvals",
            "review pending access approvals",
            "approve pending access approvals",
        ),
        "coreidentity_entitlement_approvals",
        "Approve eligible Coreidentity entitlements and email an approval report.",
    ),
    Command(
        "Review All Entitlements",
        (
            "review all entitlements",
            "approve all entitlements",
            "review all entitlement approvals",
            "approve all entitlement approvals",
            "review entitlement portals",
            "approve entitlement portals",
            "review all access approvals",
            "approve all access approvals",
        ),
        "review_all_entitlements",
        "Review all entitlement approval portals, approve eligible requests, and email a report.",
    ),
    Command(
        "evening inbox brief",
        (
            "evening inbox brief",
            "inbox brief",
            "evening email brief",
            "create evening inbox brief",
            "summarize my inbox",
            "summarize my evening inbox",
            "what did i accomplish today",
            "tomorrow priorities",
        ),
        "evening_inbox_brief",
        "Create an executive evening inbox brief from priority folders.",
    ),
    Command("how are you", ("how are you", "how's it going", "how is it going"), "how_are_you", "Respond conversationally."),
    Command("hello", ("hello", "hi", "hey", "good morning", "good afternoon", "good evening"), "hello", "Greet Rin."),
    Command("thanks", ("thank you", "thanks"), "thanks", "Acknowledge thanks."),
    Command("open calculator", ("calculator", "calc", "open calculator"), "open_calculator", "Open Calculator."),
    Command("open command prompt", ("command prompt", "cmd", "open command prompt"), "open_cmd", "Open Command Prompt."),
    Command("open powershell", ("powershell", "open powershell"), "open_powershell", "Open PowerShell."),
    Command("open notepad", ("notepad", "note pad", "open notepad", "open note pad"), "open_notepad", "Open Notepad."),
    Command("close browser", ("close browser", "close edge", "close the browser", "close the browser you opened"), "close_browser", "Close the browser Arthur opened."),
    Command("open browser", ("browser", "edge", "open browser", "open edge"), "open_browser", "Open browser."),
    Command("open Copilot", ("open copilot", "copilot"), "open_copilot", "Open Copilot."),
    Command("search web", ("search for *", "search the web for *", "look up *", "bing *"), "web_search", "Search the web."),
    Command("open scratchpad", ("open scratchpad",), "open_scratchpad", "Open Scratchpad."),
    Command("open documents", ("open documents",), "open_documents", "Open Documents."),
    Command("open downloads", ("open downloads",), "open_downloads", "Open Downloads."),
    Command("take note", ("take a note *", "make a note *", "remember this *", "note this *"), "take_note", "Append a note."),
    Command("read notes", ("read notes", "read my notes"), "read_notes", "Read recent notes."),
    Command("time", ("time", "what time is it"), "time", "Tell current time."),
    Command("date", ("date", "today", "what day is it"), "date", "Tell current date."),
    Command("list microphones", ("list microphone", "list microphones", "audio devices"), "list_mics", "List input devices."),
    Command("status", ("status", "are you listening"), "status", "Report bridge status."),
    Command("repeat heard", ("repeat", "what did you hear"), "repeat_heard", "Repeat last heard command."),
    Command("repeat response", ("say that again", "repeat your response"), "repeat_response", "Repeat last response."),
    Command("identity", ("who are you", "what is your name"), "identity", "Say identity."),
    Command("unread Teams", ("read unread teams", "unread teams message", "unread teams messages", "summarize unread teams"), "unread_teams", "Summarize unread Teams."),
    Command("recent email", ("recent email", "unread email", "latest email", "summarize unread email", "email summary"), "recent_email", "Summarize recent email."),
    Command(
        "missed meeting summary",
        (
            "missed meeting summary",
            "summarize missed meetings",
            "review missed meetings",
            "missed recorded meetings",
            "summarize meetings i missed",
            "review meetings i missed",
            "meeting summaries i missed",
            "catch me up on missed meetings",
        ),
        "missed_meeting_summary",
        "Email summaries and actions from missed recorded/transcribed meetings.",
    ),
    Command(
        "meeting summary recap",
        (
            "meeting summary recap",
            "meetings attended summary",
            "attended meeting summary",
            "summarize meetings i attended",
            "review meetings i attended",
            "summarize attended meetings",
            "review attended meetings",
            "recap meetings i attended",
            "meeting recap",
        ),
        "meeting_summary_recap",
        "Email summaries and actions from attended recorded/transcribed meetings.",
    ),
    Command("meeting prep", ("meeting prep", "prep my next meeting", "prepare me for my next meeting"), "meeting_prep", "Prepare for the next meeting."),
    Command("next meeting", ("next meeting", "what is my next meeting"), "next_meeting", "Read next meeting."),
    Command("calendar summary", ("calendar summary", "today's calendar", "my calendar", "summarize my calendar"), "calendar_summary", "Summarize today's calendar."),
    Command(
        "update Action Tracker with new items",
        (
            "update action tracker with new items",
            "add new items to action tracker",
            "update my action tracker",
            "refresh action tracker",
            "add action tracker items",
            "new action items",
        ),
        "action_tracker_new_items",
        "Add new action items to Arthur's Action Tracker.",
    ),
    Command(
        "update completed Action Tracker items",
        (
            "update completed action tracker items",
            "mark action tracker items complete",
            "mark action items complete",
            "complete action tracker items",
            "clear completed action items",
        ),
        "action_tracker_completed_items",
        "Mark completed items in Arthur's Action Tracker.",
    ),
    Command(
        "review completed Action Tracker tasks",
        (
            "review completed action tracker tasks",
            "review completed action items",
            "show completed action tracker items",
            "show completed action items",
            "what did i complete",
        ),
        "action_tracker_review_completed",
        "Review completed tasks in Arthur's Action Tracker.",
    ),
    Command(
        "Arthur's Action Tracker",
        ("what needs my attention", "action tracker", "create action tracker", "build action tracker", "prioritize my work"),
        "action_tracker",
        "Create Arthur's Action Tracker from top action items.",
    ),
    Command(
        "daily briefing task list",
        (
            "daily briefing task list",
            "create daily briefing task list",
            "daily briefing action list",
            "create daily briefing action list",
            "briefing task list",
            "create briefing task list",
            "turn daily briefing into tasks",
        ),
        "daily_briefing_task_list",
        "Create and email an Excel task list from the Daily Briefing.",
    ),
    Command("daily briefing", ("daily briefing", "work briefing", "brief me"), "daily_briefing", "Summarize workday priorities."),
    Command("daily tasks", ("summarize daily tasks", "daily task table", "create daily task table"), "daily_tasks", "Create a check-off task table from the daily briefing."),
]


def write_voice_command_index() -> None:
    now = current_time(os.environ.get("ARTHUR_TIMEZONE", DEFAULT_TIMEZONE)).strftime("%Y-%m-%d %I:%M %p %Z")
    lines = [
        "# Arthur Voice Command Index",
        "",
        f"Generated: {now}",
        "",
        "| # | Command | What it does | Voice phrases |",
        "| ---: | --- | --- | --- |",
    ]
    for idx, item in enumerate(COMMANDS, start=1):
        aliases = ", ".join(f"`{alias}`" for alias in item.aliases)
        lines.append(f"| {idx} | {item.name} | {item.description} | {aliases} |")
    VOICE_COMMAND_INDEX_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log(COMMAND_LOG, f"Voice Command Index written: {VOICE_COMMAND_INDEX_FILE}")


def find_command(text: str) -> Command | None:
    for item in COMMANDS:
        if any(command_matches(text, alias) for alias in item.aliases):
            return item
    return None


def handle_command(text: str, speaker: Speaker) -> bool:
    log(COMMAND_LOG, f"Command: {text}")
    matched = find_command(text)
    if matched:
        return HANDLERS[matched.handler](text, speaker, matched)

    log(COMMAND_LOG, f"Auto-escalated to Copilot: {text}")
    enqueue_prompt(text)
    speak(speaker, "I do not know how to do that locally yet, so I sent it to Copilot.")
    return True


def main() -> int:
    global LAST_HEARD, PENDING_WAKE_UNTIL, CONFIGURED_MICROPHONE_DEVICE

    parser = argparse.ArgumentParser(description="Arthur local real-time voice bridge.")
    parser.add_argument("--device", type=int, default=int(os.environ.get("ARTHUR_MIC_DEVICE", "2")))
    parser.add_argument("--wake-word", default="Arthur")
    parser.add_argument("--samplerate", type=int, default=16000)
    parser.add_argument("--model", default="tiny.en")
    parser.add_argument("--tts", choices=("edge", "windows"), default=os.environ.get("ARTHUR_TTS", "edge"))
    parser.add_argument("--edge-voice", default=os.environ.get("ARTHUR_EDGE_VOICE", EDGE_VOICE))
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--calibrate-seconds", type=float, default=1.5)
    parser.add_argument("--max-utterance-seconds", type=float, default=8.0)
    parser.add_argument("--silence-seconds", type=float, default=0.8)
    parser.add_argument("--response-poll-seconds", type=float, default=2.0)
    parser.add_argument("--welcome-name", default=os.environ.get("ARTHUR_WELCOME_NAME", "Rin"))
    parser.add_argument("--timezone", default=os.environ.get("ARTHUR_TIMEZONE", DEFAULT_TIMEZONE))
    parser.add_argument("--once", action="store_true", help="Handle one recognized wake-word command, then exit.")
    args = parser.parse_args()

    SCRATCH.mkdir(parents=True, exist_ok=True)
    write_voice_command_index()
    device_info = sd.query_devices(args.device)
    CONFIGURED_MICROPHONE_DEVICE = str(device_info["name"])
    os.environ["ARTHUR_MIC_DEVICE"] = str(args.device)
    os.environ["ARTHUR_TIMEZONE"] = args.timezone

    speaker = Speaker(args.tts, args.edge_voice)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    threshold = args.threshold or calibrate_noise(args.device, args.samplerate, args.calibrate_seconds)

    log(TRANSCRIPT_LOG, f"Voice bridge active on mic index {args.device}: {device_info['name']}")
    log(TRANSCRIPT_LOG, f"Wake word: {args.wake_word}; RMS threshold: {threshold:.1f}")
    log(TRANSCRIPT_LOG, f"TTS mode: {args.tts}; Edge voice: {args.edge_voice}")
    write_heartbeat("starting", mic_index=args.device, mic_name=str(device_info["name"]))
    response_stop = threading.Event()
    response_thread = threading.Thread(
        target=watch_copilot_responses,
        args=(speaker, args.response_poll_seconds, response_stop),
        daemon=True,
    )
    response_thread.start()
    speak(speaker, startup_greeting(args.welcome_name, args.timezone))

    count = 0
    try:
        while True:
            write_heartbeat("listening", mic_index=args.device, mic_name=str(device_info["name"]))
            try:
                audio = record_utterance_with_timeout(
                    timeout_seconds=args.max_utterance_seconds + args.response_poll_seconds + 3.0,
                    device=args.device,
                    samplerate=args.samplerate,
                    threshold=threshold,
                    max_seconds=args.max_utterance_seconds,
                    silence_seconds=args.silence_seconds,
                    idle_seconds=args.response_poll_seconds,
                )
            except TimeoutError as exc:
                log(COMMAND_LOG, f"Microphone read timeout: {exc}")
                write_heartbeat("mic_timeout", error=str(exc), mic_index=args.device)
                return 2
            if audio.size == 0:
                continue
            if not should_transcribe(audio, threshold):
                continue

            count += 1
            path = SCRATCH / f"arthur_bridge_utterance_{count:04d}.wav"
            wavfile.write(str(path), args.samplerate, audio)
            text = transcribe_audio(model, path)
            if not text:
                continue

            log(TRANSCRIPT_LOG, f"Heard: {text}")
            LAST_HEARD = text
            command = strip_wake_word(text, args.wake_word)
            now = time.time()
            if command is None and now < PENDING_WAKE_UNTIL:
                command = text.strip(" ,.:;-")
                log(COMMAND_LOG, f"Using pending wake word for: {command}")
            elif command == "":
                PENDING_WAKE_UNTIL = now + 8.0
                speak(speaker, "Yes?")
                continue
            if command is None:
                continue
            PENDING_WAKE_UNTIL = 0.0

            should_continue = handle_command(command, speaker)
            if args.once or not should_continue:
                break
    finally:
        response_stop.set()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nI stopped the voice bridge.", flush=True)

