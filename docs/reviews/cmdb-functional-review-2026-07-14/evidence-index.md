# CMDB 全功能生产级审查证据索引

## 不可变初始基线

| 字段 | 值 |
|---|---|
| 初始 commit | `4ed0fba9928ec1d45a406789d1287294988e184a` |
| 初始分支 | `codex/cmdb-functional-production-review` |
| 初始工作树状态 | clean（`git status --short` 无输出） |
| 审查日期 | 2026-07-14（Asia/Shanghai） |
| 环境说明 | 本地隔离 worktree；审查阶段只读业务代码，仅允许写入审查报告；不把执行期间产生的提交回写为初始基线。 |
| 基线命令 | `git rev-parse HEAD && git branch --show-current && git status --short` |

## 索引约定

- 主 Finding ID 全局使用 `CMDB-FNN`，其中 `NN` 为从 `01` 开始的两位递增序号；编号一经分配不复用。
- 同一根因跨多个功能域时只登记一个主 Finding，其他域通过 ID 引用，不重复计数或抬高严重级别。
- `结果` 记录命令退出状态及关键摘要；`覆盖率` 只登记真实输出，无法获得时明确写入 `未验证项`。
- 以下字段在对应功能域审查开始后以代码、测试和命令证据替换“待补充”，不得用架构文档推断替代真实验证。

## 01 模型治理

- 业务承诺：分类/模型/字段/唯一规则/自动关联规则/展示字段形成可授权、可校验、可恢复的图主数据；`PublicEnumLibrary` 是 ORM 主数据，模型 `attrs.option` 与实例 `_display` 是它的下游投影。字段分组同时写 ORM `FieldGroup` 与图 `MODEL.attrs.attr_group`，当前实现未声明权威主数据方，主从关系仍未确认。Enterprise 能力经社区注册表委派；HEAD 存在 Enterprise 子模块，但本 worktree 未初始化。
- 入口：`ClassificationViewSet`、`ModelViewSet`、`FieldGroupViewSet`、`PublicEnumLibraryViewSet`；异步入口 `sync_public_enum_library_snapshots_task`；企业委派入口 `model_ops.extensions.get_model_enterprise_extension()`。
- 核心调用链：分类 CRUD → `ClassificationManage` → `GraphClient` 的 `CLASSIFICATION`；模型/字段 CRUD → `ModelManage` → `MODEL.attrs`/实例属性；唯一规则 HTTP → `unique_rule` → `MODEL.unique_rules`；自动关联规则 HTTP → 校验双端 attrs → `MODEL_ASSOCIATION.auto_relation_rule` → 全量关系同步；字段分组 HTTP → `FieldGroupService` → ORM `FieldGroup` + `MODEL.attrs.attr_group`；公共枚举 HTTP → ORM `PublicEnumLibrary` → Celery → 模型枚举快照；展示字段由模型 attrs 与实例 `_display` 冗余属性共同承载。
- 外部依赖：FalkorDB 兼容 `GraphClient`、Django ORM/多数据库 JSONField、Celery broker/worker、SystemMgmt 组织与用户 RPC、`model_ops` Enterprise 注册表。
- 关键测试：`test_classification_service.py`、`test_model_service_advanced.py`、`test_unique_rule_crud.py`、`test_auto_relation_rule_validate.py`、`test_field_group_service.py`、`test_public_enum_service.py`；额外复现 `test_model_views.py::test_model_attr_delete_ok`。
- 执行命令：简报原始六文件 `uv run pytest -q -o addopts='' ...`；受控环境重跑在同命令前补充 `SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb_task2_review.sqlite3 ENABLE_CELERY=true`；额外单测使用相同环境运行 `apps/cmdb/tests/test_model_views.py::test_model_attr_delete_ok`。
- 结果：沙箱首次退出 2（uv cache 无权限）；受控原始命令退出 1（23 passed、79 setup errors，PostgreSQL `DB_NAME=None`）；显式 SQLite 环境六文件退出 0（102 passed in 2.83s）；字段删除单测退出 1（1 failed in 2.26s，SQLite `JSONField contains` 不支持）。
- 覆盖率：未测量；简报命令没有 `--cov`，不能声称达到相关模块 80% 或核心路径 90% 目标。
- 未验证项：Enterprise 子模块存在但未初始化，overlay 源码在本次审查环境不可用；本域仅完成社区委派契约审查，overlay 行为验证属于未完成范围。真实 FalkorDB 故障/恢复、Celery broker 故障与重投、公共枚举大规模实例 `_display` 重建、PostgreSQL/MySQL JSON 行为和并发写未执行。主 Findings：`CMDB-F01`–`CMDB-F07`，其中 `CMDB-F04` 为 P0，详见 [01-model-governance.md](01-model-governance.md)。

