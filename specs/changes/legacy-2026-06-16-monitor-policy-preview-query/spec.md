# Historical Superpowers change: 2026-06-16-monitor-policy-preview-query

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-16-monitor-policy-preview-query-design.md

## Background

The monitor policy create/edit page renders a metric preview while the user chooses a metric, aggregation method, period, dimensions, and source instances. That preview currently constructs PromQL in the frontend and then calls `/monitor/api/metrics_instance/query_range/`.

This diverges from the real policy scan path. The backend scanner builds policy queries through `MetricQueryService` and `policy_methods.METHOD`, including special handling for `_over_time` algorithms:

- Simple selectors can receive an explicit range selector, such as `metric{labels}[5m]`.
- Complex expressions, such as `100 - cpu_usage_idle{...}`, are not blindly rewritten with `[5m]`.
- `_over_time` results are grouped through an outer aggregation such as `any(... ) by (...)`.

The frontend preview does not follow these rules. For example, choosing `AVG_OVER_TIME` for Host CPU Usage can generate:

```promql
avg_over_time(100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", ...}[5m]) by (instance_id)
```

That expression is fragile because `by (...)` is not valid after a normal function call, and appending `[5m]` to a complex expression can produce invalid PromQL/MetricsQL.

## Goal

Make monitor policy previews use the same query semantics as backend policy scanning, so strategy creation avoids invalid preview queries for `_over_time` algorithms and complex metric expressions.

The preview should be generated and executed by the backend from a policy draft payload. The frontend should no longer construct policy-preview PromQL or call `metrics_instance/query_range` directly for this specific preview workflow.

## Non-Goals

- Do not change how policies are saved.
- Do not change scheduled policy scanning semantics.
- Do not redesign dashboard, monitor view, or search page range queries.
- Do not introduce a full PromQL parser.
- Do not mutate or persist a draft policy during preview.

## Recommended Approach

Add a backend policy preview endpoint:

```text
POST /monitor/api/monitor_policy/preview/
```

The frontend sends the query-related fields from the policy draft plus the currently selected preview instance. The backend validates the payload, builds a policy-like object without saving it, reuses the backend policy query builder, executes the preview query, applies unit conversion, and returns chart-ready VictoriaMetrics data.

This makes the backend the only source of truth for policy query construction.

## API Contract

Request body:

```json
{
  "monitor_object": 1,
  "collect_type": "1",
  "query_condition": {
    "type": "metric",
    "metric_id": 123,
    "filter": []
  },
  "source": {
    "type": "instance",
    "values": ["host-1"]
  },
  "period": {
    "type": "min",
    "value": 5
  },
  "algorithm": "avg_over_time",
  "group_by": ["instance_id"],
  "metric_unit": "percent",
  "calculation_unit": "percent",
  "preview": {
    "instance_id": "host-1",
    "instance_id_values": ["MjNlY2Q1YzdhZTc3"],
    "duration_points": 30
  }
}
```

Response body:

```json
{
  "query": "any(avg_over_time(100 - cpu_usage_idle{cpu=\"cpu-total\", instance_type=\"os\", instance_id=~\"MjNlY2Q1YzdhZTc3\"})) by (instance_id)",
  "data": {
    "status": "success",
    "data": {
      "result": []
    },
    "unit": "percent"
  },
  "warnings": []
}
```

The `query` field is returned for diagnostics and support. The frontend should render `data`, not rebuild or reinterpret `query`.

## Backend Design

Create `server/apps/monitor/services/policy_preview.py`.

The service should expose a small orchestration API, for example:

```text
PolicyPreviewService.preview(payload) -> dict
```

Responsibilities:

- Validate required preview fields.
- Load the referenced `Metric`.
- Build the metric label filter from both `query_condition.filter` and the selected preview instance.
- Construct a lightweight policy-like object with the fields needed by `MetricQueryService`.
- Reuse `MetricQueryService.format_pmq()` and `policy_methods.METHOD` for aggregation query construction.
- Execute the preview query against VictoriaMetrics.
- Apply the same unit conversion behavior used by policy scanning when `metric_unit` and `calculation_unit` differ.
- Return the actual query string, response data, and warnings.

The implementation should avoid saving a `MonitorPolicy`, creating periodic tasks, refreshing baselines, or closing alerts.

