from __future__ import annotations

import logging
from pathlib import Path

_CONFIGURED = False
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(log_file: Path) -> None:
    global _CONFIGURED
    log_file.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    if _CONFIGURED:
        return
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(file_handler)
    root.addHandler(stream)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def read_log_tail(log_file: Path, max_chars: int = 80_000) -> str:
    if not log_file.exists():
        return "(no log file yet)"
    data = log_file.read_text(encoding="utf-8", errors="replace")
    if len(data) <= max_chars:
        return data
    return data[-max_chars:]
