"""ComponentManager —— 组件注册中心。

三种实现：
- GatewayComponentManager  — 有前端（WebSocket 推送 + 回调 Future resolve）
- StdioComponentManager    — CLI 模式（print + stdin）
- NullComponentManager     — 无交互/后台（抛异常）
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .exceptions import ComponentNotFound, ComponentNotSupported, ComponentTimeout

if TYPE_CHECKING:
    from .gateway import Gateway

logger = logging.getLogger("tclaw.gateway.component_manager")


# ── 抽象接口 ────────────────────────────────────────────────


class ComponentManager(ABC):
    """组件注册中心抽象。Tool 通过 bus.component_manager 访问。"""

    @abstractmethod
    async def register(
        self,
        session_id: str,
        tool_id: str,
        schema: dict,
    ) -> str:
        """注册交互组件。返回 component_id。"""

    @abstractmethod
    async def wait_for_component(
        self,
        component_id: str,
        *,
        timeout: float | None = None,
    ) -> Any:
        """等待组件的用户回调。Tool 在这个调用上阻塞。"""

    @abstractmethod
    async def update_component(self, component_id: str, data: dict) -> None:
        """更新已渲染的组件（进度、验证结果等）。"""

    @abstractmethod
    async def destroy_component(self, component_id: str) -> None:
        """销毁组件。"""

    def cleanup_session(self, session_id: str) -> None:
        """清理 session 关联的所有组件。子类可重写。"""


# ── ComponentBinding ────────────────────────────────────────


@dataclass
class ComponentBinding:
    """已注册组件的内部绑定信息。"""
    component_id: str
    session_id: str
    tool_id: str
    schema: dict
    blocking: bool = False  # True=wait_for_component 在等, False=非阻塞
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())


# ── Gateway 实现 ────────────────────────────────────────────


class GatewayComponentManager(ComponentManager):
    """基于 WebSocket 的组件注册中心。"""

    def __init__(self, gateway: Gateway) -> None:
        self._gateway = gateway
        self._components: dict[str, ComponentBinding] = {}

    def _resolve_component_url(self, tool_id: str, schema: dict) -> str | None:
        """为 custom 类型组件解析 URL。"""
        if schema.get("type") != "custom":
            return None
        # 优先用显式 URL
        url = schema.get("component_url")
        if url:
            return url
        # 自动拼接本地静态路由
        schema["component_url"] = f"/components/{tool_id}/index.html"
        return schema["component_url"]

    async def register(self, session_id: str, tool_id: str, schema: dict) -> str:
        component_id = f"comp_{uuid.uuid4().hex[:12]}"
        self._resolve_component_url(tool_id, schema)
        binding = ComponentBinding(
            component_id=component_id,
            session_id=session_id,
            tool_id=tool_id,
            schema=schema,
        )
        self._components[component_id] = binding

        await self._gateway.send(session_id, {
            "type": "component_register",
            "component_id": component_id,
            "session_id": session_id,
            "tool_id": tool_id,
            "schema": schema,
        })
        logger.debug("component registered: %s (tool=%s, session=%s)",
                     component_id, tool_id, session_id)
        return component_id

    async def wait_for_component(
        self,
        component_id: str,
        *,
        timeout: float | None = None,
    ) -> Any:
        binding = self._components.get(component_id)
        if not binding:
            raise ComponentNotFound(component_id)
        binding.blocking = True  # 标记为阻塞模式
        try:
            result = await asyncio.wait_for(binding.future, timeout=timeout)
            logger.debug("component callback resolved: %s", component_id)
            return result
        except asyncio.TimeoutError:
            raise ComponentTimeout(component_id)

    async def update_component(self, component_id: str, data: dict) -> None:
        binding = self._components.get(component_id)
        if not binding:
            return
        await self._gateway.send(binding.session_id, {
            "type": "component_update",
            "component_id": component_id,
            "data": data,
        })

    async def destroy_component(self, component_id: str) -> None:
        binding = self._components.pop(component_id, None)
        if binding:
            if not binding.future.done():
                binding.future.cancel()
            await self._gateway.send(binding.session_id, {
                "type": "component_destroy",
                "component_id": component_id,
            })

    def resolve_callback(self, component_id: str, result: Any) -> None:
        """前端回调时由 Gateway 调用。"""
        binding = self._components.get(component_id)
        if not binding or binding.future.done():
            return

        if binding.blocking:
            binding.future.set_result(result)
            logger.debug("callback resolved (blocking): %s", component_id)
        else:
            # 非阻塞：路由到 Tool.handle_gateway_event
            logger.debug("callback routing to tool (non-blocking): %s", component_id)
            asyncio.create_task(self._route_non_blocking(binding, result))

    async def _route_non_blocking(self, binding: ComponentBinding, result: Any) -> None:
        """非阻塞回调：路由到 Tool.handle_gateway_event。

        不在 resolve_callback 里 pop binding，
        由 Tool.handle_gateway_event → destroy_component 负责 pop + 发 WS destroy。
        """
        tool = self._gateway.bus.get_tool(binding.tool_id)
        if not tool:
            return
        await tool.handle_gateway_event({
            "_component_id": binding.component_id,
            "event": result.get("event", ""),
            "data": result.get("data", {}),
        }, binding.session_id)

    def cleanup_session(self, session_id: str) -> None:
        to_remove = [
            cid for cid, b in self._components.items()
            if b.session_id == session_id
        ]
        for cid in to_remove:
            binding = self._components.pop(cid, None)
            if binding and not binding.future.done():
                binding.future.cancel()
        if to_remove:
            logger.debug("cleaned %d components for session %s", len(to_remove), session_id)


# ── Null 实现 ───────────────────────────────────────────────


class NullComponentManager(ComponentManager):
    """无前端时使用。调用 register 会引发 ComponentNotSupported。"""

    async def register(self, session_id: str, tool_id: str, schema: dict) -> str:
        raise ComponentNotSupported("no frontend connected")

    async def wait_for_component(
        self,
        component_id: str,
        *,
        timeout: float | None = None,
    ) -> Any:
        raise ComponentNotSupported("no frontend connected")

    async def update_component(self, component_id: str, data: dict) -> None:
        logger.warning("update_component called with no frontend: %s", component_id)

    async def destroy_component(self, component_id: str) -> None:
        pass


# ── Stdio 实现 ──────────────────────────────────────────────


class StdioComponentManager(ComponentManager):
    """CLI 模式：交互组件打印到终端，从 stdin 读。"""

    def __init__(self) -> None:
        self._waiters: dict[str, asyncio.Future] = {}

    async def register(self, session_id: str, tool_id: str, schema: dict) -> str:
        component_id = f"comp_cli_{uuid.uuid4().hex[:8]}"
        self._waiters[component_id] = asyncio.get_event_loop().create_future()

        prompt = schema.get("prompt", schema.get("placeholder", ""))
        print(f"\n[{tool_id}] {prompt}")
        if schema.get("type") == "select":
            options = schema.get("options", [])
            for i, opt in enumerate(options):
                print(f"  {i + 1}. {opt.get('label', opt.get('value', opt))}")
        return component_id

    async def wait_for_component(
        self,
        component_id: str,
        *,
        timeout: float | None = None,
    ) -> Any:
        future = self._waiters.get(component_id)
        if not future:
            raise ComponentNotFound(component_id)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, input, "> ")
        future.set_result({"text": result.strip()})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            raise ComponentTimeout(component_id)

    async def update_component(self, component_id: str, data: dict) -> None:
        print(f"[update {component_id}]: {data}")

    async def destroy_component(self, component_id: str) -> None:
        self._waiters.pop(component_id, None)