## 02 实例写入

- 业务承诺：实例 create/update/delete/batch 在组织与实例权限内执行字段、枚举、唯一规则和文件校验；相同幂等请求只产生一次图事实。跨 FalkorDB、Django ORM 文件/审计台账和自动关系投影的失败必须可核对、可重试且旧 Worker 不得覆盖新 owner。Task 2 的 `CMDB-F01`/`CMDB-F02` 分别提供唯一规则与自动关系上游契约；自动关系把 broker ack 当业务完成与 Task 2 `CMDB-F04` 同根因，本域仅登记跨域证据，不重复计数。
- 入口：`InstanceViewSet.create/partial_update/destroy/instance_batch_update/instance_batch_delete`；Service 入口 `InstanceManage.instance_create/instance_update/batch_instance_update/instance_batch_delete`；恢复入口 `reconcile_cmdb_operations_task`；Enterprise 门面 `instance_ops.extensions`。
- 核心调用链：单 create/update → 菜单/组织/实例权限 → `OperationService.start` → `GRAPH_WRITING` owner → 唯一签名锁 → 带 `_cmdb_operation_id` 图写 → `GRAPH_COMMITTED` + change_record/auto_relation Outbox → lease 消费 → COMPLETED；Beat 每 5 分钟核对过期图写和重投 Outbox。批量更新/删除直接编排图、文件、审计和自动关系，不进入 Operation。
- 外部依赖：FalkorDB/GraphClient、Django ORM/SQLite 测试库、Celery broker/worker/Beat、Enterprise 文件台账与对象存储、SystemMgmt 组织权限。
- 关键测试：`test_instance_service_crud.py`、`test_operation_service.py`、`test_operation_outbox.py`、`test_unique_write_lock.py`、`bdd/test_instance_crud_bdd.py`；静态补充审查 `test_instance_views.py` 与自动关系 task/调度实现。
- 执行命令：`SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task3.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_instance_service_crud.py apps/cmdb/tests/test_operation_service.py apps/cmdb/tests/test_operation_outbox.py apps/cmdb/tests/test_unique_write_lock.py apps/cmdb/tests/bdd/test_instance_crud_bdd.py --cov=apps.cmdb.services.instance --cov=apps.cmdb.services.operation_service --cov-report=term-missing`。
- 结果：沙箱首次退出 2（uv cache 无权限，未收集）；受控权限原命令退出 1，49 passed、1 failed in 28.76s。唯一失败 `test_instance_batch_delete_ok` 是历史 #0076：夹具未 mock incoming 自动关系图查询而连接空 Neo4j URI，不是本次回归。
- 覆盖率：`instance.py` 37%（905/567 missed）；`operation_service.py` 82%（192/34 missed）；合计 45%（1097/601 missed）。实例服务和功能域合计未达质量门槛。
- 未验证项：Enterprise 子模块未初始化，真实文件台账/GC/overlay 行为不可用；未执行真实 FalkorDB、真实 broker/worker 崩溃、并发进程、MySQL/PostgreSQL 和大规模资源验证。旧 Outbox Worker owner 隔离已有测试；旧图 Worker 晚到、5 次 FAILED、批量部分失败和删除副作用没有测试。本域主 Findings 为 `CMDB-F08`、`CMDB-F10`–`CMDB-F13`（P0 1/P1 2/P2 2）；自动关系异步完成语义引用 `CMDB-F04`，详见 [02-instance-write.md](02-instance-write.md)。

## 03 查询与拓扑

