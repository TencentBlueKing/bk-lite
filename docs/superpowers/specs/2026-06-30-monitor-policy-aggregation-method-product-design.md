# 监控策略汇聚方法产品设计

## 1. 产品判断

监控策略的“分组维度、汇聚周期、汇聚方法”应被设计成一个完整的阈值计算模型，而不是让用户直接选择 PromQL 函数。

推荐产品心智：

```text
先确定告警对象是谁：分组维度
再确定看多长时间：汇聚周期
最后确定如何得到判断值：汇聚方法
```

本次设计建议将页面汇聚方法收敛为 6 个业务方法：

- 平均值 `AVG`
- 最大值 `MAX`
- 最小值 `MIN`
- 累计值 `SUM`
- 有效数量 `COUNT`
- 最近值 `LAST`

其中 `AVG/MAX/MIN/SUM/COUNT` 都应明确使用汇聚周期；`LAST` 作为状态类指标的特殊方法保留。

## 2. 背景与问题

### 仓库事实

当前后端查询生成在 `server/apps/monitor/tasks/utils/policy_methods.py` 中维护 `METHOD` 和 `build_policy_query`。

当前页面方法列表在 `web/src/app/monitor/hooks/event.tsx` 中包含：

```text
SUM
SUM_OVER_TIME
MAX
MAX_OVER_TIME
MIN
MIN_OVER_TIME
AVG
AVG_OVER_TIME
COUNT
LAST_OVER_TIME
```

当前策略预览已迁移到后端服务 `server/apps/monitor/services/policy_preview.py`，但仍依赖同一类聚合查询生成能力。

策略模板来源包括：

- 文件模板：`server/apps/monitor/support-files/plugins/**/policy.json`
- 数据库模板：`PolicyTemplate.templates`

### 当前问题

1. `AVG/MAX/MIN/SUM` 可以按分组维度聚合，但最终更接近只取扫描点附近的瞬时结果，用户配置的汇聚周期没有稳定参与最终阈值判断。
2. `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME` 带有时间窗口，但没有统一做到“先按分组维度聚合，再计算周期结果”。
3. `COUNT` 更接近当前时刻序列数量，不适合表达“汇聚周期内仍有数据的有效序列数量”。
4. `LAST_OVER_TIME` 对接口状态、服务状态、枚举状态有实际价值，但它是状态快照类方法，不应和数值趋势聚合混在同一类心智中。
5. 页面暴露过多底层函数名，用户需要理解 PromQL 函数差异才能正确配置策略。

## 3. 设计目标

- 让用户按业务意图选择汇聚方法，而不是按底层函数名选择。
- 让“分组维度、汇聚周期、汇聚方法”同时生效。
- 策略预览与后台扫描使用同一查询生成逻辑。
- 保留 `LAST` 以支持状态类指标。
- 为旧策略实例与旧策略模板提供明确迁移规则。
- 为指标模板提供推荐汇聚方法，降低新建策略误配概率。

## 4. 非目标

- 本设计不引入完整 PromQL 编辑器。
- 本设计不要求用户手动配置 subquery resolution。
- 本设计不改变阈值比较符、触发次数、恢复条件等策略生命周期逻辑。
- 本设计不处理日志告警策略聚合逻辑。

## 5. 用户侧功能设计

### 5.1 字段心智

页面应将聚合配置解释为：

| 字段 | 用户理解 | 示例 |
| --- | --- | --- |
| 分组维度 | 最终按哪些对象分别判断和产生告警 | `instance_id`、`interface` |
| 汇聚周期 | 每次扫描向前查看多长时间的数据 | 5 分钟 |
| 汇聚方法 | 在这个时间窗口里如何算出阈值判断值 | 最大值、平均值、最近值 |

建议文案：

```text
分组维度决定哪些对象会被独立判断并产生告警。
汇聚周期是观察窗口，不是策略扫描频率。
汇聚方法决定窗口内如何计算阈值判断值。
```

### 5.2 页面方法列表

页面展示 6 个方法：

