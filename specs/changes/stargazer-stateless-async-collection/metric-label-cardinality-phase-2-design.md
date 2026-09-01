# Stargazer 配置快照标签基数治理实施方案

Status: implemented-awaiting-deployment-validation

> 修订说明（2026-08-31）：本稿保留最初的“VM 资产行 + Redis 小型控制元数据”探索过程；
> 后续复核确认 timestamp-per-run Redis key、instant query `value[0]` 和仅有下界的
> `sample_ts >= round_ts` 不能形成可靠轮次边界。修订后的实施基线见
> [`metric-label-cardinality-round-boundary-implementation.md`](metric-label-cardinality-round-boundary-implementation.md)。

## 1. 决策摘要

本次只治理 PC 与 WinSphere 的快照轮次元数据标签，不迁移完整资产数据，不处理其他动态业务字段。

完整 PC/WinSphere 资产行继续写入 VictoriaMetrics；Stargazer Redis 只保存一份有界的小型快照元数据，
CMDB 通过现有 NATS request/reply 查询该元数据。CMDB 不需要、也不允许直接连接 Stargazer Redis。

本次从 VictoriaMetrics 标签删除：

| 采集对象 | 删除标签 |
|---|---|
| `pc` | `snapshot_id`、`software_snapshot_status`、`software_expected_count`、`software_error_count` |
| `pc_software` | `snapshot_id` |
| WinSphere 全部八个模型 | `snapshot_id`、`snapshot_status` |
| WinSphere 根对象 `winsphere` | `snapshot_manifest` |

WinSphere 八个模型是：

1. `winsphere`；
2. `winsphere_host_pool`；
3. `winsphere_cluster`；
4. `winsphere_host`；
5. `winsphere_vm`；
6. `winsphere_storage_pool`；
7. `winsphere_vswitch`；
8. `winsphere_port_group`。

本次不删除资源身份标签，例如 `resource_id`、`inst_name`、`pc_inst_name`、`instance_id`、
`collection_task_id`、`collection_target`、`collection_plugin_ref` 和 `model_id`。

本方案是纯代码改造：不新增数据库表或迁移，不新增端口、服务、Redis 实例、NATS 实例、Object Store、
环境变量或部署配置。历史 VictoriaMetrics 数据不迁移、不回填、不主动删除，随现有保留策略自然过期。

## 2. 背景与根因

结构化配置编码器把记录中的所有非空标量转换为 Influx tag，指标值固定为 `1`：

```text
配置记录 -> 所有标量成为 tags -> *_info{属性...} gauge=1
```

VictoriaMetrics 以 measurement 和完整 tag set 识别一条 series。因此只要标签中的任意字段变化，
同一个资产就会形成一条新 series。

PC 与 WinSphere 每轮生成新的 `snapshot_id`；WinSphere 还把完整 JSON manifest 编码为标签。结果是：

```text
series ~= 资源数 * 采集轮数
```

而正确的不变量应为：

```text
series ~= 资源数 * 指标数 * 有限状态数
series 不随采集轮数线性增长
```

当前关键证据：

- `agents/stargazer/tasks/utils/nats_helper.py` 的结构化编码器统一使用一个
  `_publish_timestamp_ms` 写入同一目标结果的所有行；
- `agents/stargazer/service/collection_service.py` 当前把顶层 snapshot 字段复制到每条资产行；
- `agents/stargazer/enterprise/plugins/inputs/pc/pc_inventory.py` 每轮创建 `snapshot_id`，并复制到 PC
  和每条软件记录；
- `agents/stargazer/enterprise/plugins/inputs/winsphere/winsphere_info.py` 每轮创建 `snapshot_id` 和
  `snapshot_manifest`；
- `server/apps/cmdb/collection/query_vm.py` 已按最新 `round_ts` 限制查询窗口，并按样本时间再次过滤；
- `server/apps/cmdb/collection/common.py` 已提供
  `is_authoritative_snapshot(model_id)` 删除安全 Interface。

所以本次不需要把完整快照搬出 VictoriaMetrics。资产行仍由 VM 承载；快照分组改用同一目标结果天然共享的
样本时间，完整性、计数、hash 和权威性等控制信息通过小型轮次元数据补充。

## 3. 目标与非目标

### 3.1 目标

