"""Unit tests for Loop 1 queue overflow handling."""

import asyncio
import sys
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import loop1


class Loop1QueueOverflowTests(unittest.TestCase):
    def test_enqueue_drops_when_queue_is_full_without_raising(self) -> None:
        loop1._audio_queue = asyncio.Queue(maxsize=1)
        loop1._dropped_audio_frames = 0

        first = np.zeros((512, 1), dtype=np.int16)
        second = np.ones((512, 1), dtype=np.int16)

        loop1._enqueue_audio_chunk(first)
        with patch("builtins.print") as mock_print:
            loop1._enqueue_audio_chunk(second)

        self.assertEqual(loop1._audio_queue.qsize(), 1)
        self.assertEqual(loop1._dropped_audio_frames, 1)
        self.assertTrue(mock_print.called)

    def test_schedule_audio_chunk_noop_when_loop_closed(self) -> None:
        class ClosedLoop:
            def is_closed(self) -> bool:
                return True

            def call_soon_threadsafe(self, callback, arg):
                raise AssertionError("call_soon_threadsafe should not be invoked")

        with patch("loop1._enqueue_audio_chunk") as mock_enqueue:
            loop1._schedule_audio_chunk(ClosedLoop(), np.zeros((1, 1), dtype=np.int16))

        mock_enqueue.assert_not_called()

    def test_schedule_audio_chunk_ignores_runtime_error(self) -> None:
        class RuntimeErrorLoop:
            def is_closed(self) -> bool:
                return False

            def call_soon_threadsafe(self, callback, arg):
                raise RuntimeError("Event loop is closed")

        with patch("loop1._enqueue_audio_chunk") as mock_enqueue:
            loop1._schedule_audio_chunk(
                RuntimeErrorLoop(),
                np.zeros((1, 1), dtype=np.int16),
            )

        mock_enqueue.assert_not_called()


class Loop1StopListeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_stop_listening_times_out_hung_stream_without_raising(self) -> None:
        class DummyStream:
            pass

        loop1._stream = DummyStream()
        loop1._ws = None
        loop1._tasks = []

        async def fake_wait_for(awaitable, timeout):
            # Close the to_thread coroutine to avoid "never awaited" warnings.
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise TimeoutError

        with (
            patch("loop1._stop_and_close_stream"),
            patch("loop1.asyncio.wait_for", side_effect=fake_wait_for),
            patch("builtins.print") as mock_print,
        ):
            await loop1.stop_listening()

        self.assertTrue(
            any("Timed out stopping microphone stream" in str(c) for c in mock_print.call_args_list)
        )

    async def test_stop_listening_closes_ws_and_cancels_tasks(self) -> None:
        loop1._stream = None
        ws = AsyncMock()
        ws.close = AsyncMock(return_value=None)
        loop1._ws = ws

        task = asyncio.create_task(asyncio.sleep(60))
        loop1._tasks = [task]

        await loop1.stop_listening()

        ws.close.assert_awaited_once()
        self.assertTrue(task.cancelled())


if __name__ == "__main__":
    unittest.main()
