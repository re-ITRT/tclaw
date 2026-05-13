# Gateway Phase 1 收尾计划

> 文档先行。确认方案后再写代码。

---

## 一、当前状态

```
Gateway 已实现：
├── gateway.py     ✅ Gateway 主类（连接管理 + 消息路由 + EventBus 订阅）
├── component_manager.py  ✅ ComponentManager（三实现 + resolve_callback）
├── app.py         ✅ FastAPI 路由（WS + REST + 组件静态文件）
├── models.py      ✅ 消息模型
├── exceptions.py  ✅ 异常定义
│
Tool 基类已更新：
├── handle_event()         ✅ （已有）
├── handle_gateway_event() ✅ （新增）
├── register_component()   ✅ （新增）
├── wait_for_component()   ✅ （新增）
├── update_component()     ✅ （新增）
├── destroy_component()    ✅ （新增）
└── reply_to_llm()         ✅ （新增）
│
设计文档：
├── ARCHITECTURE.md   ✅
├── docs/gateway.md   ✅
└── docs/dynamic-components.md  ✅
```

## 二、待办清单

### P0 — 重写内置工具

现有 11 个工具中，有几个需要适配新基类：

| 工具 | 改动 | 原因 |
|------|------|------|
| `output` | 使用 `reply_to_llm()` | 替代直接 publish Event，更简洁 |
| `user_input` | 使用 `register_component` + `wait_for_component` + `destroy_component` + `reply_to_llm` | 交互型工具的标准写法 |
| `exec` / `edit` / `read` / `write` / `memory_*` / `compact` / `load_skill` | 使用 `reply_to_llm()` | 替代手写 publish Event |

改动很小——基本都是把：
```python
await self.publish(Event(
    topic=Topics.AGENT_TOOL_RESULT,
    payload={"tool_id": self.tool_id, ...},
    source=self.tool_id,
    session_id=...,
))
```
换成：
```python
await self.reply_to_llm({...}, event.session_id)
```

### P1 — Session 管理独立模块

当前 Connection 类 + session 生命周期散落在 `gateway.py` 里：

```python
# 现在：gateway.py 里直接写了
class Connection: ...
def get_or_create_connection(self, ws, session_id): ...
def remove_connection(self, session_id): ...
def cleanup_session(self, session_id): ...
```

应该抽出为 `session.py`：

```python
# 抽出后
from .session import SessionManager

class Gateway:
    def __init__(self, ...):
        self.sessions = SessionManager()
```

**SessionManager 职责：**
- Connection 映射（session_id ↔ WS）
- 自动创建 ContextManager（延迟加载）
- 断线重连
- 过期清理（组件 + 上下文）
- Session 创建/断开日志

### P2 — 启动入口 `main.py`

一个干净的一键启动：

```python
# src/tclaw/main.py
async def main():
    bus = EventBus()
    bus.load_all_tools(ALL_TOOLS)
    bus.set_llm(LLMClient())
    bus.set_context_manager(ContextManager(system_prompt="你是 tclaw"))
    await bus.start()

    gateway = Gateway(bus, host="0.0.0.0", port=8080)
    task = await start_gateway(gateway)

    await task  # 阻塞直到 Ctrl+C
    await bus.stop()
```

同时暴露命令行入口：

```bash
tclaw start               # 默认 8080
tclaw start --port 9000   # 指定端口
tclaw start --headless    # 无 Gateway，纯引擎
```

### P3 — 集成测试

一个脚本验证全链路：

```
tests/test_gateway.py

├── 1. 启动 EventBus + Gateway
├── 2. WS 连接 /ws/test-session
├── 3. 发 text 消息
├── 4. 发 tool_event
├── 5. 注册组件 → iframe 加载
├── 6. 组件回调 → resolve → destroy
├── 7. 点叉 → dismiss 回调
├── 8. 断开 → session 清理
└── 9. 停服务
```

---

## 三、依赖关系

```
P0（重写工具） ← 不依赖其他，直接改
P1（session.py） ← 不依赖 P0
P2（main.py）   ← 依赖 P1（Gateway 用 SessionManager）
P3（集成测试）  ← 依赖 P0 + P1 + P2
```

所以我建议的顺序：

```
P0 → P1 → P2 → P3
  或
P1 → P0 → P2 → P3  (先抽 session，再改工具)
```

---

## 四、不做的

- 流式输出（Phase 2）
- Cancel 支持（Phase 2）
- 预制组件渲染器（前端的事）
- CLI/Stdio Transport（Phase 2）
- 安全/沙箱（以后再说）

---

你觉得这个顺序怎么样？P0 和 P1 先做哪个？
