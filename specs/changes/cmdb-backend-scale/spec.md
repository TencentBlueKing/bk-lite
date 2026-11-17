# CMDB 后端规模收敛

Status: implemented

日期：2026-11-09

本次只记录已确认的方案，不改代码。收到单独的实施指令后再改。

## Problem Statement

实例、关联边和采集资产变多之后，自动关联、关联查询、采集守门、订阅检查、实例拓扑、展示名同步和唯一性校验会把整模型、整张图或整段变长路径装进进程。一次规则重算、一次关联打开、一轮 5 分钟任务或一次保存唯一性规则，时间和内存随数据量放大，周期任务超时后从头再来，队尾数据一直轮不到。

## Solution

重算、扫描和校验按页推进，进度落库，到时间或到条数就停，下一轮从游标继续。图查询只收窄 FalkorDB：关联退路保留实例 UUID，实例拓扑一跳一跳扩展并封顶。不带新参数的既有接口保持原来的返回。Neo4j 驱动不改。

## User Stories

1. As a CMDB 管理员, I want 自动关联在大模型上按页重算并在中断后接着跑, so that 改一条规则或一批目标实例不会把两端实例整表装进内存
2. As a CMDB 管理员, I want 打开实例关联时只查这个实例自己的边, so that 没有边或旧边缺模型属性时也不会扫全图
3. As a CMDB 管理员, I want 采集守门从上次停下的任务继续，并且每轮派发有上限, so that 队尾任务不会一直排不上，单任务对账也不会把该任务的全部资产全文留下
4. As a CMDB 管理员, I want 订阅按变更窗口判断，检查超时后下一轮跳过而不是叠跑, so that 命中大量实例的规则不会每 5 分钟重装整份实例和关联
5. As a CMDB 管理员, I want 打开实例拓扑时按层展开并在节点过多时停住, so that 图库不必先枚举起点出发的全部变长路径
6. As a CMDB 管理员, I want 组织名或用户显示名同步中断后从上次成功的实例继续, so that 超时重试不会反复重写开头的实例
7. As a CMDB 管理员, I want 保存唯一性规则时按页核对规则字段, so that 大模型上保存一条规则不会把实例全文一次拿回来

## Implementation Decisions

- 落地顺序：关联查询、实例拓扑、自动关联、采集守门、订阅、展示名同步、唯一性规则。
- 图库只改 FalkorDB。新的查询形状、跳数上界和空条件收窄都落在 FalkorDB 客户端。Neo4j 驱动的 `query_edge`、`query_topo`、`query_topo_lite` 保持原样，不补 Neo4j 语句，也不为 Neo4j 写用例。运行在 Neo4j 上时，沿用改动前的图查询行为。
- 服务层的游标、分页、锁和预算仍然做。它们通过现有图客户端读 FalkorDB，不新增 Neo4j 分支。
- 不带新参数的关联、拓扑和订阅接口保持现有调用方的返回字段。
- 前端规模文档 `cmdb-frontend-scale` 已经覆盖关联列表分页、应用拓扑和网络拓扑节点上限。本次不改那份范围。应用拓扑仍由那份文档封顶 100。本文件的实例拓扑是 `topo_search` 这条树。

### 自动关联全量重算

当前路径：

1. `POST /cmdb/api/model/{model_id}/auto_association_rules/`、`PUT` 和 `DELETE /cmdb/api/model/{model_id}/auto_association_rules/{model_asst_id}/{rule_id}/` 进入 `ModelManage.save_model_auto_relation_rule`、`update_model_auto_relation_rule`、`delete_model_auto_relation_rule`。删除模型关联进入 `model_association_delete`。这些入口都调用 `schedule_rule_auto_relation_full_sync`，把 `model_asst_id` 写入 `AutoRelationPending`。
2. 实例创建、更新、导入、采集落库和节点同步调用 `schedule_instance_auto_relation_reconcile`，写入 `instance_id`。
3. 每 5 分钟，队列 `background` 上的 `reconcile_auto_relation_pending_task` 调用 `drain_auto_relation_pending`。单飞锁 30 分钟。
4. `_drain_instance_rows` 经 `_claim_pending` 认领后立刻删掉待重算行，再调用 `AutoRelationRuleReconcileService.reconcile_for_instances`。源侧规则逐实例进入 `reconcile_source_instance`。实例处在目标侧时，`schedule_rule_auto_relation_full_sync` 把整条规则登记成全量。
5. `_drain_rule_rows` 对每条规则调用 `full_sync_rule`。`_query_instances_by_model` 按 500 条翻页，翻完拼成源、目标两个完整列表。先对全部源跑 `phase="delete"`，再跑 `phase="create"`。1:n 和 1:1 占用放在本次进程的 `target_claims`。
6. 每个源在 `reconcile_source_instance` 里新建一次 `GraphClient`，调用 `_query_existing_edges_for_source`。删一条边新建一次连接。建一条边先 `InstanceManage.check_asso_mapping`，再新建一次连接执行 `create_edge`。
7. `TargetSnapshot.candidates` 对精确匹配和忽略大小写用内存索引。`contains` 返回全部目标。

