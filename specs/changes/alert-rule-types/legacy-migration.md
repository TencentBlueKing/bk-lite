# 存量告警筛选规则迁移

日期：2026-09-14。已实现并完成本地测试，尚未对客户数据库执行。

## 用途与范围

旧规则可能保存 `level eq ["1"]`、`source_id eq 12` 等配置。新目录拒绝这些字段/操作符组合，导致编辑无法回显、执行整条规则不命中。新增 Django 数据迁移 `0033_migrate_legacy_match_rules`，依赖 `0032_alertassignment_priority`，随正常 `migrate` 升级五入口的存量规则。Django 在成功后记录迁移版本，后续启动或再次执行 `migrate` 不会重复转换。本方案替换此前未发布的独立 management 命令。

| scope | 策略模型 | 匹配对象 |
| --- | --- | --- |
| correlation | AlarmStrategy，相关性 | Event |
| assignment | AlertAssignment，分派 | Alert |
| shield | AlertShield，屏蔽 | Event |
| enrichment | EnrichmentRule，丰富 | Event |
| action | ActionRule，处理 | Alert |

扫描全部五入口，包括停用策略。分派、屏蔽的 `match_type=all` 不改动残留条件；`filter` 的空规则报错保留，不能转换为全部匹配。其他入口合法的顶层空数组保持不变。

## 转换规则

| 旧配置 | 处理方式 |
| --- | --- |
| 级别、类型对象、对象实例、来源等候选字段的 eq/ne，单值或数组 | 转为 any_of/none_of，候选保存字符串数组；级别须存在于对应 Event/Alert 目录 |
| 支持候选匹配字段的 in/not_in | 数组转为 any_of/none_of；不猜测单字符串的分隔方式 |
| 标题、正文的 eq/ne 候选数组 | 等于展开为 OR，不等于展开为 AND；保留与其他条件的组合关系 |
| text_any / text_all / text_none | 分别展开为文本包含 OR、文本包含 AND、文本不包含 AND；目标字段仍须支持文本操作 |
| 合法的单文本 contains/not_contains/re | 保留字段允许的操作符及文本；不会转成集合包含 |
| level_id、source__name、Event content 等已知旧别名 | 转为当前目录对应字段；相关性中文“对象实例”按旧实现映射为 resource_name，不误改为 resource_id |
| Alert source_name、push_source_id | 转为 source_names、push_source_ids，对应条件转为集合候选匹配 |
| 旧 source_id | 从 AlertSource 解析名称：丰富使用业务编码 source_id，其他入口使用主键；转为 Event source_name 或 Alert source_names |
| 已符合当前契约的条件 | 原样保留；数组转换时去重，不任意修剪值或拆分逗号 |

旧告警源 ID 只接受完整候选操作。包含软删除但仍有记录的来源；来源已物理删除、名称为空或存在未选中的同名来源时阻止转换，不能猜测或扩大名称匹配范围。

升级后遵守已确认的新业务契约：Alert 告警源取关联 Event 的名称集合，排除恢复事件、保留 closed 事件，按当前名称去重，不再只看历史快照或首条 Event。所有字段的空实际值均不命中，否定条件也一样。这些是版本的业务变化，迁移不恢复旧运行语义。

以下情况保留**整条策略**并报告 scope、ID、条件位置：未知字段、目标字段不再支持的旧文本/正则操作（例如标题正则、对象实例的字符串包含）、不明确的数组文本条件、无效级别、来源歧义、展开后超过 20 组/100 条条件，或候选超过 50 项、文本超过 256 字符。不删除失败条件，也不只迁移某个 OR 分支；需按当前字段目录人工重新配置。

## 执行方式与一次性保证

在部署环境的 `server` 目录执行正常迁移即可，无需另外运行自定义命令：

```bash
python manage.py migrate
```

生产启动脚本已包含 `migrate`，本次不修改启动脚本，也不增加独立步骤。Django 的 `django_migrations` 记录保证成功后不再运行；转换本身亦幂等，已经符合新格式的记录不重复写入。

