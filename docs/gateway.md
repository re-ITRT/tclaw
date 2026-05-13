# tclaw Gateway 设计文档

> v0.2 设计稿 · 2026-05-08

---

## 1. 为什么需要 Gateway

Gateway 是系统的**边界层**，也是一座**桥**——连接三类角色：

```
┌──────────┐               ┌──────────────────────────────────────┐
│  前端     │               │              Gateway                │
│  WebChat │── WS:text ───→│   ──publish──→ EventBus ──→ LLM循环  │
│  Discord │               │                                      │
│  Telegram│←─ WS:push ────│   ←──subscribe── EventBus ←─ LLM/Tool│
│  CLI     │               │                                      │
│          │               │   ComponentManager（组件注册中心）     │
│  交互组件 │←─ WS:component│   ↑                                 │
│  交互组件 │── WS:callback─│   │   Tool 直接调                    │
└──────────┘               └───┼──────────────────────────────────┘
                               │
                        ┌──────┴──────┐
                        │    Tools     │
                        │  user_input  │
                        │  interactive │
                        │  quiz 等     │
                        └─────────────┘
```

**三条路径，职责分明：**

| 路径 | 方式 | 用途 |
|------|------|------|
| 用户→引擎 | `publish → EventBus` | 文本消息、普通工具调用 |
| 引擎→用户 | `subscribe → push WS` | LLM 回复、工具结果推送 |
| 工具↔用户 | **直接调 Gateway ComponentManager** | 交互组件注册/更新/回调 |

**为什么交互组件要走直连？**

```
EventBus 绕路版：
  Tool → publish(AGENT_OUTPUT, mode=interactive)
       → Gateway 收到 → 推前端
       → 前端回调 → publish(TOOL_INVOKE.{tool_id})
       → Tool 收到
  问题：Tool 无法"持有等待"，必须提前返回给 LLM 循环

Gateway 直连版：
  Tool → gateway.register_component(id, schema)
       → Gateway 推前端 + Tools返回component_id
       → Tool await gateway.wait_for_component(id)
       → 前端回调 → gateway 唤醒 Tool
  好处：Tool 自然持有等待，LLM 循环不用感知交互状态
```

---

## 2. 职责清单

```
Gateway 负责：
├── 1. 网络服务（HTTP + WebSocket）
│   ├── FastAPI 应用入口
│   ├── WebSocket 端点 /ws/{session_id}
│   └── REST 端点 /api/settings /api/health ...
│
├── 2. 连接管理
│   ├── 连接 ↔ session 映射
│   ├── 断线重连 / 超时清理
│   └── 优雅关闭
│
├── 3. 消息路由（走 EventBus）
│   ├── 用户文本 → AGENT_MESSAGE_INCOMING
│   └── 工具事件 → TOOL_INVOKE.{tool_id}
│
├── 4. EventBus 订阅（推前端）
│   ├── AGENT_OUTPUT → 前端渲染文本/图形/结束
│   └── AGENT_TOOL_RESULT → 前端显示工具状态
│
├── 5. 组件注册中心（Tool 直接调）
│   ├── register_component()  — Tool 注册交互组件
│   ├── wait_for_component()  — Tool 阻塞等回调
│   ├── update_component()    — Tool 更新已渲染组件
│   └── destroy_component()   — Tool 销毁组件
│
└── 6. Session 生命周期
    ├── 首次连接 → 创建 session
    ├── 连接断开 → 保持 session（存活期内可重连）
    └── session 过期 → 清理组件 + 资源
```

Gateway **不负责**：
- ❌ LLM 推理
- ❌ 上下文构建
- ❌ Tool 业务逻辑

---

## 3. ComponentManager —— 组件注册中心

### 3.1 抽象接口

```python
class ComponentManager(ABC):
    """组件注册中心抽象。Gateway 和 CLI 各有实现。"""

    @abstractmethod
    async def register(
        self,
        session_id: str,
        tool_id: str,
        schema: dict,
    ) -> str:
        """注册交互组件。返回 component_id。"""
        ...

    @abstractmethod
    async def wait_for_component(self, component_id: str, *, timeout: float | None = None) -> Any:
        """等待组件的用户回调。Tool 在这个调用上阻塞。"""
        ...

    @abstractmethod
    async def update_component(self, component_id: str, data: dict) -> None:
        """更新已渲染的组件（进度、验证结果等）。"""
        ...

    @abstractmethod
    async def destroy_component(self, component_id: str) -> None:
        """销毁组件。"""
        ...


class NullComponentManager(ComponentManager):
    """无前端时使用。调用 register 会引发 ComponentNotSupported。"""

    async def register(self, session_id, tool_id, schema) -> str:
        raise ComponentNotSupported("no frontend connected")

    async def wait_for_component(self, component_id, *, timeout=None):
        raise ComponentNotSupported("no frontend connected")

    async def update_component(self, component_id, data):
        pass

    async def destroy_component(self, component_id):
        pass
```

