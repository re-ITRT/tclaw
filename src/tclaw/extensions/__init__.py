"""tclaw 内置扩展包（Extension）。

扩展是系统钩子/中间件，不暴露给 LLM，通过订阅 EventBus 事件工作。
自动发现 src/tclaw/extensions/ 下的所有 Mod 子类。

用法：
    bus.load_all_extensions(ALL_EXTENSIONS)
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..common.extension import Extension


def _discover_extensions() -> list[type[Extension]]:
    """扫描 extensions 包下的子目录，找到所有 Extension 子类。

    每个扩展一个文件夹，包含 __init__.py（继承 Extension）。
    """
    from ..common.extension import Extension as _ExtBase
    from .. import extensions as _pkg

    classes: list[type[Extension]] = []
    for _imp, modname, ispkg in pkgutil.iter_modules(
        _pkg.__path__, prefix="tclaw.extensions."
    ):
        if not ispkg:
            continue
        try:
            mod = importlib.import_module(modname)
        except Exception:
            continue
        for name in dir(mod):
            obj = getattr(mod, name)
            if isinstance(obj, type) and issubclass(obj, _ExtBase) and obj is not _ExtBase:
                classes.append(obj)
    return classes


ALL_EXTENSIONS: list[type[Extension]] = _discover_extensions()
"""自动发现的全部扩展类列表。在 main.py 中加载。"""
