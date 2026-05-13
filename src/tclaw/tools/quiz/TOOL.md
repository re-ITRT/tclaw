--- 
name: quiz 
description: "向用户展示一道选择题，等待用户选择后返回结果。适合需要用户主动参与的交互场景。"
---

# quiz —— 选择题交互组件

## 功能

在对话中插入一道选择题，前端渲染为浮动选择框。  
用户点击选项后，选中结果回传 LLM。用户点叉则视为取消。

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `question` | string | 题目文本 |
| `options` | array | 选项列表，每个含 label（显示文本）和 value（选项值） |

## 示例

```json
{
  "question": "Python 常用的包管理器是？",
  "options": [
    {"label": "pip", "value": "A"},
    {"label": "npm", "value": "B"},
    {"label": "brew", "value": "C"},
    {"label": "cargo", "value": "D"}
  ]
}
```

## 注意事项

- options 建议 2-6 个，太多选项前端显示不佳
- label 是用户看到的文本，value 是回传给 LLM 的值
- 用户点叉关闭时返回 dismissed=true
