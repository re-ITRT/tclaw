---
name: write
description: "写入文件。相对路径以工作区为根，绝对路径直接使用。"
---

# write —— 文件写入

将内容写入指定文件。

## 路径规则

- **相对路径**：基于工作区根目录
  - `"memory/NOTES.md"` → `workspace/memory/NOTES.md`
- **绝对路径**：直接使用

## 模式

- 覆盖（默认）和追加（`append=true`）两种模式
- 自动创建父目录
