# Historical Superpowers change: 2026-07-16-unified-component-param-switch

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-16-unified-component-param-switch.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the TopN-only `widget`/`RuntimeParamControl` model with a reusable `InputControlConfig.componentSwitch` on one `params + string` parameter per component.

**Architecture:** Component-level parameter overrides remain in `ValueConfig.dataSourceParams`. A focused pure utility owns eligibility, uniqueness, typed option matching, fallback values, and runtime request parameters; a shared option-loading hook supplies both configuration controls and the TopN header control. TopN is the only initial consumer, while the persisted shape stays chart-agnostic.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, pnpm/tsx assertion scripts, Django JSON support-file tests.

## Global Constraints

- Do not create a git commit unless the user explicitly authorizes it; each task ends with an unstaged-diff review checkpoint.
- Only `filterType: 'params'` plus `type: 'string'` parameters are eligible.
- Only `control: 'select' | 'radio'` may carry `componentSwitch?: boolean`.
- A component may enable at most one component-switch parameter.
- Only TopN exposes and consumes the switch in the first release.
- TopN header rendering is `select` -> Ant Design `Select`, `radio` -> Ant Design `Segmented`.
- Invalid values reset silently to the first resolved option; no toast or inline notice is shown.
- Empty, unresolved, or failed option sources preserve the existing value.
- Option equality compares both JavaScript type and value (`'1' !== 1`).
- Leaving TopN clears only `componentSwitch`, preserving control type and option source.
- Unified-filter uses of `ParamInputConfigEditor` never show the component-switch control.
- No database migration and no legacy read-compatibility layer; the single existing data source and component are converted manually.

---

## File Structure

- Create `web/src/app/ops-analysis/utils/componentParamSwitch.ts`: pure eligibility, uniqueness, typed-value reconciliation, and runtime-param helpers.
- Create `web/src/app/ops-analysis/hooks/useParamInputOptions.ts`: shared static/dynamic option loading with request-race protection.
- Create `web/src/app/ops-analysis/components/componentParamSwitchControl.tsx`: TopN header `Select`/`Segmented` renderer.
- Create `web/scripts/ops-analysis-component-param-switch-test.ts`: focused behavioral and source-wiring regression suite.
- Modify `web/src/app/ops-analysis/types/dataSource.ts`: add `componentSwitch`; remove `widget` filter type.
- Modify `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx`: TopN-only switch UI, occupancy state, and resolved-option return.
- Modify `web/src/app/ops-analysis/components/paramInputControl.tsx`: consume shared option hook and expose an opt-in resolved-options callback.
- Modify `web/src/app/ops-analysis/components/paramsConfig.tsx`: reconcile invalid form values after options resolve.
- Modify `web/src/app/ops-analysis/components/widgetConfig.tsx`: enforce one switch, clear on chart change, reconcile on editor confirmation, and persist overrides.
- Modify `web/src/app/ops-analysis/components/widgetConfig/utils/submitConfig.ts`: reject multiple switches and remove legacy runtime fields.
- Modify `web/src/app/ops-analysis/components/widgetDataRenderer.tsx`: resolve header options/value and merge runtime query parameters.
- Modify `web/src/app/ops-analysis/utils/widgetDataTransform.ts`: replace legacy active-runtime detection with generic runtime-param detection.
- Modify TopN renderer files to remove inline legacy interaction props.
- Delete legacy runtime utility/editor/component files after all consumers move.
- Modify Dashboard/Screen/Topology mappings and types to stop copying legacy fields.
- Modify locales, Storybook, package scripts, built-in data, and backend tests to describe only the new model.

---

### Task 1: Define the new data shape and pure switch rules

**Files:**
- Create: `web/src/app/ops-analysis/utils/componentParamSwitch.ts`
- Create: `web/scripts/ops-analysis-component-param-switch-test.ts`
- Modify: `web/src/app/ops-analysis/types/dataSource.ts:85-141`
- Modify: `web/package.json:54`

**Interfaces:**
- Produces: `ComponentSwitchValidation`, `isComponentSwitchCandidate(param)`, `findComponentSwitchParams(params)`, `validateSingleComponentSwitch(params)`, `reconcileParamOptionValue(currentValue, options)`, `clearComponentSwitch(config)`, and `buildComponentSwitchRuntimeParams(param, activeValue)`.
- Consumes: existing `ParamItem`, `InputControlConfig`, and `InputOption`.

- [ ] **Step 1: Write failing type and pure-function assertions**

Create `web/scripts/ops-analysis-component-param-switch-test.ts` with assertions equivalent to:

