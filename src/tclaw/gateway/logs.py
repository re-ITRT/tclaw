"""LogCapture —— 内存日志捕获，供前端查看。"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any


class RingBufferHandler(logging.Handler):
    """环形缓冲区日志处理器。保留最近 N 条日志。"""

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._buffer: deque[dict[str, Any]] = deque(maxlen=capacity)
        # 用于格式化的 formatter，仅取时间用
        self._time_fmt = logging.Formatter("%(asctime)s", datefmt="%H:%M:%S")

    def emit(self, record: logging.LogRecord) -> None:
        time_str = self._time_fmt.formatTime(record, "%H:%M:%S")
        self._buffer.append({
            "time": time_str,
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        })

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


# 全局单例
_log_handler = RingBufferHandler()
_log_handler.setLevel(logging.DEBUG)


def install_log_capture() -> None:
    """安装日志捕获处理器到 tclaw 命名空间。"""
    root = logging.getLogger("tclaw")
    if not any(isinstance(h, RingBufferHandler) for h in root.handlers):
        root.addHandler(_log_handler)
        root.setLevel(logging.DEBUG)
        for name in list(logging.root.manager.loggerDict):
            if name.startswith("tclaw"):
                logging.getLogger(name).setLevel(logging.DEBUG)


def get_logs() -> list[dict[str, Any]]:
    return _log_handler.get_all()


def clear_logs() -> None:
    _log_handler.clear()