1. PC/WinSphere 不再因采集轮次产生新的 snapshot series；
2. 保留 PC 软件清单和 WinSphere 八模型的完整性校验；
3. 完整性无法证明时 fail closed，绝不执行破坏性差集删除；
4. NATS/Redis 只承载小型控制元数据，不复制完整资产行；
5. 写入、重试、重复 RPC 和重复 CMDB 对账保持幂等；
6. 不扩大 Server 启动依赖，不让元数据资源声明进入 `batch_init`；
7. 不修改现有部署配置和历史数据。

### 3.2 非目标

以下内容不在本次范围：

- VMware `uptime_seconds`；
- WinSphere `up_time_seconds`；
- Nacos `last_refresh`、count 类字段；
- 容量、使用量、对象数量等动态业务字段；
- `channel_config_version`；
- `status`、`state`、`version`、`remark`、`description` 等资产属性；
- 通用配置编码器的 `0`、`0.0`、`False` 保留问题；
- 配置采集整体迁出 VictoriaMetrics；
- PC/WinSphere 历史快照兼容、历史 series 清理或数据回填。

## 4. 核心不变量

实施必须同时满足以下不变量：

1. **数据与元数据分离**：VM 保存资产行；Redis 只保存快照控制信息；
2. **同轮归属**：一条元数据由
   `(collection_task_id, collection_target, publish_timestamp_ms)` 唯一定位；
3. **精确读取**：NATS 只允许按完整键批量读取，不提供扫描、前缀查询或列举接口；
4. **完成标记含义增强**：PC/WinSphere 发布 `cmdb_round_complete` 前，所有目标的 VM 发布和元数据
   持久化都必须成功；
5. **不可覆盖冲突**：同一个元数据键重复写入相同内容视为幂等成功，不同内容视为冲突并失败；
6. **删除默认关闭**：元数据缺失、过期、schema 不支持、计数/hash 不一致或 RPC 超时时，不执行任何删除；
7. **游标不前移**：元数据读取或验证失败时，CMDB 本轮任务失败并保留旧 `last_synced_round`；
8. **容量有界**：单条元数据、批量查询数量、响应大小和 TTL 都有硬上限；
9. **无敏感正文**：元数据、NATS 响应和日志中不得出现凭据、完整资产 payload 或外部响应正文。

## 5. 目标架构

```text
PC / WinSphere plugin
  -> 资产 records + SnapshotMetadata
  -> StructuredMetricsPayload
       data           = 完整资产行
       round_metadata = 小型完整性元数据
  -> ResultPublisher
       1. RedisRoundMetadataStore.save(metadata)
       2. publish asset rows to VictoriaMetrics
       3. 两者成功后返回 publish confirmed
  -> 全部目标 confirmed
  -> publish cmdb_round_complete(round_ts)

CMDB round gate
  -> 读取最新 cmdb_round_complete
  -> 查询该轮 VictoriaMetrics 资产行
  -> 从根对象行提取 target + sample_timestamp_ms
  -> StargazerRoundMetadataClient.get_many(keys)
  -> 校验 metadata 与 VM 行
  -> PCSnapshotAdapter / WinsphereSnapshotValidator
  -> 安全 Upsert；仅权威完整快照允许 Delete
```

该设计形成两个深 Module：

- Stargazer `RoundMetadataStore`：隐藏 Redis key、序列化、TTL、幂等和容量限制；
- Server `RoundMetadataReader`：隐藏 Stargazer 路由、NATS RPC、批量切分、响应校验和错误映射。

PC 和 WinSphere 调用方不直接操作 Redis key 或 NATS subject。

## 6. 元数据协议

### 6.1 内部 Envelope

Stargazer 内部使用版本化结构：

```yaml
schema_version: 1
kind: inventory_snapshot
collection_task_id: "321"
instance_id: "cmdb_321"
collection_target: "10.0.0.8"
collection_plugin_ref: "..."
model_id: "pc"               # 或 winsphere
publish_timestamp_ms: 1780000000123
snapshot_id: "..."
snapshot_status: complete     # complete | partial
details:
  # PC
  software_expected_count: 42
  software_error_count: 0

  # WinSphere
  snapshot_manifest:
    schema_version: 1
    snapshot_id: "..."
    expected_models: [...固定八模型...]
    models:
      winsphere_vm:
        count: 56
        identity_hash: "sha256..."
        authoritative: true
```

`collection_task_id`、target、plugin、model 和时间由发布层补齐，插件只生成 snapshot 业务元数据。

### 6.2 Redis key 与写入语义

建议 key：

```text
stargazer:collection:v1:round-meta:<task_id>:<target_sha256>:<publish_timestamp_ms>
```

约束：

