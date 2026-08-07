from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import tempfile
import time
from typing import Any

import edge_tts
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame
import pyttsx3
import sounddevice as sd


def edge_voice_entry(voice: dict[str, Any]) -> dict[str, Any]:
    tag = voice.get("VoiceTag")
    personalities = (
        tag.get("VoicePersonalities", [])
        if isinstance(tag, dict)
        else []
    )
    return {
        "id": str(voice.get("ShortName") or voice.get("Name") or ""),
        "name": str(voice.get("FriendlyName") or voice.get("ShortName") or ""),
        "locale": str(voice.get("Locale") or ""),
        "gender": str(voice.get("Gender") or ""),
        "provider": "edge",
        "personalities": [
            str(item) for item in personalities if str(item).strip()
        ],
    }


async def list_edge_voices() -> list[dict[str, Any]]:
    voices = [edge_voice_entry(voice) for voice in await edge_tts.list_voices()]
    return sorted(voices, key=lambda item: (item["locale"], item["name"]))


def list_windows_voices() -> list[dict[str, Any]]:
    engine = pyttsx3.init()
    try:
        voices = []
        for voice in engine.getProperty("voices"):
            languages = []
            for language in getattr(voice, "languages", []) or []:
                if isinstance(language, bytes):
                    languages.append(
                        language.decode("utf-8", errors="replace").lstrip("\x05")
                    )
                else:
                    languages.append(str(language))
            voices.append(
                {
                    "id": str(voice.id),
                    "name": str(voice.name),
                    "locale": ", ".join(languages),
                    "gender": str(getattr(voice, "gender", "") or ""),
                    "provider": "windows",
                    "personalities": [],
                }
            )
        return sorted(voices, key=lambda item: item["name"])
    finally:
        engine.stop()


def list_microphones() -> list[dict[str, Any]]:
    default_input = int(sd.default.device[0])
    return [
        {
            "index": index,
            "id": str(index),
            "name": str(device["name"]),
            "hostApi": str(device["hostapi"]),
            "isDefault": index == default_input,
            "channels": int(device["max_input_channels"]),
            "sampleRate": float(device["default_samplerate"]),
        }
        for index, device in enumerate(sd.query_devices())
        if int(device.get("max_input_channels", 0)) > 0
    ]


async def preview_edge(
    text: str,
    voice: str,
    rate: str,
    volume: str,
    pitch: str,
) -> None:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
        path = pathlib.Path(handle.name)
    try:
        await edge_tts.Communicate(
            text,
            voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
        ).save(str(path))
        pygame.mixer.init()
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            time.sleep(0.05)
        pygame.mixer.music.unload()
    finally:
        try:
            pygame.mixer.quit()
        except pygame.error:
            pass
        path.unlink(missing_ok=True)


def preview_windows(
    text: str,
    voice_id: str,
    rate: int,
    volume: float,
) -> None:
    engine = pyttsx3.init()
    try:
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.setProperty("rate", rate)
        engine.setProperty("volume", volume)
        engine.say(text)
        engine.runAndWait()
    finally:
        engine.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Arthur voice and microphone catalog.")
    parser.add_argument(
        "--list",
        choices=("edge", "windows", "microphones"),
    )
    parser.add_argument("--preview", choices=("edge", "windows"))
    parser.add_argument("--text", default="Hello, I am Arthur.")
    parser.add_argument("--voice", default="")
    parser.add_argument("--rate", default="+0%")
    parser.add_argument("--volume", default="+0%")
    parser.add_argument("--pitch", default="+0Hz")
    parser.add_argument("--windows-rate", type=int, default=180)
    parser.add_argument("--windows-volume", type=float, default=1.0)
    args = parser.parse_args()

    if args.list == "edge":
        result = asyncio.run(list_edge_voices())
    elif args.list == "windows":
        result = list_windows_voices()
    elif args.list == "microphones":
        result = list_microphones()
    elif args.preview == "edge":
        asyncio.run(
            preview_edge(
                args.text,
                args.voice or "en-GB-RyanNeural",
                args.rate,
                args.volume,
                args.pitch,
            )
        )
        result = {"status": "played", "provider": "edge"}
    elif args.preview == "windows":
        preview_windows(
            args.text,
            args.voice,
            args.windows_rate,
            args.windows_volume,
        )
        result = {"status": "played", "provider": "windows"}
    else:
        parser.error("Choose --list or --preview")

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
