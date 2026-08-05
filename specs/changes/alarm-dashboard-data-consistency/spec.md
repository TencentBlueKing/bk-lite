# 告警运营大屏与统一告警仪表盘数据一致性修复说明

Status: implemented

更新时间：2026-08-04

关联问题：[TencentBlueKing/bk-lite#4478](https://github.com/TencentBlueKing/bk-lite/issues/4478)

## 1. 文档目的

本文件记录 2026-08-04 对以下页面进行人工核数、代码排查和方案讨论后形成的完整修复范围，供后续新对话直接接手实现：

- 告警中心 → 集成源概览；
- 运营分析 → `统一告警中心仪表盘_内置`；
- 运营分析 → `告警运营大屏_内置`；
- 运营分析画布组件的数据请求缓存；
- 内置数据源及内置画布的初始化与升级同步。

本文件不是要求把截图中的演示数字写死，而是记录当时环境中的核数证据、已经确认的统计口径、代码原因和验收要求。实现时仍须以测试数据和当前数据库查询结果为准。

## 2. 前情与核数基线

### 2.1 用户看到的主要现象

1. 集成源概览中的各来源“事件数量”相加为 34，但告警运营大屏显示“事件数 15”。
2. 大屏“活动状态分布”显示总数 3，三个状态各 1；同一页面的活动告警总数却为 20。
3. 统一告警仪表盘选择“最近 30 天”后，概览仍显示 15 个事件、20 个告警等存量数据，时间筛选没有作用于这些组件。
4. 统一告警仪表盘显示告警源总数 4、已启用 4、启用率 100%，与集成页面实际配置数量不一致。
5. 从画布 A 切换到 B，再切回 A，组件直接使用旧缓存，不重新请求数据源。
6. 内置 YAML 已经修改了数据源参数，但初始化遇到已有数据源时执行 `skip`，数据库配置没有同步。

### 2.2 2026-08-04 演示环境核数结果

以下数字只用于解释问题和建立回归夹具，不作为生产环境固定期望：

| 项目 | 数量 | 说明 |
|---|---:|---|
| 原始事件总数 | 34 | 集成源接收到的所有 `Event` |
| 已关联告警的事件数 | 15 | `Event.alert` 指向当前授权告警的事件 |
| 未关联告警的事件数 | 19 | 34 - 15 |
| 最近 30 天原始事件数 | 21 | 按 `Event.received_at` |
| 最近 30 天告警关联事件数 | 2 | 同时满足时间范围和告警授权 |
| 最近 30 天未关联事件数 | 19 | 21 - 2 |
| 当前存量告警数 | 20 | 当时授权范围内全部告警记录 |
| 当前活动告警数 | 20 | 未分派 8、待响应 8、处理中 4 |
| 当前告警等级分布 | 8 / 7 / 5 | 合计 20，当前该组件结果正确 |
| 告警源配置总数 | 11 | `AlertSource` 配置数 |
| 已启用告警源数 | 10 | 预期启用率约 90.9% |
| 最近 30 天新增告警数 | 2 | 当时为 Zabbix、Codex Webhook 各 1 |
| 最近 30 天通知数 | 0 | 因此通知数量为 0 是合法结果 |

集成源卡片当时显示的来源事件数为 RESTful 13、NATS 1、网络状态拓扑演示 4、Prometheus 3、Zabbix 3、K8s 4、SNMP Trap 2、Codex 演示 Webhook 3、Codex 静默演示源 1，合计 34。

统一仪表盘的来源 TOP 当时为 RESTful 9、网络状态拓扑演示 4、Codex 演示 Webhook 1、Zabbix 1，合计 15。它统计的是已关联告警的事件，因此不能与集成页的原始事件数直接比较。

## 3. 统一术语和统计原则

后续代码、数据源字段、组件名称和描述统一使用以下术语：

| 术语 | 定义 | 时间字段 |
|---|---|---|
| 原始事件数 `raw_event_count` | 告警源接收到的全部事件，不要求已经形成或关联告警 | `Event.received_at` |
| 告警关联事件数 `linked_event_count` | 已关联当前授权告警的事件数 | `Event.received_at` |
| 期间新增告警数 `new_alert_count` | 统计期间创建的告警 | `Alert.created_at` |
| 期间受影响告警数 `affected_alert_count` | 统计期间收到事件的去重关联告警数，告警本身可以早于统计期间创建 | 由期间 `Event.received_at` 推导 |
| 期间新增事故数 `new_incident_count` | 统计期间创建的事故 | `Incident.created_at` |
| 当前活动告警数 `active_count` | 查询时刻处于活动状态的告警快照 | 不受期间筛选影响 |
| 当前状态分布 | 查询时刻未分派、待响应、处理中的告警数量 | 不受期间筛选影响 |

时间范围统一采用半开区间 `[start, end)`，即包含开始时刻、不包含结束时刻。这样相邻时间窗口不会重复统计边界数据。

### 3.1 期间、快照和累计不是同一概念

- **期间指标**回答“最近 30 天发生了多少”，必须响应仪表盘时间筛选。
- **当前快照**回答“现在还有多少”，不能因为选择最近 30 天而排除 30 天前产生但仍未恢复的告警。
- **平台累计**回答“数据库保留的全部历史有多少”。受数据保留和清理策略影响，它不一定等于产品生命周期累计值。

统一告警仪表盘是运营分析页面，应同时展示期间变化和当前处置压力，不能把所有组件都简单改成累计口径，也不能让同一个后端返回结构混合期间与快照字段而没有明确接口约束。

## 4. 已确认的产品与实现决定

1. 统一告警仪表盘同时保留期间指标和当前快照指标，名称必须直接说明口径。
2. 新增期间统计接口与快照统计接口；旧 `get_alert_statistics` 暂时保留兼容，内置画布迁移后再评估删除。
3. 集成源概览展示原始事件数；告警仪表盘展示告警关联事件数，二者不强求相等。
4. 告警运营大屏的趋势、来源和比率等期间指标默认使用“最近7天”相对时间窗口，即当前时刻往前 10080 分钟；当前状态类组件使用快照。
5. 内置数据源前端禁止编辑和删除，后端也必须拒绝普通接口修改和删除。
6. 初始化时内置数据源执行新增或覆盖；配置中已移除的内置数据源直接物理删除，不扫描或迁移用户画布引用。
7. 用户自定义画布引用被删除的数据源后，由组件提示数据源不存在，用户自行进入编辑状态更换。
8. 画布 A → B → A 时不得预展示上一次挂载的成功结果，必须等待本次请求返回；相同的进行中请求仍可去重。
9. “今日关闭数”本轮维持现有实现，不增加 `closed_at`，不隐藏组件，也不修改口径。
10. 本轮统一补齐告警与 CMDB 内置数据源的名称、描述、参数和出参契约；计数、比率等可计算字段必须声明为数字类型。
11. 只有 `string`、`timeRange`、`dateRange` 参数可以声明为画布筛选；数据源编辑器与后端使用同一约束。
12. 非固定组件参数允许清空；空值保存为 `null` 且请求时省略，不能自动补成 `0` 或重新回退到数据源默认值。数字 `0` 和布尔 `false` 仍是有效值。

## 5. 缺陷与解决方案

### 5.1 活动状态分布被错误拆组（Issue #4478）

#### 问题

`get_alert_status_distribution` 应返回未分派 8、待响应 8、处理中 4，但实际返回三个状态各 1。

#### 原因

`Alert.Meta.ordering` 包含 `updated_at`。当前聚合直接执行：

```python
queryset.filter(...).values("status").annotate(count=Count("id"))
```

默认排序可能使数据库把排序列带入 `GROUP BY`，同一状态按不同更新时间拆成多行。后续字典推导只保留每个状态的最后一行，因此最终看起来每类都只有 1。

代码位置：

- `server/apps/alerts/nats/nats.py:945-957`
- 正确参考：`get_alert_level_distribution` 已在聚合前调用 `.order_by()`，位于同文件约 `1036-1038`。

#### 方案

聚合前清除默认排序：

```python
status_counts = (
    queryset.filter(status__in=status_order)
    .order_by()
    .values("status")
    .annotate(count=Count("id"))
)
```

同时检查告警 NATS 统计代码中的其他 `values(...).annotate(...)`，凡是基于 `Alert` 聚合且不需要默认排序的查询，都应显式清除排序。

#### 验收

- 8 条未分派、8 条待响应、4 条处理中返回 `8/8/4`，总数 20；
- 某状态没有数据时仍返回该状态且值为 0；
- 不依赖不同数据库对 `ORDER BY/GROUP BY` 的隐式处理差异。

### 5.2 集成页面与告警页面的“事件数”口径混用

#### 问题

集成页事件数合计 34，大屏事件数为 15，用户无法从名称判断两者分别统计什么。

#### 原因

- 集成页按告警源统计收到的全部原始事件；
- 告警统计使用 `Event.objects.filter(alert__in=queryset).distinct()`，只统计已经关联授权告警的事件；
- 两个页面都写“事件数”，隐藏了是否要求关联告警这一关键条件。

#### 方案

- 集成页卡片名称或描述明确为“原始事件数”，字段语义为 `raw_event_count`；
- 告警仪表盘和告警大屏使用“告警关联事件数”，字段语义为 `linked_event_count`；
- 如果后续需要展示“未形成告警事件数”，使用 `unlinked_event_count = raw_event_count - linked_event_count`，不要把它混入告警统计概览；
- 所有按告警来源统计的 TOP 图也写明“告警关联事件来源”。

#### 验收

- 在 34 条原始事件、其中 15 条关联告警的夹具中，集成页显示 34，告警页面显示 15；
- 两个组件的名称或描述足以解释差异；
- 告警关联事件统计继续应用告警查看权限。

### 5.3 “最近 30 天”没有作用于统计概览

#### 问题

统一告警仪表盘选择最近 30 天后，告警总数、事件数、事故数、会话告警占比和聚合倍率仍按全部存量统计。

#### 原因

`get_alert_statistics` 位于 `server/apps/alerts/nats/nats.py:855-908`，没有接收或解析 `time`，直接对授权 `Alert`、其关联 `Event` 和 `Incident` 做全量统计。内置画布对应组件也没有一致的时间绑定。

#### 方案：拆成两个清晰接口

新增期间统计接口：

```python
get_alert_period_statistics(time=[start, end])
```

`time` 必填，返回：

```json
{
  "new_alert_count": 0,
  "linked_event_count": 0,
  "affected_alert_count": 0,
  "new_incident_count": 0,
  "session_alert_count": 0,
  "session_alert_rate": 0,
  "aggregation_ratio": 0
}
```

字段规则：

- `new_alert_count`：授权告警中 `created_at` 位于 `[start, end)` 的数量；
- `linked_event_count`：关联授权告警且 `received_at` 位于 `[start, end)` 的事件数量；
- `affected_alert_count`：上述期间事件关联到的去重告警数量；
- `new_incident_count`：授权范围相关事故中 `created_at` 位于 `[start, end)` 的去重数量；
- `session_alert_count`：期间新增告警中 `is_session_alert=True` 的数量；
- `session_alert_rate = session_alert_count / new_alert_count * 100`；
- `aggregation_ratio = linked_event_count / affected_alert_count`。

聚合倍率不能使用 `linked_event_count / new_alert_count`，因为期间收到的事件可以继续关联到期间开始前已经存在的告警。

新增快照统计接口：

```python
get_alert_snapshot_statistics()
```

返回当前状态字段：

```json
{
  "active_count": 0,
  "unassigned_count": 0,
  "pending_count": 0,
  "processing_count": 0,
  "auto_recovery_count": 0,
  "auto_recovery_rate": 0
}
```

其中活动状态相关字段不接收仪表盘时间范围。当前告警没有可靠的状态迁移时间，`auto_recovery_count/rate` 只能表达“当前数据库中状态为自动恢复的告警数量/占存量告警比例”，不能描述“期间自动恢复”。

旧 `get_alert_statistics` 暂时保持兼容，避免未知外部调用立刻失效；内置画布不得继续依赖其混合口径。

#### 验收

- 最近 30 天只有 2 条新告警时，期间新增告警数返回 2，而当前活动告警仍可返回 20；
- 30 天前创建的活动告警仍计入当前活动告警；
- 30 天前创建的告警在最近 30 天收到 3 个事件时，期间关联事件数增加 3，期间受影响告警数增加 1；
- 所有时间查询使用 `[start, end)`。

### 5.4 统一告警仪表盘组件名称和绑定不准确

#### 问题

当前“告警总数”“事故总数”等名称无法判断是期间、当前还是累计；部分描述声称“统计周期内”，接口却返回全量。

#### 方案

统一仪表盘按下表迁移：

| 当前名称 | 新名称 | 新接口/字段 | 是否绑定时间筛选 |
|---|---|---|---|
| 告警事件总数 | 所选时段告警关联事件数 | period / `linked_event_count` | 是 |
| 告警总数 | 所选时段新增告警数 | period / `new_alert_count` | 是 |
| 事故总数 | 所选时段新增事故数 | period / `new_incident_count` | 是 |
| 活跃告警数 | 活跃告警数 | snapshot / `active_count` | 否 |
| 自动恢复告警数 | 自动恢复状态告警数 | snapshot / `auto_recovery_count` | 否 |
| 自动恢复占比 | 自动恢复状态告警占比 | snapshot / `auto_recovery_rate` | 否 |
| 聚合倍率 | 所选时段事件聚合倍率 | period / `aggregation_ratio` | 是 |
| 会话告警占比 | 所选时段会话告警占比 | period / `session_alert_rate` | 是 |
| 告警趋势数据 | 所选时段告警与关联事件趋势 | `alert/get_alert_trend_data` | 是 |
| 告警等级分布 | 活跃告警等级分布 | 现有等级接口 + `status_filter=active` | 否 |
| 告警源事件数 TOP 5 | 所选时段告警关联事件来源 TOP 5 | 修复后的来源 TOP | 是 |
| 活跃告警 TOP 10 | 活跃告警持续时长 TOP 10 | 现有活跃 TOP | 否 |

告警源配置总数、已启用数、启用率属于当前配置快照，不需要绑定时间；只有“活跃告警源数”绑定时间。

#### 验收

- 用户仅看组件名称即可判断期间或当前口径；
- 期间组件共享仪表盘时间筛选；
- 当前快照组件不因时间筛选变化而丢失仍在处置中的旧告警。

### 5.5 告警运营大屏内部口径不统一

#### 问题

大屏同时展示今日、近 7 日、当前状态和无时间说明的全量字段；“事件数”“告警源事件 TOP10”“告警聚合压缩率”等组件无法判断窗口。

#### 方案

大屏提供全局时间筛选。绑定 `time` 筛选参数的组件跟随所选时段，快照组件不绑定时间参数：

- “今日已产生”“今日已关闭”：继续使用今日摘要接口；
- “当前处理中”“活动告警总数”“待响应”“处理中”：使用快照接口；
- “事件数”改为“所选时段告警关联事件数”；
- “近 7 日产生告警数量”“近 7 日告警接入趋势”改为“所选时段产生告警数量”“所选时段告警与关联事件趋势”；
- “告警等级分布”改为“活跃告警等级分布”；
- “活动状态分布”改为“活跃告警状态分布”；
- “活动告警持续时长 TOP10”改为“活跃告警持续时长 TOP10”；
- “告警源事件 TOP10”改为“所选时段告警关联事件来源 TOP10”；
- “告警聚合压缩率”改为“所选时段事件聚合倍率”，去掉百分号；
- “会话告警率”改为“所选时段会话告警占比”；
- “自动恢复率”改为“自动恢复状态告警占比”，因为本轮没有恢复时间字段。

这里明确使用“聚合倍率”而不是“压缩率”：倍率 3 表示平均每个受影响告警聚合 3 个事件；它不是 300% 的压缩率。

#### 验收

- 大屏所有数字从标题或是否标注“所选时段”即可识别为今日、筛选时段或状态快照；
- 当前活动告警及其分布合计一致；
- 近 7 日事件数与近 7 日来源 TOP 的合计口径一致。

### 5.6 告警源事件 TOP 不响应时间范围

#### 问题

`get_alert_source_event_top` 接收 `limit`，但完全没有解析 `time`，因此统一仪表盘切换时间范围后来源排行不变。

代码位置：`server/apps/alerts/nats/nats.py:388-421`。

#### 方案

- 增加并校验 `time=[start,end]`；
- 对授权告警关联事件按 `Event.received_at__gte=start`、`received_at__lt=end` 过滤；
- 再按 `source__name` 分组、降序、取 `limit`；
- 统一仪表盘绑定全局时间；大屏默认传滚动 10080 分钟窗口；
- 数据源和组件名称改成“告警关联事件来源 TOP N”。

#### 验收

- 改变时间范围后排行和数量重新计算；
- TOP 合计不超过相同窗口的 `linked_event_count`；
- 无事件时返回空数组，组件显示暂无数据。

### 5.7 告警源总数、启用数和启用率统计范围错误

#### 问题

实际存在 11 个告警源、启用 10 个，但仪表盘显示总数 4、启用 4、启用率 100%。

#### 原因

`get_alert_source_statistics` 先从已关联告警事件提取 `source_id`，再构造 `visible_sources`：

```python
visible_source_ids = event_qs.values_list("source_id", flat=True).distinct()
visible_sources = AlertSource.objects.filter(id__in=visible_source_ids)
```

因此“告警源总数”实际变成了“历史上产生过关联事件的来源数”，没有事件的已配置来源被排除。

代码位置：`server/apps/alerts/nats/nats.py:451-504`。

#### 方案

- `total_count`：当前用户可见范围内的 `AlertSource` 配置总数；
- `enabled_count`：其中 `is_active=True` 的数量；
- `enabled_rate = enabled_count / total_count * 100`；
- `active_count`：在所选期间内至少收到一条事件的去重来源数；
- 总数、启用数和启用率是当前配置快照，不受时间筛选影响；活跃数受时间筛选影响；
- 如果 `AlertSource` 当前没有组织权限字段，需要先明确其产品可见范围。本轮不得继续用“是否产生过授权告警事件”冒充配置可见性。

#### 验收

- 11 个来源、10 个启用时返回总数 11、启用 10、启用率 90.9%；
- 一个从未产生事件的已配置来源仍计入总数和启用数；
- 活跃来源数随时间范围变化。

### 5.8 内置数据源配置升级没有同步

#### 问题

YAML 中部分时间参数已经改为 `filterType: filter`，数据库仍保留旧的 `filterType: params` 和 10080 分钟默认值，导致仪表盘显示最近 30 天时，组件实际仍使用自己的固定 7 天参数。

#### 原因

当前存在两条内置数据源初始化路径：

1. `batch_init` 调用 `init_source_api_data(force_update=True)`，读取 `support-files/source_api.json`；
2. 随后调用 `init_builtin_canvases`，读取 `builtin_canvases.yaml` 及扩展 YAML；
3. `init_builtin_canvases._build_conflict_decisions()` 对数据源硬编码 `skip`；
4. `source_api.json` 与 `builtin_canvases.yaml` 的数据源集合和部分参数并不完全一致。

相关代码：

- `server/apps/core/management/commands/batch_init.py:146-155`
- `server/apps/operation_analysis/management/commands/init_source_api_data.py:72-141`
- `server/apps/operation_analysis/management/commands/init_builtin_canvases.py:77-99`
- `server/apps/operation_analysis/services/import_export/import_service.py:325-386` 已经支持 `overwrite`，但初始化没有选择它。

#### 方案

不新增独立的“对账服务”或退役状态，直接收敛现有初始化命令：

1. 给 `DataSourceAPIModel` 增加：
   - `is_build_in`：是否由系统内置配置管理；
   - `build_in_key`：内置配置中的稳定键，允许为空，内置数据源必须唯一。
2. 将 `source_api.json`、基础 `builtin_canvases.yaml` 和 `OPERATION_ANALYSIS_BUILTIN_CANVAS_FILES` 中的数据源视为本次启动的完整内置配置集合。
3. 同一 `build_in_key` 在多份配置中出现时，定义必须一致；通过测试阻止两份配置再次漂移。不要依赖“谁最后执行谁覆盖”的隐式优先级。
4. 对完整集合逐条处理：
   - 不存在：新增并标记内置；
   - 已存在：覆盖名称、接口、描述、类型、连接/查询配置、参数、图表类型、字段定义、标签、命名空间和组织等声明式配置；
   - 敏感占位符继续复用 `ImportService` 现有的旧值补全规则，不把 `******` 写入数据库。
5. 首次升级旧数据时，以模型联合唯一约束保护的精确 `(name, rest_api)` 作为旧内置数据源稳定身份，并补上 `is_build_in/build_in_key`；不得只按名称或只按接口认领，也不依赖可能因历史页面编辑而变化的 `created_by`。发生 `build_in_key` 指向不同记录等无法确认的唯一键冲突时明确失败。
6. 完成新增/覆盖和内置画布更新后，删除数据库中 `is_build_in=True` 但 `build_in_key` 已不在完整配置集合中的数据源。

删除采用已经确认的产品取舍：直接物理删除，不扫描用户自定义画布引用，不增加“已退役”状态。自定义画布中的旧 ID 保留为失效引用。

实现初始化修改前必须先阅读 `docs/operations/server-startup-dependencies.md`。该同步只能依赖本地配置和数据库，不得在 `batch_init` 中依赖同一 Supervisor 下尚未就绪的 HTTP、NATS responder 或异步任务。

#### 验收

- 修改一个内置数据源参数后重复执行初始化，数据库变成新值；
- 重复初始化不产生重复数据源；
- 新增配置自动创建数据源；
- 从完整内置配置集合移除数据源后，数据库记录被物理删除；
- 用户自定义数据源不被覆盖或删除；
- 两份内置配置对同一键声明不同内容时，自动化测试失败并指出键名；
- 初始化失败时事务回滚，不出现画布已经更新但数据源只更新一半的状态。

### 5.9 内置数据源仍可通过页面和普通接口编辑、删除

#### 问题

当前 `DataSourceAPIModel` 没有内置身份字段，列表页始终显示编辑和删除按钮；后端 `update/destroy` 也没有内置保护，`destroy` 会直接 `instance.delete()`。

代码位置：

- 模型：`server/apps/operation_analysis/models/datasource_models.py:93-127`
- 序列化器：`server/apps/operation_analysis/serializers/datasource_serializers.py:54-108`
- 后端更新/删除：`server/apps/operation_analysis/views/datasource_view.py:563-582`
- 前端操作列：`web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx:236-266`

#### 方案

前端：

- 数据源列表显示“内置”标识；
- 内置数据源把“编辑”替换为“查看”，复用现有抽屉展示完整配置，但所有表单、参数表、字段定义、上传和预览操作均为只读，且不显示提交按钮；
- 内置数据源隐藏删除操作，保留查看、导出和画布选用能力。

后端：

- 序列化器把 `is_build_in/build_in_key` 设为只读，普通请求不能伪造内置身份；
- `update`、`partial_update` 和 `destroy` 对内置数据源返回明确的 403 业务错误；
- 只有系统初始化路径可以修改或删除内置数据源；
- `DataSourceBriefSerializer` 等列表结构返回 `is_build_in`，供前端判断。

删除后的失效体验：

- 现有组件已经能区分数据源加载失败与“数据源不存在”，位置为 `widgetDataRenderer.tsx:904-919`；
- 失效只影响对应组件，不能让整个画布崩溃。

#### 验收

- 有普通编辑/删除权限的用户仍不能修改或删除内置数据源；
- 内置数据源列表只显示“查看”而非“编辑”，查看抽屉内不能修改或提交配置；
- 用户不能通过提交 `is_build_in=true` 把自定义数据源变成内置；
- 初始化命令可以正常覆盖和删除内置数据源；
- 内置数据源被升级删除后，引用它的自定义画布仅对应组件显示可操作的缺失提示。

### 5.10 画布切换后成功缓存阻止重新取数

#### 问题

从画布 A 切换到 B，再切回 A，A 的组件没有重新请求数据源，继续显示第一次进入 A 时的旧数据。

#### 原因

旧实现的成功结果缓存是模块级 `Map`，键由以下内容组成：

```text
scopeId : requestVersionKey : requestSignature
```

重新进入 A 时，`dashboardId`、请求参数和重载/筛选版本又回到相同值，因此会命中旧键。即使同时重新请求，旧成功结果也会先被写回新挂载的组件，使尚未返回的页面看起来已经完成加载。

此外当前缓存：

- 没有 TTL；
- 没有容量上限；
- 失败响应也跨挂载缓存；
- 模块生命周期内不会清理。

相关代码：

- `web/src/app/ops-analysis/utils/widgetRequestCache.ts`
- `web/src/app/ops-analysis/components/widgetDataRenderer.tsx:556-584`
- `web/src/app/ops-analysis/components/widgetDataRenderer.tsx:628-694`
- `web/src/app/ops-analysis/components/widgetDataRenderer.tsx:757-829`

#### 方案

取消跨挂载的成功结果缓存，只保留进行中请求去重：

1. 首次进入：正常请求并展示加载状态。
2. A → B → A：A 的新挂载不回填旧成功结果，等待本次请求返回。
3. 多个相同组件同时请求相同键：继续使用现有 in-flight 去重，不重复打后端。
4. 请求成功或失败都不写入跨挂载结果缓存；下次进入必须重新请求。
5. 手动刷新、统一筛选搜索、命名空间搜索和表格查询变化继续产生新的请求版本或签名。

关键点是区分“进行中的同一请求”和“已经完成的旧结果”：前者可以共享 Promise，后者不能跨画布挂载预展示。

#### 验收

- 首次进入 A 请求一次；
- 切到 B 后请求 B；
- 切回 A 时显示加载状态，网络面板必须出现 A 的新请求，响应后才展示新值；
- 两个相同请求并发时后端只收到一次；
- A 首次请求失败后，切走再回来会重新请求；
- 已完成的旧结果不会跨挂载保留或展示。

### 5.11 数据完整性指标混合了告警和事件分母

#### 问题

页面把所有指标称为“缺少……事件占比”，但后端实际混用两类对象：

- `resource_id`、`rule_id` 位于 `Alert`，分母是告警数；
- `service`、`item`、`external_id` 位于 `Event`，分母是事件数。

当前接口还会先按 `Alert.created_at` 过滤告警，再统计这些告警关联的所有事件；这不等价于“期间收到的事件完整性”。

代码位置：`server/apps/alerts/nats/nats.py:617-689`。

#### 方案

一个接口可以保留，但返回结构和页面分组必须明确拆成两类：

```json
{
  "alert_quality": {
    "total_count": 0,
    "missing_resource_id_count": 0,
    "missing_resource_id_rate": 0,
    "missing_rule_id_count": 0,
    "missing_rule_id_rate": 0
  },
  "event_quality": {
    "total_count": 0,
    "missing_service_count": 0,
    "missing_service_rate": 0,
    "missing_item_count": 0,
    "missing_item_rate": 0,
    "missing_external_id_count": 0,
    "missing_external_id_rate": 0
  }
}
```

- 告警完整性：按 `Alert.created_at` 过滤；
- 事件完整性：按 `Event.received_at` 过滤，并限制为授权告警关联事件；
- 每个指标同时返回缺失数量、样本总数和比例，便于核数；
- 页面标题分别使用“期间告警完整性”和“期间告警关联事件完整性”；
- 分母为 0 时比例显示 `--`，而不是声称缺失率为 0%。

#### 验收

- 告警和事件指标分别使用自己的总数；
- 期间外事件不会因为关联到期间内新建告警而被计入；
- 每个比例都能用同一响应中的 `missing_count / total_count` 复算。

### 5.12 通知组件的时间绑定、空样本和单位不一致

#### 问题

当时环境没有通知记录，数量显示 0 本身正确，但存在以下配置问题：

- “通知失败率”的 `time__timeRange` 绑定为 `false`；
- “按渠道通知成功率”保留组件私有的 10080 分钟参数，可能与统一筛选冲突；
- 无通知样本时显示 0% 容易被理解为真实失败率/成功率；
- 百分比字段的单位和转换规则需要统一。

配置位置：`server/apps/operation_analysis/support-files/builtin_canvases.yaml` 约 `721-934`。

#### 方案

- 通知成功数、失败数、成功率、失败率、渠道成功率全部绑定同一个仪表盘时间范围；
- 移除会覆盖统一筛选的组件私有 7 天参数，或改为统一筛选参数；
- 后端百分比字段统一返回 `0..100`；前端只添加 `%` 单位，不再乘 100；
- `total_count=0` 时：成功数和失败数显示 0，成功率和失败率显示 `--`，渠道图显示“暂无数据”；
- 有样本时验证 `success_count + failed_count` 与总数的业务关系。如果存在其他通知状态，不能强制假设二者之和等于总数，描述中要说明。

#### 验收

- 切换统一时间范围后所有通知组件一起重新请求；
- 无通知时不展示误导性的 0% 成功率；
- 后端返回 75.0 时前端显示 75.0%，不是 7500%。

### 5.13 百分比重复换算，聚合倍率被误称为压缩率

#### 问题

后端 `session_alert_rate`、`auto_recovery_rate` 等已经乘以 100，大屏配置又设置 `conversionFactor: 100`。`aggregation_ratio` 本来是倍率，大屏也添加 `%` 并乘 100。

配置位置：`builtin_canvases.yaml` 约 `2047-2096`。

#### 方案

- 百分比接口统一返回 `0..100`，组件只设置 `unit: '%'`，删除 `conversionFactor: 100`；
- 聚合倍率返回普通数值，例如 `3.25`，不设置百分号，不做乘 100；
- “告警聚合压缩率”统一改为“事件聚合倍率”；
- 如果未来确实需要压缩率，应单独定义公式和字段，例如 `1 - affected_alert_count / linked_event_count`，不能复用倍率字段。

#### 验收

- 后端 75.0 显示为 75.0%；
- 聚合倍率 3.25 显示为 3.25；
- 页面上不再出现把倍率 0.75 显示成 75% 的混合语义。

### 5.14 相对时间的日桶边界

#### 问题

`_generate_time_periods` 的 day 分支原来使用：

```python
num_periods = (end_dt.date() - start_dt.date()).days + 1
```

该实现会在结束时间恰好是零点时仍生成结束日的空桶，与查询使用的 `[start, end)` 半开区间不一致。

“最近7天”是相对时间选择器的快捷项，定义为当前时刻往前 10080 分钟。当开始和结束不在零点时，这个滚动 168 小时区间通常覆盖 8 个自然日，因此按 `day` 分组返回 8 个日桶是预期行为，首尾为两个不完整日桶。

代码位置：`server/apps/alerts/nats/nats.py:214-244`。

#### 方案

- 保持时间选择器的现有相对时间协议：`selectValue: 10080`；
- 请求转换只获取一次当前时间，保证开始和结束严格相差 10080 分钟；
- 统计查询仍使用 `[start, end)`；
- day 桶生成逻辑以半开区间实际覆盖的自然日为准：结束时间是零点时不包含结束日，否则包含结束日的部分日桶。

#### 验收

- 选择“最近7天”时，请求开始和结束严格相差 `604800000` 毫秒；
- 非零点时刻的滚动 168 小时按自然日聚合时可返回 8 个日桶，且首尾桶只统计实际区间内的数据；
- 结束时间恰好是零点时，不生成结束日空桶；
- 跨月、跨年和夏令时区域仍按目标时区生成正确日桶。

### 5.15 告警与 CMDB 内置数据源契约不完整

#### 问题

告警与 CMDB 数据源分布在 `source_api.json`、基础内置画布 YAML 和商业版扩展 YAML 中。部分配置存在名称和真实统计口径不一致、描述为空、参数缺少可选范围、出参字段缺失或计数字段被声明为字符串等问题；同一告警趋势接口还存在两份不同名称和图表类型的逻辑重复配置。

#### 方案

- 保留三个配置文件按稳定键合并的现有架构，不要求同一数据源在多个文件中重复声明；初始化后的有效数据源集合是三者并集；
- 同一稳定键在多个文件出现时配置必须完全一致，否则初始化拒绝合并；
- 名称和描述直接说明统计对象、时间语义和排序方向，避免使用“概览”“统计”等无法判断口径的泛化名称；
- 参数补齐中文别名、正确类型、固定值或可选范围；分页、返回条数和比率等数值参数使用 `number`；
- 可枚举参数使用静态下拉约束，时间参数继续通过画布筛选联动；
- 补齐接口实际返回的固定字段，计数、比率和时长使用 `number`；动态时间序列或专用结构可以不展开 `field_schema`，但描述必须明确返回内容；
- 告警趋势统一使用 `告警趋势::alert/get_alert_trend_data`，内置画布不再引用无时间语义的兼容接口 `alert/get_alert_statistics`；
- CMDB 无权限返回保持与正常返回相同的字段集合，值统一为零，避免组件字段在权限边界上消失。

#### 验收

- 告警与 CMDB 内置数据源的名称、描述、参数和固定出参字段与 handler 契约一致；
- 所有内置画布数据源引用均能在合并后的有效数据源集合中精确命中；
- 同一 `(name, rest_api)` 不存在互相漂移的重复定义，同一逻辑接口不再以多个内置身份出现；
- 基础版与商业版 YAML 均能独立解析并通过初始化合并校验；
- CMDB 统计接口在有权限和无权限场景返回相同字段集合。

## 6. 本轮明确不处理

### 6.1 今日关闭数使用 `updated_at`

现状：`get_alert_today_status_summary` 通过“当前状态属于关闭状态且 `updated_at` 在今日”推断今日关闭。后续其他更新可能改变 `updated_at`，因此它不是可靠的关闭时间。

位置：`server/apps/alerts/nats/nats.py:911-941`。

本轮决定：维持原样，不新增 `closed_at`，不修改组件，不隐藏数据。测试不要把该已知限制误当成本轮必须修复的失败。只有用户重新打开此议题时再设计状态迁移时间。

## 7. 当前已核对为合理的数据

以下结果在当时数据集上与现有模型一致，不应因为“看起来异常”而直接改成别的数字：

- 当前活动告警数 20；
- 当前活跃告警等级分布 8/7/5，合计 20；
- 活跃告警 TOP 中出现 2023、2024、2025 年创建的告警：只要仍处于活动状态，就应继续出现；
- 最近 30 天新增告警 2、告警关联事件 2；
- 通知成功数和失败数均为 0：当时没有通知记录；
- 事故数 0：当时没有符合条件的事故。

这些数据仍需在接口口径调整后通过自动化测试复核，但不属于已确认的统计错误。

## 8. 建议实现顺序

1. 阅读 `docs/operations/server-startup-dependencies.md`，确认初始化修改不引入启动期外部依赖。
2. 为状态分布、期间统计、快照统计、来源统计、数据质量和时间桶补充后端失败测试。
3. 修复 Issue #4478 的聚合排序问题。
4. 实现期间/快照统计接口，迁移统一仪表盘和告警大屏组件名称、字段及时间绑定。
5. 修复来源 TOP、来源配置统计、数据质量和通知组件口径。
6. 统一百分比与聚合倍率展示。
7. 增加内置数据源身份字段，改造现有初始化命令完成新增、覆盖、物理删除，并增加前后端只读限制。
8. 移除组件成功结果的跨挂载预展示，仅保留进行中请求去重，补 A → B → A 回归测试。
9. 执行配置静态校验、后端测试、前端脚本测试和真实页面核数。

这个顺序不是要求一个超大提交。可以按后端统计、内置配置、前端缓存三个可独立验证的提交组织，但最终必须一起重新校对两个内置页面。

## 9. 测试与验证清单

### 9.1 后端统计测试

- `get_alert_status_distribution` 在相同状态、不同 `updated_at` 下正确聚合；
- 期间接口严格使用 `[start, end)`；
- 新告警、期间事件、受影响告警和新事故使用各自正确时间字段；
- 旧告警在期间收到新事件时，聚合倍率分母使用受影响告警数；
- 快照接口不接受或忽略时间筛选，并保留期间前创建的活动告警；
- 来源 TOP 响应时间范围；
- 告警源总数包含没有事件的已配置来源；
- 数据质量的告警和事件分母分离；
- 无通知样本时接口和 UI 不伪造有效百分比；
- 最近7天严格使用滚动 10080 分钟窗口，日桶仅覆盖 `[start, end)` 实际相交的自然日。

### 9.2 内置数据源测试

- 模型迁移后自定义数据源默认 `is_build_in=False`；
- 普通序列化请求不能写入内置标识；
- 内置数据源 update、partial_update、destroy 均被拒绝；
- 初始化新增缺失项、覆盖已有项、删除配置移除项；
- 重复初始化幂等；
- 配置冲突或中途失败时事务回滚；
- 基础 JSON、基础 YAML、扩展 YAML 的完整键集合参与删除判断；
- 相同键的重复定义不一致时测试失败；
- 敏感占位符覆盖时保留数据库原值。

### 9.3 前端缓存测试

- 首次挂载请求；
- 有历史成功结果的重新挂载不预展示旧值，并重新发起请求；
- in-flight 请求去重；
- 成功和失败结果都不跨挂载缓存；
- 手动刷新、统一筛选、命名空间和表格查询仍触发请求。

### 9.4 页面核数

使用一套可控制的夹具同时打开：

1. 告警集成源概览；
2. `统一告警中心仪表盘_内置`；
3. `告警运营大屏_内置`。

逐项确认：

- 集成页原始事件数与数据库原始事件一致；
- 告警页面关联事件数与关联授权告警的事件一致；
- 统一时间筛选只影响期间组件；
- 当前快照组件保持当前状态口径；
- 活动告警总数等于活动状态分布之和，也等于活动等级分布之和；
- 来源配置总数、启用数和启用率可直接由 `AlertSource` 复算；
- 大屏的最近7天组件共享同一滚动 10080 分钟窗口；
- 百分比和倍率没有重复换算；
- A → B → A 能观察到 A 的重新取数请求。

## 10. 主要代码定位

| 范围 | 文件 |
|---|---|
| 告警统计 NATS 接口 | `server/apps/alerts/nats/nats.py` |
| 告警模型默认排序 | `server/apps/alerts/models/models.py` |
| 内置画布和数据源配置 | `server/apps/operation_analysis/support-files/builtin_canvases.yaml` |
| 旧内置数据源配置 | `server/apps/operation_analysis/support-files/source_api.json` |
| 批量初始化顺序 | `server/apps/core/management/commands/batch_init.py` |
| 数据源初始化 | `server/apps/operation_analysis/management/commands/init_source_api_data.py` |
| 内置画布初始化 | `server/apps/operation_analysis/management/commands/init_builtin_canvases.py` |
| 导入覆盖实现 | `server/apps/operation_analysis/services/import_export/import_service.py` |
| 数据源模型 | `server/apps/operation_analysis/models/datasource_models.py` |
| 数据源序列化器 | `server/apps/operation_analysis/serializers/datasource_serializers.py` |
| 数据源更新/删除接口 | `server/apps/operation_analysis/views/datasource_view.py` |
| 数据源管理页面 | `web/src/app/ops-analysis/(pages)/settings/dataSource/page.tsx` |
| 组件数据请求 | `web/src/app/ops-analysis/components/widgetDataRenderer.tsx` |
| 组件请求缓存 | `web/src/app/ops-analysis/utils/widgetRequestCache.ts` |
| 统一筛选契约 | `specs/capabilities/dashboard-unified-filter.md` |
| Server 启动依赖约束 | `docs/operations/server-startup-dependencies.md` |

## 11. 完成定义

本变更只有同时满足以下条件才算完成：

- Issue #4478 的状态分布计数正确；
- 原始事件与告警关联事件在名称、接口和页面上不再混淆；
- 统一告警仪表盘的期间组件真正响应时间筛选，当前组件维持快照；
- 告警运营大屏所有指标具有明确的今日、所选时段或状态快照口径；
- 告警源配置统计、来源 TOP、数据完整性、通知、百分比和时间桶通过核数；
- 内置数据源不可人工修改，升级时能够新增、覆盖和物理删除；
- 删除内置数据源后，自定义画布中的旧引用以组件级错误安全降级；
- 画布 A → B → A 会重新请求数据；
- “今日关闭数”保持本轮明确的暂缓状态；
- 已运行与影响范围匹配的新鲜测试，并保留测试命令和结果。
