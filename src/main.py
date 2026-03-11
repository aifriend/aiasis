"""AIASIS PoC — Session orchestration, keyboard controls, logging."""

import asyncio
import atexit
import json
import signal
import sys
import termios
import time
import tty
from datetime import datetime
from pathlib import Path

from config import Config, BUFFER_MAX_AGE_MIN, parse_config, print_config
from loop1 import (
    start_listening,
    stop_listening,
    pause,
    resume,
    is_paused,
    get_speech_seconds,
    reset_speech_seconds,
    TranscriptEntry,
)
from loop2 import trigger_whisper, abort_playback, is_playing, WhisperResult


# ── Session state ────────────────────────────────────────────────────────────

class Session:
    def __init__(self, config: Config):
        self.config = config
        self.transcript_buffer: list[TranscriptEntry] = []
        self.previous_whispers: list[str] = []
        self.whisper_results: list[WhisperResult] = []
        self.started_at: str = ""
        self.active = False
        self._whisper_in_progress = False
        self._skip_requested = False
        self._log_file: str = ""
        self.event_log: list[dict] = []
        self.last_sent_timestamp: str | None = None


# ── Terminal raw mode ────────────────────────────────────────────────────────

_original_termios = None


def _enter_cbreak() -> None:
    global _original_termios
    if not sys.stdin.isatty():
        return  # non-interactive shell, skip cbreak
    _original_termios = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())


def _restore_terminal() -> None:
    if _original_termios is not None:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _original_termios)


# ── Rolling buffer management ────────────────────────────────────────────────

def _evict_old_entries(buffer: list[TranscriptEntry]) -> None:
    """Remove entries older than BUFFER_MAX_AGE_MIN from the buffer."""
    cutoff = time.time() - (BUFFER_MAX_AGE_MIN * 60)
    # Entries have ISO timestamps — compare via datetime
    i = 0
    while i < len(buffer):
        try:
            ts = datetime.fromisoformat(buffer[i]["timestamp"]).timestamp()
            if ts < cutoff:
                buffer.pop(i)
            else:
                i += 1
        except (ValueError, KeyError):
            i += 1


def _is_newer_timestamp(ts: str, last_ts: str | None) -> bool:
    """Return True if ts is newer than last_ts; parse failures are treated as new."""
    if last_ts is None:
        return True
    try:
        return datetime.fromisoformat(ts) > datetime.fromisoformat(last_ts)
    except (ValueError, TypeError):
        return True


def _build_whisper_payload(
    buffer: list[TranscriptEntry],
    last_sent_timestamp: str | None,
    tail_entries: int = 3,
) -> tuple[list[TranscriptEntry], str | None]:
    """
    Build incremental payload: [tail context] + [new entries].

    Returns (payload_entries, newest_timestamp_in_payload_or_existing_cursor).
    """
    if not buffer:
        return [], last_sent_timestamp

    first_new_idx: int | None = None
    for idx, entry in enumerate(buffer):
        ts = entry.get("timestamp", "")
        if _is_newer_timestamp(ts, last_sent_timestamp):
            first_new_idx = idx
            break

    if first_new_idx is None:
        return [], last_sent_timestamp

    start_idx = max(0, first_new_idx - tail_entries)
    payload = buffer[start_idx:]
    newest_ts = payload[-1].get("timestamp", last_sent_timestamp)
    return payload, newest_ts


# ── Session logging ──────────────────────────────────────────────────────────

