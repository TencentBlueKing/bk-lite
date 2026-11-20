# 告警丰富把应用名写入 service

Status: implemented

## Completion Evidence

- CMDB 丰富在事件入库前写入 `Event.service`。应用 `inst_name` 优先，为空时用该条应用的系统 `inst_name`。未命中、查询失败、名称超过 200 字符时保留上报值。多个应用取 `root_uuid` 最小的一条，不改看下一条。
- 同一个字符串写入 CMDB 丰富结果的 `service` 键。出参投影不必声明 `application.inst_name`。投影没有选择应用或系统时，记录不展开，只取 `root_uuid` 最小的那条应用名称写回。
- 相关性规则、聚合 SQL 和编辑器未改。
- 验证（2026-11-20，sqlite 内存库）：`apps/alerts/tests/test_enrichment_service_name.py` 9 passed。其中 `test_same_application_events_aggregate_by_service` 用桩 CMDB 应用数据接入三条事件，再走 `AggregationProcessor`。同一应用的 host-a 和 host-b 收成一条告警，`dimensions.service` 为 `adv-app-test`。没有应用归属的 host-c 保持 `node-exporter`，单独成组。

## Problem Statement

同一故障里，交换机、主机和应用会一起刷屏。相关性规则可以按事件的 `service` 分组，但这一列只有上报值。监控和日志经 NATS 进入告警中心时，`service` 经常是空的。Prometheus 会把 `labels.service` 或 `labels.job` 放进这一列，那是采集任务名，不是 CMDB 里的应用名称。

CMDB 丰富已经能查出应用和应用系统。结果停在丰富数据的 `cmdb` 命名空间里，应用名称在 `application.inst_name`，系统侧目前投影出去的是运维人 `system.operator`。相关性分组读的是 `Event.service`。按 `service` 分组因此还聚不出「同一个应用」。

## Solution

事件入库前，默认的 CMDB 丰富如果得到应用名称，就把该名称写入 `Event.service`，并覆盖上报值。应用名称为空时，改写这条应用所属应用系统的名称。两个名称都没有，或者这次 CMDB 查询失败，则保持上报的 `service`。

相关性规则、聚合 SQL 和规则编辑器都不改。操作人在降噪策略的详细配置里只保留聚合维度 `service`。同一应用名称的事件进一组。

## User Stories

1. As a 一线值班人, I want 同一应用下的主机和中间件告警带上同一个 `service`, so that 一条只按 `service` 分组的相关性规则能把它们收成一组
2. As a 一线值班人, I want 没有 CMDB 应用归属的告警保持原来的 `service`, so that 空值和 Prometheus 的 `job` 不会被并进某个应用
3. As a 告警中心管理员, I want 在事件和丰富结果里看到写入后的 `service`, so that 我能核对分组键是哪一个应用名称

## Implementation Decisions

### 写入时机

丰富批处理结束、事件实例化之前写入。与责任人写回 `Event.assignee` 是同一阶段。此时 CMDB 原始记录还在，写回不读出参投影。因此不依赖内置预设里有没有 `application.inst_name`，也不依赖初始化用 `get_or_create` 时有没有更新旧的预设行。

只有这次 CMDB 丰富实际叠上了应用或系统字段的事件才参与取值。没有跑到这一层的事件不改 `service`。

同一条事件因为接入幂等键已经存在而整行跳过时，不再丰富，也不改已经入库的 `service`。不为历史事件回填。

### 取值

从本次执行顺序里第一条给出非空名称的 CMDB 规则取值。后面的规则不再覆盖。一个对象挂多个应用时，按成员 `root_uuid` 字典序取最小的那条，不看应用实例上的 `inst_uuid`，也不改去下一条。出参投影没有选择应用或系统时，不把这条记录展开成多行，也不把系统运维人写进责任人字段。

名称按下面的顺序决定：

1. 该应用的 `inst_name` 去掉首尾空白后非空，则 `service` 用这个字符串。这就是 CMDB 应用列表里的「应用名称」。应用 ID `app_id` 不作为 `service`。
2. 应用名称为空时，用这条记录上应用系统的 `inst_name`，同样去掉首尾空白。`system.operator` 是运维人，不是系统名。
3. 系统名也为空，则不写 `service`。

