"""Unit tests for parse_config: precedence, validation and required settings."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import config as cfg


BASE_ENV = {
    "DEEPGRAM_API_KEY": "dg-key",
    "LLM_PROVIDER": "openai",
    "LLM_API_KEY": "llm-key",
    "LLM_MODEL": "env-model",
}


def _parse(argv=None, env=None, json_cfg=None):
    """Run parse_config with the audio/ffmpeg checks and config file mocked out."""
    environment = dict(BASE_ENV if env is None else env)
    with (
        patch("sys.argv", ["aiasis", *(argv or [])]),
        patch.dict(os.environ, environment, clear=True),
        patch.object(cfg, "_check_ffmpeg"),
        patch.object(cfg, "_check_audio_devices"),
        patch.object(cfg, "_load_json_config", return_value=json_cfg or {}),
    ):
        return cfg.parse_config()


class ParseConfigTests(unittest.TestCase):
    def test_defaults_come_from_env_and_constants(self) -> None:
        config = _parse()
        self.assertEqual(config.llm_provider, "openai")
        self.assertEqual(config.llm_model, "env-model")
        self.assertEqual(config.deepgram_api_key, "dg-key")
        self.assertEqual(config.trigger_interval_min, cfg.DEFAULT_INTERVAL_MIN)
        self.assertEqual(config.coaching_max_words, cfg.DEFAULT_COACHING_MAX_WORDS)
        self.assertFalse(config.debug_logs)
        self.assertTrue(Path(config.prompt_file).is_file())

    def test_json_overrides_env_and_cli_overrides_json(self) -> None:
        json_cfg = {"llm_model": "json-model", "trigger_interval_min": 7}
        config = _parse(json_cfg=json_cfg)
        self.assertEqual(config.llm_model, "json-model")
        self.assertEqual(config.trigger_interval_min, 7)

        config = _parse(
            ["--llm-model", "cli-model", "--interval", "3"], json_cfg=json_cfg
        )
        self.assertEqual(config.llm_model, "cli-model")
        self.assertEqual(config.trigger_interval_min, 3)

    def test_latest_prompt_version_is_selected(self) -> None:
        config = _parse()
        versions = [
            int(p.stem[1:]) for p in Path("prompts").glob("v*.txt")
        ]
        self.assertTrue(config.prompt_file.endswith(f"v{max(versions)}.txt"))

    def test_debug_flag_enables_debug_logs(self) -> None:
        self.assertTrue(_parse(["--debug-logs"]).debug_logs)

    def test_missing_deepgram_key_exits(self) -> None:
        env = {k: v for k, v in BASE_ENV.items() if k != "DEEPGRAM_API_KEY"}
        with patch("builtins.print"), self.assertRaises(SystemExit):
            _parse(env=env)

    def test_missing_llm_key_exits(self) -> None:
        env = {k: v for k, v in BASE_ENV.items() if k != "LLM_API_KEY"}
        with patch("builtins.print"), self.assertRaises(SystemExit):
            _parse(env=env)

    def test_unknown_provider_exits(self) -> None:
        with patch("builtins.print"), self.assertRaises(SystemExit):
            _parse(["--llm-provider", "bogus"])

    def test_azure_requires_base_url_and_api_version(self) -> None:
        with patch("builtins.print"), self.assertRaises(SystemExit):
            _parse(["--llm-provider", "azure"])
        config = _parse(
            ["--llm-provider", "azure"],
            env={**BASE_ENV, "LLM_BASE_URL": "https://x", "LLM_API_VERSION": "v1"},
        )
        self.assertEqual(config.llm_base_url, "https://x")

    def test_max_words_below_minimum_exits(self) -> None:
        with patch("builtins.print"), self.assertRaises(SystemExit):
            _parse(["--max-words", "4"])

    def test_missing_prompt_file_exits(self) -> None:
        with patch("builtins.print"), self.assertRaises(SystemExit):
            _parse(["--prompt", "does/not/exist.txt"])


class LoadJsonConfigTests(unittest.TestCase):
    def test_missing_file_returns_empty_dict(self) -> None:
        self.assertEqual(cfg._load_json_config(Path("nope-does-not-exist.json")), {})

    def test_nested_sections_are_flattened_and_meta_skipped(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "active.json"
            path.write_text(
                json.dumps({"_meta": {"x": 1}, "llm": {"llm_model": "m"}, "top": 2}),
                encoding="utf-8",
            )
            self.assertEqual(cfg._load_json_config(path), {"llm_model": "m", "top": 2})

    def test_invalid_json_returns_empty_dict(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp, patch("builtins.print"):
            path = Path(tmp) / "active.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(cfg._load_json_config(path), {})


if __name__ == "__main__":
    unittest.main()
