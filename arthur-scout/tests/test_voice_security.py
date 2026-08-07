from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

import arthur_voice_bridge as bridge
import arthur_queue_watchdog as watchdog
import arthur_config


class VoiceSecurityTests(unittest.TestCase):
    def tearDown(self) -> None:
        bridge.SMOKE_TEST_MODE = False

    def test_wake_name_must_start_the_utterance(self) -> None:
        self.assertEqual(bridge.strip_wake_word("Arthur status", "Arthur"), "status")
        self.assertEqual(
            bridge.strip_wake_word("Hey Arthur, status", "Arthur"),
            "status",
        )
        self.assertIsNone(
            bridge.strip_wake_word(
                "I was talking to Arthur about status",
                "Arthur",
            )
        )

    def test_command_matching_is_exact_or_explicit_prefix(self) -> None:
        self.assertTrue(bridge.command_matches("status", "status"))
        self.assertFalse(bridge.command_matches("please show status", "status"))
        self.assertTrue(
            bridge.command_matches(
                "search the web for Arthur",
                "search the web for *",
            )
        )
        self.assertFalse(
            bridge.command_matches(
                "please search the web for Arthur",
                "search the web for *",
            )
        )

    def test_calendar_question_maps_to_enabled_daily_briefing(self) -> None:
        intent = bridge.interpret_intent("what is on my calendar today")

        self.assertIsNotNone(intent.command)
        self.assertEqual(intent.command.handler, "daily_briefing")
        self.assertEqual(intent.source, "natural-language")

    def test_security_smoke_blocks_unmatched_voice_handoffs(self) -> None:
        result = bridge.run_command_smoke_tests()

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["security_failures"], [])

    def test_scout_queueing_can_be_turned_off(self) -> None:
        bridge.SMOKE_TEST_MODE = True
        bridge.SMOKE_TEST_ACTIONS = []
        scout = bridge.CONFIG.setdefault("scout", {})
        previous = scout.get("queueEnabled", True)
        scout["queueEnabled"] = False
        try:
            self.assertIsNone(bridge.enqueue_prompt("test prompt"))
            self.assertFalse(
                any(
                    action["kind"] == "enqueue_prompt"
                    for action in bridge.SMOKE_TEST_ACTIONS
                )
            )
        finally:
            scout["queueEnabled"] = previous

    def test_scout_queueing_defaults_on(self) -> None:
        self.assertTrue(
            bridge.CONFIG.get("scout", {}).get("queueEnabled")
        )

    def test_default_profile_includes_explicit_calendar_and_handoff_commands(self) -> None:
        enabled = arthur_config.DEFAULT_CONFIG["enabledCommands"]

        self.assertIn("calendar_summary", enabled)
        self.assertIn("fast_mbr_review", enabled)
        self.assertNotIn("prompt_window", enabled)

    def test_claimed_voice_prompt_retains_authorization_metadata(self) -> None:
        original_queue_file = watchdog.QUEUE_FILE
        try:
            with tempfile.TemporaryDirectory() as directory:
                watchdog.QUEUE_FILE = pathlib.Path(directory) / "queue.jsonl"
                watchdog.QUEUE_FILE.write_text(
                    json.dumps(
                        {
                            "id": "voice-1",
                            "status": "pending",
                            "prompt": "open dashboard",
                            "spoken_prompt": "open dashboard",
                            "source": "voice",
                            "authorization": "enabled_command",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(watchdog.claim_next("test-runner"), 0)
                claim = json.loads(output.getvalue())
        finally:
            watchdog.QUEUE_FILE = original_queue_file

        self.assertEqual(claim["source"], "voice")
        self.assertEqual(claim["authorization"], "enabled_command")


if __name__ == "__main__":
    unittest.main()
