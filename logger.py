from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


class TextHandler(logging.Handler):
    """将日志输出到 tkinter Text 控件"""

    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        try:
            self.text_widget.after(0, self._append, msg)
        except Exception:
            pass

    def _append(self, msg):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", msg + "\n")
        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")


def setup_logger(text_widget=None) -> logging.Logger:
    """配置日志器，同时输出到文件和 GUI 控件。"""
    logger = logging.getLogger("mirth_tracker")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 文件输出
    log_dir = _get_base_dir() / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"mirth_{datetime.now():%Y%m%d}.log"
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # GUI 输出
    if text_widget:
        gh = TextHandler(text_widget)
        gh.setLevel(logging.INFO)
        gh.setFormatter(fmt)
        logger.addHandler(gh)

    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("mirth_tracker")
