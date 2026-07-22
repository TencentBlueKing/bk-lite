# Historical Superpowers change: 2026-06-16-monitor-search-plugin-scope

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## specs: 2026-06-16-monitor-search-plugin-scope-design.md

## Background

The monitor data query page currently identifies a selected metric by `Metric.name`. This breaks when one monitor object has multiple plugins that expose the same metric name. The Host object is the concrete failing case:

- Host plugin `cpu_usage_total` uses `100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", __$labels__}` and has data in the open environment.
- Host Remote plugin `cpu_usage_total` uses `host_cpu_usage_percent_gauge{instance_type="os", __$labels__}` and has no data for the same host instances.
- Windows WMI plugin also defines `cpu_usage_total` for Windows collection.

The query page can therefore lose plugin context and query the wrong metric expression. Memory appears normal only because the selected or resolved `mem_used_percent` path happens to match available data more often. The underlying issue is still the same: metric name is not a globally unique metric identity.

## Goal

Make the monitor search page plugin-aware so that selecting Host / Host Remote / Windows WMI yields the correct metric list, asset list, and PromQL query. New query state must use concrete metric identity (`Metric.id`) rather than only metric name.

## Non-Goals

- Do not redesign the monitor dashboard pages.
- Do not change metric ingestion, VictoriaMetrics storage, or plugin metric definitions.
- Do not remove existing plugins or merge same-name metrics.
- Do not require users to choose a plugin when the selected object has only one plugin.

## Recommended Approach

Use the query flow:

```text
Object -> Plugin -> Asset -> Metric -> Aggregation -> Conditions
```

After the user selects an object, the page loads that object's plugins. If there is exactly one plugin, the page auto-selects it. If there are multiple plugins, the page shows a Plugin selector below Object. The selected plugin scopes both the metric selector and the asset selector.

This provides a visible explanation for same-name metrics while keeping simple objects fast to query.

## Query State

Each query group should store:

- `object`: monitor object id.
- `plugin`: monitor plugin id, nullable only while not selected or while resolving legacy data.
- `instanceIds`: selected monitor instance ids.
- `metric`: concrete metric id for new state.
- `legacyMetricName`: optional metric name for loading old saved queries or old URLs.
- `aggregation`: aggregation function.
- `conditions`: extra label filters.

The search payload should keep maps keyed by object and plugin where helpful:

- `pluginsMap[objectId]`
- `metricsMap[objectId_pluginId]`
- `instancesMap[objectId_pluginId]` or equivalent filtered instance results
- `objectsMap[objectId]`

New saved queries and new URLs must write the concrete metric id. Existing saved queries and URLs that contain a metric name should still load through compatibility resolution.

## UI Behavior

When Object changes:

1. Clear plugin, asset, metric, and conditions.
2. Load plugins for the selected object with the existing monitor plugin API.
3. If one plugin exists, auto-select it.
4. If multiple plugins exist, render the Plugin selector.

When Plugin changes:

1. Clear asset, metric, and conditions.
2. Load metrics for `{ monitor_object_id, monitor_plugin_id }`.
3. Load or filter assets for that plugin.

When Metric changes:

1. Store `Metric.id`.
2. Load available dimensions from the selected metric.
3. Clear existing conditions.

The Metric selector should display readable names and may include plugin context in option metadata or tooltip, but the option value must be metric id.

## Asset Filtering

The asset selector should prefer plugin-scoped assets so users do not select an instance that cannot produce data for the selected plugin.

Preferred source order:

1. Use effective plugin information when an instance list endpoint already provides it or can cheaply derive it.
2. Otherwise filter by the selected plugin status query against VictoriaMetrics and intersect with monitor instances.
3. If plugin-scoped filtering is unavailable for a particular object, fall back to the object instance list but keep the selected plugin context for metric querying.

The Host case should only present Host plugin assets for Host plugin metrics and Host Remote assets for Host Remote metrics when that distinction is available.

## Data Flow

The frontend can reuse existing APIs:

- `getMonitorPlugin({ monitor_object_id })` to list plugins for an object.
- `getMonitorMetrics({ monitor_object_id, monitor_plugin_id })` to load plugin-scoped metrics.
- `getInstanceList(objectId, ...)` for object instances, with plugin filtering added where feasible.
- `/monitor/api/metrics_instance/query_range/` for final range queries.

Final query construction must resolve the selected metric by id, then use that metric's:

- `query`
- `unit`
- `instance_id_keys`
- `dimensions`

The query page must no longer resolve the selected metric with `metrics.find((item) => item.name === group.metric)` for new query state.

## Navigation and Compatibility

New navigation into search should pass real ids:

- `monitor_object=<object id>`
- `plugin_id=<plugin id>` when known
- `instance_id=<monitor instance id>`
- `metric_id=<Metric.id>`

Existing links may still pass `metric_id=cpu_usage_total`. The search page should interpret non-numeric `metric_id` as a legacy metric name:

1. If `plugin_id` exists, resolve the name within that plugin.
2. If no plugin id exists, prefer the plugin that is effective for the selected instance.
3. If still ambiguous, choose the first resolved metric and allow the user to change plugin explicitly.

Saved queries should follow the same compatibility rule. Once a legacy saved query is loaded and saved again, it should persist the concrete plugin and metric ids.

## Error Handling

- If an object has no plugins, keep the current object-level metric behavior where possible and show an empty plugin state only when metrics cannot be loaded.
- If the selected plugin has no assets, show an empty asset selector with normal empty-state text.
- If a legacy metric name resolves to multiple plugins and no instance context exists, choose the first plugin deterministically and keep the plugin selector visible.
- If a selected metric id no longer exists, clear metric selection and keep object/plugin selections.

## Testing

Frontend validation should cover:

- Host object with multiple plugins shows the Plugin selector.
- Single-plugin objects auto-select the plugin and do not require extra user action.
- Selecting Host plugin and CPU Usage queries `100 - cpu_usage_idle{cpu="cpu-total", instance_type="os", ...}`.
- Selecting Host Remote plugin and CPU Usage queries `host_cpu_usage_percent_gauge{instance_type="os", ...}`.
- Metric selector values are metric ids, not names.
- Legacy URL `metric_id=cpu_usage_total` still loads a usable metric.
- Saved query load/save preserves plugin id and metric id.

Backend or integration validation should cover:

- `getMonitorMetrics({ monitor_object_id, monitor_plugin_id })` returns only metrics for that plugin.
- Plugin-scoped asset filtering returns instances effective for the selected plugin when available.

## Acceptance Criteria

- On the monitor search page, Host object users can choose Host, Host Remote, or Windows WMI before selecting a metric.
- CPU Usage under the Host plugin returns data for the open environment host instances.
- Same-name metrics from different plugins no longer collide in query construction.
- Existing saved queries and old query links continue to load through compatibility resolution.
- The change is limited to monitor search and its navigation/query-state contracts unless a small shared helper is needed.
