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
- 未验证项：真实 MinIO/NATS/Celery worker、发布与恢复并发、MySQL/PostgreSQL nullable unique、同毫秒手动上传、大文件/base64/diff 输出、大 MinIO 目录和 DB 引用集均未执行。主 Findings `CMDB-F33`–`CMDB-F35`（P0 2/P1 1）；孤儿清理无界扫描引用 `CMDB-F23`，端到端资源放大引用 `CMDB-F28`，异常泄露引用 `CMDB-F25`，详见 [06-config-file.md](06-config-file.md)。

## 07 IPAM

- 业务承诺：子网 IP 视图必须同时满足菜单和实例权限；发现任务只能持久化、下发并条件性回写授权子网，且区分完整空快照与失败；人工/每小时 Beat 共用持久化单活作业，owner 租约覆盖全部图副作用；来源使用稳定游标，参考集、占用者、关联和执行时长均受硬预算；失败释放 `active_scope` 且错误不泄密。关系对端与在线返回预算引用 `CMDB-F14/F16`，错误脱敏、Agent 插件路径引用 `CMDB-F25/F30`。
- 入口：`InstanceViewSet.ipam_view/ipam_reconcile`；`CollectModelViewSet.create/update/exec_task` 与 `CollectModelSerializer`；`IPDiscoveryNodeParams`、`IPAMDiscoveryCollectionPlugin`、`apply_ip_discovery_vm_rows/apply_discovery_result`；Beat `reconcile_ipam_task`、Worker `execute_ipam_reconcile_task`；来源 ORM `IPAMReconcileSource`。
- 核心调用链：IP 视图 → 菜单/中心 subnet VIEW → 关系+旧字段查询 → 容量/状态列表；发现任务 JSON `subnet_ids` → 无实例授权持久化 → system 读取目标 CIDR → NodeMgmt 参数；当前正常 Agent 加载受 `CMDB-F30` 阻断，只有已有/延迟 VM rows、其他合法生产者或 F30 修复后结果到达，才继续经 VM `ip_info` → system upsert/offline/关系 → 利用率；人工/Beat → enqueue/nullable unique active_scope → Celery → owner claim/lease → 来源 ID 游标 → occupant 聚合 → IP/关系/离线/利用率 → owner 条件终态并释放 active_scope。
- 外部依赖：FalkorDB/Neo4j GraphClient、Django ORM 及多数据库唯一约束、Celery broker/worker/Beat、NodeMgmt、Stargazer、VictoriaMetrics、SystemMgmt 权限与组织上下文。
- 关键测试：brief 五文件 `test_ipam_views.py`、`test_ipam_discovery_service.py`、`test_ipam_reconcile_service.py`、`test_ipam_reconcile_job.py`、`test_ipam_reconcile_task.py`；静态补充审查 `test_ipam_subnet_service.py`、`test_ipam_cidr_pure.py`、`test_ipam_discovery_node_params.py` 及 Agent `test_ip_discovery_targets.py`。
- 执行命令：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task8-review.sqlite3 uv run pytest -q -o addopts='' apps/cmdb/tests/test_ipam_views.py apps/cmdb/tests/test_ipam_discovery_service.py apps/cmdb/tests/test_ipam_reconcile_service.py apps/cmdb/tests/test_ipam_reconcile_job.py apps/cmdb/tests/test_ipam_reconcile_task.py --cov=apps.cmdb.services.ipam_view --cov=apps.cmdb.services.ipam_subnet --cov=apps.cmdb.services.ipam_discovery --cov=apps.cmdb.services.ipam_reconcile --cov=apps.cmdb.services.ipam_reconcile_job --cov=apps.cmdb.models.ipam_models --cov-report=term-missing`。
- 结果：首次沙箱退出 2（uv cache 无权限，未收集）；受控缓存权限重跑退出 0，54 passed in 2.97s。测试证明 SQLite 单活唯一、终态 owner 条件、失败释放 active_scope、安全顶层错误、ID 游标与 existing IP 上限；但测试锁定空扫描结果批量离线，且未证明任务内子网授权、旧 owner 图 fencing 或真实 occupant 总预算。
- 覆盖率：ipam_models 100%、ipam_discovery 77%、ipam_reconcile 79%、ipam_reconcile_job 90%、ipam_view 40%，聚焦合计 78%；ipam_subnet 未被 brief 五文件导入，无可声明覆盖率。相关模块未达 80%，仅作业状态机达到核心 90%。
- 未验证项：真实 FalkorDB/Neo4j、Celery broker/多 Worker、NodeMgmt/Stargazer/VM、MySQL/PostgreSQL nullable unique、跨组织发现 E2E、租约过期旧 owner 图副作用、CIDR 并发、同 IP 海量占用者、来源总量/内存/deadline 和在线 IP 视图大响应。主 Findings `CMDB-F36`–`CMDB-F40`（P0 2/P1 3），Recommendation Block，详见 [07-ipam.md](07-ipam.md)。

## 08 专项资源视图

- 业务承诺：K8s setup 内部入口按 Execute/View 授权，公开 render 仅凭绝对过期且原子限次的 token 生成 YAML；K8s、应用、网络、机房/机柜视图先授权根实例，再按真实模型收敛父级和对端；实体分页之外还必须限制关系、节点、查询、响应字节和 deadline。跨模型对端授权引用 `CMDB-F14`，通用遍历预算引用 `CMDB-F18`，敏感外部错误引用 `CMDB-F25`。
- 入口：`K8sSetupViewSet.install_token/install_command/verify`、`K8sSetupOpenViewSet.render`；`InstanceViewSet.k8s_resource_overview/k8s_resource_layer/k8s_workload_pods/k8s_unowned_pods/k8s_resource_list`；`application_resource_apps/topology/resources/instances/export`；`network_topo`；`room_layout/rack_layout`。
- 核心调用链：内部 setup 权限 → `K8sSetupService` → cache token/NodeMgmt/Webhook/VictoriaMetrics；公开 token → 非原子 cache get/set 消费 → NodeMgmt NATS 参数 → Webhook YAML；K8s 根 cluster VIEW → 四模型 permission map → Namespace 500 条权限分页 → 批量关系/实体页/统计；应用根 VIEW → 单一根模型 permission map → 逐节点 BFS/分组/openpyxl（容量分别引用 `CMDB-F18/F17`）；network 根 VIEW → depth 钳制 1–4 → 单连接逐节点 BFS → `node_limit=100/truncated`（剩余权限/邻接预算引用 `CMDB-F14/F18`）；room/rack 根 VIEW → 关系实例 → rack/device 权限 → U 位布局，其中 room 逐 rack 查询设备。
- 外部依赖：FalkorDB/Neo4j GraphClient、Django cache/Redis、NodeMgmt cloud region RPC、infra Webhook、VictoriaMetrics、SystemMgmt 权限与组织上下文、openpyxl。
- 关键测试：brief 五文件 `test_k8s_resource_overview_service.py`、`test_k8s_resource_overview_views.py`、`test_application_resource_overview_views.py`、`test_infra_service.py`、`test_rack_room_service.py`；补充权限测试 `test_k8s_setup_views.py`。
- 执行命令：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task9-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_k8s_resource_overview_service.py apps/cmdb/tests/test_k8s_resource_overview_views.py apps/cmdb/tests/test_application_resource_overview_views.py apps/cmdb/tests/test_infra_service.py apps/cmdb/tests/test_rack_room_service.py --cov=apps.cmdb.services.k8s_resource_overview --cov=apps.cmdb.services.application_resource_overview --cov=apps.cmdb.services.infra --cov=apps.cmdb.services.rack_room --cov=apps.cmdb.views.k8s_setup --cov-report=term-missing`；补充 `... uv run pytest -q -o addopts='' apps/cmdb/tests/test_k8s_setup_views.py --cov=apps.cmdb.views.k8s_setup --cov=apps.cmdb.services.k8s_setup --cov-report=term-missing`。
- 结果：首次五文件命令被沙箱拒绝读取 uv cache，退出 2、未收集；受控权限重跑退出 0，51 passed in 4.75s。补充 setup 权限测试退出 0，6 passed in 0.15s；三项内部入口无权限均 403 且 Service 零调用，有权限 200。
- 覆盖率：brief 五文件 K8s overview 76%、应用资源 20%、infra 95%、rack_room 89%，合计 63%；setup View 未被五文件导入。补充测试 setup View 79%、setup Service 34%、合计 54%。相关模块与核心路径总体未达 80%/90% 目标。
- 未验证项：真实 Redis 多进程 token 原子性/绝对 TTL、FalkorDB/Neo4j、NodeMgmt/Webhook/VM、隐藏 Workload/Node 下可见 Pod、K8s 高关系边集、room 大量 rack 的查询次数与内存。brief 未运行网络拓扑测试；其 node_limit/truncated 仅静态复核，跨模型权限、单跳邻接行数/查询数/deadline 归 `CMDB-F14/F18`。应用高扇出/环与超大 node_ids/Excel 归 `CMDB-F18/F17`。主 Findings `CMDB-F41`–`CMDB-F43`（P0 2/P1 1），Recommendation Block，详见 [08-specialized-resources.md](08-specialized-resources.md)。

