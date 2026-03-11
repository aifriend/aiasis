"""Configuration: CLI args, env vars, constants, startup checks."""

import argparse
import glob
import os
import re
import shutil
import ssl
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── Load .env file (must run before any os.environ reads) ─────────────────────
from dotenv import load_dotenv

load_dotenv()  # loads .env from cwd (project root), won't override existing vars

# ── Fix macOS SSL certs (Python.org builds don't include them) ───────────────
if not os.environ.get("SSL_CERT_FILE"):
    try:
        import certifi
        os.environ["SSL_CERT_FILE"] = certifi.where()
    except ImportError:
        pass  # certifi not installed, hope system certs work


# ── Constants ────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
VAD_CHUNK_SIZE = 512          # samples per VAD frame (32ms at 16kHz)
VAD_THRESHOLD = 0.5           # speech probability threshold
BUFFER_MAX_AGE_MIN = 15       # rolling transcript window (minutes)
DEFAULT_INTERVAL_MIN = 10     # trigger interval (minutes)
DEFAULT_COACHING_MAX_WORDS = 80

TTS_VOICE = "en-US-AriaNeural"
TTS_RATE = "-20%"
TTS_VOLUME = "-15%"
TTS_PITCH = "+0Hz"

NO_OBSERVATION = "No notable observations."


# ── Config dataclass ─────────────────────────────────────────────────────────

@dataclass
class Config:
    # Audio devices (None = system default)
    input_device: int | None = None
    output_device: int | None = None

    # LLM — provider-agnostic
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str | None = None
    llm_api_version: str | None = None  # required for azure provider

    # Deepgram
    deepgram_api_key: str = ""

    # Session
    prompt_file: str = ""
    trigger_interval_min: float = DEFAULT_INTERVAL_MIN
    coaching_max_words: int = DEFAULT_COACHING_MAX_WORDS
    debug_logs: bool = False

    # TTS
    tts_voice: str = TTS_VOICE
    tts_rate: str = TTS_RATE
    tts_volume: str = TTS_VOLUME
    tts_pitch: str = TTS_PITCH


# ── Helpers ──────────────────────────────────────────────────────────────────

def _find_latest_prompt() -> str:
    """Glob prompts/v*.txt and return the highest-versioned file path."""
    pattern = str(Path("prompts") / "v*.txt")
    files = glob.glob(pattern)
    if not files:
        _die("No prompt files found in prompts/v*.txt")

    def version_key(path: str) -> int:
        match = re.search(r"v(\d+)\.txt$", path)
        return int(match.group(1)) if match else 0

    return sorted(files, key=version_key)[-1]


def _die(msg: str) -> None:
    print(f"\n✖ {msg}", file=sys.stderr)
    sys.exit(1)


# ── Startup checks ──────────────────────────────────────────────────────────

def _check_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        _die("ffmpeg not found. Install with: brew install ffmpeg")


def _check_audio_devices() -> None:
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        # Check at least one input exists
        has_input = any(d["max_input_channels"] > 0 for d in devices)
        if not has_input:
            _die("No audio input device found. Connect a microphone.")
    except Exception as e:
        _die(f"Cannot query audio devices: {e}")


# ── Build config from CLI + env ─────────────────────────────────────────────

