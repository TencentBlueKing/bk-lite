# CMDB 数据治理：重复与孤岛实施

Status: 已落地

规格：`specs/changes/cmdb-governance-duplicate-island/spec.md`。六条数据口径和九条前端取舍已确认。

测试接缝是「写入模型、实例、关系后再扫描」。图用内存假图，变更记录、问题行和快照用 SQLite。不把内部循环变量当断言。

## 切片

1. 属性治理标记补齐企业版字段校验、导入导出和变更文案。现有 `test_governance_tags` 已规定行为。
2. 纯扫描 `governance/scan.py`  
   输入是已写入的模型、实例、模型关系、实例边、核实时间和忽略记录。输出健康度快照和问题行。重复复用唯一规则的值签名；任一比较字段为空则该实例不进组。唯一性冲突单独成组，包含内置 `inst_name`、历史单字段唯一和额外唯一规则。孤岛只看必连关系的源实例，目标模型没有实例时不报。
3. 落库  
   快照增加重复组数、孤岛实例数、唯一性冲突组数。问题行和忽略记录各一张表。日更任务改为跑这次完整扫描，仍返回快照条数。
4. 配置写入  
   重复规则写在模型节点 `duplicate_rules`。保存时拒绝唯一规则已占用字段。保存唯一规则时拒绝重复检测已占用字段。关系边写 `required`，默认视为关闭。
5. 处置  
   忽略本组记下规则、分组键、成员指纹和字段列表；指纹或字段变化后失效。确认仍有效写一条不改字段值的核实记录，日更把它算进新鲜度。孤岛建边走现有实例关系创建。
6. 页面  
   管理下增加数据治理。模型详情增加重复性检测 Tab。关系表插入必连和孤岛数。属性弹窗经企业版扩展位配置关键属性和时效性。重新采集没有实例级重跑接口，按钮进现有自动发现采集页。

## 不改的行为

唯一规则的写入拦截、条数上限和页面表格保持原样。运营分析健康度查询的返回字段不追加新键，避免看板合同变化。新计数只给治理页。

重新采集没有实例级重跑接口，按钮进入现有自动发现采集页。

## 验证记录

2026-11-06，在已有测试库上执行：

`cd server && uv run pytest apps/cmdb_enterprise/tests/test_governance_duplicate_island.py apps/cmdb_enterprise/tests/test_governance_health_core.py apps/cmdb_enterprise/tests/test_governance_health_calculation.py apps/cmdb_enterprise/tests/test_governance_health_snapshot_model.py apps/cmdb_enterprise/tests/test_governance_health_query.py apps/cmdb_enterprise/tests/test_governance_tasks.py apps/cmdb_enterprise/tests/test_governance_tags.py apps/cmdb_enterprise/tests/test_governance_ops_analysis.py apps/cmdb/tests/test_unique_rule_pure.py apps/cmdb/tests/test_unique_rule_crud.py --no-cov --reuse-db --override-ini="addopts=-q --reuse-db"`

结果：127 passed。

功能测试先把模型、重复规则、唯一规则、实例、模型关系和实例边写进内存图，再把核实记录写入 SQLite，然后跑治理扫描。核对了完整性、新鲜度、重复组、唯一性冲突、孤岛、健康度分母、忽略失效、确认仍有效和补边消孤岛。相同序列号的两次写入没有抛错。重复字段和唯一字段互相拒绝。

治理页没有在浏览器里走通。本机这次没有打开可用的前端服务。
