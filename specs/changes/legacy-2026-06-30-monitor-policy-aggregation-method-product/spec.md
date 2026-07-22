# Historical Superpowers change: 2026-06-30-monitor-policy-aggregation-method-product

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-30-monitor-policy-aggregation-method-product-design.md

## 1. 产品判断

本次调整后，监控策略不再把“分组维度怎么合并”和“汇聚周期内怎么计算”混在同一个字段里，而是拆成两个明确配置：

```text
先按分组维度确定告警对象
再用分组聚合方式合并未入选维度的多条序列
最后用汇聚方式在汇聚周期内计算阈值判断值
```

页面字段建议为：

| 字段 | 配置项 | 默认值 | 用户理解 |
| --- | --- | --- | --- |
| 分组维度 | 维度多选 | 指标模板推荐 | 最终按哪些对象分别判断和产生告警 |
| 分组聚合方式 | `AVG/MAX/MIN/SUM/COUNT` | `AVG` | 同一分组下多条序列先怎么合并 |
| 汇聚周期 | 时间窗口 | 5 分钟 | 每次扫描向前观察多长时间 |
| 汇聚方式 | `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME/COUNT_OVER_TIME/LAST_OVER_TIME` | `AVG_OVER_TIME` | 窗口内如何得到最终判断值 |

这套模型比“只保留 AVG/MAX/MIN/SUM/COUNT/LAST 六个业务方法”更贴近产品最新结论：保留 over_time 方法作为窗口语义，同时新增分组聚合方式承接 by 前的聚合语义。

## 2. 背景与问题

当前旧方法列表同时包含：

```text
AVG
MAX
MIN
SUM
COUNT
AVG_OVER_TIME
MAX_OVER_TIME
MIN_OVER_TIME
SUM_OVER_TIME
LAST_OVER_TIME
```

存在的问题：

1. `AVG/MAX/MIN/SUM` 能按分组维度聚合，但汇聚周期没有稳定参与最终阈值判断。
2. `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME` 能表达时间窗口，但没有统一做到先按分组维度聚合。
3. 旧 `COUNT` 只表达当前时刻序列数量，但没有和窗口内最近有效数量语义绑定。
4. `LAST_OVER_TIME` 对接口状态、服务状态、枚举状态有价值，应保留为状态类窗口方法。
5. 当前 step 按周期生成时，如果 subquery 不显式指定 resolution，窗口函数可能只作用在极少采样点上，和“看一个周期”心智不一致。

## 3. 设计目标

- 让“分组维度、分组聚合方式、汇聚周期、汇聚方式”同时生效。
- 让策略预览与后台扫描使用同一套查询生成逻辑。
- 保留 `LAST_OVER_TIME` 支持状态类指标。
- 将 `COUNT` 迁移为“分组 COUNT + 窗口 LAST_OVER_TIME”语义，用于表达最近窗口内有效序列数量。
- 为旧策略实例和旧策略模板提供明确迁移规则。
- step 根据汇聚周期自动计算，固定拆成 30 个计算点。

## 4. 非目标

- 不引入完整 PromQL/MetricsQL 编辑器。
- 不要求用户手动配置 subquery resolution。
- 不改变阈值比较符、触发次数、恢复条件等策略生命周期逻辑。
- 不处理日志告警策略聚合逻辑。

## 5. 页面功能设计

### 5.1 字段说明

建议页面在现有“分组维度”下方新增“分组聚合方式”：

| 字段 | 文案建议 |
| --- | --- |
| 分组维度 | 监控策略根据所选分组维度分析指标，未指定的维度数据将统一聚合处理。 |
| 分组聚合方式 | 默认 AVG。用于决定同一分组下未入选维度的多条序列如何先合并。 |
| 汇聚周期 | 汇聚周期是观察窗口，step 根据汇聚周期自动计算为 30 个计算点。 |
| 汇聚方式 | 默认 AVG_OVER_TIME。用于决定观察窗口内如何得到最终阈值判断值。 |

### 5.2 分组聚合方式

| 配置值 | 语义 | 适用场景 |
| --- | --- | --- |
| `AVG` | 同一分组下多条序列先求平均 | 使用率、延迟、负载等整体水平 |
| `MAX` | 同一分组下多条序列先取最大 | 磁盘、队列、错误率等保留最危险子序列 |
| `MIN` | 同一分组下多条序列先取最小 | 可用率、健康分、剩余容量等低值风险 |
| `SUM` | 同一分组下多条序列先求和 | 数量、容量、增量、清单统计 |
| `COUNT` | 同一分组下多条序列先计数 | 接口数、磁盘数、进程数、有效序列数量 |

默认值：`AVG`。

### 5.3 汇聚方式

