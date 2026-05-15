# tclaw 开发文档

> 面向 Tool、Extension 和 Skill 开发者

---

## 目录

1. [Tool 开发](#1-tool-开发)
2. [Extension 开发](#2-extension-开发)
3. [Skill 开发](#3-skill-开发)
4. [最佳实践](#4-最佳实践)
5. [API 参考](#5-api-参考)

---

## 1. Tool 开发

Tool 是 LLM 可见的功能单元。每个 tool 是一个文件夹，自动发现。

### 目录结构

```
src/tclaw/tools/{tool_name}/
├── __init__.py      ← 代码 + 参数 schema
└── TOOL.md          ← LLM 看到的说明文档
```

### 最小 Tool

```python
"""MyTool —— 示例工具。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ...common.tool import Tool

if TYPE_CHECKING:
    from ...common.event_bus import EventBus


class MyTool(Tool):
    tool_id = "my_tool"

    # LLM function-calling 参数 schema
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "要问候的名字",
            },
        },
        "required": ["name"],
    }

    async def do_execute(self, payload: dict) -> None:
        """LLM 调此工具时的入口。payload 包含参数。"""
        name = payload.get("name", "")
        sid = payload.get("session_id", "")

        # 做你的逻辑
        result = f"你好，{name}！"

        # 把结果返回给 LLM
        await self.reply_to_llm({"status": "ok", "message": result}, sid)
```

### TOOL.md 写法

```markdown
# my_tool — 问候工具

向用户打招呼。

## 参数

- `name` — 要问候的名字

## 返回值

返回问候语。
```

### 完整 Tool 生命周期

```
LLM 决定调此 tool
    ↓
EventBus publish("tool.invoke.{tool_id}")
    ↓
_session_worker → _route_to_handlers
    ↓
Tool._on_invoke(event)
    ├── send_to_frontend("tool_start")    ← 前端显示工具卡片
    ├── execute(payload)
    │   ├── dispatch_sync(":before")      ← 扩展可拦截
    │   ├── do_execute(payload)           ← 你的逻辑
    │   └── dispatch_sync(":after")       ← 扩展可响应
    └── send_to_frontend("tool_result")   ← 前端更新卡片
    ↓
reply_to_llm(result, session_id)
    ↓
EventBus publish("agent.tool.result")
    ↓
LLM 继续推理
```

### 关键方法

| 方法 | 用途 |
|------|------|
| `do_execute(payload)` | 实现核心逻辑。必须重写。 |
| `reply_to_llm(dict, session_id)` | 把结果返回给 LLM。 |
| `send_to_frontend(session_id, data)` | 推消息到前端。 |
| `register_component(session_id, schema)` | 注册交互组件（如 quiz）。 |
| `wait_for_component(component_id)` | 等待用户交互（blocking 模式）。 |
| `update_component(component_id, data)` | 更新组件状态。 |
| `destroy_component(component_id)` | 销毁组件。 |

### Tool 可以使用的事件

通过 `self._bus.subscribe()` 监听其他事件。

### 交互式组件（如选择题）

参考 `src/tclaw/tools/quiz/`。组件可以是：
- **built-in**：前端用 JavaScript 渲染（select / confirm / input）
- **iframe**：工具目录下的 `component/index.html`，通过 `postMessage` 通信

---

## 2. Extension 开发

Extension 是系统钩子/中间件，不暴露给 LLM。通过订阅 EventBus 事件工作。

### 目录结构

```
src/tclaw/extensions/{ext_id}/
└── __init__.py
```

### 最小 Extension

```python
"""AuditExtension —— 审计扩展。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ...common.extension import Extension
from ...common.events import Topics

if TYPE_CHECKING:
    from ...common.event_bus import EventBus

logger = logging.getLogger("tclaw.extensions.audit")


class AuditExtension(Extension):
    ext_id = "audit"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        # 订阅 exec 工具的 after 事件
        bus.subscribe("tool.invoke.exec:after", self._on_exec)
        logger.info("audit extension active")

    async def _on_exec(self, event: dict) -> None:
        """exec 工具执行完毕后触发。"""
        payload = event.get("payload", {})
        cmd = payload.get("command", "")
        sid = payload.get("session_id", "")
        logger.info("[audit] session=%s exec=%s", sid, cmd[:100])
```

### Extension 可以做的事

| 能力 | 说明 |
|------|------|
| 订阅事件 | `bus.subscribe("tool.invoke.{id}:before/after", handler)` |
| 推前端 | `self.send_to_frontend(sid, data)` |
| 注册组件 | `self.register_component(sid, schema)` |
| 访问总线 | `self._bus` |
| 访问 Gateway | `self._gateway`（如果有） |

### 常用订阅事件

| 事件 | 触发时机 |
|------|---------|
| `tool.invoke.{id}:before` | tool 执行前（可取消） |
| `tool.invoke.{id}:after` | tool 执行后 |
| `tool.invoke.output:after` | LLM 输出后 |
| `agent.message.incoming` | 用户消息到达 |
| `agent.tool.result` | tool 返回结果 |
| `system.startup` | EventBus 启动 |

### 参考实现

- `src/tclaw/extensions/compactor/` — 上下文压缩
- `src/tclaw/extensions/usage/` — Token 用量统计
- `src/tclaw/extensions/sample/` — 示例钩子

---

## 3. Skill 开发

Skill 是 AgentSkills 兼容的技能包，教 LLM 如何使用工具。

### 目录结构

```
workspace/skills/{skill_name}/
├── SKILL.md          ← 功能说明书（Markdown + YAML 头部）
├── scripts/          ← 执行脚本（可选）
├── references/       ← 详细参考文档（可选）
├── assets/           ← 模板、图片等静态资源（可选）
└── setup.sh          ← 环境依赖安装脚本（可选）
```

### SKILL.md 格式

```markdown
---
name: my-skill
description: 技能描述，一句话说明功能
---

# My Skill

这里写完整的技能说明。LLM 通过 `load_skill` 加载此文件后能看到全部内容。

## 用法

### 子命令 1

用 `read` 工具读取配置文件。

### 子命令 2

用 `exec` 工具执行以下命令：

```bash
echo hello
```
```

### YAML 头部字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 技能名称，用于菜单显示 |
| `description` | 是 | 一句话描述，出现在技能菜单中 |

### 两阶段加载

1. **菜单** — `SKILL.md` 的 YAML `description` 自动注入 system prompt
2. **完整加载** — LLM 通过 `load_skill(name="{skill_name}")` 按需读取完整内容

### 安装方式

将技能文件夹放入 `workspace/skills/` 即可。技能开关可在前端 Skills 标签控制。

---

## 4. 最佳实践

### Tool

- `do_execute` 必须返回 `reply_to_llm`，否则 LLM 永远等不到结果
- `payload` 里一定有 `session_id`，用 `payload.get("session_id", "")` 获取
- 耗时操作用 `asyncio.to_thread()` 放到后台线程，避免阻塞 EventBus worker
- `_result(args, result)` 中 `args` 有 `session_id`，`result` 没有。用 `args.get("session_id")` 获取
- 工具应该尽快调用 `reply_to_llm`，不要长时间阻塞

### Extension

- `__init__` 里订阅事件，不要在 handler 里重复订阅
- handler 是异步方法，用 `async def` 定义
- 修改 `payload` 可以影响后续处理（如设置 `cancelled=True`）
- 持久化数据存到 `workspace/` 下的 `.json` 文件

### Skill

- 描述要清晰具体，让 LLM 一眼知道什么时候该用
- 提供具体示例（命令、代码片段）
- 不要写 TOOL.md 格式的描述——那是给 tool 用的，不是技能
- 技能可以引用 tclaw 的内置 tool（exec, read, write 等）

---

## 5. API 参考

### ToolBase API

```python
class Tool(Executable):
    tool_id: str                     # 工具标识，LLM 用此名称调用
    parameters: dict                 # OpenAI function-calling schema

    async def do_execute(self, payload: dict) -> None:  # 必须重写
    async def reply_to_llm(self, result: dict, session_id: str) -> None:
    async def send_to_frontend(self, session_id: str, data: dict) -> None:
    async def register_component(self, session_id: str, schema: dict) -> str:
    async def wait_for_component(self, component_id: str, timeout=None):
    async def update_component(self, component_id: str, data: dict) -> None:
    async def destroy_component(self, component_id: str) -> None:
```

### ExtensionBase API

```python
class Extension(Executable):
    ext_id: str                      # 扩展标识

    def __init__(self, bus: EventBus):
    async def send_to_frontend(self, session_id: str, data: dict) -> None:
    async def register_component(self, session_id: str, schema: dict) -> str:
```

### 事件格式

```python
event = {
    "topic": "tool.invoke.read",     # 事件类型
    "payload": {                     # 数据
        "path": "test.txt",
        "session_id": "main",
        ...
    },
    "session_id": "main",            # 目标 session
}
```

### 前端通信格式

```python
# 发送到前端的消息格式
await self.send_to_frontend(sid, {
    "type": "assistant",             # 聊天气泡
    "content": "回复内容",
})
await self.send_to_frontend(sid, {
    "type": "system",                # 系统通知
    "content": "通知内容",
})
await self.send_to_frontend(sid, {
    "type": "tool_start",            # 工具卡片
    "tool_id": "exec",
    "args": {"command": "ls"},
})
```
