"""Unit tests for Loop 2 playback event logging hooks."""

import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from loop2 import trigger_whisper


class Loop2LoggingTests(unittest.IsolatedAsyncioTestCase):
    async def test_trigger_whisper_emits_playback_events(self) -> None:
        config = Config(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_model="test-model",
            deepgram_api_key="test-deepgram",
            prompt_file="prompts/v1.txt",
            debug_logs=True,
        )
        transcript_buffer = [{"timestamp": "2026-01-01T00:00:00", "text": "hello"}]
        events: list[tuple[str, dict]] = []

        def on_playback_event(event: str, payload: dict) -> None:
            events.append((event, payload))

        with (
            patch("loop2._call_llm", new=AsyncMock(return_value="Do this next.")),
            patch("loop2._synthesize_tts", new=AsyncMock(return_value=([[0.0]], 16000))),
            patch("loop2._play_audio", new=AsyncMock(return_value=850.0)),
        ):
            result = await trigger_whisper(
                config=config,
                transcript_buffer=transcript_buffer,
                previous_whispers=[],
                trigger_type="manual",
                on_playback_event=on_playback_event,
            )

        self.assertEqual(result.tts_duration_ms, 850)
        self.assertFalse(result.aborted)
        self.assertIn("[2026-01-01T00:00:00] hello", result.transcript_sent_to_llm)
        self.assertEqual(result.spoken_text, result.llm_response)
        self.assertEqual(events[0][0], "coaching_voice_started")
        self.assertEqual(events[1][0], "coaching_voice_finished")
        self.assertEqual(events[1][1]["duration_ms"], 850)


if __name__ == "__main__":
    unittest.main()