改动：

- `full_sync_rule` 按源实例 id 续跑，一页 500。一页内共用一个 `GraphClient`，这一页已有自动边一次取回。精确匹配只取这一页源字段可能命中的目标。`contains` 和忽略大小写把目标按 500 条写入临时匹配表，源再按页查。1:n 和 1:1 占用记在表上，源按 id 升序。每一页先删不再匹配的边，再建新边。
- `AutoRelationPending` 增加游标和阶段。认领时不先删行，这一页成功才前移游标。每轮最多 2000 个源或 60 秒。单飞锁改为大约 5 分钟，覆盖一页写入，不再覆盖一整轮全量。
- 目标实例变更不再升级成整表全量。精确匹配只重算字段能对上的源，以及已经连着这些目标的源。旧值从这次 `ChangeRecord.before_data` 取。`contains`、忽略大小写，或本轮变更目标超过该规则目标总数的一成，才退回分页全量，并且只退回一次。
- 临时匹配表随规则跑完或游标清零删除。FalkorDB 上的边写入仍走现有 `create_edge` 和删除边。

### 关联查询退路

当前路径：

1. `GET /cmdb/api/instance/association_instance_list/{model_id}/{inst_uuid}/` 进入 `InstanceViewSet.instance_association_instance_list`，再进 `InstanceManage.instance_association_instance_list_by_uuid`。
2. `GET /cmdb/api/instance/instance_association/{model_id}/{inst_uuid}/` 进入 `InstanceViewSet.instance_association`，再进 `instance_association_by_uuid`。
3. 批量入口是 `instance_association_map_by_uuids`。OpenAPI 关联、NATS 关联查询、服务树、IPAM、机柜、应用拓扑 `ApplicationResourceOverviewService.build_application_topology`，以及订阅 `SubscriptionTriggerService._get_relation_instances`，都走到这三条。
4. 三条都先按 `src_inst_uuid` 或 `dst_inst_uuid` 加上模型调用 `GraphClient.query_edge`。结果为空时再调用 `query_edge(INSTANCE_ASSOCIATION, [])`。FalkorDB 对空条件生成 `MATCH p=(a)-[n]->(b) RETURN p`，没有 `LIMIT`。返回后在 Python 里按端点 UUID 和 `model_id` 过滤。
5. 订阅先走 `instance_association_map`。批量失败后，`_get_relation_instances` 对每个实例调用 `instance_association`，每个实例都可以再触发一次全图扫描。

改动：

- FalkorDB 的第二次查询只去掉 `model_id`，保留端点 UUID。单实例用等于，批量用 `IN`。返回后再按边或端点上的模型过滤。UUID 查询也是空的，就返回空列表。
- 缺 UUID 的历史边继续只由离线命令 `migrate_cmdb_instance_uuid_refs` 处理。
- `_get_relation_instances` 不再逐实例回退。批量失败就让本轮规则失败，`last_check_time` 不前移。
- 带 `model_asst_id` 的分页查询维持前端规模文档的约定：只按当前实例和这个关联过滤，查不到返回空页。
- Neo4j 的 `query_edge` 不改。上述收窄只在 FalkorDB 客户端生效。

### 采集守门和单任务对账

当前路径：