```ts
import assert from 'node:assert/strict';
import {
  buildComponentSwitchRuntimeParams,
  clearComponentSwitch,
  findComponentSwitchParams,
  reconcileParamOptionValue,
  validateSingleComponentSwitch,
} from '../src/app/ops-analysis/utils/componentParamSwitch';
import type { ParamItem } from '../src/app/ops-analysis/types/dataSource';

const options = [
  { label: 'One string', value: '1' },
  { label: 'One number', value: 1 },
];

assert.deepEqual(reconcileParamOptionValue('1', options), {
  value: '1', changed: false,
});
assert.deepEqual(reconcileParamOptionValue('missing', options), {
  value: '1', changed: true,
});
assert.deepEqual(reconcileParamOptionValue('missing', []), {
  value: 'missing', changed: false,
});
assert.deepEqual(reconcileParamOptionValue(1, options), {
  value: 1, changed: false,
});

const switchParam: ParamItem = {
  name: 'group_by', alias_name: '排行主体', type: 'string',
  filterType: 'params', value: 'instance_type',
  inputConfig: {
    control: 'radio', componentSwitch: true,
    optionsSource: { type: 'static', staticItems: options },
  },
};
assert.deepEqual(findComponentSwitchParams([switchParam]), [switchParam]);
assert.equal(validateSingleComponentSwitch([switchParam]).valid, true);
assert.equal(validateSingleComponentSwitch([switchParam, { ...switchParam, name: 'region' }]).valid, false);
assert.deepEqual(buildComponentSwitchRuntimeParams(switchParam, '1'), { group_by: '1' });
assert.deepEqual(clearComponentSwitch(switchParam.inputConfig), {
  control: 'radio', optionsSource: switchParam.inputConfig.optionsSource,
});
```

Add source assertions that `DataSourceParamFilterType` no longer contains `'widget'` and the select/radio branch contains `componentSwitch?: boolean`.

- [ ] **Step 2: Add the package command and verify failure**

Add:

```json
"test:ops-analysis-component-param-switch": "pnpm exec tsx scripts/ops-analysis-component-param-switch-test.ts"
```

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: FAIL because `componentParamSwitch.ts` and `componentSwitch` do not exist.

- [ ] **Step 3: Implement the discriminated-union field and pure helpers**

Change the option branch to:

```ts
| {
    control: 'select' | 'radio';
    optionsSource: StaticOptionsSource | DynamicOptionsSource;
    componentSwitch?: boolean;
  };
```

Implement typed matching with a key such as:

```ts
const valueKey = (value: string | number) => `${typeof value}:${String(value)}`;
```

Eligibility must require `params`, `string`, `select|radio`, and `componentSwitch === true`. `reconcileParamOptionValue` must return the first option only when a non-empty resolved list excludes the current value.

- [ ] **Step 4: Run the focused test**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: PASS.

- [ ] **Step 5: Review without committing**

Run: `git diff --check; git status --short`

Expected: only Task 1 files changed; do not stage or commit.

---

### Task 2: Centralize static and dynamic option loading

**Files:**
- Create: `web/src/app/ops-analysis/hooks/useParamInputOptions.ts`
- Modify: `web/src/app/ops-analysis/components/paramInputControl.tsx:1-130`
- Modify: `web/scripts/param-input-config-utils-test.ts`
- Modify: `web/scripts/ops-analysis-component-param-switch-test.ts`

**Interfaces:**
- Produces: `useParamInputOptions(inputConfig): { status: 'idle' | 'loading' | 'success' | 'error'; options: InputOption[] }`.
- Consumes: `extractDataSourceItems`, `mapDynamicItems`, `resolveDynamicSourceId`, and `useDataSourceApi`.

- [ ] **Step 1: Add failing source and behavior assertions**

Assert that `ParamInputControl` imports `useParamInputOptions`, no longer owns `FetchState` or calls `getSourceDataByApiId`, and accepts:

