# TopN 组件内运行时参数与多排行主体切换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为运营分析 TopN 增加一个组件实例级运行时参数控件，使用户可在同一排行榜内切换排行主体并重新请求数据，同时让云费用分布以 `total_cost` 为数值字段返回标准 TopN 数组。

**Architecture:** 数据源用 `filterType: "widget"` 声明可由组件控制的参数，组件实例用 `runtimeParamControl` 保存参数绑定和选项。`WidgetWrapper` 持有当前实例的选中值并把它加入请求参数与缓存签名，`ComTopN` 只负责渲染 Segmented 和触发回调。`CloudCostService.distribution` 直接返回 `[{ key, total_cost, instance_count, pct }]`，NATS 层只包装成功响应。

**Tech Stack:** Python 3.12、Django 4.2、pytest、Next.js 16、React 19、TypeScript 5、Ant Design 5、pnpm/tsx。

## Global Constraints

- 本计划只实现一个 `runtimeParamControl`；一个 TopN 组件一期只能绑定一个 `widget` 参数。
- `options` 只保存在组件实例配置中，数据源设置页不增加 options 编辑能力。
- 数据源没有 `filterType: "widget"` 参数时，TopN 侧栏的“组件内切换”区域完全不渲染。
- 切换必须重新请求数据源，不在前端聚合、排序或计算占比。
- 云费用 TopN 固定使用 `topNLabelField: "key"` 和 `topNValueField: "total_cost"`；`total_cost`、`instance_count`、`pct` 的 schema 类型均为 `number`。
- `pct` 取值范围为 `0..100`。
- 历史排行榜没有 `runtimeParamControl` 时保持原行为，不迁移旧组件配置。
- 点击切换只更新当前组件内存状态，不写回画布配置，不影响其他组件。
- 所有业务代码变更遵循 TDD：先看到目标测试失败，再写最小实现。
- 当前工作区已有用户的未提交与已暂存改动；实施时只修改本计划列出的文件，不覆盖、不清理其他改动。
- 未经用户明确授权，不执行 `git add`、`git commit`、push 或创建 PR；每个任务末尾只做 diff 审查检查点。

---

## File Structure

### 新建文件

- `web/src/app/ops-analysis/utils/runtimeParamControl.ts`：运行时参数候选项、配置校验、默认值解析和请求白名单纯函数。
- `web/src/app/ops-analysis/components/widgetConfig/sections/runtimeParamControlEditor.tsx`：TopN 侧栏中的启用开关、参数选择、选项编辑和默认项表单。
- `web/scripts/ops-analysis-topn-runtime-param-test.ts`：无需浏览器的 TypeScript 合约测试，覆盖纯函数、提交配置和跨画布透传。

### 修改文件

- `server/apps/cmdb/services/cloud_cost/service.py`：`distribution` 直接返回标准 TopN 行数组和 JSON number 兼容数值。
- `server/apps/cmdb/nats/nats.py`：费用分布 NATS handler 透传数组，不再解包 `groups`。
- `server/apps/cmdb/tests/cloud_cost/test_distribution.py`：锁定三个分组维度、数组结构、类型、排序、占比和非法参数。
- `server/apps/cmdb/tests/cloud_cost/test_three_widget_consistency.py`：按新数组结构校验三组件总费用一致。
- `server/apps/operation_analysis/support-files/source_api.json`：将 `group_by` 改为 `widget`，将费用字段 schema 改为 number。
- `server/apps/operation_analysis/migrations/0018_set_cloud_cost_distribution_field_schema.py`：同步已有内置数据源的 params 和 field schema。该迁移目前尚未发布，直接在现有 0018 中完成最终契约。
- `server/apps/operation_analysis/tests/test_management_commands.py`：验证初始化后的云费用分布数据源契约。
- `web/src/app/ops-analysis/types/dataSource.ts`：增加参数用途联合类型中的 `widget`。
- `web/src/app/ops-analysis/types/dashBoard.ts`：声明 `RuntimeParamOption`、`RuntimeParamControl` 和 `ValueConfig.runtimeParamControl`。
- `web/src/app/ops-analysis/types/topology.ts`：在共享表单类型中透传 `runtimeParamControl`。
- `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx`：参数用途下拉增加 `widget`。
- `web/src/app/ops-analysis/components/widgetConfig/sections/topNSettingsSection.tsx`：挂载运行时参数编辑器。
- `web/src/app/ops-analysis/components/widgetConfig/utils/submitConfig.ts`：验证并持久化 TopN 运行时控件，删除仅供表单使用的开关字段。
- `web/src/app/ops-analysis/components/widgetConfig.tsx`：加载、初始化、切换数据源时清理配置，并向 TopN section 传入 form。
- `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx`：显式复制 `runtimeParamControl`。
- `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`：拓扑配置复制时保留该字段。
- `web/src/app/ops-analysis/utils/widgetDataTransform.ts`：复用现有 `extraParams` 最高优先级，并由测试锁定运行时参数进入请求与签名。
- `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`：持有实例级选中值、构造请求扩展参数、保留切换加载和错误态控件。
- `web/src/app/ops-analysis/components/widgetRenderer.tsx`：把运行时值、变更回调和错误信息传给 TopN。
- `web/src/app/ops-analysis/components/widgets/comTopN.tsx`：渲染 Segmented，保持加载/空态/错误态下的顶部控件。
- `web/src/app/ops-analysis/locales/zh.json`、`en.json`：增加参数用途和 TopN 侧栏文案。
- `web/package.json`：增加定向合约测试命令。