1. 每 5 分钟 `sync_collect_tasks_gate` 把 `after_id` 设为 0，按 `CollectModels.id` 每页 `GATE_PAGE_SIZE = 200` 扫描。配置文件、K8s 和节点同步系统任务排除在外。软超时 240 秒，硬超时 270 秒。
2. 每一页 `query_latest_completed_rounds` 查 VictoriaMetrics 完成标记，`decide_gate_action` 决定 `sync_round` 或 `sync_compat`。命中的任务 `sync_collect_task.delay`。网络任务再 `maybe_replay_topology_from_gate`。`after_id` 只活在本次进程。
3. `sync_collect_task` 经 `_claim_collect_task_execution` 领取。配置文件任务直接返回。其余走 `JobCollect.main` 或 `ProtocolCollect.main`。
4. `ProtocolCollect.main` 进入 `RegisteredCollect`，`BaseCollect.run` 创建 `MetricsCannula`，`reconcile_task_assets=True`，再 `collect_controller`。VMware 走 `collect_vmware`，其余走 `_collect_models`。
5. 核对路径 `_query_task_assets` 把该任务已有资产放进 `already_data`。名称和 IP 候选按 200 条分段。不核对时 `query_entity` 不带分页。`Management` 用这份旧数据和本轮结果做对比、更新和差集删除。
6. 完整 `collect_data` 和 `format_data` 写回 `CollectModels`。节点同步有 `_bound_node_mgmt_raw_data`，其他采集类型没有。`collect_digest` 只记增删改数量。`sync_collect_task` 没有和守门同级的软超时。

改动：

- 守门游标落到一行状态，记下扫到的任务 id 和本轮开始时间，每页提交。超时后下一轮从这行继续，扫完一轮清零。每轮派发上限默认 100，用环境变量配置。没派发到的任务不改 `last_synced_round`。
- `_collect_models` 读图只取 `_id`、`inst_uuid`、`inst_name`、唯一键、`collect_task`、`collect_time`、`organization` 和本插件会改的属性，按 `_id` 每 500 条前进。差集删除用键集合相减。
- `format_data` 复用节点同步上限：最多 5 万行、序列化后最多 64MB，超出丢掉。`collect_digest` 保留裁剪前的数量。
- `sync_collect_task` 加上同级软超时。超时记失败并释放领取，不写差集删除。

### 订阅检查

当前路径：

1. 每 5 分钟 `check_subscription_rules` 调用 `SubscriptionTaskService.check_rules`。有事件时再派发 `send_subscription_notifications`。任务本身没有单飞。
2. `check_rules` 取出全部启用的 `SubscriptionRule`，逐条 `select_for_update`，再 `SubscriptionTriggerService.process`。
3. `_get_current_instances` 经 `InstanceManage.instance_list` 每页 `INSTANCE_QUERY_PAGE_SIZE = 1000` 拉取，页结果拼进 `all_instances`。
4. 含关联触发时，对每个关联模型调用 `_get_relation_instances`，里面是 `instance_association_map`。失败后再逐实例 `instance_association`。
5. 然后才是 `_check_attribute_change`、`_check_relation_change`、`_check_expiration`、`_check_config_file`。`_update_snapshot` 把全部实例 id 和每个实例的关联列表写回快照，成功后才前移 `last_check_time`。

改动：

- `check_subscription_rules` 改为单飞，重复触发直接跳过。每轮按规则 id 续跑，最多 20 条或 60 秒。`last_check_time` 仍只在该规则成功后前移。
- 属性、新增、删除直接查 `ChangeRecord`，条件带 `model_id`、变更类型和 `created_at`。指定实例的规则把 UUID 放进查询。条件筛选的规则，只把窗口里出现过的实例再套进筛选条件。显示名从 `after_data` 或 `before_data` 取。
- 关联用已有的 `create_edge`、`delete_edge` 记录判断边增减，用对端模型的属性变更判断关联实例字段变化。快照按边增量维护，不再每轮调用 `instance_association_map`。
- 到期和配置文件仍看当前属性，保留分页。扫完一页就判断，不把全部实例留到最后。规则没勾这两类时不扫描。快照继续只存 id 和关联 UUID。

### 实例拓扑

当前路径：

1. `GET /cmdb/api/instance/topo_search/{model_id}/{inst_uuid}/` 进入 `InstanceViewSet.topo_search`，深度写死 3，再进 `InstanceManage.topo_search_lite_by_uuid`。
2. `POST /cmdb/api/instance/topo_search_expand` 进入 `topo_search_expand_post`，深度写死 2，再进 `topo_search_expand_by_uuid`。
3. 两者把 UUID 换成图 id，打开一个 `GraphClient`，调用 `query_topo_lite`。
4. FalkorDB 的 `query_topo_lite` 把深度加 1 得到 `probe_depth`。深度 3 时语句是 `MATCH p=(n)-[*1..4]->(m) WHERE ID(n) = $inst_id RETURN p`，反方向再查一次。`format_topo_lite` 在 Python 里按深度裁树，并处理 `exclude_ids`。
5. `_filter_topology_result` 做权限过滤，`_transport_topology_result` 把图 id 转成对外 UUID。
6. FalkorDB 的 `query_topo` 仍是不带上界的 `[*]`。这两个接口当前没有调用它。

