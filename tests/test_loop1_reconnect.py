"""Unit tests for Loop 1 Deepgram reconnect handling."""

import unittest
from unittest.mock import AsyncMock, patch

import websockets

import loop1


def _closed() -> websockets.ConnectionClosed:
    return websockets.ConnectionClosed(None, None)


class _ClosedWs:
    async def recv(self):
        raise _closed()


class _OpenWs:
    async def recv(self):
        # Stop the receive loop after the reconnect has delivered one message.
        loop1._running = False
        return '{"event": "Update", "transcript": "hello after reconnect"}'


class Loop1ReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._saved = (loop1._ws, loop1._running, loop1._current_config)
        loop1._running = True
        loop1._current_config = object()

    async def asyncTearDown(self) -> None:
        loop1._ws, loop1._running, loop1._current_config = self._saved

    async def test_keeps_receiving_after_connection_closed_and_reconnect(self) -> None:
        loop1._ws = _ClosedWs()
        buffer: list = []
        connect = AsyncMock(return_value=_OpenWs())

        with (
            patch("loop1._connect_deepgram", new=connect),
            patch("loop1.asyncio.sleep", new=AsyncMock()),
            patch("builtins.print"),
        ):
            await loop1._receive_transcripts(buffer)

        connect.assert_awaited_once()
        self.assertEqual([e["text"] for e in buffer], ["hello after reconnect"])

    async def test_retries_when_reconnect_fails(self) -> None:
        loop1._ws = _ClosedWs()
        buffer: list = []
        connect = AsyncMock(side_effect=[OSError("down"), _OpenWs()])

        with (
            patch("loop1._connect_deepgram", new=connect),
            patch("loop1.asyncio.sleep", new=AsyncMock()),
            patch("builtins.print"),
        ):
            await loop1._receive_transcripts(buffer)

        self.assertEqual(connect.await_count, 2)
        self.assertEqual(len(buffer), 1)

    async def test_does_not_reconnect_when_stopped(self) -> None:
        class _StopWs:
            async def recv(self):
                loop1._running = False
                raise _closed()

        loop1._ws = _StopWs()
        connect = AsyncMock()

        with patch("loop1._connect_deepgram", new=connect), patch("builtins.print"):
            await loop1._receive_transcripts([])

        connect.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
