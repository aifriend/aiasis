"""Loop 1: Audio capture → Silero VAD → Deepgram Flux v2 STT → transcript buffer."""

import asyncio
import base64
import json
import time
from collections.abc import Callable
from datetime import datetime

import numpy as np
import sounddevice as sd
import torch
import websockets

from config import Config, SAMPLE_RATE, VAD_CHUNK_SIZE, VAD_THRESHOLD

# ── Types ────────────────────────────────────────────────────────────────────

TranscriptEntry = dict  # {"timestamp": str, "text": str, "turn_index": int}


# ── Module state ─────────────────────────────────────────────────────────────

_stream: sd.InputStream | None = None
_ws: websockets.WebSocketClientProtocol | None = None
_vad_model: torch.jit.ScriptModule | None = None
_audio_queue: asyncio.Queue | None = None
_paused = False
_running = False
_tasks: list[asyncio.Task] = []
_dropped_audio_frames = 0


# ── VAD setup ────────────────────────────────────────────────────────────────

def _load_vad() -> torch.jit.ScriptModule:
    """Load Silero VAD model (cached after first call)."""
    global _vad_model
    if _vad_model is None:
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        _vad_model = model
    return _vad_model


def _is_speech(chunk_int16: np.ndarray) -> bool:
    """Run Silero VAD on a single chunk. Returns True if speech detected."""
    vad = _load_vad()
    # int16 → float32 normalized to [-1, 1]
    audio_float = chunk_int16.astype(np.float32) / 32768.0
    tensor = torch.from_numpy(audio_float.squeeze())
    prob = vad(tensor, SAMPLE_RATE).item()
    return prob >= VAD_THRESHOLD


# ── Deepgram v2 Flux WebSocket ───────────────────────────────────────────────

def _build_deepgram_url(config: Config) -> str:
    """Build the Deepgram v2 Flux WebSocket URL with query params."""
    base = "wss://api.deepgram.com/v2/listen"
    params = (
        "model=flux-general-en"
        "&encoding=linear16"
        f"&sample_rate={SAMPLE_RATE}"
        "&eot_threshold=0.7"
        "&eot_timeout_ms=5000"
    )
    return f"{base}?{params}"


async def _connect_deepgram(config: Config) -> websockets.WebSocketClientProtocol:
    """Open WebSocket to Deepgram v2 Flux API with limited retries."""
    url = _build_deepgram_url(config)
    headers = {"Authorization": f"Token {config.deepgram_api_key}"}
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            ws = await websockets.connect(
                url,
                additional_headers=headers,
                open_timeout=15,
            )
            print("  ✓ Deepgram v2 Flux connected")
            return ws
        except Exception as e:
            last_error = e
            if attempt < 3:
                print(f"  ⚠ Deepgram connect failed (attempt {attempt}/3): {e}")
                await asyncio.sleep(1.5 * attempt)

    raise TimeoutError(f"Deepgram connection failed after 3 attempts: {last_error}")


async def _receive_transcripts(
    transcript_buffer: list[TranscriptEntry],
    on_end_of_turn: Callable[[int], None] | None = None,
) -> None:
    """Read messages from Deepgram WS, append finals to buffer."""
    global _ws, _running

    while _running and _ws is not None:
        try:
            raw = await _ws.recv()
            # Deepgram v2 sends base64-encoded JSON (when using binary mode)
            # or plain JSON text — handle both
            if isinstance(raw, bytes):
                data = json.loads(raw.decode("utf-8"))
            else:
                data = json.loads(raw)

            event = data.get("event", "")
            turn_index = data.get("turn_index")
            transcript = data.get("transcript", "").strip()

            if event == "StartOfTurn":
                print(f"  🎙 Turn {turn_index} started")

            if transcript:
                entry: TranscriptEntry = {
                    "timestamp": datetime.now().isoformat(),
                    "text": transcript,
                    "turn_index": turn_index or 0,
                }
                transcript_buffer.append(entry)
                print(f"  📝 [{turn_index}] {transcript}")

            if event == "EndOfTurn":
                confidence = data.get("end_of_turn_confidence", 0)
                print(f"  ⏹ Turn {turn_index} ended (confidence: {confidence})")
                if on_end_of_turn:
                    on_end_of_turn(turn_index)

        except websockets.ConnectionClosed:
            if _running:
                print("  ⚠ Deepgram connection lost. Reconnecting in 2s...")
                await asyncio.sleep(2)
                try:
                    _ws = await _connect_deepgram(_current_config)
                except Exception as e:
                    print(f"  ✖ Reconnect failed: {e}")
                    await asyncio.sleep(5)
            break
        except json.JSONDecodeError as e:
            print(f"  ⚠ Bad JSON from Deepgram: {e}")
        except Exception as e:
            if _running:
                print(f"  ⚠ Receive error: {e}")
            break


# ── Audio capture → VAD → Deepgram ──────────────────────────────────────────

_current_config: Config = None  # set on start_listening
_speech_seconds: float = 0.0


def _enqueue_audio_chunk(chunk: np.ndarray) -> None:
    """Queue one audio chunk without raising on overflow."""
    global _dropped_audio_frames
    if _audio_queue is None:
        return
    try:
        _audio_queue.put_nowait(chunk)
    except asyncio.QueueFull:
        _dropped_audio_frames += 1
        # Throttle logs to avoid flooding terminal under sustained overload.
        if _dropped_audio_frames in (1, 10) or _dropped_audio_frames % 100 == 0:
            print(
                f"  ⚠ Audio queue full, dropping frames "
                f"(total dropped: {_dropped_audio_frames})"
            )


