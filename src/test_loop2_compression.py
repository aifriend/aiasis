"""Unit tests for coaching text compression."""

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from loop2 import _compress_coaching_text


class Loop2CompressionTests(unittest.TestCase):
    def test_keeps_short_text_unchanged(self) -> None:
        text = "Address budget risk and lock next steps now."
        self.assertEqual(_compress_coaching_text(text, 20), text)

    def test_compresses_multiline_and_caps_words(self) -> None:
        text = "- You said basically five times.\n- Confirm owner, deadline, and risk mitigation before closing."
        compressed = _compress_coaching_text(text, 8)
        self.assertLessEqual(len(compressed.split()), 8)

    def test_prefers_actionable_sentence_over_generic_one(self) -> None:
        text = (
            "Your pacing is okay. "
            "Address the blocker now and confirm owner plus deadline."
        )
        compressed = _compress_coaching_text(text, 14)
        self.assertIn("Address the blocker now", compressed)


if __name__ == "__main__":
    unittest.main()