- target 使用 SHA-256，避免不安全字符和无界 key；原 target 保留在有界 payload 内用于二次校验；
- 默认 TTL 为 24 小时，使用代码常量，不增加部署参数；
- 单条序列化后最大 16 KiB；超过上限视为发布失败；
- 使用 canonical JSON 计算 payload SHA-256；
- 首次写入使用带 TTL 的原子 `SET NX`；
- key 已存在时读取并比较 digest：相同返回 `duplicate`，不同返回 `conflict`，禁止覆盖；
- 不设置永久 key，不保存完整 `records`，不记录凭据和错误正文。

容量估算必须在实施验收时记录：

```text
active_keys ~= targets * (TTL / collection_interval)
```

若实际任务规模使 24 小时 TTL 不可接受，应在实施前重新确认 TTL，而不是无界增加 Redis 容量。

### 6.3 NATS request/reply

新增 Stargazer handler：

```text
<region>_stargazer.get_collection_round_metadata
```

Request：

```yaml
schema_version: 1
collection_task_id: "321"
instance_id: "cmdb_321"
lookups:
  - collection_target: "10.0.0.8"
    publish_timestamp_ms: 1780000000123
```

Response：

```yaml
success: true                  # 现有 Stargazer NATS Adapter 自动包装
schema_version: 1
items:
  - collection_target: "10.0.0.8"
    publish_timestamp_ms: 1780000000123
    found: true
    metadata: {...RoundMetadataEnvelope...}
```

协议约束：

- `instance_id` 必须严格等于 `cmdb_<collection_task_id>`；
- 每次最多查询 50 个完整 key，Server 超过时自行分批；
- 单条元数据最大 16 KiB，整个响应最大 1 MiB；
- 禁止空 lookup、通配符、前缀和范围查询；
- handler 使用 queue group，多个 Stargazer Pod 只由一个 responder 处理；
- 同一服务名下的 Stargazer Pod 必须继续共享其现有 Redis，这是现有租约/fencing 已经依赖的条件；
- NATS 只返回固定错误码，如 `invalid_request`、`metadata_missing`、`metadata_conflict`、
  `metadata_unavailable`，不返回异常正文；
- Server 调用超时建议 3 秒，不在单次调用内无限重试；周期对账负责后续补偿。

CMDB 与 Stargazer 不要求使用同一个 Redis。CMDB 只通过同一个 NATS 控制面请求目标区域的
Stargazer；Stargazer 自己读取自己的 Redis。

仓库内未发现按 Stargazer method 枚举的 NATS ACL，现有调用也使用 `<service>.<method>` 形式，因而
按仓库事实不需要部署配置变更。上线前的逐区域 smoke test 必须验证实际环境允许新 subject；若客户环境
额外维护了仓库外的逐 subject 白名单，则需先把该外部事实反馈并重新确认“纯代码改造”前提。

## 7. 对象级改造

### 7.1 PC / `pc_software`

#### Stargazer

`normalize_snapshot()` 继续校验脚本输出中的 snapshot 身份，但输出时：

- PC 资产行删除：
  `snapshot_id`、`software_snapshot_status`、`software_expected_count`、`software_error_count`；
- 软件资产行删除 `snapshot_id`；
- `snapshot_id`、status、expected/error count 改为顶层 `round_metadata`；
- `pc_inst_name` 和 `software_key` 保留，它们是稳定归属/身份字段；
- PC 与软件行继续共享同一个 `publish_timestamp_ms`。

#### CMDB

PC 以以下键分组：

```text
(collection_target, publish_timestamp_ms, pc_inst_name)
```

不再使用 `(pc_inst_name, snapshot_id)`。`snapshot_id` 仅从元数据进入 `PCSnapshot`，用于审计和
故障关联，不参与 VM series identity。

校验规则保持并收紧：

1. 每个 target/time 恰好一个 PC 根记录；
2. 软件记录的 `pc_inst_name` 必须等于根记录 `inst_name`；
3. 软件 `inst_name`/`software_key` 不重复；
4. complete 时，实际软件数等于 `software_expected_count`；
5. `software_error_count == 0`；
6. 只有全部成立时 `PCSnapshot.can_delete=True`；
7. 合法 partial 快照可以保守 Upsert，但不能删除；
8. 元数据缺失或协议错误时整轮失败，不写图、不前移游标。

### 7.2 WinSphere 八模型

#### Stargazer

