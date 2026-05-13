"""tclaw 启动入口。

用法：
  python -m tclaw              # 默认 8080
  python -m tclaw --port 9000  # 指定端口
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal

from .common.event_bus import EventBus
from .common.context_manager import ContextManager
from .common.llm_client import LLMClient
from .common.settings import LLM_MODEL, LLM_API_KEY, LOG_LEVEL, GATEWAY_HOST, GATEWAY_PORT
from .tools import ALL_TOOLS
from .extensions import ALL_EXTENSIONS

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

# 文件日志（DEBUG 级别，按时间戳分文件）
from .common.settings import WORKSPACE_DIR
import os
_log_dir = os.path.join(WORKSPACE_DIR, "logs")
os.makedirs(_log_dir, exist_ok=True)
from datetime import datetime
_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
_fh = logging.FileHandler(
    os.path.join(_log_dir, f"tclaw_{_ts}.log"),
    encoding="utf-8",
)
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
))
logging.getLogger("tclaw").addHandler(_fh)

logger = logging.getLogger("tclaw")


async def main() -> None:
    parser = argparse.ArgumentParser(description="tclaw Gateway")
    parser.add_argument("--port", type=int, default=None, help="override port")
    parser.add_argument("--host", type=str, default=None, help="override host")
    args = parser.parse_args()

    host = args.host or GATEWAY_HOST
    port = args.port or GATEWAY_PORT

    # ── 检查 API Key ──────────────────────────────────
    if not LLM_API_KEY:
        logger.warning("LLM_API_KEY not set — LLM calls will fail")

    # ── 初始化 EventBus ──────────────────────────────
    bus = EventBus()
    bus.load_all_tools(ALL_TOOLS)
    bus.load_all_extensions(ALL_EXTENSIONS)
    bus.set_llm(LLMClient())
    bus.set_context_manager(
        ContextManager(system_prompt="你是 tclaw，一个 AI 助手。")
    )
    await bus.start()
    n_tools = len(bus.registered_tools)
    n_exts = len(bus.registered_extensions)
    logger.info("EventBus started with %d tools, %d extensions", n_tools, n_exts)

    # ── 启动 Gateway ─────────────────────────────────
    from .gateway import Gateway
    from .gateway.app import start_gateway

    gateway = Gateway(bus, host=host, port=port)
    server_task, server = await start_gateway(gateway)
    logger.info("Gateway listening on ws://%s:%d", host, port)

    # ── 等待退出信号 ─────────────────────────────────
    stop_event = asyncio.Event()

    def _shutdown():
        logger.info("shutdown signal received")
        server.should_exit = True
        stop_event.set()

    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGINT, _shutdown)
    loop.add_signal_handler(signal.SIGTERM, _shutdown)

    await stop_event.wait()

    # ── 优雅关闭 ─────────────────────────────────────
    logger.info("shutting down...")
    try:
        await asyncio.wait_for(server_task, timeout=5.0)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        logger.warning("server shutdown timed out, forcing...")
        server_task.cancel()
        try:
            await server_task
        except (asyncio.CancelledError, Exception):
            pass
    await bus.stop()
    logger.info("shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
