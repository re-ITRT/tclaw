# tclaw 架构文档

> v2025.5.15.1 · 2026-05-15

---

## 总览

```
前端 (WebSocket)
     │
     ▼
Gateway ──→ Tool (直调) ──→ LLM 循环
     │
 FrontendService
     │
 EventBus ──→ Tool / Extension
     │
 Executable (execute 管道)
     │  ├── {topic}:before  (扩展可拦截/取消)
     │  ├── do_execute      (核心逻辑)
     │  └── {topic}:after   (扩展可响应)
     │
 ContextManager → LLMClient
```

tclaw 是一个事件驱动的 AI Agent 框架。核心设计思路：

1. **统一执行管道** — Tool 和 Extension 共用 `Executable` 基类，`execute()` 带 before/after 生命周期
2. **事件使用 dict** — `{"topic": str, "payload": dict}`，无 Event 数据类
3. **Gateway 直连 Tool** — 前端交互不走 EventBus，通过 FrontendService 直调 Tool
4. **EventBus 只做 LLM 调度** — 消息排队 + pending tool_calls 检查 + session 队列
5. **Server-Driven UI** — 前端纯渲染，组件注册/更新/销毁由服务端驱动

## 组件

### EventBus (`common/event_bus.py`)
- 按 session 分队列（`asyncio.Queue`），每个 session 独立 worker
- 事件格式：`{"topic": str, "payload": dict}`
- `publish()` — 异步排队
- `dispatch_sync()` — 同步分发（用于 before/after 生命周期）
- 订阅者通过 `subscribe(topic, handler)` 注册

### Executable (`common/executable.py`)
Tool 和 Extension 的共用基类，提供统一执行管道：

```python
async def execute(self, payload: dict) -> None:
    # 1. 检查 payload.cancelled
    # 2. dispatch_sync({topic}:before) → 订阅者可取消
    # 3. 检查 cancelled
    # 4. do_execute(payload)          ← 子类实现
    # 5. dispatch_sync({topic}:after)
```

所有前端通信方法也在这里：
- `send_to_frontend()` — 推消息到前端
- `register_component()` / `wait_for_component()` / `update_component()` / `destroy_component()`

### Tool (`common/tool.py`)
继承 `Executable`，额外提供：
- `tool_id` + `parameters` → LLM function-calling spec
- `TOOL.md` — 对 LLM 的自然语言描述
- `reply_to_llm()` — 快捷发布 `AGENT_TOOL_RESULT`
- `get_tool_spec()` — 生成 OpenAI 兼容的 tool definition

内置工具：exec, read, write, edit, output, user_input, memory_get, memory_search, load_skill, quiz

### Extension (`common/extension.py`)
继承 `Executable`，不暴露给 LLM：
- 纯事件驱动：在 `__init__` 里 `bus.subscribe()` 订阅感兴趣的事件
- 可用于审计、过滤、中转、通知等
- 自动发现：`src/tclaw/extensions/` 目录

### Gateway (`gateway/`)
FastAPI + WebSocket 服务：
- WebSocket 端点：`/ws/{session_id}`
- SessionManager — 连接生命周期、断线重连
- ComponentManager — 组件注册/等待/回调/销毁
- FrontendService — 统一前端通信层
- REST API：
  - `GET /api/tools` — 列出所有工具及描述
  - `GET /api/extensions` — 列出所有扩展
  - `GET /api/skills` — 列出 workspace skills
  - `GET /api/sessions` — 列出会话
  - `DELETE /api/sessions/{id}` — 删除会话

### ContextManager (`common/context_manager.py`)
构建 LLM 对话上下文，分四个区块：
1. 系统初始化：SOUL + 身份/用户/环境 + 记忆文件
2. 已加载技能（`_prelude`）
3. 对话历史（`_history`）
4. 技能菜单

### LLM 客户端 (`common/llm_client.py`)
- OpenAI 兼容 API（默认 DeepSeek）
- `finish_reason="length"` 自动续写
- 多 tool_calls 并行处理

## 数据流

### 用户发消息
```
前端 → WS:text → Gateway._handle_text()
  → user_input.handle_gateway_event()
  → publish(AGENT_MESSAGE_INCOMING)
  → EventBus session worker
  → _run_llm_loop()
  → LLM 推理
      ├── 回文本 → send_to_frontend({type:"assistant"})
      └── 调工具 → publish(tool.invoke.{id}) → Tool.execute()
                                                   ├── :before
                                                   ├── do_execute → reply_to_llm()
                                                   └── :after
```

### 组件交互
```
Tool.register_component()
  → frontend 渲染 iframe/builtin 组件
用户操作 → iframe postMessage → 前端 WS:component_callback
  → ComponentManager.resolve_callback()
      ├── blocking → future.set_result()
      └── non_blocking → Tool.handle_gateway_event() → publish(AGENT_MESSAGE_INCOMING)
```

### Extension 钩子
```
Tool.execute()  →  dispatch_sync({topic}:after)
                      → Extension._handler(event)  ← 订阅了此 topic
```

## 关键决策

| 决策 | 原因 |
|------|------|
| Event = dict，无数据类 | 解耦，生产者和消费者无需共享数据类型 |
| Gateway 直连 Tool | 前端交互低延迟，架构简单 |
| Executable 基类 | Tool 和 Extension 共用执行管道 |
| before/after 生命周期 | 可插拔的钩子系统，无需特殊接口 |
| Extension 与 Tool 分离 | 系统钩子不暴露给 LLM |
| Server-Driven UI | 前端只渲染，不做决策 |
| session 分队列 | 隔离性好，一个 session 卡住不影响其他 |
| 默认 60s exec 超时 | 防止 WSL2 文件系统扫描卡死 |