| 展示名称 | 标签 | 适用场景 |
| --- | --- | --- |
| 平均值 | `AVG` | 使用率、延迟、负载等整体水平 |
| 最大值 | `MAX` | 磁盘使用率、队列堆积、错误率、连接数等峰值风险 |
| 最小值 | `MIN` | 可用率、健康分、剩余容量、最小副本数等低值风险 |
| 累计值 | `SUM` | 每周期增量、周期内新增数量 |
| 有效数量 | `COUNT` | 接口数、磁盘数、进程数、有效序列数量 |
| 最近值 | `LAST` | 接口 up/down、服务状态、枚举状态、开关状态 |

页面不再展示：

```text
AVG_OVER_TIME
MAX_OVER_TIME
MIN_OVER_TIME
SUM_OVER_TIME
```

### 5.3 方法提示

`SUM` 需要提示：

```text
累计值适合每个采样点本身就是增量的指标。
对于 CPU 使用率、内存使用率、磁盘使用率等瞬时值指标，累计值通常不适合，因为结果会受采样频率影响。
```

`LAST` 需要提示：

```text
最近值适合状态、枚举、开关类指标。
如果同一分组下存在多条状态序列，请把能区分状态对象的维度加入分组。
例如接口状态通常应按 instance_id + interface 分组。
```

## 6. 底层语义设计

### 6.1 数值趋势类

数值类方法统一为“先按分组维度聚合，再按汇聚周期计算”。

`AVG`：

```promql
avg_over_time((avg(metric) by (group_by))[period:resolution])
```

`MAX`：

```promql
max_over_time((max(metric) by (group_by))[period:resolution])
```

`MIN`：

```promql
min_over_time((min(metric) by (group_by))[period:resolution])
```

`SUM`：

```promql
sum_over_time((sum(metric) by (group_by))[period:resolution])
```

示例：

```promql
avg_over_time((avg(disk_used_percent) by (instance_id))[5m:1m])
```

该查询表示：

1. 每个采样点先按 `instance_id` 聚合同一实例下的磁盘序列。
2. 再取最近 5 分钟内多个实例级采样点。
3. 最后计算平均值作为阈值判断值。

### 6.2 有效数量

`COUNT` 表示“汇聚周期内仍有数据的有效序列数量”：

```promql
count(last_over_time(metric[period])) by (group_by)
```

示例：

```promql
count(last_over_time(interface_info[5m])) by (instance_id)
```

该查询表示：统计每个实例最近 5 分钟内仍有数据的接口序列数量。

### 6.3 最近值

`LAST` 保留状态快照语义：

```promql
any(last_over_time(metric[period])) by (group_by)
```

示例：

```promql
any(last_over_time(interface_oper_status[5m])) by (instance_id, interface)
```

该查询表示：每个接口输出最近 5 分钟内最后一次有效状态。

如果一个设备有 10 个接口，按 `instance_id + interface` 分组，且 10 个接口最近 5 分钟都有数据，则会输出 10 条接口状态序列。

### 6.4 Subquery resolution

数值趋势类不建议生成裸 subquery：

```promql
[5m:]
```

原因：当前策略查询的外层 step 通常按汇聚周期生成。如果 subquery 不显式指定 resolution，可能退化为窗口内采样点过少，导致 `avg_over_time/max_over_time/min_over_time/sum_over_time` 没有真正覆盖周期内多点。

建议底层生成：

```promql
[5m:1m]
```

或根据采集间隔和汇聚周期动态计算 resolution。第一阶段可采用保守默认值，例如 `1m`，后续再结合采集频率优化。

## 7. 指标推荐方法

策略模板或指标元数据可提供推荐汇聚方法。推荐不应作为强制限制，只作为默认值和提示。

建议规则：

| 指标类型 | 推荐方法 | 说明 |
| --- | --- | --- |
| 使用率、延迟、负载 | `AVG` | 关注周期内整体水平，减少单点抖动 |
| 容量风险、队列堆积、错误率、连接数上限 | `MAX` | 关注周期内峰值风险 |
| 可用率、剩余容量、健康分 | `MIN` | 关注周期内最低点 |
| 每周期增量、周期内新增量 | `SUM` | 关注周期总量 |
| 序列存在性、接口/磁盘/进程数量 | `COUNT` | 关注有效序列数量 |
| 状态、枚举、up/down、开关 | `LAST` | 关注最近有效状态 |

