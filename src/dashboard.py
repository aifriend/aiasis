"""AIASIS Dashboard — Gradio frontend for configuring the coaching engine."""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import gradio as gr
from dotenv import load_dotenv

load_dotenv()  # Load .env so dashboard sees same env vars as CLI

# Add src/ to path so we can import config helpers
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    Config,
    CONFIG_DIR,
    CONFIG_JSON_PATH,
    PRESETS_DIR,
    config_to_json,
    save_json_config,
    _load_json_config,
)

# ── Paths ────────────────────────────────────────────────────────────────────

PROMPTS_DIR = Path("prompts")
LOGS_DIR = Path("logs")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _list_audio_devices() -> list[str]:
    """Return human-readable list of audio devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        return [f"{i}: {d['name']}" for i, d in enumerate(devices)]
    except Exception:
        return ["(cannot query audio devices)"]


def _list_input_devices() -> list[str]:
    """Return input-capable audio devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        choices = ["System default"]
        for i, d in enumerate(devices):
            if d["max_input_channels"] > 0:
                choices.append(f"{i}: {d['name']}")
        return choices
    except Exception:
        return ["System default"]


def _list_output_devices() -> list[str]:
    """Return output-capable audio devices."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        choices = ["System default"]
        for i, d in enumerate(devices):
            if d["max_output_channels"] > 0:
                choices.append(f"{i}: {d['name']}")
        return choices
    except Exception:
        return ["System default"]


def _parse_device_choice(choice: str) -> int | None:
    """Extract device index from dropdown choice string."""
    if not choice or choice == "System default":
        return None
    try:
        return int(choice.split(":")[0])
    except (ValueError, IndexError):
        return None


def _device_to_choice(device_id: int | None, device_list: list[str]) -> str:
    """Convert device index to dropdown choice string."""
    if device_id is None:
        return "System default"
    prefix = f"{device_id}:"
    for choice in device_list:
        if choice.startswith(prefix):
            return choice
    return "System default"


def _list_tts_voices() -> list[str]:
    """Fetch available edge-tts voices (cached)."""
    try:
        import edge_tts
        voices = asyncio.run(edge_tts.list_voices())
        return [v["ShortName"] for v in voices]
    except Exception:
        return ["en-US-AriaNeural", "en-US-GuyNeural", "en-GB-SoniaNeural"]


def _list_prompt_files() -> list[str]:
    """List prompt files in prompts/ directory."""
    if not PROMPTS_DIR.is_dir():
        return []
    return sorted(str(p) for p in PROMPTS_DIR.glob("*.txt"))


def _list_preset_files() -> list[str]:
    """List preset JSON files."""
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


def _list_log_files() -> list[str]:
    """List session log files (newest first)."""
    if not LOGS_DIR.is_dir():
        return []
    return sorted(
        (str(p) for p in LOGS_DIR.glob("*.jsonl")),
        reverse=True,
    )


def _load_active_config() -> dict:
    """Load active config or return defaults from env vars."""
    if CONFIG_JSON_PATH.is_file():
        try:
            with open(CONFIG_JSON_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    # No active.json yet — build defaults from env vars (same source as CLI)
    defaults = Config(
        llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
        llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=os.environ.get("LLM_BASE_URL"),
        llm_api_version=os.environ.get("LLM_API_VERSION"),
    )
    return config_to_json(defaults)


def _has_api_key(env_var: str) -> str:
    """Return masked status of an API key."""
    val = os.environ.get(env_var, "")
    if val:
        return f"✓ Set ({val[:4]}...{val[-4:]})"
    return "✗ Not set"


# ── Tab builders ─────────────────────────────────────────────────────────────

def build_audio_tab():
    """Audio settings tab."""
    input_devices = _list_input_devices()
    output_devices = _list_output_devices()

    gr.Markdown("### Audio Devices & VAD")

    input_dd = gr.Dropdown(
        choices=input_devices,
        value="System default",
        label="Input Device (microphone)",
    )
    output_dd = gr.Dropdown(
        choices=output_devices,
        value="System default",
        label="Output Device (speaker/AirPods)",
    )
    vad_threshold = gr.Slider(
        minimum=0.1, maximum=0.95, step=0.05, value=0.5,
        label="VAD Threshold",
        info="Speech probability threshold (higher = less sensitive)",
    )
    queue_max = gr.Number(
        value=200, label="Audio Queue Max",
        info="Max queued audio frames before dropping",
        precision=0,
    )

    return input_dd, output_dd, vad_threshold, queue_max


def build_llm_tab():
    """LLM settings tab."""
    gr.Markdown("### LLM Configuration")

    provider = gr.Radio(
        choices=["openai", "anthropic", "azure"],
        value="openai",
        label="Provider",
    )
    model = gr.Textbox(value="gpt-4o-mini", label="Model Name")
    temperature = gr.Slider(
        minimum=0.0, maximum=2.0, step=0.05, value=0.7,
        label="Temperature",
    )
    max_tokens = gr.Number(
        value=300, label="Max Tokens", precision=0,
    )
    base_url = gr.Textbox(
        value="", label="Base URL (optional)",
        info="For Azure endpoint or custom OpenAI-compatible API",
    )
    api_version = gr.Textbox(
        value="", label="API Version (Azure only)",
        info="e.g. 2025-01-01-preview",
    )

    gr.Markdown("#### API Key Status")
    gr.Textbox(
        value=_has_api_key("LLM_API_KEY"),
        label="LLM_API_KEY",
        interactive=False,
    )

    return provider, model, temperature, max_tokens, base_url, api_version


def build_stt_tab():
    """STT (Deepgram) settings tab."""
    gr.Markdown("### Speech-to-Text (Deepgram)")

    dg_model = gr.Textbox(
        value="flux-general-en",
        label="Deepgram Model",
    )
    eot_threshold = gr.Slider(
        minimum=0.1, maximum=1.0, step=0.05, value=0.7,
        label="End-of-Turn Threshold",
    )
    retries = gr.Number(
        value=3, label="Connection Retries", precision=0,
    )
    timeout = gr.Number(
        value=15, label="Connection Timeout (seconds)", precision=0,
    )

    gr.Markdown("#### API Key Status")
    gr.Textbox(
        value=_has_api_key("DEEPGRAM_API_KEY"),
        label="DEEPGRAM_API_KEY",
        interactive=False,
    )

    return dg_model, eot_threshold, retries, timeout


def build_tts_tab():
    """TTS settings tab."""
    gr.Markdown("### Text-to-Speech (edge-tts)")

    voices = _list_tts_voices()
    voice = gr.Dropdown(
        choices=voices,
        value="en-US-AriaNeural",
        label="Voice",
        allow_custom_value=True,
    )
    rate = gr.Textbox(value="-20%", label="Rate", info="e.g. -20%, +10%")
    volume = gr.Textbox(value="-15%", label="Volume", info="e.g. -15%, +0%")
    pitch = gr.Textbox(value="+0Hz", label="Pitch", info="e.g. +0Hz, -5Hz")

    preview_text = gr.Textbox(
        value="This is a preview of the coaching voice.",
        label="Preview Text",
    )
    preview_btn = gr.Button("🔊 Preview Voice", variant="secondary")
    preview_audio = gr.Audio(label="Preview", type="filepath", visible=True)

    def do_preview(voice_name, rate_val, vol_val, pitch_val, text):
        try:
            import edge_tts
            from io import BytesIO
            from pydub import AudioSegment
            import tempfile

            async def _synth():
                comm = edge_tts.Communicate(
                    text, voice_name, rate=rate_val, volume=vol_val, pitch=pitch_val,
                )
                mp3 = b""
                async for chunk in comm.stream():
                    if chunk["type"] == "audio":
                        mp3 += chunk["data"]
                return mp3

            mp3_bytes = asyncio.run(_synth())
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(mp3_bytes)
            tmp.close()
            return tmp.name
        except Exception as e:
            gr.Warning(f"TTS preview failed: {e}")
            return None

    preview_btn.click(
        fn=do_preview,
        inputs=[voice, rate, volume, pitch, preview_text],
        outputs=preview_audio,
    )

    return voice, rate, volume, pitch


def build_session_tab():
    """Session behavior settings tab."""
    gr.Markdown("### Session Behavior")

    trigger_interval = gr.Number(
        value=10, label="Trigger Interval (minutes)",
        info="Auto-trigger whisper after this much speech time",
    )
    max_words = gr.Number(
        value=80, label="Coaching Max Words",
        info="Hard cap for spoken coaching length",
        precision=0,
    )
    buffer_age = gr.Number(
        value=15, label="Buffer Max Age (minutes)",
        info="Rolling transcript window duration",
        precision=0,
    )
    timer_interval = gr.Number(
        value=5, label="Timer Check Interval (seconds)",
        info="How often to check if auto-trigger threshold is reached",
        precision=0,
    )
    tail_entries = gr.Number(
        value=3, label="Tail Context Entries",
        info="Number of prior entries to include as context in each whisper",
        precision=0,
    )
    no_obs_text = gr.Textbox(
        value="No notable observations.",
        label="No Observation Text",
        info="LLM returns this when nothing to say (skips TTS)",
    )
    debug_toggle = gr.Checkbox(
        value=False, label="Debug Logs",
        info="Log full transcripts and event timeline to session files",
    )

    return (trigger_interval, max_words, buffer_age, timer_interval,
            tail_entries, no_obs_text, debug_toggle)


def build_prompt_tab():
    """Prompt editor tab."""
    gr.Markdown("### Prompt Editor")

    prompt_files = _list_prompt_files()
    prompt_selector = gr.Dropdown(
        choices=prompt_files,
        value=prompt_files[-1] if prompt_files else None,
        label="Prompt File",
        allow_custom_value=False,
    )
    prompt_editor = gr.Textbox(
        lines=20, label="Prompt Content", interactive=True,
    )
    with gr.Row():
        save_btn = gr.Button("💾 Save", variant="primary")
        save_as_btn = gr.Button("📝 Save As New Version", variant="secondary")
    save_status = gr.Textbox(label="Status", interactive=False, visible=True)

    def load_prompt(filepath):
        if not filepath:
            return ""
        try:
            return Path(filepath).read_text(encoding="utf-8")
        except Exception as e:
            return f"Error loading: {e}"

    def save_prompt(filepath, content):
        if not filepath:
            return "No file selected"
        try:
            Path(filepath).write_text(content, encoding="utf-8")
            return f"Saved to {filepath}"
        except Exception as e:
            return f"Error: {e}"

    def save_as_new(content):
        """Save as next version number."""
        existing = _list_prompt_files()
        import re
        max_ver = 0
        for f in existing:
            m = re.search(r"v(\d+)\.txt$", f)
            if m:
                max_ver = max(max_ver, int(m.group(1)))
        new_path = PROMPTS_DIR / f"v{max_ver + 1}.txt"
        try:
            new_path.write_text(content, encoding="utf-8")
            new_files = _list_prompt_files()
            return (
                gr.update(choices=new_files, value=str(new_path)),
                f"Saved to {new_path}",
            )
        except Exception as e:
            return gr.update(), f"Error: {e}"

    prompt_selector.change(
        fn=load_prompt, inputs=prompt_selector, outputs=prompt_editor,
    )
    save_btn.click(
        fn=save_prompt,
        inputs=[prompt_selector, prompt_editor],
        outputs=save_status,
    )
    save_as_btn.click(
        fn=save_as_new,
        inputs=prompt_editor,
        outputs=[prompt_selector, save_status],
    )

    # Load initial prompt
    if prompt_files:
        prompt_editor.value = load_prompt(prompt_files[-1])

    return prompt_selector, prompt_editor


def build_presets_tab(all_controls: dict):
    """Presets management tab."""
    gr.Markdown("### Presets — Coaching Domain Skins")
    gr.Markdown(
        "A preset defines a complete coaching domain: prompt, LLM tuning, "
        "TTS voice, session behavior. Switch presets to change what AIASIS coaches."
    )

    preset_list = gr.Dropdown(
        choices=_list_preset_files(),
        label="Select Preset",
        allow_custom_value=False,
    )
    with gr.Row():
        load_btn = gr.Button("📂 Load Preset", variant="secondary")
        apply_btn = gr.Button("✅ Apply to Active Config", variant="primary")
    with gr.Row():
        preset_name_input = gr.Textbox(
            label="Preset Name (for saving)",
            placeholder="e.g. english-coach",
        )
        save_preset_btn = gr.Button("💾 Save Current as Preset", variant="secondary")
    with gr.Row():
        delete_btn = gr.Button("🗑 Delete Preset", variant="stop")
    preset_status = gr.Textbox(label="Status", interactive=False)

    return (preset_list, load_btn, apply_btn, preset_name_input,
            save_preset_btn, delete_btn, preset_status)


def build_logs_tab():
    """Session logs viewer tab."""
    gr.Markdown("### Session Logs")

    log_files = _list_log_files()
    log_selector = gr.Dropdown(
        choices=log_files,
        label="Session Log File",
        value=log_files[0] if log_files else None,
    )
    refresh_btn = gr.Button("🔄 Refresh", variant="secondary")
    summary_box = gr.JSON(label="Session Summary")
    whispers_table = gr.Dataframe(
        label="Whisper Entries",
        headers=["#", "Time", "Trigger", "Response", "Duration(ms)", "Rating", "Aborted"],
        interactive=False,
    )

    def load_log(filepath):
        if not filepath or not Path(filepath).is_file():
            return {}, []
        summary = {}
        rows = []
        idx = 0
        try:
            with open(filepath, encoding="utf-8") as f:
                for line in f:
                    record = json.loads(line.strip())
                    if record.get("type") == "summary":
                        summary = record
                    elif record.get("type") == "whisper":
                        idx += 1
                        rows.append([
                            idx,
                            record.get("timestamp", "")[:19],
                            record.get("trigger_type", ""),
                            (record.get("llm_response", "")[:80] + "..."
                             if len(record.get("llm_response", "")) > 80
                             else record.get("llm_response", "")),
                            record.get("tts_duration_ms", 0),
                            record.get("user_rating", "—"),
                            "Yes" if record.get("aborted") else "",
                        ])
        except Exception as e:
            summary = {"error": str(e)}
        return summary, rows

    def refresh_logs():
        new_files = _list_log_files()
        return gr.update(choices=new_files, value=new_files[0] if new_files else None)

    log_selector.change(fn=load_log, inputs=log_selector, outputs=[summary_box, whispers_table])
    refresh_btn.click(fn=refresh_logs, outputs=log_selector)

    return log_selector


# ── Main App ─────────────────────────────────────────────────────────────────

def create_app() -> gr.Blocks:
    """Build and return the Gradio Blocks app."""

    input_devices = _list_input_devices()
    output_devices = _list_output_devices()

    with gr.Blocks(title="AIASIS Dashboard") as app:

        gr.Markdown("# 🎧 AIASIS Dashboard")
        gr.Markdown(
            "Configure the coaching engine, manage presets, edit prompts, "
            "and review session logs. Changes are saved to `config/active.json` "
            "and picked up by the CLI on next startup."
        )

        # ── All controls (we'll collect references for preset load/save) ───
        controls = {}

        with gr.Tabs():

            # ── Audio Tab ────────────────────────────────────────────────
            with gr.Tab("🎙 Audio"):
                (controls["input_device"], controls["output_device"],
                 controls["vad_threshold"], controls["audio_queue_max"],
                ) = build_audio_tab()

            # ── LLM Tab ──────────────────────────────────────────────────
            with gr.Tab("🧠 LLM"):
                (controls["provider"], controls["model"],
                 controls["temperature"], controls["max_tokens"],
                 controls["base_url"], controls["api_version"],
                ) = build_llm_tab()

            # ── STT Tab ──────────────────────────────────────────────────
            with gr.Tab("🗣 STT"):
                (controls["deepgram_model"], controls["eot_threshold"],
                 controls["connection_retries"], controls["connection_timeout"],
                ) = build_stt_tab()

            # ── TTS Tab ──────────────────────────────────────────────────
            with gr.Tab("🔊 TTS"):
                (controls["voice"], controls["rate"],
                 controls["volume"], controls["pitch"],
                ) = build_tts_tab()

            # ── Session Tab ──────────────────────────────────────────────
            with gr.Tab("⚙ Session"):
                (controls["trigger_interval_min"], controls["coaching_max_words"],
                 controls["buffer_max_age_min"], controls["timer_check_interval_sec"],
                 controls["tail_context_entries"], controls["no_observation_text"],
                 controls["debug_logs"],
                ) = build_session_tab()

            # ── Prompt Tab ───────────────────────────────────────────────
            with gr.Tab("📝 Prompt"):
                controls["prompt_selector"], controls["prompt_editor"] = build_prompt_tab()

            # ── Presets Tab ──────────────────────────────────────────────
            with gr.Tab("🎨 Presets"):
                (preset_list, load_btn, apply_btn, preset_name_input,
                 save_preset_btn, delete_btn, preset_status,
                ) = build_presets_tab(controls)

            # ── Logs Tab ─────────────────────────────────────────────────
            with gr.Tab("📊 Logs"):
                build_logs_tab()

        # ── Preset: Load ─────────────────────────────────────────────────

        def load_preset(preset_name):
            if not preset_name:
                return [gr.update()] * 18 + ["No preset selected"]

            path = PRESETS_DIR / f"{preset_name}.json"
            if not path.is_file():
                return [gr.update()] * 18 + [f"Preset file not found: {path}"]

            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                return [gr.update()] * 18 + [f"Error loading preset: {e}"]

            # Flatten
            flat = {}
            for k, v in data.items():
                if k == "_meta":
                    continue
                if isinstance(v, dict):
                    flat.update(v)
                else:
                    flat[k] = v

            # Map to control updates — validate prompt file is in choices
            prompt_files = _list_prompt_files()
            prompt_file = flat.get("file", "")
            if prompt_file not in prompt_files:
                prompt_file = prompt_files[-1] if prompt_files else None
            prompt_content = ""
            if prompt_file and Path(prompt_file).is_file():
                try:
                    prompt_content = Path(prompt_file).read_text(encoding="utf-8")
                except Exception:
                    pass

            # Return updates in the exact order of the output list
            meta = data.get("_meta", {})
            name = meta.get("preset_name", preset_name)

            return [
                # Audio
                _device_to_choice(flat.get("input_device"), input_devices),
                _device_to_choice(flat.get("output_device"), output_devices),
                flat.get("vad_threshold", 0.5),
                flat.get("audio_queue_max", 200),
                # LLM
                flat.get("provider", "openai"),
                flat.get("model", "gpt-4o-mini"),
                flat.get("temperature", 0.7),
                flat.get("max_tokens", 300),
                flat.get("base_url", ""),
                flat.get("api_version", ""),
                # STT
                flat.get("deepgram_model", "flux-general-en"),
                flat.get("eot_threshold", 0.7),
                flat.get("connection_retries", 3),
                flat.get("connection_timeout", 15),
                # TTS
                flat.get("voice", "en-US-AriaNeural"),
                flat.get("rate", "-20%"),
                flat.get("volume", "-15%"),
                flat.get("pitch", "+0Hz"),
                # Session
                flat.get("trigger_interval_min", 10),
                flat.get("coaching_max_words", 80),
                flat.get("buffer_max_age_min", 15),
                flat.get("timer_check_interval_sec", 5),
                flat.get("tail_context_entries", 3),
                flat.get("no_observation_text", "No notable observations."),
                flat.get("debug_logs", False),
                # Prompt
                gr.update(value=prompt_file),
                prompt_content,
                # Status
                f"Loaded preset: {name}",
            ]

        load_outputs = [
            # Audio
            controls["input_device"], controls["output_device"],
            controls["vad_threshold"], controls["audio_queue_max"],
            # LLM
            controls["provider"], controls["model"],
            controls["temperature"], controls["max_tokens"],
            controls["base_url"], controls["api_version"],
            # STT
            controls["deepgram_model"], controls["eot_threshold"],
            controls["connection_retries"], controls["connection_timeout"],
            # TTS
            controls["voice"], controls["rate"],
            controls["volume"], controls["pitch"],
            # Session
            controls["trigger_interval_min"], controls["coaching_max_words"],
            controls["buffer_max_age_min"], controls["timer_check_interval_sec"],
            controls["tail_context_entries"], controls["no_observation_text"],
            controls["debug_logs"],
            # Prompt
            controls["prompt_selector"], controls["prompt_editor"],
            # Status
            preset_status,
        ]

        load_btn.click(fn=load_preset, inputs=preset_list, outputs=load_outputs)

        # ── Collect all control inputs for save/apply ────────────────────

        all_inputs = [
            controls["input_device"], controls["output_device"],
            controls["vad_threshold"], controls["audio_queue_max"],
            controls["provider"], controls["model"],
            controls["temperature"], controls["max_tokens"],
            controls["base_url"], controls["api_version"],
            controls["deepgram_model"], controls["eot_threshold"],
            controls["connection_retries"], controls["connection_timeout"],
            controls["voice"], controls["rate"],
            controls["volume"], controls["pitch"],
            controls["trigger_interval_min"], controls["coaching_max_words"],
            controls["buffer_max_age_min"], controls["timer_check_interval_sec"],
            controls["tail_context_entries"], controls["no_observation_text"],
            controls["debug_logs"],
            controls["prompt_selector"],
        ]

        def _build_json_from_controls(
            input_dev, output_dev, vad_thresh, queue_max,
            provider, model, temp, max_tok, base_url, api_ver,
            dg_model, eot_thresh, retries, timeout,
            voice, rate, volume, pitch,
            trigger_int, max_words, buf_age, timer_int,
            tail_ent, no_obs, debug,
            prompt_file,
            preset_name="", description="",
        ) -> dict:
            """Build the JSON config dict from control values."""
            return {
                "_meta": {
                    "preset_name": preset_name,
                    "description": description,
                },
                "audio": {
                    "input_device": _parse_device_choice(input_dev),
                    "output_device": _parse_device_choice(output_dev),
                    "vad_threshold": float(vad_thresh),
                    "audio_queue_max": int(queue_max),
                },
                "llm": {
                    "provider": provider,
                    "model": model,
                    "temperature": float(temp),
                    "max_tokens": int(max_tok),
                    "base_url": base_url or None,
                    "api_version": api_ver or None,
                },
                "stt": {
                    "deepgram_model": dg_model,
                    "eot_threshold": float(eot_thresh),
                    "connection_retries": int(retries),
                    "connection_timeout": int(timeout),
                },
                "tts": {
                    "voice": voice,
                    "rate": rate,
                    "volume": volume,
                    "pitch": pitch,
                },
                "session": {
                    "trigger_interval_min": float(trigger_int),
                    "coaching_max_words": int(max_words),
                    "buffer_max_age_min": int(buf_age),
                    "timer_check_interval_sec": int(timer_int),
                    "tail_context_entries": int(tail_ent),
                    "no_observation_text": no_obs,
                    "debug_logs": bool(debug),
                },
                "prompt": {
                    "file": prompt_file or "",
                },
            }

        # ── Apply to active config ───────────────────────────────────────

        def apply_config(*args):
            data = _build_json_from_controls(*args)
            try:
                save_json_config(data)
                return f"✅ Saved to {CONFIG_JSON_PATH} — CLI will use on next startup"
            except Exception as e:
                return f"Error saving: {e}"

        apply_btn.click(fn=apply_config, inputs=all_inputs, outputs=preset_status)

        # ── Save as preset ───────────────────────────────────────────────

        def save_preset(name, *args):
            if not name or not name.strip():
                return gr.update(), "Enter a preset name first"
            slug = name.strip().lower().replace(" ", "-")
            data = _build_json_from_controls(*args, preset_name=name.strip())
            path = PRESETS_DIR / f"{slug}.json"
            try:
                PRESETS_DIR.mkdir(parents=True, exist_ok=True)
                save_json_config(data, path)
                new_presets = _list_preset_files()
                return (
                    gr.update(choices=new_presets, value=slug),
                    f"Saved preset: {path}",
                )
            except Exception as e:
                return gr.update(), f"Error: {e}"

        save_preset_btn.click(
            fn=save_preset,
            inputs=[preset_name_input] + all_inputs,
            outputs=[preset_list, preset_status],
        )

        # ── Delete preset ────────────────────────────────────────────────

        def delete_preset(name):
            if not name:
                return gr.update(), "No preset selected"
            path = PRESETS_DIR / f"{name}.json"
            if not path.is_file():
                return gr.update(), f"Not found: {path}"
            try:
                path.unlink()
                new_presets = _list_preset_files()
                return (
                    gr.update(choices=new_presets, value=None),
                    f"Deleted preset: {name}",
                )
            except Exception as e:
                return gr.update(), f"Error: {e}"

        delete_btn.click(
            fn=delete_preset,
            inputs=preset_list,
            outputs=[preset_list, preset_status],
        )

        # ── Load active config into controls on app start ────────────────

        def on_load():
            """Populate controls from active.json on app open."""
            data = _load_active_config()
            flat = {}
            for k, v in data.items():
                if k == "_meta":
                    continue
                if isinstance(v, dict):
                    flat.update(v)
                else:
                    flat[k] = v

            prompt_files = _list_prompt_files()
            prompt_file = flat.get("file", "")
            # Ensure prompt_file is a valid choice; fall back to latest
            if prompt_file not in prompt_files:
                prompt_file = prompt_files[-1] if prompt_files else None
            prompt_content = ""
            if prompt_file and Path(prompt_file).is_file():
                try:
                    prompt_content = Path(prompt_file).read_text(encoding="utf-8")
                except Exception:
                    pass

            return [
                _device_to_choice(flat.get("input_device"), input_devices),
                _device_to_choice(flat.get("output_device"), output_devices),
                flat.get("vad_threshold", 0.5),
                flat.get("audio_queue_max", 200),
                flat.get("provider", "openai"),
                flat.get("model", "gpt-4o-mini"),
                flat.get("temperature", 0.7),
                flat.get("max_tokens", 300),
                flat.get("base_url", "") or "",
                flat.get("api_version", "") or "",
                flat.get("deepgram_model", "flux-general-en"),
                flat.get("eot_threshold", 0.7),
                flat.get("connection_retries", 3),
                flat.get("connection_timeout", 15),
                flat.get("voice", "en-US-AriaNeural"),
                flat.get("rate", "-20%"),
                flat.get("volume", "-15%"),
                flat.get("pitch", "+0Hz"),
                flat.get("trigger_interval_min", 10),
                flat.get("coaching_max_words", 80),
                flat.get("buffer_max_age_min", 15),
                flat.get("timer_check_interval_sec", 5),
                flat.get("tail_context_entries", 3),
                flat.get("no_observation_text", "No notable observations."),
                flat.get("debug_logs", False),
                gr.update(choices=prompt_files, value=prompt_file),
                prompt_content,
            ]

        # Wire load event
        load_on_start_outputs = [
            controls["input_device"], controls["output_device"],
            controls["vad_threshold"], controls["audio_queue_max"],
            controls["provider"], controls["model"],
            controls["temperature"], controls["max_tokens"],
            controls["base_url"], controls["api_version"],
            controls["deepgram_model"], controls["eot_threshold"],
            controls["connection_retries"], controls["connection_timeout"],
            controls["voice"], controls["rate"],
            controls["volume"], controls["pitch"],
            controls["trigger_interval_min"], controls["coaching_max_words"],
            controls["buffer_max_age_min"], controls["timer_check_interval_sec"],
            controls["tail_context_entries"], controls["no_observation_text"],
            controls["debug_logs"],
            controls["prompt_selector"], controls["prompt_editor"],
        ]
        app.load(fn=on_load, outputs=load_on_start_outputs)

    return app


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Ensure we run from project root (same as main.py)
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    app = create_app()
    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft(),
    )
