# AIASIS (PoC)

Mac-first Python CLI for validating in-ear AI coaching during live conversations.

## What It Does

- **Loop 1:** Microphone capture -> Silero VAD -> Deepgram streaming STT -> rolling transcript buffer
- **Loop 2:** Timer/manual trigger -> LLM coaching response -> TTS playback through output device (for example, AirPods)
- Session logs written as JSONL in `logs/`

This repository is a product-validation PoC, not a production system.

## Requirements

- macOS
- Python 3.11+
- `ffmpeg` installed (`brew install ffmpeg`)
- Deepgram API key
- LLM API access (OpenAI, Anthropic, or Azure OpenAI-compatible endpoint)

## Quick Start

```bash
# 1) Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Set required environment variables
export DEEPGRAM_API_KEY="..."
export LLM_PROVIDER="openai"     # openai | anthropic | azure
export LLM_API_KEY="..."
export LLM_MODEL="gpt-4o-mini"

# Optional (required for azure provider)
# export LLM_BASE_URL="https://<your-resource>.openai.azure.com"
# export LLM_API_VERSION="2025-04-01-preview"

# 4) Run
python src/main.py
```

## Audio Device Setup

List available devices:

```bash
source .venv/bin/activate
python -m sounddevice
```

Run with explicit input/output device indices:

```bash
source .venv/bin/activate
python src/main.py --input-device 2 --output-device 4
```

If AirPods mic quality is poor, use built-in Mac mic for input and AirPods for output.

## CLI Options

```bash
python src/main.py \
  --input-device 2 \
  --output-device 4 \
  --prompt prompts/v1.txt \
  --interval 10 \
  --max-words 20 \
  --llm-provider openai \
  --llm-model gpt-4o-mini
```

- `--prompt`: defaults to latest `prompts/vN.txt`
- `--interval`: auto-trigger minutes from accumulated speech
- `--max-words`: spoken coaching hard cap (must be `>= 5`)
- `--llm-provider` / `--llm-model`: override environment values

## Keyboard Controls

- `s` start session
- `q` stop and quit
- `space` manual whisper trigger
- `x` abort current TTS playback
- `p` pause/resume transcription
- `1-5` rate last whisper

## Logs

Session logs are created in `logs/` as:

- `session-YYYY-MM-DD-HHMMSS.jsonl`

Each file includes:

- event markers (manual trigger, pause/resume, playback start/end)
- whisper entries (trigger type, LLM response, duration, rating, aborted flag, prompt version)
- session summary (start/end, average rating, abort count, duration)

## Security Notes

- API keys are read from environment variables (`.env` is supported via `python-dotenv`)
- Never hardcode secrets in source files
- Never commit `.env` or real credentials
- Transcript and LLM outputs may contain sensitive conversation content; treat `logs/` as sensitive data

## Project Docs

- Product/validation plan: `docs/aiasis-poc.md`
- Internal project instructions: `CLAUDE.md`
