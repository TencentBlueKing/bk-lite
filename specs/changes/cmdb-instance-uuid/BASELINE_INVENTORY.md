# CMDB 实例身份基线清单（事实）

Status: facts-only  
Branch: `local_codex/cmdb-instance-uuid` @ `902698906`  
Date: 2026-08-10  

本文件只记录主仓**当前代码事实**，不含方案。证据路径相对仓库根。  
不作准：`worktrees/cmdb-instance-uuid`（旧 UUID 实现归档）。

## 0. 身份模型（现状）

| 概念 | 字段 | 存储 | 语义 |
|---|---|---|---|
| 实例主键 | `_id` | 图引擎原生 `ID(n)`，读出后写入返回 dict | CMDB 图实例数字身份的源头 |
| API/RPC 惯用名 | `inst_id` / `inst_ids` | 传输参数；多数等于 `_id` | OpenAPI 常把 `_id` 别名为 `inst_id` |
| 关联边端点 | `src_inst_id` / `dst_inst_id` | **图边属性**（int） | 冗余存两端节点数字 ID |
| OA 画布 | `bk_inst_id` / `instId` | PG JSON（view_sets 等） | 与 CMDB `_id` 同值 |

图节点属性中**不存在**业务 UUID。删除为 `DETACH DELETE` **硬删**，无实例级 tombstone。

## 1. 实例创建旁路

| 区域 | 现状事实 | 证据 |
|---|---|---|
| 核心服务 | `InstanceManage.instance_create` / `instance_batch_create` → `GraphClient.create_entity`；结果用 `result["_id"]` | `server/apps/cmdb/services/instance.py` |
| 图层 | FalkorDB/Neo4j `CREATE` 后 `entity_to_dict` 注入 `_id=node.id`；`CQLValidator.validate_id` 强制 int | `server/apps/cmdb/graph/falkordb.py`、`neo4j.py`、`validators.py` |
| HTTP UI | `InstanceViewSet` 创建经 Operation outbox；`pk` 为数字；响应带 `_id` | `server/apps/cmdb/views/instance.py`、`services/operation_service.py` |
| OpenAPI | 创建/批量走 InstanceManage；路径/批量 `inst_id: IntegerField`；出站 `_id→inst_id` | `server/apps/cmdb/open_api/` |
| NATS / RPC | `create_instance`；删除 `inst_ids`；关联数字端点 | `server/apps/cmdb/nats/nats.py`、`server/apps/rpc/cmdb.py` |
| 采集入库 | `collection/common.py` **直接** `ag.create_entity`，旁路 InstanceManage；边写 `src_inst_id`/`dst_inst_id` | `server/apps/cmdb/collection/common.py` |
| Excel 导入 | `Import.inst_list_save` → `batch_create_entity`；变更记录用 `_id` | `server/apps/cmdb/utils/Import.py` |
| IPAM | `instance_create("ip")`；关联 payload 数字端点 | `services/ipam_discovery.py`、`ipam_reconcile.py` |
| PC discovery | **直接** `ag.create_entity`；差集 `DETACH DELETE` | `services/pc_discovery.py` |
| NodeMgmt sync | `instance_create("host")`；`persisted["_id"]` 记入变更集 | `services/node_mgmt_sync_service.py` |
| 模型 migrate/seed | 创建 classification/model，**不创建 instance** | `model_migrate/migrete_service.py` |

## 2. 关联与拓扑

| 区域 | 现状事实 | 证据 |
|---|---|---|
| 边写入 | `create_edge(..., data)`，`data` 含 `src_inst_id`/`dst_inst_id`；端点用 `ID(a)/ID(b)` 匹配 | `instance.py` `instance_association_create`；`graph/*._create_edge` |
| 边查询 | 按边属性 int 过滤；`instance_association_map` 用边字段建图 | `instance.py` |
| 自动关联 | 构造 `"src_inst_id": source["_id"]` 后创建 | `auto_relation_reconcile.py` |
| 通用拓扑 | `WHERE ID(n)=$inst_id`；树节点含数字 `_id` | `graph/falkordb.py` `format_topo` |
| 网络拓扑 | 中心/节点 id 为数字字符串 | `instance.py` `network_topology` |
| 机柜机房 | 设备关联用 `_id` / 边端点 int | `rack_room.py` |

