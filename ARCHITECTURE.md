# tclaw 架构文档

> v0.1 · 2026-05-08

---

## 总览

tclaw 是一个事件驱动的 AI Agent 框架。核心设计思路：

1. **事件驱动** — 一切皆事件，EventBus 是中枢神经
2. **Agent 作为内循环** — LLM 推理 + Tool 调用形成闭环，不依赖外部编排
3. **Gateway 作为边界 + 组件中心** — 前端接入通过 Gateway，交互组件也通过 Gateway 直连
4. **技能两阶段加载** — 菜单 ~100 tokens，完整内容按需读取

```
┌──────────┐               ┌──────────────────────────────────────┐
│  前端     │               │             Gateway                 │
│  WebChat │── WS:text ───→│  ──publish──→ EventBus ──→ LLM循环  │
│  Discord │               │                                      │
│  Telegram│←─ WS:push ────│  ←──subscribe── EventBus ←─ LLM/Tool│
│  CLI     │               │                                      │
│          │               │   ComponentManager（组件注册中心）     │
│  交互组件 │←─ WS:component│   ↑  register / wait / update       │
│  交互组件 │── WS:callback─│   │  Tool 直接调, 不走 EventBus     │
└──────────┘               └───┼──────────────────────────────────┘
                               │
                        ┌──────┴────────┐
                        │     Tools     │
                        │  (11 内置)     │
                        │  热加载        │
                        │  user_input   │  ← 交互组件直连 Gateway
                        │  output       │  ← 走 EventBus AGENT_OUTPUT
                        │  quiz 等      │
                        └───────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │    EventBus      │
                        │  订阅表           │
                        │  session 队列     │
                        │  LLM 循环调度     │
                        │  工具路由         │
                        └────┬──────────┬─┘
                            │          │
                            ▼          ▼
                    ┌─────────┐ ┌───────────┐
                    │Context  │ │LLMClient  │
                    │Manager  │ │(DeepSeek) │
                    │system   │ │自动续写    │
                    │prelude  │ │功能调用    │
                    │history  │ │           │
                    └─────────┘ └───────────┘
```

**三条路径，各司其职：**

| 路径 | 中介 | 用途 |
|------|------|------|
| 用户 ══文本══▶ 引擎 | **EventBus** publish | 对话消息、普通工具调用 |
| 引擎 ══回复══▶ 用户 | **EventBus** subscribe | LLM 回复、工具状态推送 |
| 工具 ══组件══▶ 用户 | **Gateway** 直连 | 交互组件注册/更新/回调 |

---

## 核心架构原则

### 1. 事件驱动，不耦合

| 不要做的事 | 正确的做法 |
|-----------|-----------|
| Gateway 直接调 LLM | Gateway 发布事件，EventBus 调度 |
| Tool 直接写前端 | 普通输出经 EventBus；交互组件经 Gateway ComponentManager |
| LLM 直接读写上下文 | ContextManager 构建，EventBus 管理生命周期 |

### 2. 按 Session 隔离

每个对话 session 拥有独立的：
- EventBus 队列（串行 FIFO）
- ContextManager（上下文 + 历史）
- Gateway 连接（WebSocket）
- 组件实例池

### 3. 信道无关

Gateway 不关心前端是什么协议。以及 ComponentManager 提供抽象，让 Tool 无需知道前端类型：

```
ComponentManager（抽象）
├── GatewayComponentManager  ← 有前端（WebSocket）
├── StdioComponentManager    ← CLI 模式
└── NullComponentManager     ← 无交互/后台
```

### 4. 工具作为一等公民

- 每个工具独立文件夹（`__init__.py` + `TOOL.md`）
- 普通工具通过 EventBus 交互
- 交互工具通过 `bus.component_manager` 直连 Gateway
- LLM 通过 function-calling 触发，Tool 通过 EventBus 发布结果回循环

---

## 模块分层

```
src/tclaw/
├── gateway/        ← 前端接入层 + 组件注册中心（当前实现中）
│   ├── gateway.py            — Gateway 主类
│   ├── component_manager.py  — 组件注册中心 + 多种实现
│   ├── session.py            — Session 生命周期
│   ├── models.py             — 消息协议
│   ├── exceptions.py         — 组件异常
│   └── transports/           — 信道适配器
│       ├── websocket.py
│       ├── sse.py
│       └── stdio.py
│
├── common/         ← 引擎核心层 ✅ 已完工
│   ├── event_bus.py       — 事件总线 + component_manager 持有人
│   ├── context_manager.py — 上下文管理
│   ├── llm_client.py      — LLM API 客户端
│   ├── tool.py            — Tool 基类
│   ├── events.py          — Event + Topics 定义
│   ├── skills.py          — 技能加载器
│   └── settings.py        — 全局配置
│
├── tools/          ← 内置工具 ✅ 已完工（11 个）
│   ├── compact/
│   ├── edit/
│   ├── exec/
│   ├── load_skill/
│   ├── memory_get/
│   ├── memory_search/
│   ├── output/
│   ├── read/
│   ├── session_comm/
│   ├── user_input/        ← 交互工具，调 bus.component_manager
│   └── write/
│
├── backend/        ← 后端服务（记忆索引等）
│   └── memory_reader.py
│
├── __init__.py
└── main.py         ← 启动入口
```