- 八模型所有资产行删除 `snapshot_id` 和 `snapshot_status`；
- 根对象删除 `snapshot_manifest`；
- manifest 仍由现有 `_snapshot_manifest()` 生成并保存到 round metadata；
- `resource_id`、关系字段和全部正式 CMDB 属性保持不变；
- 空模型的现有占位指标行为暂时保持，删除权威性由 manifest 决定。

#### CMDB

WinSphere 按以下键识别一次目标快照：

```text
(collection_target, publish_timestamp_ms)
```

`WinsphereSnapshotValidator` 校验：

1. metadata schema 支持；
2. 顶层与 manifest 的 `snapshot_id` 相同；
3. manifest 精确包含固定八模型；
4. 每个模型实际有效 `resource_id` 数量等于 manifest count；
5. `resource_id` 在模型内唯一；
6. 按排序后的 `resource_id` 重算 SHA-256，必须等于 `identity_hash`；
7. `authoritative` 必须是布尔值；
8. 同一 target 的八模型样本时间必须一致。

验证结果保存在 WinSphere collect plugin 实例中，并实现现有 Interface：

```python
is_authoritative_snapshot(model_id) -> bool
```

`Management` 已经通过该 Interface 决定是否允许差集删除，因此无需修改通用删除算法：

- manifest 完整且模型 `authoritative=true`：允许该模型按配置策略删除；
- 模型 `authoritative=false`：只 Upsert，不删除；
- metadata 缺失、计数/hash 错误：整轮失败，不执行图写入；
- 合法 partial/可选端点不可用：仅权威模型允许删除，其他模型保守处理。

## 8. 一致性与顺序

### 8.1 Stargazer 写入顺序

每个目标必须执行：

1. 插件返回资产数据和 snapshot metadata；
2. 发布协调器分配一次稳定的 `publish_timestamp_ms`；
3. 发布器构造完整 `RoundMetadataEnvelope`；
4. 元数据幂等写入 Redis；
5. 资产行写入 VictoriaMetrics，并等待现有发布确认；
6. 两者均成功，该目标 publish 状态才是 `confirmed`；
7. 所有目标 confirmed 后才写 `cmdb_round_complete(round_ts)`。

若第 4 步成功而第 5 步失败，Redis 中只是一个有 TTL 的孤立元数据，不会产生完成标记，也不会被
CMDB 采用。重试使用同一个 timestamp/key 和相同 digest，属于幂等写。

若 Redis 写入失败，PC/WinSphere 目标发布失败；不得只写 VM 后仍发布完成标记。

### 8.2 CMDB 读取顺序

1. `round_sync` 取得最新 `round_ts`；
2. `query_vm` 查询并过滤 `sample_ts >= round_ts` 的行；
3. 从 `pc_info` 或 `winsphere_info_gauge` 根行提取 target 和 sample timestamp；
4. 把秒级 VM timestamp 规范转换为整数毫秒；
5. 按目标 Stargazer namespace 分批调用 metadata RPC；
6. 验证返回 envelope 与请求 task/target/timestamp/model 完全一致；
7. 完成 PC 或 WinSphere 快照校验；
8. 校验通过后才进入图 Upsert/Delete；
9. 整轮成功后才更新 `last_synced_round`。

## 9. 失败语义

| 故障 | Stargazer 行为 | CMDB 行为 | 删除 |
|---|---|---|---|
| Redis 写失败/超时 | 目标发布失败，不发 round complete | 看不到新完成轮次 | 禁止 |
| 元数据 key 冲突 | permanent failure，保留原值 | 不消费冲突轮次 | 禁止 |
| VM 发布失败 | 不发 round complete，元数据等 TTL 回收 | 不消费该轮 | 禁止 |
| NATS 超时/无 responder | VM 数据不写图，本轮 ERROR | 保留旧游标，后续周期重试 | 禁止 |
| metadata missing/expired | 本轮 ERROR，记录稳定错误码 | 保留旧资产和旧游标 | 禁止 |
| schema 不支持 | 本轮 ERROR | 不猜测、不降级解析 | 禁止 |
| PC partial | 元数据正常保存 | 允许保守 Upsert | 禁止 |
| WinSphere 某模型非权威 | 元数据正常保存 | 该模型允许 Upsert | 仅该模型禁止 |
| count/hash/重复身份错误 | 元数据协议校验失败 | 整轮不写图 | 禁止 |
| 重复 RPC/重复对账 | 返回相同元数据 | 依赖现有对账幂等 | 不产生额外副作用 |

失败日志只记录稳定 event、task ID、有界 target 摘要、timestamp、failed_stage 和 error_type/error_code，
不记录 manifest、资产 payload、NATS 请求正文或外部响应正文。