## 09 Node 同步

- 业务承诺：全局 Node Management 配置、同步与采集应按读写权限和组织范围执行；NodeMgmt 节点映射到 CMDB host 与区域隐藏采集任务后，运行记录必须准确表达新增、更新、部分失败、实际采集终态、timeout 与恢复。重复 HTTP/Beat/broker 执行只能有一个 owner，外部 RPC/分页/节点参数下发应有资源预算、幂等和脱敏错误闭环。Alerts `k8s_meta` 只读本地告警源，不进入 NodeMgmt 状态机；`snmp_trap_nodes` 是带用户 permission_data 的 NodeMgmt 查询对照入口。
- 入口：CMDB `NodeMgmtSyncViewSet.task/config/latest_run/display/run_sync/run_collect/detail_compat`；Celery `sync_node_mgmt_hosts/collect_node_mgmt_hosts`；Service `sync_hosts/collect_hosts/update_task`。跨 app 只读复核 Alerts `AlertSourceModelViewSet.k8s_meta/snmp_trap_nodes`。
- 核心调用链：task/config PUT → `update_task` → `NodeMgmtSyncConfig` + django-celery-beat → 全部系统 CollectModels NodeParams delete/push；run_sync/Beat → `NodeMgmt.cloud_region_list/node_list` 分页 → 按 region 选 container access point → 全量 host map → 缺失 host `InstanceManage.instance_create(system)`、已有 host 只计 update 不写 → 区域 `CollectModels` 先查后建/更新 → NodeMgmt 节点参数 delete/push → `NodeMgmtSyncRun`/last_sync_at；run_collect/Beat → 区域任务 → `CollectModelService.exec_task` 把子任务置 RUNNING/投递 Celery或返回已运行错误 Response → 父编排忽略返回值并立即终态/last_collect_at，子 ERROR/TIME_OUT 无回写；latest/display → 全局 Run 或全部系统 CollectModels 聚合。Alerts k8s_meta → `AlertSource` 本地元数据；snmp_trap_nodes → 当前用户/组织 permission_data → `NodeMgmt.node_list` → 无本地运行持久化。
- 外部依赖：NodeMgmt NATS RPC（cloud region/node list/child config）、FalkorDB/GraphClient 与 Instance Operation、Django ORM、django-celery-beat、Celery broker/Worker、SystemMgmt 用户组织上下文；Alerts `AlertSource` ORM。
- 关键测试：brief `test_node_mgmt_sync_resilience.py`、`test_node_mgmt_sync_helpers.py`；静态补充 `server/apps/cmdb/tests.py` 的 View/config/sync/display 测试与 `server/apps/alerts/tests/test_alert_source_views.py` 的 k8s_meta/snmp_trap_nodes 测试。
- 执行命令：`MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task10-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_node_mgmt_sync_resilience.py apps/cmdb/tests/test_node_mgmt_sync_helpers.py --cov=apps.cmdb.views.node_mgmt_sync --cov=apps.cmdb.services.node_mgmt_sync_service --cov=apps.cmdb.models.node_mgmt_sync --cov-report=term-missing`。
- 结果：首次命令被沙箱拒绝读取 uv cache，退出 2、未收集；受控权限原始重跑退出 0，36 passed in 2.90s；reviewer 修订后以原始 `term-missing` 命令新鲜重跑退出 0，36 passed in 2.66s。有效证明顶层异常 FAILED、单节点/区域任务抛异常继续并 PARTIAL、正常分页和序列化；没有证明 View/组织、真实更新、错误 Response、父子终态、重复运行、租约/恢复、异常分页、singleton/system_code 并发、delete→push 补偿或脱敏。
- 覆盖率：Node sync Service 64%、Model 100%，合计 66%；View 未被 brief 两文件导入，coverage 无该模块行。本域未达相关模块 80%/核心路径 90% 目标。
- 未验证项：真实 NodeMgmt/NATS、Celery broker/多 Worker/硬退出、FalkorDB、MySQL/PostgreSQL、并发配置/区域任务、跨组织普通用户、NodeMgmt 异常大/持续增长 count 与大规模节点、NodeParams delete→push 部分失败、实际 CollectModels Worker 父子终态。主 Findings `CMDB-F44`–`CMDB-F51`（P0 4/P1 4）；外部错误泄露引用 `CMDB-F25`。Recommendation Block，详见 [09-node-sync.md](09-node-sync.md)。