只使用 `apps.get_model` 提供的历史模型及迁移连接的数据库别名，通过 ORM 更新。转换所需的字段与操作符契约固定在 `0033` 内，不导入运行期模型、服务或 JSON 字段目录，避免未来代码变更破坏旧版本迁移。完成后不要修改此文件来追加新转换需求，应新增后续迁移。

## 事务与失败处理

- 按主键分批读取，每批最多 200 条，每个入口固定扫描最大 ID；包含停用策略，不改变优先级、更新时间、启用状态和其他配置。
- 整个数据步骤在一个事务中完成；发生不支持的条件、来源歧义或数据库失败时，回滚此次五入口数据修改，不记录 `0033` 成功。此前已经完成的 schema 迁移仍保留。
- 不可转换规则的错误包含 scope、策略 ID 和原因，不输出规则正文；修正该策略后重新执行 `migrate`。不会删除失败条件或只保存某个 OR 分支，也不能用 `--fake` 跳过问题。
- 迁移只读写数据库，不调用 API、RPC、队列、Worker，不执行分派或通知，不追补历史触发。该步骤负责存量业务配置的格式切换，失败时保持旧配置供修复/回退，不能把未完成的升级标成成功。
- 发布前备份数据库，在维护窗口暂停策略编辑和旧版本写入，协调前后端及所有规则 Worker 升级。迁移过程的行锁不代替整个部署的停写安排。

## 回退边界

不同旧字段/操作符可能转换为同一个新格式，数据迁移无法仅靠新值还原原始配置，因此 **不提供伪造的逆向转换**。Django 反向迁移会明确报 `IrreversibleError`；需要回退版本时，按发布前的数据库备份恢复旧规则及相应迁移记录，再切回旧代码。不要只回退前端或用 `--fake` 假装已恢复旧数据。

本迁移不回填历史 Alert 的 `push_source_ids`。尚未完成监控源回填的环境仍按原发布流程使用 `backfill_alert_monitor_sources`；它与本次规则配置迁移是两个独立步骤。

## 验证

最新回归结果：**1299 项通过**，其中迁移相关测试 **171 项**；数据迁移代码覆盖率 **93%**。Black、isort 与定向 Flake8 检查通过。运行证据：`/tmp/alert-data-migration-regression.log`。

迁移测试覆盖五入口转换、序列化回显、保存校验、实际来源匹配和恢复事件排除、超过两批的规则扫描、停用策略、保留无关配置、幂等、跨入口失败回滚和修复后重试。

另外使用独立内存数据库，按 `0032` 的历史模型状态建表，通过真实 `MigrationExecutor` 执行 `0033`，验证历史模型、成功记录、重复执行不再运行、失败不记录成功、修复重试、空数据升级以及反向迁移明确拒绝。

```bash
DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true \
CELERY_BROKER_URL=memory:// CELERY_RESULT_BACKEND=cache+memory:// \
.venv/bin/python -m pytest \
  apps/alerts/tests/test_migrate_alert_match_rules_service.py \
  apps/alerts/tests/test_field_operator_cross_product_service.py \
  apps/alerts/tests/test_source_name_rules_service.py \
  apps/alerts/tests/test_typed_rules_service.py \
  --nomigrations -o addopts= -q \
  --cov=apps.alerts.migrations.0033_migrate_legacy_match_rules --cov-report=term-missing
```

本地完整历史链另有基线限制：SQLite 执行旧 `0009_remove_correlationrules_aggregation_rules_and_more` 时，删除 `SessionEventRelation.event` 后残留索引引用，引发 `FieldDoesNotExist: NewSessionEventRelation has no field named 'event'`，在到达本次迁移前失败。本次未改动旧迁移，升级测试从 `0032` 历史状态开始；不将此测试结果声称为完整历史链从零安装通过。原始失败证据：`/tmp/alert-data-migration-tests.log`。

本轮未修改前端，回显验证覆盖 API 输出和保存校验，没有重新进行浏览器操作测试。SQLite 测试不代表生产数据库的行锁竞争验证；尚未对客户数据库执行。
