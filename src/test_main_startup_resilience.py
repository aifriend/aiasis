"""Unit tests for graceful startup failure handling."""

import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from main import Session, _handle_key, _teardown


class MainStartupResilienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_key_does_not_crash_on_listen_failure(self) -> None:
        session = Session(
            Config(
                llm_provider="openai",
                llm_api_key="key",
                llm_model="model",
                deepgram_api_key="dg-key",
                prompt_file="prompts/v1.txt",
            )
        )

        with patch("main.start_listening", new=AsyncMock(side_effect=TimeoutError("timed out"))):
            keep_running = await _handle_key("s", session)

        self.assertTrue(keep_running)
        self.assertFalse(session.active)

    async def test_teardown_always_stops_listening_even_when_inactive(self) -> None:
        session = Session(
            Config(
                llm_provider="openai",
                llm_api_key="key",
                llm_model="model",
                deepgram_api_key="dg-key",
                prompt_file="prompts/v1.txt",
            )
        )
        session.active = False

        with (
            patch("main.abort_playback"),
            patch("main.stop_listening", new=AsyncMock()) as stop_mock,
            patch("main._write_session_log"),
            patch("main._restore_terminal"),
            patch("builtins.print"),
        ):
            await _teardown(session)

        stop_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