## 10. 计划修改面

### 10.1 Stargazer Core 与 Enterprise 插件

| 文件 | 计划变更 |
|---|---|
| `agents/stargazer/core/collection/contracts.py` | 为结构化结果增加默认空的 `round_metadata`，保持其他插件兼容 |
| `agents/stargazer/core/collection/round_metadata.py`（新增） | Envelope、canonical 编码、大小校验、Redis Store Interface/Adapter、幂等冲突判断 |
| `agents/stargazer/core/collection/application.py` | 用现有共享 Redis 构造 Store，并注入发布器 |
| `agents/stargazer/core/collection/result_publisher.py` | PC/WinSphere 发布前保存元数据；元数据失败进入现有 publish 失败语义 |
| `agents/stargazer/service/collection_service.py` | snapshot metadata 不再复制到资产行，改为放入结构化结果的独立字段 |
| `agents/stargazer/service/nats_server.py` | 新增有界、精确读取的 metadata handler |
| `agents/stargazer/enterprise/plugins/inputs/pc/pc_inventory.py` | 保留输入校验，输出资产行时剥离五个传输字段，生成 PC metadata |
| `agents/stargazer/enterprise/plugins/inputs/winsphere/winsphere_info.py` | manifest 生成保持不变，作为 metadata 输出 |

企业插件文件只存在企业版时，Community 的动态加载和无 enterprise 环境测试必须继续通过。

### 10.2 Server Core 与 PC Enterprise Adapter

| 文件 | 计划变更 |
|---|---|
| `server/apps/rpc/stargazer.py` | 增加 `get_collection_round_metadata()` RPC Adapter |
| `server/apps/cmdb/collection/round_metadata.py`（新增） | Stargazer namespace 解析、RPC 分批、响应校验、按 VM 根行构造 lookup |
| `enterprise/server/apps/cmdb_enterprise/collect/pc.py` | 查询 metadata；按 target/time/PC 分组；调用现有 `PCSnapshotReconciler` |
| `server/apps/cmdb/services/pc_discovery.py` | parser 从 metadata 获取 snapshot 状态和计数，不再从 VM 标签读取 |

### 10.3 Server Enterprise

| 文件 | 计划变更 |
|---|---|
| `enterprise/server/apps/cmdb_enterprise/collect/winsphere.py` | 获取并验证 metadata/manifest，实现 `is_authoritative_snapshot(model_id)` |

通用 `Management` 已有权威快照 Interface，原则上不修改
`server/apps/cmdb/collection/common.py`；只有测试证明现有调用顺序不足时，才做最小调整并单独说明。

## 11. 实施步骤

实施按测试先行拆为以下步骤，每一步都必须保持可审查的小 diff。

### 步骤 0：锁定现状与红测

1. 增加基数回归测试：同一资产只改变本次六类 snapshot 字段时，当前实现 series key 会变化；
2. 增加 PC/WinSphere 端到端合同红测：目标输出不再包含 snapshot 标签，但 CMDB 仍能完成安全对账；
3. 锁定旧的 PC partial 不删除、WinSphere 八模型映射、round gate 游标语义；
4. 确认 Community 无 enterprise package 时测试仍可收集。

### 步骤 1：实现 Stargazer RoundMetadataStore

1. 定义 Envelope 和 validation；
2. 实现 canonical JSON、digest、key 构造；
3. 实现 `save()` 和 `get_many()` 小 Interface；
4. 加入 24 小时 TTL、16 KiB 单条上限和幂等冲突检测；
5. 使用现有 `GatedRedis`，不创建第二连接池；
6. 单测覆盖首次写、重复写、冲突、过期、Redis 故障、超限和非法输入。

### 步骤 2：分离插件数据与元数据

1. 扩展 `StructuredMetricsPayload`，新增默认空 metadata 字段；
2. PC 在内部完成 snapshot_id 一致性校验后，从资产行剥离目标标签；
3. WinSphere 停止把顶层 snapshot 字段复制到八模型资产行；
4. 保留 WinSphere manifest 原生成算法；
5. 证明其他配置插件编码结果不变。

### 步骤 3：接入发布一致性

1. 发布器拿到稳定 `publish_timestamp_ms` 后补全 Envelope；
2. 先幂等保存 metadata，再发布 VM 资产行；
3. Store 失败映射为可诊断的 publish outcome；
4. round complete 继续只在全部目标 publish clean 后产生；
5. 重试必须复用同一个 timestamp 和 metadata key；
6. 加入无动态标签的固定观测计数。