### 3.2 Gateway 实现

```python
@dataclass
class ComponentBinding:
    component_id: str
    session_id: str
    tool_id: str
    schema: dict
    created_at: float = field(default_factory=time.time)
    future: asyncio.Future = field(default_factory=lambda: asyncio.get_event_loop().create_future())


class GatewayComponentManager(ComponentManager):
    """基于 WebSocket 的组件注册中心。"""

    def __init__(self, gateway: "Gateway"):
        self._gateway = gateway
        self._components: dict[str, ComponentBinding] = {}

    async def register(self, session_id: str, tool_id: str, schema: dict) -> str:
        component_id = f"comp_{uuid4().hex[:12]}"
        binding = ComponentBinding(
            component_id=component_id,
            session_id=session_id,
            tool_id=tool_id,
            schema=schema,
        )
        self._components[component_id] = binding

        # 推给前端
        await self._gateway._send_to_session(session_id, {
            "type": "component_register",
            "component_id": component_id,
            "tool_id": tool_id,
            "schema": schema,
        })
        return component_id

    async def wait_for_component(self, component_id: str, *, timeout: float | None = None) -> Any:
        binding = self._components.get(component_id)
        if not binding:
            raise ValueError(f"component not found: {component_id}")
        try:
            result = await asyncio.wait_for(binding.future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise ComponentTimeout(f"component {component_id} timed out")

    async def update_component(self, component_id: str, data: dict) -> None:
        binding = self._components.get(component_id)
        if not binding:
            return
        await self._gateway._send_to_session(binding.session_id, {
            "type": "component_update",
            "component_id": component_id,
            "data": data,
        })

    async def destroy_component(self, component_id: str) -> None:
        binding = self._components.pop(component_id, None)
        if binding and not binding.future.done():
            binding.future.cancel()
        if binding:
            await self._gateway._send_to_session(binding.session_id, {
                "type": "component_destroy",
                "component_id": component_id,
            })

    def resolve_callback(self, component_id: str, result: Any) -> None:
        """前端回调时由 Gateway 调用。"""
        binding = self._components.get(component_id)
        if binding and not binding.future.done():
            binding.future.set_result(result)
            # 回调后自动销毁
            self._components.pop(component_id, None)

    def cleanup_session(self, session_id: str) -> None:
        """清理 session 关联的所有组件。"""
        to_remove = [
            cid for cid, b in self._components.items()
            if b.session_id == session_id
        ]
        for cid in to_remove:
            binding = self._components.pop(cid, None)
            if binding and not binding.future.done():
                binding.future.cancel()
```

---

## 4. 接口定义

### 4.1 WebSocket 消息协议

```
ws://host:port/ws/{session_id}

──────────────────────────────────────────────
前端 → Gateway
──────────────────────────────────────────────

{ type: "text", content: "hello", files?: [...] }
    → Gateway publish(AGENT_MESSAGE_INCOMING)

{ type: "tool_event", tool: "exec", data: {...} }
    → Tool.handle_gateway_event() 直达（不走 EventBus）

{ type: "component_callback", component_id: "comp_...", result: {...} }
    → Gateway component_manager.resolve_callback(component_id, result)

{ type: "cancel" }
    → Gateway 取消当前推理


──────────────────────────────────────────────
Gateway → 前端
──────────────────────────────────────────────

{ type: "assistant", content: "回复文本" }
    ← 订阅 AGENT_OUTPUT

{ type: "assistant", mode: "figure", figure_type: "chart", data: {...} }
    ← 订阅 AGENT_OUTPUT(mode=figure)

{ type: "assistant", mode: "end" }
    ← 订阅 AGENT_OUTPUT(mode=end)

{ type: "tool_result", tool_id: "exec", status: "ok", duration_ms: 1234 }
    ← 订阅 AGENT_TOOL_RESULT

{ type: "component_register", component_id: "...", tool_id: "...", schema: {...} }
    ← Gateway.component_manager.register()

{ type: "component_update", component_id: "...", data: {...} }
    ← Gateway.component_manager.update_component()

{ type: "component_destroy", component_id: "..." }
    ← Gateway.component_manager.destroy_component()
```

### 4.2 REST 配置管理