Preview instance filtering should use the metric's `instance_id_keys` and `preview.instance_id_values` to add escaped regex label matchers, matching the existing `mergeViewQueryKeyValues` behavior. This preserves the current frontend behavior where the preview chart is scoped to one selected asset while still allowing multi-part instance identities.

The current `policy_methods.METHOD` functions execute queries directly and do not expose the final query string. Implementation should extract the query-string formatting into small shared helpers, then keep the existing method behavior as wrappers around those helpers. This lets policy preview return `query` without duplicating aggregation formatting or relying on test-only interception.

## Query Construction

Policy preview must follow the backend scanner's aggregation rules.

Normal aggregation:

```promql
avg(<metric_query>) by (<group_by>)
```

`_over_time` aggregation:

```promql
any(avg_over_time(<metric_query_or_selector_range>)) by (<group_by>)
```

Simple selectors may receive an explicit range selector:

```promql
any(avg_over_time(cpu_usage_idle{...}[5m])) by (instance_id)
```

Complex expressions must not be blindly suffixed with a range selector:

```promql
any(avg_over_time(100 - cpu_usage_idle{...})) by (instance_id)
```

This should use the existing backend simple-selector check in `policy_methods.py` rather than introducing a separate frontend rule.

## View Layer

Add an action to `MonitorPolicyViewSet`:

```text
@action(methods=["post"], detail=False, url_path="preview")
```

The view should:

- Accept draft policy payloads.
- Delegate validation and query execution to `PolicyPreviewService`.
- Return `WebUtils.response_success(result)` on success.
- Raise `BaseAppException` with a clear message for invalid payloads or failed query construction.

## Frontend Design

Update `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`.

The component should continue to manage UI state:

- Preview instance loading and selection.
- Request aborting.
- Loading state.
- Chart rendering through existing `renderChart` and `LineChart`.
- Empty state display.

The component should stop doing policy-query construction:

- Remove policy preview-specific `wrapQueryWithAlgorithm`.
- Stop appending range selectors for `_over_time`.
- Stop calling `/monitor/api/metrics_instance/query_range/` for policy preview.

Instead, it calls:

```text
/monitor/api/monitor_policy/preview/
```

using the selected metric id, filters, period, algorithm, group dimensions, selected preview instance, and units.

## Error Handling

Backend errors should be explicit:

- Missing `metric_id`, `period`, `algorithm`, `group_by`, or preview instance data should return a validation error.
- Unknown metric or unsupported algorithm should return a validation error.
- VictoriaMetrics syntax/query errors should return a readable error message.

Frontend preview states:

- Loading: keep current spinner behavior.
- Success with results: render chart.
- Success with no results: render empty state.
- Error: show a concise preview error message in the preview area and do not leave stale chart data visible.

Warnings can be returned for non-fatal situations such as no result data or skipped unit conversion. The first implementation may return an empty `warnings` list unless a non-fatal condition is already easy to detect.

## Testing

Backend tests should cover:

- `avg_over_time` with Host CPU Usage (`100 - cpu_usage_idle{...}`) produces a valid backend-style query without appending `[5m]` to the complex expression.
- `avg_over_time` with a simple selector appends `[period]`.
- Normal `avg` with a complex expression produces `avg(<expr>) by (...)`.
- Missing preview instance values fail with a clear validation error.
- Unsupported algorithm fails with a clear validation error.
- VictoriaMetrics errors are surfaced as preview errors.
- Unit conversion is applied consistently with policy scanning when source and target units differ.

Frontend validation should cover:

- `MetricPreview` calls `monitor_policy/preview` instead of `metrics_instance/query_range`.
- `_over_time` PromQL is not constructed in the frontend.
- Preview errors clear chart data and display an error state.
- Existing loading and abort behavior still works.

## Acceptance Criteria

- Creating or editing a monitor policy no longer sends frontend-generated `_over_time` PromQL to `metrics_instance/query_range`.
- Host CPU Usage with `AVG_OVER_TIME` previews through backend-generated query semantics and does not generate `avg_over_time(100 - metric[5m]) by (...)`.
- Backend policy preview and scheduled policy scanning share the same aggregation construction rules.
- Preview failures are visible to the user as meaningful errors instead of silent empty charts.
- The change is limited to policy preview behavior and does not change saved policy payloads or scheduled scanner behavior.