- 业务承诺：实例列表、全文、关联、拓扑、导入导出与附件查询必须同时满足菜单权限、当前组织/子组织范围和真实模型实例权限；关系两端均需授权，隐藏父级及其子树 fail-closed；分页稳定且所有查询有硬资源上限；Neo4j/FalkorDB 具备同一参数、排序和错误契约。导入裸批写的唯一/恢复问题引用 Task 3 `CMDB-F10/CMDB-F11`，不重复计数。
- 入口：`InstanceViewSet.search/retrieve/fulltext_search/fulltext_search_stats/fulltext_search_by_model`、`instance_association_instance_list/instance_association`、`topo_search/topo_search_expand_post/network_topology`、`inst_import/inst_export`、`upload_file/download_file/delete_file`；Service/工具入口 `InstanceManage`、`Import`、`Export`、`topology_theme`。
- 核心调用链：列表/全文 → 按当前 model 构建 permission map → GraphClient → 驱动 CQL，Neo4j/FalkorDB 的 legacy fulltext 均无 SKIP/LIMIT；关联查询 → 只校验中心实例 → `instance_association_instance_list(return_entity=True)` 返回对端实体，`instance_association` 返回边元数据；通用/网络拓扑 → 中心实例权限 → 中心 model permission map → 跨模型节点后置裁剪；导入 → 组织单元格范围校验 → 全模型 `batch_save_entity` → 全量关联名称映射/建边 → 审计/自动关系；导出 → 根实例权限图查询 → openpyxl → `format_inst_asst_name` 逐根实例查询并回填关联名称；附件由 Enterprise 门面接收实例读权限 callback。
- 外部依赖：FalkorDB/Neo4j 双图驱动、SystemMgmt 权限/组织 RPC、Django ORM Group、openpyxl、Enterprise instance file overlay/MinIO、审计与 Celery 自动关系。
- 关键测试：`test_instance_views.py`、`test_search_inst_batch.py`、`test_topology_theme.py`、`test_import_organization.py`、`test_import_asso_export.py`、`test_permission_util.py`；额外静态/直接验证排序驱动契约。
- 执行命令：`SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task4-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_instance_views.py apps/cmdb/tests/test_search_inst_batch.py apps/cmdb/tests/test_topology_theme.py apps/cmdb/tests/test_import_organization.py apps/cmdb/tests/test_import_asso_export.py apps/cmdb/tests/test_permission_util.py --cov=apps.cmdb.views.instance --cov=apps.cmdb.services.instance --cov=apps.cmdb.services.topology_theme --cov=apps.cmdb.graph.drivers.graph_client --cov=apps.cmdb.graph.falkordb --cov-report=term-missing`；Falkor降序复现为 `.venv/bin/python -c "from apps.cmdb.graph.validators import CQLValidator; CQLValidator.validate_field('inst_name DESC')"`。
- 结果：沙箱首次退出 2（uv cache 无权限，未收集）；受控缓存权限最新重跑退出 1，115 passed、1 failed in 7.38s。唯一失败为 subnet 主题实现返回 `ipam`、测试仍断言空列表。历史 `f2f2ee211` 已明确把 IPAM 迁出主题到独立左侧菜单，`c729f2299` 从并行旧基线新增应用拓扑时意外回带该分支。排序复现退出 1，验证器按预期抛 `Invalid field name: 'inst_name DESC'`，证明现有 Service 与 Falkor 字段契约不兼容；无 `FALKORDB_HOST` 时 GraphClient 实际选择 Neo4j。
- 覆盖率：`views/instance.py` 53%、`services/instance.py` 16%、`services/topology_theme.py` 95%、`graph_client.py` 29%，合计 33%；FalkorDB 未被测试路径导入，coverage 无可声明数据。本域远低于 75%/核心 90% 门槛。
- 未验证项：Enterprise 子模块未初始化，真实文件 overlay/MinIO 未验证；无真实 FalkorDB/Neo4j、跨模型关系权限、全文入口、通用/网络拓扑、稳定分页、资源超限、跨组织关联导入、大文件/稠密图、并发和 MySQL/PostgreSQL 验证。主 Findings `CMDB-F14`–`CMDB-F19`（P0 1/P1 4/P2 1），详见 [03-query-topology.md](03-query-topology.md)。

