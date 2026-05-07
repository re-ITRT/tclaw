# tclaw 项目历程

> **v0.1 — Phase Zero: Engine**

---

## ✅ v0.1 已完工

### 基础设施
- 项目骨架 + uv 虚拟环境 + Git
- `pyproject.toml` + `requirements.txt`
- `settings.py` — 全局配置常量（环境变量驱动）

### 事件系统
- `Event` 核心数据结构 + `Topics` 常量
- `EventBus` — 按 session 分队列，LLM 循环内嵌
- `Tool` 基类 — topic 自动派生，构造时注册
- 热加载：`bus.reload_user_tools()`

### 内置工具（11 个）
| 工具 | 功能 |
|------|------|
| `exec` | CLI 执行（return / no_return） |
| `read` | 文件阅读（offset/limit/截断/图片） |
| `write` | 文件写入（覆盖/追加） |
| `edit` | 文件精确替换 |
| `output` | 输出给用户（text / figure / end） |
| `user_input` | 用户输入转发（前端存根） |
| `memory_search` | FTS5 全文搜索记忆 |
| `memory_get` | 读取记忆文件 |
| `load_skill` | 按需加载完整 SKILL.md |
| `compact` | LLM 自主压缩上下文 |
| `session_comm` | 跨 session 通信（用户示例） |

### 上下文管理
- `ContextManager` — workspace 文件 + skills 菜单 + 今日笔记 → system prompt
- `_prelude` 区（skill 注入，对话前） + `_history`（对话历史）
- `compact(llm)` — 用 LLM 压缩历史
- `truncate(N)` — 丢弃最早轮次

### 记忆系统
- SQLite 索引（meta / files / chunks / fts5 / embedding_cache）
- `memory_reader` — 共享层，ContextManager 和 tool 共用
- 自动注入今日每日笔记

### LLM 客户端
- OpenAI 兼容 API（DeepSeek 默认）
- `finish_reason="length"` 自动续写
- `max_tokens` 模型级别配置

### 技能体系
- 两阶段加载：YAML 头部菜单 → `load_skill` 读完整内容
- 标准目录结构：SKILL.md / scripts / references / assets / setup.sh
- 热加载：新增 skill 即时生效

### Workspace
- MEMORY / SOUL / USER / IDENTITY / TOOLS / HEARTBEAT
- `daily/` 每日笔记 / `skills/` 技能 / `uploads/` 上传

---

## 🚧 进行中 / 待打磨

- `UserInputTool` 后端路由 — 前端输入通道
- `OutputTool` 前端推送通道
- Tool 运行时热插拔生命周期

---

## 📋 已讨论但尚未实现

### 网关
- HTTP/WS 服务入口（FastAPI？）
- 信道抽象（Discord / Telegram / WebChat）
- 多 Agent 路由
- session 持久化

### 后端
- 会话存储（内存 → 数据库）
- 用户管理 / 配置管理
- 插件/Skill 加载机制

### 更多工具
- `SearchTool` / `FetchTool` / `ProcessTool`

### 架构
- 外部队列（Redis / NATS）
- 可观测性（日志/指标/链路追踪）
- 安全/沙箱
- API 兼容层

---

*最后更新：2026-05-07 · v0.1*