def _write_session_log(session: Session) -> None:
    """Write full session to JSONL file."""
    if not session.whisper_results:
        print("  No whispers to log.")
        return

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    log_path = log_dir / f"session-{ts}.jsonl"

    with open(log_path, "w", encoding="utf-8") as f:
        # Write event markers only in debug mode (avoid extra runtime overhead by default)
        if session.config.debug_logs:
            for ev in session.event_log:
                line = {"type": "event", **ev}
                f.write(json.dumps(line) + "\n")

        # Write each whisper event
        for wr in session.whisper_results:
            line = {
                "type": "whisper",
                "timestamp": wr.timestamp,
                "trigger_type": wr.trigger_type,
                "transcript_chunk_length": wr.transcript_chunk_length,
                "llm_response": wr.llm_response,
                "tts_duration_ms": wr.tts_duration_ms,
                "user_rating": wr.user_rating,
                "aborted": wr.aborted,
                "prompt_version": wr.prompt_version,
            }
            if session.config.debug_logs:
                line["transcript_sent_to_llm"] = wr.transcript_sent_to_llm
                line["spoken_text"] = wr.spoken_text
            f.write(json.dumps(line) + "\n")

        # Write summary
        rated = [w for w in session.whisper_results if w.user_rating is not None]
        avg_rating = (
            sum(w.user_rating for w in rated) / len(rated)
            if rated else 0
        )
        abort_count = sum(1 for w in session.whisper_results if w.aborted)
        duration_min = 0
        if session.started_at:
            start = datetime.fromisoformat(session.started_at)
            duration_min = round((datetime.now() - start).total_seconds() / 60, 1)

        summary = {
            "type": "summary",
            "session_start": session.started_at,
            "session_end": datetime.now().isoformat(),
            "total_whispers": len(session.whisper_results),
            "avg_rating": round(avg_rating, 1),
            "abort_count": abort_count,
            "duration_minutes": duration_min,
            "prompt_version": Path(session.config.prompt_file).stem,
        }
        f.write(json.dumps(summary) + "\n")

    print(f"\n  📄 Session log saved: {log_path}")


def _log_event(session: Session, event: str, details: dict | None = None) -> None:
    """Append an event marker to session log and print it."""
    if not session.config.debug_logs:
        return
    record = {"timestamp": datetime.now().isoformat(), "event": event}
    if details:
        record.update(details)
    session.event_log.append(record)
    print(f"  📍 LOG_EVENT {event}")


# ── Whisper trigger (guarded) ────────────────────────────────────────────────

async def _do_whisper(session: Session, trigger_type: str) -> None:
    """Trigger Loop 2 with guard against concurrent runs."""
    if session._whisper_in_progress:
        print("  ⚠ Whisper already in progress, skipping")
        return

    if not session.transcript_buffer and trigger_type != "challenge":
        print("  ⚠ No transcript data yet, skipping")
        return

    session._whisper_in_progress = True
    paused_by_trigger = False
    next_sent_timestamp = session.last_sent_timestamp

    try:
        # For challenge triggers (e.g., initial prompt), use empty buffer
        if trigger_type == "challenge":
            payload_entries = []
        else:
            # Evict old buffer entries
            _evict_old_entries(session.transcript_buffer)

            payload_entries, next_sent_timestamp = _build_whisper_payload(
                session.transcript_buffer,
                session.last_sent_timestamp,
                tail_entries=3,
            )
            if not payload_entries:
                print("  ⚠ No new transcript since last whisper, skipping")
                _log_event(session, "whisper_skipped_no_new_transcript")
                return

        # Always pause listening during the entire whisper pipeline
        # (LLM call + TTS playback) to prevent the coach's own voice
        # from being captured by the mic and polluting the transcript.
        if not is_paused():
            pause()
            paused_by_trigger = True
            _log_event(session, "transcription_paused", {
                "reason": f"{trigger_type}_whisper_pipeline",
            })

        result = await trigger_whisper(
            config=session.config,
            transcript_buffer=payload_entries,
            previous_whispers=session.previous_whispers,
            trigger_type=trigger_type,
            on_playback_event=lambda event, payload: _log_event(session, event, payload),
        )

        session.whisper_results.append(result)

        # Track previous whispers for context (LLM de-duplication)
        if result.llm_response and not result.llm_response.startswith("[ERROR]"):
            session.previous_whispers.append(result.llm_response)
            session.last_sent_timestamp = next_sent_timestamp

        # Clear buffer entries that were captured before/during this whisper
        # so the coach's TTS residue doesn't leak into the next turn.
        session.transcript_buffer.clear()
        session.last_sent_timestamp = None

        # Reset speech counter after trigger
        reset_speech_seconds()

    except Exception as e:
        print(f"  ✖ Whisper error: {e}")
    finally:
        if paused_by_trigger:
            resume()
            _log_event(session, "transcription_resumed", {
                "reason": f"{trigger_type}_whisper_pipeline_complete",
            })
        session._whisper_in_progress = False

        # If skip was requested during this whisper, fire a fresh challenge
        if session._skip_requested:
            session._skip_requested = False
            session.transcript_buffer.clear()
            session.previous_whispers.clear()
            session.last_sent_timestamp = None
            asyncio.create_task(_do_whisper(session, "challenge"))