### 步骤 4：增加 NATS 查询 Interface

1. Stargazer 注册 queue-group handler；
2. 严格校验 schema、task/instance 对应关系、lookup 数量、字段长度和时间类型；
3. 只执行精确 MGET/get，不支持扫描；
4. Server RPC Adapter 增加 3 秒超时调用；
5. CMDB Reader 按接入点/云区域路由到正确 `<region>_stargazer` namespace；
6. lookup 超过 50 条时分批，任何一批失败则整体失败；
7. 测试默认区域、区域 Stargazer、多 Pod queue、missing、timeout 和错误 envelope。

### 步骤 5：迁移 PC 消费

1. PC VM parser 保留 `_metric_time`；
2. 用 PC 根行构造 metadata lookup；
3. 按 target + timestamp + PC 身份关联软件行；
4. metadata 转换为现有 `PCSnapshot`；
5. 保持完整快照可删除、partial 不删除；
6. metadata 缺失/非法时在任何图写入之前失败；
7. 必须先完成本轮所有 target 的 metadata 获取和校验，再调用 `apply_pc_snapshots()`，避免批次中途失败留下部分图写入；
8. 更新 PC fixtures 和端到端测试，不再在 VM row 中构造 snapshot 标签。

### 步骤 6：迁移 WinSphere 消费和删除安全门

1. WinSphere 格式化保留每行 sample timestamp；
2. 从根对象行构造 metadata lookup；
3. 验证固定八模型、count、唯一身份和 identity hash；
4. 保存每模型 authoritative 判定；
5. 实现 `is_authoritative_snapshot(model_id)`；
6. 多 target 任务按 target 分别验证；某模型只有所有 target 对该模型都权威时，任务级判定才为 true；
7. 验证 complete、部分非权威、空模型、缺模型、重复 identity、count/hash 错误；
8. 在验证完成前不进入 `MetricsCannula.collect_controller()` 的图副作用阶段。

### 步骤 7：删除标签与清理旧契约

1. 删除六类字段的 VM 标签复制/输出；
2. 更新现有 TODO，改为记录剩余动态业务字段，不再把 snapshot 方案标为未决；
3. 更新第一阶段总览文档；
4. 搜索生产路径，确保 snapshot 字段不再进入 VM label；
5. 保留 snapshot ID 在元数据、审计和日志关联中的业务用途。

### 步骤 8：验证、灰度和交付

1. 跑 Stargazer 定向测试和 lint；
2. 跑 Server/Enterprise 定向测试和 sqlite 测试；
3. 跑 `git diff --check`；
4. 在灰度环境连续执行至少两个完整采集周期；
5. 查询 VictoriaMetrics 验证 snapshot 标签不存在且 series 不随轮次增长；
6. 验证完整、partial、空清单和 metadata 故障下的删除结果；
7. 记录 Redis key 数、metadata hit/miss、RPC 延迟和 VM series 数。

## 12. 测试矩阵

### 12.1 Stargazer Unit/Contract

- Store save/get/TTL/duplicate/conflict；
- Redis 连接失败、池超时和超限 payload；
- NATS handler 非字典、错误 schema、task/instance 不一致、空/超量 lookup；
- PC complete/partial/empty 的资产行无 snapshot 标签，metadata 正确；
- WinSphere 八模型资产行无 snapshot 标签，manifest metadata 正确；
- 同一结果重试复用 timestamp/key；
- metadata 保存失败时不产生 round complete；
- 其他插件结构化指标输出不变；
- 日志不泄露 payload、manifest、凭据或响应正文。

### 12.2 Server Unit/Service

- RPC Adapter subject、timeout 和参数转发；
- 默认/区域 Stargazer namespace 解析；
- 50 条分批和任一批失败整体失败；
- response schema、task/target/timestamp/model 二次校验；
- PC complete 可删除、partial/缺 metadata 不删除；
- PC 空软件完整快照可安全删除旧软件；
- WinSphere 八模型完整校验；
- WinSphere 某模型 `authoritative=false` 时只禁该模型删除；
- 空权威模型允许删除旧对象；
- 缺模型、重复 resource_id、count/hash 错误整轮失败；
- 失败时 `last_synced_round` 保持旧值；
- 重复对账不重复新增或删除。

### 12.3 跨服务协议

由于当前功能无人使用且明确不兼容历史数据，本次不实现旧/新协议双读，但仍测试部署窗口的安全行为：