---

### Task 1: 将云费用分布收敛为标准 TopN 数组

**Files:**
- Modify: `server/apps/cmdb/tests/cloud_cost/test_distribution.py`
- Modify: `server/apps/cmdb/tests/cloud_cost/test_three_widget_consistency.py`
- Modify: `server/apps/cmdb/services/cloud_cost/service.py:105-158`
- Modify: `server/apps/cmdb/nats/nats.py:1521-1534`

**Interfaces:**
- Consumes: `CloudCostService._GROUP_FIELD` 和现有 ORM 查询函数。
- Produces: `CloudCostService.distribution(...) -> list[dict[str, str | int | float]]`，行字段固定为 `key`、`total_cost`、`instance_count`、`pct`。

- [ ] **Step 1: 先把 Service 测试改成新契约**

在 `test_distribution.py` 中不再读取 `result["groups"]`，直接断言数组，并锁定数值类型：

```python
def _rows_by_key(result):
    assert isinstance(result, list)
    return {row["key"]: row for row in result}


def test_distribution_by_instance_type(stub_orm):
    result = CloudCostService.distribution(
        stub_orm["user_info"], group_by="instance_type"
    )
    rows = _rows_by_key(result)
    assert rows["database"]["total_cost"] == 600.0
    assert rows["database"]["instance_count"] == 2
    assert rows["cache"]["total_cost"] == 300.0
    assert rows["compute"]["total_cost"] == 300.0
    assert isinstance(rows["database"]["total_cost"], float)
    assert isinstance(rows["database"]["instance_count"], int)
    assert isinstance(rows["database"]["pct"], float)
```

部门、申请人、占比和排序测试使用同一个 `_rows_by_key`；占比求和使用 `sum(row["pct"] for row in result)`，期望与 `100.0` 的差小于 `0.01`。

同文件从 `apps.cmdb.nats.nats` 导入 `get_cloud_resource_cost_distribution`，再增加 NATS 透传测试：

```python
def test_nats_distribution_returns_standard_rows(monkeypatch):
    rows = [
        {"key": "database", "total_cost": 600.0,
         "instance_count": 2, "pct": 50.0},
    ]
    monkeypatch.setattr(
        CloudCostService,
        "distribution",
        staticmethod(lambda *args, **kwargs: rows),
    )

    result = get_cloud_resource_cost_distribution(
        user_info={"team": 1},
        group_by="instance_type",
    )

    assert result == {"result": True, "data": rows, "message": ""}
```

- [ ] **Step 2: 把三组件一致性测试改成数组求和**

```python
d_total = sum(
    (Decimal(str(row["total_cost"])) for row in d),
    Decimal("0"),
)
```

同时把模块注释中的 `distribution.groups[]` 改为 `distribution[]`。

- [ ] **Step 3: 运行定向测试并确认按旧结构失败**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/cloud_cost/test_distribution.py apps/cmdb/tests/cloud_cost/test_three_widget_consistency.py -q
```

Expected: FAIL，Service 返回值仍是 dict；NATS 透传测试会因旧代码执行 `data["groups"]` 而失败。

- [ ] **Step 4: 最小修改 `CloudCostService.distribution`**

保留 Decimal 聚合和排序，只修改行值及最终返回：

```python
groups.append({
    "key": str(key),
    "total_cost": float(total.quantize(_TWO)),
    "instance_count": len(group_insts[key]),
    "pct": float(pct),
})
groups.sort(key=lambda row: row["total_cost"], reverse=True)
return groups
```

同步把 docstring 返回类型改为：

```python
Returns:
    [{"key": str, "total_cost": float,
      "instance_count": int, "pct": float}]
```

- [ ] **Step 5: 让 NATS handler 原样透传数组**

删除 `data["groups"] = ...`，最终保持：

```python
data = CloudCostService.distribution(
    user_info or {},
    inst_type=kwargs.get("inst_type"),
    user_department=kwargs.get("department"),
    applying_user=kwargs.get("applying_user"),
    billing_period=_parse_billing_period(kwargs.get("billing_period")),
    group_by=kwargs.get("group_by", "instance_type"),
)
return {"result": True, "data": data, "message": ""}
```

- [ ] **Step 6: 重新运行云费用测试**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/cloud_cost/test_distribution.py apps/cmdb/tests/cloud_cost/test_three_widget_consistency.py apps/cmdb/tests/cloud_cost/test_parse_billing_period.py -q
```

Expected: PASS。

- [ ] **Step 7: Review checkpoint（不暂存、不提交）**

检查 diff 只包含数组结构、数值类型、NATS 透传及相应测试，不改 summary 和 bill detail 的返回契约。

---

### Task 2: 对齐云费用数据源声明与数值字段 schema

