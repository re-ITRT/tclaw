# load_skill — 加载技能文档

按名称加载完整的 SKILL.md（功能说明书）。

从菜单中看到感兴趣的技能后，调用此工具获取完整内容。
获取后可用 read 工具读取 scripts/、references/、assets/ 下的文件。

每个 skill 的目录结构：
- `SKILL.md` — 功能说明书（必选）
- `scripts/` — 执行脚本
- `references/` — 详细参考文档
- `assets/` — 模板、图片等静态资源
- `setup.sh` — 环境依赖安装脚本

参数：
- `name`：技能名称（必填，菜单中的 name 字段）