```ts
onOptionsResolved?: (options: InputOption[]) => void;
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run: `cd web; pnpm exec tsx scripts/param-input-config-utils-test.ts; pnpm test:ops-analysis-component-param-switch`

Expected: FAIL on the missing hook/wiring assertions.

- [ ] **Step 3: Extract the hook**

Move the existing request-id race protection and static/dynamic branches from `ParamInputControl` into the hook. Return `options: []` for idle/loading/error, and return mapped options only for success. Preserve the existing fallback behavior when loading fails or returns no options.

- [ ] **Step 4: Wire the resolved-options callback**

In `ParamInputControl`, call the callback only for successful non-empty results:

```ts
useEffect(() => {
  if (state.status === 'success' && state.options.length > 0) {
    onOptionsResolved?.(state.options);
  }
}, [onOptionsResolved, state]);
```

Do not call it for input controls, empty options, or failures.

- [ ] **Step 5: Run focused tests**

Run: `cd web; pnpm exec tsx scripts/param-input-config-utils-test.ts; pnpm test:ops-analysis-component-param-switch`

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run: `git diff --check; git status --short`

Expected: Task 1-2 changes only; do not stage or commit.

---

### Task 3: Add component-switch configuration and silent value reconciliation

**Files:**
- Modify: `web/src/app/ops-analysis/components/paramInputConfigEditor.tsx:40-46,113-347,364-388`
- Modify: `web/src/app/ops-analysis/components/paramsConfig.tsx:77-284`
- Modify: `web/src/app/ops-analysis/components/widgetConfig.tsx:117,474-481,741-779,817-838,1221-1228`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Modify: `web/scripts/ops-analysis-component-param-switch-test.ts`

**Interfaces:**
- `ParamInputConfigEditor` consumes `componentSwitchEnabled?: boolean`, `componentSwitchOwner?: { name: string; label: string }`, and `editingParamName?: string`.
- `onConfirm` becomes `(value: InputControlConfig, resolvedOptions?: InputOption[]) => void`.
- `DataSourceParamsConfig` consumes `onParamOptionsResolved?: (param: ParamItem, options: InputOption[]) => void`.

- [ ] **Step 1: Add failing configuration assertions**

Cover these source-visible rules in the focused script:

```ts
assert.match(editorSource, /componentSwitchEnabled/);
assert.match(editorSource, /componentSwitchOwner/);
assert.match(editorSource, /control !== 'input'/);
assert.match(widgetConfigSource, /reconcileParamOptionValue/);
assert.match(widgetConfigSource, /clearComponentSwitch/);
assert.doesNotMatch(unifiedFilterSource, /componentSwitchEnabled/);
```

Also test a pure merge helper, if extracted, that preserves the current value when options are empty and silently replaces an invalid value when options are non-empty.

- [ ] **Step 2: Run and confirm failure**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: FAIL on missing editor props and reconciliation wiring.

- [ ] **Step 3: Render the switch only for eligible TopN editor sessions**

For `select|radio`, render an Ant Design `Switch` labeled `paramInput.componentSwitch`. If another parameter owns the switch, disable it and wrap it in a tooltip using:

```text
每个组件暂时只能配置一个组件内切换参数，当前已由「{label}」启用。
```

The current owner remains editable. When control changes to `input`, return `{ control: 'input' }` without `componentSwitch`.

- [ ] **Step 4: Return resolved options from the editor**

For static options, pass `staticItems` as the second `onConfirm` argument. For dynamic options, map the already loaded preview with `dynamicValueField` and `dynamicLabelField`; pass the mapped non-empty list, otherwise pass `undefined`. Do not persist preview rows.

- [ ] **Step 5: Reconcile the form value silently**

In `widgetConfig.tsx`, after accepting the new config:

```ts
const currentValue = form.getFieldValue(['params', editingInputConfigParam.name]);
const reconciled = reconcileParamOptionValue(currentValue, resolvedOptions || []);
if (reconciled.changed) {
  form.setFieldValue(['params', editingInputConfigParam.name], reconciled.value);
}
```

Do not call `message`, show a toast, or render an inline warning.

Also pass `onOptionsResolved` through `DataSourceParamsConfig` so a later successful dynamic load applies the same reconciliation rule.

- [ ] **Step 6: Enforce occupancy and chart changes**

Derive the owner from `widgetParamOverrides`. Only pass `componentSwitchEnabled` when `chartType === 'topN'`. In `handleChartTypeChange`, when leaving TopN, map overrides through `clearComponentSwitch` while preserving `control` and `optionsSource`.

- [ ] **Step 7: Run focused tests**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: PASS.

- [ ] **Step 8: Review without committing**

Run: `git diff --check; git status --short`

Expected: no staged files and no commit; inspect the editor and value-reset diff manually.

---

### Task 4: Persist and validate exactly one switch parameter

**Files:**
- Modify: `web/src/app/ops-analysis/components/widgetConfig/utils/submitConfig.ts:17-75,202-285`
- Modify: `web/src/app/ops-analysis/components/widgetConfig.tsx:817-875`
- Modify: `web/scripts/ops-analysis-component-param-switch-test.ts`

**Interfaces:**
- Produces: new `WidgetSubmitError` variant `'multipleComponentSwitchParams'`.
- Consumes: `validateSingleComponentSwitch(values.dataSourceParams || [])`.

- [ ] **Step 1: Add failing submit assertions**

Build one valid config and one config with two enabled params. Assert the first preserves `inputConfig.componentSwitch`, the second returns:

```ts
{ error: 'multipleComponentSwitchParams' }
```

Assert the serialized result has neither `runtimeParamControl` nor `runtimeParamControlEnabled`.

- [ ] **Step 2: Run and confirm failure**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: FAIL on the missing submit error and legacy-field removal.

- [ ] **Step 3: Add submit-time validation**

Before building the final widget config, validate `dataSourceParams`. Return the new error when conflicts exist. In `widgetConfig.tsx`, display a localized blocking error naming conflicting parameter aliases. This is an error state, not the silent invalid-value reconciliation path.

- [ ] **Step 4: Add save-time value reconciliation**

Keep a ref/map of successfully resolved options by parameter name. Before `processFormParamsForSubmit`, reconcile only entries with known non-empty options. Unknown, empty, and failed sources retain their value.

- [ ] **Step 5: Run focused tests**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: PASS.

- [ ] **Step 6: Review without committing**

Run: `git diff --check; git status --short`

Expected: unstaged implementation changes only.

---

### Task 5: Render the new TopN header control and drive requests

**Files:**
- Create: `web/src/app/ops-analysis/components/componentParamSwitchControl.tsx`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx:20-52,244-367,747-832`
- Modify: `web/src/app/ops-analysis/utils/widgetDataTransform.ts:340-355`
- Modify: `web/src/app/ops-analysis/components/widgetRenderer.tsx`
- Modify: `web/src/app/ops-analysis/components/widgets/comTopN.tsx`
- Modify: `web/scripts/ops-analysis-component-param-switch-test.ts`