**Files:**
- Modify: `server/apps/operation_analysis/tests/test_management_commands.py`
- Modify: `server/apps/operation_analysis/support-files/source_api.json:440-460`
- Modify: `server/apps/operation_analysis/migrations/0018_set_cloud_cost_distribution_field_schema.py`

**Interfaces:**
- Consumes: 内置数据源初始化命令 `init_source_api_data`。
- Produces: `group_by.filterType === "widget"`，以及 `total_cost`、`instance_count`、`pct` 均可作为 number schema 字段，其中 TopN 主数值字段选择 `total_cost`。

- [ ] **Step 1: 添加内置数据源初始化失败测试**

在 `test_management_commands.py` 的 `init_source_api_data` 测试段新增：

```python
@pytest.mark.django_db
def test_init_source_api_data_creates_cloud_cost_distribution_contract(settings):
    settings.NATS_SERVERS = "nats://admin:secret@127.0.0.1:4222"
    call_command("init_default_namespace")
    call_command("init_source_api_data")

    source = DataSourceAPIModel.objects.get(
        rest_api="cmdb/get_cloud_resource_cost_distribution"
    )
    params = {item["name"]: item for item in source.params}
    fields = {item["key"]: item for item in source.field_schema}

    assert source.chart_type == ["topN"]
    assert params["group_by"]["filterType"] == "widget"
    assert params["group_by"]["value"] == "instance_type"
    assert fields["key"]["value_type"] == "string"
    assert fields["total_cost"]["value_type"] == "number"
    assert fields["instance_count"]["value_type"] == "number"
    assert fields["pct"]["value_type"] == "number"
```

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_management_commands.py::test_init_source_api_data_creates_cloud_cost_distribution_contract -q
```

Expected: FAIL，当前 `group_by` 为 `params`，`total_cost` / `pct` 为 `string`。

- [ ] **Step 3: 修改 `source_api.json`**

目标片段固定为：

```json
{"name": "group_by", "type": "string", "value": "instance_type", "alias_name": "排行主体", "filterType": "widget"}
```

字段类型固定为：

```json
{"key": "total_cost", "title": "费用合计(元)", "value_type": "number", "description": "该分组窗口内 total_cost SUM"}
{"key": "instance_count", "title": "实例数", "value_type": "number", "description": "该分组下关联的 bill 数"}
{"key": "pct", "title": "占比(%)", "value_type": "number", "description": "该分组 total_cost 占全局的百分比"}
```

- [ ] **Step 4: 扩展未发布的 0018 数据迁移**

把 0018 的正向函数改为同时更新 `field_schema` 和 `params`：

```python
params = [dict(item) for item in (target.params or [])]
found_group_by = False
for item in params:
    if item.get("name") == "group_by":
        found_group_by = True
        item.update({
            "alias_name": "排行主体",
            "type": "string",
            "value": "instance_type",
            "filterType": "widget",
        })

if not found_group_by:
    params.append({
        "name": "group_by",
        "alias_name": "排行主体",
        "type": "string",
        "value": "instance_type",
        "filterType": "widget",
    })

target.params = params
target.field_schema = _DISTRIBUTION_FIELD_SCHEMA
target.save(update_fields=["params", "field_schema", "updated_at"])
```

同步更新迁移注释，去掉 `groups[i]` 和 string schema 的旧描述。反向仍保持 no-op，避免回滚后 TopN 再次失去字段。

- [ ] **Step 5: 运行初始化与迁移检查**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_management_commands.py::test_init_source_api_data_creates_cloud_cost_distribution_contract -q
cd server && uv run python manage.py makemigrations --check --dry-run
```

Expected: 测试 PASS；迁移检查输出 `No changes detected`。

- [ ] **Step 6: Review checkpoint（不暂存、不提交）**

确认 `total_cost` 已是 number，且没有把 options 写入数据源 params。

---

### Task 3: 建立通用运行时参数类型与纯函数边界

**Files:**
- Create: `web/src/app/ops-analysis/utils/runtimeParamControl.ts`
- Create: `web/scripts/ops-analysis-topn-runtime-param-test.ts`
- Modify: `web/src/app/ops-analysis/types/dataSource.ts:85-95`
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts:89-117`
- Modify: `web/src/app/ops-analysis/types/topology.ts:321-360`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `RuntimeParamControl`、`getWidgetRuntimeParamCandidates`、`validateRuntimeParamControl`、`resolveRuntimeParamInitialValue`、`buildWidgetRuntimeParams`。
- Consumers: Task 4 的侧栏提交和 Task 5 的 `WidgetWrapper`。

- [ ] **Step 1: 先创建纯函数合约测试脚本**

创建 `web/scripts/ops-analysis-topn-runtime-param-test.ts`，首批断言：

```ts
import assert from 'node:assert/strict';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';
import {
  buildWidgetRuntimeParams,
  getWidgetRuntimeParamCandidates,
  resolveRuntimeParamInitialValue,
  validateRuntimeParamControl,
} from '../src/app/ops-analysis/utils/runtimeParamControl';