## 04 自动采集

- 业务承诺：采集任务 create/update/delete/execute 必须在组织权限内形成可恢复的数据库、周期任务与节点配置状态；每次 execution 单 owner，重复投递幂等且旧 Worker 不能写图、关系、审计或结果；每个目标和凭据尝试有结构化 outcome，部分成功不得误报；实例 merge、自动关系与清理复用统一权限、唯一、Operation 和审计契约；目标、批次、内存、原始数据和日志均有硬边界且不泄露凭据。跨存储/异步恢复引用 `CMDB-F04/F11`，实例批写引用 `CMDB-F10/F11`，关系对端引用 `CMDB-F14`，不重复计数。
- 入口：`CollectModelViewSet.create/update/destroy/exec_task`；周期入口 `sync_collect_task`；超时与清理 Beat 入口 `sync_periodic_update_task_status/daily_data_cleanup_task`；派发/轮换入口 `CollectDispatchService`、`CollectCredentialPoolService`、`CollectHitStateService`；实例落地入口 `BaseCollect → MetricsCannula → Management`；Enterprise hook `collect.extensions`。
- 核心调用链：CRUD → ORM/ChangeRecord → on_commit 周期任务与 NodeMgmt；execute/周期消息 → execution claim → Job/Protocol 或多凭据 dispatch → target×credential attempt → BaseCollect 格式化 add/update/delete/association/raw → Management 图写/关系 → 审计 outbox/Enterprise hook/自动关系 → token 条件结果写回；Beat 每 5 分钟收敛 timeout，每日 02:00 全量扫描过期实例并批删。
- 外部依赖：Django ORM/多数据库 JSON、Celery broker/worker/Beat/django-celery-beat、FalkorDB/GraphClient、NodeMgmt RPC、Stargazer/采集插件、Enterprise collect extension、ChangeRecord mirror outbox。
- 关键测试：`test_collect_service_methods.py`、`test_collect_dispatch_service.py`、`test_collect_celery_tasks_svc.py`、`test_collect_management_hooks.py`；Enterprise `test_new_collect_objects_pipeline.py` 因子模块未初始化未执行。
- 执行命令：`SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task5-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_collect_service_methods.py apps/cmdb/tests/test_collect_dispatch_service.py apps/cmdb/tests/test_collect_celery_tasks_svc.py apps/cmdb/tests/test_collect_management_hooks.py --cov=apps.cmdb.services.collect_service --cov=apps.cmdb.services.collect_dispatch_service --cov=apps.cmdb.services.collect_credential_pool_service --cov=apps.cmdb.services.collect_target_service --cov=apps.cmdb.services.collect_hit_state_service --cov=apps.cmdb.collection.common --cov=apps.cmdb.collection.collect_tasks.base --cov=apps.cmdb.tasks.celery_tasks --cov=apps.cmdb.services.data_cleanup_service --cov-report=term-missing`。Enterprise 初始化后必须使用 `uv run --with jsonschema pytest`，本次未执行。
- 结果：沙箱首次退出 2（uv cache 无权限，未收集）；受控缓存权限重跑退出 0，82 passed in 3.61s。Enterprise gitlink `enterprise` 前缀为 `-`，子模块未初始化，brief 路径在当前 worktree 不存在并明确未验证。
- 覆盖率：collect_service 85%、dispatch 73%、credential_pool 61%、target 61%、hit_state 76%、common 38%、base 17%、celery_tasks 84%、cleanup 23%，合计 65%，未达 75%/核心 90% 门槛。
- 未验证项：Enterprise pipeline/overlay hook、真实 FalkorDB、真实 broker/多 Worker 重投与崩溃、NodeMgmt/Stargazer、MySQL/PostgreSQL、大 IP/实例/原始结果和 cleanup 规模均未验证。测试未覆盖相同 token 双 owner、旧 Worker 图副作用、混合目标失败、结构化错误分类、批次/内存上限、删除审计，以及日志/DB/用户摘要的 secret 脱敏。主 Findings `CMDB-F20`–`CMDB-F25`（P0 3/P1 3），详见 [04-auto-collection.md](04-auto-collection.md)。

