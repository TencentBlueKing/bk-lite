# Monitor View Gap Interval Highlight

Status: in-progress

## Migration Context

- Legacy source: `openspec/changes/monitor-view-gap-interval-highlight/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

监控指标视图在长时间范围下会按较大的 step 降采样展示数据。即使底层采集间隔较短，例如 1 分钟采集、30 天范围按小时级展示，某个展示点区间内发生 5 分钟未上报也不会被用户感知，容易误判为指标连续正常。

需要在降采样视图中提示“该展示区间内部存在采集中断”，引导用户拖选或缩小时间范围进一步排查断点。

## What Changes

- 在指标范围查询中支持可选断点检测，基于采集间隔识别查询窗口内的未上报区间。
- 查询结果返回断点区间元数据，包含断点开始时间、结束时间、持续时间和关联序列信息。
- 监控折线图在对应 x 轴区间渲染明显的变色背景，并在 hover 时提示存在采集中断。
- 保留现有指标线连接行为，断点提示作为辅助视觉层，不改变指标数值曲线和阈值线语义。
- 覆盖通用监控视图和对象 dashboard 中使用的折线图组件，使 Recharts 与 ECharts 展示一致。

## Capabilities

### New Capabilities

- `monitor-view-gap-interval-highlight`: Defines how monitor metric range queries expose collection gap intervals and how monitor views highlight those intervals on time-series charts.

### Modified Capabilities

None.

## Impact

- **Server monitor metrics API**: `server/apps/monitor/views/metrics_instance.py`, `server/apps/monitor/services/metrics.py`, and `server/apps/monitor/utils/victoriametrics_api.py`.
- **Web monitor query builders**: metric view/search/dashboard request parameter construction under `web/src/app/monitor/`.
- **Web monitor chart data model**: `ChartData`, `renderChart`, and shared chart utilities.
- **Web chart rendering**: Recharts `LineChart` and ECharts dashboard line chart components.
- **Verification**: targeted backend tests for gap detection and response shape, plus frontend tests for chart metadata transformation and interval rendering inputs.

## Implementation Decisions

## Context

监控指标视图通过 `/monitor/api/metrics_instance/query_range/` 查询 VictoriaMetrics range 数据。前端会根据时间范围和采集间隔计算展示 step，当前目标点数为 100；后端再按展示 step 补齐缺失点。通用监控视图使用 Recharts `LineChart`，对象 dashboard 使用 ECharts line chart，两者都开启了 `connectNulls`，因此缺失值不会自然形成明显视觉断裂。

这个现状能处理“展示 step 本身没有数据”的场景，但不能暴露“展示 step 内部出现短时间未上报”的场景。例如 1 分钟采集、小时级展示时，中间 5 分钟未上报仍可能在小时级曲线上看起来连续。

## Goals / Non-Goals

**Goals:**

- 在长时间范围和较大展示 step 下提示采集中断区间。
- 基于采集间隔识别短断点，而不是只基于展示点间距推断。
- 将断点作为查询结果元数据返回，使 Recharts 和 ECharts 可以共享同一数据契约。
- 保持现有折线、阈值、tooltip、拖选缩放能力不被破坏。
- 让断点提示引导用户缩小时间范围查看，不在粗粒度视图中展开原始明细。

**Non-Goals:**

- 不改变指标表达式的数值计算语义。
- 不强制所有 range 查询都执行细粒度断点检测；该能力应由监控视图按需启用。
- 不新增外部存储或持久化断点记录。
- 不在本次变更中重做监控 dashboard 图表体系。

## Decisions

### 1. 后端生成断点元数据，前端只渲染

`query_range` 支持可选参数启用断点检测，例如 `detect_gaps=true` 和 `collection_interval=<seconds>`。后端在返回 VictoriaMetrics 原有 `data.result` 的同时，附加 `data.gaps` 或等价元数据结构，字段至少包括 `start`、`end`、`duration`、`series`。

**Rationale**: 降采样后的前端数据无法可靠知道展示点内部是否有 5 分钟未上报。断点检测必须在拥有采集间隔和更细粒度查询能力的一侧完成。

**Alternative considered**: 前端仅根据相邻展示点缺失值或时间差推断断点。这个方案实现简单，但只能发现展示 step 级别的空洞，无法满足用户示例中的“小时展示内 5 分钟断采”。

### 2. 断点检测以采集间隔为基准

断点阈值应使用采集间隔计算，默认命中条件为连续无数据时间达到 `max(2 * collection_interval, 60s)` 或更高的产品配置阈值。若请求未提供有效采集间隔，后端不执行细粒度断点检测，只保留现有缺失点补齐行为。

**Rationale**: 不同监控对象采集间隔不同，固定 5 分钟阈值会误判高频或低频采集。采集间隔是实例数据模型中已有字段，也已被前端用于最小查询 step。

**Alternative considered**: 使用展示 step 的固定比例作为阈值。这个方案对粗粒度视图友好，但与实际采集周期脱节，可能漏掉 1 分钟采集中的明显断点。

### 3. 断点检测查询与展示查询分离

展示查询继续使用现有 `step`。启用断点检测时，后端额外以采集间隔或受限的检测 step 获取可用性信号，并把检测结果压缩为区间元数据。实现时必须限制最大检测点数或最大时间范围，避免 30 天窗口按 1 分钟检测造成不可控开销。

**Rationale**: 用展示 step 查询无法获得短断点，用原始采集 step 替代展示 step 又会让图表和网络负载膨胀。分离查询能保留粗粒度展示，同时获得断点信号。

**Alternative considered**: 前端发起第二个细粒度查询。这样会把复杂度分散到多个前端入口，并且每个图表组件都要理解 PromQL、采集间隔和检测限流。

### 4. 图表以区间背景表达断点

Recharts 使用 `ReferenceArea`，ECharts 使用 `markArea` 渲染断点区间。断点层应位于数据线下方、阈值层之下或不遮挡阈值标签，颜色使用告警提示但低透明度。tooltip 文案应说明“该区间存在采集中断，可缩小时间范围查看”。

**Rationale**: 用户目标是被引导缩小时间范围，而不是在粗视图中读取每个缺失点。区间背景比断线更适合表达“两个展示点之间内部曾断采”。

**Alternative considered**: 直接关闭 `connectNulls`。这会让展示 step 空洞更明显，但仍不能表示 step 内部断点，并可能破坏已有多序列 tooltip 对齐和视觉连续性。

### 5. 断点元数据挂在共享 chart 数据契约上

`renderChart` 和相关类型应保留查询响应中的断点元数据，并将其传给通用 `LineChart`、搜索页、概览页和对象 dashboard 的图表组件。不同图表库可以有各自渲染实现，但不应各自计算断点。

**Rationale**: 当前监控模块已有多处 range 查询入口。共享契约可以减少行为分叉，并便于测试数据转换。

**Alternative considered**: 仅在通用指标视图中实现。这样能更快满足部分页面，但对象 dashboard 仍会隐藏同类断点，用户体验不一致。

## Risks / Trade-offs

- **Risk: 细粒度断点检测增加 VictoriaMetrics 查询压力** -> 对检测功能设置启用条件、最大检测点数、最大时间范围和超限降级，必要时只返回展示 step 级别断点。
- **Risk: 复杂 PromQL 表达式的“无数据”不等同于原始采集未上报** -> 明确本能力检测最终查询序列的可用性；后续如需检测原始指标采集状态，再增加 metric 元数据驱动的专用探针。
- **Risk: 多序列断点区间重叠导致图表过于嘈杂** -> 合并相邻或重叠区间，并在 tooltip/元数据中保留受影响序列数量。
- **Risk: 断点高亮遮挡阈值阴影或事件条** -> 将断点层设计为低透明背景，保持阈值线和事件条可见。
- **Risk: 未提供采集间隔的旧入口行为不一致** -> 未提供有效采集间隔时不启用细粒度检测，保持现有响应兼容。

## Migration Plan

- 后端先以 additive response 字段发布，未传 `detect_gaps` 的请求响应保持兼容。
- 前端逐步在监控视图、搜索页、概览页和 dashboard 查询入口传入采集间隔并消费断点元数据。
- 回滚时前端忽略断点元数据即可恢复旧视觉；后端新增字段不需要数据迁移。

## Open Questions

- 产品是否需要暴露断点阈值配置，还是固定使用 `max(2 * collection_interval, 60s)`。
- 超过最大检测点数时，是完全不展示断点，还是退化为展示 step 级别缺失区间。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-22
```

