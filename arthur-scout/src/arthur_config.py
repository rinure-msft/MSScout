import json
import os
import pathlib
import re
import sys
import getpass
from copy import deepcopy
from typing import Any


MODULE_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = MODULE_DIR / "arthur.config.json"
DEFAULT_USER = os.environ.get("USERNAME") or getpass.getuser() or "User"
DEFAULT_ENABLED_COMMANDS = [
    "voice_command_index",
    "fast_mbr_review",
    "biweekly_incident_review",
    "leadership_watch_brief",
    "coreidentity_entitlement_approvals",
    "review_all_entitlements",
    "evening_inbox_brief",
    "how_are_you",
    "hello",
    "thanks",
    "open_calculator",
    "open_cmd",
    "open_powershell",
    "open_notepad",
    "close_browser",
    "open_browser",
    "open_dashboard",
    "open_copilot",
    "web_search",
    "open_scratchpad",
    "open_documents",
    "open_downloads",
    "take_note",
    "read_notes",
    "time",
    "date",
    "list_mics",
    "repeat_heard",
    "repeat_response",
    "identity",
    "unread_teams",
    "recent_email",
    "missed_meeting_summary",
    "meeting_summary_recap",
    "meeting_prep",
    "next_meeting",
    "calendar_summary",
    "action_tracker_new_items",
    "action_tracker_completed_items",
    "action_tracker_review_completed",
    "action_tracker",
    "daily_briefing_task_list",
    "daily_briefing",
    "daily_tasks",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "assistantName": "Arthur",
    "userDisplayName": DEFAULT_USER,
    "userFirstName": DEFAULT_USER.split()[0],
    "timezone": "Europe/London",
    "voice": {
        "tts": "edge",
        "edgeVoice": "en-GB-RyanNeural",
        "edgeRate": "+10%",
        "edgePitch": "+0Hz",
        "edgeVolume": "+0%",
        "windowsVoiceId": "",
        "windowsRate": 180,
        "windowsVolume": 1.0,
    },
    "greetings": {
        "startup": "good {time_of_day} {name}, I am ready to be of assistance.",
        "updates": "good {time_of_day} {name}, your updates have been applied and I am ready to assist you.",
    },
    "microphone": {
        "deviceIndex": 1,
        "threshold": 350,
        "minTranscribeRms": 120.0,
        "minTranscribePeak": 700,
    },
    "speechRecognition": {
        "backend": "zipformer",
        "postActivationBackend": "zipformer",
        "modelDirectory": r"models\zipformer-en-balanced-int8",
        "numThreads": 4,
        "decodingMethod": "modified_beam_search",
        "maxActivePaths": 4,
        "provider": "cpu",
        "hotwordsEnabled": True,
        "hotwordsFile": "hotwords.txt",
        "hotwordsScore": 2.0,
        "bpeVocab": "bpe.vocab",
    },
    "notification": {
        "selfEmail": "",
        "teamsSelfMessage": False,
    },
    "azureDevOps": {
        "organization": "",
        "project": "",
        "url": "",
        "tag": "ArthurActionTracker",
        "defaultAssignee": "",
        "defaultAssigneeEmail": "",
        "defaultWorkItemType": "Task",
    },
    "dashboard": {
        "port": 8765,
    },
    "scout": {
        "queueEnabled": True,
    },
    "runtime": {
        "scratchpadPath": str(MODULE_DIR),
        "browserProfilePath": str(
            pathlib.Path(
                os.environ.get(
                    "LOCALAPPDATA",
                    pathlib.Path.home() / "AppData" / "Local",
                )
            )
            / "Arthur"
            / "EdgeProfile"
        ),
        "workiqPath": "",
        "automationFile": "",
        "promptResponderAutomationId": "",
        "cleanupChatArtifactsOlderThanHours": 4,
        "chatCleanupIntervalMinutes": 45,
        "logRetentionDays": 7,
    },
    "emailFolders": [
        "Tier 1 (Leadership)",
        "Tier 2 (Stakeholders)",
        "Tier 3 (Partners)",
        "My To Action",
        "My Informed (CC)",
    ],
    "enabledCommands": DEFAULT_ENABLED_COMMANDS,
}