## 10 Enterprise 自定义上报

- 业务承诺：社区稳定入口在无 Overlay 时必须明确降级；Overlay 启用后，任务管理按功能权限和组织隔离，公开 ingest 只以已签发/可轮换/可作废且绑定 task scope 的 token 授权。Batch 应准确表达完整、部分失败与重投，identity/字段/关系必须验证；merge、pending、snapshot/expire cleanup 与审核只能作用于本 task 拥有的数据，并具备请求、数量、扫描、并发和恢复边界。
- 入口：社区 `CustomReportingTaskViewSet` 的 CRUD/stats/field_registrations/batch_activity/onboarding/credential/review；`CustomReportingIngestViewSet.create`（`OpenAPIViewSet`、AllowAny、空 authentication）；Enterprise `CmdbEnterpriseConfig.ready → registry_hooks → CustomReportingProvider`；Celery Beat `custom_reporting_expire_cleanup`。
- 核心调用链：task HTTP → serializer → registry provider → `_allowed_orgs/_require_task` → task/model/credential/document/activity/cleanup services → ORM/Graph；open ingest → Authorization Bearer/raw token → enabled credential SHA-256 全表匹配 → enabled task → 每次新建 Batch RUNNING（无 idempotency/generation）→ quick field register → Model attrs + FieldRegistration；社区已声明 instance/relation validate 扩展但 Enterprise 未实现、ingest 未调用 → 全模型 old_data → Management add/update + ChangeRecord → relation create或无唯一约束地新增 pending/backfill → snapshot direct delete/review → Batch SUCCESS/FAILED + last_reported_at；Beat schedule → 未被 `apps.cmdb_enterprise.tasks` 导入注册的 expire task（实际 Worker registry 缺失）。无 Overlay 时 registry 返回社区 `_EMPTY_CUSTOM_REPORTING`，读为空、写明确 `_NOT_ENABLED`。
- 外部依赖：Django ORM/事务与 JSONField、GraphClient/FalkorDB/Neo4j、社区 ModelManage/Management/InstanceManage/ChangeRecord、Celery Beat/Worker、SystemMgmt 请求组织上下文。来源边界：根 `enterprise` gitlink SHA `7c7db340961d6b010d2c533de92970df253b545f` 且未初始化；worktree 无 Overlay；主工作区 ignored Overlay 的 15 个 custom_reporting Python 源聚合 SHA-256 `1c4d5f1b9e3cbfb17798faf119779565e33bc1d23db7bba61e04cf519ff25ed9`，六测试聚合 SHA-256 `0e4b7eee9e8361f1479546444287ae2c540f303edfc8658c7d9f2ec5f47c8043`。
- 关键测试：Overlay `test_custom_reporting_authz.py`、`test_custom_reporting_ingest_service.py`、`test_custom_reporting_merge_service.py`、`test_custom_reporting_relation_service.py`、`test_custom_reporting_cleanup_service.py`、`bdd/test_custom_reporting_bdd.py`；社区缺失态补充 `test_custom_reporting_extension.py`、`test_model_custom_reporting_delegation.py`。
- 执行命令：主工作区 Overlay：`PYTHONDONTWRITEBYTECODE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise uv run pytest -q -o addopts='' apps/cmdb_enterprise/tests/test_custom_reporting_authz.py apps/cmdb_enterprise/tests/test_custom_reporting_ingest_service.py apps/cmdb_enterprise/tests/test_custom_reporting_merge_service.py apps/cmdb_enterprise/tests/test_custom_reporting_relation_service.py apps/cmdb_enterprise/tests/test_custom_reporting_cleanup_service.py apps/cmdb_enterprise/tests/bdd/test_custom_reporting_bdd.py --cov=apps.cmdb_enterprise.custom_reporting --cov-report=term-missing`。worktree Overlay 缺失态：`PYTHONDONTWRITEBYTECODE=1 MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb uv run pytest -q -o addopts='' apps/cmdb/tests/test_custom_reporting_extension.py apps/cmdb/tests/test_model_custom_reporting_delegation.py`。Celery registry：`PYTHONDONTWRITEBYTECODE=1 DJANGO_SETTINGS_MODULE=settings MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false INSTALL_APPS=system_mgmt,node_mgmt,cmdb,cmdb_enterprise ENABLE_CELERY=true uv run python -c "import django; django.setup(); from apps.core.celery import app; app.loader.import_default_modules(); name='apps.cmdb_enterprise.custom_reporting.tasks.custom_reporting_expire_cleanup'; print('registered=', name in app.tasks); print('enterprise_tasks=', sorted(k for k in app.tasks if k.startswith('apps.cmdb_enterprise')))"`。
- 结果：两条 pytest 命令首次都因沙箱拒绝读取 uv cache、退出 2 且未收集；受控权限重跑 Overlay 六文件退出 0，38 passed in 25.02s；无 Overlay 社区两文件退出 0，6 passed in 0.07s。Celery registry 首次漏设 settings 退出，补正命令后退出 0，`registered=False`，Enterprise 任务只有附件 cleanup。主工作区测试前后 `git status --short --branch` 相同，未修改/清理用户代码与未跟踪文件。
- 覆盖率：Overlay custom_reporting 15 模块合计 59%（808 statements / 333 missed）；models 92%、provider 67%、activity 21%、cleanup 81%、credential 32%、document 27%、field 27%、ingest 78%、merge 73%、model 20%、relation 84%、task 17%、tasks 0%，未达相关模块80%/核心90%目标。社区缺失态未测 coverage，只证明 no-op/拒绝/registry 委托。
- 未验证项：当前主仓库 branch 无法单独重建 ignored Overlay，gitlink commit 内容与安装态哈希的映射未知；未验证真实 View 功能权限、create/update 新 team、同模型跨 task/team、partial snapshot、空 identity、字段/保留字段/关系端点 schema、真实并发重投与幂等 key/generation、请求/字段/pending/credential 大规模预算、FalkorDB/Neo4j、多数据库和真实 Beat→broker→Worker。确定重投行为是每次新 Batch、重复变更审计、未解析关系重复 pending；相同 identity 并发引用 `CMDB-F10`，副作用恢复引用 `CMDB-F11`。主 Findings `CMDB-F52`–`CMDB-F57`（P0 3/P1 3）；关系授权、唯一锁、清理状态机、资源预算引用 `CMDB-F14/F10/F11/F23`。Recommendation Block，详见 [10-custom-reporting.md](10-custom-reporting.md)。

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
