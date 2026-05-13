---
name: read
description: "读取文件。相对路径以工作区为根，绝对路径直接使用。"
---

# read — 文件阅读

读取指定文件的内容。支持文本文件和图片文件。

## 路径规则

- **相对路径**（不以 `/` 开头）：基于工作区根目录
  - `"memory/MEMORY.md"` → `workspace/memory/MEMORY.md`
  - `"skills/sample-skill/SKILL.md"` → `workspace/skills/sample-skill/SKILL.md`
- **绝对路径**（以 `/` 开头）：直接使用，可读取系统文件
  - `"/home/iter/config.json"`

## 文本文件

- `offset`：起始行号（从 1 开始），不指定则从开头
- `limit`：最多读取多少行（默认 2000）
- 超过 50KB 时自动截断

## 图片文件

自动检测图片格式（jpg/png/gif/webp），返回 base64 编码数据。