示例：

- 磁盘使用率：默认 `MAX`，可选 `AVG`。
- 接口状态：默认 `LAST`，建议分组 `instance_id + interface`。
- 请求增量：默认 `SUM`。
- 接口清单：默认 `COUNT`。

## 8. 旧方法迁移规则

### 8.1 用户已创建策略

需要迁移 `MonitorPolicy.algorithm`：

| 旧值 | 新值 | 说明 |
| --- | --- | --- |
| `avg_over_time` | `avg` | 以后由 `AVG` 的新周期语义承载 |
| `max_over_time` | `max` | 以后由 `MAX` 的新周期语义承载 |
| `min_over_time` | `min` | 以后由 `MIN` 的新周期语义承载 |
| `sum_over_time` | `sum` | 以后由 `SUM` 的新周期语义承载 |
| `last_over_time` | `last_over_time` | 保留，页面展示为 `LAST` |
| `avg/max/min/sum/count` | 保持 | 底层语义升级为周期窗口计算 |

### 8.2 监控策略模板

需要同步处理：

- `server/apps/monitor/support-files/plugins/**/policy.json`
- `PolicyTemplate.templates`

模板中的迁移规则与策略实例一致：

```text
avg_over_time -> avg
max_over_time -> max
min_over_time -> min
sum_over_time -> sum
last_over_time -> last_over_time
```

新导入模板时也应做归一化保护，避免旧模板文件再次写入旧方法。

### 8.3 API 兼容

短期内后端可继续接受旧四类数值 `*_over_time`，但保存或执行前应归一化为新值。

这样可以兼容：

- 旧页面缓存
- 外部 API 调用
- 未及时更新的模板数据

## 9. 前后端影响范围

### 前端

需要调整：

- 策略表单方法列表：`web/src/app/monitor/hooks/event.tsx`
- 方法 tooltip 文案
- 策略详情/编辑页旧值展示归一
- 策略模板批量创建页的默认方法展示

Storybook 原型：

- `web/src/stories/monitor-strategy-aggregation-designer.stories.tsx`

### 后端

需要调整：

- 聚合方法归一化函数
- `server/apps/monitor/tasks/utils/policy_methods.py`
- 策略扫描查询生成
- 策略预览查询生成
- `MonitorPolicySerializer` 的合法方法校验与保存归一
- `PolicyTemplate.templates` 数据迁移或导入归一
- `MonitorPolicy.algorithm` 数据迁移

## 10. 验收标准

### 产品验收

- 页面只展示 `AVG/MAX/MIN/SUM/COUNT/LAST` 六个方法。
- 页面不再展示 `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME`。
- 用户能从文案理解：
  - 分组维度决定告警对象。
  - 汇聚周期是观察窗口。
  - 汇聚方法决定窗口内如何得到阈值判断值。
- `LAST` 明确定位为状态类方法。
- `SUM` 对瞬时值指标有风险提示。
- 指标模板可提供推荐汇聚方法。

### 查询语义验收

- `AVG` 生成先分组、再周期平均的查询。
- `MAX` 生成先分组、再周期最大值的查询。
- `MIN` 生成先分组、再周期最小值的查询。
- `SUM` 生成先分组、再周期累计的查询。
- `COUNT` 统计周期内仍有数据的有效序列数量。
- `LAST` 保留周期内最近有效状态语义。
- 数值趋势类查询显式带 subquery resolution。

### 迁移验收

- 已创建策略中的旧四类数值 `*_over_time` 被迁移为新方法。
- 已创建策略中的 `last_over_time` 保留。
- 策略模板文件与数据库模板完成同样转换。
- 新建或批量创建策略不会再写入旧四类数值 `*_over_time`。

## 11. 待产品确认点

1. `SUM` 是否继续作为通用可选项展示，还是仅在增量类指标中推荐但仍允许用户手动选择。
2. 数值趋势类 subquery resolution 第一阶段是否统一默认 `1m`，还是必须读取采集间隔动态生成。
3. 指标推荐方法的数据来源：先写入策略模板，还是扩展指标元数据。
4. `LAST` 页面展示名称使用“最近值 LAST”，还是继续使用“LAST_OVER_TIME”作为技术标签。