不因为最小的那条应用没有名称，就改去下一条应用再找。系统也只用这条应用上已经收好的那一个应用系统。一个应用挂多个系统时，上下文里本来就只留 `system_uuid` 最小的那个。

命中则替换上报值，不与原值拼接。未命中时不把 `service` 写成空字符串。下面都算未命中：查询失败、超时、组织不匹配、对象不是任何应用的成员、两个名称都是空白。

名称超过 `Event.service` 的 200 个字符时也算未命中，保留上报值。截断会把不同应用收成同一个分组键。

大小写和中间空格保持原样。`API` 和 `api` 仍是两个分组键。

### 对账

写入 `Event.service` 的同一个字符串，同时写入这次 CMDB 丰富结果的 `service` 键。事件接口返回的 `service` 就是分组会读到的值。丰富结果里的 `service` 键只用于核对。

相关性规则继续选择列 `service`。不把 `enrichment.cmdb.application.inst_name` 配成分组路径。那个键是带点的扁平字符串，和聚合用的嵌套 JSON 路径不是同一种形状。

上报原值留在 `raw_data`。不另存一列。

### 规则侧

`AlarmStrategy.params.group_by` 已经允许只包含 `service`。聚合按 `Event.service` 的精确字符串分组。`NULL` 和空字符串视为缺失。仅按 `service` 分组且 `service` 缺失时，分组退回 `external_id`，不会把所有空 `service` 收成一组。

本次不修改默认的「应用优先」。该预设的 `group_by` 仍是 `service`、`location`、`resource_name`、`item`。四个维度都在时，同一应用下的不同对象仍然拆开。使用和验收时，在详细配置里去掉后三个维度。选择「自定义」不会自动改成只剩 `service`，它保留当前维度。

即时告警不按 `service` 合并。模板里的 `{service}` 会读到已经写好的事件列，但仍然是一事件一条告警。

## Testing Decisions

只断言丰富结束后事件上的 `service`，以及 CMDB 丰富结果里的同一个字符串。不新测分组 SQL。现有聚合已经按 `Event.service` 分组。

测试走现有的丰富批处理入口，用桩 CMDB 记录驱动。断言对外结果，不断言内部调用顺序。

- 记录含应用 `inst_name`，且事件已有 `service`。结束后 `service` 等于应用名称，丰富结果的 `service` 键相同。
- 记录没有应用名，也没有系统名。原 `service` 保持不变。原值为空则仍为空。
- 应用 `inst_name` 为空白，系统 `inst_name` 有值。`service` 等于系统名。
- 同一对象有两条应用。`service` 等于 `root_uuid` 较小的那条应用名。
- CMDB 查询失败。原 `service` 保持不变，事件不因为这次写回而中断入库。
- 名称长于 200 个字符。原 `service` 保持不变。

Prometheus 适配器把 `job` 写入 `service` 的现有测试不改。它覆盖的是丰富之前。丰富命中后再覆盖，由上面的批处理用例锁住。

另有一条真实聚合链路：桩 CMDB 返回同一应用下的两台主机，以及一台没有应用归属的主机。事件经接入适配器入库，再由 `AggregationProcessor` 按 `group_by: ["service"]` 聚合。两台主机进同一条告警，第三台保持上报的 `service` 并单独成组。

手工验收用同一应用下的一条主机告警和一条中间件告警。详细配置里的聚合维度只留 `service`。窗口内它们收成一条告警，告警维度里的 `service` 是该应用名称。

## Out of Scope

- 父告警抑制子告警。
- 按拓扑自动合并告警。
- 把应用或应用系统做成新的聚合维度。
- 修改「应用优先」的默认四维度，或让「自定义」自动套用只含 `service` 的预设。
- 为「主归属应用」新增 CMDB 字段。多个应用时固定取 `root_uuid` 最小的应用名称。
- 回填已入库事件，或在幂等键命中时更新 `service`。
- 即时告警按 `service` 合并。
- 告警对象本身就是应用实例时专门补名称。应用实例通常不在应用成员上下文里。验收使用主机或中间件。

## Further Notes

新事件的聚合指纹会带上写入后的应用名称。已经按旧 `service` 打开的告警留在原组，不会被搬进新组。
