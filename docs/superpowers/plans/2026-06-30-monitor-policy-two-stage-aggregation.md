# Monitor Policy Two-Stage Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将监控策略聚合从单一 `algorithm + group_by` 升级为“分组聚合方式 + by 分组维度 + 窗口汇聚方式”，并让策略预览、后台扫描、旧策略、策略模板使用同一语义。

**Architecture:** 后端新增 `group_algorithm` 字段承载 `AVG/MAX/MIN/SUM/COUNT by (...)` 的左侧聚合方法，保留 `algorithm` 字段承载窗口方法 `*_OVER_TIME/COUNT_OVER_TIME/LAST_OVER_TIME`。查询生成统一走 `build_policy_query(window_algorithm, metric_query, period, group_by, group_algorithm)`，内部生成 `<window>((<group>(metric) by (...))[period:period/30])`；前端把 `group_algorithm` 和 `group_by` 合并成一个组合控件。

**Tech Stack:** Django 4.2 + DRF + Celery + VictoriaMetrics/MetricsQL；Next.js 16 + React 19 + Ant Design；测试使用现有 `pytest` 和 `tsx` 脚本。

---

## File Structure

- Modify: `server/apps/monitor/tasks/utils/policy_methods.py`
  - 职责：聚合算法常量、旧算法迁移归一、period step 计算、MetricsQL 查询生成。
- Modify: `server/apps/monitor/tasks/services/policy_scan/metric_query.py`
  - 职责：后台扫描调用统一查询生成，传入 `policy.group_algorithm`。
- Modify: `server/apps/monitor/services/policy_preview.py`
  - 职责：策略预览 payload 校验、查询生成和扫描逻辑保持一致。
- Modify: `server/apps/monitor/models/monitor_policy.py`
  - 职责：新增 `MonitorPolicy.group_algorithm`。
- Create: `server/apps/monitor/migrations/0042_monitorpolicy_group_algorithm.py`
  - 职责：新增字段并迁移旧策略值。
- Modify: `server/apps/monitor/serializers/monitor_policy.py`
  - 职责：校验 `group_algorithm` 和新的窗口 `algorithm` 合法集合；兼容旧单字段输入。
- Modify: `server/apps/monitor/services/policy.py`
  - 职责：导入/读取策略模板时归一化模板字段。
- Modify: `server/apps/monitor/services/policy_bulk.py`
  - 职责：批量创建策略时把模板中的 `group_algorithm` 带入 payload。
- Modify: `server/apps/monitor/support-files/plugins/**/policy.json`
  - 职责：模板增加 `group_algorithm`，旧 `algorithm` 按迁移规则改为窗口方法。
- Modify: `web/src/app/monitor/hooks/event.tsx`
  - 职责：拆分分组聚合方法列表和窗口汇聚方法列表。
