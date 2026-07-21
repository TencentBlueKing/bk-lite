# Unified Component Parameter Switch Implementation Plan

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
