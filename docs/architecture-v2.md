# tclaw 架构重构 —— Gateway 直连 Tool，EventBus 仅做 LLM 调度

## 现状问题

```
前端 ──WS──→ Gateway ──publish──→ EventBus ──→ LLM 循环
                │                      ↑
                │ subscribe ───────────┘
                │
                └──→ Tool.handle_gateway_event()
```

Gateway 同时和 EventBus、Tools 耦合。组件回调走：
`component_callback → resolve_callback → _route_non_blocking → handle_gateway_event → publish(AGENT_MESSAGE_INCOMING) → EventBus 队列 → pending 检查 → _run_llm_loop`

绕过三圈，每圈都有冲突可能。

## 新架构

```
前端 ──WS──→ Gateway ───→ Tools
                  ↑            │
                  │            ├──→ EventBus → LLM 循环（工具决定何时触发）
                  │            │
                  └─────── 推前端（工具直接调）
```

**Gateway 只连接前端和 Tools，不碰 EventBus。**

| 现在 | 改成 |
|------|------|
| Gateway 直接 publish(AGENT_MESSAGE_INCOMING) | Gateway 调 user_input.handle_gateway_event() |
| Gateway subscribe(AGENT_OUTPUT) 推前端 | Tool 用 `self._gateway.send()` 推前端 |
| Gateway subscribe(AGENT_TOOL_RESULT) 推前端 | Tool 自己推 |
| resolve_callback → EventBus | resolve_callback → handle_gateway_event（已实现） |

## Gateway 新职责

```
WS:text         → user_input.handle_gateway_event(data, session_id)
WS:tool_event   → tool.handle_gateway_event(data, session_id)
WS:callback     → component_manager.resolve_callback(cid, result)
                   ├─ blocking → Future.set_result（Tool 在 EventBus 那边等）
                   └─ non-blocking → _route_non_blocking(binding, result)
                                     → handle_gateway_event()
WS:cancel       → Gateway 自己处理
WS:reset        → Gateway 自己处理

推前端：
  tools/gateway.py 暴露 send(session_id, data) 给 Tool
  Tool 直接调 self._gateway.send() 推消息
  不再通过 EventBus 订阅
```

## EventBus 新职责

只做三件事：
1. 接收 Tool 发的 `AGENT_MESSAGE_INCOMING` → LLM 循环
2. 接收 Tool 发的 `AGENT_TOOL_RESULT` → 记历史 + 触发 LLM
3. 分发 `TOOL_INVOKE` 给对应 Tool

EventBus 不再知道前端的存在。Gateway 不再知道 EventBus 的存在。

## Tool 的新能力

Tool 现在有三个入口，对应三个来源：

| 入口 | 来源 | 用途 |
|------|------|------|
| `handle_event(event)` | EventBus（LLM 调 tool） | 干活、注册组件、调 LLM |
| `handle_gateway_event(data, session_id)` | Gateway（前端交互） | 处理回调、推前端、调 LLM |
| `send(session_id, data)` | Tool 自己调 | 推消息到前端 |

Tool 需要能调 EventBus 发事件（publish），也需要能调 Gateway 推前端（send）。

## 组件回调新流程（non-blocking）

```
用户点选项 → iframe → postMessage → 前端 → WS:component_callback
    ↓
Gateway.resolve_callback()
    ↓ binding.blocking == False
_route_non_blocking() → handle_gateway_event()
    ├─ add_to_prelude() → 存结果到上下文
    ├─ destroy_component() → 关窗口
    └─ 可选：publish(AGENT_MESSAGE_INCOMING) → 触发 LLM
       （Tool 自己决定要不要触发、何时触发）
```

没有 pending 检查，没有队列冲突。Tool 可以直接调用 EventBus 触发 LLM，也可以不调等下次用户消息。

## 迁移步骤

1. Gateway 不再 subscribe AGENT_OUTPUT / AGENT_TOOL_RESULT
2. 加 `Gateway.send(session_id, data)` 公开方法
3. Tool 基类的 `publish(event)` 保留（走 EventBus）
4. Tool 基类新增 `_gateway` 引用（注册时注入）
5. 改 user_input：前端文本走 handle_gateway_event，内部 publish 到 EventBus
6. 改 output：直接调 `self._gateway.send()` 推前端
7. 其他工具：如果有 AGENT_OUTPUT 推送的，改走 Gateway
