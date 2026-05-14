---
name: postels-coding-system
description: "Postel 的个人编码系统。通过 toOpenClaw（命令行）和 execnohup（Agent tool）实现触发式开发：后台执行命令，跑完自动通知到对话，可查询历史。适用于： (1) 跑长任务不想阻塞对话时， (2) 编写/维护项目代码时， (3) 处理实验/数据处理/模型训练等耗时任务时， (4) 需要项目规范化管理（Git、README）时。"
---

# Postel's Coding System

通过 `execnohup`（Agent tool，推荐）或 `toOpenClaw`（命令行）后台执行命令，跑完自动通知到对话，不阻塞聊天。

## 🚨 强制规则：先估耗时，再选执行方式

**用 `exec` 前必须先判断耗时：**

```
收到请求 → 判断耗时
  ├─ < 30 秒（ls, cat, grep, 小计算） → exec 直接跑
  └─ > 30 秒或拿不准（训练、批量扫描、编译）
      → execnohup（优先）或 toOpenClaw
```

### 执行后行为

| 方式 | 行为 |
|------|------|
| **exec** | 等待结果，正常汇报 |
| **exec execnohup <命令>** / **execnohup** tool | 调 toOpenClaw 后台跑+自动通知+写索引；调用后**立即结束本回合** |
| **toOpenClaw** | 命令行执行，后台跑完自动通知；调用后**立即结束本回合** |

## 使用方式

### 方式一：execnohup（Agent tool，推荐）

对话中直接让 AI 调 `execnohup` tool 即可。内部调用 `toOpenClaw` 后台执行，跑完自动通知，同时维护索引方便查询。

**参数**：
- `command`（必填）：要运行的命令
- `workdir`（可选）：工作目录
- `delay`（可选）：跑完等 N 秒再通知（默认 10）

**后续查询**：
```
execnohup_status pid=<PID> 或 id=<ID>  → 查状态+最近日志
execnohup_list                          → 列所有历史（按时间倒序）
```

### 方式二：toOpenClaw（命令行）

```bash
toOpenClaw python3 train.py --epochs 100
toOpenClaw make build
```

后台跑完自动通知到对话。不推荐，优先用 `execnohup`。

## 功能特性

- **后台执行+自动通知**：`execnohup` 调 `toOpenClaw`，跑完自动发到对话
- **进程管理**：索引文件 `~/.openclaw/execnohup/index.json` 记录每次调用的 PID、命令、状态
- **多语言**：任何 CLI 命令（Python、Shell、Node.js 等）
- **Git 管理**：所有项目用 Git 管理，及时提交
- **README 规范**：每个项目维护 README.md 记录约定和决策

## 耗时判断标准

| 因素 | 快速 | 耗时 |
|------|------|------|
| 命令类型 | 查询、读取、简单计算 | 训练、处理、编译 |
| 数据量 | 小文件、少量数据 | 大文件、批量数据 |
| 关键词 | echo, cat, ls, grep, pip | train, process, build, experiment |
| 网络 | 本地操作 | 网络请求、下载 |
| 模糊时默认 | exec | execnohup |

## 项目规范化管理

### Git 工作流

**所有项目用 Git 管理。**

```bash
# 初始化
git init && git add . && git commit -m "init: 项目初始化"

# 日常
git add -A && git commit -m "类型: 简短描述"
```

**提交类型**：`feat` / `fix` / `refactor` / `docs` / `chore` / `experiment`

**Agent 规范**：
- 改代码前先 `git status`，检查当前状态
- 改完代码后、commit 前，**必须检查 README.md 是否需要更新**：
  - 新增了文件/功能 → 更新文件结构和功能说明
  - 改了参数/配置 → 更新参数表格
  - 跑了新实验出结果 → 更新结果表格/关键发现
  - 改了流程/用法 → 更新使用说明
- 每次有意义变更及时 commit
- 不同方案用分支或实验式提交

### README.md 模板

每个项目根目录维护 README.md，记录约定和决策：

```markdown
# 项目名称
## 核心约定
- 数据限制、代码规范、文件结构
## 关键决策记录
| 日期 | 决策 | 原因 |
## 待办事项 / 已知问题
```

## 🔒 安全机制

- 敏感信息（token、密码）只通过对话管理，不写入代码
- 危险命令（`rm -rf /` 等）需二次确认

## 文件结构

```
postels-coding-system/
├── SKILL.md
└── references/
    └── project-templates.md
```

### 核心工具

| 工具 | 方式 | 说明 |
|------|------|------|
| `exec execnohup <命令>` | CLI 脚本 | **推荐**。调 toOpenClaw 后台跑+自动通知+写索引，和 exec 同级 |
| `execnohup` | Agent tool | 对话中 function-call 版，效果同上 |
| `execnohup_status` | Agent tool | 对话中按 PID/ID 查任务状态 |
| `execnohup_list` | Agent tool | 列出所有历史后台任务 |
| `toOpenClaw` | `~/.local/bin/toOpenClaw` | 命令行工具，后台跑命令+自动通知（内部调用） |

### 运行环境

| 项目 | 说明 |
|------|------|
| Python | `~/.openclaw/workspace/.venv`（含 torch/rocm），运行前 `source .venv/bin/activate` |
| 包管理 | `uv pip install xxx` |
| WSL2 | Windows 路径 `C:\xxx` → `/mnt/c/xxx`，自动转换 |
| MATLAB | `/usr/local/bin/matlab`，范式：Python 跑数据→导出 JSON/CSV→MATLAB 画图 |
