"""Unit tests for debug log gating in Loop 2."""

import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import Config
from loop2 import trigger_whisper


class Loop2DebugFlagsTests(unittest.IsolatedAsyncioTestCase):
    async def test_debug_payload_fields_disabled_by_default(self) -> None:
        config = Config(
            llm_provider="openai",
            llm_api_key="test-key",
            llm_model="test-model",
            deepgram_api_key="test-deepgram",
            prompt_file="prompts/v1.txt",
            debug_logs=False,
        )

        with (
            patch("loop2._call_llm", new=AsyncMock(return_value="Confirm owner and deadline.")),
            patch("loop2._synthesize_tts", new=AsyncMock(return_value=([[0.0]], 16000))),
            patch("loop2._play_audio", new=AsyncMock(return_value=450.0)),
        ):
            result = await trigger_whisper(
                config=config,
                transcript_buffer=[{"timestamp": "2026-01-01T00:00:00", "text": "hello"}],
                previous_whispers=[],
                trigger_type="manual",
            )

        self.assertEqual(result.transcript_sent_to_llm, "")
        self.assertEqual(result.spoken_text, "")
        self.assertTrue(result.llm_response)


if __name__ == "__main__":
    unittest.main()