- 新 Server + 旧 Stargazer：metadata missing，fail closed，不删除；
- 旧 Server + 新 Stargazer：不得在运行采集任务时出现，发布步骤通过暂停任务规避；
- 新 Server + 新 Stargazer：正常对账；
- NATS 超时、Redis 故障、重复请求、响应乱序；
- 多 Stargazer Pod 共享 Redis 时任一 responder 返回一致结果。
- `test_snapshot_metadata_full_flow.py` 必须从企业版 Stargazer 源目录执行，覆盖真实企业插件解析、
  `CollectionService`、结构化 VM 编码、Redis Store、NATS handler、Server Reader 与 CMDB formatter；
- PC 完整流程覆盖新增、metadata 丢失时 fail closed、恢复后删除；WinSphere 覆盖八模型和连续两轮
  series key 稳定。

### 12.4 基数验收

对固定 PC/WinSphere 对象连续采集至少两轮：

```text
snapshot_id label count = 0
snapshot_status label count = 0
snapshot_manifest label count = 0
software_snapshot_status label count = 0
software_expected_count label count = 0
software_error_count label count = 0

仅改变 snapshot metadata 时：
series key round_1 == series key round_2
```

历史 series 不计入新增结果，应按新 Stargazer 上线时间过滤或使用全新测试任务验收。

### 12.5 建议验证命令

实施时根据实际新增测试文件补全路径，至少运行：

```bash
cd agents/stargazer
uv run pytest \
  tests/test_round_metadata.py \
  tests/test_result_publisher.py \
  tests/test_pc_inventory.py \
  tests/test_pc_discovery_contract.py \
  tests/test_winsphere_info.py \
  tests/test_winsphere_snapshot_transport.py
make lint

cd ../../server
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
  uv run pytest \
  apps/rpc/tests/test_misc_forwarding.py \
  apps/cmdb/tests/test_round_metadata.py \
  apps/cmdb/tests/test_pc_snapshot_parser.py \
  apps/cmdb/tests/test_pc_reconcile_service.py \
  apps/cmdb/tests/e2e/test_pc_discovery_pipeline.py \
  ../enterprise/server/apps/cmdb_enterprise/tests/test_winsphere_collect.py \
  apps/cmdb/tests/e2e/test_winsphere_enterprise_pipeline.py \
  --no-cov

# 跨仓库完整流程：从企业版 Stargazer 权威源目录执行，复用 Community 运行时和 Server 测试依赖
cd ../enterprise/agents/stargazer
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
DJANGO_SETTINGS_MODULE=settings \
PYTHONPATH=../../../server/.venv/lib/python3.12/site-packages:../../../server:../../../enterprise/server:../../../agents/stargazer:. \
../../../agents/stargazer/.venv/bin/python -m pytest -c ../../../server/pytest.ini \
  ../../../server/apps/cmdb/tests/e2e/test_snapshot_metadata_full_flow.py \
  -q --no-cov --nomigrations
```

最后运行仓库根目录 `git diff --check`。若 `uv` 不在 PATH，使用工作区已安装的对应虚拟环境执行相同测试，
不得为了测试启动整套 PostgreSQL、Redis 或 NATS。

## 13. 上线步骤

本次采用硬切换，不双写、不双读、不回填：

1. 确认没有正在运行的 PC/WinSphere 采集；
2. 暂停 PC/WinSphere 周期任务；
3. 部署 Server Community 与 Enterprise 代码；
4. 部署 Stargazer Community 与 Enterprise 插件代码；
5. 对每个目标区域执行 metadata NATS RPC smoke test；
6. 使用新的测试任务各运行一轮 PC complete、PC partial、WinSphere complete；
7. 核对 CMDB 对象数、关系数、删除数、Redis metadata hit 和 VM 标签；
8. 再运行第二轮，确认 series key 稳定；
9. 恢复 PC/WinSphere 周期任务；
10. 观察至少两个业务周期后完成发布。

不需要执行数据库迁移、Redis 初始化、NATS stream/bucket 声明或部署配置修改。

## 14. 回滚步骤

1. 再次暂停 PC/WinSphere 周期任务；
2. 同时回滚 Server 与 Stargazer，避免旧 Server 消费无 snapshot 标签的新数据；
3. 不删除 Redis metadata key，让 TTL 自动回收；
4. 不清理 VictoriaMetrics，不修改 CMDB 现有资产；
5. 用旧链路新建测试任务完成一轮验证后恢复周期任务。

回滚会重新产生 snapshot 动态标签，因此只能作为短期恢复手段；历史新旧 series 都由 VM 保留策略自然清理。

