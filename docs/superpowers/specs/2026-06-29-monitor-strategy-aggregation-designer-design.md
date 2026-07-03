# Monitor Strategy Aggregation Designer Design

## Background

Monitor threshold policies currently expose aggregation methods that mix business intent with PromQL function names. Users can choose methods such as `AVG`, `AVG_OVER_TIME`, and `LAST_OVER_TIME`, while also configuring group dimensions and an aggregation period. This creates an unclear mental model:

- `AVG/MAX/MIN/SUM` can aggregate by dimensions, but the aggregation period may not affect the final threshold value.
- `*_OVER_TIME` methods use a time window, but they do not consistently aggregate by the selected group dimensions first.
- `COUNT` currently behaves like a current-point series count rather than a count of series that were valid during the configured period.
- `LAST_OVER_TIME` is useful for state metrics, but its special behavior is not explained separately from numeric aggregation methods.

The desired product model is: determine the alert object first, observe a time window, then calculate one threshold value for each alert object.

## Goals

- Redesign the policy aggregation experience around user intent instead of raw PromQL function names.
- Keep the configuration understandable for numeric metrics, count/existence metrics, and state metrics.
- Produce a Storybook prototype that lets product and engineering review the interaction before changing the real strategy form.
- Align the prototype with the eventual backend semantics for policy preview and scheduled scanning.

## Non-Goals

- Do not implement backend query changes in this prototype step.
- Do not migrate existing policies or policy templates in this prototype step.
- Do not replace the full monitor strategy create/edit page.
- Do not expose subquery resolution as a required user-facing field.

## Product Model

The aggregation section should explain three concepts:

```text
Alert object = group dimensions
Observation window = aggregation period
Calculation = aggregation method
```

User-facing copy:

- Group dimensions: decide which objects are judged and alerted independently.
- Aggregation period: every scan looks back over this time window.
- Aggregation method: calculate the value used for threshold comparison within the window.

The method list should use business labels while retaining compact technical tags:

- Average `AVG`
- Maximum `MAX`
- Minimum `MIN`
- Accumulated `SUM`
- Valid count `COUNT`
- Latest value `LAST`

`LAST` maps to the existing `last_over_time` method. The UI should avoid showing `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME` as separate choices.

## Method Semantics

### Numeric Trend Methods

`AVG` answers: what is the typical level during the window?

Expected backend semantics:

```promql
avg_over_time((avg(metric) by (group_by))[period:resolution])
```

Recommended for usage, latency, load, and other metrics where short spikes should be smoothed.

`MAX` answers: what is the worst high value during the window?

Expected backend semantics:

```promql
max_over_time((max(metric) by (group_by))[period:resolution])
```

Recommended for disk usage, connection count, queue depth, error rate, and other metrics where a peak matters.

`MIN` answers: what is the worst low value during the window?

Expected backend semantics:

```promql
min_over_time((min(metric) by (group_by))[period:resolution])
```

Recommended for remaining capacity, availability, health score, replica count, and similar low-bound metrics.

`SUM` answers: what is the accumulated amount during the window?

Expected backend semantics:

```promql
sum_over_time((sum(metric) by (group_by))[period:resolution])
```

Recommended for metrics that already represent per-sample increments or per-period quantities, such as errors added per minute or jobs processed per interval. The UI should caution that `SUM` is usually not appropriate for gauge metrics such as CPU usage or memory usage because the result depends on sampling frequency.

### Count Method

`COUNT` answers: how many valid series existed during the window?

Expected backend semantics:

```promql
count(last_over_time(metric[period])) by (group_by)
```

Recommended for interface count, disk count, process count, and other presence/existence checks. This avoids counting only the exact current timestamp.

### State Method

`LAST` answers: what was the latest valid value during the window?

Expected backend semantics:

```promql
any(last_over_time(metric[period])) by (group_by)
```

Recommended for status, enum, switch, port, and up/down metrics. The UI should warn that when multiple raw series exist inside one group, users should include enough dimensions to identify the state object. For example, interface status should usually group by `instance_id` and `interface`.