**Interfaces:**
- `ComponentParamSwitchControl` consumes `{ inputConfig, options, value, onChange, disabled? }`.
- `widgetDataRenderer` consumes `findComponentSwitchParams`, `reconcileParamOptionValue`, and `buildComponentSwitchRuntimeParams`.
- Produces runtime params merged into the existing request params and signature.

- [ ] **Step 1: Add failing renderer/request assertions**

Assert that:

- `select` source renders `<Select>`.
- `radio` source renders `<Segmented>`.
- the header renderer consumes `InputControlConfig`, not `RuntimeParamControl`.
- a saved invalid value and options `[a, b]` produce initial value `a` and request params `{ [paramName]: 'a' }`.
- non-TopN charts produce no component-switch runtime params.

- [ ] **Step 2: Run and confirm failure**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: FAIL because the new header component and request path do not exist.

- [ ] **Step 3: Implement the header renderer**

Use Ant Design components directly:

```tsx
return inputConfig.control === 'radio' ? (
  <Segmented options={options} value={value} onChange={onChange} />
) : (
  <Select options={options} value={value} onChange={onChange} />
);
```

Return `null` for input controls or empty options.

- [ ] **Step 4: Resolve options and initial runtime value in WidgetWrapper**

Find the unique eligible parameter from effective component params. Load its options through `useParamInputOptions`. When non-empty options resolve, reconcile the saved component value and set runtime state to the reconciled value. Clear runtime state when chart type, data source, parameter name, or option config changes.

- [ ] **Step 5: Merge runtime params before the first request**

Do not issue a TopN request with a known-invalid saved value while options are successfully resolved. Build runtime params from the reconciled value, merge them into `buildWidgetExtraParams`, and include them in the request signature/cache key.

If dynamic options are still loading, preserve current behavior until resolution; once resolved, issue the request with the reconciled value. If loading fails or returns empty, query with the saved parameter value and hide the header control.

- [ ] **Step 6: Remove legacy renderer props**

Remove `runtimeParamControlPlacement`, `runtimeParamValue`, and `onRuntimeParamChange` from `WidgetRenderer` and `ComTopN`. Keep the existing header slot and render `ComponentParamSwitchControl` through it.

- [ ] **Step 7: Run focused tests**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: PASS.

- [ ] **Step 8: Review without committing**

Run: `git diff --check; git status --short`

Expected: new runtime implementation is unstaged and no commit exists.

---

### Task 6: Delete the legacy widget/runtime configuration model

