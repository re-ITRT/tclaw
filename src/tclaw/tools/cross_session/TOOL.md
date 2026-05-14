# cross_session — 跨 session 通信

通过此工具向其他 session 发送消息。非阻塞，发送即返回。

## 参数

- `target_session` — 目标 session ID（如 `main`、`sub:my-project`、`my-agent`）
- `content` — 消息内容

## 对方收到

对方 session 的上下文中会显示 `[from session {你的ID}] 消息内容`。
对方可以用 `cross_session` 工具回复。

## 获取对方 ID

当前上下文的第一条用户消息可能包含 `from_session_id`，
标识是谁发来的。回复时用那个 ID 作为 target_session。