## Subquery Resolution

The backend design should not emit bare subqueries such as:

```promql
[5m:]
```

When the outer `query_range` step equals the policy period, a bare subquery can effectively sample only one point or too few points. The eventual query builder should use an explicit resolution:

```promql
[5m:1m]
```

or a resolution derived from collection interval and policy period. The prototype should display the resolution as `auto` in normal copy and show `1m` in example advanced query text.

## Storybook Prototype

Create a dedicated Storybook prototype:

```text
web/src/stories/monitor-strategy-aggregation-designer.stories.tsx
```

The prototype should be isolated from production strategy code and use local mock data.

### Layout

The prototype should use a quiet operations-product layout:

- Left column: configuration controls.
- Right column: calculation explanation and generated query.
- Bottom area: scenario preview and method recommendations.

Use existing project dependencies, especially React and Ant Design. Keep the interface dense, scannable, and form-oriented rather than marketing-like.

### Configuration Controls

Controls:

- Metric selector with example metrics:
  - Disk usage, numeric gauge.
  - Interface status, state metric.
  - Request increment, delta metric.
  - Interface inventory, count metric.
- Group dimension selector with chips such as `instance_id`, `interface`, and `disk`.
- Aggregation period selector with values such as 5, 10, and 30 minutes.
- Aggregation method selector with the six product methods.

The method selector should show label, tag, short explanation, and recommended metric type.

### Explanation Panel

The explanation panel should update from the selected config:

```text
1. Group by instance_id to produce one alert series per instance.
2. Look back over the latest 5 minutes.
3. Calculate the average value in that window for threshold comparison.
```

Advanced query text should be visible but secondary. It helps engineering/support review the generated semantics without making PromQL the primary user experience.

### Scenario Preview

The preview should explain concrete outcomes:

- Disk usage with `AVG`: one instance-level value after grouping disks and averaging over the window.
- Interface status with `LAST`: ten interface-level results when ten interfaces have data, including down/up examples.
- Request increment with `SUM`: accumulated request count across the window.
- Inventory with `COUNT`: valid series count across the window.

### Method Recommendation

Show contextual recommendations based on metric type:

- Disk usage: recommend `MAX`, then `AVG`.
- Interface status: recommend `LAST`.
- Request increment: recommend `SUM`.
- Interface inventory: recommend `COUNT`.

Recommendations are helper text, not hard validation.

## Stories

The Storybook file should export at least these states:

- `DefaultNumericMetric`: disk usage with `MAX` or `AVG`.
- `InterfaceStatusLast`: interface status grouped by `instance_id` and `interface` with `LAST`.
- `DeltaCounterSum`: request increment with `SUM`.
- `MethodComparison`: compare method explanations for the same numeric metric.

## Acceptance Criteria

- The prototype presents exactly six user-facing methods: `AVG`, `MAX`, `MIN`, `SUM`, `COUNT`, and `LAST`.
- The prototype does not present `AVG_OVER_TIME`, `MAX_OVER_TIME`, `MIN_OVER_TIME`, or `SUM_OVER_TIME` as user-facing options.
- Users can understand that group dimensions determine alert objects.
- Users can understand that aggregation period is an observation window, not the scan frequency.
- `LAST` is clearly positioned as a status/enum method.
- `SUM` includes a caution for gauge metrics.
- Advanced query examples show explicit subquery resolution for numeric trend methods.
- The prototype is self-contained and does not call backend APIs.

## Future Backend Alignment

After the prototype is approved, the implementation plan should cover:

- Shared backend query generation for preview and scheduled scanning.
- Runtime normalization of old methods:
  - `avg_over_time -> avg`
  - `max_over_time -> max`
  - `min_over_time -> min`
  - `sum_over_time -> sum`
  - `last_over_time -> last_over_time`
- Data migration for existing `MonitorPolicy.algorithm` values.
- Migration or re-import normalization for `PolicyTemplate.templates`.
- Frontend method list update in the real monitor strategy form.
- Tests for query generation, method normalization, template migration, and Storybook prototype expectations.