改动：

- 只改 FalkorDB 的 `query_topo_lite`：一跳查询，按深度循环。每层用上一层节点 id 做 `IN`，同一轮用一个 `GraphClient`。环用已访问集合剪掉。节点上限 100。到达上限停止扩展，节点保留现有的还有更多标记。返回仍是现在的树，两个接口的字段不变。
- FalkorDB 的 `query_topo` 改为调用这个有上限的实现，深度固定 3。FalkorDB 不再发出无上界变长路径。
- Neo4j 的 `query_topo_lite` 和 `query_topo` 不改。

### 组织 / 用户展示名同步

当前路径：

1. NATS `sync_display_fields` 调用 `sync_display_fields_for_system_mgmt`，再 `sync_cmdb_display_fields_task.delay`。任务软超时 240 秒，硬超时 300 秒，最多重试 3 次。
2. 任务用 `UniqueWriteLockService.serialize("cmdb-display-field-sync", lease_seconds=310)` 串行。锁内先 `refresh_display_sync_data`，再 `DisplayFieldSynchronizer.sync_all`。
3. `sync_all` 从 `ExcludeFieldsCache.get_model_fields_mapping` 找出带组织或用户字段的模型。游标从空开始，按 `id > cursor` 每次取 `_get_sync_batch_size()`，默认 500。每一页 `_update_instance_page`，再 `batch_update_node_property_values` 写 `_display`。游标只在这次循环里。
4. `SoftTimeLimitExceeded` 释放锁。Celery 按 5 秒后重试，`sync_all` 再次从空游标开始。

改动：

- 游标放到现有锁记录或同一行状态里。每批写成功就提交游标。任务在 180 秒时主动停下，释放锁，再投递下一次，从游标往后扫。软超时如果先到，重试读的也是这枚游标。全部模型扫完再清游标。计数按批累加到状态行。

### 保存唯一性规则

当前路径：

1. `POST /cmdb/api/model/{model_id}/unique_rules/` 和 `PUT /cmdb/api/model/{model_id}/unique_rules/{rule_id}/` 进入 `ModelViewSet.model_unique_rules` 或 `model_unique_rule_detail`，再进 `ModelManage.create_model_unique_rule`、`update_model_unique_rule`。
2. `create_unique_rule`、`update_unique_rule` 进入 `_apply_unique_rule_mutation`，先拿 `UniqueWriteLockService.hold`，锁键 `cmdb:unique-rules:{model_id}`。
3. `build_unique_rule_context` 读取现有规则，`validate_unique_rule_payload` 校验字段。`_raise_conflict_if_rules_invalid` 调用 `validate_unique_rules_against_existing_instances`。
4. 实例来自 `_query_model_instances`：一次 `query_entity`，条件只有模型 id，不带分页，也不限制字段。冲突则不调用 `_save_unique_rules`。没有冲突才 `set_entity_properties` 写 `unique_rules`，并失效字段缓存。
5. 删除规则不扫实例。

改动：

- `_query_model_instances` 按 `_id` 每 500 条读取，字段只含 `_id`、`inst_uuid` 和规则里的字段。内存里只留「签名到第一个实例 id」。同一签名第二次出现就记录冲突。扫完后仍抛出现在的第一个冲突。任一重复仍拒绝保存。

## Testing Decisions

测试锁外部行为：图查询语句和过滤条件、分页游标、返回形状、处理条数、锁和预算。图库替身只模拟 FalkorDB，记录语句、条件和返回页。不连接 Neo4j，也不断言 Neo4j 语句。优先沿现有自动关联、关联查询、采集守门、订阅、拓扑、展示名和唯一性规则测试的服务入口写，不新开一层只为计数的内部探针。

各任务原有行为用例保持：

