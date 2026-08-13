# CMDB 实例 UUID — 重设计 README

| 文档 | 用途 |
|---|---|
| [BASELINE_INVENTORY.md](./BASELINE_INVENTORY.md) | 主仓基线身份事实清单（只读结论） |
| [GRILL_DECISIONS.md](./GRILL_DECISIONS.md) | Grill 结论（**Q2 已锁定**） |
| [spec.md](./spec.md) | 重设计规格 + 需求契约（**已批准**） |
| [IMPLEMENTATION_WALKTHROUGH.md](./IMPLEMENTATION_WALKTHROUGH.md) | 实现前走读（契约→代码落点） |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | 实现 Plan（**T1–T8 完成**） |
| [ACCEPTANCE.md](./ACCEPTANCE.md) | §13 验收证据与复跑命令 |
| [FRONTEND_HANDOFF.md](./FRONTEND_HANDOFF.md) | 前端对接说明（本阶段不改 Web） |
| [DEFER.md](./DEFER.md) | 前端实现延期 / 旧 worktree / 未交付项 |

运维与架构：

- [docs/operations/cmdb-instance-uuid-cutover.md](../../../docs/operations/cmdb-instance-uuid-cutover.md)
- [docs/adr/0005-use-uuid-as-cmdb-instance-identity.md](../../../docs/adr/0005-use-uuid-as-cmdb-instance-identity.md)

**后端分支**：`local_codex/cmdb-instance-uuid`

**已锁定**：跨模块用 `inst_uuid` 唯一确定实例；CMDB 后端内部可用 `_id`/`inst_id`。

**契约状态**：已批准（2026-08-10）。  
**实现状态**：T1–T8 完成；Web 已按 FRONTEND_HANDOFF 落地于本分支；删列 cutover / `prepare_*` 未交付（结构迁移现为 `0045_instance_uuid_transition`）。
