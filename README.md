# tclaw — 下一代 AI Agent 框架

借鉴 OpenClaw 的设计思想，在关键选型上做自己的决策，自建体系。

## 架构概览

```
前端 (WebSocket) ←→ Gateway → Tool（直调）→ LLM 循环
                      │
                   FrontendService
                      │
                   EventBus → Tool / Mod
                      │
                  ContextManager
```

- **Gateway 直连 Tool**：前端的交互不经过 EventBus，通过 `FrontendService` 直调
- **Server-Driven UI**：前端纯渲染，不决策；组件注册/更新/销毁由服务端驱动
- **Tool / Mod 分离**：Tool 暴露给 LLM，Mod 为系统钩子，互不干扰
- **EventBus 只做 LLM 调度**：消息排队 + pending tool_calls 检查

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
- **前端**：纯 HTML/CSS/JS，服务端驱动 UI
- **工具**：每个工具一个文件夹（`__init__.py` + `TOOL.md`）
- **模块**：系统钩子在 `mods/` 目录，不暴露给 LLM
- **工作区**：`workspace/` — 记忆文件、日志、会话数据

## 文件结构

```
tclaw/
├── src/tclaw/
│   ├── common/           ← EventBus、Tool、Mod、ContextManager、LLMClient
│   ├── gateway/          ← FastAPI + WebSocket、SessionManager、FrontendService
│   │   ├── app.py        ← FastAPI 路由
│   │   ├── gateway.py    ← Gateway 主类（消息路由）
│   │   ├── session.py    ← Session 生命周期管理
│   │   ├── component_manager.py  ← 前端组件注册中心
│   │   ├── frontend_service.py   ← 统一前端通信层
│   │   └── models.py     ← 数据模型
│   ├── tools/            ← 内置工具（各一个文件夹）
│   │   ├── exec/         ← CLI 执行
│   │   ├── read/         ← 文件阅读
│   │   ├── write/        ← 文件写入
│   │   ├── edit/         ← 文件精确替换
│   │   ├── quiz/         ← 交互式选择题
│   │   ├── output/       ← 输出给用户
│   │   ├── user_input/   ← 用户输入接收器
│   │   ├── memory_get/   ← 读取记忆
│   │   ├── memory_search/← 全文搜索记忆
│   │   └── load_skill/   ← 技能加载
│   ├── mods/             ← 系统模块/钩子
│   │   └── sample/       ← 示例钩子
│   └── main.py           ← 启动入口
├── frontend/             ← 前端 HTML/CSS/JS
│   └── index.html        ← 单页应用
├── workspace/
│   ├── memory/           ← MEMORY/SOUL/USER/IDENTITY/TOOLS.md
│   ├── logs/             ← 日志 + 会话持久化 + 对话记录
│   │   ├── sessions/     ← 会话 JSON
│   │   └── conversations/← 对话 Markdown
│   └── skills/           ← 技能
├── config.json           ← 配置文件（不 commit）
├── pyproject.toml
└── requirements.txt
```

## 关键决策记录

| 日期 | 决策 | 原因 |
|------|------|------|
| 2026-05-07 | 项目初始化 | 新建 tclaw Python 项目 |
| 2026-05-07 | 定位为"下一代 OpenClaw" | 借鉴设计思想，自建体系 |
| 2026-05-07 | MVP：引擎层先行 | 先打好 EventBus + Tool + ContextManager 基础 |
| 2026-05-07 | 技能两阶段加载 | 菜单 ~100 tokens，完整内容按需读取 |
| 2026-05-09 | Gateway 直连 Tool，不经过 EventBus | 前端交互延迟更低，架构更简单 |
| 2026-05-09 | FrontendService 统一前端通信层 | Tool 不直接碰 Gateway，解耦 |
| 2026-05-09 | Server-Driven UI | 前端只渲染，不做决策 |
| 2026-05-09 | Tool 基类统一处理前端通信 | send_to_frontend / register_component 等 |
| 2026-05-11 | Tool / Mod 分离 | 系统钩子不暴露给 LLM，职责清晰 |
| 2026-05-11 | 默认 60s exec 超时 | 防止 WSL2 文件系统扫描卡死 |
| 2026-05-11 | 会话恢复只恢复人话 | 跳过 tool_call/tool_result 内部噪音 |

## 版本

- **v0.2** — Gateway + Frontend（[ROADMAP.md](./ROADMAP.md)）
- v0.1 — Phase Zero: Engine（已归档）

## 许可证

MIT
