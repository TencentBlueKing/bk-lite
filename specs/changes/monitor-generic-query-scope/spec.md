# 通用监控查询在大范围下少做整表读取

Status: implemented

## Problem Statement

监控概况和网络设备运行汇总只是若干通用数据源的一种绑定。大范围打开时，采集、接口当前值和网络设备排行会先把授权范围内的实例或接口整表物化，再过滤、排序、分页或计数，VictoriaMetrics 和监控 NATS 路径被打满。不能把这些接口收成某两个大屏专用的 API。

## Solution

五个 handler 的请求和响应形状不变。先在完整授权范围上得到过滤键、排序键和总数，分页时只为当前页补展示列。计数只返回整数。无法把插件状态查询收窄到本次实例时，不再原样下发。排行先在 SQL 里收成网络设备（CPU/内存再收成既有五类对象），调用方超时后停止后续分块，不返回半截榜。

## User Stories

1. As a 运营分析调用方, I want 采集和接口列表在填写分页时拿到正确排序的一页和完整 `count`, so that 我不能把第一页长度当成总数。
2. As a 运营分析调用方, I want 两个计数接口拒绝分页和排序，并返回范围内的整数, so that 500 条列表上限不会把计数截短。
3. As a 运营分析调用方, I want 未分页时仍拿到全部匹配行，超过 500 条时失败, so that 不会静默变成默认 10 条。
4. As a 运维, I want 采集失联仍是已配置插件减去已上报插件, so that 上报、采集状态、采集方式和最后采样排序都还在。
5. As a 运维, I want 接口「全部」仍是快照指标合并后的并集，一台 VM 序列对应多台实例时按归属台数计数, so that 默认排序仍是实例名、接口名、实例 ID。
6. As a 运维, I want 网络设备排行仍是授权设备上的真 Top N, so that 超时或中途失败不会交出半截榜。

## Implementation Decisions

- 数据形状不变：采集/接口列表、计数、排行的对外字段和错误文案保持原样。列表和计数仍是两次调用。
- 采集：上报、采集状态或最后采样排序需要全量状态。否则总数来自实例范围，名称排序后只对当前页读 VictoriaMetrics。未分页且超过 `INSTANCE_LIST_MAX` 时在读指标前失败。计数在没有这些过滤时不读 VictoriaMetrics。
- 插件 `status_query` 没有选择器、实例身份无法解析、或改写后仍等于原查询时，不原样下发，该插件视为没有上报。选择器里已经有实例标签时，仍然并上本次实例匹配，扫描宽度停在请求范围内。
- 手动采集的实例如果本次请求的授权并过滤后的范围里有同伴配了插件，仍查询那些插件，但选择器只含这次要出结果的实例。不使用同对象上、却不在本次请求范围内的实例所配置的插件。
- 接口列表：匹配和排序所需指标覆盖全范围；其余展示列只补当前页（未分页则补全部匹配行）。接口计数用 `count by (instance_id)` 包住与列表现在相同的判定表达式，先按列表同样去掉接口名首尾空白并丢掉空白名，再按现有归属规则乘以实例台数。同一接口有多条互相冲突的序列时，计数认「任一序列满足条件」；列表的后写覆盖顺序不稳定，不在 PromQL 里复现。
- 接口列表和计数使用与采集相同量级的调用方截止时间。到点抛错，不返回已经算完的一部分。采集在截止时间已过、且没有任何可发的状态查询时也同样失败。接口计数遇到非成功响应时整次失败，不把该块当成 0。
- 接口展示列按去掉首尾空白后的接口名回填，选择器仍能命中原始序列上带空白的 `ifDescr`。
- 排行：`_get_authorized_monitor_instances` 增加可选的对象分类和对象名过滤，只给这个 handler 使用。权限判断仍在收窄后的集合上做。CPU/内存只含 Switch、Router、Firewall、Loadbalance、Wanopt。流量含全部分类为 Network Device 的活动实例。分块保持串行，避免默认打满 VictoriaMetrics。排序仍在 Python 里按值、名称、实例 ID 完成，不用 PromQL `topk`。
- 采集和接口 handler 继续离开共享 NATS 同步线程。排行保持默认的线程敏感。
- 不改两块内置画布的 YAML 绑定，不改 VictoriaMetrics 客户端把 URL 打进日志的问题。

## Testing Decisions

缝在现有服务和 NATS handler 上：分页形状、`count` 与页长、未分页 500 失败与计数不受该上限、失联定义、无法收窄的状态查询、接口并集与归属倍数、默认名称排序与速率排序、排行 Top N、失败关闭和截止时间。

Prior art：`server/apps/monitor/tests/test_collection_and_interface_sources.py`、`test_network_device_resource_top.py`、`test_network_device_resource_top_handler.py`。

## Out of Scope

告警、实例数量、分布和 `get_monitor_statistics`。前端调度。CMDB。新的大屏专用接口。短时缓存。
