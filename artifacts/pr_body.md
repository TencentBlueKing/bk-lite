# 新增深信服 EDS 分布式存储 SNMP 插件

## 摘要

新增 Telegraf SNMP 存储插件 `storage_sangfor_eds`，监控对象为 **存储**（硬件设备分类），展示名「深信服 aStor/EDS 分布式存储」。采集深信服企业级分布式存储私有 MIB，OID 根 `1.3.6.1.4.1.35047.2.12`。

**无真机 walk，待实机校验。** 证据为厂商 MIB 对齐；贴证据审过即可合。

## 对象与身份

| 项 | 值 |
| --- | --- |
| 目录 | `server/apps/monitor/support-files/plugins/Telegraf/snmp/storage_sangfor_eds/` |
| 插件 | `Storage Sangfor EDS SNMP` |
| collect_type | `snmp_storage_sangfor_eds` |
| config_type | `storage_sangfor_eds` |
| 监控对象 | `Storage` / `Hardware Device` |
| instance_type | `storage` |
| brand | `sangfor` |

与现有防火墙叶子无冲突：`firewall_sangfor` 使用 `snmp_sangfor` + `35047.1` / `35047.2.1`；本插件不占用这些 collect_type，也不使用网络设备 `device_*` 指标名。

## 测量与 OID（高层）

标量一律 `[[inputs.snmp.table]]` + `table.field`，OID **不含** 末尾 `.0`。表按列采集，字符串 INDEX 作 tag。

- `sangfor_eds_cluster`：`…2.12.1` 主机数、SSD/HDD 已用与空闲、管理/业务/存储网正常与异常网卡数、物理总/已用/空闲字节、块池与容量池个数
- `sangfor_eds_block_pool`：`…2.12.2` 容量字节、使用率、恢复/同步/均衡/亚健康任务、状态
- `sangfor_eds_capacity_pool`：`…2.12.3` 容量、任务、daemon/PG/池状态
- `sangfor_eds_lun`：`…2.12.4.3` lunTable 使用率（tag `lun_name`）
- `sangfor_eds_fs`：`…2.12.5` NFS/CIFS/FTP 连接数（最小可选）
- `sangfor_eds_disk`：`…2.12.7.1` diskTable 状态/类型/容量/使用率/寿命/坏道（tag `disk_name`）
- `sangfor_eds_host`：`…2.12.7.3` hostTable 在线/CPU/内存（可解析时转换，tag `host_name`）

DisplayString 使用率（0..1）经 processor 转为 0-100 百分比。字符串状态映射：`1` 正常、`2` 异常、`3` 未知；空/notPresent→1；厂商字面 unknown→3 且不告警；策略仅 `=2`。

未纳入：文件目录/用户/组配额表、对象用户与桶配额（可二期）。

## 看板

现有社区专业盘无法直接绑定 `sangfor_eds_*`。本次把对象挂到 Storage，并补最小接入 configLoader + 详情卡；不接入防火墙/交换机专业盘。缺口见 `artifacts/storage_dashboard_gaps.md`。

## 验证

- 插件 JSON/YAML 可解析，collect_type 在 metrics / UI / 模板中一致。
- 标量 table.field OID 无末尾 `.0`；与 `firewall_sangfor` 的 `35047.2.1` 无交叉。
- 无真机 walk，未做现网 `--test` 采数。合成样例与厂商 MIB 对齐。
