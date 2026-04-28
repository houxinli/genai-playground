import os
import unittest
from unittest.mock import patch

from tasks.translation.src.cli import create_argument_parser
from tasks.translation.src.core.config import TranslationConfig


class TranslationConfigProviderTest(unittest.TestCase):
    def parse_args(self, extra=None):
        parser = create_argument_parser()
        return parser.parse_args((extra or []) + ["input.txt"])

    def test_openrouter_ignores_unscoped_env_base_url(self):
        args = self.parse_args()
        with patch.dict(os.environ, {"LLM_BASE_URL": "http://localhost:11434/v1"}, clear=True):
            config = TranslationConfig.from_args(args)
        self.assertEqual(config.llm_provider, "openrouter")
        self.assertIsNone(config.llm_base_url)

    def test_env_base_url_applies_when_env_provider_matches(self):
        args = self.parse_args()
        with patch.dict(
            os.environ,
            {"LLM_PROVIDER": "ollama", "LLM_BASE_URL": "http://localhost:11434/v1"},
            clear=True,
        ):
            config = TranslationConfig.from_args(args)
        self.assertEqual(config.llm_provider, "ollama")
        self.assertEqual(config.llm_base_url, "http://localhost:11434/v1")

    def test_validate_rejects_openrouter_localhost_pair(self):
        config = TranslationConfig(llm_provider="openrouter", llm_base_url="http://localhost:11434/v1")
        self.assertTrue(any("openrouter.ai" in error for error in config.validate()))

    def test_validate_rejects_local_provider_openrouter_pair(self):
        config = TranslationConfig(llm_provider="vllm", llm_base_url="https://openrouter.ai/api/v1")
        self.assertTrue(any("OpenRouter" in error for error in config.validate()))


if __name__ == "__main__":
    unittest.main()
