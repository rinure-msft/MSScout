import argparse
import json
import pathlib
import sys
from typing import Any


MODULE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))

from arthur_voice_bridge import COMMANDS, HANDLERS, find_command  # noqa: E402


class SilentSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def say(self, text: str) -> None:
        self.spoken.append(text)


def run_briefing(briefing: str) -> dict[str, Any]:
    phrase = "daily briefing" if briefing == "morning" else "evening brief"
    command = find_command(phrase)
    if command is None:
        raise RuntimeError(f"Arthur command not found: {phrase}")
    speaker = SilentSpeaker()
    result = HANDLERS[command.handler](phrase, speaker, command)
    return {
        "status": "queued",
        "briefing": briefing,
        "command": command.name,
        "phrase": phrase,
        "handler": command.handler,
        "handler_result": result,
        "spoken": speaker.spoken,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Queue scheduled Arthur briefing commands.")
    parser.add_argument("--briefing", choices=("morning", "evening"), required=True)
    args = parser.parse_args()
    print(json.dumps(run_briefing(args.briefing), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
