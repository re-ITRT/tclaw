# tclaw — 下一代 AI Agent 框架

借鉴 OpenClaw 的设计思想，在关键选型上做自己的决策，自建体系。

## 架构概览

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
     │  ├── :before  (扩展可拦截)
     │  ├── do_execute
     │  └── :after   (扩展可响应)
     │
 ContextManager
```

- **统一执行管道**：Tool 和 Extension 共用 `Executable.execute()`，带 before/after 生命周期
- **Event = dict**：`{"topic": str, "payload": dict}`，不再有 Event dataclass
- **Server-Driven UI**：前端纯渲染，组件注册/更新/销毁由服务端驱动
- **Gateway 直连 Tool**：前端交互不走 EventBus，通过 FrontendService 直调

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

    async def do_execute(self, payload: dict) -> None:
        pass  # 子类重写

    async def send_to_frontend(self, session_id, data) -> None:
    async def register_component(self, session_id, schema) -> str:
    async def wait_for_component(self, component_id, ...) -> Any:
    async def update_component(self, component_id, data) -> None:
    async def destroy_component(self, component_id) -> None:
```

### Tool（LLM 工具）

```python
class ReadTool(Tool):
    tool_id = "read"
    parameters = {"path": {"type": "string"}}

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
        cmd = event["payload"].get("command", "")
        print(f"[audit] exec: {cmd}")
```

## 文件结构

```
tclaw/
├── src/tclaw/
│   ├── common/              ← 核心
│   │   ├── event_bus.py     ← 事件总线（按 session 分队列）
│   │   ├── events.py        ← Topics 常量
│   │   ├── executable.py    ← Executable 基类（共用执行管道）
│   │   ├── tool.py          ← Tool 基类（LLM 可见）
│   │   ├── extension.py     ← Extension 基类（系统钩子）
│   │   ├── context_manager.py  ← 上下文管理
│   │   ├── llm_client.py    ← LLM 客户端
│   │   └── settings.py      ← 全局配置
│   ├── gateway/             ← 前端接入层
│   │   ├── app.py           ← FastAPI 路由
│   │   ├── gateway.py       ← 消息路由
│   │   ├── session.py       ← Session 生命周期
│   │   ├── component_manager.py  ← 组件注册中心
│   │   └── frontend_service.py   ← 前端通信层
│   ├── tools/               ← 内置工具（自动发现）
│   │   ├── exec/ + TOOL.md
│   │   ├── read/ + TOOL.md
│   │   ├── quiz/ + TOOL.md + component/ (内嵌 iframe)
│   │   ├── output/ + TOOL.md  ← text / figure / end 三种模式
│   │   └── ... (write, edit, user_input, memory_*)
│   ├── extensions/          ← 系统扩展（自动发现）
│   │   ├── sample/          ← 示例：监听 exec:after
│   │   └── output_plugin/   ← 示例：监听 output:after
│   └── main.py              ← 启动入口
├── frontend/
│   └── index.html           ← 单页应用
├── workspace/
│   ├── memory/              ← MEMORY/SOUL/USER/IDENTITY/TOOLS.md
│   └── logs/                ← 日志 + 会话 JSON + 对话 Markdown
├── config.json              ← 配置文件（不 commit）
├── pyproject.toml
└── requirements.txt
```

## 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-07 | 项目初始化 | 新建 tclaw Python 项目 |
| 2026-05-07 | 定位为"下一代 OpenClaw" | 借鉴设计思想，自建体系 |
| 2026-05-07 | MVP：引擎层先行 | 先打好 EventBus + Tool + ContextManager 基础 |
| 2026-05-09 | Gateway 直连 Tool | 前端交互延迟更低 |
| 2026-05-09 | FrontendService 统一前端通信层 | Tool 不直接碰 Gateway |
| 2026-05-09 | Server-Driven UI | 前端只渲染，不做决策 |
| 2026-05-11 | 默认 60s exec 超时 | 防止 WSL2 文件系统扫描卡死 |
| 2026-05-11 | 会话恢复只恢复人话 | 跳过 tool_call 噪音 |
| 2026-05-12 | Event 简化为 dict | 事件格式统一为 topic + payload |
| 2026-05-12 | Tool / Extension 分离 + Executable 基类 | 系统钩子与 LLM 工具分家 |
| 2026-05-12 | before/after 生命周期 | 每个执行都有可插拔管道 |
| 2026-05-13 | LLM 输出走 output tool | text/figure/end 三种模式 |
| 2026-05-13 | 前端 session 选择 + 删除 | 简化登录，支持多会话管理 |

## 版本

- **v0.2** — Gateway + Frontend + Extension（[ROADMAP.md](./ROADMAP.md)）
- v0.1 — Phase Zero: Engine（已归档）

## 许可证

MIT