const sourceParams: ParamItem[] = [
  { name: 'department', alias_name: '部门', type: 'string', value: '', filterType: 'filter' },
  { name: 'group_by', alias_name: '排行主体', type: 'string', value: 'instance_type', filterType: 'widget' },
];
const control = {
  paramName: 'group_by',
  controlType: 'segmented' as const,
  defaultValue: 'department',
  options: [
    { label: '对象类型', value: 'instance_type' },
    { label: '使用部门', value: 'department' },
  ],
};

assert.deepEqual(getWidgetRuntimeParamCandidates(sourceParams).map(item => item.name), ['group_by']);
assert.equal(validateRuntimeParamControl(control, sourceParams), null);
assert.equal(resolveRuntimeParamInitialValue(control, sourceParams), 'department');
assert.deepEqual(buildWidgetRuntimeParams(control, 'instance_type', sourceParams), { group_by: 'instance_type' });
assert.deepEqual(buildWidgetRuntimeParams({ ...control, paramName: 'unknown' }, 'department', sourceParams), {});
assert.equal(validateRuntimeParamControl({ ...control, options: [] }, sourceParams), 'emptyOptions');
assert.equal(validateRuntimeParamControl({ ...control, defaultValue: 'user' }, sourceParams), 'invalidDefault');

console.log('ops analysis TopN runtime parameter tests passed');
```

- [ ] **Step 2: 增加 package 命令并确认失败**

在 `web/package.json` scripts 增加：

```json
"test:ops-analysis-topn-runtime-param": "pnpm exec tsx scripts/ops-analysis-topn-runtime-param-test.ts"
```

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
```

Expected: FAIL，提示 `runtimeParamControl` 模块不存在。

- [ ] **Step 3: 增加类型定义**

在 `types/dataSource.ts` 增加：

```ts
export type DataSourceParamFilterType = 'filter' | 'fixed' | 'params' | 'widget';
```

并把 `ParamItem.filterType?: string` 改成 `filterType?: DataSourceParamFilterType`。

在 `types/dashBoard.ts` 增加：

```ts
export type RuntimeParamValue = string | number;

export interface RuntimeParamOption {
  label: string;
  value: RuntimeParamValue;
}

export interface RuntimeParamControl {
  paramName: string;
  controlType: 'segmented';
  defaultValue: RuntimeParamValue;
  options: RuntimeParamOption[];
}
```

并在 `ValueConfig` 增加：

```ts
runtimeParamControl?: RuntimeParamControl;
```

`types/topology.ts` 从 `dashBoard.ts` 导入 `RuntimeParamControl`，在 `ViewConfigFormValues` 和 `NodeConfigFormValues` 中增加同名可选字段，不复制新的结构定义。

- [ ] **Step 4: 实现纯函数模块**

`runtimeParamControl.ts` 对外导出以下行为：

```ts
export type RuntimeParamControlError =
  | 'missingParam'
  | 'emptyOptions'
  | 'emptyLabel'
  | 'emptyValue'
  | 'duplicateValue'
  | 'invalidDefault';

export const getWidgetRuntimeParamCandidates = (params: ParamItem[] = []) =>
  params.filter((item) => item.filterType === 'widget' && item.name.trim());

const valueKey = (value: RuntimeParamValue) => `${typeof value}:${String(value)}`;

export const validateRuntimeParamControl = (
  control: RuntimeParamControl | undefined,
  params: ParamItem[] = [],
): RuntimeParamControlError | null => {
  if (!control || !getWidgetRuntimeParamCandidates(params).some(item => item.name === control.paramName)) return 'missingParam';
  if (!control.options.length) return 'emptyOptions';
  if (control.options.some(item => !item.label.trim())) return 'emptyLabel';
  if (control.options.some(item => typeof item.value === 'string' ? !item.value.trim() : !Number.isFinite(item.value))) return 'emptyValue';
  const keys = control.options.map(item => valueKey(item.value));
  if (new Set(keys).size !== keys.length) return 'duplicateValue';
  if (!keys.includes(valueKey(control.defaultValue))) return 'invalidDefault';
  return null;
};
```

`resolveRuntimeParamInitialValue` 的优先级必须是：合法组件默认值 → 命中 options 的数据源默认值 → 第一项；只有参数不存在、选项为空或选项本身非法时才返回 `undefined`。`buildWidgetRuntimeParams` 只有在参数仍是 `widget` 且 activeValue 命中 options 时才返回 `{ [paramName]: activeValue }`，否则返回 `{}`。