| 配置值 | 语义 | 适用场景 |
| --- | --- | --- |
| `AVG_OVER_TIME` | 窗口内求平均 | 周期内整体水平 |
| `MAX_OVER_TIME` | 窗口内取最大 | 周期内峰值风险 |
| `MIN_OVER_TIME` | 窗口内取最小 | 周期内最低健康值 |
| `SUM_OVER_TIME` | 窗口内累加 | 每个采样点是增量时统计周期总量 |
| `COUNT_OVER_TIME` | 窗口内统计有效数量 | 清单、接口数、磁盘数、有效序列/有效点 |
| `LAST_OVER_TIME` | 窗口内取最近有效值 | 状态、枚举、up/down、开关 |

默认值：`AVG_OVER_TIME`。

## 6. 底层查询语义

### 6.1 通用结构

数值趋势类统一为：

```promql
<window_method>((<group_method>(metric) by (group_by))[period:step])
```

其中：

- `group_method` 来自分组聚合方式：`avg/max/min/sum/count`
- `window_method` 来自汇聚方式：`avg_over_time/max_over_time/min_over_time/sum_over_time/count_over_time/last_over_time`
- `period` 来自汇聚周期
- `step = period / 30`

step 示例：

| 汇聚周期 | step | 说明 |
| --- | --- | --- |
| `5m` | `10s` | 300 秒 / 30 |
| `10m` | `20s` | 600 秒 / 30 |
| `30m` | `1m` | 1800 秒 / 30 |

### 6.2 常用示例

双 AVG：

```promql
avg_over_time((avg(metric) by (instance_id))[5m:10s])
```

双 MAX：

```promql
max_over_time((max(metric) by (instance_id))[5m:10s])
```

双 MIN：

```promql
min_over_time((min(metric) by (instance_id))[5m:10s])
```

双 SUM：

```promql
sum_over_time((sum(metric) by (service))[5m:10s])
```

COUNT：

```promql
last_over_time((count(metric) by (instance_id))[5m:10s])
```

LAST_OVER_TIME：

```promql
last_over_time((avg(metric) by (instance_id, interface))[5m:10s])
```

### 6.3 场景解释

磁盘使用率按 `instance_id` 分组、分组聚合方式 `AVG`、汇聚方式 `AVG_OVER_TIME`：

```promql
avg_over_time((avg(disk_used_percent) by (instance_id))[5m:10s])
```

表示：

1. 每个采样点先按 `instance_id` 聚合同一实例下的磁盘序列。
2. 汇聚周期内用 30 个计算点观察实例级序列。
3. 最后计算最近 5 分钟平均值作为阈值判断值。

接口状态按 `instance_id + interface` 分组、分组聚合方式 `AVG`、汇聚方式 `LAST_OVER_TIME`：

```promql
last_over_time((avg(interface_oper_status) by (instance_id, interface))[5m:10s])
```

如果一个设备有 10 个接口，且分组维度包含 `interface`，最近 5 分钟内 10 个接口都有数据，则最终会输出 10 条接口状态序列。

## 7. 指标模板推荐

策略模板或指标元数据应同时给出“分组聚合方式”和“汇聚方式”的推荐值。推荐不作为强制限制，只作为默认值和提示。

| 指标类型 | 推荐分组聚合方式 | 推荐汇聚方式 | 说明 |
| --- | --- | --- | --- |
| 使用率、延迟、负载 | `AVG` | `AVG_OVER_TIME` | 关注周期内整体水平 |
| 容量风险、队列堆积、错误率 | `MAX` | `MAX_OVER_TIME` | 关注周期内峰值风险 |
| 可用率、剩余容量、健康分 | `MIN` | `MIN_OVER_TIME` | 关注周期内最低点 |
| 每周期增量、周期内新增量 | `SUM` | `SUM_OVER_TIME` | 关注周期总量 |
| 序列存在性、接口/磁盘/进程数量 | `COUNT` | `LAST_OVER_TIME` | 关注最近窗口内有效序列数量 |
| 状态、枚举、up/down、开关 | `AVG` | `LAST_OVER_TIME` | 关注最近有效状态，分组维度要保留状态对象 |

## 8. 旧策略迁移规则

### 8.1 用户已创建策略

旧策略需要迁移为两个字段：`group_aggregation_method` 和 `window_aggregation_method`。

