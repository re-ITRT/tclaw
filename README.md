# tclaw — 下一代 OpenClaw

借鉴 OpenClaw 的设计思想，在关键选型上做自己的决策，自建体系。

## 快速开始

```bash
# 安装
uv venv && source .venv/bin/activate
uv pip install -e .
uv pip install -r requirements.txt
export LLM_API_KEY="your-key"

# 测试
python -c "from tclaw.common.llm_client import LLMClient; print('OK')"
```

## 核心约定

- **语言**：Python 3.11+
- **架构**：Event-driven，按 session 分队列
- **技能**：两阶段加载（菜单 → `load_skill`）
- **记忆**：工具化（`memory_search` / `memory_get`），不自动注入
- **工作区**：`workspace/` — 记忆文件、Skill 目录、上传文件

## 文件结构

```
tclaw/
├── src/tclaw/
│   ├── common/          ← EventBus、Tool、ContextManager、LLMClient
│   ├── backend/         ← 记忆索引、memory_reader
│   └── tools/           ← 内置工具（各一个文件夹）
├── tools/               ← 用户安装的工具
├── workspace/
│   ├── memory/          ← MEMORY/SOUL/USER/IDENTITY 等
│   ├── skills/          ← 技能（含 SKILL.md + scripts/ + references/）
│   └── uploads/         ← 用户上传文件
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

## 版本

- **v0.1** — Phase Zero: Engine（[ROADMAP.md](./ROADMAP.md)）
