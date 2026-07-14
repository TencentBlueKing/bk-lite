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

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

## 03 查询与拓扑

- 业务承诺：待补充
- 入口：待补充
- 核心调用链：待补充
- 外部依赖：待补充
- 关键测试：待补充
- 执行命令：待补充
- 结果：待补充
- 覆盖率：待补充
- 未验证项：待补充

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
