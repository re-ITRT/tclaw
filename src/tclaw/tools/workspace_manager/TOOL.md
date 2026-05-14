# workspace_manager — 会话与工作区管理

LLM 通过此工具管理多会话、多开、复制、创建新工作区。

## 基本概念

- **main** — 默认会话，不可删除，记忆在 `workspace/memory/`
- **sub:{name}** — 独立工作区，每个有自己的记忆文件
- **fork** — 共享记忆：多个 session 指向同一套记忆文件（配置驱动，不占磁盘）
- **template:{name}** — 模板，可从模板创建新工作区

## 用法

### 列举会话

`action=list`：返回所有会话、多开、模板列表。

### 创建全新工作区

`action=create, name=项目名`：创建独立的 `sub:{name}` 工作区，
自动从当前 session 复制记忆模板。

可选参数覆盖初始记忆文件：
- `soul` — 人格设定
- `identity` — 身份信息  
- `user` — 用户信息
- `tools` — 环境配置
- `memory` — 长期记忆
- `skills` — 要启用的技能列表（其他禁用）

### 多开（fork）

`action=fork, source=项目名, name=新名字`：共享 source 的记忆（配置映射，不占磁盘）。

source 可以是 `main` 或 `sub:{name}`。

### 复制（clone）

`action=clone, source=项目名, name=新名字`：完整拷贝一份独立工作区。