## Capability Deltas

### monitor-view-gap-interval-highlight

## ADDED Requirements

### Requirement: Metric range queries expose collection gap intervals
When a monitor metric range query is requested with gap detection enabled and a valid collection interval, the system SHALL return collection gap interval metadata alongside the existing metric range data.

#### Scenario: Gap interval is detected inside a coarse display step
- **WHEN** a metric is collected every 60 seconds and the displayed query step is 3600 seconds
- **AND** the underlying metric series has no reported samples for a continuous 300 second period between two displayed points
- **THEN** the range query response SHALL include a gap interval covering the missing sample period
- **AND** the existing metric `data.result` response shape SHALL remain available for chart rendering

#### Scenario: Gap detection is not requested
- **WHEN** a metric range query does not enable gap detection
- **THEN** the response SHALL preserve the existing range query behavior
- **AND** the system SHALL NOT require callers to handle gap metadata

#### Scenario: Collection interval is invalid or absent
- **WHEN** a metric range query enables gap detection without a positive collection interval
- **THEN** the system SHALL skip fine-grained gap detection
- **AND** the response SHALL remain compatible with existing range query consumers

### Requirement: Gap detection uses collection interval tolerance
The system SHALL determine collection gaps using the metric instance collection interval as the primary tolerance baseline.

