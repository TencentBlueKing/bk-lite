# Agent 工具链与规格体系迁移到 Grill

Status: done

## Problem Statement

仓库同时维护 ProjectMem、CodeGraph、OpenSpec、OPSX 和 Superpowers，多套强制入口重复加载指令、增加工具回合，并把规格分散在四套目录中。

## Solution

- 移除仓库级 ProjectMem/CodeGraph wiring、OpenSpec/OPSX/Superpowers 入口和运行资产。
- 安装固定版本的 Grill 13 核心 Skills，保留并适配两个 BK-Lite 专属 Skills。
- 使用 `CONTEXT.md`、`docs/adr/`、`specs/capabilities/`、`specs/changes/` 作为唯一事实源。
- 全量迁移旧四套 spec corpus，并维护逐文件映射和迁移警告。

## Implementation Decisions

- 清晰小改走直接路径；模糊、跨域、破坏性或难回滚变更才显式进入 Grill。
- 旧 canonical specs 一对一迁为 capability contracts。
- OpenSpec change 的 proposal/design/delta/tasks 合并到单份 change spec，不自动把未验证 delta 写入长期 capability。
- Superpowers 历史规格/计划迁为 `done` 或 `cancelled` 的 change specs。
- `spec/` 中长期 Markdown 迁为 legacy capability evidence；一次性计划迁为历史 change specs；非 Markdown 原型保存在只读资产区并由 change spec 建索引。
- 所有旧 tracked 文件必须有且仅有可达的迁移目标；旧校验失败保留为迁移警告。

## Testing Decisions

- 验证旧 corpus tracked 文件集合与迁移映射精确相等。
- 验证所有映射目标存在，Markdown 内容保留，二进制/HTML/JSON/JS 资产字节一致。
- 验证 15/15 Skills 通过官方 validator，15/15 metadata 可解析。
- 扫描活跃入口残留，验证所有代码和文档规格引用可达。
- 运行 JSON、shell、Python/TypeScript 最小语法检查与 `git diff --check`。

## Out of Scope

- 不卸载机器级 CLI 或修改其他仓库配置。
- 不把旧 OpenSpec 校验失败项伪装成已确认业务事实。
- 不修改本次迁移无关的业务行为。
