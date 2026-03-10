# AIASIS - Project Instructions

## What This Is

In-ear AI assistant that listens via AirPods, reasons about conversations, and whispers coaching insights back. See `docs/aiasis-blueprint.md` for full architecture and `docs/aiasis-poc.md` for the validation plan.

## Current Phase: PoC (Mac-First)

We are building a **Python CLI script on Mac** to validate the product hypothesis before any iOS work. No backend, no Swift, no infrastructure.

### Two-Loop Architecture

- **Loop 1**: Mic capture -> Silero VAD -> Deepgram Flux v2 STT -> rolling transcript buffer (in-memory)
- **Loop 2**: Timer/keypress trigger -> send buffer to LLM -> get coaching text -> edge-tts -> play through AirPods

### Key Files

```
src/
├── main.py          # Session orchestration, keyboard controls, logging
├── loop1.py         # Audio capture + VAD + Deepgram streaming STT
├── loop2.py         # LLM call + TTS playback + abort mechanism
└── config.py        # API keys (from env vars), device settings, trigger interval
prompts/
└── v1.txt           # Meeting coaching system prompt (versioned: v1, v2, etc.)
logs/                # Session logs with whisper ratings (gitignored)
```

## Coding Conventions

- **Python 3.11+**
- **No frameworks**: Raw `asyncio` for concurrency. No FastAPI, no Flask, no Pipecat.
- **No classes unless needed**: Prefer functions and modules. This is a PoC, not a product.
- **Type hints**: Yes, but don't over-annotate. Function signatures only.
- **Error handling**: Log and continue. Never crash the session silently -- print errors to terminal.
- **Dependencies**: Only what's in `requirements.txt`. Ask before adding new ones.

## API Keys

All keys come from environment variables. Never hardcode, never commit.

```bash
# Deepgram (always required — STT)
export DEEPGRAM_API_KEY="..."

# LLM (provider-agnostic)
export LLM_PROVIDER="openai"         # or "anthropic"
export LLM_API_KEY="..."
export LLM_MODEL="gpt-4o-mini"       # or any model name
# export LLM_BASE_URL="..."          # optional, for Azure/custom endpoints
```

CLI overrides: `--llm-provider`, `--llm-model`.

Check `config.py` for the full list. If a key is missing, print a clear error and exit.

**System dependency**: `ffmpeg` must be installed (`brew install ffmpeg`).

## Audio Device

AirPods on Mac may not auto-select as input/output. The script must:
1. List available devices on startup (`sounddevice.query_devices()`)
2. Allow explicit device selection via env var or CLI arg (`--input-device`, `--output-device`)
3. Default to system defaults if not specified

If AirPods mic quality is poor (SCO codec), use Mac built-in mic for input and AirPods for output only.

## System Prompt

The meeting coaching prompt lives in `prompts/v1.txt` (and v2, v3, etc.). The script loads the prompt file specified by `--prompt` arg (default: latest version).

**Prompt rules** (from blueprint section 5):
- Output must be speakable in <15 seconds
- 1-3 bullet insights, prioritized by actionability
- No preamble, no pleasantries
- Never repeat information from a previous whisper
- Never interrupt with trivial observations

## Session Logging

Every session produces a log file in `logs/` with:
- Session start/end timestamps
- Prompt version used
- Each whisper: timestamp, trigger type (timer/manual), transcript chunk sent, LLM response, TTS duration, user rating (1-5)
- Abort events (x key)

Format: JSON lines (`logs/session-YYYY-MM-DD-HHMMSS.jsonl`)

## Keyboard Controls

| Key | Action |
|-----|--------|
| `s` | Start session |
| `q` | Stop session and quit |
| `space` | Manual trigger (send buffer to LLM now) |
| `x` | Abort current TTS playback |
| `1-5` | Rate the last whisper (after it finishes playing) |
| `p` | Pause/resume listening |

## Testing

- **No unit test framework for PoC**. Testing is manual with real conversations.
- Minimum valid test session: 20 minutes of conversation.
- Minimum sessions before evaluation: 3 across 2+ contexts.
- See `docs/aiasis-poc.md` sections "Pre-Code Validation" and "PoC Evaluation" for full test protocol.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# List audio devices
python -m sounddevice

# Run with defaults
python src/main.py

# Run with specific devices and prompt
python src/main.py --input-device 2 --output-device 4 --prompt prompts/v2.txt

# Run with custom trigger interval (minutes)
python src/main.py --interval 5
```

## Do NOT

- Add a backend or web server
- Use Pipecat, LiveKit, or any voice agent framework
- Add a database or persistent storage
- Write Swift or any iOS code
- Over-engineer: this is a 7-day PoC, not a product
- Create new files outside `src/`, `prompts/`, `logs/` without asking
