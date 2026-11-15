"""Unit tests for the JSONL session log written at the end of a session."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import Config
from loop2 import WhisperResult
from main import Session, _write_session_log


def _session(debug_logs: bool = False) -> Session:
    return Session(
        Config(
            llm_provider="openai",
            llm_api_key="key",
            llm_model="model",
            deepgram_api_key="dg-key",
            prompt_file="prompts/v2.txt",
            debug_logs=debug_logs,
        )
    )


class SessionLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.addCleanup(os.chdir, self._cwd)

    def _records(self) -> list[dict]:
        files = list(Path("logs").glob("session-*.jsonl"))
        self.assertEqual(len(files), 1)
        return [json.loads(l) for l in files[0].read_text(encoding="utf-8").splitlines()]

    def test_no_whispers_writes_no_file(self) -> None:
        with patch("builtins.print"):
            _write_session_log(_session())
        self.assertFalse(Path("logs").exists())

    def test_writes_whispers_and_summary(self) -> None:
        session = _session()
        session.started_at = "2026-03-10T10:00:00"
        session.whisper_results = [
            WhisperResult(timestamp="t1", trigger_type="manual", llm_response="a",
                          user_rating=4, transcript_sent_to_llm="secret", spoken_text="s"),
            WhisperResult(timestamp="t2", trigger_type="timer", llm_response="b",
                          user_rating=2, aborted=True),
            WhisperResult(timestamp="t3", trigger_type="timer", llm_response="c"),
        ]
        with patch("builtins.print"):
            _write_session_log(session)

        records = self._records()
        self.assertEqual([r["type"] for r in records], ["whisper"] * 3 + ["summary"])
        # Transcript text is only logged in debug mode.
        self.assertNotIn("transcript_sent_to_llm", records[0])
        summary = records[-1]
        self.assertEqual(summary["total_whispers"], 3)
        self.assertEqual(summary["avg_rating"], 3.0)  # unrated whispers are ignored
        self.assertEqual(summary["abort_count"], 1)
        self.assertEqual(summary["prompt_version"], "v2")
        self.assertEqual(summary["session_start"], "2026-03-10T10:00:00")

    def test_debug_mode_adds_events_and_transcript_fields(self) -> None:
        session = _session(debug_logs=True)
        session.event_log = [{"timestamp": "t0", "event": "START"}]
        session.whisper_results = [
            WhisperResult(timestamp="t1", transcript_sent_to_llm="hello", spoken_text="hi")
        ]
        with patch("builtins.print"):
            _write_session_log(session)

        records = self._records()
        self.assertEqual(records[0]["type"], "event")
        self.assertEqual(records[0]["event"], "START")
        whisper = records[1]
        self.assertEqual(whisper["transcript_sent_to_llm"], "hello")
        self.assertEqual(whisper["spoken_text"], "hi")


if __name__ == "__main__":
    unittest.main()
