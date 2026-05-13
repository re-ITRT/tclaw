# tclaw 动态组件设计

> Tool 通过 JSON 协议向前端注册组件，前端负责渲染 + 通信中转。

---

## 1. 核心原则

**Tool 给前端的不是 HTML，而是 JSON。**

```
Tool ──JSON──→ Gateway ──WS──→ 前端

前端拆解 JSON：
  1. 看 schema 是预制组件还是 custom
  2. custom 组件 → 创建 iframe，加载 index.html
  3. 通过 postMessage 把 component_id/session_id/初始数据 传给 iframe
  4. iframe 是纯渲染器，通信全靠 postMessage
```

---

## 2. 注册消息（Tool → 前端）

`component_register` 是一条完整的 JSON 消息，前端据此决定如何渲染：

```json
{
  "type": "component_register",
  "component_id": "comp_abc123",
  "tool_id": "quiz",
  "session_id": "session-xxx",
  "schema": {
    "type": "custom",
    "display": "floating",
    "component_url": "/components/quiz/index.html",
    "initial_data": {
      "question": "选哪个方案？",
      "options": [
        {"label": "方案A", "value": "A"},
        {"label": "方案B", "value": "B"}
      ]
    }
  }
}
```

前端收到后：
- `schema.type = "custom"` → iframe 加载 `component_url`
- `display = "floating"` → 浮动弹窗
- 通过 postMessage 把 `component_id`, `session_id`, `initial_data` 传给 iframe

---

## 3. postMessage 通信协议

### 前端 → iframe（初始化 + 更新）

```javascript
// 前端在 iframe 加载完成后发送

// 初始化
iframe.contentWindow.postMessage({
  type: "tclaw_component_init",
  component_id: "comp_abc123",
  session_id: "session-xxx",
  tool_id: "quiz",
  initial_data: { question: "...", options: [...] }
}, "*");

// 更新数据
iframe.contentWindow.postMessage({
  type: "tclaw_component_update",
  component_id: "comp_abc123",
  data: { new_options: [...] }
}, "*");
```

### iframe → 前端（用户事件）

```javascript
// iframe 中的组件代码
window.parent.postMessage({
  type: "tclaw_component_event",
  component_id: "comp_abc123",
  session_id: "session-xxx",
  event: "on_select",
  data: { value: "B" }
}, "*");
```

### 前端 → Gateway（转发到后端）

```json
// 前端收到 iframe 的 postMessage 后，通过 WebSocket 转发
{
  "type": "component_callback",
  "component_id": "comp_abc123",
  "result": {
    "event": "on_select",
    "data": { "value": "B" }
  }
}
```

session_id 前端已在 WebSocket 连接上绑定，回调消息里不需要重复带。

---

## 4. iframe 渲染流程

```
                                  Tool
                                   │ register({ type:"custom", ... })
                                   ▼
                               Gateway
                                   │ WS: component_register (JSON)
                                   ▼
                               前端
                                   │
                      ┌────────────┴────────────┐
                      │ schema.type == "custom"  │
                      └────────────┬────────────┘
                                   │
                         创建 iframe
                    src = component_url
                                   │
                        iframe 加载完成
                                   │
                      postMessage(init)
                      ┌── component_id
                      ├── session_id
                      └── initial_data
                                   │
                         用户操作组件
                                   │
                      postMessage(event)
                      ┌── component_id
                      ├── event
                      └── data
                                   │
                       前端 → WS: callback
                              │
                        Gateway ComponentManager
                              │ resolve_callback()
                     ┌────────┴────────┐
                     │                 │
                 Future.set_result   WS: component_destroy
                     │                 │
                     ▼                 ▼
               Tool 被唤醒        前端收到 → 移除 iframe
                     │
               publish(result)
                     │
                     ▼
              LLM 循环继续
```

Tool 拿到 result 后**自己决定**要不要关窗口：
- 交互型 Tool（选择题、输入框）→ `cm.destroy_component(cid)` 一起带走
- 展示型 Tool（图表、地图、状态面板）→ 不关，一直挂着
- 用户也可以手动关（前端提供关闭按钮）

---

## 5. 通信关系图

```
                    Tool
                     │
          ┌──────────┴──────────┐
          │  register()         │
          │  wait_for_component │
          │  update_component   │
          └──────────┬──────────┘
                     │ 方法调用（直连）
                     ▼
               ComponentManager
          (GatewayComponentManager)
                     │
          ┌──────────┴──────────┐
          │ WS 推前端            │ register → component_register
          │ WS 更新              │ update  → component_update
          │ WS 接收回调          │ callback → resolve Future
          └──────────┬──────────┘
                     │ WebSocket
                     ▼
                 前端主界面
                     │
          ┌──────────┴──────────┐
          │ postMessage         │ init/update → iframe
          │ postMessage         │ event ← iframe
          └──────────┬──────────┘
                     │ iframe
                     ▼
              Tool 的 index.html
              (纯渲染器，无上下文)
```

