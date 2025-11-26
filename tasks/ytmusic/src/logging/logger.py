"""简单统一的日志配置：控制台 + 可选文件。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


def get_logger(name: str, log_file: Optional[Path] = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


__all__ = ["get_logger"]
