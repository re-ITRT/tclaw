# tclaw — 下一代 AI Agent 框架

借鉴 OpenClaw 的设计思想，在关键选型上做自己的决策，自建体系。

## 架构概览

```
前端 (WebSocket)
     │
     ▼
Gateway ──→ Tool (直调) ──→ LLM 循环
     │
 FrontendService (events.db 持久化)
     │
 EventBus ──→ Tool / Extension
     │
 Executable (execute 管道)
     │  ├── {topic}:before  (扩展可拦截)
     │  ├── do_execute
     │  └── {topic}:after   (扩展可响应)
     │
 ContextManager
     ├── main ← workspace/memory/
     ├── sub:{name} ← workspace/sub_workspaces/sub:{name}/memory/
     └── fork:{name} ← 映射到源工作区 (.forks.json)
```

- **统一执行管道**：Tool 和 Extension 共用 `Executable.execute()`，带 before/after 生命周期
- **Event = dict**：`{"topic": str, "payload": dict}`
- **Server-Driven UI**：前端纯渲染，所有消息经 FrontendService 持久化到 events.db
- **多 session 记忆隔离**：每个 session 可拥有独立记忆文件

## 快速开始

```bash
# 安装
uv venv && source .venv/bin/activate
uv pip install -e .
uv pip install -r requirements.txt
export LLM_API_KEY="your-deepseek-key"

# 启动
python -m tclaw --port 18792

# 打开 http://localhost:18792
```

## 核心约定

- **语言**：Python 3.11+
- **架构**：Event-driven，按 session 分队列
- **事件格式**：`{"topic": str, "payload": dict}`
- **前端**：纯 HTML/CSS/JS，单页应用
- **Tool**：LLM 可见，有 TOOL.md + function-calling
- **Extension**：系统钩子，不暴露给 LLM
- **工作区**：`workspace/` — 记忆文件、日志、会话数据

## 关键概念

### Executable（执行管道）

Tool 和 Extension 都继承自 `Executable`，共用 `execute()` 方法：

```python
class Executable(ABC):
    async def execute(self, payload: dict) -> None:
        # 1. 检查是否已取消
        # 2. 广播 {topic}:before（同步分发，订阅者可取消）
        # 3. 再次检查
        # 4. do_execute(payload)  ← 子类实现
        # 5. 广播 {topic}:after
```

### Tool（LLM 工具）

```python
class ReadTool(Tool):
    tool_id = "read"
    async def do_execute(self, payload: dict) -> None:
        content = read_file(payload["path"])
        await self.reply_to_llm({"content": content}, session_id)
```

### Extension（系统钩子）

```python
class AuditExtension(Extension):
    ext_id = "audit"
    def __init__(self, bus):
        super().__init__(bus)
        bus.subscribe("tool.invoke.exec:after", self._on_exec)
    async def _on_exec(self, event: dict):
        print(f"[audit] exec: {event['payload'].get('command', '')}")
```

## 多 session 系统

每个 session 可拥有独立的记忆空间：

| session | 记忆位置 | 说明 |
|---------|---------|------|
| `main` | `workspace/memory/` | 默认会话，不可删除 |
| `sub:{name}` | `workspace/sub_workspaces/sub:{name}/memory/` | 独立工作区，全套记忆文件 |
| `{name}`（fork） | 映射到源工作区（.forks.json） | 共享记忆，不占磁盘 |
| `template:{name}` | `workspace/sub_workspaces/template:{name}/` | 模板，含记忆 + 技能配置 |

**前端操作：** 新建 / 连接 / 多开（共享）/ 复制（独立）/ 生成模板 / 删除

**LLM 工具：** `workspace_manager` — 创建/多开/复制/列举会话

### 跨 session 通信

`cross_session(target_session="sub:my-agent", content="你好")` — 非阻塞发送消息到其他 session，对方上下文自动处理。

## 文件结构

```
tclaw/
├── src/tclaw/
│   ├── common/
│   │   ├── event_bus.py       ← 事件总线
│   │   ├── events.py          ← Topics 常量
│   │   ├── executable.py      ← Executable 基类
│   │   ├── tool.py            ← Tool 基类
│   │   ├── extension.py       ← Extension 基类
│   │   ├── sub_workspace.py   ← 子工作区管理
│   │   ├── context_manager.py ← 上下文管理
│   │   ├── llm_client.py      ← LLM 客户端
│   │   └── settings.py        ← 全局配置
│   ├── gateway/               ← 前端接入层
│   │   ├── app.py             ← FastAPI 路由
│   │   ├── frontend_service.py← 前端通信 + events.db
│   │   └── component_manager.py
│   ├── tools/                 ← 内置工具（自动发现）
│   │   ├── exec/ + TOOL.md
│   │   ├── read/ + TOOL.md
│   │   ├── cross_session/     ← 跨 session 通信
│   │   ├── workspace_manager/ ← 会话管理
│   │   └── ... (write, quiz, output, etc.)
│   └── extensions/            ← 系统扩展
├── frontend/index.html        ← 单页应用
├── workspace/
│   ├── memory/                ← main session 的记忆
│   ├── sub_workspaces/        ← 子工作区 + 模板 + fork 映射
│   └── logs/                  ← 日志 + events.db + 会话 JSON
├── config.json                ← 配置文件（不 commit）
└── pyproject.toml
```

## 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-07 | 项目初始化 | 新建 tclaw Python 项目 |
| 2026-05-09 | Gateway 直连 Tool | 前端交互低延迟 |
| 2026-05-09 | Server-Driven UI | 前端只渲染，不做决策 |
| 2026-05-12 | Event 简化为 dict | 事件格式统一 |
| 2026-05-12 | Tool / Extension 分离 | 系统钩子与 LLM 工具分家 |
| 2026-05-12 | before/after 生命周期 | 可插拔执行管道 |
| 2026-05-14 | 子工作区 + fork/clone/template | 多 session 记忆隔离 |
| 2026-05-14 | 所有前端消息持久化 events.db | 断线重连全量回放 |

## 版本

- **v0.2** — Gateway + Frontend + Multi-session（[ROADMAP.md](./ROADMAP.md)）

## 许可证

MIT
