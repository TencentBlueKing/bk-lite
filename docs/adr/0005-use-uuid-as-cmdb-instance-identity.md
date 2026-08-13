# ADR 0005：使用 UUID 作为 CMDB 实例业务身份

Status: accepted  
Date: 2026-08-10

## Context

CMDB 曾把 FalkorDB 节点 ID 用作实例身份，并持久化到 PostgreSQL、Web URL、
OpenAPI、NATS、Stargazer 与相邻模块。节点 ID 会在图库重建或数据搬迁时重新
分配，不能稳定表达同一业务实例。

## Decision

- 每个 CMDB 实例由 Server 生成不可变、全局唯一的 UUIDv4，字段名 `inst_uuid`。
- Web、API、消息、服务边界与跨模块调用只接受并返回 UUID；仓外不提供数字 ID
  兼容窗（前端代码改动可后置，但契约已定）。
- 图节点/关系内部 ID 仅用于同进程 Graph Adapter 与 `InstanceManage` 工作集，
  不得作为持久引用或对外业务键；出站响应剥离 `_id` / 数字 `inst_id`。
- 实例关系稳定业务键为端点 UUID；边持久化 `src_inst_uuid` / `dst_inst_uuid`，
  禁止数字端点属性。
- `ChangeRecord`：活跃查询用 `inst_uuid`；历史无法映射的数字 `inst_id` 可空保留。
- `ConfigFileVersion`：过渡期 **双列**（保留 `instance_id`，新增 `instance_uuid`）；
  配置采集协议 v2 回调必须带 `instance_uuid`。
- VM/Telegraf 的 `instance_id=cmdb_<CollectModels.id>` 是**采集任务**身份，保持不变；
  配置文件目标改用 `target_instance_uuid` + `protocol_version=2`。
- 结构迁移 `0045_instance_uuid_transition` 后，数据清洗由维护命令
  `migrate_cmdb_instance_uuid_refs` / `migrate_oa_cmdb_instance_uuid_refs`
  （`--dry-run` / `--apply` / `--verify`）完成；**不属于** `batch_init`。
- 本阶段不做 Neo4j；不做启动期 `prepare_*` 编排；不做删列 cutover 迁移（可选后续，编号另定）。

## Consequences

- 图重建后只要保留 `inst_uuid` 与边 UUID 端点，跨模块引用仍可定位原实例。
- 旧数字 URL/消息在后端切换后立即失效；须与前端同发或接受短暂不可用。
- PG 与图无跨库事务；发布依赖协调备份、幂等断点清洗与 verify。
- UUID 唯一性由图索引、应用不变量与 verify 共同保证；不宣称图库级唯一约束。

详细范围与验收见 `specs/changes/cmdb-instance-uuid/spec.md` 与
`docs/operations/cmdb-instance-uuid-cutover.md`。
