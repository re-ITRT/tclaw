# Gateway 直连 Tool 改造 —— 详细步骤

> 目标：Gateway 不碰 EventBus，前端和 LLM 完全通过 Tool 中转。

---

## 总览

```
改前            改后
Gateway          Gateway
├── subscribe(AGENT_OUTPUT)   ❌ 删掉
├── subscribe(TOOL_RESULT)    ❌ 删掉
├── publish(AGENT_MESSAGE)    ❌ 删掉（text 交给 tool）
└── _send_to_session()        → send() 公开方法给 Tool 调
```

```
Tool             Tool
├── _bus         ✅ 保留（调 LLM）
└── _gateway     ✨ 新增（推前端）
```

---

## Step 1 — Gateway 加 `send()` 公开方法

**gateway.py**，把 `_send_to_session` 改成公开方法：

```python
# 原：async def _send_to_session(self, session_id, data):
# 改：async def send(self, session_id, data):
#      component_manager.py 里全部改用 self._gateway.send()

async def send(self, session_id: str, data: dict) -> None:
    """推消息到前端。Tool 直接调这个方法发数据给用户。"""
    await self.sessions.send(session_id, data)
```

同时把 `component_manager.py` 里的 `self._gateway._send_to_session(` 全部改为 `self._gateway.send(`。

---

## Step 2 — Tool 基类加 `send_to_frontend()`

**tool.py**，构造时存 gateway 引用，加推送方法：

```python
class Tool(ABC):
    def __init__(self, bus):
        self._bus = bus
        self._gateway = getattr(bus, '_gateway', None)  # Gateway 可能不存在
        ...

    async def send_to_frontend(self, session_id: str, data: dict) -> None:
        """推消息到前端。不经过 EventBus，Tool 直连 Gateway。"""
        if self._gateway:
            await self._gateway.send(session_id, data)
```

所有现有的 `self.publish(AGENT_OUTPUT)` 可以根据情况改为 `self.send_to_frontend()`。

---

## Step 3 — Gateway 取消 EventBus 订阅

**gateway.py**，移除 `__init__` 里的两行订阅：

```python
# 删掉这两行：
bus.subscribe(Topics.AGENT_OUTPUT, self._on_output)
bus.subscribe(Topics.AGENT_TOOL_RESULT, self._on_tool_result)

# 删掉这两个方法：
async def _on_output(self, event): ...
async def _on_tool_result(self, event): ...
```

Gateway 不再从 EventBus 收消息。前端所有内容都由 Tool 直接推送。

---

## Step 4 — 改 `output` tool

**tools/output/__init__.py**，原来 publish `AGENT_OUTPUT` 给 Gateway 订阅，现在直接推前端：

```python
# 原来：
await self.publish(Event(topic=Topics.AGENT_OUTPUT, payload=...))
await self.reply_to_llm(...)

# 改成：
await self.send_to_frontend(event.session_id, {
    "type": "assistant",
    "mode": mode,
    "content": ...,
})
await self.reply_to_llm(...)
```

注意 `type: "assistant"` 原来是在 `_on_output` 里加的，现在 Tool 自己加。

---

## Step 5 — 改 `user_input` tool 接管文本消息

**gateway.py**，`_handle_text` 不再 publish 到 EventBus，改成调 tool：

```python
# 原来：
async def _handle_text(self, data, session_id):
    await self.bus.publish(Event(
        topic=Topics.AGENT_MESSAGE_INCOMING, ...))

# 改成：
async def _handle_text(self, data, session_id):
    tool = self.bus.get_tool("user_input")
    if tool:
        await tool.handle_gateway_event(data, session_id)
```

**user_input tool** 的 `handle_gateway_event` 处理文本消息：

```python
class UserInputTool(Tool):
    async def handle_gateway_event(self, data: dict, session_id: str):
        """前端文本消息 → 记入历史 → 触发 LLM"""
        text = data.get("content", "")
        files = data.get("files", [])
        
        # 文件处理（同原来）
        saved_paths = ...
        
        # 触发 LLM
        await self.publish(Event(
            topic=Topics.AGENT_MESSAGE_INCOMING,
            payload={"text": text, "file_path": saved_paths},
            source=self.tool_id,
            session_id=session_id,
        ))
```

user_input 本身的 `handle_event` 保持不变（LLM 也可以主动调它）。

---

## Step 6 — 测试与清理

重启验证：
1. 发文本消息 → Gateway → user_input.handle_gateway_event → EventBus → LLM → LLM 回复
2. LLM 回文本 → output tool → send_to_frontend → 前端显示
3. LLM 调工具 → TOOL_INVOKE → tool 执行 → reply_to_llm/推前端
4. 组件回调 → resolve_callback → handle_gateway_event → 存 prelude/调 LLM

验证没有回归后，清理：
- 删掉 `gateway.py` 的 `_on_output`、`_on_tool_result`
- 删掉 `events.py` 里不再用的 topic
- 更新 `ARCHITECTURE.md` 和 `docs/gateway.md`

---

## 变更清单

| 文件 | 改动 |
|------|------|
| `gateway/gateway.py` | `_send_to_session` → `send()`；删 subscription；`_handle_text` 调 tool |
| `gateway/component_manager.py` | `_send_to_session` → `send()` |
| `common/tool.py` | 加 `_gateway`、`send_to_frontend()` |
| `tools/output/__init__.py` | `publish(AGENT_OUTPUT)` → `send_to_frontend()` |
| `tools/user_input/__init__.py` | 加 `handle_gateway_event()` 处理文本 |
| `ARCHITECTURE.md` | 更新架构图 |
| `docs/gateway.md` | 更新设计文档 |

不影响：其余 9 个工具（exec/edit/read/write/compact/load_skill/memory_*/quiz），它们只调 `reply_to_llm`（走 EventBus），不改。
