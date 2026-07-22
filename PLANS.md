# PLANS.md

> 当前工作与长期规格的导航，不复制实体内容。

## 规格与变更

| 内容 | 位置 |
|---|---|
| 长期能力契约 | [`specs/capabilities/`](specs/capabilities/) |
| 跨会话变更与状态 | [`specs/changes/`](specs/changes/) |
| 共享术语 | [`CONTEXT.md`](CONTEXT.md) |
| 关键架构决定 | [`docs/adr/`](docs/adr/) |
| 旧规格逐文件映射 | [`docs/agents/spec-migration-map.md`](docs/agents/spec-migration-map.md) |
| 待核实迁移项 | [`docs/agents/spec-migration-warnings.md`](docs/agents/spec-migration-warnings.md) |

清晰小改不创建计划。跨会话变更最多维护一份 `specs/changes/<feature>/spec.md`；只有存在真实阻塞边时才拆 tickets。完整规则见 [`docs/agents/workflow.md`](docs/agents/workflow.md)。

## 技术债

技术债按团队约定或显式 `$tech-debt-audit` 维护；不要把零散 TODO 当作执行计划。