**Files:**
- Delete: `web/src/app/ops-analysis/utils/runtimeParamControl.ts`
- Delete: `web/src/app/ops-analysis/components/widgetConfig/sections/runtimeParamControlEditor.tsx`
- Delete: `web/src/app/ops-analysis/components/widgets/runtimeParamSegmented.tsx`
- Delete: `web/scripts/ops-analysis-topn-runtime-param-test.ts`
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts:91-121`
- Modify: `web/src/app/ops-analysis/types/topology.ts:330-365`
- Modify: `web/src/app/ops-analysis/components/widgetConfig/sections/topNSettingsSection.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/index.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts`
- Modify: `web/src/app/ops-analysis/components/widgets/widgetShowcase.stories.tsx`
- Modify: `web/package.json`
- Modify: `web/scripts/ops-analysis-component-param-switch-test.ts`

**Interfaces:**
- Consumes: Tasks 1-5 replacement types, config UI, and runtime renderer.
- Produces: no production references to the legacy model.

- [ ] **Step 1: Add a failing legacy-production scan**

Scan production files and current fixtures, excluding historical `docs/superpowers/**`, for:

```text
filterType: 'widget'
"filterType": "widget"
runtimeParamControl
runtimeParamControlEnabled
RuntimeParamControl
RuntimeParamSegmented
```

The test must fail before deletion.

- [ ] **Step 2: Remove legacy types, UI, helpers, and mappings**

Delete the three dedicated files and all imports/usages. Remove old TopN sidebar fields, form initialization, chart-type patches, submit validation, Dashboard copying, Topology copying, and Storybook legacy examples.

- [ ] **Step 3: Remove the obsolete package command**

Delete `test:ops-analysis-topn-runtime-param`; retain the new component-switch command.

- [ ] **Step 4: Run the new suite and production scan**

Run: `cd web; pnpm test:ops-analysis-component-param-switch`

Expected: PASS and no legacy production matches.

- [ ] **Step 5: Review without committing**

Run: `git diff --check; git status --short`

Expected: deletions and replacements are visible but unstaged.

---

### Task 7: Update built-in data, backend fixtures, copy, and final gates

**Files:**
- Modify: `server/apps/operation_analysis/support-files/source_api.json:469`
- Modify: `server/apps/operation_analysis/tests/test_management_commands.py:146,243,277`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Modify: `web/scripts/ops-analysis-component-param-switch-test.ts`

**Interfaces:**
- Consumes: final `params + string + InputControlConfig.componentSwitch` model.
- Produces: clean initialization data and regression coverage.

- [ ] **Step 1: Change built-in `group_by` to a normal parameter**

Use:

```json
{"name":"group_by","type":"string","value":"instance_type","alias_name":"排行主体","filterType":"params"}
```

Do not embed component-level `inputConfig` in the global data-source definition; the user configures it on the component.

- [ ] **Step 2: Update backend tests**

Change assertions and fixtures expecting `widget` to expect `params`. Keep tests proving initialization/update preserves the parameter object.

- [ ] **Step 3: Finalize locale copy**

Retain/add component-editor keys for “组件内切换”, occupancy, and multiple-switch errors. Delete old TopN-sidebar keys and the data-source `filterTypes.widget` key.

- [ ] **Step 4: Run focused frontend and backend tests**

Run:

```powershell
Set-Location web
pnpm exec tsx scripts/param-input-config-utils-test.ts
pnpm test:ops-analysis-component-param-switch
pnpm type-check
Set-Location ../server
uv run pytest apps/operation_analysis/tests/test_management_commands.py -q
```

Expected: all commands exit 0.

- [ ] **Step 5: Run final legacy and quality scans**

Run from repository root:

```powershell
rg -n "filterType.*widget|runtimeParamControl|RuntimeParamControl|RuntimeParamSegmented" web/src web/scripts server/apps/operation_analysis --glob '!docs/superpowers/**'
git diff --check
git status --short
```

Expected: `rg` returns no legacy production matches; diff check passes; all changes remain unstaged and uncommitted.

- [ ] **Step 6: Perform the manual stored-data conversion**

After deployment, follow the approved design document: change the one stored data-source parameter from “组件内交互” to “参数”, open the one TopN component, recreate its select/radio options, enable “组件内切换”, set the desired saved parameter value, save, and verify header switching triggers refreshed requests.

- [ ] **Step 7: Handoff without committing**

Present the complete changed-file list, test results, manual conversion checklist, and remaining untracked design/plan documents. Do not stage or commit unless the user explicitly requests it.

---

## 恢复后的最终实现差异

- 原计划的 `componentParamValueKey` 最终实现为 `getTypedValueKey`。
- 原计划的 `validateSingleComponentSwitch` 最终以错误码接口接入提交链，并补充返回 `{ valid, params }` 的详细校验辅助函数。
- 原计划的 `reconcileParamOptionValue` 最终以值接口接入表单链，并补充返回 `{ value, changed }` 的辅助函数。
- 原计划的 `resolveComponentSwitchRuntime` 最初未按原名接入；恢复阶段增加等价纯解析函数，集中处理 TopN、候选、校正、完整 options 校验和最终请求参数。
- loader 最终采用 `sync + initial + promise`，使静态选项同步参与首次渲染和首次请求。
- `sourceRef` 第一阶段列表请求完成后立即检查 stale；旧请求不会继续发起第二阶段请求。
- active value 只有存在于完整 options 中才进入额外请求参数和 request signature。
- 无 header slot 时通过 TopN 内联回退；有 slot 时使用标题区 portal，避免重复渲染。
- 新增 `topNContentState.ts`，承接删除旧 runtime utility 后仍需保留的 TopN `loading/error/empty/ready` 状态逻辑。

## specs: 2026-07-16-unified-component-param-switch-design.md

## 背景

运营分析当前存在两套相互重叠的参数交互模型：

- 普通查询参数使用 `filterType: 'params'`，字符串参数可在组件级配置输入框、下拉选择或单选按钮，并支持静态、动态选项来源。
- TopN 组件内切换使用独立的 `filterType: 'widget'`、`RuntimeParamControl` 和侧边栏“组件内切换”区块。

两套模型重复保存参数绑定、选项和运行时输入行为。新的参数输入配置已经能够表达控件类型和选项来源，因此本设计将 TopN 组件内切换合并到普通字符串参数配置中，并完整删除旧模型。

## 目标

- 使用 `filterType: 'params'`、`type: 'string'` 的参数配置组件内切换。
- 在 `ParamInputConfigEditor` 中完成输入方式、选项来源和组件内切换配置。
- 第一阶段只允许 TopN 使用组件内切换，但数据结构不与 TopN 类型绑定。
- 每个组件暂时只能启用一个组件内切换参数。
- 复用现有静态、动态选项来源和参数请求链路。
- 删除 `filterType: 'widget'`、`RuntimeParamControl` 和 TopN 专用配置区块。
- 不引入数据库迁移或长期兼容层；现有唯一数据源和组件由用户手动转换。

## 非目标

- 第一阶段不支持 TopN 以外的图表类型展示组件内切换。
- 不支持一个组件同时展示多个组件内切换控件。
- 不允许文本输入框作为组件内切换控件。
- 不改变统一筛选编辑器的行为。
- 不在组件内切换后自动保存新的参数值到组件配置。

## 数据模型

在 `InputControlConfig` 的选项型分支增加 `componentSwitch?: boolean`：

```ts
export type InputControlConfig =
  | {
      control: 'input';
    }
  | {
      control: 'select' | 'radio';
      optionsSource: StaticOptionsSource | DynamicOptionsSource;
      componentSwitch?: boolean;
    };
```

约束如下：

1. 只有 `filterType: 'params'`、`type: 'string'` 的参数可配置组件内切换。
2. `componentSwitch` 只允许出现在 `select` 或 `radio` 分支。
3. 每个组件的最终 `dataSourceParams` 中最多存在一个 `componentSwitch: true`。
4. 第一阶段只有 TopN 消费该字段。
5. 静态和动态选项继续保存在 `optionsSource`，不复制成另一份运行时配置。

删除以下旧结构：

- `DataSourceParamFilterType` 中的 `'widget'`
- `RuntimeParamValue`
- `RuntimeParamOption`
- `RuntimeParamControl`
- `ValueConfig.runtimeParamControl`
- 表单临时字段 `runtimeParamControlEnabled`

## 组件配置交互

### 编辑入口

组件侧边栏继续在查询参数区域展示 `params` 和 `fixed` 参数。字符串参数保留输入配置入口，配置作为组件级覆盖写入 `valueConfig.dataSourceParams`，不修改数据源定义。

### ParamInputConfigEditor

组件配置场景打开编辑器时：

- 控件类型为“输入框”时，不显示“组件内切换”。
- 控件类型为“下拉选择”或“单选按钮”时，在选项来源配置之前显示“组件内切换”开关。
- 当前图表不是 TopN 时，不显示开关。
- 当前组件已有另一个参数启用组件内切换时，开关保持关闭并禁用。
- 禁用提示为：`每个组件暂时只能配置一个组件内切换参数，当前已由「{参数显示名}」启用。`
- 编辑当前已启用的参数时，允许关闭开关。
- 从 `select` 或 `radio` 改成 `input` 时，清除 `componentSwitch`。

编辑器需要由组件配置调用方传入当前图表类型和已占用参数信息。统一筛选配置调用同一编辑器时不传组件切换能力，因此不显示该开关。

### 图表类型切换

组件从 TopN 切换到其他图表类型时：

- 自动删除组件参数覆盖中的 `componentSwitch`。
- 保留 `control` 和完整 `optionsSource`。
- 以后切回 TopN 时，用户可以重新开启组件内切换。

这样可以避免非 TopN 组件持有界面不可见、当前也不生效的隐藏开关配置。

### 保存校验

界面禁用不是唯一保障。组件提交前必须再次统计 `componentSwitch: true` 的参数：

- 0 个或 1 个时允许保存。
- 超过 1 个时阻止保存，并明确列出冲突参数。
- `input` 分支上异常存在的 `componentSwitch` 按未启用处理并在规范化时清除。

### 选项变化后的参数值校正

下拉选择或单选按钮的选项发生变化后，组件当前参数值必须与有效选项保持一致：

- 当前值仍在有效选项中时保留当前值。
- 当前值不在有效选项中且选项非空时，静默重置为 `options[0].value`，不展示提示消息。
- 选项为空、动态选项加载失败或尚未解析完成时，保留当前值，不擅自清空或覆盖。

静态选项在用户确认输入配置时立即执行校正。动态选项在成功加载后执行校正；组件保存前对已经成功解析出选项的参数再做一次兜底校验。普通下拉、单选参数与组件内切换参数复用同一套规则，不能只修正标题区运行时值。

值匹配必须同时比较类型和值，例如字符串 `"1"` 与数字 `1` 视为不同值。

## 运行时行为

### 解析有效配置

运行时从数据源参数与组件级 `dataSourceParams` 合并出最终参数配置，然后寻找唯一满足以下条件的参数：

- `filterType === 'params'`
- `type === 'string'`
- `inputConfig.control` 为 `select` 或 `radio`
- `inputConfig.componentSwitch === true`

非 TopN 图表不解析或展示组件内切换。

### 选项加载

- 静态来源直接使用 `staticItems`。
- 动态来源复用现有数据源请求、`valueField`、`labelField` 和选项映射逻辑。
- 动态选项加载失败、配置无效或结果为空时，不展示标题区控件；组件仍使用已保存参数值查询，不让整个组件进入错误状态。

### 初始值

初始值取组件保存的参数值。若该值不在有效选项中，则使用第一项，并且首次组件数据请求也使用同一个回退值，保证控件状态与请求参数一致。

该运行时回退与配置阶段的参数值校正复用同一个纯函数，避免配置表单、保存结果和组件请求采用不同判断规则。

旧 `RuntimeParamControl.defaultValue` 不再保留；现有唯一组件在手动转换时，将期望的默认选项写入组件参数值。

### 标题区展示

- `control: 'select'` 渲染下拉框。
- `control: 'radio'` 在组件配置区仍使用单选按钮，在 TopN 标题区渲染 `Segmented`。

标题区控件继续复用现有 header slot 布局。控件切换后只更新当前组件实例的运行时参数值，将该值合并进数据请求参数和请求缓存签名，触发重新查询；不自动持久化组件配置。

## 旧能力删除

实现需完整删除：

- 数据源参数用途中的“组件内交互”选项及文案。
- TopN 设置区中的独立“组件内切换”区块。
- `RuntimeParamControlEditor`。
- `runtimeParamControl` 的校验、初始值、请求参数和渲染工具。
- Dashboard、Screen、Topology 对旧字段的复制和透传。
- 旧 `RuntimeParamSegmented`；新的标题区控件直接基于 `InputControlConfig` 渲染。
- 旧 Storybook 示例、测试夹具和本功能专用旧文案。

内置数据源 `server/apps/operation_analysis/support-files/source_api.json` 中的 `group_by` 参数从 `filterType: 'widget'` 改为 `filterType: 'params'`，防止新环境或初始化流程重新生成旧类型。

## 存量数据处理

不编写数据库迁移，也不保留旧配置读取兼容层。原因是当前只有一个数据源和一个 TopN 组件使用旧能力，人工转换更明确，且可避免一次性迁移与长期兼容代码形成技术债。

上线后按以下步骤处理：

1. 记录旧 TopN 配置的绑定参数、选项和值。
2. 在数据源设置页把对应参数从“组件内交互”改为“参数”，保持字符串类型并保存。
3. 打开原 TopN 组件，在查询参数区域进入该参数的输入配置。
4. 选择下拉选择或单选按钮，重新配置静态或动态选项来源。
5. 开启“组件内切换”。
6. 将组件参数值设置为期望的首次选中值并保存组件。
7. 验证标题区控件、初始查询、切换查询和重新打开后的配置。

重新保存唯一组件后，新配置不再输出 `runtimeParamControl`，旧字段随组件保存被清除。

## 异常与降级

- 多个参数同时启用：阻止组件保存并展示冲突参数。
- 动态选项请求失败或为空：隐藏标题区控件，继续用已保存参数查询。
- 初始值不在选项中：回退第一项，并使用回退值发起首次请求。
- 配置阶段已成功解析出非空选项但当前值失效：静默重置为第一项，不展示提示消息。
- 切换数据源：移除不属于新数据源的组件参数覆盖，不能把旧开关绑定到同名但无关的参数。
- 切换离开 TopN：清除 `componentSwitch`，保留其他输入配置。
- 异常的 `input + componentSwitch`：按未启用处理并清除异常字段。

## 测试策略

### 类型与纯函数

- 组件内切换候选参数筛选。
- 单参数唯一性校验及冲突参数报告。
- 静态、动态选项解析。
- 已保存初始值与第一项回退。
- 选项值按“类型 + 值”匹配，字符串 `"1"` 不匹配数字 `1`。
- 运行时参数合并和请求签名变化。
- 非 TopN 不启用组件内切换。

### 配置界面

- TopN 的 `select/radio` 显示开关，`input` 不显示。
- 非 TopN 不显示开关。
- 统一筛选编辑器不显示开关。
- 已有其他占用参数时禁用开关并显示参数名。
- 编辑当前占用参数时可以关闭。
- 离开 TopN 清除开关但保留控件和选项来源。
- 多参数异常状态在保存阶段被拒绝。
- 静态选项变更后，失效参数值立即静默重置为第一项。
- 动态选项成功加载后，失效参数值静默重置为第一项。
- 选项为空或动态加载失败时保留原参数值。

### 保存与恢复

- `componentSwitch` 随组件级 `dataSourceParams` 保存并恢复。
- 数据源原始参数不被组件级配置修改。
- 保存前对已解析选项执行兜底校正，不再持久化已失效的参数值。
- 保存结果不再包含 `runtimeParamControl` 或临时启用字段。
- Dashboard、Screen、Topology 的正常参数配置不因删除旧透传字段而丢失。

### 运行时

- `select` 在标题区渲染下拉框。
- `radio` 在标题区渲染 `Segmented`。
- 切换选项触发带新参数值的数据请求。
- 运行时值参与请求缓存签名。
- 动态选项失败、空数据及无效初始值按设计降级。

### 清理检查

生产代码、内置数据和当前测试夹具中不再出现：

- `filterType: 'widget'`
- `runtimeParamControl`
- `runtimeParamControlEnabled`
- `RuntimeParamControl`

历史设计文档和历史实施计划作为决策记录保留，不纳入生产代码清理要求。

## 验收标准

1. TopN 组件的字符串查询参数可以在输入配置弹窗中开启组件内切换。
2. 每个组件最多开启一个，其他参数开关禁用并显示占用参数。
3. 下拉选择在标题区显示下拉框，单选按钮在标题区显示 `Segmented`。
4. 静态和动态选项来源均可工作。
5. 初始值来自组件参数，无效时回退第一项且首次请求一致。
6. 切换触发重新查询但不自动保存组件配置。
7. 非 TopN 和统一筛选编辑器不显示组件内切换开关。
8. 离开 TopN 自动清除开关但保留输入控件配置。
9. 旧 widget 类型、旧侧栏和旧运行时配置从生产代码中完全删除。
10. 用户按手动步骤转换唯一存量数据源和组件后，功能连续且数据库不再保留该组件的旧字段。

## 恢复后的最终实现补充

- 当组件标题区没有可用的 header slot 时，TopN 通过 `WidgetRenderer` 接收同一个切换控件并在内容区顶部内联回退显示；有 header slot 时只通过 portal 渲染，不重复内联。
- 动态选项通过 `sourceRef` 定位数据源时，数据源列表这一阶段完成后立即检查 generation。请求已 stale 时直接返回 `null`，不再启动第二阶段数据请求。
- 运行时 active value 必须按“类型 + 值”存在于完整 options 中，才允许写入额外请求参数；preview 的前 5 条永不参与该判断。
- 删除旧 `runtimeParamControl.ts` 后，其中与参数切换无关的 TopN `loading/error/empty/ready` 状态能力迁入 `topNContentState.ts`，保持原渲染和 `onReady` 语义。