- Modify: `web/src/app/monitor/types/event.ts`
  - 职责：`StrategyFields` 增加 `group_algorithm`。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
  - 职责：把分组聚合方式和分组维度合并为 `AVG（平均值） by instance_id` 控件。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
  - 职责：新增状态、初始化、编辑回填、保存 payload、预览传参。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`
  - 职责：预览 payload 增加 `group_algorithm`。
- Modify: `web/src/app/monitor/locales/zh.json`
  - 职责：新增/调整分组维度组合控件提示、窗口汇聚方法提示。
- Modify: `web/src/app/monitor/locales/en.json`
  - 职责：英文文案同步。
- Create/Modify tests listed in each task.

## Migration Rules

| 旧 `algorithm` | 新 `group_algorithm` | 新 `algorithm` |
| --- | --- | --- |
| `avg` | `avg` | `avg_over_time` |
| `avg_over_time` | `avg` | `avg_over_time` |
| `max` | `max` | `max_over_time` |
| `max_over_time` | `max` | `max_over_time` |
| `min` | `min` | `min_over_time` |
| `min_over_time` | `min` | `min_over_time` |
| `sum` | `sum` | `sum_over_time` |
| `sum_over_time` | `sum` | `sum_over_time` |
| `count` | `count` | `last_over_time` |
| `last_over_time` | `avg` | `last_over_time` |

---

### Task 1: Backend Query Builder

**Files:**
- Modify: `server/apps/monitor/tasks/utils/policy_methods.py`
- Test: `server/apps/monitor/tests/test_policy_preview_query.py`

- [ ] **Step 1: Write failing query-builder tests**

Add tests to `server/apps/monitor/tests/test_policy_preview_query.py`:

```python
def test_build_two_stage_avg_query_uses_group_then_window(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_two_stage_avg_query_builder_test_module")

    query = module.build_policy_query(
        "avg_over_time",
        "disk_used_percent",
        "5m",
        "instance_id",
        "avg",
    )

    assert query == "avg_over_time((avg(disk_used_percent) by (instance_id))[5m:10s])"


def test_build_two_stage_count_query_uses_count_grouping(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_two_stage_count_query_builder_test_module")

    query = module.build_policy_query(
        "count_over_time",
        "interface_info",
        "5m",
        "instance_id",
        "sum",
    )

    assert query == "count_over_time((count(interface_info) by (instance_id))[5m:10s])"


def test_build_two_stage_last_query_uses_avg_grouping(monkeypatch):
    module = _load_policy_methods(monkeypatch, "monitor_two_stage_last_query_builder_test_module")

    query = module.build_policy_query(
        "last_over_time",
        "interface_oper_status",
        "5m",
        "instance_id,interface",
        "avg",
    )

    assert query == "last_over_time((avg(interface_oper_status) by (instance_id,interface))[5m:10s])"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_preview_query.py -q
```

Expected: FAIL because `build_policy_query()` currently takes 4 arguments and does not support `count_over_time`.

- [ ] **Step 3: Implement constants, step helper, and new query builder**

Replace the algorithm constants and query-builder section in `server/apps/monitor/tasks/utils/policy_methods.py` with:

```python
GROUP_AGGREGATION_ALGORITHMS = {"sum", "avg", "max", "min", "count"}
WINDOW_AGGREGATION_ALGORITHMS = {
    "max_over_time",
    "min_over_time",
    "avg_over_time",
    "sum_over_time",
    "count_over_time",
    "last_over_time",
}

LEGACY_ALGORITHM_MAPPING = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}


def normalize_policy_algorithms(algorithm, group_algorithm=None):
    if group_algorithm:
        if group_algorithm not in GROUP_AGGREGATION_ALGORITHMS:
            raise BaseAppException(f"invalid group algorithm method: {group_algorithm}")
        if algorithm not in WINDOW_AGGREGATION_ALGORITHMS:
            raise BaseAppException(f"invalid algorithm method: {algorithm}")
        return group_algorithm, algorithm

    if algorithm in LEGACY_ALGORITHM_MAPPING:
        return LEGACY_ALGORITHM_MAPPING[algorithm]
    raise BaseAppException(f"invalid algorithm method: {algorithm}")


def period_step(period):
    seconds = max(1, period_to_seconds({"type": "min", "value": 5}) // 30)
    matched = re.match(r"^(\d+)(m|h|d)$", str(period or ""))
    if matched:
        value = int(matched.group(1))
        unit = matched.group(2)
        seconds = value * {"m": 60, "h": 3600, "d": 86400}[unit] // 30
    seconds = max(1, seconds)
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def build_policy_query(algorithm, metric_query, period, group_by, group_algorithm=None):
    group_algorithm, algorithm = normalize_policy_algorithms(algorithm, group_algorithm)
    if not group_by:
        raise BaseAppException("group_by is required")
    resolution = period_step(period)
    return f"{algorithm}(({group_algorithm}({metric_query}) by ({group_by}))[{period}:{resolution}])"
```

Then add a compatibility wrapper for legacy `algorithm=count`:

```python
def _legacy_count(metric_query, start, end, step, group_by):
    query = build_policy_query("last_over_time", metric_query, step, group_by, "count")
    return VictoriaMetricsAPI().query_range(query, start, end, step)
```

Then update `METHOD` keys to include only window methods plus legacy keys during transition:

```python
METHOD = {
    "sum": sum_over_time,
    "avg": avg_over_time,
    "max": max_over_time,
    "min": min_over_time,
    "count": _legacy_count,
    "max_over_time": max_over_time,
    "min_over_time": min_over_time,
    "avg_over_time": avg_over_time,
    "sum_over_time": sum_over_time,
    "count_over_time": count_over_time,
    "last_over_time": last_over_time,
}
```

Add a new method:

```python
def count_over_time(metric_query, start, end, step, group_by, group_algorithm=None):
    query = build_policy_query("count_over_time", metric_query, step, group_by, group_algorithm)
    return VictoriaMetricsAPI().query_range(query, start, end, step)
```

Update `avg_over_time/max_over_time/min_over_time/sum_over_time/last_over_time` to accept `group_algorithm=None` and call `build_policy_query(..., group_algorithm)`.

- [ ] **Step 4: Run query-builder tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_preview_query.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add server/apps/monitor/tasks/utils/policy_methods.py server/apps/monitor/tests/test_policy_preview_query.py
git commit -m "feat(monitor): build two-stage policy aggregation queries"
```

### Task 2: Backend Scan And Preview Use `group_algorithm`

**Files:**
- Modify: `server/apps/monitor/tasks/services/policy_scan/metric_query.py`
- Modify: `server/apps/monitor/services/policy_preview.py`
- Test: `server/apps/monitor/tests/test_metric_query_trigger_count.py`
- Test: `server/apps/monitor/tests/test_policy_preview_query.py`

- [ ] **Step 1: Write failing scan test**

Add to `server/apps/monitor/tests/test_metric_query_trigger_count.py`:

```python
def test_query_aggregation_metrics_passes_group_algorithm_to_method(monkeypatch):
    module = _load_metric_query_module(monkeypatch)
    captured = {}

    def fake_method(query, start, end, step, group_by, group_algorithm=None):
        captured.update({"step": step, "group_by": group_by, "group_algorithm": group_algorithm})
        return {"data": {"result": []}}

    monkeypatch.setitem(module.METHOD, "avg_over_time", fake_method)

    policy = types.SimpleNamespace(
        last_run_time=datetime(2026, 6, 24, 10, 10, tzinfo=timezone.utc),
        query_condition={"type": "pmq", "query": "up{}"},
        group_by=["instance_id"],
        group_algorithm="avg",
        algorithm="avg_over_time",
        metric_unit="",
        calculation_unit="",
    )

    service = module.MetricQueryService(policy, {})
    service.query_aggregation_metrics({"type": "min", "value": 5}, points=2)

    assert captured["step"] == "5m"
    assert captured["group_by"] == "instance_id"
    assert captured["group_algorithm"] == "avg"
```

- [ ] **Step 2: Write failing preview test**

Add to `server/apps/monitor/tests/test_policy_preview_query.py`:

```python
def test_policy_preview_uses_group_algorithm_in_query(monkeypatch):
    metric = types.SimpleNamespace(
        query="disk_used_percent{__$labels__}",
        unit="percent",
        instance_id_keys=["instance_id"],
    )
    module = _load_policy_preview_service(monkeypatch, metric)
    payload = {
        "query_condition": {"type": "metric", "metric_id": 10, "filter": []},
        "period": {"type": "min", "value": 5},
        "group_algorithm": "max",
        "algorithm": "max_over_time",
        "group_by": ["instance_id"],
        "preview": {"instance_id": "host-1", "instance_id_values": ["abc"]},
    }

    result = module.PolicyPreviewService(payload).preview()

    assert result["query"] == (
        'max_over_time((max(disk_used_percent{instance_id=~"abc"}) '
        'by (instance_id))[5m:10s])'
    )
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_metric_query_trigger_count.py apps/monitor/tests/test_policy_preview_query.py -q
```

Expected: FAIL because services do not pass/read `group_algorithm`.

- [ ] **Step 4: Implement scan service change**

In `server/apps/monitor/tasks/services/policy_scan/metric_query.py`, change:

```python
return method(query, start_timestamp, end_timestamp, step, group_by)
```

to:

```python
return method(
    query,
    start_timestamp,
    end_timestamp,
    step,
    group_by,
    getattr(self.policy, "group_algorithm", None),
)
```

- [ ] **Step 5: Implement preview service change**

In `server/apps/monitor/services/policy_preview.py`, change:

```python
algorithm = self._require_value("algorithm")
```

to:

```python
algorithm = self._require_value("algorithm")
group_algorithm = self.payload.get("group_algorithm")
```

Change:

```python
query = build_policy_query(algorithm, metric_query, step, group_by_clause)
data = method(metric_query, start, end, step, group_by_clause)
```

to:

```python
query = build_policy_query(algorithm, metric_query, step, group_by_clause, group_algorithm)
data = method(metric_query, start, end, step, group_by_clause, group_algorithm)
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_metric_query_trigger_count.py apps/monitor/tests/test_policy_preview_query.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add server/apps/monitor/tasks/services/policy_scan/metric_query.py server/apps/monitor/services/policy_preview.py server/apps/monitor/tests/test_metric_query_trigger_count.py server/apps/monitor/tests/test_policy_preview_query.py
git commit -m "feat(monitor): use group algorithm in scan and preview"
```

### Task 3: Model, Serializer, And Data Migration

**Files:**
- Modify: `server/apps/monitor/models/monitor_policy.py`
- Create: `server/apps/monitor/migrations/0042_monitorpolicy_group_algorithm.py`
- Modify: `server/apps/monitor/serializers/monitor_policy.py`
- Test: `server/apps/monitor/tests/test_monitor_policy_serializer_validation.py`

- [ ] **Step 1: Write failing serializer tests**

Add to `server/apps/monitor/tests/test_monitor_policy_serializer_validation.py`:

```python
def test_policy_serializer_accepts_two_stage_algorithms():
    from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

    serializer = MonitorPolicySerializer()

    assert serializer.validate_group_algorithm("avg") == "avg"
    assert serializer.validate_algorithm("avg_over_time") == "avg_over_time"
    assert serializer.validate_algorithm("count_over_time") == "count_over_time"


def test_policy_serializer_rejects_legacy_count_as_window_algorithm():
    from apps.monitor.serializers.monitor_policy import MonitorPolicySerializer

    serializer = MonitorPolicySerializer()

    with pytest.raises(Exception):
        serializer.validate_algorithm("count")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_policy_serializer_validation.py -q
```

Expected: FAIL because `group_algorithm` does not exist and `count` is still accepted.

- [ ] **Step 3: Add model field**

In `server/apps/monitor/models/monitor_policy.py`, add below `algorithm`:

```python
    group_algorithm = models.CharField(max_length=50, default="avg", verbose_name="分组聚合算法")
```

- [ ] **Step 4: Create migration**

Create `server/apps/monitor/migrations/0042_monitorpolicy_group_algorithm.py`:

```python
from django.db import migrations, models


MAPPING = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}


def forwards(apps, schema_editor):
    MonitorPolicy = apps.get_model("monitor", "MonitorPolicy")
    for policy in MonitorPolicy.objects.all().only("id", "algorithm", "group_algorithm"):
        group_algorithm, algorithm = MAPPING.get(policy.algorithm, ("avg", "avg_over_time"))
        policy.group_algorithm = group_algorithm
        policy.algorithm = algorithm
        policy.save(update_fields=["group_algorithm", "algorithm"])


def backwards(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("monitor", "0041_monitorpolicy_trigger_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="monitorpolicy",
            name="group_algorithm",
            field=models.CharField(default="avg", max_length=50, verbose_name="分组聚合算法"),
        ),
        migrations.RunPython(forwards, backwards),
    ]
```

- [ ] **Step 5: Update serializer validation**

In `server/apps/monitor/serializers/monitor_policy.py`, replace `_VALID_AGGREGATION_ALGORITHMS` with:

```python
_VALID_GROUP_AGGREGATION_ALGORITHMS = {"sum", "avg", "max", "min", "count"}
_VALID_WINDOW_AGGREGATION_ALGORITHMS = {
    "max_over_time",
    "min_over_time",
    "avg_over_time",
    "sum_over_time",
    "count_over_time",
    "last_over_time",
}
```

Change `validate_algorithm`:

```python
    def validate_algorithm(self, value):
        if value and value not in _VALID_WINDOW_AGGREGATION_ALGORITHMS:
            raise serializers.ValidationError(f"algorithm 非法，须为 {sorted(_VALID_WINDOW_AGGREGATION_ALGORITHMS)} 之一")
        return value

    def validate_group_algorithm(self, value):
        if value and value not in _VALID_GROUP_AGGREGATION_ALGORITHMS:
            raise serializers.ValidationError(f"group_algorithm 非法，须为 {sorted(_VALID_GROUP_AGGREGATION_ALGORITHMS)} 之一")
        return value or "avg"
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_policy_serializer_validation.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add server/apps/monitor/models/monitor_policy.py server/apps/monitor/migrations/0042_monitorpolicy_group_algorithm.py server/apps/monitor/serializers/monitor_policy.py server/apps/monitor/tests/test_monitor_policy_serializer_validation.py
git commit -m "feat(monitor): persist group aggregation algorithm"
```

### Task 4: Policy Templates And Bulk Payloads

**Files:**
- Modify: `server/apps/monitor/services/policy.py`
- Modify: `server/apps/monitor/services/policy_bulk.py`
- Modify: `server/apps/monitor/support-files/plugins/**/policy.json`
- Test: `server/apps/monitor/tests/test_policy_bulk_payload.py`
- Test: `server/apps/monitor/tests/test_policy_service_templates.py`
- Test: `server/apps/monitor/tests/test_policy_migrate.py`

- [ ] **Step 1: Write failing bulk payload test**

Add to `server/apps/monitor/tests/test_policy_bulk_payload.py`:

```python
def test_build_bulk_policy_payloads_includes_group_algorithm_from_template():
    module_path = Path(__file__).resolve().parents[1] / "services" / "policy_bulk.py"
    module = _load_module("monitor_policy_bulk_group_algorithm_payload_test_module", module_path)

    payloads = module.build_bulk_policy_payloads(
        monitor_object_id=3,
        templates=[
            {
                "name": "接口数量变化",
                "metric_id": 101,
                "collect_type": 9,
                "group_algorithm": "count",
                "algorithm": "last_over_time",
            }
        ],
        assets=[{"instance_id": "('host-a',)", "organizations": [7]}],
        config={"group_by": ["instance_id"]},
    )

    assert payloads[0]["group_algorithm"] == "count"
    assert payloads[0]["algorithm"] == "last_over_time"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_bulk_payload.py -q
```

Expected: FAIL because `group_algorithm` is not included.

- [ ] **Step 3: Implement bulk payload propagation**

In `server/apps/monitor/services/policy_bulk.py`, add:

```python
                "group_algorithm": template.get("group_algorithm") or "avg",
```

next to:

```python
                "algorithm": template.get("algorithm") or "avg_over_time",
```

Use `avg_over_time` as the default window algorithm, not legacy `avg`.

- [ ] **Step 4: Implement template normalization**

In `server/apps/monitor/services/policy.py`, add helper:

```python
LEGACY_TEMPLATE_ALGORITHM_MAPPING = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}


def normalize_policy_template(template):
    item = {**template}
    group_algorithm, algorithm = LEGACY_TEMPLATE_ALGORITHM_MAPPING.get(
        item.get("algorithm"),
        (item.get("group_algorithm") or "avg", item.get("algorithm") or "avg_over_time"),
    )
    item["group_algorithm"] = item.get("group_algorithm") or group_algorithm
    item["algorithm"] = algorithm
    return item
```

Use it in `import_monitor_policy` before saving:

```python
data = {**data, "templates": [normalize_policy_template(item) for item in data.get("templates", [])]}
```

Use it in `get_policy_templates` before building `item`:

```python
template = normalize_policy_template(template)
```

- [ ] **Step 5: Mechanically update policy files**

Run a small one-off script from repo root:

```bash
python - <<'PY'
import json
from pathlib import Path

mapping = {
    "avg": ("avg", "avg_over_time"),
    "avg_over_time": ("avg", "avg_over_time"),
    "max": ("max", "max_over_time"),
    "max_over_time": ("max", "max_over_time"),
    "min": ("min", "min_over_time"),
    "min_over_time": ("min", "min_over_time"),
    "sum": ("sum", "sum_over_time"),
    "sum_over_time": ("sum", "sum_over_time"),
    "count": ("count", "last_over_time"),
    "last_over_time": ("avg", "last_over_time"),
}

for path in Path("server/apps/monitor/support-files/plugins").rglob("policy.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    templates = data.get("templates", []) if isinstance(data, dict) else []
    for template in templates:
        old = template.get("algorithm")
        if old in mapping:
            group_algorithm, algorithm = mapping[old]
            if template.get("group_algorithm") != group_algorithm or template.get("algorithm") != algorithm:
                template["group_algorithm"] = group_algorithm
                template["algorithm"] = algorithm
                changed = True
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
```

- [ ] **Step 6: Run template and bulk tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_bulk_payload.py apps/monitor/tests/test_policy_service_templates.py apps/monitor/tests/test_policy_migrate.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add server/apps/monitor/services/policy.py server/apps/monitor/services/policy_bulk.py server/apps/monitor/support-files/plugins server/apps/monitor/tests/test_policy_bulk_payload.py server/apps/monitor/tests/test_policy_service_templates.py server/apps/monitor/tests/test_policy_migrate.py
git commit -m "feat(monitor): normalize policy templates for two-stage aggregation"
```

### Task 5: Frontend Form And Preview Payload

**Files:**
- Modify: `web/src/app/monitor/hooks/event.tsx`
- Modify: `web/src/app/monitor/types/event.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx`
- Modify: `web/src/app/monitor/locales/zh.json`
- Modify: `web/src/app/monitor/locales/en.json`
- Test: `web/scripts/monitor-strategy-aggregation-designer-story-test.ts`
- Optional new test: `web/scripts/monitor-policy-two-stage-aggregation-form-test.ts`

- [ ] **Step 1: Write failing source contract test**

Create `web/scripts/monitor-policy-two-stage-aggregation-form-test.ts`:

```ts
import fs from 'fs';
import path from 'path';

const root = process.cwd();
const formPath = path.join(root, 'src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx');
const pagePath = path.join(root, 'src/app/monitor/(pages)/event/strategy/detail/page.tsx');
const previewPath = path.join(root, 'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx');
const hooksPath = path.join(root, 'src/app/monitor/hooks/event.tsx');

const read = (file: string) => fs.readFileSync(file, 'utf8');
const assert = (condition: unknown, message: string) => {
  if (!condition) throw new Error(message);
};

const form = read(formPath);
const page = read(pagePath);
const preview = read(previewPath);
const hooks = read(hooksPath);

assert(form.includes('groupAlgorithm'), 'metric form should accept groupAlgorithm');
assert(form.includes('by'), 'metric form should render group algorithm by dimensions');
assert(page.includes('group_algorithm'), 'strategy page should save group_algorithm');
assert(preview.includes('group_algorithm'), 'preview payload should include group_algorithm');
assert(hooks.includes('useGroupAlgorithmList'), 'hooks should expose group algorithm options');
assert(hooks.includes('COUNT_OVER_TIME'), 'window method list should include COUNT_OVER_TIME');
assert(!hooks.includes("value: 'count'"), 'window method list should not keep legacy count');

console.log('monitor policy two-stage aggregation form contract OK');
```

- [ ] **Step 2: Add package script**

In `web/package.json`, add:

```json
"test:monitor-policy-two-stage-aggregation-form": "pnpm exec tsx scripts/monitor-policy-two-stage-aggregation-form-test.ts"
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
cd web && pnpm test:monitor-policy-two-stage-aggregation-form
```

Expected: FAIL because production form does not yet include `groupAlgorithm/group_algorithm`.

- [ ] **Step 4: Add frontend types**

In `web/src/app/monitor/types/event.ts`, add:

```ts
  group_algorithm?: string;
```

near `algorithm?: string;`.

- [ ] **Step 5: Split method hooks**

In `web/src/app/monitor/hooks/event.tsx`, add:

```ts
const useGroupAlgorithmList = (): ListItem[] => {
  return useMemo(
    () => [
      { label: 'AVG（平均值）', value: 'avg' },
      { label: 'MAX（最大值）', value: 'max' },
      { label: 'MIN（最小值）', value: 'min' },
      { label: 'SUM（求和）', value: 'sum' },
      { label: 'COUNT（计数）', value: 'count' },
    ],
    []
  );
};
```

Replace `useMethodList` options with:

```ts
[
  { label: 'AVG_OVER_TIME', value: 'avg_over_time', title: t('monitor.events.avgOverTimeTitle') },
  { label: 'MAX_OVER_TIME', value: 'max_over_time', title: t('monitor.events.maxOverTimeTitle') },
  { label: 'MIN_OVER_TIME', value: 'min_over_time', title: t('monitor.events.minOverTimeTitle') },
  { label: 'SUM_OVER_TIME', value: 'sum_over_time', title: t('monitor.events.sumOverTimeTitle') },
  { label: 'COUNT_OVER_TIME', value: 'count_over_time', title: t('monitor.events.countOverTimeTitle') },
  { label: 'LAST_OVER_TIME', value: 'last_over_time', title: t('monitor.events.lastOverTimeTitle') },
]
```

Export `useGroupAlgorithmList`.

- [ ] **Step 6: Update page state and payload**

In `page.tsx`, add state:

```ts
const [groupAlgorithm, setGroupAlgorithm] = useState<string>('avg');
```

Initialize add/built-in default:

```ts
group_algorithm: strategyInfo.group_algorithm || 'avg',
algorithm: strategyInfo.algorithm || 'avg_over_time',
```

In `dealDetail`, add:

```ts
const { group_algorithm } = data;
setGroupAlgorithm((group_algorithm as string) || 'avg');
```

Add handler:

```ts
const handleGroupAlgorithmChange = (val: string) => {
  setGroupAlgorithm(val);
};
```

In `createStrategy`, before `operateStrategy(params)`:

```ts
params.group_algorithm = groupAlgorithm || 'avg';
```

Pass props to `MetricDefinitionForm`:

```tsx
groupAlgorithm={groupAlgorithm}
onGroupAlgorithmChange={handleGroupAlgorithmChange}
```

Pass prop to `MetricPreview`:

```tsx
groupAlgorithm={groupAlgorithm}
```

- [ ] **Step 7: Update metric form combined control**

In `metricDefinitionForm.tsx`, import `useGroupAlgorithmList`, add props:

```ts
  groupAlgorithm: string;
  onGroupAlgorithmChange: (val: string) => void;
```

Use:

```ts
const GROUP_ALGORITHM_LIST = useGroupAlgorithmList();
```

Replace the group dimension `<Select>` with the production version of the prototype:

```tsx
<div className={strategyStyle.groupByControl}>
  <Select
    className={strategyStyle.groupBySelect}
    variant="borderless"
    value={groupAlgorithm}
    onChange={onGroupAlgorithmChange}
    options={GROUP_ALGORITHM_LIST}
  />
  <div className={strategyStyle.groupByDivider}>by</div>
  <Select
    className={strategyStyle.groupDimensionSelect}
    variant="borderless"
    showSearch
    allowClear
    mode="multiple"
    maxTagCount="responsive"
    placeholder={t('monitor.events.groupDimension')}
    value={groupBy}
    onChange={(value) => onGroupChange(sanitizeGroupBy(value))}
  >
    {groupByOptions.map((item: string) => (
      <Option value={item} key={item}>
        {item}
      </Option>
    ))}
  </Select>
</div>
```

Add SCSS to `web/src/app/monitor/(pages)/event/strategy/index.module.scss`:

```scss
.groupByControl {
  display: grid;
  grid-template-columns: 184px 42px minmax(0, 1fr);
  align-items: center;
  height: 36px;
  overflow: hidden;
  background: var(--color-bg-1);
  border: 1px solid var(--color-primary);
  border-radius: 5px;
  box-shadow: 0 0 0 2px rgb(22 119 255 / 8%);
}

.groupBySelect,
.groupDimensionSelect {
  height: 34px;
}

.groupByDivider {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-3);
  font-size: 13px;
  background: var(--color-bg-1);
  border-left: 1px solid var(--color-border-1);
  border-right: 1px solid var(--color-border-1);
}
```

- [ ] **Step 8: Update preview payload**

In `metricPreview.tsx`, add prop:

```ts
  groupAlgorithm: string;
```

Add to payload:

```ts
group_algorithm: groupAlgorithm || 'avg',
```

Add `groupAlgorithm` to effect dependencies.

- [ ] **Step 9: Run frontend tests and type check**

Run:

```bash
cd web && pnpm test:monitor-policy-two-stage-aggregation-form
cd web && pnpm test:monitor-strategy-aggregation-designer
cd web && pnpm type-check
```

Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add web/src/app/monitor/hooks/event.tsx web/src/app/monitor/types/event.ts 'web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' 'web/src/app/monitor/(pages)/event/strategy/detail/page.tsx' 'web/src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' 'web/src/app/monitor/(pages)/event/strategy/index.module.scss' web/src/app/monitor/locales/zh.json web/src/app/monitor/locales/en.json web/scripts/monitor-policy-two-stage-aggregation-form-test.ts web/package.json
git commit -m "feat(monitor): add two-stage aggregation controls"
```

### Task 6: End-To-End Verification

**Files:**
- No new files unless failures require fixes.

- [ ] **Step 1: Run backend monitor tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_policy_preview_query.py apps/monitor/tests/test_metric_query_trigger_count.py apps/monitor/tests/test_monitor_policy_serializer_validation.py apps/monitor/tests/test_policy_bulk_payload.py apps/monitor/tests/test_policy_service_templates.py apps/monitor/tests/test_policy_migrate.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend focused tests**

Run:

```bash
cd web && pnpm test:monitor-policy-two-stage-aggregation-form && pnpm test:monitor-strategy-aggregation-designer
```

Expected: PASS.

- [ ] **Step 3: Run module gates**

Run:

```bash
cd server && make test
cd web && pnpm lint && pnpm type-check
```

Expected: PASS. If full server test is too slow or environment-blocked, record the exact failure and keep the focused backend test output.

- [ ] **Step 4: Manual Storybook/product check**

Run or keep Storybook:

```bash
cd web && ./node_modules/.bin/storybook dev -p 6006 --no-open
```

Open:

```text
http://localhost:6006/iframe.html?id=monitor-strategyaggregationdesigner--default-numeric-metric&viewMode=story
```

Check:

- 分组维度行 shows `AVG（平均值） by instance_id`.
- 汇聚方式 only shows `AVG_OVER_TIME/MAX_OVER_TIME/MIN_OVER_TIME/SUM_OVER_TIME/COUNT_OVER_TIME/LAST_OVER_TIME`.
- Query preview shows `[5m:10s]`.

- [ ] **Step 5: Final commit if verification fixes were needed**

If Step 1-4 required additional fixes:

```bash
git add <changed-files>
git commit -m "fix(monitor): complete two-stage aggregation verification"
```

## Self-Review

- Spec coverage: The plan covers group aggregation config, retained window methods, old policy migration, template normalization, preview/scan shared query structure, and 30-point subquery step.
- Placeholder scan: No placeholder markers remain. Each task includes concrete files, test commands, and expected outcomes.
- Type consistency: The chosen API/model field is `group_algorithm`; existing `algorithm` becomes the window aggregation method. Frontend state uses `groupAlgorithm` and serializes to `group_algorithm`.

## Execution Options

Plan complete and saved to `docs/superpowers/plans/2026-06-30-monitor-policy-two-stage-aggregation.md`. Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
