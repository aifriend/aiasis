"""Loop 2: LLM coaching call → TTS synthesis → audio playback."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from collections.abc import Callable
import re

import edge_tts
import numpy as np
import sounddevice as sd
from pydub import AudioSegment

from config import Config


# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class WhisperResult:
    timestamp: str = ""
    trigger_type: str = ""            # "manual" | "timer"
    transcript_chunk_length: int = 0
    transcript_sent_to_llm: str = ""
    llm_response: str = ""
    spoken_text: str = ""
    tts_duration_ms: int = 0
    user_rating: int | None = None
    aborted: bool = False
    prompt_version: str = ""


# ── Module state ─────────────────────────────────────────────────────────────

_playing = asyncio.Event()  # set when playback is active
_abort_requested = False


# ── LLM call (provider-agnostic) ─────────────────────────────────────────────

async def _call_llm(
    system_prompt: str,
    user_message: str,
    config: Config,
) -> str:
    """Call LLM. Dispatches to the right SDK based on config.llm_provider."""

    if config.llm_provider == "openai":
        return await _call_openai(system_prompt, user_message, config)
    elif config.llm_provider == "azure":
        return await _call_azure(system_prompt, user_message, config)
    elif config.llm_provider == "anthropic":
        return await _call_anthropic(system_prompt, user_message, config)
    else:
        raise ValueError(f"Unknown LLM provider: {config.llm_provider}")


async def _call_openai(
    system_prompt: str,
    user_message: str,
    config: Config,
) -> str:
    """Call OpenAI-compatible API (works with Azure, local endpoints too)."""
    from openai import AsyncOpenAI

    client_kwargs = {"api_key": config.llm_api_key}
    if config.llm_base_url:
        client_kwargs["base_url"] = config.llm_base_url

    client = AsyncOpenAI(**client_kwargs)

    response = await client.chat.completions.create(
        model=config.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    return response.choices[0].message.content.strip()


async def _call_azure(
    system_prompt: str,
    user_message: str,
    config: Config,
) -> str:
    """Call Azure OpenAI API (uses AsyncAzureOpenAI with endpoint + api_version)."""
    from openai import AsyncAzureOpenAI

    client = AsyncAzureOpenAI(
        api_key=config.llm_api_key,
        azure_endpoint=config.llm_base_url,
        api_version=config.llm_api_version,
    )

    response = await client.chat.completions.create(
        model=config.llm_model,  # = Azure deployment name
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    return response.choices[0].message.content.strip()


async def _call_anthropic(
    system_prompt: str,
    user_message: str,
    config: Config,
) -> str:
    """Call Anthropic API."""
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=config.llm_api_key)

    response = await client.messages.create(
        model=config.llm_model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    return response.content[0].text.strip()


# ── TTS ──────────────────────────────────────────────────────────────────────

async def _synthesize_tts(text: str, config: Config) -> tuple[np.ndarray, int]:
    """Synthesize text via edge-tts → numpy array + sample rate."""
    communicate = edge_tts.Communicate(
        text,
        config.tts_voice,
        rate=config.tts_rate,
        volume=config.tts_volume,
        pitch=config.tts_pitch,
    )

    mp3_bytes = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_bytes += chunk["data"]

    # Decode MP3 → PCM via pydub
    audio = AudioSegment.from_file(BytesIO(mp3_bytes), format="mp3")
    samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
    samples /= 2 ** (audio.sample_width * 8 - 1)  # normalize to [-1, 1]
    samples = samples.reshape((-1, audio.channels))

    return samples, audio.frame_rate


async def _fallback_tts(text: str) -> None:
    """Fallback: macOS `say` command (no device selection, blocking)."""
    proc = await asyncio.create_subprocess_exec(
        "say", "-r", "180", text,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()


def _compress_coaching_text(text: str, max_words: int) -> str:
    """Normalize coach text, keep the highest-leverage line, then cap words."""
    normalized_lines = [
        re.sub(r"^[\-\*\u2022\d\)\.\s]+", "", line.strip())
        for line in text.splitlines()
        if line.strip()
    ]
    normalized = " ".join(normalized_lines).strip()
    if not normalized:
        return ""

    # If the full text fits within max_words, return as-is (no sentence picking)
    if len(normalized.split()) <= max_words:
        return normalized

    # Only pick the best sentence when we need to compress
    sentence_candidates = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()
    ]
    if sentence_candidates:
        action_keywords = {
            "ask", "confirm", "address", "clarify", "commit", "assign",
            "summarize", "close", "decide", "state", "redirect", "answer",
        }
        insight_keywords = {
            "risk", "blocker", "deadline", "owner", "decision", "objection",
            "concern", "priority", "tradeoff", "scope",
        }

        def score(sentence: str) -> tuple[int, int]:
            lower = sentence.lower()
            action_score = sum(1 for k in action_keywords if k in lower)
            insight_score = sum(1 for k in insight_keywords if k in lower)
            # Prefer richer/actionable sentences; tie-breaker prefers shorter.
            return (action_score * 3 + insight_score * 2, -len(sentence.split()))

        normalized = max(sentence_candidates, key=score)

    words = normalized.split()
    if len(words) <= max_words:
        return normalized

    clipped = " ".join(words[:max_words]).rstrip(".,;:!?")
    return f"{clipped}..."


# ── Playback ─────────────────────────────────────────────────────────────────

async def _play_audio(
    samples: np.ndarray,
    sample_rate: int,
    config: Config,
) -> float:
    """Play numpy audio via sounddevice. Returns duration in ms. Abortable."""
    global _abort_requested

    _playing.set()
    _abort_requested = False

    duration_ms = len(samples) / sample_rate * 1000
    sd.play(samples, samplerate=sample_rate, device=config.output_device, blocking=False)

    start = time.monotonic()

    # Poll for completion or abort
    while sd.get_stream().active and not _abort_requested:
        await asyncio.sleep(0.1)

    if _abort_requested:
        sd.stop()
        elapsed = (time.monotonic() - start) * 1000
        print("  ⏹ Playback aborted")
        _playing.clear()
        return elapsed

    sd.wait()
    _playing.clear()
    return duration_ms


# ── Public interface ─────────────────────────────────────────────────────────

async def trigger_whisper(
    config: Config,
    transcript_buffer: list[dict],
    previous_whispers: list[str],
    trigger_type: str = "manual",
    on_playback_event: Callable[[str, dict], None] | None = None,
) -> WhisperResult:
    """Full Loop 2 pipeline: buffer → LLM → TTS → playback. Returns result."""

    result = WhisperResult(
        timestamp=datetime.now().isoformat(),
        trigger_type=trigger_type,
        prompt_version=Path(config.prompt_file).stem,
    )

    # 1. Build transcript text from buffer
    transcript_text = "\n".join(
        f"[{e['timestamp']}] {e['text']}" for e in transcript_buffer
    )
    result.transcript_chunk_length = len(transcript_text)
    if config.debug_logs:
        result.transcript_sent_to_llm = transcript_text

    # 2. Load system prompt
    try:
        system_prompt = Path(config.prompt_file).read_text(encoding="utf-8")
    except Exception as e:
        print(f"  ✖ Cannot read prompt file: {e}")
        return result

    # 3. Build user message
    user_message = json.dumps({
        "transcript": transcript_text,
        "previous_whispers": previous_whispers,
    })

    # 4. Call LLM
    print("  🧠 Calling LLM...")
    try:
        llm_response = await _call_llm(system_prompt, user_message, config)
    except Exception as e:
        print(f"  ✖ LLM error: {e}")
        result.llm_response = f"[ERROR] {e}"
        return result

    result.llm_response = llm_response
    compressed = _compress_coaching_text(llm_response, config.coaching_max_words)
    if compressed and compressed != llm_response:
        print(
            f"  ✂ Compressed coaching from {len(llm_response.split())} to "
            f"{len(compressed.split())} words"
        )
    result.llm_response = compressed or llm_response
    if config.debug_logs:
        result.spoken_text = result.llm_response
    print(f"  💬 {result.llm_response}")

    # 5. Skip TTS if nothing notable
    if result.llm_response.strip() == config.no_observation_text:
        print("  — No notable observations, skipping TTS")
        return result

    # 6. Synthesize & play TTS
    print("  🔊 Synthesizing speech...")
    try:
        samples, sample_rate = await _synthesize_tts(result.llm_response, config)
        if on_playback_event:
            on_playback_event("coaching_voice_started", {
                "trigger_type": trigger_type,
                "char_count": len(result.llm_response),
            })
        print("  🔈 COACHING_VOICE_STARTED")
        duration = await _play_audio(samples, sample_rate, config)
        result.tts_duration_ms = int(duration)
        result.aborted = _abort_requested
        if on_playback_event:
            on_playback_event("coaching_voice_finished", {
                "trigger_type": trigger_type,
                "duration_ms": int(duration),
                "aborted": result.aborted,
            })
        print(f"  🔇 COACHING_VOICE_FINISHED (aborted={result.aborted})")
    except Exception as e:
        print(f"  ⚠ TTS error, trying fallback: {e}")
        try:
            if on_playback_event:
                on_playback_event("coaching_voice_started", {
                    "trigger_type": trigger_type,
                    "char_count": len(result.llm_response),
                    "engine": "fallback_say",
                })
            print("  🔈 COACHING_VOICE_STARTED (fallback_say)")
            await _fallback_tts(result.llm_response)
            result.tts_duration_ms = 0  # unknown duration with `say`
            if on_playback_event:
                on_playback_event("coaching_voice_finished", {
                    "trigger_type": trigger_type,
                    "duration_ms": 0,
                    "aborted": False,
                    "engine": "fallback_say",
                })
            print("  🔇 COACHING_VOICE_FINISHED (fallback_say)")
        except Exception as e2:
            print(f"  ✖ Fallback TTS also failed: {e2}")

    return result


def abort_playback() -> None:
    """Abort current TTS playback immediately."""
    global _abort_requested
    if _playing.is_set():
        _abort_requested = True
        sd.stop()


def is_playing() -> bool:
    """Check if Loop 2 is currently playing audio."""
    return _playing.is_set()
