# Monitor Object Field Display Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build monitor object display columns that can show either metric values or VM label field values, with VM-backed field-key selection in the object display configuration modal.

**Architecture:** Keep the existing `MonitorObject.display_fields` JSON storage and extend it with an optional column `type` plus binding `field` for field display columns. Backend validation, list enrichment, and frontend rendering share one field display key format: `field::<plugin>::<metric>::<field>`. The object configuration modal keeps the current card model and adds a second add button plus a VM field selection modal.

**Tech Stack:** Django REST Framework, VictoriaMetrics API wrapper, pytest, Next.js 16, React 19, TypeScript, Ant Design, Storybook.

---

## File Structure

- Modify `server/apps/monitor/utils/display_fields.py`: normalize metric and field display column configs.
- Modify `server/apps/monitor/utils/display_fields_metrics.py`: add field binding extraction and key helpers.
- Modify `server/apps/monitor/services/monitor_object.py`: query VM labels and enrich instance list rows for field columns.
- Modify `server/apps/monitor/views/monitor_metrics.py`: add `vm_fields` action on metrics.
- Modify `server/apps/monitor/tests/test_display_fields_metric_union.py`: backend unit coverage for keys, validation, VM fields, and list enrichment.
- Modify `web/src/app/monitor/(pages)/integration/object/types.ts`: add `type` and `field` to display column types.
- Modify `web/src/app/monitor/(pages)/integration/object/api.ts`: add `getMetricVmFields(metricId)`.
- Modify `web/src/app/monitor/(pages)/integration/object/displayFieldsModal.tsx`: add metric/field column controls and VM field picker.
- Modify `web/src/app/monitor/(pages)/view/viewList.tsx`: render field columns as text from field display keys.
- Modify `web/src/app/monitor/(pages)/view/viewHive.tsx`: ignore field columns when deriving metric value candidates.
- Modify `web/src/app/monitor/types/index.ts`: align public monitor object display field type.
- Modify `web/src/app/monitor/locales/zh.json` and `web/src/app/monitor/locales/en.json`: add labels and messages.
- Create `web/src/stories/monitor-object-display-fields-modal.stories.tsx`: Storybook visual states for the new modal.

## Task 1: Backend Display Field Contract

**Files:**
- Modify: `server/apps/monitor/utils/display_fields.py`
- Modify: `server/apps/monitor/utils/display_fields_metrics.py`
- Test: `server/apps/monitor/tests/test_display_fields_metric_union.py`

- [ ] **Step 1: Write failing tests for normalization and helper keys**

Add tests that assert old configs stay metric columns, field columns require `field`, and field keys use `field::<plugin>::<metric>::<field>`.

```python
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.utils.display_fields import validate_display_fields
from apps.monitor.utils.display_fields_metrics import (
    display_field_key,
    extract_field_bindings,
    extract_metric_bindings,
)


def test_display_field_key_for_metric_and_field():
    assert display_field_key("P", "cpu") == "P::cpu"
    assert display_field_key("", "cpu") == "cpu"
    assert display_field_key("P", "node_info", "collector_ip") == "field::P::node_info::collector_ip"


@pytest.mark.django_db
def test_validate_display_fields_accepts_metric_and_field_columns():
    obj = MonitorObject.objects.create(name="UTDisplayContract", level="base")
    plugin = MonitorPlugin.objects.create(name="P")
    _mk_metric(obj, plugin, "cpu")
    _mk_metric(obj, plugin, "node_info")

    normalized = validate_display_fields(obj, [
        {"name": "CPU", "sort_order": 1, "metrics": [{"plugin": "P", "metric": "cpu"}]},
        {"name": "采集IP", "type": "field", "sort_order": 0,
         "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}]},
    ])

    assert normalized == [
        {"name": "采集IP", "type": "field", "sort_order": 0,
         "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}]},
        {"name": "CPU", "sort_order": 1, "metrics": [{"plugin": "P", "metric": "cpu"}]},
    ]


@pytest.mark.django_db
def test_validate_display_fields_rejects_field_column_without_field():
    obj = MonitorObject.objects.create(name="UTDisplayMissingField", level="base")
    plugin = MonitorPlugin.objects.create(name="P")
    _mk_metric(obj, plugin, "node_info")

    with pytest.raises(BaseAppException, match="field"):
        validate_display_fields(obj, [
            {"name": "采集IP", "type": "field", "sort_order": 0,
             "metrics": [{"plugin": "P", "metric": "node_info"}]},
        ])


def test_extract_metric_and_field_bindings_separate_column_types():
    display_fields = [
        {"name": "CPU", "metrics": [{"plugin": "P", "metric": "cpu"}]},
        {"name": "IP", "type": "field", "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}]},
    ]
    assert extract_metric_bindings(display_fields) == [{"plugin": "P", "metric": "cpu"}]
    assert extract_field_bindings(display_fields) == [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd server && pytest apps/monitor/tests/test_display_fields_metric_union.py -q`