## 05 Stargazer 边界

- 业务承诺：CMDB 下发的任务、凭据、远程命令与 callback 必须在 Stargazer 最终执行边界再次 fail-closed 校验；host/instance/execution identity 在拆分、重试和 callback 中保持一致；任务参数、文件、CIDR、并发、输出和 deadline 有硬预算；metrics/callback/凭据事件具备明确投递状态、幂等键和可恢复 checkpoint；日志、缓存与错误响应不泄露凭据、配置正文或设备输出。敏感错误面引用 `CMDB-F25`，通用 fire-and-forget 状态机引用 `CMDB-F04`，不重复计数。
- 入口：Sanic `GET /collect/collect_info` 与 `/collect/credential_results`；ARQ `collect_plugin_task`；`CollectionService`/`PluginExecutor`；`config_file`、`network_config_file`、`ip`、`network_topo` 插件；周期 `CollectCredentialResultPushService.push_once`；NATS metrics、`receive_config_file_result`、`receive_collect_credential_result`。
- 核心调用链：CMDB NodeParams/Telegraf header → `collect_info` 解析 `cmdb*` 与 host/credential pool → ARQ enqueue/dedupe → `collect_plugin_task` → `CollectionService` 解析 plugin.yml → job/protocol collector → metrics 或 callback 归一化 → core NATS `publish+flush` → CMDB handler；凭据执行结果同时写 Redis ZSET/cooldown，周期按 finished_at cursor 批推 CMDB。配置文件拆分后的 callback identity 当前按单 host 构造，历史 instance_name 错配线索未复现。
- 外部依赖：Redis/ARQ、core NATS 与 CMDB consumer、NodeMgmt local/ssh executor、Netmiko/网络设备、PowerShell/POSIX shell、pysnmp/SNMP 设备、icmplib privileged ICMP/TCP、Docker/VM/SSH collect fixtures。
- 关键测试：`test_collect_multicred.py`、`test_collect_credential_push.py`、`test_ip_discovery_targets.py`、`tests/collect_fixtures/`；额外复核 `test_network_config_file_info.py`、`test_ip_discovery_scanner.py` 与直接命令/转义/未知投递复现。
- 执行命令：`make lint`；`uv run pytest -q tests/test_collect_multicred.py tests/test_collect_credential_push.py tests/test_ip_discovery_targets.py tests/collect_fixtures/`；拆分 `uv run pytest -q tests/test_collect_multicred.py tests/test_collect_credential_push.py`、`uv run pytest -q tests/collect_fixtures/`、`uv run pytest -q tests/test_network_config_file_info.py`；pytest-cov 探测命令；`.venv/bin/python -c`/受控 `uv run python -c` 复现命令策略、空命令、PowerShell 转义与 NATS 未知态。
- 结果：`make lint` 退出2，Stargazer 目录无 `.pre-commit-config.yaml`。brief 组合 pytest 退出2，`test_ip_discovery_targets.py` 收集期 `ModuleNotFoundError: plugins.inputs.ip_discovery`；拆分多凭据/凭据推送 49 passed；独立 collect fixtures 154 passed、6 failed、1 warning（catalog 缺 mssql，实际56而测试要求57），与前述49项组合运行时为203 passed、6 failed；网络配置现有测试10 passed；IP scanner 测试同样旧路径收集失败。直接复现确认 `request system reboot` 被 Agent 放行、空命令返回 `[]`、PowerShell 产生 POSIX 转义串，首次 generic publish 异常得到 `success_count=0, delivery_detected=True`。
- 覆盖率：未测量；Stargazer 环境未安装 pytest-cov，`--cov` 命令退出4，不能声明达到相关模块80%或核心路径90%。
- 未验证项：CodeGraph darwin-x64 bundle 缺失且受控下载超时，调用链改用 rg/逐文件复核；未连接真实 Redis/ARQ、NATS broker/CMDB consumer、Netmiko/SSH/PowerShell/SNMP/ICMP、Docker/VM fixture，也未执行大文件、大 CIDR、真实设备高危命令（安全原因）、多 Worker/进程重启、应用 ack 与 retention 边界。主 Findings `CMDB-F26`–`CMDB-F32`（P0 3/P1 4）；raw result/外部错误泄露引用 `CMDB-F25`，core NATS 无应用确认引用 `CMDB-F04`，详见 [05-stargazer-boundary.md](05-stargazer-boundary.md)。

