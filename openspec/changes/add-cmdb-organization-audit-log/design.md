## Context

CMDB 已有 `ChangeRecord` 作为业务变更记录，部分管理类场景会通过 `server/apps/cmdb/utils/change_record.py` 镜像到 `system_mgmt.OperationLog`。当前镜像 detail 透传 `before_data` 和 `after_data`，但没有稳定的组织变化结构，调用方需要自行理解采集任务 `team`、模型 `group`、资产实例 `organization` 等不同字段。

本次变更面向统一操作日志审计，不新增数据库字段，不改变 CMDB 源变更记录模型。组织变化作为 `OperationLog.detail.organization_change` 的 JSON 子结构保存。

## Goals / Non-Goals

**Goals:**

- 在平台操作日志中为 CMDB 组织归属变化提供稳定、可测试的审计结构。
- 覆盖采集任务、模型、资产实例的创建、修改、删除组织上下文。
- 资产实例普通属性变更不扩大镜像范围，只有组织变化时才进入平台操作日志。
- 保持操作日志写入失败不影响主业务流程。

**Non-Goals:**

- 不新增数据库字段或迁移。
- 不在写日志时解析组织名称或路径。
- 不改变 CMDB `ChangeRecord` 的已有保存语义。
- 不把所有资产普通属性变更镜像到平台操作日志。

## Decisions

### Decision 1: 组织变化写入 `OperationLog.detail.organization_change`

`organization_change` 固定结构如下：

```json
{
  "field": "organization",
  "before_ids": [1],
  "after_ids": [2],
  "added_ids": [2],
  "removed_ids": [1],
  "changed": true
}
```

理由：`OperationLog.detail` 已经是 JSONField，当前 CMDB 镜像也在 detail 中传递 `before_data`/`after_data`。复用 detail 可以避免 schema migration，并保持已有消费者兼容。

替代方案：新增 `OperationLog` 列。这个方案便于查询，但会引入 migration、跨数据库兼容和历史数据填充问题，不符合当前“补齐审计 detail”的范围。

### Decision 2: 只持久化组织 ID

组织变化只保存 ID。组织名称和路径由展示层或查询层按需解析。

理由：ID 是审计事实，不受组织重命名或路径调整影响；写日志时不跨模块查询组织树，降低失败面和性能开销。

替代方案：写入名称或路径快照。这个方案阅读更直观，但组织改名后历史名称语义复杂，也会让日志写入依赖组织树查询。

### Decision 3: 对外字段统一为 `organization`

采集任务源字段为 `team`，模型源字段为 `group`，资产实例源字段为 `organization`。镜像到操作日志时统一输出 `field: "organization"`。

理由：平台操作日志消费者关心“组织变化”，不应理解 CMDB 内部不同对象的字段名差异。

替代方案：输出源字段名或增加 `source_field`。这个方案利于排查实现细节，但会把内部模型差异泄露到审计合同中。

### Decision 4: 创建、删除、修改都记录组织上下文

创建时 `before_ids=[]`、`after_ids=<创建后组织>`；删除时反向记录；修改时记录迁移差异。没有组织上下文且未发生变化时不写 `organization_change`。

理由：审计场景不仅要知道“从 A 迁到 B”，也要知道对象何时进入或离开某个组织。

替代方案：只记录 update 迁移。这个方案日志更少，但无法回答“某组织新增或移除了哪些 CMDB 对象”的审计问题。

### Decision 5: 资产组织变化条件镜像

资产实例普通属性变更仍只保存 CMDB `ChangeRecord`；当 `organization` 变化时，才额外镜像到平台 `OperationLog`。

理由：资产属性更新频率高，全量镜像会显著放大平台操作日志噪音。组织变化是权限和审计相关字段，值得进入统一日志。

替代方案：把所有资产普通属性变更都镜像到平台操作日志。这个方案最完整，但会带来明显噪音和存储压力。

## Risks / Trade-offs

- [Risk] 组织 ID 在历史日志中不可直接阅读。  
  Mitigation: 这是第一版有意取舍；展示层需要名称时按 ID 解析。

- [Risk] 不同对象的组织字段类型可能不一致，例如字符串、数字、列表、空值。  
  Mitigation: 实现统一 normalize helper，将输入规范为去重后的 ID 列表，并覆盖测试。

- [Risk] 批量资产更新可能产生多条平台操作日志。  
  Mitigation: 仅在每个实例组织确实变化时镜像，普通属性批量更新不镜像。

- [Risk] CMDB 镜像调用 system_mgmt 失败。  
  Mitigation: 延续当前策略，捕获异常并记录 warning，不影响源 `ChangeRecord` 与主业务。

## Migration Plan

- 无数据库迁移。
- 部署后新产生的操作日志会带 `organization_change`；历史日志不回填。
- 回滚时移除 detail 增强逻辑即可，已有 JSON detail 字段可被旧版本忽略。

## Open Questions

无。当前已确认：创建/删除/修改均记录组织上下文；只存组织 ID；字段名统一为 `organization`。
