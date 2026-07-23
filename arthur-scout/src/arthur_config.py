import json
import os
import pathlib
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
        "Rin.Ure@microsoft.com": self_email(),
        "rin.ure@microsoft.com": self_email(),
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