- [ ] **Step 5: 运行纯函数测试和类型检查**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
cd web && pnpm type-check
```

Expected: PASS。

- [ ] **Step 6: Review checkpoint（不暂存、不提交）**

确认纯函数不依赖 React/AntD，其他组件未来可复用；确认 `1` 与 `"1"` 按不同 option value 处理。

---

### Task 4: 实现 TopN 侧栏配置和跨画布持久化

**Files:**
- Create: `web/src/app/ops-analysis/components/widgetConfig/sections/runtimeParamControlEditor.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx:100-104`
- Modify: `web/src/app/ops-analysis/components/widgetConfig/sections/topNSettingsSection.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetConfig/utils/submitConfig.ts:15-40, 51-53, 257-260`
- Modify: `web/src/app/ops-analysis/components/widgetConfig.tsx:249-326, 667-707, 767-790, 1132-1140`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx:574-587, 941-954`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts:188-233`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Modify: `web/scripts/ops-analysis-topn-runtime-param-test.ts`

**Interfaces:**
- Consumes: Task 3 的类型和 `validateRuntimeParamControl` / `getWidgetRuntimeParamCandidates`。
- Produces: 持久化的 `ValueConfig.runtimeParamControl`，不持久化临时开关 `runtimeParamControlEnabled`。

- [ ] **Step 1: 扩展合约测试，先锁定提交和透传**

在测试脚本中构造 `buildWidgetSubmitConfig` 的完整输入，断言：

```ts
const submitResult = buildWidgetSubmitConfig({
  values: {
    name: '费用分布',
    chartType: 'topN',
    dataSource: 34,
    dataSourceParams: sourceParams,
    topNLabelField: 'key',
    topNValueField: 'total_cost',
    runtimeParamControlEnabled: true,
    runtimeParamControl: control,
  },
  chartType: 'topN',
  showChartThemeMode: false,
  showTableFilterFields: false,
  selectedFields: [],
  thresholdColors: [],
  filterBindings: {},
  displayColumns: [],
  filterFields: [],
  actions: [],
});
assert.deepEqual(submitResult.config?.runtimeParamControl, control);
assert.equal('runtimeParamControlEnabled' in (submitResult.config || {}), false);
assert.equal(submitResult.config?.topNValueField, 'total_cost');
```

再调用 Screen 的 `addConfiguredScreenWidget` 和 Topology 的 `buildValueConfig`，断言两者输出仍包含同一个 `runtimeParamControl`。

- [ ] **Step 2: 运行脚本并确认提交/透传断言失败**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
```

Expected: FAIL，`WidgetConfigFormValues` 尚无临时开关，Topology 显式复制也尚未透传。

- [ ] **Step 3: 数据源设置页增加参数用途**

`paramTable.tsx` 的 `filterTypeOptions` 增加：

```ts
{ label: t('dataSource.filterTypes.widget'), value: 'widget' }
```

locale 增加：

```json
// zh
"widget": "组件内交互"

// en
"widget": "Widget Interaction"
```

不修改 `normalizeParams` 的字段结构，不增加 options 表单。

- [ ] **Step 4: 创建独立侧栏编辑器**

`RuntimeParamControlEditor` 接口固定为：

```ts
interface RuntimeParamControlEditorProps {
  form: FormInstance<WidgetConfigFormValues>;
  selectedDataSource?: DatasourceItem;
  t: (key: string) => string;
}
```

核心渲染规则：

```tsx
const candidates = getWidgetRuntimeParamCandidates(selectedDataSource?.params || []);
if (candidates.length === 0) return null;

const enabled = Form.useWatch('runtimeParamControlEnabled', form);
```

组件先渲染 `Switch`。启用时：

- `Select` 绑定 `['runtimeParamControl', 'paramName']`，options 来自 candidates。
- 隐藏字段把 `controlType` 固定写为 `segmented`。
- `Form.List name={['runtimeParamControl', 'options']}` 每行渲染 label、value、删除按钮和上下移动按钮。
- 默认项 Select 绑定 `['runtimeParamControl', 'defaultValue']`，候选项实时来自已填 options。
- 新增行初始值为 `{ label: '', value: '' }`。
- 开启且只有一个候选参数时自动写入该 paramName；关闭时把 `runtimeParamControl` 设为 `undefined`。

不要在该组件维护第二份 options React state，始终以 AntD Form 为事实来源。

- [ ] **Step 5: 将编辑器挂到 TopN section**

`TopNSettingsSectionProps` 增加 `form`，在既有名称字段和数值字段后渲染：

```tsx
<RuntimeParamControlEditor
  form={form}
  selectedDataSource={selectedDataSource}
  t={t}
/>
```

`widgetConfig.tsx` 调用处传入当前 `form`。

- [ ] **Step 6: 加载、切换和提交配置**

`WidgetConfigFormValues` 增加：

```ts
runtimeParamControlEnabled?: boolean;
runtimeParamControl?: RuntimeParamControl;
```

加载旧组件时：

```ts
formValues.runtimeParamControl = valueConfig?.runtimeParamControl;
formValues.runtimeParamControlEnabled = Boolean(valueConfig?.runtimeParamControl);
```

切换数据源或切换到 scene widget 时，两字段都清空。提交时先执行：

```ts
delete (result as WidgetConfig & { runtimeParamControlEnabled?: boolean })
  .runtimeParamControlEnabled;
```

TopN 启用控件时调用 `validateRuntimeParamControl`；失败返回新的 `WidgetSubmitError = 'invalidRuntimeParamControl'`，由 `widgetConfig.tsx` 显示 `dashboard.runtimeParamControlInvalid`。未启用或非 TopN 时删除 `result.runtimeParamControl`。

- [ ] **Step 7: 补齐 Dashboard/Topology 显式字段复制**

Dashboard 两处与 `topNValueField` 相邻增加：