## 06 配置文件

- 业务承诺：当前 execution 的配置 callback 必须以任务内实例和稳定版本键幂等落库；正文采用临时对象 + DB PENDING + 提交后发布，只有 READY 才能作为采集成功与可读事实；发布/删除失败可恢复且旧 Worker 不覆盖新状态；手动版本、读取、diff、删除满足实例权限和正文大小契约。通用异步 ack 引用 `CMDB-F04`，周期清理预算引用 `CMDB-F23`，敏感错误引用 `CMDB-F25`，Agent/端到端资源预算引用 `CMDB-F28`。
- 入口：HTTP `ConfigFileVersionViewSet.list/content/diff/file_list/receive_result/create_manual/destroy`；NATS `receive_config_file_result`；即时 `ConfigFileCollect`；Service `ConfigFileService.process_collect_result/create_manual_version`；Beat/Celery `reconcile_config_file_content_task`。
- 核心调用链：Stargazer callback → NATS handler → execution/实例/版本校验 → base64 解码/5MB 截断 → 临时 MinIO 对象 → DB `(collect_task, instance_id, version)` PENDING 行与任务汇总 → robust on_commit publish → READY/ERROR；删除先 DB DELETE_PENDING，再 on_commit 删除对象/行；每15分钟恢复过期 PENDING/ERROR/DELETE_PENDING 并清理孤儿临时对象。HTTP 读取/diff 先校验双方实例权限和 READY。
- 外部依赖：MinIO/django-minio-backend、Django ORM/多数据库唯一与 nullable 语义、NATS callback、Stargazer、Celery/Beat、FalkorDB 实例权限查询、SystemMgmt 组织权限。
- 关键测试：`test_config_file_process_collect_db.py`、`test_config_file_content_lifecycle.py`、`test_config_file_views.py`、`e2e/test_config_file_pipeline.py`；额外静态复核 serializer、Beat 配置和 Task 5/6 execution/callback/资源/错误主 Findings。
- 执行命令：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task7-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run --with jsonschema pytest -q -o addopts='' apps/cmdb/tests/test_config_file_process_collect_db.py apps/cmdb/tests/test_config_file_content_lifecycle.py apps/cmdb/tests/test_config_file_views.py apps/cmdb/tests/e2e/test_config_file_pipeline.py --cov=apps.cmdb.services.config_file_service --cov=apps.cmdb.services.config_file_content_lifecycle --cov=apps.cmdb.views.config_file --cov=apps.cmdb.collection.collect_tasks.config_file_collect --cov=apps.cmdb.nats.nats --cov-report=term-missing`。
- 结果：沙箱首次退出2（uv cache 无权限，未收集）；受控缓存权限重跑退出0，66 passed in 8.21s。测试证明采集业务键、旧 execution、权限、局部发布/删除失败、恢复和 NATS envelope，但发布失败与任务/callback 被 Mock 分层隔离。
- 覆盖率：content lifecycle 91%、config service 73%、config View 81%、即时触发协调器 27%、NATS 整文件16%，五目标合计46%；主 Service、触发链和整体未达80%/核心90%门槛。
- 未验证项：真实 MinIO/NATS/Celery worker、发布与恢复并发、MySQL/PostgreSQL nullable unique、同毫秒手动上传、大文件/base64/diff 输出、大 MinIO 目录和 DB 引用集均未执行。主 Findings `CMDB-F33`–`CMDB-F35`（P1 3）；孤儿清理无界扫描引用 `CMDB-F23`，端到端资源放大引用 `CMDB-F28`，异常泄露引用 `CMDB-F25`，详见 [06-config-file.md](06-config-file.md)。

## 07 IPAM

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 08 专项资源视图

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 09 Node 同步

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 10 Enterprise 自定义上报

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 11 变更与订阅

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 12 NATS / RPC

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 13 跨域架构复核

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充