- 自动关联：一页中断后续跑，边不重复。一千个目标变更只重算命中的源。两个 `reconcile_auto_relation_pending_task` 重叠时，第二轮不写第一轮已经占住的页。增删幂等、1:n 换源、歧义跳过保持不变。
- 关联查询：图里有无关边时，FalkorDB 语句必须带 UUID，次数固定为两次，返回只含该实例自己的边。无边实例返回空，且不出现无 `WHERE` 的 `MATCH`。10 个实例同时查询时，各自条件只带自己的 UUID。订阅批量失败时，空条件 `query_edge` 次数为 0。默认响应字段不变。
- 采集：守门在第 3 页软超时后，下一次从第 3 页末尾的 id 继续，已派发任务不再派一次。对账的 `query_entity` 带 `LIMIT` 和字段列表。超限明细被裁剪，摘要里的新增、更新、删除仍是裁剪前的数量。两个守门重叠时，第二轮不从 0 重扫已经提交的页。
- 订阅：只订阅属性变更时，图查询次数为 0，`ChangeRecord` 查询带时间窗。只有一条边变更时，只更新这一个实例的快照项。任务跑过 5 分钟时，下一轮直接跳过。两轮重叠时，第二轮不前移第一轮还没成功的规则的检查时间。
- 实例拓扑：FalkorDB 查询次数等于深度，返回节点数不超过 100，响应带截断标记，语句不是 `[*]` 或 `[*1..n]`。两个实例同时打开时，各自查询只带自己的起点。树字段保持不变。
- 展示名：第 3 批之后模拟软超时，下一次 `query_entity` 的条件带 `id > 第 3 批最后一个 id`，最终计数等于全部命中实例数。两个任务重叠时，第二轮在锁还被持有时跳过，不从 0 重写。
- 唯一性：两处字段重复时，每次 `query_entity` 都带 `LIMIT` 和字段列表，抛出的冲突实例与一次装入全表的结果相同。同一模型两次保存同时进行时，第二轮等锁，各自只保留自己的签名表。

规模并发矩阵是本次新增的必测项。每一项都在 1000、5000、10000 条实例上各跑一遍。替身按这个数量装入实例并按页返回，断言不随条数变成整表或全图。10000 条再加一轮重叠执行。

| 任务 | 1000 / 5000 / 10000 条怎么装 | 三个规模都要成立的断言 |
|---|---|---|
| 自动关联 | N 个源实例、N 个目标实例，精确匹配只有少数命中 | FalkorDB 读取按页，每页不超过 500。精确匹配不装入全部目标。两轮重叠不重复写同一页 |
| 关联查询 | N 条与被查实例无关的边，再查 1 个实例 | FalkorDB 语句带该实例 UUID，次数为 2。无边返回空，且不出现无 `WHERE` 的 `MATCH` |
| 采集对账 | 一个采集任务名下 N 条资产 | `query_entity` 带 `LIMIT` 和字段列表。`format_data` 不超过 5 万行、序列化后不超过 64MB |
| 订阅 | 一条规则命中 N 个实例，只订阅属性变更 | 图查询次数为 0。`ChangeRecord` 查询带时间窗。10000 条上两轮重叠时，第二轮跳过 |
| 实例拓扑 | 图中共 N 个实例，起点向外连出多层 | FalkorDB 查询次数等于深度，返回节点不超过 100，语句不是变长路径。10000 条上两个起点同时打开，各自只带自己的起点 |
| 展示名同步 | N 条带组织或用户字段的实例 | 中断后从已提交游标继续。最终计数等于 N。10000 条上两轮重叠时，第二轮不从 0 重写 |
| 唯一性规则 | 一个模型 N 条实例，其中两处规则字段重复 | 每次查询带 `LIMIT` 和规则字段。冲突实例与全表扫描结果相同。10000 条上两次保存同时进行时，第二轮等锁 |

Neo4j 不进入这张矩阵。

## Out of Scope

- Neo4j 驱动及其 `query_edge`、`query_topo`、`query_topo_lite`。不为 Neo4j 改语句、补测试或做规模矩阵。
- CMDB 用户列表，以及用户列表接口的全局上限。
- IPAM、节点主机同步、导出和迁移。
- 前端规模文档里的关联列表分页、扫描命中、下拉远程搜索、高级筛选、配置文件版本、应用拓扑和网络拓扑节点上限。网络拓扑保持现有的一跳和 100 个节点上限，本次不重做。
- 全局分页对 `page_size` 为 `None`、`0` 或 `-1` 时返回整表的行为。
- 缺 UUID 历史边的在线修复。仍只由离线命令 `migrate_cmdb_instance_uuid_refs` 处理。

## Further Notes

方案已实施。图库改动只在 FalkorDB。规模矩阵见 `server/apps/cmdb/tests/test_cmdb_scale_matrix.py`，1000、5000、10000 均通过。精确匹配的目标实例变更仍登记整条规则的分页重算，没有单独的受影响源列表。订阅的关联增量快照尚未改成边变更记录，属性、新增、删除已走变更窗口。