```ts
runtimeParamControl: config.runtimeParamControl,
```

以及：

```ts
runtimeParamControl: values.runtimeParamControl,
```

Topology 的 `buildValueConfig` 在 `chartType === 'topN'` 分支增加：

```ts
valueConfig.runtimeParamControl = values.runtimeParamControl;
```

Screen 已通过 `...values` / `...item.valueConfig` 透传，不增加重复映射，只用脚本断言保护。

- [ ] **Step 8: 增加中英文侧栏文案**

在 `dashboard` locale 下增加对应键：

```json
"runtimeParamControl": "组件内切换",
"runtimeParamControlEnabled": "启用切换",
"runtimeParamName": "绑定参数",
"runtimeParamOptions": "切换选项",
"runtimeParamOptionLabel": "显示名称",
"runtimeParamOptionValue": "参数值",
"runtimeParamDefault": "默认项",
"runtimeParamAddOption": "添加选项",
"runtimeParamControlInvalid": "请完整配置组件内切换参数、选项和默认项"
```

英文分别使用 `Widget Switch`、`Enable Switch`、`Parameter`、`Options`、`Label`、`Value`、`Default Option`、`Add Option`、`Complete the widget switch parameter, options, and default option`。

- [ ] **Step 9: 运行合约测试与类型检查**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
cd web && pnpm type-check
```

Expected: PASS。

- [ ] **Step 10: Review checkpoint（不暂存、不提交）**

检查无 `widget` 参数的数据源不会渲染编辑区域；确认 options 只存在于 `runtimeParamControl`，没有写回 `ParamItem.options`。

---

### Task 5: 在 WidgetWrapper 中加入实例级状态和请求覆盖

**Files:**
- Modify: `web/scripts/ops-analysis-topn-runtime-param-test.ts`
- Modify: `web/src/app/ops-analysis/utils/widgetDataTransform.ts:213-291`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx:205-690`
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`

**Interfaces:**
- Consumes: `resolveRuntimeParamInitialValue`、`buildWidgetRuntimeParams`。
- Produces: `buildWidgetExtraParams`，以及 `runtimeParamValue?: RuntimeParamValue`、`onRuntimeParamChange?: (value: RuntimeParamValue) => void`、`errorMessage?: string` 三个渲染属性。

- [ ] **Step 1: 扩展请求参数和签名失败测试**

在脚本中先导入尚不存在的 `buildWidgetExtraParams`，再增加：

```ts
const runtimeParams = buildWidgetRuntimeParams(control, 'department', sourceParams);
const requestConfig = { dataSource: 34, dataSourceParams: sourceParams };
const extraParams = buildWidgetExtraParams({
  namespaceId: 7,
  isTableLikeChart: false,
  tableQueryParams: { page: 3, page_size: 20 },
  runtimeParams,
});

assert.deepEqual(extraParams, {
  namespace_id: 7,
  group_by: 'department',
});

assert.equal(buildWidgetRequestParams({
  config: requestConfig,
  dataSource: { params: sourceParams },
  extraParams,
}).group_by, 'department');

assert.equal(buildWidgetRequestSignatureParams({
  config: requestConfig,
  dataSource: { params: sourceParams },
  extraParams,
}).group_by, 'department');
```

再断言 `isTableLikeChart: true` 时包含 table query，且即便 table query 中意外带有旧 `group_by`，最终仍由 `runtimeParams.group_by` 覆盖。active value 为 `user` 且不在 options 中时，`buildWidgetRuntimeParams` 必须返回 `{}`。

- [ ] **Step 2: 运行脚本确认新增边界失败或通过现有覆盖逻辑**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
```

Expected: FAIL，提示 `buildWidgetExtraParams` 尚未导出。

- [ ] **Step 3: 在 `WidgetWrapper` 初始化实例级状态**

增加：

```ts
const effectiveSourceParams = useMemo(
  () => config?.dataSourceParams?.length
    ? config.dataSourceParams
    : (dataSource?.params || []),
  [config?.dataSourceParams, dataSource?.params],
);
const [runtimeParamValue, setRuntimeParamValue] = useState<RuntimeParamValue>();

useEffect(() => {
  setRuntimeParamValue(resolveRuntimeParamInitialValue(
    config?.runtimeParamControl,
    effectiveSourceParams,
  ));
}, [config?.runtimeParamControl, effectiveSourceParams]);
```

每个 `WidgetWrapper` 自己持有 state，禁止提升到 Dashboard context。

- [ ] **Step 4: 构造唯一的请求扩展参数对象**

先在 `widgetDataTransform.ts` 增加纯函数：

```ts
export const buildWidgetExtraParams = ({
  namespaceId,
  isTableLikeChart,
  tableQueryParams,
  runtimeParams,
}: {
  namespaceId?: number;
  isTableLikeChart: boolean;
  tableQueryParams: Record<string, unknown>;
  runtimeParams: Record<string, unknown>;
}) => ({
  ...(namespaceId !== undefined ? { namespace_id: namespaceId } : {}),
  ...(isTableLikeChart ? tableQueryParams : {}),
  ...runtimeParams,
});
```