---

## 数据流

### 路径 A：LLM 调 Tool（handle_event → Gateway）

LLM 通过 function-calling 触发工具。Tool.handle_event() 干活，可选通过
ComponentManager 与前端交互。

```
LLM 循环
  │ publish(TOOL_INVOKE.{tool_id})
  ▼
EventBus → Tool.handle_event(event)
  │
  ├── ❶ 直接干活
  │   └── publish(AGENT_TOOL_RESULT) → LLM 继续
  │
  └── ❷ 需要前端交互
      │
      │ cm.register(session_id, schema)
      ├──▶ Gateway ── WS ──▶ 前端渲染组件
      │
      │ cm.wait_for_component(id)  ← 持有等待
      │                         用户操作 → WS → Gateway
      │ ◀───────── Future resolved ───────────┘
      │
      └── publish(AGENT_TOOL_RESULT) → LLM 继续
```

### 路径 B：前端调 Tool（handle_gateway_event → EventBus）

前端直接发送 tool_event，**不走 EventBus 排队**，Gateway 直调 Tool。

```
前端 ── WS:tool_event ──→ Gateway
  │ bus.get_tool(tool_id)
  ▼
Tool.handle_gateway_event(data, session_id)
  │
  ├── 处理前端输入（按钮点击、表单提交等）
  │
  └── publish(AGENT_TOOL_RESULT) → EventBus → LLM 循环继续
```

### 路径 C：普通消息流（用户 → LLM → 回复）

```
用户 ── WS:text ──→ Gateway
                       │ publish(AGENT_MESSAGE_INCOMING)
                       ▼
                   EventBus
                       │ _session_worker()
                       ▼
                  _run_llm_loop()
                       │
               ┌───────┴────────┐
               ▼                ▼
       ContextManager       Tool Specs
       .build_context()     .collect()
               │                │
               └────┬───────────┘
                    ▼
             LLMClient.chat()
                    │
               ┌────┴────┐
               ▼         ▼
        有 tool_call    无 tool_call
               │              │
               ▼              ▼
       publish(TOOL_INVOKE)   publish(AGENT_OUTPUT)
               │              │
           路径 A            Gateway → 前端
               │
        Tool.handle_event()
               │
        publish(AGENT_TOOL_RESULT)
               │
        _run_llm_loop(继续)
```

### 三条路径汇总

```
                    ┌──────────────────┐
                    │    Tool 基类       │
                    │                   │
  EventBus ────▶  handle_event()       │
       (LLM 调用)    │            │      │
                     │ 干活        │ 组件  │
                     │             ▼      │
                     │     ComponentManager
                     │       │ Gateway    │
                     ▼       ▼            │
  Gateway ───▶  handle_gateway_event()   │
  (前端交互)        │                     │
                     │                     │
                     ▼                     │
              publish(AGENT_TOOL_RESULT)   │
                     │                     │
                     ▼                     │
              EventBus → LLM 继续          │
                    └──────────────────────┘
```

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| LLM 循环 | EventBus 同步调度 | 简化模型，自然闭环 |
| 工具结果回传 | publish(AGENT_TOOL_RESULT) | 触发下一轮 LLM 循环 |
| 交互组件 | Gateway ComponentManager 直连 | Tool 需要持有等待，EventBus 不适合 |
| ComponentManager 抽象 | 接口 + 三种实现 | 前端/CLI/后台各得其所 |
| 信道 | WebSocket + Transport 抽象 | 可扩展，不硬编码 |
| 上下文压缩 | LLM 自压缩 | 保留语义 |
| 技能加载 | 两阶段（菜单→按需） | 节省 tokens |

---

## 演进路线

```
v0.1 ──→ v0.2 ──→ v0.3 ──→ v1.0
Engine    Gateway    Backend    Production
✅        🚧         📋         🔮
```

- **v0.1** ✅ — Phase Zero: Engine（已完工）
- **v0.2** 🚧 — Phase One: Gateway & ComponentManager（当前进行中）
- **v0.3** 📋 — Phase Two: Backend & Toolchain
- **v1.0** 🔮 — Production Ready

详见 [ROADMAP.md](./ROADMAP.md)
