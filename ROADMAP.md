# tclaw 项目历程

> **v0.2 — Gateway + Frontend**

---

## ✅ v0.2 已完工

### 基础设施
- 项目骨架 + uv 虚拟环境 + Git
- `pyproject.toml` + `requirements.txt`
- `settings.py` — 全局配置常量（环境变量驱动）
- 文件日志（DEBUG）+ 终端日志（INFO），按时间戳分文件

### 事件系统
- `Event` 核心数据结构 + `Topics` 常量
- `EventBus` — 按 session 分队列，LLM 循环内嵌
- `Tool` 基类 — topic 自动派生，构造时注册
- 热加载：`bus.reload_user_tools()`
- 生命周期事件：`tool.completed.{tool_id}`（Tool 执行完毕广播）

### 系统模块（Mod）
- `Mod` 基类 — 与 Tool 分离，不暴露给 LLM
- 纯事件订阅：在 `__init__` 里订阅感兴趣的事件
- 自动扫描发现：`src/tclaw/mods/` 目录
- 内置示例：`sample` mod（演示 user_input 钩子）

### Gateway（Phase 1）
- **FastAPI + WebSocket** — ws://host:port/ws/{session_id}
- **SessionManager** — 连接生命周期、断线重连、过期清理
- **ComponentManager** — 注册/等待/回调/销毁组件
- **FrontendService** — 统一前端通信层，Tool 不直接碰 Gateway
- 消息路由：用户文本→LLM / tool_event→Tool 直调 / component_callback→组件

### 前端
- 两页设计：登录页（WS URL + Session ID）→ 连接后主界面
- 侧边栏布局：聊天 / 概览 / 实例 / Skills 标签切换
- 工具卡片显示（tool_start / tool_result）
- 动态组件（quiz 等 iframe 组件 + built-in select/confirm/input）
- 会话恢复：WS 重连时恢复历史消息（只恢复人话，跳过 tool 内部交互）
- 日志面板：实时 tail 后端日志
- session 概览：会话列表与统计

### 内置工具（10 个）
| 工具 | 功能 |
|------|------|
| `exec` | CLI 执行（return / no_return，默认 60s 超时） |
| `read` | 文件阅读（offset/limit/截断/图片） |
| `write` | 文件写入（覆盖/追加） |
| `edit` | 文件精确替换 |
| `output` | 输出给用户（text / figure / end） |
| `user_input` | 用户输入转发 + 文件上传 |
| `memory_search` | FTS5 全文搜索记忆 |
| `memory_get` | 读取记忆文件 |
| `load_skill` | 按需加载完整 SKILL.md |
| `quiz` | 交互式选择题（服务端驱动 UI） |

### 上下文管理
- `ContextManager` — workspace 文件 + skills 菜单 + 环境信息 + 每日笔记 → system prompt
- `_prelude` 区（skill 注入，对话前） + `_history`（对话历史）
- 环境信息自动注入：工作区路径、会话目录、技能目录等
- `compact(llm)` — 用 LLM 压缩历史
- 会话持久化：`logs/sessions/{session_id}.json`
- 对话记录：`logs/conversations/session_{id}.md`

### 记忆系统
- SQLite 索引（meta / files / chunks / fts5 / embedding_cache）
- 自動注入今日 + 昨日每日笔记

### LLM 客户端
- OpenAI 兼容 API（DeepSeek 默认）
- `finish_reason="length"` 自动续写
- 多 tool_calls 并行处理（deferred pending 检查）

### 技能体系
- 两阶段加载：YAML 头部菜单 → `load_skill` 读完整内容
- 标准目录结构：SKILL.md / scripts / references / assets / setup.sh

### 网络服务
- FileBrowser 文件管理器（:8080）
- SSH 隧道（autossh）转发 Gateway（:18789）和 FileBrowser（:8080）

---

## 🚧 进行中 / 待打磨

- 侧边栏各标签（概览、实例、Skills）具体内容
- 动态组件 iframe 高度自适应
- exec no_return 后台任务跟踪
- Tool 运行时热插拔

---

## 📋 已讨论但尚未实现

### 网关
- 信道抽象（Discord / Telegram / WebChat）
- 多 Agent 路由
- cancel 取消推理

### 后端
- 会话存储（文件 → 数据库）
- 用户管理 / 配置管理

### 更多工具
- `SearchTool` / `FetchTool` / `ProcessTool`

### 架构
- 外部队列（Redis / NATS）
- 可观测性（日志/指标/链路追踪）
- 安全 / 沙箱
- API 兼容层

---

*最后更新：2026-05-11 · v0.2*