def parse_config() -> Config:
    """Parse CLI args + env vars, validate, return Config."""

    parser = argparse.ArgumentParser(
        description="AIASIS — in-ear AI coaching assistant (PoC)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input-device", type=int, default=None,
                        help="Audio input device index (default: system default)")
    parser.add_argument("--output-device", type=int, default=None,
                        help="Audio output device index (default: system default)")
    parser.add_argument("--prompt", type=str, default=None,
                        help="Path to system prompt file (default: latest prompts/vN.txt)")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_MIN,
                        help=f"Auto-trigger interval in minutes (default: {DEFAULT_INTERVAL_MIN})")
    parser.add_argument("--max-words", type=int, default=DEFAULT_COACHING_MAX_WORDS,
                        help=f"Hard cap for spoken coaching length in words (default: {DEFAULT_COACHING_MAX_WORDS})")
    parser.add_argument("--debug-logs", action="store_true",
                        help="Enable verbose debug logging (full transcript payloads and event timeline)")
    parser.add_argument("--llm-provider", type=str, default=None,
                        help="LLM provider: openai, anthropic, azure (overrides LLM_PROVIDER env)")
    parser.add_argument("--llm-model", type=str, default=None,
                        help="LLM model name (overrides LLM_MODEL env)")

    args = parser.parse_args()

    # ── System checks ────────────────────────────────────────────────────
    _check_ffmpeg()
    _check_audio_devices()

    # ── Deepgram key (always required) ───────────────────────────────────
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not deepgram_key:
        _die("DEEPGRAM_API_KEY env var is required. Get one at console.deepgram.com")

    # ── LLM config (generic, provider-agnostic) ─────────────────────────
    llm_provider = args.llm_provider or os.environ.get("LLM_PROVIDER", "")
    llm_api_key = os.environ.get("LLM_API_KEY", "")
    llm_model = args.llm_model or os.environ.get("LLM_MODEL", "")
    llm_base_url = os.environ.get("LLM_BASE_URL")
    llm_api_version = os.environ.get("LLM_API_VERSION")

    if not llm_provider:
        _die("LLM_PROVIDER env var (or --llm-provider) is required. Values: openai, anthropic, azure")
    if not llm_api_key:
        _die("LLM_API_KEY env var is required.")
    if not llm_model:
        _die("LLM_MODEL env var (or --llm-model) is required. Example: gpt-4o-mini")

    if llm_provider not in ("openai", "anthropic", "azure"):
        _die(f"Unknown LLM_PROVIDER '{llm_provider}'. Supported: openai, anthropic, azure")

    if llm_provider == "azure":
        if not llm_base_url:
            _die("LLM_BASE_URL is required for azure provider (Azure endpoint URL)")
        if not llm_api_version:
            _die("LLM_API_VERSION is required for azure provider (e.g. 2025-04-01-preview)")

    # ── Prompt file ──────────────────────────────────────────────────────
    prompt_file = args.prompt or _find_latest_prompt()
    if not Path(prompt_file).is_file():
        _die(f"Prompt file not found: {prompt_file}")

    # ── Build Config ─────────────────────────────────────────────────────
    if args.max_words < 5:
        _die("--max-words must be >= 5")

    config = Config(
        input_device=args.input_device,
        output_device=args.output_device,
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_version=llm_api_version,
        deepgram_api_key=deepgram_key,
        prompt_file=prompt_file,
        trigger_interval_min=args.interval,
        coaching_max_words=args.max_words,
        debug_logs=args.debug_logs,
    )

    return config


def print_config(config: Config) -> None:
    """Print loaded config summary to terminal."""
    import sounddevice as sd

    print("\n╔══════════════════════════════════════════╗")
    print("║         AIASIS PoC — Mac-First           ║")
    print("╚══════════════════════════════════════════╝\n")

    print(f"  Prompt:       {config.prompt_file}")
    print(f"  LLM:          {config.llm_provider} / {config.llm_model}")
    if config.llm_base_url:
        print(f"  LLM URL:      {config.llm_base_url}")
    print(f"  Interval:     {config.trigger_interval_min} min")
    print(f"  Max words:    {config.coaching_max_words}")
    print(f"  Debug logs:   {config.debug_logs}")
    print(f"  TTS voice:    {config.tts_voice}")
    print(f"  Input device:  {config.input_device or 'system default'}")
    print(f"  Output device: {config.output_device or 'system default'}")

    print("\n── Audio Devices ──────────────────────────")
    print(sd.query_devices())

    print("\n── Keyboard Controls ─────────────────────")
    print("  [s] Start session    [q] Quit")
    print("  [space] Send my speech for feedback")
    print("  [n] Skip to next challenge")
    print("  [x] Abort playback   [p] Pause/resume")
    print("  [1-5] Rate last whisper")
    print("──────────────────────────────────────────\n")
