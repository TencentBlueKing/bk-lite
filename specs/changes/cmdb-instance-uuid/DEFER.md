# 延期项（本阶段明确不做）

Date: 2026-08-10  
Updated: 2026-08-10（T8：前端仍延期；对接说明已产出）  
关联：[spec.md](./spec.md) · [FRONTEND_HANDOFF.md](./FRONTEND_HANDOFF.md)

## 前端（实现延期，契约不延期）

- **最终交互契约已定**：CMDB 前后端以 `inst_uuid` 为实例业务身份（见规格 Q2）。  
- **本阶段仍不改 Web 代码**；路径/字段清单见 [FRONTEND_HANDOFF.md](./FRONTEND_HANDOFF.md)。  
- 后续前端评估范围：资产列表/详情/关系/拓扑 URL 与 rowKey、订阅、关注资产、配置文件、采集表单、运营分析网络拓扑等。  

## 旧 worktree 实现

- 路径：`worktrees/cmdb-instance-uuid`（分支 `feature_windyzhao_cmdb-instance-uuid`）。  
- **不作准**；不在本阶段删除、重置或继续开发。  
- 仅可作参考 diff；新实现以本目录契约 + 主仓基线为准。

## 实现与发布

- 契约已于 2026-08-10 批准；实现 Plan T1–T8 已收口（见 IMPLEMENTATION_PLAN / ACCEPTANCE）。  
- 删列 cutover（早期计划编号曾称 `0045`；现该号已用于结构过渡迁移）与启动期 `prepare_*` 编排：**本阶段不做**，见 cutover Runbook §6。  
- 清洗命令保持维护编排，**∉** `batch_init`。
