"""Configuration: CLI args, env vars, JSON config, constants, startup checks."""

import argparse
import glob
import json
import os
import re
import shutil
import ssl
import sys
from dataclasses import dataclass, asdict
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


# ── Paths ───────────────────────────────────────────────────────────────────

CONFIG_DIR = Path("config")
CONFIG_JSON_PATH = CONFIG_DIR / "active.json"
PRESETS_DIR = CONFIG_DIR / "presets"


# ── Constants (used as dataclass defaults — backward compatible) ────────────

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

    # Audio / VAD
    sample_rate: int = SAMPLE_RATE
    vad_chunk_size: int = VAD_CHUNK_SIZE
    vad_threshold: float = VAD_THRESHOLD
    audio_queue_max: int = 200

    # LLM — provider-agnostic
    llm_provider: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_base_url: str | None = None
    llm_api_version: str | None = None  # required for azure provider
    temperature: float = 0.7
    max_tokens: int = 300

    # Deepgram STT
    deepgram_api_key: str = ""
    deepgram_model: str = "flux-general-en"
    eot_threshold: float = 0.7
    connection_retries: int = 3
    connection_timeout: int = 15

    # Session
    prompt_file: str = ""
    trigger_interval_min: float = DEFAULT_INTERVAL_MIN
    coaching_max_words: int = DEFAULT_COACHING_MAX_WORDS
    buffer_max_age_min: int = BUFFER_MAX_AGE_MIN
    timer_check_interval_sec: int = 5
    tail_context_entries: int = 3
    no_observation_text: str = NO_OBSERVATION
    debug_logs: bool = False

    # TTS
    tts_voice: str = TTS_VOICE
    tts_rate: str = TTS_RATE
    tts_volume: str = TTS_VOLUME
    tts_pitch: str = TTS_PITCH


# ── JSON config I/O ─────────────────────────────────────────────────────────

# Fields that are secrets and must NEVER be written to JSON
_SECRET_FIELDS = {"llm_api_key", "deepgram_api_key"}


def _load_json_config(path: Path = CONFIG_JSON_PATH) -> dict:
    """Read config/active.json if it exists. Returns flat dict, {} if missing."""
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Flatten nested structure into Config field names
        flat = {}
        for section_key, section_val in data.items():
            if section_key == "_meta":
                continue  # skip metadata
            if isinstance(section_val, dict):
                flat.update(section_val)
            else:
                flat[section_key] = section_val
        return flat
    except (json.JSONDecodeError, OSError) as e:
        print(f"  ⚠ Could not read {path}: {e}")
        return {}


def config_to_json(config: Config) -> dict:
    """Serialize non-secret Config fields to the JSON schema for dashboard."""
    return {
        "_meta": {
            "preset_name": "",
            "description": "",
        },
        "audio": {
            "input_device": config.input_device,
            "output_device": config.output_device,
            "sample_rate": config.sample_rate,
            "vad_chunk_size": config.vad_chunk_size,
            "vad_threshold": config.vad_threshold,
            "audio_queue_max": config.audio_queue_max,
        },
        "llm": {
            "provider": config.llm_provider,
            "model": config.llm_model,
            "base_url": config.llm_base_url,
            "api_version": config.llm_api_version,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        },
        "stt": {
            "deepgram_model": config.deepgram_model,
            "eot_threshold": config.eot_threshold,
            "connection_retries": config.connection_retries,
            "connection_timeout": config.connection_timeout,
        },
        "tts": {
            "voice": config.tts_voice,
            "rate": config.tts_rate,
            "volume": config.tts_volume,
            "pitch": config.tts_pitch,
        },
        "session": {
            "trigger_interval_min": config.trigger_interval_min,
            "coaching_max_words": config.coaching_max_words,
            "buffer_max_age_min": config.buffer_max_age_min,
            "timer_check_interval_sec": config.timer_check_interval_sec,
            "tail_context_entries": config.tail_context_entries,
            "no_observation_text": config.no_observation_text,
            "debug_logs": config.debug_logs,
        },
        "prompt": {
            "file": config.prompt_file,
        },
    }


