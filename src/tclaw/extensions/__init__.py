"""tclaw 内置扩展包。"""

from __future__ import annotations

import importlib
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..common.extension import Extension


def _discover_extensions() -> list[type[Extension]]:
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
