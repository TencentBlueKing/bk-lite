# 字段顺序实施

Status: 已实现

规格：`field-declaration.md`。成员顺序和落库判断表仍以 `spec.md` 为准。

## 任务

1. 字段行改读各插件转换层写入主实例的模型字段名。不再读任务参数 `collect_fields`，也不把脚本返回名放进顺序。
2. 网络设备用设备转换表的模型字段一侧，不含接口字段，也不含 `sysdescr` 这类采集侧名字。
3. 自定义脚本和内置插件一样：转换结果里的模型字段进入同一行。自定义脚本的转换层把对得上模型属性的标签写成该属性，配置时按目标模型的属性列出。模型属性查不到时，该任务不出现在任何字段行。
4. 落库只把本轮转换结果送去判断。转换层没产出的模型字段不改值、不改来源。
5. 不同模型的任务不能创建成一条调和。这条保持现有校验。
6. 实机 SNMP 用调用方给出的四台设备做采集转换，并核对写入字段能按模型字段查询。社区字符串不入库。

## 验证

- 配置与判断：22 passed。`cd server && DB_ENGINE=sqlite DB_NAME=:memory: SECRET_KEY=cursor-cloud-dev ENABLE_CELERY=true uv run pytest apps/cmdb/tests/test_collect_reconcile_service.py apps/cmdb/tests/test_field_reconcile.py --nomigrations --no-cov -q --override-ini="addopts="`
- 写入后按实例名查询：`test_snmp_device_is_written_by_model_field_and_read_back` passed。`sysdescr` 转成 `sys_desc` 后写入，查询结果没有采集侧名字。
- 实机 SNMP 只读系统标识，社区字符串未写入仓库：
  - `10.10.69.247` 华为 S5735S-L8T4S-QA2，sysName `HUAWEI`，对象标识 `enterprises.2011.2.23.968`
  - `10.10.69.245` H3C S2610V2，sysName `H3C`，对象标识 `enterprises.25506.1.2609`
  - `10.10.69.248` Cisco Catalyst 1200，sysName `weopscisco`，对象标识 `enterprises.9.1.3210`
  - `10.10.69.246` 按给定超时 20 秒、重试 3 次，没有 SNMP 响应
- 这四台没有写入正在运行的 CMDB 实例库。写入和查询走采集落库路径上的假图。
