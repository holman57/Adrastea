import os
import unittest
from pathlib import Path
from adrastea.config import Config, config, load_dotenv


class TestConfig(unittest.TestCase):
    def test_default_config(self):
        self.assertEqual(config.ollama_base_url, "http://127.0.0.1:11434")
        self.assertEqual(config.ollama_model, "qwen3-coder:30b")
        self.assertEqual(config.ipc_host, "127.0.0.1")
        self.assertEqual(config.ipc_port, 8765)

    def test_env_override(self):
        os.environ["NOTIFICATION_TARGET_EMAIL"] = "tester@example.com"
        os.environ["NOTIFICATION_TARGET_PHONE"] = "555-0100"
        cfg = Config()
        self.assertEqual(cfg.target_email, "tester@example.com")
        self.assertEqual(cfg.target_phone, "555-0100")

    def test_directories_created(self):
        self.assertTrue(config.data_dir.exists())
        self.assertTrue(config.logs_dir.exists())


if __name__ == "__main__":
    unittest.main()