#### Scenario: Missing samples exceed tolerance
- **WHEN** consecutive expected collection timestamps are missing for at least the configured gap tolerance
- **THEN** the system SHALL emit a gap interval with start time, end time, duration, and affected series metadata

#### Scenario: Missing samples are below tolerance
- **WHEN** missing samples are shorter than the configured gap tolerance
- **THEN** the system SHALL NOT emit a visible gap interval for that transient absence

#### Scenario: Multiple affected series share overlapping gaps
- **WHEN** multiple result series have overlapping or adjacent gap intervals
- **THEN** the system SHALL merge those intervals for chart display
- **AND** the merged interval metadata SHALL retain enough information to indicate affected series count or identity

### Requirement: Gap detection is bounded for long time ranges
The system SHALL bound fine-grained gap detection work so long-range monitor views do not create unbounded VictoriaMetrics query load.

#### Scenario: Detection work is within limits
- **WHEN** the requested time range and collection interval produce an allowed number of detection points
- **THEN** the system SHALL perform fine-grained gap detection
- **AND** the system SHALL return detected gap intervals in the response

#### Scenario: Detection work exceeds limits
- **WHEN** the requested time range and collection interval exceed the configured detection limit
- **THEN** the system SHALL degrade gracefully without failing the metric chart request
- **AND** the response SHALL indicate that fine-grained gap detection was limited or skipped

### Requirement: Monitor charts highlight gap intervals
Monitor time-series charts SHALL render returned collection gap intervals as visually distinct x-axis background ranges without changing the metric value line semantics.

#### Scenario: Gap metadata exists for a visible chart range
- **WHEN** chart data includes one or more gap intervals within the current x-axis domain
- **THEN** the chart SHALL render each gap interval as a noticeable low-opacity highlighted region between its start and end timestamps
- **AND** the metric lines, threshold lines, and event indicators SHALL remain visible

#### Scenario: User hovers over a highlighted interval
- **WHEN** the user hovers over or focuses a highlighted gap interval
- **THEN** the chart SHALL explain that the interval contains missing collection data
- **AND** the chart SHALL guide the user to narrow the time range to inspect the gap in detail

#### Scenario: No gap metadata exists
- **WHEN** chart data has no returned gap intervals
- **THEN** the chart SHALL render with the existing visual behavior

