# 数据调和实施

Status: 已实现。验证命令与结果见文末。

规格：`specs/changes/cmdb-collection-supplement-task/spec.md`。

测试接缝就是规格「验证」一节，不再另选内部函数。SQLite 用 `--nomigrations`。图写入用假图适配器走 `MetricsCannula` → `Management`。FalkorDB 的条件 SET 和删除核对单独断言生成的查询。

## 切片

1. 纯判断 `collection/field_reconcile.py`  
   空值、字段顺序、人工来源、过期、相同值只改来源、成员顺序决定归属、删除保护。N≤0 不过期、不移交。
2. PostgreSQL  
   `CollectReconcile` / `CollectReconcileOrder`，迁移 `0062`，依赖社区版 `0061_showfield_created_by_model_unique`。生效 = `scope=member` 不少于 2，不落库。
3. 配置服务  
   支持的 `task_type`、`vmware_vc` 自定义脚本拒绝、一任务一条成员记录、字段顺序只含会采集该字段的成员。可见任务复用 `CollectModelViewSet.get_queryset_by_permission`。无权限任务不返回名称。保存时可见成员必须到齐；显式 `added_task_ids` / `removed_task_ids` 才增删。版本不一致拒绝。
4. 落库  
   只在任务目标模型的主实例上放开同一调和内的所有者。子模型仍走原冲突。`_collect_sources` 与字段同一次 SET。FalkorDB 条件 SET 失败重读一次，再失败记并发放弃。删除核对加上 `_collect_sources`。Neo4j 驱动不改。
5. 人工来源  
   `instance_update`（含 uuid）、批量更新、`inst_list_update`。`skip_permission_check=True` 的系统回填不标人工。详情用 `manual_fields`，不把 `_collect_sources` 返回给列表、详情、搜索和变更记录。`restore_collect` 清除人工来源。
6. 页面  
   采集任务页进入某个插件后打开「数据调和」：先列出该模型的调和，再建表单。模型固定为当前插件，任务用复选框从该模型里选。过期天数只在系统配置键 `cmdb_collect_source_stale_days`，默认 7，不放在这个抽屉里。实例详情人工字段可恢复自动采集。
7. SNMP  
   用调用方提供的四台设备做实机 `snmpget`。社区字符串不入库。

## 验证记录

- 判断、表结构、配置服务、落库和格式化：`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_field_reconcile.py apps/cmdb/tests/test_collect_reconcile_schema.py apps/cmdb/tests/test_collect_reconcile_service.py apps/cmdb/tests/test_collect_reconcile_write.py --nomigrations --no-cov -q --override-ini="addopts="`
- 相邻回归：`test_collect_management_service.py`、`test_instance_service_crud.py::test_instance_update_ok`、`test_collect_change_records.py`、FalkorDB 条件删除与条件 SET。
- 实机 SNMP 只读 `sysDescr` / `sysObjectID` / `sysName`，社区字符串未写入仓库：
  - `10.10.69.247` 华为 S5735S-L8T4S-QA2，sysName `HUAWEI`
  - `10.10.69.245` H3C S2610V2，sysName `H3C`
  - `10.10.69.248` Cisco Catalyst 1200，sysName `weopscisco`
  - `10.10.69.246` 用给定社区字符串，超时 20 秒、重试 3 次，没有 SNMP 响应
- 没有在浏览器里打开采集任务页。页面入口已接到 `/cmdb/api/collect_reconcile/`。

## 插件作者

脚本输出哪个字段，调和就可能写哪个字段。`inst_name` 只用来匹配。空值不会盖掉其他来源的非空值；要把自己上次写下的值清掉，只有当前来源是本任务时才做得到。