Expected: FAIL because `extract_field_bindings` and 3-argument `display_field_key` do not exist, and `validate_display_fields` does not enforce field columns.

- [ ] **Step 3: Implement backend contract helpers**

Update `display_field_key` to accept optional `field`, make `extract_metric_bindings` skip `type="field"`, and add `extract_field_bindings`.

```python
FIELD_DISPLAY_KEY_PREFIX = "field"


def display_field_key(plugin, metric, field=None):
    if field:
        return f"{FIELD_DISPLAY_KEY_PREFIX}{DISPLAY_FIELD_KEY_SEP}{plugin}{DISPLAY_FIELD_KEY_SEP}{metric}{DISPLAY_FIELD_KEY_SEP}{field}"
    if plugin:
        return f"{plugin}{DISPLAY_FIELD_KEY_SEP}{metric}"
    return metric


def is_field_display_column(col):
    return (col.get("type") or "metric") == "field"


def extract_metric_bindings(display_fields):
    bindings = []
    seen = set()
    for col in display_fields or []:
        if is_field_display_column(col):
            continue
        for binding in col.get("metrics", []):
            metric = binding.get("metric")
            if not metric:
                continue
            plugin = binding.get("plugin") or ""
            dedup_key = (plugin, metric)
            if dedup_key not in seen:
                seen.add(dedup_key)
                bindings.append({"plugin": plugin, "metric": metric})
    return bindings


def extract_field_bindings(display_fields):
    bindings = []
    seen = set()
    for col in display_fields or []:
        if not is_field_display_column(col):
            continue
        for binding in col.get("metrics", []):
            metric = binding.get("metric")
            field = binding.get("field")
            if not metric or not field:
                continue
            plugin = binding.get("plugin") or ""
            dedup_key = (plugin, metric, field)
            if dedup_key not in seen:
                seen.add(dedup_key)
                bindings.append({"plugin": plugin, "metric": metric, "field": field})
    return bindings
```

Update `validate_display_fields()` to branch on `type`.

```python
col_type = (col.get("type") or "metric").strip()
if col_type not in {"metric", "field"}:
    raise BaseAppException(f"display field '{name}' has invalid type")
...
field = (binding.get("field") or "").strip()
if col_type == "field" and not field:
    raise BaseAppException(f"display field '{name}' has an incomplete field binding")
...
norm_binding = {"plugin": plugin, "metric": metric}
if col_type == "field":
    norm_binding["field"] = field
...
normalized_col = {"name": name, "sort_order": col.get("sort_order", idx), "metrics": norm_metrics}
if col_type == "field":
    normalized_col["type"] = "field"
normalized.append(normalized_col)
```

- [ ] **Step 4: Run backend contract tests**

Run: `cd server && pytest apps/monitor/tests/test_display_fields_metric_union.py -q`

Expected: existing and new tests PASS.

## Task 2: Backend VM Field Enrichment and Candidate API

**Files:**
- Modify: `server/apps/monitor/services/monitor_object.py`
- Modify: `server/apps/monitor/views/monitor_metrics.py`
- Test: `server/apps/monitor/tests/test_display_fields_metric_union.py`

- [ ] **Step 1: Write failing tests for field value enrichment and VM field candidates**

Add tests that prove VM labels enrich rows and metric detail action returns label keys.