---

## 6. Tool 开发者模板

基类已经把组件方法包好了，开发者直接调：

```python
from tclaw.common.tool import Tool
from tclaw.common.events import Topics


class QuizTool(Tool):
    tool_id = "quiz"

    parameters = {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "value": {"type": "string"},
                    }
                }
            }
        }
    }

    async def handle_event(self, event):
        cid = await self.register_component(
            session_id=event.session_id,
            schema={
                "type": "custom",
                "display": "floating",
                "initial_data": {
                    "question": event.payload["question"],
                    "options": event.payload["options"],
                },
            },
        )
        result = await self.wait_for_component(cid)

        if result.get("event") == "dismiss":
            await self.reply_to_llm({"dismissed": True}, event.session_id)
        else:
            await self.destroy_component(cid)
            await self.reply_to_llm({"selected": result}, event.session_id)

    async def handle_gateway_event(self, data, session_id):
        """用户点选后直接回调。"""
        await self.reply_to_llm({"selected": data}, session_id)
```

对比之前要自己调 `_bus.component_manager` 的写法，现在干净多了。

Tool 开发者只需要知道这 5 个方法：

| 方法 | 用途 | 是否必须 |
|------|------|---------|
| `register_component()` | 注册组件到前端 | 交互型必须 |
| `wait_for_component()` | 等用户操作 | 交互型必须 |
| `update_component()` | 更新已渲染的组件 | 可选 |
| `destroy_component()` | 关窗口 | 交互型拿到结果后调 |
| `reply_to_llm()` | 回 LLM 循环 | 每个工具最后都调 |

不涉及前端的 Tool 一个组件方法都不用碰，该干嘛干嘛。

---

## 7. 预制组件（无 component/ 目录时）

当 Tool 不提供 `component/` 目录时，schema 走预制类型：

```json
{
  "schema": {
    "type": "select",
    "prompt": "选哪个？",
    "options": [{"label": "A", "value": "a"}]
  }
}
```

前端用内置渲染器处理，无需 iframe。两种模式：

| schema.type | 渲染方式 | 前置条件 |
|-------------|----------|----------|
| `custom` | iframe 加载 component/index.html | Tool 有 component/ 目录 |
| `input` / `select` / `confirm` | 前端预制组件 | 无需额外文件 |

---

## 8. 位置参数

```json
{
  "display": "floating",
  "position": {"top": "50%", "left": "50%", "transform": "translate(-50%, -50%)"},
  "size": {"width": "400px", "height": "auto"},
  "closable": true,
  "resizable": false
}
```

| display | 含义 |
|---------|------|
| `floating` | 浮动弹窗，不阻塞对话 |
| `fixed` | 固定在对话流中 |
| `inline` | 嵌入在消息里 |

---

## 9. 叉叉关闭（前端默认行为）

每个组件前端默认给它一个叉（X 按钮），除非 Tool 显式设置 `closable: false`。

```
┌──────────────────────┐
│ 标题           [ × ] │  ← 前端加的叉，不在 iframe 里
├──────────────────────┤
│                      │
│  Tool 的组件内容      │
│  (iframe / 预制组件)  │
│                      │
└──────────────────────┘
```

用户点叉时，前端发 `component_callback`：

```json
{
  "type": "component_callback",
  "component_id": "comp_abc",
  "result": {
    "event": "dismiss",
    "data": {}
  }
}
```

### Tool 怎么知道是被叉掉的

```python
result = await cm.wait_for_component(cid)

if result.get("event") == "dismiss":
    # 用户点叉关掉了，不需要额外 destroy
    await self.publish(AGENT_TOOL_RESULT, {"dismissed": True})
else:
    # 用户做了选择
    await cm.destroy_component(cid)
    await self.publish(AGENT_TOOL_RESULT, result)
```

### 规则

| 场景 | 谁关窗口 | 谁发 destroy 消息 |
|------|---------|------------------|
| 用户点叉 | 前端直接移除 | `resolve_callback` 时 pop 注册表，**不**发 WS destroy（已移除） |
| Tool 拿到选择后 | Tool 调 `destroy_component` | CM 发 WS destroy 通知前端移除 |
| 展示型挂了没人管 | Session 断开时 | `cleanup_session` 统一清理 |
| Tool 想禁止用户关 | schema `closable: false` | 前端不显示叉 |