随后用一个 `requestExtraParams` 替代 request params、signature 和 `fetchCompareData` 中三份重复对象：

```ts
const runtimeParams = useMemo(
  () => buildWidgetRuntimeParams(
    config?.runtimeParamControl,
    runtimeParamValue,
    effectiveSourceParams,
  ),
  [config?.runtimeParamControl, runtimeParamValue, effectiveSourceParams],
);

const requestExtraParams = useMemo(() => buildWidgetExtraParams({
  namespaceId: widgetUsesNamespace ? effectiveNamespaceId : undefined,
  isTableLikeChart,
  tableQueryParams,
  runtimeParams,
}), [widgetUsesNamespace, effectiveNamespaceId, isTableLikeChart, tableQueryParams, runtimeParams]);
```

将它传给 `buildWidgetRequestParams`、`buildWidgetRequestSignatureParams` 和 `fetchCompareData`。这样 `group_by` 同时进入实际请求和缓存签名。

- [ ] **Step 5: 保留二次加载和错误态中的 TopN 外壳**

把非表格全屏 Spin 条件收窄为首次加载：

```ts
const isInitialNonTableLoading = loading && !isTableLikeChart && !hasRawPayload;
if (isInitialNonTableLoading || isWaitingForInitialData) {
  return <div className="h-full flex items-center justify-center"><Spin spinning /></div>;
}
```

定义 `hasActiveRuntimeControl = chartType === 'topN' && runtimeParamValue !== undefined`。只有它为 true 时，数据校验或请求错误不在 Wrapper 提前 return，而是把错误文本传入 TopN；无效历史配置和其他图表保持现有全局错误态。

- [ ] **Step 6: 扩展 WidgetRenderer props**

```ts
runtimeParamValue?: RuntimeParamValue;
onRuntimeParamChange?: (value: RuntimeParamValue) => void;
errorMessage?: string;
```

`WidgetWrapper` 传入当前值和 `setRuntimeParamValue`；`WidgetRenderer` 原样传给注册组件。未使用这些 props 的其他图表不改变行为。

- [ ] **Step 7: 运行合约测试和类型检查**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
cd web && pnpm type-check
```

Expected: PASS。

- [ ] **Step 8: Review checkpoint（不暂存、不提交）**

确认 runtime value 不进入 `ValueConfig`，确认两个 WidgetWrapper 不共享 state，确认 `requestSignature` 的 JSON 中包含当前 `group_by`。

---

### Task 6: 渲染 TopN 切换控件并保持加载/空态/错误态

**Files:**
- Modify: `web/src/app/ops-analysis/components/widgets/comTopN.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/widgetShowcase.stories.tsx`
- Modify: `web/scripts/ops-analysis-topn-runtime-param-test.ts`

**Interfaces:**
- Consumes: Task 5 传入的 `runtimeParamValue`、`onRuntimeParamChange`、`errorMessage`。
- Produces: 始终可见的 TopN Segmented 控件和独立内容状态。

- [ ] **Step 1: 给 TopN 视图模型补纯函数断言**

在 `runtimeParamControl.ts` 增加并在脚本中测试：

```ts
export const getRuntimeParamSegmentedOptions = (
  control?: RuntimeParamControl,
) => (control?.options || []).map(item => ({
  label: item.label,
  value: item.value,
}));
```

断言输出顺序与配置 options 顺序完全一致，空配置返回 `[]`。

- [ ] **Step 2: 运行脚本并确认函数缺失失败**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
```

Expected: FAIL，提示导出函数不存在。

- [ ] **Step 3: 扩展 `TopNProps` 并调整布局**

Props 增加：

```ts
runtimeParamValue?: RuntimeParamValue;
onRuntimeParamChange?: (value: RuntimeParamValue) => void;
errorMessage?: string;
```

最外层改成 `flex h-full min-h-0 flex-col`。仅当 options 非空且当前值有效时，在顶部渲染：

```tsx
<div className="shrink-0 overflow-x-auto px-3 pt-2">
  <Segmented
    block
    options={getRuntimeParamSegmentedOptions(config?.runtimeParamControl)}
    value={runtimeParamValue}
    onChange={(value) => onRuntimeParamChange?.(value as RuntimeParamValue)}
  />
</div>
```

内容区使用 `min-h-0 flex-1`。状态优先级固定为：`loading` → `errorMessage` → 空数据 → 排行列表。顶部 Segmented 不进入任何状态分支，因此切换加载、失败和空结果时仍保持可见。

`onReady` 的就绪条件同步收紧为 `!loading && !errorMessage && isDataReady`；错误态和空态回调 `false`，成功行数组回调 `true`。

- [ ] **Step 4: 保持历史 TopN 行为**

当没有合法 `runtimeParamControl` 时不渲染 Segmented；既有 header、名称、数值和进度条算法不改。`topNValueField` 继续从配置读取，因此云费用使用 `total_cost`，历史排行仍可使用 `count`。

- [ ] **Step 5: 增加 Storybook 场景**