```
GET  /api/settings            ← 获取配置
PUT  /api/settings            → 更新配置
GET  /api/health              ← 健康检查
POST /api/session/{id}/clear  ← 清理 session
```

---

## 5. Gateway 类设计

```python
class Gateway:
    """前端接入层。连接管理 + EventBus 代理 + 组件注册中心。"""

    def __init__(self, bus: EventBus, host: str = "0.0.0.0", port: int = 8080):
        self.bus = bus
        self.host = host
        self.port = port
        self._connections: dict[str, WebSocketConnection] = {}
        self.component_manager: ComponentManager = GatewayComponentManager(self)
        self._app = FastAPI()

        # 注册到 EventBus —— Tool 和 Gateway 双向可见
        bus.component_manager = self.component_manager  # Tool → bus.cm → Gateway
        bus._gateway = self                              # EventBus → Gateway

        # 订阅 EventBus（引擎 → 前端推送）
        bus.subscribe(Topics.AGENT_OUTPUT, self._on_output)
        bus.subscribe(Topics.AGENT_TOOL_RESULT, self._on_tool_result)

    # ── 生命周期 ─────────────────────────────────────

    async def start(self):
        """启动 uvicorn + FastAPI。"""
        config = uvicorn.Config(self._app, host=self.host, port=self.port)
        ...

    async def stop(self):
        """关闭连接 + 停止服务。"""
        ...

    # ── WS 收消息 ────────────────────────────────────
    #
    #  路由逻辑：
    #    text             → EventBus (AGENT_MESSAGE_INCOMING)
    #    tool_event       → Tool.handle_gateway_event() 直调，不走 EventBus
    #    component_callback → ComponentManager.resolve_callback()
    #    cancel           → 取消推理

    async def _on_ws_message(self, ws: WebSocket, data: dict):
        """WebSocket 消息路由。"""

        session_id = self._session_id(ws)

        match data["type"]:
            # ── 用户文本 → EventBus ──────────────────
            case "text":
                await self.bus.publish(Event(
                    topic=Topics.AGENT_MESSAGE_INCOMING,
                    payload={"text": data["content"], "files": data.get("files", [])},
                    source="gateway",
                    session_id=session_id,
                ))

            # ── 前端工具交互 → Tool 直调 ──────────────
            # 不走 EventBus 排队，直接找 Tool 处理。
            case "tool_event":
                tool = self.bus.get_tool(data["tool"])
                if tool:
                    await tool.handle_gateway_event(
                        data=data["data"],
                        session_id=session_id,
                    )
                else:
                    logger.warning("tool not found: %s", data["tool"])

            # ── 组件回调 → ComponentManager ──────────
            case "component_callback":
                self.component_manager.resolve_callback(
                    component_id=data["component_id"],
                    result=data["result"],
                )

            case "cancel":
                self._cancel_inference(session_id)

    # ── EventBus 订阅 → 推前端 ──────────────────────

    async def _on_output(self, event: Event):
        conn = self._connections.get(event.session_id)
        if not conn:
            return

        payload = event.payload
        msg = {"type": "assistant"}

        mode = payload.get("mode", "text")
        if mode == "text":
            msg["content"] = payload.get("text", "")
        elif mode == "figure":
            msg.update(mode="figure", **payload)
        elif mode == "end":
            msg["mode"] = "end"
        elif mode == "tool_start":
            msg.update(mode="tool_start", **payload)
        else:
            msg["content"] = str(payload)

        await conn.send_json(msg)

    async def _on_tool_result(self, event: Event):
        conn = self._connections.get(event.session_id)
        if not conn:
            return
        await conn.send_json({
            "type": "tool_result",
            **event.payload,
        })

    # ── 内部辅助 ────────────────────────────────────

    async def _send_to_session(self, session_id: str, data: dict) -> None:
        conn = self._connections.get(session_id)
        if conn:
            await conn.send_json(data)

    def _session_id(self, ws: WebSocket) -> str:
        ...

    def _cancel_inference(self, session_id: str) -> None:
        ...
```

---

## 6. Tool 基类：两种入口

每个 Tool 有两种入口，对应**两种调用来源**：

| 入口 | 调用来源 | 路由 |
|------|---------|------|
| `handle_event(event)` | LLM function-calling | EventBus TOOL_INVOKE 分发 |
| `handle_gateway_event(data, session_id)` | 前端 tool_event | Gateway 直调 Tool |

两种入口最终都通过 `publish(AGENT_TOOL_RESULT)` 回 LLM 循环。