```python
@pytest.mark.django_db
@patch("apps.monitor.services.monitor_object.VictoriaMetricsAPI")
def test_field_display_columns_fill_label_value(mock_vm):
    mock_vm.return_value.query.return_value = {"data": {"result": [
        {"metric": {"instance_id": "i1", "collector_ip": "10.0.0.8"}, "value": [0, "1"]},
    ]}}
    obj = MonitorObject.objects.create(
        name="UTFieldFill", level="base",
        default_metric="any({instance_type='UTFieldFill'}) by (instance_id)",
        instance_id_keys=["instance_id"], supplementary_indicators=[],
        display_fields=[{"name": "采集IP", "type": "field", "sort_order": 0,
                         "metrics": [{"plugin": "P", "metric": "node_info", "field": "collector_ip"}]}],
    )
    plugin = MonitorPlugin.objects.create(name="P")
    _mk_metric(obj, plugin, "node_info")
    inst = MonitorInstance.objects.create(id="('i1',)", name="i1", monitor_object=obj)
    _mk_collect_config("cc-field-i1", inst, plugin)

    res = MonitorObjectService.get_monitor_instance(
        obj.id, page=1, page_size=10, name=None,
        qs=MonitorInstance.objects.all(), add_metrics=True,
    )

    assert res["results"][0]["field::P::node_info::collector_ip"] == "10.0.0.8"


@pytest.mark.django_db
@patch("apps.monitor.views.monitor_metrics.VictoriaMetricsAPI")
def test_metric_vm_fields_returns_vm_label_keys(mock_vm, rf):
    mock_vm.return_value.query.return_value = {"data": {"result": [
        {"metric": {"__name__": "node_info", "instance_id": "i1", "collector_ip": "10.0.0.8", "model": "R740"}},
    ]}}
    obj = MonitorObject.objects.create(name="UTVmFields", level="base")
    plugin = MonitorPlugin.objects.create(name="P")
    metric = _mk_metric(obj, plugin, "node_info")
    view = MetricViewSet.as_view({"get": "vm_fields"})
    request = rf.get(f"/monitor/api/metrics/{metric.id}/vm_fields/")

    response = view(request, pk=metric.id)

    assert response.data["result"] == ["collector_ip", "instance_id", "model"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd server && pytest apps/monitor/tests/test_display_fields_metric_union.py -q`

Expected: FAIL because field enrichment and `vm_fields` action are not implemented.

- [ ] **Step 3: Implement field enrichment**

Import `extract_field_bindings`, then add a `_query_metric_label_values(metric_obj, target_instances, field)` helper that mirrors `_query_metric_values()` but reads labels.

```python
@staticmethod
def _query_metric_label_values(metric_obj, target_instances, field):
    target_ids = [parse_instance_id(inst["instance_id"]) for inst in target_instances]
    query_parts = []
    for i, key in enumerate(metric_obj.instance_id_keys):
        values_set = {re.escape(str(item[i])) for item in target_ids if len(item) > i and item[i] is not None}
        if not values_set:
            continue
        values = MonitorObjectService._escape_promql_label_value("|".join(sorted(values_set)))
        query_parts.append(f'{key}=~"{values}"')

    query = metric_obj.query.replace("__$labels__", f"{', '.join(query_parts)}")
    metrics = VictoriaMetricsAPI().query(query)
    value_map = {}
    for metric in metrics.get("data", {}).get("result", []):
        instance_id = str(tuple([metric["metric"].get(i) for i in metric_obj.instance_id_keys]))
        value = metric.get("metric", {}).get(field)
        if value and instance_id not in value_map:
            value_map[instance_id] = value
    return value_map
```

In `_fill_display_metrics()`, after metric value enrichment, resolve field bindings with the same plugin eligibility map and write `display_field_key(plugin_name, metric_name, field)`.

- [ ] **Step 4: Implement VM fields API**

In `MetricViewSet`, add a detail action.

```python
@action(methods=["get"], detail=True, url_path="vm_fields")
def vm_fields(self, request, pk=None):
    metric = self.get_object()
    resp = VictoriaMetricsAPI().query(metric.query)
    fields = set()
    for item in resp.get("data", {}).get("result", []):
        fields.update((item.get("metric") or {}).keys())
    fields.discard("__name__")
    return WebUtils.response_success(sorted(fields))
```

- [ ] **Step 5: Run backend tests**

Run: `cd server && pytest apps/monitor/tests/test_display_fields_metric_union.py -q`

Expected: PASS.

## Task 3: Frontend Types, API, and Modal Interaction

**Files:**
- Modify: `web/src/app/monitor/(pages)/integration/object/types.ts`
- Modify: `web/src/app/monitor/(pages)/integration/object/api.ts`
- Modify: `web/src/app/monitor/(pages)/integration/object/displayFieldsModal.tsx`
- Modify: `web/src/app/monitor/locales/zh.json`
- Modify: `web/src/app/monitor/locales/en.json`

- [ ] **Step 1: Add TypeScript model support**

Update `DisplayMetricBinding` and `DisplayColumn`.

```ts
export type DisplayColumnType = 'metric' | 'field';

export interface DisplayMetricBinding {
  plugin: string;
  metric: string;
  field?: string;
}

export interface DisplayColumn {
  name: string;
  type?: DisplayColumnType;
  sort_order: number;
  metrics: DisplayMetricBinding[];
}
```

- [ ] **Step 2: Add API helper**

