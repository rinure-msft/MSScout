import json
import os
import pathlib
import re
import sys
from copy import deepcopy
from typing import Any


MODULE_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = MODULE_DIR / "arthur.config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "assistantName": "Arthur",
    "userDisplayName": "<YOUR_NAME>",
    "userFirstName": "<YOUR_FIRST_NAME>",
    "timezone": "Mountain Standard Time",
    "voice": {
        "tts": "edge",
        "edgeVoice": "en-US-BrianNeural",
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
    "notification": {
        "selfEmail": "<YOUR_EMAIL>",
        "teamsSelfMessage": True,
    },
    "azureDevOps": {
        "organization": "<ADO_ORGANIZATION>",
        "project": "<ADO_PROJECT>",
        "url": "https://dev.azure.com/<ADO_ORGANIZATION>/<ADO_PROJECT>",
        "tag": "ArthurActionTracker",
        "defaultAssignee": "<YOUR_NAME>",
        "defaultAssigneeEmail": "<YOUR_EMAIL>",
        "defaultWorkItemType": "Task",
    },
    "runtime": {
        "scratchpadPath": str(MODULE_DIR),
        "workiqPath": str(pathlib.Path.home() / ".copilot" / "bin" / "workiq.cmd"),
        "automationFile": str(pathlib.Path.home() / ".copilot" / "m-automations" / "automations.json"),
        "promptResponderAutomationId": "2w51kbs3mqra79xo",
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
}

REQUIRED_CONFIG_FIELDS = (
    "userDisplayName",
    "userFirstName",
    "timezone",
    "voice.tts",
    "voice.edgeVoice",
    "microphone.deviceIndex",
    "microphone.threshold",
    "notification.selfEmail",
    "azureDevOps.organization",
    "azureDevOps.project",
    "azureDevOps.url",
    "azureDevOps.tag",
    "azureDevOps.defaultAssignee",
    "azureDevOps.defaultAssigneeEmail",
    "runtime.scratchpadPath",
    "runtime.workiqPath",
    "runtime.automationFile",
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
    tts = str(_get_from(config, "voice.tts") or "")
    if tts and tts not in {"edge", "windows"}:
        errors.append("voice.tts must be 'edge' or 'windows'")
    try:
        int(_get_from(config, "microphone.deviceIndex"))
    except (TypeError, ValueError):
        errors.append("microphone.deviceIndex must be an integer")
    try:
        int(_get_from(config, "microphone.threshold"))
    except (TypeError, ValueError):
        errors.append("microphone.threshold must be an integer")
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
        r"C:\Users\riur\OneDrive - Microsoft\Documents\Microsoft Scout\Scratchpad": scratchpad,
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