```python
class UserInputTool(Tool):
    """用户输入工具。

    有两种交互路径：
    - 入口 A (handle_event): LLM 问用户问题 → 注册输入框 → 等回复
    - 入口 B (handle_gateway_event): 前端直接提交 → publish 结果
    """

    tool_id = "user_input"

    parameters = {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "提示用户输入什么"},
            "schema": {"type": "object", "description": "交互组件 schema"},
        },
        "required": ["prompt"],
    }

    # ── 入口 A：LLM 调此工具 ──────────────────────

    async def handle_event(self, event: Event) -> None:
        """从 EventBus 来。LLM 需要用户输入。

        流程：
          1. 注册输入框组件到 Gateway → 前端渲染
          2. 持有等待用户回复
          3. publish(AGENT_TOOL_RESULT) 回 LLM 循环
        """
        prompt = event.payload.get("prompt", "")
        schema = event.payload.get("schema", {
            "type": "input",
            "placeholder": prompt,
        })

        # 注册组件到 Gateway（直连，不走 EventBus）
        cm = self._bus.component_manager
        component_id = await cm.register(
            session_id=event.session_id,
            tool_id=self.tool_id,
            schema=schema,
        )

        # 持有等待用户回复
        try:
            result = await cm.wait_for_component(component_id, timeout=300)
        except ComponentTimeout:
            result = {"error": "timeout"}
        except ComponentNotSupported:
            result = {"text": input(f"{prompt}: ")}

        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={"tool_id": self.tool_id, "result": result},
            source=self.tool_id,
            session_id=event.session_id,
        ))

    # ── 入口 B：前端直接提交 ─────────────────────

    async def handle_gateway_event(self, data: dict, session_id: str) -> None:
        """从 Gateway 来。前端用户提交了输入。

        不走 EventBus 排队，直接 publish 结果。
        """
        await self.publish(Event(
            topic=Topics.AGENT_TOOL_RESULT,
            payload={"tool_id": self.tool_id, "result": data},
            source=self.tool_id,
            session_id=session_id,
        ))
```

Tool 只看到 `bus.component_manager` 这个抽象接口，不依赖 Gateway 具体实现。

---

## 7. 三种 ComponentManager 实现

| 实现 | 场景 | register | wait_for | update |
|------|------|---------|----------|--------|
| `GatewayComponentManager` | 有前端的场景 | WS 推前端 | 等 WS callback | WS 推前端 |
| `StdioComponentManager` | CLI 模式 | print schema 到终端 | 等 stdin 输入 | print 更新 |
| `NullComponentManager` | 无交互/后台 | 抛异常 | 抛异常 | no-op |

```python
class StdioComponentManager(ComponentManager):
    """CLI 模式：交互组件打印到终端，从 stdin 读。"""

    async def register(self, session_id, tool_id, schema) -> str:
        component_id = f"comp_cli_{uuid4().hex[:8]}"
        self._waiters[component_id] = asyncio.get_event_loop().create_future()
        print(f"\n[{tool_id}] {schema.get('prompt', '')}")
        if schema.get("type") == "select":
            for i, opt in enumerate(schema.get("options", [])):
                print(f"  {i + 1}. {opt['label']}")
        return component_id

    async def wait_for_component(self, component_id, *, timeout=None):
        future = self._waiters.get(component_id)
        if not future:
            raise ValueError(f"component not found: {component_id}")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, input, "> ")
        future.set_result({"text": result.strip()})
        return await future
```

---

## 8. 启动流程

```python
# main.py
from tclaw.common.event_bus import EventBus
from tclaw.common.llm_client import LLMClient
from tclaw.common.context_manager import ContextManager
from tclaw.tools import ALL_TOOLS
from tclaw.gateway import Gateway

async def main():
    # 1. EventBus 初始化
    bus = EventBus()

    # 2. 注册工具
    bus.load_all_tools(ALL_TOOLS)

    # 3. 设置 LLM + 上下文
    bus.set_llm(LLMClient())
    bus.set_context_manager(ContextManager(system_prompt="你是 tclaw"))

    # 4. 启动 EventBus
    await bus.start()

    # 5. 启动 Gateway
    gateway = Gateway(bus, host="0.0.0.0", port=8080)
    await gateway.start()
```

`bus.component_manager` 自动设为 `GatewayComponentManager`，Tool 直接可用。

---

## 9. 交互组件的完整生命周期

### 路径 A：LLM 发起 → handle_event → 注册组件 → 等回调

