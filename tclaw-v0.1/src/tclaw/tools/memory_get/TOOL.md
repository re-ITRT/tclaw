# memory_get — 读取记忆文件

读取指定记忆文件的内容。路径相对于 memory/ 目录。

参数：
- `path`：文件路径（如 `MEMORY.md`、`daily/2026-05-07.md`）
- `offset`：起始行号（默认 1）
- `limit`：最大行数（默认 200）

> 只能访问 memory/ 目录下的文件。