| 旧方法 | 新分组聚合方式 | 新汇聚方式 | 说明 |
| --- | --- | --- | --- |
| `AVG` | `AVG` | `AVG_OVER_TIME` | 原 AVG、AVG_OVER_TIME 统一迁移为双 AVG |
| `AVG_OVER_TIME` | `AVG` | `AVG_OVER_TIME` | 原 AVG、AVG_OVER_TIME 统一迁移为双 AVG |
| `MAX` | `MAX` | `MAX_OVER_TIME` | 原 MAX、MAX_OVER_TIME 统一迁移为双 MAX |
| `MAX_OVER_TIME` | `MAX` | `MAX_OVER_TIME` | 原 MAX、MAX_OVER_TIME 统一迁移为双 MAX |
| `MIN` | `MIN` | `MIN_OVER_TIME` | 原 MIN、MIN_OVER_TIME 统一迁移为双 MIN |
| `MIN_OVER_TIME` | `MIN` | `MIN_OVER_TIME` | 原 MIN、MIN_OVER_TIME 统一迁移为双 MIN |
| `SUM` | `SUM` | `SUM_OVER_TIME` | 原 SUM、SUM_OVER_TIME 统一迁移为双 SUM |
| `SUM_OVER_TIME` | `SUM` | `SUM_OVER_TIME` | 原 SUM、SUM_OVER_TIME 统一迁移为双 SUM |
| `COUNT` | `COUNT` | `LAST_OVER_TIME` | COUNT 迁移为分组 COUNT + 汇聚 LAST_OVER_TIME |
| `LAST_OVER_TIME` | `AVG` | `LAST_OVER_TIME` | LAST_OVER_TIME 迁移为分组 AVG + 汇聚 LAST_OVER_TIME |

### 8.2 监控策略模板

已有策略模板需要全部调整为新方案：

- 模板字段补齐分组聚合方式，默认按迁移规则生成。
- 模板字段补齐汇聚方式，旧 `algorithm` 按迁移规则转换。
- 新模板不再只写单一 `algorithm` 表达双层语义。
- 模板导入或初始化逻辑应做归一化保护，避免旧模板再次写入旧方法。

需要检查的模板来源：

- 文件模板：`server/apps/monitor/support-files/plugins/**/policy.json`
- 数据库模板：`PolicyTemplate.templates`

## 9. 前后端影响范围

### 前端

需要调整：

- 策略表单新增“分组聚合方式”。
- 汇聚方式列表调整为 `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME/COUNT_OVER_TIME/LAST_OVER_TIME`。
- 默认值：分组聚合方式 `AVG`，汇聚方式 `AVG_OVER_TIME`。
- 策略详情、编辑页、模板页展示两个字段。
- 指标模板推荐值需要展示两个维度。

Storybook 原型：

- `web/src/stories/monitor-strategy-aggregation-designer.stories.tsx`

### 后端

需要调整：

- 策略模型或配置结构新增分组聚合方式字段。
- 聚合方法合法值校验拆成两组。
- 策略扫描查询生成逻辑。
- 策略预览查询生成逻辑。
- `MonitorPolicy` 已有数据迁移。
- `PolicyTemplate.templates` 数据迁移或导入归一。
- 文件模板批量整改。

## 10. 验收标准

### 产品验收

- 页面存在“分组聚合方式”，可选 `AVG/MAX/MIN/SUM/COUNT`，默认 `AVG`。
- 页面存在“汇聚方式”，可选 `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME/COUNT_OVER_TIME/LAST_OVER_TIME`，默认 `AVG_OVER_TIME`。
- 用户能从文案理解：
  - 分组维度决定告警对象。
  - 分组聚合方式决定未入选维度如何先合并。
  - 汇聚周期是观察窗口。
  - 汇聚方式决定窗口内如何得到阈值判断值。
- step 根据汇聚周期自动计算为 30 个计算点。
- 指标模板可同时推荐分组聚合方式和汇聚方式。

### 查询语义验收

- `AVG + AVG_OVER_TIME` 生成先分组平均、再周期平均的查询。
- `MAX + MAX_OVER_TIME` 生成先分组最大、再周期最大值的查询。
- `MIN + MIN_OVER_TIME` 生成先分组最小、再周期最小值的查询。
- `SUM + SUM_OVER_TIME` 生成先分组求和、再周期累计的查询。
- `COUNT + LAST_OVER_TIME` 表达最近窗口内有效序列数量。
- `AVG + LAST_OVER_TIME` 表达窗口内最近有效状态。
- 所有窗口查询显式带 subquery step，且 step = period / 30。

### 迁移验收

- 已创建策略按迁移表补齐两个字段。
- 已有策略模板按迁移表补齐两个字段。
- 策略预览和后台扫描生成完全一致的查询结构。
- 新建策略不再只依赖旧单字段表达双层语义。

## 11. 实现确认点

1. `COUNT_OVER_TIME` 是否仍作为高级窗口方法保留给“窗口内采样点数量”场景；清单类默认不使用它，而使用 `COUNT + LAST_OVER_TIME`。
2. `LAST_OVER_TIME` 是否使用 `last_over_time((avg(metric) by (...))[period:step])`，还是为了兼容旧状态语义继续使用 `any(last_over_time(metric[period])) by (...)`。
3. 30 个计算点是否需要设置最小 step，例如低于采集间隔时按采集间隔兜底。
