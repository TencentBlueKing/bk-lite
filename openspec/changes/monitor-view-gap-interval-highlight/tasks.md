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