REQUIRED_CONFIG_FIELDS = (
    "assistantName",
    "userDisplayName",
    "userFirstName",
    "timezone",
    "voice.tts",
    "voice.edgeVoice",
    "microphone.deviceIndex",
    "microphone.threshold",
    "speechRecognition.backend",
    "speechRecognition.modelDirectory",
    "runtime.scratchpadPath",
)
PLACEHOLDER_PATTERN = re.compile(r"^<[^>]+>$")


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    configured_path = os.environ.get("ARTHUR_CONFIG")
    path = pathlib.Path(configured_path) if configured_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        return deepcopy(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Arthur config root must be an object: {path}")
    return _merge(DEFAULT_CONFIG, data)


CONFIG = load_config()


def get_config(path: str, default: Any = None) -> Any:
    value: Any = CONFIG
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def _get_from(config: dict[str, Any], path: str) -> Any:
    value: Any = config
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _is_placeholder(value: Any) -> bool:
    return isinstance(value, str) and bool(PLACEHOLDER_PATTERN.match(value.strip()))


def validate_config(config: dict[str, Any] | None = None, config_path: pathlib.Path | None = None) -> list[str]:
    config = config if config is not None else CONFIG
    errors: list[str] = []
    if config_path is not None and not config_path.exists():
        errors.append(f"Config file is required and was not found: {config_path}")
    for field in REQUIRED_CONFIG_FIELDS:
        value = _get_from(config, field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"Missing required config field: {field}")
        elif _is_placeholder(value):
            errors.append(f"Required config field still contains a placeholder: {field}={value}")
    assistant_name = str(_get_from(config, "assistantName") or "")
    if assistant_name and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9' -]{0,39}", assistant_name):
        errors.append(
            "assistantName must be 1 to 40 letters, numbers, spaces, apostrophes, or hyphens"
        )
    tts = str(_get_from(config, "voice.tts") or "")
    if tts and tts not in {"edge", "windows"}:
        errors.append("voice.tts must be 'edge' or 'windows'")
    edge_rate = str(_get_from(config, "voice.edgeRate") or "")
    if edge_rate and not re.fullmatch(r"[+-]\d{1,3}%", edge_rate):
        errors.append("voice.edgeRate must look like '+0%' or '-10%'")
    edge_pitch = str(_get_from(config, "voice.edgePitch") or "")
    if edge_pitch and not re.fullmatch(r"[+-]\d{1,3}Hz", edge_pitch):
        errors.append("voice.edgePitch must look like '+0Hz' or '-5Hz'")
    edge_volume = str(_get_from(config, "voice.edgeVolume") or "")
    if edge_volume and not re.fullmatch(r"[+-]\d{1,3}%", edge_volume):
        errors.append("voice.edgeVolume must look like '+0%' or '-10%'")
    try:
        windows_rate = int(_get_from(config, "voice.windowsRate"))
        if windows_rate < 50 or windows_rate > 400:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("voice.windowsRate must be between 50 and 400")
    try:
        windows_volume = float(_get_from(config, "voice.windowsVolume"))
        if windows_volume < 0 or windows_volume > 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("voice.windowsVolume must be between 0 and 1")
    try:
        int(_get_from(config, "microphone.deviceIndex"))
    except (TypeError, ValueError):
        errors.append("microphone.deviceIndex must be an integer")
    try:
        int(_get_from(config, "microphone.threshold"))
    except (TypeError, ValueError):
        errors.append("microphone.threshold must be an integer")
    try:
        dashboard_port = int(_get_from(config, "dashboard.port"))
        if dashboard_port < 1024 or dashboard_port > 65535:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("dashboard.port must be between 1024 and 65535")
    if not isinstance(_get_from(config, "scout.queueEnabled"), bool):
        errors.append("scout.queueEnabled must be true or false")
    backend = str(_get_from(config, "speechRecognition.backend") or "")
    if backend and backend != "zipformer":
        errors.append("speechRecognition.backend must be 'zipformer'")
    post_activation_backend = str(
        _get_from(config, "speechRecognition.postActivationBackend")
        or backend
    )
    if post_activation_backend != "zipformer":
        errors.append(
            "speechRecognition.postActivationBackend must be 'zipformer'"
        )
    decoding_method = str(
        _get_from(config, "speechRecognition.decodingMethod") or ""
    )
    if decoding_method and decoding_method not in {
        "greedy_search",
        "modified_beam_search",
    }:
        errors.append(
            "speechRecognition.decodingMethod must be "
            "'greedy_search' or 'modified_beam_search'"
        )
    try:
        if int(_get_from(config, "speechRecognition.numThreads")) < 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("speechRecognition.numThreads must be an integer >= 1")
    try:
        if int(_get_from(config, "speechRecognition.maxActivePaths")) < 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(
            "speechRecognition.maxActivePaths must be an integer >= 1"
        )
    try:
        if float(_get_from(config, "speechRecognition.hotwordsScore")) <= 0:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(
            "speechRecognition.hotwordsScore must be a number greater than 0"
        )
    email = str(_get_from(config, "notification.selfEmail") or "")
    if email and "@" not in email:
        errors.append("notification.selfEmail must look like an email address")
    ado_email = str(_get_from(config, "azureDevOps.defaultAssigneeEmail") or "")
    if ado_email and "@" not in ado_email:
        errors.append("azureDevOps.defaultAssigneeEmail must look like an email address")
    return errors


def get_path(path: str, default: str | None = None) -> pathlib.Path:
    value = get_config(path, default)
    if value is None:
        raise ValueError(f"Missing Arthur config path: {path}")
    return pathlib.Path(str(value))


def self_email() -> str:
    return str(get_config("notification.selfEmail", ""))


def user_first_name() -> str:
    return str(get_config("userFirstName", get_config("userDisplayName", "user"))).split()[0]


def user_display_name() -> str:
    return str(get_config("userDisplayName", user_first_name()))


def ado_url() -> str:
    return str(get_config("azureDevOps.url", ""))


def apply_text_config(text: str) -> str:
    scratchpad = str(get_path("runtime.scratchpadPath", str(MODULE_DIR)))
    workiq_path = str(get_path("runtime.workiqPath", str(pathlib.Path.home() / ".copilot" / "bin" / "workiq.cmd")))
    replacements = {
        "<SELF_EMAIL>": self_email(),
        "Rin Ure": str(get_config("azureDevOps.defaultAssignee", user_display_name())),
        "Rin": user_first_name(),
        r"C:\Users\riur\.copilot\bin\workiq.cmd": workiq_path,
        "https://dev.azure.com/FraudOps/Fraud%20Ops%20AI%20Tracker": ado_url(),
        "FraudOps": str(get_config("azureDevOps.organization", "FraudOps")),
        "Fraud Ops AI Tracker": str(get_config("azureDevOps.project", "Fraud Ops AI Tracker")),
        "ArthurActionTracker": str(get_config("azureDevOps.tag", "ArthurActionTracker")),
    }
    for old, new in replacements.items():
        if new:
            text = text.replace(old, new)
    return text


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Arthur config helper.")
    parser.add_argument("--config", help="Path to arthur.config.json")
    parser.add_argument("--validate", action="store_true", help="Validate required config fields.")
    args = parser.parse_args()
    if not args.validate:
        parser.print_help()
        return 0

    path = pathlib.Path(args.config) if args.config else DEFAULT_CONFIG_PATH
    if not path.exists():
        print(f"Arthur config validation failed:\n- Config file is required and was not found: {path}", file=sys.stderr)
        return 1
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        print(f"Arthur config validation failed:\n- Arthur config root must be an object: {path}", file=sys.stderr)
        return 1
    errors = validate_config(_merge(DEFAULT_CONFIG, data), path)
    if errors:
        print("Arthur config validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"Arthur config validation passed: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