def _schedule_audio_chunk(loop: asyncio.AbstractEventLoop, chunk: np.ndarray) -> None:
    """Safely schedule chunk enqueue from the sounddevice callback thread."""
    if loop.is_closed():
        return
    try:
        loop.call_soon_threadsafe(_enqueue_audio_chunk, chunk)
    except RuntimeError:
        # Happens during interpreter/loop shutdown races; safe to ignore.
        return


async def _audio_processor(
    config: Config,
    on_speech_time: Callable[[float], None] | None = None,
) -> None:
    """Consume audio queue: VAD filter → send speech to Deepgram."""
    global _ws, _running, _speech_seconds

    chunk_duration = VAD_CHUNK_SIZE / SAMPLE_RATE  # seconds per chunk

    while _running:
        try:
            chunk = await asyncio.wait_for(_audio_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue

        if _paused:
            continue

        # VAD: only send speech chunks to Deepgram
        try:
            if _is_speech(chunk):
                _speech_seconds += chunk_duration
                if on_speech_time:
                    on_speech_time(_speech_seconds)

                # Send raw int16 bytes to Deepgram
                if _ws is not None:
                    try:
                        await _ws.send(chunk.tobytes())
                    except websockets.ConnectionClosed:
                        print("  ⚠ WS closed during send")
        except Exception as e:
            print(f"  ⚠ VAD/send error: {e}")


# ── Public interface ─────────────────────────────────────────────────────────

async def start_listening(
    config: Config,
    transcript_buffer: list[TranscriptEntry],
    on_speech_time: Callable[[float], None] | None = None,
    on_end_of_turn: Callable[[int], None] | None = None,
) -> None:
    """Start the full Loop 1 pipeline: mic → VAD → Deepgram → buffer."""
    global _stream, _ws, _audio_queue, _running, _paused, _speech_seconds
    global _current_config, _tasks
    global _dropped_audio_frames

    _current_config = config
    _running = True
    _paused = False
    _speech_seconds = 0.0
    _dropped_audio_frames = 0
    _audio_queue = asyncio.Queue(maxsize=200)

    loop = asyncio.get_event_loop()

    # 1. Connect to Deepgram
    try:
        _ws = await _connect_deepgram(config)
    except Exception as e:
        print(f"  ✖ Cannot connect to Deepgram: {e}")
        _running = False
        raise

    # 2. Start audio capture
    def audio_callback(indata: np.ndarray, frames: int, time_info, status):
        if status:
            print(f"  ⚠ Audio: {status}")
        # Thread-safe push to asyncio queue
        _schedule_audio_chunk(loop, indata.copy())

    _stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        blocksize=VAD_CHUNK_SIZE,
        device=config.input_device,
        channels=1,
        dtype="int16",
        callback=audio_callback,
    )
    _stream.start()
    print("  ✓ Microphone capture started")

    # 3. Launch async tasks
    t1 = asyncio.create_task(_audio_processor(config, on_speech_time))
    t2 = asyncio.create_task(_receive_transcripts(transcript_buffer, on_end_of_turn))
    _tasks = [t1, t2]


async def stop_listening() -> None:
    """Stop capture, close Deepgram, cancel tasks."""
    global _stream, _ws, _running, _tasks

    _running = False

    # Stop audio stream
    stream = _stream
    _stream = None
    if stream is not None:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_stop_and_close_stream, stream),
                timeout=2.0,
            )
            print("  ✓ Microphone stopped")
        except TimeoutError:
            print("  ⚠ Timed out stopping microphone stream")
        except Exception as e:
            print(f"  ⚠ Error stopping microphone stream: {e}")

    # Close Deepgram
    ws = _ws
    _ws = None
    if ws is not None:
        try:
            await asyncio.wait_for(ws.close(), timeout=2.0)
            print("  ✓ Deepgram disconnected")
        except TimeoutError:
            print("  ⚠ Timed out disconnecting Deepgram")
        except Exception as e:
            print(f"  ⚠ Error disconnecting Deepgram: {e}")

    # Cancel tasks
    tasks = list(_tasks)
    _tasks = []
    for t in tasks:
        t.cancel()
    for t in tasks:
        try:
            await asyncio.wait_for(t, timeout=1.0)
        except asyncio.CancelledError:
            pass
        except TimeoutError:
            print("  ⚠ Timed out waiting for Loop 1 task shutdown")
        except Exception as e:
            print(f"  ⚠ Loop 1 task shutdown error: {e}")


def _stop_and_close_stream(stream: sd.InputStream) -> None:
    """Stop and close stream from a worker thread to avoid blocking asyncio loop."""
    stream.stop()
    stream.close()


def pause() -> None:
    """Pause audio forwarding (keep capturing but don't send)."""
    global _paused
    _paused = True
    print("  ⏸ Listening paused")


def resume() -> None:
    """Resume audio forwarding."""
    global _paused
    _paused = False
    print("  ▶ Listening resumed")


def is_paused() -> bool:
    """Return whether Loop 1 forwarding is currently paused."""
    return _paused


def get_speech_seconds() -> float:
    """Return accumulated speech seconds since last reset."""
    return _speech_seconds


def reset_speech_seconds() -> None:
    """Reset the speech counter (after a trigger)."""
    global _speech_seconds
    _speech_seconds = 0.0