# ── Timer trigger check ─────────────────────────────────────────────────────

async def _timer_loop(session: Session) -> None:
    """Periodically check if enough speech has accumulated to auto-trigger."""
    interval_sec = session.config.trigger_interval_min * 60

    while session.active:
        await asyncio.sleep(5)  # check every 5 seconds

        if not session.active:
            break

        speech = get_speech_seconds()
        if speech >= interval_sec:
            print(f"\n  ⏰ Auto-trigger ({speech:.0f}s speech accumulated)")
            await _do_whisper(session, "timer")


# ── Keyboard handler ─────────────────────────────────────────────────────────

async def _handle_key(key: str, session: Session) -> bool:
    """Process a keypress. Returns False if should quit."""

    if key == "s" and not session.active:
        # Start session
        session.active = True
        session.started_at = datetime.now().isoformat()
        print("\n  🟢 Session started. Listening...")

        try:
            await start_listening(
                config=session.config,
                transcript_buffer=session.transcript_buffer,
                on_speech_time=lambda secs: None,  # tracked internally in loop1
            )
        except Exception as e:
            session.active = False
            print(f"  ✖ Session failed to start: {e}")
            print("  ↺ Press [s] to retry after checking network/Deepgram access.")
            return True

        # Start timer loop
        asyncio.create_task(_timer_loop(session))

        # Auto-trigger initial challenge (empty buffer → prompt generates a challenge)
        asyncio.create_task(_do_whisper(session, "challenge"))
        return True

    elif key == "q":
        # Quit
        print("\n  🔴 Stopping session...")
        session.active = False
        return False

    elif key == " " and session.active:
        # Manual trigger
        print("\n  👆 Manual trigger")
        _log_event(session, "manual_trigger_pressed", {
            "buffer_entries": len(session.transcript_buffer),
        })
        asyncio.create_task(_do_whisper(session, "manual"))
        return True

    elif key == "n" and session.active:
        # Skip to next challenge — reset all context for a fresh start
        print("\n  ⏭ Skip requested")
        abort_playback()
        _log_event(session, "skip_to_next_challenge")
        if session._whisper_in_progress:
            # Let the running whisper finish, then its finally block fires challenge
            session._skip_requested = True
        else:
            # No whisper running — clear context and fire immediately
            session.transcript_buffer.clear()
            session.previous_whispers.clear()
            session.last_sent_timestamp = None
            asyncio.create_task(_do_whisper(session, "challenge"))
        return True

    elif key == "x":
        # Abort playback
        abort_playback()
        # Mark the last whisper as aborted
        if session.whisper_results:
            session.whisper_results[-1].aborted = True
        return True

    elif key == "p" and session.active:
        # Toggle pause
        if is_paused():
            resume()
            _log_event(session, "transcription_resumed", {"reason": "manual_pause_toggle"})
        else:
            pause()
            _log_event(session, "transcription_paused", {"reason": "manual_pause_toggle"})
        return True

    elif key in "12345" and session.whisper_results:
        # Rate the last whisper
        rating = int(key)
        session.whisper_results[-1].user_rating = rating
        print(f"  ⭐ Rated last whisper: {rating}/5")
        return True

    return True


# ── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Parse config and print startup info
    config = parse_config()
    print_config(config)

    session = Session(config)

    # Enter cbreak mode for single-key input
    _enter_cbreak()
    atexit.register(_restore_terminal)

    # Handle signals for clean shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        session.active = False

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    print("  Press [s] to start session, [q] to quit.\n")

    # Key input loop
    running = True
    while running:
        # Non-blocking read from stdin via asyncio
        try:
            key = await loop.run_in_executor(None, sys.stdin.read, 1)
        except (EOFError, OSError):
            break

        if not key:
            continue

        running = await _handle_key(key, session)

    await _teardown(session)


async def _teardown(session: Session) -> None:
    """Run ordered shutdown steps for a session."""
    # 1. Stop TTS
    abort_playback()

    # 2-3. Stop capture + Deepgram
    session.active = False
    await stop_listening()

    # 4. Write session log
    _write_session_log(session)

    # 5. Restore terminal (via atexit)
    _restore_terminal()

    print("\n  👋 Session ended. Goodbye.\n")


if __name__ == "__main__":
    asyncio.run(main())
