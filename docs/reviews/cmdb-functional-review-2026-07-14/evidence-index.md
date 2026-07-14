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
- 核心调用链：列表/全文 → 按当前 model 构建 permission map → GraphClient → 驱动 CQL；关联查询 → 只校验中心实例 → 无权限关系/对端实体查询；通用/网络拓扑 → 中心实例权限 → 中心 model permission map → 跨模型节点后置裁剪；导入 → 组织单元格范围校验 → 全模型 `batch_save_entity` → 全量关联名称映射/建边 → 审计/自动关系；导出 → 根实例权限图查询 → openpyxl → 无权限关联名称回填；附件由 Enterprise 门面接收实例读权限 callback。
- 外部依赖：FalkorDB/Neo4j 双图驱动、SystemMgmt 权限/组织 RPC、Django ORM Group、openpyxl、Enterprise instance file overlay/MinIO、审计与 Celery 自动关系。
- 关键测试：`test_instance_views.py`、`test_search_inst_batch.py`、`test_topology_theme.py`、`test_import_organization.py`、`test_import_asso_export.py`、`test_permission_util.py`；额外静态/直接验证排序驱动契约。
- 执行命令：`SECRET_KEY=test DB_ENGINE=sqlite DB_NAME=/private/tmp/cmdb-task4-review.sqlite3 ENABLE_CELERY=true INSTALL_APPS=system_mgmt,node_mgmt,cmdb MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=test MINIO_SECRET_KEY=test MINIO_USE_HTTPS=false uv run pytest -q -o addopts='' apps/cmdb/tests/test_instance_views.py apps/cmdb/tests/test_search_inst_batch.py apps/cmdb/tests/test_topology_theme.py apps/cmdb/tests/test_import_organization.py apps/cmdb/tests/test_import_asso_export.py apps/cmdb/tests/test_permission_util.py --cov=apps.cmdb.views.instance --cov=apps.cmdb.services.instance --cov=apps.cmdb.services.topology_theme --cov=apps.cmdb.graph.drivers.graph_client --cov=apps.cmdb.graph.falkordb --cov-report=term-missing`；Falkor降序复现为 `.venv/bin/python -c "from apps.cmdb.graph.validators import CQLValidator; CQLValidator.validate_field('inst_name DESC')"`。
- 结果：沙箱首次退出 2（uv cache 无权限，未收集）；受控缓存权限重跑退出 1，115 passed、1 failed in 7.45s。唯一失败为 subnet 主题实现返回 `ipam`、测试仍断言空列表。排序复现退出 1，验证器按预期抛 `Invalid field name: 'inst_name DESC'`，证明现有 Service 与 Falkor 字段契约不兼容。
- 覆盖率：`views/instance.py` 53%、`services/instance.py` 16%、`services/topology_theme.py` 95%、`graph_client.py` 29%，合计 33%；FalkorDB 未被测试路径导入，coverage 无可声明数据。本域远低于 75%/核心 90% 门槛。
- 未验证项：Enterprise 子模块未初始化，真实文件 overlay/MinIO 未验证；无真实 FalkorDB/Neo4j、跨模型关系权限、全文入口、通用/网络拓扑、稳定分页、资源超限、跨组织关联导入、大文件/稠密图、并发和 MySQL/PostgreSQL 验证。主 Findings `CMDB-F14`–`CMDB-F17`（P0 2/P1 1/P2 1），详见 [03-query-topology.md](03-query-topology.md)。

## 04 自动采集

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 05 Stargazer 边界

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 06 配置文件

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

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