## 3. PostgreSQL / JSON 一等引用

| 数据 | 现状事实 | 证据 |
|---|---|---|
| ChangeRecord | `inst_id = BigIntegerField`；关联变更对 src/dst 各写一条 | `models/change_record.py`、`utils/change_record.py` |
| ConfigFileVersion | `instance_id = CharField`，值为图 `_id` 字符串；MinIO key 含该值 | `models/config_file_version.py`、`config_file_service.py` |
| SubscriptionRule | `instance_filter.instance_ids`；`snapshot_data` 以数字 ID 为键 | `models/subscription_rule.py`、`subscription_trigger.py` |
| CollectModels | `instances` JSON 含 `_id`；目标服务取 `_id`/`id` | `collect_model.py`、`collect_target_service.py` |
| CmdbOperation / outbox | `target`/`result_snapshot` 含 `instance_id=_id`；mirror `target_id=str(inst_id)` | `operation.py`、`operation_service.py` |
| 关注资产 | `UserPersonalConfig` `cmdb_followed_assets`：`{inst_id}` | `user_personal_config.py`；Web followedAssets |
| OA 网络拓扑 | `view_sets` 中 `bk_inst_id` / 组件 `instId` | `operation_analysis/.../canvas_config.py`、`runtime.py` |

## 4. 跨模块传输

| 从 → 到 | 字段 | 载体 | 活跃 |
|---|---|---|---|
| CMDB → Stargazer（配置采集） | `target_instance_id`（来自实例 `_id`） | 节点下发 JSON | 是 |
| Stargazer → CMDB | 回调 `instance_id` / `instance_name` | NATS | 是 |
| CMDB → Alerts | RPC 按 `_id`/ids 批量查 | NATS/RPC | 是（查询） |
| CMDB → OpsPilot | 工具入参 `inst_id:int` | 进程内 | 是 |
| CMDB → OA | HTTP `inst_id`；画布 `bk_inst_id` | API + PG | 是 |

## 5. 同名异义（非 CMDB 图实例身份）

| 名称 | 真实语义 | 证据提示 |
|---|---|---|
| `instance_id=cmdb_{task_id}` | 采集任务 / Telegraf 标签 | `collection/collect_plugin/base.py`、`node_configs/base.py` |
| 云厂商 `instance_id` / `resource_id` | 云资源原生 ID | 云采集插件 / 模型属性 |
| Monitor `instance_id` | 监控维度身份 | `monitor/` |
| OpsPilot Bot `instance_id` | 机器人自身 UUID | `opspilot` 模型 |
| 操作日志 `target_id` | 审计目标字符串（可含数字 inst_id） | `system_mgmt`；ChangeRecord mirror |
| RPC `instance_id`（executor 等） | 服务实例命名 | `rpc/stargazer.py` 等 |

## 6. 启动约束（相关事实）

- 生产 `startup.sh`：`migrate` → cache/static → `batch_init` → supervisord。  
- `batch_init` 完成前不得依赖 API/Celery/NATS 消费者。  
- 一次性身份数据转换属于**发版维护步骤**，不得误当作普通启动任务塞进 `batch_init` 依赖链。  
- 证据：`docs/operations/server-startup-dependencies.md`、`support-files/release/startup.sh`、`batch_init.py`。

## 7. 迁移优先级（事实分级，非方案）

| 优先级 | 类别 |
|---|---|
| P0 | 图 `_id`、边 `src/dst_inst_id`、ChangeRecord、ConfigFileVersion、采集/订阅 JSON、OpenAPI/NATS/HTTP path |
| P1 | OA `bk_inst_id`、配置采集 `target_instance_id`、关注资产 |
| P2 | 告警 enrichment lookup、操作日志历史 |
| 排除 | Telegraf `cmdb_{task_id}`、云/监控/OpsPilot 同名字段 |

## 8. 相对旧实现的事实对比（仅说明差异，不评判）

`worktrees/cmdb-instance-uuid` 上曾存在整包 UUID 切换提交；**主仓本分支无** `instance_identity.py`、无 0044/0045、无 ADR 0005。本清单以主仓为准。