Add `getMetricVmFields(metricId)` to `useObjectApi()`.

```ts
const getMetricVmFields = async (
  metricId: number | string,
  signal?: AbortSignal
): Promise<string[]> => {
  return await get(`/monitor/api/metrics/${metricId}/vm_fields/`, { signal });
};
```

Return it from the hook.

- [ ] **Step 3: Update modal state and add actions**

Add:

```ts
const FIELD_COLUMN_TYPE = 'field';
const getColumnType = (col: DisplayColumn) => col.type === FIELD_COLUMN_TYPE ? 'field' : 'metric';
```

Replace `addColumn()` with two functions:

```ts
const addMetricColumn = () => {
  setCurrentColumns([...currentColumns, {
    name: t('monitor.object.newDisplayColumn'),
    type: 'metric',
    sort_order: currentColumns.length,
    metrics: []
  }]);
};

const addFieldColumn = () => {
  setCurrentColumns([...currentColumns, {
    name: t('monitor.object.newFieldDisplayColumn'),
    type: 'field',
    sort_order: currentColumns.length,
    metrics: []
  }]);
};
```

When adding a binding, include `field: ''` only for field columns.

- [ ] **Step 4: Add VM field picker modal**

Use Ant Design `Modal` and `Radio.Group` state:

```ts
const [fieldPickerOpen, setFieldPickerOpen] = useState(false);
const [fieldPickerLoading, setFieldPickerLoading] = useState(false);
const [fieldOptions, setFieldOptions] = useState<string[]>([]);
const [selectedField, setSelectedField] = useState('');
const fieldTargetRef = useRef<{ colIdx: number; bindIdx: number } | null>(null);
```

On query button click, find the selected metric option for the row and call `getMetricVmFields(metric.id)`. Open a modal with single-select fields and confirm button that calls `updateBindingField(colIdx, bindIdx, selectedField)`.

- [ ] **Step 5: Add localization**

Add Chinese keys:

```json
"addMetricColumn": "添加指标列",
"newFieldDisplayColumn": "新展示列",
"metricColumn": "指标列",
"fieldColumn": "展示列",
"fieldPlaceholder": "请输入维度 key",
"queryFields": "查询字段",
"selectField": "选择字段",
"noFieldsFound": "未查询到字段",
"selectMetricFirst": "请先选择模板和指标"
```

Add matching English keys.

- [ ] **Step 6: Run frontend type check for touched surface**

Run: `cd web && pnpm type-check`

Expected: PASS or unrelated existing errors documented before proceeding.

## Task 4: Frontend List Rendering and Hive Compatibility

**Files:**
- Modify: `web/src/app/monitor/(pages)/view/viewList.tsx`
- Modify: `web/src/app/monitor/(pages)/view/viewHive.tsx`
- Modify: `web/src/app/monitor/types/index.ts`

- [ ] **Step 1: Update public display field type**

Update `ObjectItem.display_fields` to include optional `type` and binding `field`.

```ts
display_fields?: {
  name: string;
  type?: 'metric' | 'field';
  sort_order: number;
  metrics: { plugin: string; metric: string; field?: string }[];
}[];
```

- [ ] **Step 2: Update `viewList.tsx` key resolution**

Change key helper to accept field columns.

```ts
const displayMetricKey = (plugin?: string, metric?: string): string =>
  plugin ? `${plugin}${DISPLAY_FIELD_KEY_SEP}${metric}` : (metric ?? '');

const displayFieldValueKey = (plugin?: string, metric?: string, field?: string): string =>
  `field${DISPLAY_FIELD_KEY_SEP}${plugin || ''}${DISPLAY_FIELD_KEY_SEP}${metric || ''}${DISPLAY_FIELD_KEY_SEP}${field || ''}`;
```

In `resolveCell`, use field key when `col.type === 'field'`, and return the plain label string.

- [ ] **Step 3: Render field columns as text**

Before progress/enum rendering, if column type is `field`, return a simple column definition:

```tsx
return {
  title: col.name,
  dataIndex: dataKey,
  key: dataKey,
  onCell: () => ({ style: { minWidth: 150 } }),
  render: (_: unknown, record: TableDataItem) => (
    <EllipsisWithTooltip
      text={String(resolveCell(record, col).value || '--')}
      className="w-full overflow-hidden text-ellipsis whitespace-nowrap"
    />
  )
};
```

- [ ] **Step 4: Update hive metric derivation**

Filter field columns out when deriving metric value candidates:

