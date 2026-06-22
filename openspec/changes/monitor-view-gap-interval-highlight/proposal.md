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
