import logging
import tempfile
import unittest
from pathlib import Path

from tasks.ytmusic.src.logging.logger import get_logger


class LoggerTest(unittest.TestCase):
    def test_logger_writes_to_file_and_console(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "test.log"
            logger = get_logger("test_logger_module", log_file=log_path, level=logging.INFO)
            logger.info("hello")
            # 再次获取同名 logger 不应重复添加 handler
            logger2 = get_logger("test_logger_module", log_file=log_path, level=logging.INFO)
            logger2.info("world")

            content = log_path.read_text()
            self.assertIn("hello", content)
            self.assertIn("world", content)


if __name__ == "__main__":
    unittest.main()
