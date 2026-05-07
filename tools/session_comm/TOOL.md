# session_comm — 跨 session 通信

向另一个 session 发送消息。两个 session 可以通过 Session ID 互相交流。

参数：
- `to_session_id`：目标 session 的 ID（必填）
- `message`：要发送的消息内容（必填）

> 对方收到的消息不带来源前缀，来源和内容分开存储。ContextManager 负责拼接。
