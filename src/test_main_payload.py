"""Unit tests for incremental whisper payload selection."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import _build_whisper_payload


class MainPayloadTests(unittest.TestCase):
    def test_first_payload_sends_all_entries(self) -> None:
        buffer = [
            {"timestamp": "2026-03-10T10:00:00", "text": "a"},
            {"timestamp": "2026-03-10T10:00:01", "text": "b"},
        ]
        payload, newest = _build_whisper_payload(buffer, None, tail_entries=3)
        self.assertEqual(len(payload), 2)
        self.assertEqual(newest, "2026-03-10T10:00:01")

    def test_subsequent_payload_sends_tail_plus_new(self) -> None:
        buffer = [
            {"timestamp": "2026-03-10T10:00:00", "text": "old-1"},
            {"timestamp": "2026-03-10T10:00:01", "text": "old-2"},
            {"timestamp": "2026-03-10T10:00:02", "text": "new-1"},
            {"timestamp": "2026-03-10T10:00:03", "text": "new-2"},
        ]
        payload, newest = _build_whisper_payload(
            buffer,
            "2026-03-10T10:00:01",
            tail_entries=1,
        )
        self.assertEqual([e["text"] for e in payload], ["old-2", "new-1", "new-2"])
        self.assertEqual(newest, "2026-03-10T10:00:03")

    def test_returns_empty_when_no_new_entries(self) -> None:
        buffer = [
            {"timestamp": "2026-03-10T10:00:00", "text": "old-1"},
            {"timestamp": "2026-03-10T10:00:01", "text": "old-2"},
        ]
        payload, newest = _build_whisper_payload(
            buffer,
            "2026-03-10T10:00:01",
            tail_entries=2,
        )
        self.assertEqual(payload, [])
        self.assertEqual(newest, "2026-03-10T10:00:01")


if __name__ == "__main__":
    unittest.main()