def save_json_config(data: dict, path: Path = CONFIG_JSON_PATH) -> None:
    """Write config JSON to disk (creates directories as needed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── JSON field mapping ──────────────────────────────────────────────────────

# Maps JSON flat keys to Config field names (when they differ)
_JSON_TO_CONFIG = {
    "provider": "llm_provider",
    "model": "llm_model",
    "base_url": "llm_base_url",
    "api_version": "llm_api_version",
    "voice": "tts_voice",
    "rate": "tts_rate",
    "volume": "tts_volume",
    "pitch": "tts_pitch",
    "file": "prompt_file",
}


def _json_val(json_cfg: dict, config_field: str, default):
    """Get a value from the flattened JSON config, handling key mapping."""
    # Try direct field name first
    if config_field in json_cfg:
        return json_cfg[config_field]
    # Try reverse mapping (some JSON keys are shorter than Config field names)
    for json_key, mapped_field in _JSON_TO_CONFIG.items():
        if mapped_field == config_field and json_key in json_cfg:
            return json_cfg[json_key]
    return default


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


# ── Build config from CLI + JSON + env ───────────────────────────────────────

def parse_config() -> Config:
    """Parse CLI args + JSON config + env vars, validate, return Config.

    Priority: CLI args > config/active.json > env vars > hardcoded defaults.
    """

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
    parser.add_argument("--interval", type=float, default=None,
                        help=f"Auto-trigger interval in minutes (default: {DEFAULT_INTERVAL_MIN})")
    parser.add_argument("--max-words", type=int, default=None,
                        help=f"Hard cap for spoken coaching length in words (default: {DEFAULT_COACHING_MAX_WORDS})")
    parser.add_argument("--debug-logs", action="store_true", default=None,
                        help="Enable verbose debug logging (full transcript payloads and event timeline)")
    parser.add_argument("--llm-provider", type=str, default=None,
                        help="LLM provider: openai, anthropic, azure (overrides LLM_PROVIDER env)")
    parser.add_argument("--llm-model", type=str, default=None,
                        help="LLM model name (overrides LLM_MODEL env)")

    args = parser.parse_args()

    # ── System checks ────────────────────────────────────────────────────
    _check_ffmpeg()
    _check_audio_devices()

    # ── Load JSON config layer ───────────────────────────────────────────
    json_cfg = _load_json_config()

    # ── Deepgram key (always required) ───────────────────────────────────
    deepgram_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not deepgram_key:
        _die("DEEPGRAM_API_KEY env var is required. Get one at console.deepgram.com")

    # ── LLM config: CLI > JSON > env > default ──────────────────────────
    llm_provider = (args.llm_provider
                    or _json_val(json_cfg, "llm_provider", None)
                    or os.environ.get("LLM_PROVIDER", ""))
    llm_api_key = os.environ.get("LLM_API_KEY", "")
    llm_model = (args.llm_model
                 or _json_val(json_cfg, "llm_model", None)
                 or os.environ.get("LLM_MODEL", ""))
    llm_base_url = _json_val(json_cfg, "llm_base_url", None) or os.environ.get("LLM_BASE_URL")
    llm_api_version = _json_val(json_cfg, "llm_api_version", None) or os.environ.get("LLM_API_VERSION")

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

    # ── Prompt file: CLI > JSON > auto-detect ────────────────────────────
    prompt_file = (args.prompt
                   or _json_val(json_cfg, "prompt_file", None)
                   or _find_latest_prompt())
    if not Path(prompt_file).is_file():
        _die(f"Prompt file not found: {prompt_file}")

    # ── Numeric/session params: CLI > JSON > default ─────────────────────
    def _resolve(cli_val, field_name, default):
        if cli_val is not None:
            return cli_val
        return _json_val(json_cfg, field_name, default)

    interval = _resolve(args.interval, "trigger_interval_min", DEFAULT_INTERVAL_MIN)
    max_words = _resolve(args.max_words, "coaching_max_words", DEFAULT_COACHING_MAX_WORDS)
    debug_logs = _resolve(args.debug_logs, "debug_logs", False)

    if max_words < 5:
        _die("--max-words must be >= 5")

    # ── Build Config ─────────────────────────────────────────────────────
    config = Config(
        input_device=_resolve(args.input_device, "input_device", None),
        output_device=_resolve(args.output_device, "output_device", None),
        sample_rate=_json_val(json_cfg, "sample_rate", SAMPLE_RATE),
        vad_chunk_size=_json_val(json_cfg, "vad_chunk_size", VAD_CHUNK_SIZE),
        vad_threshold=_json_val(json_cfg, "vad_threshold", VAD_THRESHOLD),
        audio_queue_max=_json_val(json_cfg, "audio_queue_max", 200),
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
        llm_base_url=llm_base_url,
        llm_api_version=llm_api_version,
        temperature=_json_val(json_cfg, "temperature", 0.7),
        max_tokens=_json_val(json_cfg, "max_tokens", 300),
        deepgram_api_key=deepgram_key,
        deepgram_model=_json_val(json_cfg, "deepgram_model", "flux-general-en"),
        eot_threshold=_json_val(json_cfg, "eot_threshold", 0.7),
        connection_retries=_json_val(json_cfg, "connection_retries", 3),
        connection_timeout=_json_val(json_cfg, "connection_timeout", 15),
        prompt_file=prompt_file,
        trigger_interval_min=interval,
        coaching_max_words=max_words,
        buffer_max_age_min=_json_val(json_cfg, "buffer_max_age_min", BUFFER_MAX_AGE_MIN),
        timer_check_interval_sec=_json_val(json_cfg, "timer_check_interval_sec", 5),
        tail_context_entries=_json_val(json_cfg, "tail_context_entries", 3),
        no_observation_text=_json_val(json_cfg, "no_observation_text", NO_OBSERVATION),
        debug_logs=debug_logs,
        tts_voice=_json_val(json_cfg, "tts_voice", TTS_VOICE),
        tts_rate=_json_val(json_cfg, "tts_rate", TTS_RATE),
        tts_volume=_json_val(json_cfg, "tts_volume", TTS_VOLUME),
        tts_pitch=_json_val(json_cfg, "tts_pitch", TTS_PITCH),
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
    print(f"  Temperature:  {config.temperature}")
    print(f"  Max tokens:   {config.max_tokens}")
    print(f"  Interval:     {config.trigger_interval_min} min")
    print(f"  Max words:    {config.coaching_max_words}")
    print(f"  Debug logs:   {config.debug_logs}")
    print(f"  TTS voice:    {config.tts_voice}")
    print(f"  VAD threshold:{config.vad_threshold}")
    print(f"  Input device:  {config.input_device or 'system default'}")
    print(f"  Output device: {config.output_device or 'system default'}")

    if CONFIG_JSON_PATH.is_file():
        print(f"  Config file:  {CONFIG_JSON_PATH}")

    print("\n── Audio Devices ──────────────────────────")
    print(sd.query_devices())

    print("\n── Keyboard Controls ─────────────────────")
    print("  [s] Start session    [q] Quit")
    print("  [space] Send my speech for feedback")
    print("  [n] Skip to next challenge")
    print("  [x] Abort playback   [p] Pause/resume")
    print("  [1-5] Rate last whisper")
    print("──────────────────────────────────────────\n")
