# tclaw 项目历程

> **v0.2 — Gateway + Frontend + Extension 系统**

---

## ✅ v0.2 已完工

### 基础设施
- 项目骨架 + uv 虚拟环境 + Git
- `pyproject.toml` + `requirements.txt`
- `settings.py` — 全局配置常量（环境变量驱动）
- 文件日志（DEBUG）+ 终端日志（INFO），按时间戳分文件

### 事件系统
- 事件格式统一为 `{"topic": str, "payload": dict}`
- `Topics` 常量类集中管理所有 topic
- `EventBus` — 按 session 分队列，异步处理
- session_id 智能路由：同时支持事件顶层和 payload 内两种写法

### Executable 执行管道
- `Executable` 基类 — Tool 和 Extension 共用
- 统一 `execute(payload)` 入口，带完整生命周期

```python
execute(payload)
  ├── check cancelled
  ├── publish({topic}:before)  → 订阅者可取消
  ├── check cancelled
  ├── do_execute(payload)      → 实际逻辑
  └── publish({topic}:after)   → 订阅者做后续处理
```

- `dispatch_sync()` — 同步分发 before/after 事件（不入队列）
- Extension 和 Tool 共用 `send_to_frontend()`、`register_component()` 等方法

### Tool 系统
- `Tool` 基类 — 继承 `Executable`，额外提供 TOOL.md、LLM function-calling spec
- 每个工具占一个文件夹（`__init__.py` + `TOOL.md`）
- 自动扫描发现：`src/tclaw/tools/` 目录

| 工具 | 功能 |
|------|------|
| `exec` | CLI 执行（return / no_return，默认 60s 超时） |
| `read` | 文件阅读（offset/limit/截断/图片） |
| `write` | 文件写入（覆盖/追加） |
| `edit` | 文件精确替换 |
| `output` | 输出给用户：`text` / `figure` / `end` 三种模式 |
| `user_input` | 用户输入转发 + 文件上传 |
| `memory_search` | FTS5 全文搜索记忆 |
| `memory_get` | 读取记忆文件 |
| `load_skill` | 按需加载完整 SKILL.md |
| `quiz` | 交互式选择题（blocking / non_blocking 模式） |

### Extension 系统
- `Extension` 基类 — 继承 `Executable`，不暴露给 LLM
- 纯事件驱动：在 `__init__` 里订阅感兴趣的事件
- 自动扫描发现：`src/tclaw/extensions/` 目录
- 内置示例：`sample`（监听 exec:after）、`output_plugin`（监听 output:after）

### Gateway（Phase 1）
- **FastAPI + WebSocket** — ws://host:port/ws/{session_id}
- **SessionManager** — 连接生命周期、断线重连、过期清理
- **ComponentManager** — 注册/等待/回调/销毁组件
- **FrontendService** — 统一前端通信层
- 消息路由：用户文本→LLM / tool_event→Tool 直调 / component_callback→组件

### 前端
- 两页设计：登录页（仅 WS URL）→ 连接后主界面
- session 选择器：下拉切换会话、新建会话、删除会话（main 不可删）
- 侧边栏布局：聊天 / 概览 / 实例 / Skills 标签切换
- 工具卡片显示（tool_start / tool_result）
- 动态组件（quiz 等 iframe 组件 + built-in select/confirm/input）
- 会话恢复：WS 重连时只恢复人话，跳过 tool 内部交互
- 日志面板 + session 概览

### 上下文管理
- `ContextManager` — SOUL/身份/用户/环境/记忆/技能 → system prompt
- 环境信息自动注入：工作区路径、会话目录、LLM 模型等
- `_prelude` + `_history` 双层结构
- `compact(llm)` — LLM 压缩历史
- 会话持久化 `logs/sessions/{id}.json` + 对话记录 `logs/conversations/`

### 记忆系统
- SQLite 索引（meta / files / chunks / fts5）
- 自动注入今日 + 昨日每日笔记

### LLM 客户端
- OpenAI 兼容 API（DeepSeek 默认）
- `finish_reason="length"` 自动续写
- 多 tool_calls 并行处理 + pending 检查

### 技能体系
- 两阶段加载：YAML 菜单 → `load_skill` 读完整 SKILL.md
- 标准目录结构

### 网络服务
- FileBrowser（:8080）+ SSH 隧道转发 Gateway（:18792）

---

## 🚧 进行中 / 待打磨

- 侧边栏各标签具体内容
- 动态组件 iframe 高度自适应
- exec no_return 后台任务跟踪
- user_input 从 Tool 迁移为 Extension

---

## 📋 待实现

- 信道抽象（Discord / Telegram / WebChat）
- 多 Agent 路由
- cancel 取消推理
- 会话存储（文件 → 数据库）
- 用户管理
- `SearchTool` / `FetchTool` / `ProcessTool`
- 外部队列（Redis / NATS）
- 可观测性
- 安全 / 沙箱

---

*最后更新：2026-05-15 · v2026.5.15.1*
