# tclaw 项目历程

> 下一代 OpenClaw — AI Agent 网关与后端

---

## ✅ 已完工

### 基础设施
- [x] Python 项目骨架（pyproject.toml, src/tclaw/ 包结构）
- [x] uv 虚拟环境（Python 3.11.15）
- [x] Git 初始化 + 项目级 git config

### 事件系统
- [x] `Event` 核心数据结构 + `Topics` 常量（含 AGENT_OUTPUT）
- [x] `EventBus` — 按 session 分队列的订阅/发布总线 + LLM 循环内嵌
- [x] `Tool` 基类 — topic 自动派生，构造时注册到总线
- [x] `tools/__init__.py` — 自动发现 + 导出 ALL_TOOLS

### 内置工具（每个 tool 一个文件夹，含 __init__.py + TOOL.md）
- [x] `exec/` — CLI 执行（return 带 timeout / no_return 后台）
- [x] `read/` — 文件阅读（offset/limit/截断提示/图片）
- [x] `write/` — 文件写入（覆盖/追加/自动建父目录）
- [x] `edit/` — 文件编辑（精确替换/唯一性检查）
- [x] `output/` — 输出给用户（text/figure 两种模式）
- [x] `user_input/` — 用户输入转发
- [x] `end/` — TOOL.md 仅作参考，EventBus 内拦截

---

## 🏗️ 存根（接口就绪，功能待补）

以下文件的**外部接口和调用路径已完整**，但内部实现是占位符，需要后续填入真实逻辑：

- [ ] `LLMClient` — `chat()` 返回固定文本，未接入真实 LLM API
- [ ] `ContextManager` — `build_context()` 未实现上下文截断/记忆注入/system prompt
- [ ] `UserInputTool` — TOOL_INVOKE → AGENT_MESSAGE_INCOMING 已通，前端输入通道待实现
- [ ] `OutputTool` — TOOL_INVOKE → AGENT_OUTPUT + AGENT_TOOL_RESULT 已通，前端推送通道待实现

---

## 🚧 进行中 / 待打磨

- [ ] `UserInputTool` 后端路由 — 用户端到 tool 的完整链路
- [ ] Tool 热插拔 — 运行时添加/移除工具

---

## 📋 已讨论但尚未实现

### 网关
- [ ] 网关 HTTP/WS 服务入口（FastAPI？）
- [ ] 信道（channel）抽象 — Discord / Telegram / WebChat 等
- [ ] 多 Agent 路由
- [ ] session 持久化

### 后端
- [ ] 会话存储（内存 → 数据库）
- [ ] 用户管理
- [ ] 配置管理
- [ ] 插件/Skill 加载机制（借鉴但不依赖 OpenClaw）
- [ ] Workspace 文件体系

### 工具（待补）
- [ ] `SearchTool` — 网页搜索
- [ ] `FetchTool` — 网页抓取
- [ ] `ProcessTool` — 后台进程管理
- [ ] 更多按需

### 架构
- [ ] 外部队列支持（Redis / NATS 等 EventBus 后端）
- [ ] 可观测性（日志/指标/链路追踪）
- [ ] 安全/沙箱机制
- [ ] API 兼容层（OpenAI / OpenClaw 兼容接口）

---

## 💡 设计笔记

**为什么要用 Event 模式而不是 OpenClaw 的 Messenger/Router/Session 管线？**
- 松耦合：Tool 不依赖 AgentLoop，AgentLoop 不依赖具体 Tool 实现
- 可插拔：新功能只需写一个 Tool 子类，无需改核心流程
- 统一循环：不分步骤事件类型，tool 进入→上下文整理→LLM→tool/回复 单一闭环

**按 session 分队列的原因**
- 不同 session 互不阻塞
- 同一 session 内严格 FIFO，不乱序
- 天然支持多用户并发

**动态 topic 派生**
- `Topics.TOOL_INVOKE` = `"tool.invoke"`
- 每个工具 topic 自动为 `"tool.invoke.{tool_id}"`
- 新工具无需改 events.py，只需声明 tool_id

---

*最后更新：2026-05-07*
