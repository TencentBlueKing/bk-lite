# Monitor Effective Plugin View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show only the plugins that are effective for a monitor instance in monitor view tabs.

**Architecture:** Add a backend service that merges configured plugin facts from `CollectConfig` with recent reporting facts from each plugin's `status_query`. Expose the merged list through a monitor-instance action, then have both monitor view entry points request instance-effective plugins instead of object-wide plugins.

**Tech Stack:** Django 4.2, Django REST Framework viewsets, pytest, Next.js 16, React 19, TypeScript.

---

## File Structure

- Create `server/apps/monitor/services/effective_plugins.py`
  - Owns instance effective plugin resolution and output shaping.
- Modify `server/apps/monitor/views/monitor_instance.py`
  - Adds `effective_plugins` action and reuses existing permission helpers.
- Modify `server/apps/monitor/tests/test_monitor_instance_view.py`
  - Adds RED/GREEN coverage for active configured plugins, passive reported plugins, dedupe, and the API action.
- Modify `web/src/app/monitor/api/index.ts`
  - Adds `getEffectivePlugins`.
- Modify `web/src/app/monitor/(pages)/view/viewList.tsx`
  - Loads effective plugins when opening the detail drawer.
- Modify `web/src/app/monitor/components/metric-views/index.tsx`
  - Loads effective plugins for the standalone detail page.

## Task 1: Backend Service and API

**Files:**
- Create: `server/apps/monitor/services/effective_plugins.py`
- Modify: `server/apps/monitor/views/monitor_instance.py`
- Test: `server/apps/monitor/tests/test_monitor_instance_view.py`

- [x] **Step 1: Write failing service tests**

Add tests that create a monitor object, instance, configured plugin, reported-only plugin, and unused plugin. Monkeypatch VM query calls so one plugin reports the target instance.

- [x] **Step 2: Run service tests to verify RED**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_instance_view.py -k effective_plugins -q`

Expected: fails because `apps.monitor.services.effective_plugins` or `MonitorEffectivePluginService` does not exist.

- [x] **Step 3: Implement minimal service**

Implement a service that:

- Validates the instance belongs to the requested monitor object and is not deleted.
- Builds `configured_plugin_ids` from `CollectConfig`.
- Builds `reported_plugin_ids` by running plugin `status_query` and matching VM result labels against `MonitorObject.instance_id_keys`.
- Returns configured/reported union only, with `status` and `collect_mode`.

- [x] **Step 4: Run service tests to verify GREEN**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_instance_view.py -k effective_plugins -q`

Expected: all selected tests pass.

- [x] **Step 5: Write failing API action test**

Add a test that monkeypatches `_build_actor_context`, `_ensure_operate_instances`, and the service, then calls `MonitorInstanceViewSet().effective_plugins(...)`.

- [x] **Step 6: Run API action test to verify RED**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_instance_view.py -k effective_plugins_action -q`

Expected: fails because the action method does not exist.

- [x] **Step 7: Implement minimal API action**

Add `effective_plugins` action under `MonitorInstanceViewSet`:

```python
@action(methods=["get"], detail=False, url_path="(?P<monitor_object_id>[^/.]+)/effective_plugins")
def effective_plugins(self, request, monitor_object_id):
    instance_id = request.GET.get("instance_id")
    if not instance_id:
        raise BaseAppException("instance_id is required")
    actor_context = _build_actor_context(request)
    _ensure_operate_instances(request, [instance_id], actor_context)
    data = MonitorEffectivePluginService.get_effective_plugins(int(monitor_object_id), instance_id, request.user.locale)
    return WebUtils.response_success(data)
```

- [x] **Step 8: Run backend selected tests**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_instance_view.py -q`

Expected: monitor instance view tests pass.

## Task 2: Frontend API and Call Sites

**Files:**
- Modify: `web/src/app/monitor/api/index.ts`
- Modify: `web/src/app/monitor/(pages)/view/viewList.tsx`
- Modify: `web/src/app/monitor/components/metric-views/index.tsx`

- [x] **Step 1: Add frontend API method**

Add `getEffectivePlugins(monitorObjectId, params, config)` that calls:

```text
/monitor/api/monitor_instance/${monitorObjectId}/effective_plugins/
```

- [x] **Step 2: Use effective plugins in the list detail drawer**

In `ViewList`, fetch effective plugins inside `openViewModal(row)` before showing the drawer, map them to `{ label, value }`, and set `plugins`.

- [x] **Step 3: Use effective plugins in standalone metric detail**

In `MetricViews.initPage()`, replace `getMonitorPlugin({ monitor_object_id })` with `getEffectivePlugins(monitorObjectId, { instance_id: instanceId })`.

- [x] **Step 4: Run TypeScript verification**

Run: `cd web && pnpm type-check`

Expected: TypeScript completes successfully.

## Task 3: Final Verification

**Files:**
- All changed files.

- [x] **Step 1: Run backend target test**

Run: `cd server && uv run pytest apps/monitor/tests/test_monitor_instance_view.py -q`

Expected: pass.

- [x] **Step 2: Inspect diff**

Run: `git diff --check && git diff --stat`

Expected: no whitespace errors, diff limited to the planned files.