### Requirement: Gap highlighting is consistent across monitor chart implementations
The system SHALL apply the same gap interval data contract to the Recharts-based monitor line chart and the ECharts-based dashboard line chart.

#### Scenario: Common monitor metric view renders gaps
- **WHEN** a common monitor metric view receives gap interval metadata
- **THEN** the Recharts line chart SHALL render the highlighted intervals using the shared gap data contract

#### Scenario: Object dashboard renders gaps
- **WHEN** an object dashboard line chart receives gap interval metadata
- **THEN** the ECharts line chart SHALL render equivalent highlighted intervals using the shared gap data contract

#### Scenario: Chart library-specific rendering differs internally
- **WHEN** Recharts and ECharts require different rendering primitives for interval backgrounds
- **THEN** both implementations SHALL produce equivalent user-visible gap highlighting from the same gap metadata

## Work Checklist

## 1. Backend Gap Detection Contract

- [x] 1.1 Extend `MetricsInstanceViewSet.get_metrics_range` to accept optional gap detection parameters while preserving existing callers.
- [x] 1.2 Add validation and normalization for `detect_gaps`, `collection_interval`, and any detection limit settings.
- [x] 1.3 Extend `MetricsService.get_metrics_range` to return gap metadata only when detection is enabled and inputs are valid.
- [x] 1.4 Define the additive response shape for gap metadata, including interval start, end, duration, affected series, and detection status.

## 2. Backend Gap Detection Algorithm

- [x] 2.1 Implement a helper that detects missing sample intervals from timestamped VictoriaMetrics series using collection interval tolerance.
- [x] 2.2 Add interval merging for overlapping or adjacent gaps across multiple result series.
- [x] 2.3 Add bounded detection behavior for long ranges, including graceful skip or limited-status metadata when detection would exceed limits.
- [x] 2.4 Add unit tests for detected gaps, no-gap cases, invalid collection interval, overlap merging, and exceeded detection limits.

## 3. Frontend Query and Data Model

- [x] 3.1 Add gap metadata types to monitor chart data contracts without breaking existing `ChartData` consumers.
- [x] 3.2 Preserve gap metadata through `renderChart` or companion transform utilities.
- [x] 3.3 Pass gap detection parameters from common metric views using the instance collection interval.
- [x] 3.4 Pass gap detection parameters from monitor search and overview/dashboard query builders where collection interval is available.
- [x] 3.5 Add frontend unit coverage for transforming and preserving returned gap metadata.

## 4. Recharts Monitor Line Chart

- [x] 4.1 Extend the common Recharts `LineChart` props to accept gap intervals.
- [x] 4.2 Render gap intervals as low-opacity x-axis `ReferenceArea` backgrounds without hiding metric lines, thresholds, or event bars.
- [ ] 4.3 Add hover/focus copy explaining that the interval contains missing collection data and suggesting narrowing the time range.
- [ ] 4.4 Verify drag selection and existing threshold tooltip behavior still work with gap highlights present.

## 5. ECharts Dashboard Line Chart

- [x] 5.1 Extend the shared ECharts line chart props to accept the same gap interval contract.
- [x] 5.2 Render gap intervals using ECharts markArea or equivalent background ranges.
- [x] 5.3 Keep dashboard tooltip formatting, binary unit scaling, and range selection behavior intact.
- [ ] 5.4 Add or update chart option tests to prove equivalent gap rendering inputs for ECharts.

## 6. Integration and Verification

- [x] 6.1 Add targeted backend API tests for `query_range` response compatibility with and without gap detection.
- [ ] 6.2 Add targeted frontend tests or stories for no-gap, single-gap, overlapping-gap, and detection-limited states.
- [x] 6.3 Run server monitor tests relevant to `metrics_instance` and `MetricsService`.
- [ ] 6.4 Run web monitor validation for touched files: `cd web && pnpm lint && pnpm type-check`.
- [ ] 6.5 Manually verify a 1-minute collection metric over a coarse time range highlights an internal 5-minute missing-report interval and supports narrowing the time range.
