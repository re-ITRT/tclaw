# scheduler — 定时任务管理

创建和管理定时任务。触发时自动向目标 session 发送消息。

## 参数

- `action` — add（添加）| remove（删除）| list（列举）
- `id` — 任务标识（add 时可选，remove 时必需）
- `name` — 任务名称
- `target_session` — 目标 session（如 main、sub:my-project）
- `message` — 触发时发送的消息内容
- `schedule` — 调度配置

### schedule 格式

指定时间（一次）：
```json
{"kind": "at", "at": 1715731200000}
```

每隔一段时间（重复）：
```json
{"kind": "every", "every_ms": 60000}
```

Cron 表达式（重复）：
```json
{"kind": "cron", "expr": "0 */5 * * *"}
```

## 管理自身
- action=list 列举当前所有任务
- action=remove 可通过 id 删除
