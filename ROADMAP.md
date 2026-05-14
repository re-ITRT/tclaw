# tclaw 项目历程

> **v0.2 — Gateway + Frontend + Multi-session**

---

## ✅ v0.2 已完工

### 基础设施
- 项目骨架 + uv 虚拟环境 + Git
- `settings.py` — 全局配置常量
- 文件日志（DEBUG）+ 终端日志（INFO）
- systemd 托管（开机自启，崩溃自动重启）

### 事件系统
- 事件格式统一为 `{"topic": str, "payload": dict}`
- `Topics` 常量类集中管理
- `EventBus` — 按 session 分队列，异步处理
- `dispatch_sync()` — 同步分发 before/after 事件

### Executable 执行管道
- `Executable` 基类 — Tool 和 Extension 共用
- `execute(payload)` 统一入口：before → do_execute → after
- 前端通信方法：`send_to_frontend()` / `register_component()` 等

### Tool 系统（12 个）
| 工具 | 功能 |
|------|------|
| `exec` | CLI 执行（默认 60s 超时） |
| `read` | 文件阅读（支持偏移/截断/图片） |
| `write` / `edit` | 文件写入 / 精确替换 |
| `output` | 输出给用户：text / figure / end |
| `user_input` | 用户输入转发 + 文件上传 |
| `memory_search` / `memory_get` | 记忆搜索 / 读取 |
| `load_skill` | 按需加载 SKILL.md |
| `quiz` | 交互式选择题 |
| `workspace_manager` | 管理会话：创建/多开/复制/列举 |
| `cross_session` | 跨 session 通信（非阻塞） |

### Extension 系统
- `Extension` 基类 — 不暴露给 LLM
- 自动发现 `src/tclaw/extensions/`
- 内置示例：`sample`（监听 exec:after）

### 多 session 系统
- `sub_workspace.py` — 子工作区管理模块
- **独立工作区** `sub:{name}`：每 session 全套记忆文件
- **多开（fork）**：`.forks.json` 映射，共享记忆，不占磁盘
- **复制（clone）**：完全拷贝独立工作区
- **模板（template）**：导出记忆 + 技能配置
- `ContextManager` 根据 `session_id` 自动加载对应记忆

### Gateway（Phase 1）
- FastAPI + WebSocket（`/ws/{session_id}`）
- SessionManager / ComponentManager / FrontendService
- 前端事件持久化到 SQLite（events.db）
- 断线重连全量回放

### 前端
- 登录页（仅 WS URL）→ 侧边栏主界面
- 侧边栏：聊天 / 会话 / Skills / Tools / Extensions
- 会话管理：新建 / 连接 / 多开 / 复制 / 模板 / 删除
- 聊天 session 选择器（main + sub + fork）
- Markdown 渲染 + Skills 开关/展开
- 日志面板

### 上下文管理
- `ContextManager` — SOUL/身份/用户/环境/记忆/技能注入
- 环境信息自动注入（工作区路径、LLM 模型等）
- 技能菜单放对话后、最靠近 LLM
- 会话持久化 + 对话记录

### 技能体系
- 两阶段加载：YAML 菜单 → `load_skill` 读完整内容
- 7 个预装技能（兼容 OpenClaw AgentSkills 格式）
- 前端 toggle 开关，禁用不出现在 LLM 上下文

### 记忆系统
- SQLite 索引（FTS5 全文搜索）
- 自动注入今日 + 昨日每日笔记
- 子工作区独立记忆目录

---

## 🚧 待打磨

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
- 更多工具

---

*最后更新：2026-05-14 · v0.2*