## 15. 验收标准

全部满足才算完成：

1. 六类 snapshot 字段在新 VM 数据中全部消失；
2. PC/WinSphere 连续两轮仅 snapshot metadata 变化时 series key 不变；
3. 完整 PC 软件快照仍可新增、更新和删除；
4. PC partial、metadata missing、count 错误均不删除；
5. WinSphere 八模型字段和关系保持不变；
6. WinSphere 删除权限由通过验证的 manifest authoritative 决定；
7. metadata/VM 任一侧失败都不会发布可消费的完成轮次；
8. NATS/Redis 故障不会造成图数据误删或游标前移；
9. Redis/NATS/日志均不包含完整资产 payload 或凭据；
10. Community、Enterprise 定向测试、lint 和 diff 检查全部通过；
11. 无数据库迁移、无部署配置变更、无历史数据处理。

## 16. 已确认决策

本次实施已按以下决策锁定：

1. 本次范围严格限定为表中的 PC/WinSphere 六类 snapshot 标签；
2. Redis metadata 默认 TTL 使用 24 小时代码常量；
3. metadata 缺失或 RPC 失败时整轮 fail closed，不做任何 CMDB 图写入；
4. 采用暂停任务后的硬切换，不做历史兼容、双写或回填；
5. `channel_config_version`、动态业务字段和 `0`/`False` 正确性问题继续留待后续独立阶段。

## 17. 实施结果（2026-08-31）

已完成代码实施，尚未执行本文档第 13 节的部署与灰度验收：

1. Stargazer 新增有界 `RoundMetadataStore`，复用现有 `GatedRedis`，实现 24 小时 TTL、
   16 KiB 单条上限、NX 幂等写和冲突拒绝；
2. PC/WinSphere 资产行不再携带本文档列出的 snapshot 动态标签，小型控制元数据改走
   `StructuredMetricsPayload.round_metadata`；
3. 发布顺序锁定为“元数据先落 Redis，资产指标后入 VM”；需要元数据的模型缺少元数据时
   按永久发布失败拒绝，Redis 短暂故障进入现有有限重试；
4. Stargazer 新增 NATS 精确批量查询 handler，Server 新增按区域路由、50 条分批、3 秒超时和
   envelope 二次校验；
5. PC 按 `collection_target + publish_timestamp + pc_inst_name` 关联软件，元数据异常时在
   `apply_pc_snapshots()` 前失败；
6. WinSphere 按固定八模型验证 count、`resource_id` 唯一性、identity hash 和 authoritative，
   并实现现有 `Management` 删除安全 Interface；
7. 企业版 Stargazer 权威源已同步 PC/WinSphere 生产者改动；WinSphere Collector 对齐异步插件合同，
   Server 查询与解析对齐结构化传输实际生成的 `winsphere_*_info` 指标名；
8. 无数据库迁移、无新端口、无环境变量或部署配置改动，无历史数据兼容与回填。

本地定向验证覆盖 Store、发布顺序、NATS handler、RPC 转发、PC 完整/部分/空快照对账、
WinSphere 八模型完整性与两条 fail-closed 副作用边界。新增的跨仓库完整流程用例已验证：

- PC 三轮生命周期：新增软件、metadata 丢失时不删除、metadata 恢复后安全删除；
- WinSphere 两轮生命周期：八模型采集、manifest 查询/校验、关系格式化和 series key 稳定；
- 两条链路生成的 VM 行均不包含六类 snapshot 动态标签。

环境灰度仍需按第 13 节执行。

## 18. 备选方案与拒绝理由

| 方案 | 结论 | 原因 |
|---|---|---|
| 直接删除 snapshot 标签，不补元数据 | 拒绝 | 无法证明完整性，差集删除可能误删 |
| PromQL `without(snapshot_id)` | 拒绝 | 只修展示，不降低存储基数，且丢失快照边界 |
| 把完整 JSON 放入 label | 拒绝 | 仍是无界高基数标签 |
| Redis 保存完整 PC/WinSphere 资产数据 | 拒绝 | 复制完整数据、占用内存，偏离本次目标 |
| CMDB 直接连接 Stargazer Redis | 拒绝 | 跨服务共享 Redis 和凭据，扩大部署耦合 |
| Object Store + durable ready 事件 | 本次不采用 | 能承载完整快照，但本次只需迁移小型控制元数据，复杂度过高 |
| 小型 Redis metadata + NATS 精确查询 | 采用 | 复用现有基础设施，代码改动可控，且不复制完整资产数据 |
