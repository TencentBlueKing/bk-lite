# 仓库级 projectmem 与 CodeGraph 退役设计

## 背景

本仓库同时维护 projectmem（`pjm`）和 CodeGraph 的项目级状态、MCP 配置、启动脚本、安装引导与 Agent 强制规则。两套工具会写入本地状态并影响不同 Agent 的工作流，容易产生状态、规则和索引冲突，因此不再由本仓库维护。

## 目标

- 完整移除 projectmem 与 CodeGraph 的仓库级集成和强制规则。
- 保留 OpenSpec 以及其他无关的 Agent 工作流。
- 不卸载开发者机器上的全局 `pjm`、`projectmem` 或 `codegraph`。
- 防止本地工具生成的 `.projectmem/`、`.codegraph/` 再次进入版本控制。

## 变更范围

1. 删除已跟踪的 `.projectmem/`、`.codegraph/` 内容及两个仓库级 MCP 启动脚本。
2. 删除仅服务于这两项集成的 `.mcp.json`、`.codex/config.toml` 与 `.claude/settings.json`。
3. 精简 `scripts/agent-tooling-bootstrap`，只保留仍由仓库维护的工具。
4. 从 `CLAUDE.md`、`docs/operations.md` 移除安装、强制调用、预检和 CodeGraph 优先规则。
5. 将依赖 `.projectmem` 作为说明依据的测试注释和设计文档改成自包含描述；历史 OpenSpec 记录只在会误导当前工作流时改写。
6. 在根 `.gitignore` 中加入 `.projectmem/` 与 `.codegraph/`。
7. 清理当前仓库 `.git/hooks` 中由 projectmem 安装的 hook；不改用户全局配置或全局安装。

## 安全边界

- 不删除全局命令、用户目录缓存或其他仓库的数据。
- 不覆盖当前工作区中已经存在的 `.projectmem/` 删除；将其视为本次清理的一部分。
- 不顺带调整业务代码、依赖或无关 Agent 技能。

## 验证

- 检查 Git 跟踪文件和当前工作区，不再存在有效的 projectmem、`pjm` 或 CodeGraph 集成入口。
- 校验 `.mcp.json`、`.codex/config.toml` 的格式。
- 运行 bootstrap 的只读检查，确认保留工具仍可正常检查。
- 检查根 `.gitignore` 能忽略 `.projectmem/`、`.codegraph/`。
- 检查 Git diff，确保变更仅覆盖本次退役范围。
