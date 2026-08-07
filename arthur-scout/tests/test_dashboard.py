from __future__ import annotations

import os
import pathlib
import sys
import unittest


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SOURCE_ROOT))

import arthur_config
import arthur_status_dashboard
import arthur_voice_bridge as bridge


class DashboardTests(unittest.TestCase):
    def tearDown(self) -> None:
        bridge.SMOKE_TEST_MODE = False

    def test_dashboard_uses_arthur_visual_language(self) -> None:
        dashboard = arthur_status_dashboard.build_html()

        self.assertIn('class="brand-mark"', dashboard)
        self.assertIn("Status Dashboard", dashboard)
        self.assertIn("--cp-bg:", dashboard)
        self.assertIn('class="badge', dashboard)
        self.assertNotIn("data-icon=", dashboard)

    def test_open_dashboard_is_enabled_and_local(self) -> None:
        self.assertIn(
            "open_dashboard",
            arthur_config.DEFAULT_CONFIG["enabledCommands"],
        )
        self.assertEqual(
            bridge.ARTHUR_DASHBOARD_URL,
            "http://127.0.0.1:8765/dashboard",
        )

    def test_open_dashboard_handler_uses_tracked_browser(self) -> None:
        bridge.SMOKE_TEST_MODE = True
        bridge.SMOKE_TEST_ACTIONS = []
        speaker = bridge.SmokeTestSpeaker()
        command = next(
            item
            for item in bridge.COMMANDS
            if item.handler == "open_dashboard"
        )

        self.assertTrue(
            bridge.h_open_dashboard(
                "open dashboard",
                speaker,
                command,
            )
        )
        self.assertTrue(
            any(
                action["kind"] == "open_tracked_browser"
                and action["detail"] == bridge.ARTHUR_DASHBOARD_URL
                for action in bridge.SMOKE_TEST_ACTIONS
            )
        )


if __name__ == "__main__":
    unittest.main()