在 `widgetShowcase.stories.tsx` 增加 `TopNWithRuntimeDimension`，配置包含三项 options、`topNLabelField: 'key'`、`topNValueField: 'total_cost'`，用本地 state 接收 `onRuntimeParamChange`。Story 用于人工验证长文案横向滚动和不同主题，不模拟后端聚合。

- [ ] **Step 6: 运行测试、类型检查和 Storybook 构建**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
cd web && pnpm type-check
cd web && pnpm build-storybook
```

Expected: 全部 PASS，Storybook 构建无 TopN props 类型错误。

- [ ] **Step 7: Review checkpoint（不暂存、不提交）**

确认 `instance_count` 没有被硬编码为数值字段；确认 Segmented 顺序、当前值和回调值均来自组件配置。

---

### Task 7: 全链路回归与手工验收

**Files:**
- Verify only: 本计划涉及的全部文件
- No new production file

**Interfaces:**
- Consumes: Task 1—6 的完整实现。
- Produces: 可交付的测试证据和未提交 diff。

- [ ] **Step 1: 运行云费用完整测试组**

Run:

```bash
cd server && uv run pytest apps/cmdb/tests/cloud_cost -q
```

Expected: PASS；三组件费用一致性仍成立。

- [ ] **Step 2: 运行运营分析数据源相关回归**

Run:

```bash
cd server && uv run pytest apps/operation_analysis/tests/test_management_commands.py apps/operation_analysis/tests/test_datasource_view.py apps/operation_analysis/tests/test_datasource_filters_serializers.py -q
```

Expected: PASS；`widget` 参数仍受已声明参数白名单保护。

- [ ] **Step 3: 运行前端定向测试和质量门禁**

Run:

```bash
cd web && pnpm test:ops-analysis-topn-runtime-param
cd web && pnpm lint
cd web && pnpm type-check
```

Expected: PASS。

- [ ] **Step 4: 验证数据源配置页**

手工步骤：

1. 打开“运营分析 → 设置 → 数据源”。
2. 编辑云资源费用分布数据源。
3. 确认 `group_by` 的参数用途显示“组件内交互”。
4. 确认页面没有 options 编辑列或 options 弹窗。
5. 保存并重新打开，确认 `filterType: widget` 未丢失。

- [ ] **Step 5: 验证 TopN 配置侧栏**

手工步骤：

1. 新增云资源费用分布 TopN。
2. 确认名称字段可选 `key`。
3. 确认数值字段可选并选择 `total_cost`；不得因为 schema 是 string 而只显示 `instance_count`。
4. 启用组件内切换，绑定 `group_by`。
5. 配置“对象类型/instance_type、使用部门/department、申请人/user”，默认项选“对象类型”。
6. 保存、重新打开侧栏，确认配置和顺序未丢失。
7. 切换到一个没有 `widget` 参数的数据源，确认整个组件内切换区域消失。

- [ ] **Step 6: 验证编辑态、预览态和实例隔离**

手工步骤：

1. 在同一画布放置两个费用分布排行榜。
2. 第一个切换到“使用部门”，第二个保持“对象类型”。
3. 确认两个请求分别携带 `group_by=department` 和 `group_by=instance_type`。
4. 确认第一个排行榜按部门名称和 `total_cost` 重新排序，第二个不变化。
5. 快速点击“申请人 → 对象类型”，确认最终只展示对象类型响应。
6. 模拟请求失败，确认当前切换项仍可见且内容区显示错误。
7. 进入预览态重复切换，行为与编辑态一致。
8. 刷新页面，确认两个组件都回到各自配置的默认项。

- [ ] **Step 7: 检查历史兼容**

加载一个只有 `topNLabelField: "model"`、`topNValueField: "count"` 的历史排行榜，确认：

- 不显示 Segmented。
- 请求参数与改造前一致。
- 名称、数值和进度条正常显示。

- [ ] **Step 8: 最终 diff 审查（不暂存、不提交）**

Run:

```bash
git status --short
git diff --stat
```

确认没有修改计划外业务模块，没有把用户原有 staged changes 混入新的暂存操作，并把测试命令及结果汇报给用户。等待用户明确决定是否需要暂存或提交。

---

## Plan Self-Review

- **Spec coverage:** Task 1 覆盖标准数组与数值类型；Task 2 覆盖 `widget` 声明和 `total_cost:number`；Task 3 覆盖通用协议和白名单；Task 4 覆盖侧栏、校验与历史配置透传；Task 5 覆盖实例状态、重新请求、缓存和竞态；Task 6 覆盖交互与各内容状态；Task 7 覆盖编辑态、预览态、实例隔离和历史兼容。
- **Placeholder scan:** 无 TBD、TODO、“稍后实现”或未指定的测试步骤。
- **Type consistency:** 全计划统一使用 `RuntimeParamValue`、`RuntimeParamOption`、`RuntimeParamControl`、`runtimeParamControl`、`runtimeParamControlEnabled`；请求回调只传 value，参数名从 control 读取。
- **Scope check:** 没有扩展数据源 options、统一筛选、多参数控件或其他图表；Topology 只做字段透传，Screen 只用测试保护既有 spread 行为。
- **Authorization check:** 文档明确禁止在未授权时执行 Git 暂存、提交和远端操作。