```
LLM 循环                      Tool (user_input)        Gateway           前端
  │                                │                     │                │
  │ publish(TOOL_INVOKE)           │                     │                │
  ├───────────────────────────────▶│                     │                │
  │                           handle_event()             │                │
  │                                │  ① register()      │                │
  │                                │ ──────────────────→│  ② component   │
  │                                │                    │ ──────────────▶│
  │                                │ ←── component_id ──│                │ 渲染
  │                                │                     │                │
  │                                │  ③ wait_for()      │                │
  │                                │ ──────────────────→│  (持有等待)     │
  │                                │                     │                │ 用户操作
  │                                │                     │                │
  │                                │                     │  ④ callback   │
  │                                │                     │ ←──────────────│
  │                                │  ⑤ Future resolved │                │
  │                                │ ←───────────────────│                │
  │                                │                     │                │
  │                                │  ⑥ publish(result) │                │
  │ ←── AGENT_TOOL_RESULT ────────│                     │                │
  │ LLM 循环继续                    │                     │                │
```

### 路径 B：前端发起 → handle_gateway_event → 直接 publish

```
LLM 循环                      Tool (confirm)           Gateway           前端
  │                                │                     │                │
  │                                │                     │  ① tool_event │
  │                                │                     │ ←──────────────│
  │                                │  ② handle_gateway  │                │
  │                                │    _event()         │                │
  │                                │ ←───────────────────│                │
  │                                │                     │                │
  │                                │  ③ publish(result) │                │
  │ ←── AGENT_TOOL_RESULT ────────│                     │                │
  │ LLM 循环继续                    │                     │                │
```

### 两条路径对比

| | 路径 A（LLM 发起） | 路径 B（前端发起） |
|--|------------------|------------------|
| 触发者 | LLM function-calling | 用户点击前端组件 |
| 入口 | `handle_event(event)` | `handle_gateway_event(data, session_id)` |
| 路由 | EventBus TOOL_INVOKE | Gateway 直调 |
| 组件 | 注册 + 持有等待 | 无需注册，直接处理输入 |
| 耗时 | 秒级（等用户） | 毫秒级（直接 publish） |

---

## 10. Session 生命周期

```
┌──────────┐    WS 连接     ┌───────────┐
│  空闲     │ ───────────→  │ 活跃       │
│ (无连接)  │               │ (ws 在线)  │
└──────────┘               └─────┬─────┘
     ▲                           │
     │   超时 / 手动清理          │ WS 断开
     │                           ▼
     │                    ┌───────────┐
     └────────────────────│ 重连等待   │
        超时 / 清理        │ (可重连)   │
                          └───────────┘
```

| 状态 | 说明 | 清理 |
|------|------|------|
| 空闲 | 无连接，无 session | — |
| 活跃 | WS 连接中 | — |
| 重连等待 | WS 断开，session 保留 | 超时后清理 ContextManager + 所有组件 |

Session 清理时，`ComponentManager.cleanup_session()` 会取消所有等待中的组件 Future，避免 Tool 永远挂起。

---

## 11. 实现计划

```
Phase 1 (当前) — 最小可用 Gateway
├── FastAPI + WebSocket /ws/{session_id}
├── 文本消息 → AGENT_MESSAGE_INCOMING
├── AGENT_OUTPUT/TOOL_RESULT 订阅 → 推 WS
├── GatewayComponentManager（注册 + 回调 + 更新）
├── NullComponentManager（兜底）
├── session 自动创建
└── user_input 工具改为使用 component_manager

Phase 2 — 丰富组件能力
├── 组件 schema 扩展（input / select / confirm / file_picker）
├── component_destroy 生命周期管理
├── cancel 支持（取消当前推理）
├── StdioComponentManager（CLI 模式）
└── 流式输出（text_stream mode）

Phase 3 — 生产增强
├── REST /api/settings
├── 断线重连 + session 持久化
├── 流式输出（text_stream mode）
├── 多传输层（SSE / Webhook）
└── 可观测性
```

---

## 12. 文件结构

```
src/tclaw/gateway/
├── __init__.py
├── app.py                    ← FastAPI 应用 + 路由定义
├── gateway.py                ← Gateway 主类
├── component_manager.py      ← ComponentManager 抽象 + GatewayComponentManager
│                               + NullComponentManager + StdioComponentManager
├── models.py                 ← 消息模型 / 协议类型定义
├── session.py                ← Session 生命周期管理
├── exceptions.py             ← ComponentNotSupported, ComponentTimeout 等
└── transports/
    ├── __init__.py           ← Transport 基类
    ├── websocket.py          ← WebSocket 传输适配器
    ├── sse.py                ← SSE 传输适配器
    └── stdio.py              ← CLI 传输适配器
```