```ts
const metricNames = new Set(
  (target?.display_fields || [])
    .filter((col) => col.type !== 'field')
    .flatMap((col) => (col.metrics || []).map((binding) => binding.metric))
);
```

- [ ] **Step 5: Run frontend checks**

Run: `cd web && pnpm lint && pnpm type-check`

Expected: PASS or unrelated existing errors documented.

## Task 5: Storybook Visual Companion

**Files:**
- Create: `web/src/stories/monitor-object-display-fields-modal.stories.tsx`

- [ ] **Step 1: Create Storybook mock component**

Create a story that renders a compact, realistic mock of the modal states using Ant Design controls. Include stories for existing metric columns, added field columns, field picker with results, empty field picker, and mixed column order.

```tsx
import type { Meta, StoryObj } from '@storybook/nextjs';
import { Button, Input, Modal, Radio, Select, Tag } from 'antd';
import { SearchOutlined, PlusOutlined } from '@ant-design/icons';

const DisplayFieldsModalMock = ({ state }: { state: 'metric' | 'field' | 'picker' | 'empty' | 'mixed' }) => {
  const showPicker = state === 'picker' || state === 'empty';
  return (
    <div style={{ width: 900, padding: 24, background: '#fff' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h3>展示指标配置 - 主机</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <Button icon={<PlusOutlined />}>添加指标列</Button>
          <Button icon={<PlusOutlined />}>添加展示列</Button>
        </div>
      </div>
      <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, padding: 12, marginBottom: 12 }}>
        <Tag color="blue">指标列</Tag>
        <Input value="CPU使用率" style={{ width: 700 }} />
      </div>
      {(state !== 'metric') && (
        <div style={{ border: '1px solid #d9d9d9', borderRadius: 6, padding: 12 }}>
          <Tag color="green">展示列</Tag>
          <Input value="采集节点IP" style={{ width: 700 }} />
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 40px', gap: 8, marginTop: 12 }}>
            <Select value="主机（Telegraf）" />
            <Select value="node_info" />
            <Input placeholder="请输入维度 key" value={state === 'mixed' ? 'collector_ip' : undefined} />
            <Button icon={<SearchOutlined />} />
          </div>
        </div>
      )}
      <Modal open={showPicker} title="选择字段" footer={null}>
        {state === 'empty' ? '未查询到字段' : <Radio.Group options={['instance_id', 'collector_ip', 'model']} />}
      </Modal>
    </div>
  );
};
```

- [ ] **Step 2: Run Storybook type check through project type-check**

Run: `cd web && pnpm type-check`

Expected: PASS or unrelated existing errors documented.

## Task 6: Final Verification

**Files:**
- All touched files

- [ ] **Step 1: Run targeted backend tests**

Run: `cd server && pytest apps/monitor/tests/test_display_fields_metric_union.py -q`

Expected: PASS.

- [ ] **Step 2: Run frontend gates**

Run: `cd web && pnpm lint && pnpm type-check`

Expected: PASS.

- [ ] **Step 3: Inspect final diff**

Run: `git diff --check && git diff --stat`

Expected: no whitespace errors; diff only includes monitor object field display column implementation, plan, and Storybook.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add server/apps/monitor/utils/display_fields.py \
  server/apps/monitor/utils/display_fields_metrics.py \
  server/apps/monitor/services/monitor_object.py \
  server/apps/monitor/views/monitor_metrics.py \
  server/apps/monitor/tests/test_display_fields_metric_union.py \
  web/src/app/monitor/(pages)/integration/object/types.ts \
  web/src/app/monitor/(pages)/integration/object/api.ts \
  web/src/app/monitor/(pages)/integration/object/displayFieldsModal.tsx \
  web/src/app/monitor/(pages)/view/viewList.tsx \
  web/src/app/monitor/(pages)/view/viewHive.tsx \
  web/src/app/monitor/types/index.ts \
  web/src/app/monitor/locales/zh.json \
  web/src/app/monitor/locales/en.json \
  web/src/stories/monitor-object-display-fields-modal.stories.tsx \
  docs/superpowers/plans/2026-06-30-monitor-object-field-display-columns.md
git commit -m "feat(monitor): 支持对象字段展示列"
```

Expected: commit succeeds.

## Self-Review

- Spec coverage: the plan covers storage compatibility, backend validation, VM-only field lookup, list enrichment, frontend modal changes, list rendering, Storybook, and gates.
- Placeholder scan: no task contains TODO/TBD placeholders; each task includes concrete file paths and implementation snippets.
- Type consistency: backend key format is consistently `field::<plugin>::<metric>::<field>`; frontend helpers use the same separator and prefix.
