"""tclaw 内置工具包。

用法
----
    from tclaw.tools import ALL_TOOLS

    bus = EventBus()
    bus.load_all_tools(ALL_TOOLS)
    await bus.start()
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..common.tool import Tool


def _discover_tools() -> list[type[Tool]]:
    """扫描 tools 包下的子目录，找到所有 Tool 子类。"""
    from ..common.tool import Tool as _ToolBase
    from .. import tools as _pkg

    classes: list[type[Tool]] = []
    for _imp, modname, ispkg in pkgutil.iter_modules(
        _pkg.__path__, prefix="tclaw.tools."
    ):
        if not ispkg:
            continue
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and issubclass(obj, _ToolBase) and obj is not _ToolBase:
                classes.append(obj)
    return classes


ALL_TOOLS: list[type[Tool]] = _discover_tools()
