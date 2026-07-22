# Historical Superpowers change: 2026-07-17-date-range-parameter

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-17-date-range-parameter.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class `dateRange` parameter for NATS data sources and unified filters, persisting date rules and resolving them to date-only request tuples immediately before requests.

**Architecture:** Keep persisted `DateRangeValue | null` separate from resolved `[string, string]`. A focused date-range domain module owns validation, timezone selection, and deterministic rule resolution; a dedicated selector owns UI adaptation; existing parameter precedence, canvas discovery, and request aggregation are extended by exact type matching. Request and signature builders receive the same resolution context so one request cycle cannot resolve across two calendar dates.

**Tech Stack:** TypeScript, React 19, Next.js 16, Ant Design 5 `DatePicker.RangePicker`, Dayjs with timezone plugins, existing `tsx` assertion scripts, Django/Python import precheck only where configuration validation requires it.

## Global Constraints

- The exact parameter type identifier is `dateRange`; the NATS selector list is `string`, `number`, `boolean`, `date`, `timeRange`, `dateRange`.
- Persist only `{ rangeType: DateRangeType }`, `{ rangeType: "custom", startDate, endDate }`, or `null`; never persist Dayjs, `Date`, timestamps, ISO datetime strings, or resolved arrays.
- Initialize a newly selected `dateRange` to `{ rangeType: "last_7_days" }`; explicit clear emits `null`, and request construction omits `null` without fallback.
- Resolve quick rules immediately before each request in the current configured user timezone; if none is available, use the browser timezone.
- Resolved values are inclusive `["YYYY-MM-DD", "YYYY-MM-DD"]`; never call `toISOString()` or add UTC/time boundaries in date-range logic.
- Invalid non-null values are rejected on configuration save/import, preserved with an error on edit echo, and omitted at runtime without conversion to `last_7_days`.
- Preserve precedence: fixed > enabled unified-filter override > component params value > data-source default. An effective `null` is terminal omission, not a signal to fall through.
- Do not add or repair mandatory-parameter behavior. Do not touch reports, period comparison, table `inputType=time_range`, shared URLs, REST/MySQL/PostgreSQL/Excel parameter editors, or backend NATS request parsing.
- Preserve unrelated existing work in `paramsConfig.tsx`, `paramsConfigTimeRange.ts`, and `ops-analysis-params-time-range-test.ts`; inspect the working-tree diff before editing overlapping files.

---

### Task 1: Date-range domain model, validation, timezone, and resolution

**Files:**
- Create: `web/src/app/ops-analysis/types/dateRange.ts`
- Create: `web/src/app/ops-analysis/utils/dateRange.ts`
- Create: `web/scripts/ops-analysis-date-range-domain-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `DateRangeType`, `DateRangeValue`, `ResolvedDateRange`, `DATE_RANGE_TYPES`, `DEFAULT_DATE_RANGE_VALUE`.
- Produces: `validateDateRangeValue(value): DateRangeValidationResult`, `resolveDateRange(value, context): ResolvedDateRange | null`, and `getDateRangeTimezone(configuredTimezone?): string`.
- Consumes: Dayjs timezone support and the browser's `Intl.DateTimeFormat().resolvedOptions().timeZone` fallback.

- [ ] **Step 1: Write the failing domain test**

Create a table-driven assertion script covering all ten discriminators, strict custom-date validation, conflicting fields, null, timezone day changes, Monday weeks, month/year boundaries, rolling ranges including today, and DST:

```ts
import assert from 'node:assert/strict';
import {
  resolveDateRange,
  validateDateRangeValue,
} from '../src/app/ops-analysis/utils/dateRange';

assert.deepEqual(
  resolveDateRange(
    { rangeType: 'last_7_days' },
    { referenceNow: '2026-07-17T03:08:00.176Z', timezone: 'Asia/Shanghai' },
  ),
  ['2026-07-11', '2026-07-17'],
);
assert.deepEqual(
  resolveDateRange(
    { rangeType: 'this_week' },
    { referenceNow: '2026-07-12T12:00:00Z', timezone: 'Asia/Shanghai' },
  ),
  ['2026-07-06', '2026-07-12'],
);
assert.equal(validateDateRangeValue(null).valid, true);
assert.equal(validateDateRangeValue({ rangeType: 'last30days' }).valid, false);
assert.equal(
  validateDateRangeValue({ rangeType: 'custom', startDate: '2026-02-30', endDate: '2026-03-01' }).valid,
  false,
);
assert.equal(
  validateDateRangeValue({ rangeType: 'last_7_days', startDate: '2026-07-01', endDate: '2026-07-17' }).valid,
  false,
);
```

- [ ] **Step 2: Add and run the test command to verify RED**

Add:

```json
"test:ops-analysis-date-range-domain": "pnpm exec tsx scripts/ops-analysis-date-range-domain-test.ts"
```

Run: `pnpm test:ops-analysis-date-range-domain`

Expected: FAIL because `types/dateRange.ts` and `utils/dateRange.ts` do not exist.

- [ ] **Step 3: Define the closed value model**

Implement discriminated types, keeping quick rules unable to carry custom fields:

```ts
export const DATE_RANGE_TYPES = [
  'today', 'yesterday', 'this_week', 'last_week', 'this_month',
  'last_month', 'last_7_days', 'last_30_days', 'last_90_days', 'custom',
] as const;

export type DateRangeType = (typeof DATE_RANGE_TYPES)[number];
export type DateRangeValue =
  | { rangeType: Exclude<DateRangeType, 'custom'>; startDate?: never; endDate?: never }
  | { rangeType: 'custom'; startDate: string; endDate: string };
export type ResolvedDateRange = readonly [string, string];
export const DEFAULT_DATE_RANGE_VALUE: DateRangeValue = { rangeType: 'last_7_days' };
```

- [ ] **Step 4: Implement strict validation and deterministic resolution**

Use strict `YYYY-MM-DD` parsing and explicit Monday arithmetic. Resolve from a timezone-local `today`, format directly as `YYYY-MM-DD`, and return `null` for null/invalid input:

```ts
export interface DateRangeResolutionContext {
  referenceNow: string | number | Date;
  timezone: string;
}

export const resolveDateRange = (
  value: unknown,
  context: DateRangeResolutionContext,
): ResolvedDateRange | null => {
  const validation = validateDateRangeValue(value);
  if (!validation.valid || value === null) return null;
  if (value.rangeType === 'custom') return [value.startDate, value.endDate];
  const today = dayjs(context.referenceNow).tz(context.timezone).startOf('day');
  const monday = today.subtract((today.day() + 6) % 7, 'day');
  const ranges: Record<Exclude<DateRangeType, 'custom'>, [Dayjs, Dayjs]> = {
    today: [today, today],
    yesterday: [today.subtract(1, 'day'), today.subtract(1, 'day')],
    this_week: [monday, today],
    last_week: [monday.subtract(7, 'day'), monday.subtract(1, 'day')],
    this_month: [today.startOf('month'), today],
    last_month: [today.subtract(1, 'month').startOf('month'), today.subtract(1, 'month').endOf('month')],
    last_7_days: [today.subtract(6, 'day'), today],
    last_30_days: [today.subtract(29, 'day'), today],
    last_90_days: [today.subtract(89, 'day'), today],
  };
  const [start, end] = ranges[value.rangeType];
  return [start.format('YYYY-MM-DD'), end.format('YYYY-MM-DD')];
};
```

`getDateRangeTimezone` must use a non-empty configured value first, then browser `Intl`, and only use a deterministic SSR fallback when no browser exists. Do not reuse `getStoredTimezone()` as the absence test because it currently converts missing storage to `Asia/Shanghai`.

- [ ] **Step 5: Run domain tests and type-check the new files**

Run: `pnpm test:ops-analysis-date-range-domain`

Expected: PASS with `ops analysis date range domain tests passed`.

Run: `pnpm exec eslint src/app/ops-analysis/types/dateRange.ts src/app/ops-analysis/utils/dateRange.ts scripts/ops-analysis-date-range-domain-test.ts`

Expected: PASS with no errors.

- [ ] **Step 6: Commit the domain unit**

```bash
git add web/package.json web/src/app/ops-analysis/types/dateRange.ts web/src/app/ops-analysis/utils/dateRange.ts web/scripts/ops-analysis-date-range-domain-test.ts
git commit -m "feat: add date range domain model"
```

### Task 2: Dedicated DateRangeSelector

**Files:**
- Create: `web/src/app/ops-analysis/components/dateRangeSelector.tsx`
- Create: `web/src/app/ops-analysis/components/dateRangeSelectorModel.ts`
- Create: `web/scripts/ops-analysis-date-range-selector-test.ts`
- Modify: `web/package.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`
- Modify: `web/src/app/ops-analysis/locales/zh.json`

**Interfaces:**
- Consumes: `DateRangeValue | null`, `DEFAULT_DATE_RANGE_VALUE`, and `validateDateRangeValue` from Task 1.
- Produces: `<DateRangeSelector value onChange disabled allowClear status />` whose external values never contain Dayjs.
- Produces: pure adapters `toDateRangePickerValue` and `completeCustomDateRange` for focused tests.

- [ ] **Step 1: Write failing selector-model and source-wiring tests**

Assert default display, custom conversion, incomplete custom preservation, and clear semantics:

```ts
assert.deepEqual(toDateRangePickerValue({
  rangeType: 'custom', startDate: '2026-07-01', endDate: '2026-07-17',
})?.map((item) => item.format('YYYY-MM-DD')), ['2026-07-01', '2026-07-17']);
assert.equal(completeCustomDateRange([dayjs('2026-07-01'), null]), null);
assert.deepEqual(completeCustomDateRange([
  dayjs('2026-07-01'), dayjs('2026-07-17'),
]), { rangeType: 'custom', startDate: '2026-07-01', endDate: '2026-07-17' });
```

Also read the selector source and assert it imports Ant Design `DatePicker`, exposes `allowClear`, and does not contain `TimeSelector`, `toISOString`, or timestamp conversion.

- [ ] **Step 2: Run the selector test to verify RED**

Add `"test:ops-analysis-date-range-selector": "pnpm exec tsx scripts/ops-analysis-date-range-selector-test.ts"` and run it.

Expected: FAIL because selector files do not exist.

- [ ] **Step 3: Implement the pure selector adapters**

```ts
export const toDateRangePickerValue = (value: DateRangeValue | null) =>
  value?.rangeType === 'custom'
    ? [dayjs(value.startDate, 'YYYY-MM-DD', true), dayjs(value.endDate, 'YYYY-MM-DD', true)] as const
    : null;

export const completeCustomDateRange = (dates: [Dayjs | null, Dayjs | null] | null) =>
  dates?.[0] && dates[1]
    ? { rangeType: 'custom' as const, startDate: dates[0].format('YYYY-MM-DD'), endDate: dates[1].format('YYYY-MM-DD') }
    : null;
```

- [ ] **Step 4: Implement the controlled selector**

Render the nine quick rules plus `custom` from canonical identifiers. Keep incomplete picker state local; only a complete range emits custom. The clear button calls `onChange(null)`. An undefined initial value is displayed as `DEFAULT_DATE_RANGE_VALUE`, while an explicit `null` remains empty.

```tsx
export interface DateRangeSelectorProps {
  value?: DateRangeValue | null;
  onChange?: (value: DateRangeValue | null) => void;
  disabled?: boolean;
  allowClear?: boolean;
  status?: 'error' | 'warning';
}
```

Add locale keys for `dateRange`, every quick label, `custom`, invalid-value messaging, and start/end placeholders in both locale files.

- [ ] **Step 5: Verify selector behavior and lint**

Run: `pnpm test:ops-analysis-date-range-selector && pnpm test:ops-analysis-date-range-domain`

Expected: both PASS.

Run: `pnpm exec eslint src/app/ops-analysis/components/dateRangeSelector.tsx src/app/ops-analysis/components/dateRangeSelectorModel.ts scripts/ops-analysis-date-range-selector-test.ts`

Expected: PASS.

- [ ] **Step 6: Commit the selector unit**

```bash
git add web/package.json web/src/app/ops-analysis/components/dateRangeSelector.tsx web/src/app/ops-analysis/components/dateRangeSelectorModel.ts web/src/app/ops-analysis/locales/en.json web/src/app/ops-analysis/locales/zh.json web/scripts/ops-analysis-date-range-selector-test.ts
git commit -m "feat: add date range selector"
```

### Task 3: NATS data-source parameter selection, persistence, validation, and echo

**Files:**
- Modify: `web/src/app/ops-analysis/types/dataSource.ts:124`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx:95`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts:60`
- Modify: `web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx:211`
- Create: `web/scripts/ops-analysis-date-range-data-source-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `DateRangeValue`, `DEFAULT_DATE_RANGE_VALUE`, `validateDateRangeValue`, and `DateRangeSelector`.
- Produces: a typed `ParamItem.value` that accepts `DateRangeValue | null`, strict save validation, unchanged rule-object normalization, and invalid-value edit echo.

- [ ] **Step 1: Write the failing data-source configuration test**

Cover these observable contracts:

```ts
const params = [{
  id: 'p1', name: 'period', alias_name: 'Period', type: 'dateRange',
  filterType: 'filter', value: { rangeType: 'last_30_days' },
}];
assert.deepEqual(normalizeParams(params), [{
  name: 'period', alias_name: 'Period', type: 'dateRange',
  filterType: 'filter', value: { rangeType: 'last_30_days' },
}]);
assert.equal(validateParams(params).valid, true);
assert.equal(validateParams([{ ...params[0], value: { rangeType: 'custom', startDate: '2026-07-17', endDate: '2026-07-01' } }]).valid, false);
assert.equal(validateParams([{ ...params[0], value: null }]).valid, true);
```

Add these concrete source assertions for registration and rendering:

```ts
const paramTableSource = readFileSync(paramTablePath, 'utf8');
assert.match(paramTableSource, /value:\s*["']dateRange["']/);
assert.match(paramTableSource, /DEFAULT_DATE_RANGE_VALUE/);
assert.match(paramTableSource, /<DateRangeSelector/);
```

- [ ] **Step 2: Run the test to verify RED**

Add `"test:ops-analysis-date-range-data-source": "pnpm exec tsx scripts/ops-analysis-date-range-data-source-test.ts"` and run it.

Expected: FAIL because `ParamItem` and NATS configuration do not recognize `dateRange`.

- [ ] **Step 3: Extend the data-source value type without adding mandatory fields**

```ts
export interface ParamItem {
  value: string | number | boolean | [number, number] | DateRangeValue | null;
  // Keep the existing shape unchanged; do not add a dateRange-specific mandatory field.
}
```

- [ ] **Step 4: Add the NATS parameter option and editor branch**

In `paramTable.tsx`, add `dateRange` after `timeRange`, initialize it on type change, pass persisted values directly to `DateRangeSelector`, and preserve `null` on clear:

```tsx
{ label: t('dataSource.paramTypes.dateRange'), value: 'dateRange' }
```

```ts
if (val === 'dateRange') newValue = { ...DEFAULT_DATE_RANGE_VALUE };
```

```tsx
if (type === 'dateRange') {
  return <DateRangeSelector value={text as DateRangeValue | null} onChange={(value) => handleDefaultChange(value, record.id!, 'dateRange')} />;
}
```

Invalid persisted values must remain assigned to the row and render the selector with `status="error"`; do not normalize them during modal load.

- [ ] **Step 5: Centralize save validation and preserve rules through normalization**

Extend `validateParams` so `dateRange` accepts null and rejects invalid non-null values. Return the offending row IDs so `ParamTable` can display field errors. `normalizeParams` must copy the rule object unchanged. Keep `operateModal.tsx` edit initialization as pass-through; only its historical `timeRange` default-filter fallback remains type-specific.

- [ ] **Step 6: Run focused tests and lint**

Run: `pnpm test:ops-analysis-date-range-data-source && pnpm test:ops-analysis-date-range-domain && pnpm test:ops-analysis-date-range-selector`

Expected: PASS.

Run: `pnpm exec eslint 'src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx' 'src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts' 'src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx' src/app/ops-analysis/types/dataSource.ts scripts/ops-analysis-date-range-data-source-test.ts`

Expected: PASS.

- [ ] **Step 7: Commit the NATS configuration unit**

```bash
git add web/package.json web/src/app/ops-analysis/types/dataSource.ts "web/src/app/ops-analysis/(pages)/settings/dataSource/paramTable.tsx" "web/src/app/ops-analysis/(pages)/settings/dataSource/operateModalUtils.ts" "web/src/app/ops-analysis/(pages)/settings/dataSource/operateModal.tsx" web/scripts/ops-analysis-date-range-data-source-test.ts
git commit -m "feat: configure date range data source params"
```

### Task 4: Component parameter input and persisted component values

**Files:**
- Modify: `web/src/app/ops-analysis/components/paramsConfig.tsx:95`
- Create: `web/scripts/ops-analysis-params-date-range-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `DateRangeSelector` and `DateRangeValue | null`.
- Produces: component-side fixed/read-only and editable date-range controls with rule-object form values.

- [ ] **Step 1: Write a failing component-parameter wiring test**

Assert that `paramsConfig.tsx` has a `dateRange` render branch, initializes undefined values to a cloned `DEFAULT_DATE_RANGE_VALUE`, leaves explicit `null` as null, and does not use `TimeSelector` for the new branch. Include assertions that existing time-range helper tests remain unchanged.

- [ ] **Step 2: Run RED**

Add `"test:ops-analysis-params-date-range": "pnpm exec tsx scripts/ops-analysis-params-date-range-test.ts"` and run it.

Expected: FAIL because `paramsConfig.tsx` has no `dateRange` branch.

- [ ] **Step 3: Add controlled component input and initialization**

```tsx
case 'dateRange':
  return <DateRangeSelector disabled={isDisabled} allowClear />;
```

```ts
case 'dateRange':
  return value === undefined ? { ...DEFAULT_DATE_RANGE_VALUE } : value;
```

Do not add form mandatory rules and do not convert values in submit code; Ant Form must carry `DateRangeValue | null` unchanged.

- [ ] **Step 4: Verify focused regression**

Run: `pnpm test:ops-analysis-params-date-range && pnpm exec tsx scripts/ops-analysis-params-time-range-test.ts`

Expected: both PASS.

Run: `pnpm exec eslint src/app/ops-analysis/components/paramsConfig.tsx scripts/ops-analysis-params-date-range-test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the component parameter unit**

```bash
git add web/package.json web/src/app/ops-analysis/components/paramsConfig.tsx web/scripts/ops-analysis-params-date-range-test.ts
git commit -m "feat: support date range component params"
```

### Task 5: Unified-filter types, configuration, runtime control, and state

**Files:**
- Modify: `web/src/app/ops-analysis/types/dashBoard.ts:238`
- Modify: `web/src/app/ops-analysis/utils/widgetDataTransform.ts:10`
- Modify: `web/src/app/ops-analysis/utils/unifiedFilterState.ts:34`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx:73`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx:1`
- Modify: `web/src/app/ops-analysis/components/unifiedFilter/filterBindingPanel.tsx:70`
- Create: `web/scripts/ops-analysis-date-range-unified-filter-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `DateRangeValue | null`, validator, and selector.
- Produces: `FilterValue` and `UnifiedFilterDefinition.type` support for exact `dateRange`; configuration and runtime use the same persisted rules.

- [ ] **Step 1: Write failing unified-filter tests**

Assert:

```ts
assert.deepEqual(getBindableFilterParams([{ name: 'period', alias_name: 'Period', type: 'dateRange', filterType: 'filter', value: { rangeType: 'last_7_days' } }])[0]?.type, 'dateRange');
assert.equal(getFilterDefinitionId('period', 'dateRange'), 'period__dateRange');
assert.deepEqual(syncFilterValuesWithDefinitions([
  { id: 'period__dateRange', key: 'period', name: 'Period', type: 'dateRange', defaultValue: { rangeType: 'last_30_days' }, order: 0, enabled: true },
], {}), { period__dateRange: { rangeType: 'last_30_days' } });
```

Also assert exact matching keeps `timeRange` and `dateRange` definitions separate, and clear remains `null`.

- [ ] **Step 2: Run RED**

Add `"test:ops-analysis-date-range-unified-filter": "pnpm exec tsx scripts/ops-analysis-date-range-unified-filter-test.ts"` and run it.

Expected: FAIL on current unions and bindable filtering.

- [ ] **Step 3: Extend shared filter types and discovery**

Add `DateRangeValue` to `FilterValue`; extend `UnifiedFilterDefinition.type`, `ScannedFilterParam.type`, and `BindableParamType` to `'dateRange'`. Update `getBindableFilterParams` to accept only `string`, `timeRange`, and `dateRange` with `filterType === 'filter'`.

- [ ] **Step 4: Add configuration and runtime selector branches**

In both modal and bar:

```tsx
if (record.type === 'dateRange') {
  return <DateRangeSelector value={value as DateRangeValue | null} onChange={(next) => handleFieldChange(record.id, 'defaultValue', next)} allowClear />;
}
```

Use `DateRangeSelector` directly; do not copy time-range Dayjs/ISO handlers. In the binding panel, add a distinct localized `dateRange` label/color while preserving exact name+type matching.

- [ ] **Step 5: Normalize stored defaults without resolving them**

In `syncFilterValuesWithDefinitions`, validate a non-null date-range default and copy the rule into current values. Preserve null. Do not call `resolveDateRange` here—the rule must remain dynamic until request time.

- [ ] **Step 6: Run unified-filter regressions and lint**

Run: `pnpm test:ops-analysis-date-range-unified-filter && pnpm test:ops-analysis-unified-filter-input`

Expected: PASS.

Run: `pnpm exec eslint src/app/ops-analysis/types/dashBoard.ts src/app/ops-analysis/utils/widgetDataTransform.ts src/app/ops-analysis/utils/unifiedFilterState.ts src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx src/app/ops-analysis/components/unifiedFilter/filterBindingPanel.tsx scripts/ops-analysis-date-range-unified-filter-test.ts`

Expected: PASS with no errors.

- [ ] **Step 7: Commit the unified-filter unit**

```bash
git add web/package.json web/src/app/ops-analysis/types/dashBoard.ts web/src/app/ops-analysis/utils/widgetDataTransform.ts web/src/app/ops-analysis/utils/unifiedFilterState.ts web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterConfigModal.tsx web/src/app/ops-analysis/components/unifiedFilter/unifiedFilterBar.tsx web/src/app/ops-analysis/components/unifiedFilter/filterBindingPanel.tsx web/scripts/ops-analysis-date-range-unified-filter-test.ts
git commit -m "feat: add date range unified filters"
```

### Task 6: Dashboard, Screen, and Topology discovery and binding restoration

**Files:**
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts:58`
- Modify: `web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts:88`
- Modify: `web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts:120`
- Create: `web/scripts/ops-analysis-date-range-canvas-binding-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `BindableParamType`, `DateRangeValue`, `getBindableFilterParams`, and exact definition IDs.
- Produces: equivalent discovery/default restoration/binding cleanup behavior on all three supported canvas hosts.

- [ ] **Step 1: Write failing three-host tests**

Build minimal data sources and canvas items containing a `dateRange` filter. Assert each builder discovers `period__dateRange`, preserves `{ rangeType: 'last_30_days' }` as a rule, and removes a stale `period__timeRange` binding after the type changes. Include Dashboard `buildFiltersFromDashboardLayout`, Screen `buildFiltersFromScreenItems`/`syncScreenFilterBindings`, and Topology namespace utilities.

- [ ] **Step 2: Run RED**

Add `"test:ops-analysis-date-range-canvas-binding": "pnpm exec tsx scripts/ops-analysis-date-range-canvas-binding-test.ts"` and run it.

Expected: FAIL because local narrowed types and default-value branches only recognize `string | timeRange`.

- [ ] **Step 3: Replace local narrowed unions with `BindableParamType`**

Use the shared type in all three files:

```ts
const discoveredParams = new Map<
  string,
  ParamItem & { type: BindableParamType }
>();
```

Keep `buildRelativeTimeRangeFilterValue` exclusively in the `timeRange` branch. A date-range default is copied unchanged after validation; no canvas file calculates dates.

- [ ] **Step 4: Verify all hosts and existing filter tests**

Run: `pnpm test:ops-analysis-date-range-canvas-binding && pnpm test:ops-analysis-date-range-unified-filter && pnpm test:ops-analysis-unified-filter-input`

Expected: PASS.

Run: `pnpm exec eslint 'src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts' 'src/app/ops-analysis/(pages)/view/screen/utils/layout.ts' 'src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts' scripts/ops-analysis-date-range-canvas-binding-test.ts`

Expected: PASS with no errors.

- [ ] **Step 5: Commit canvas integration**

```bash
git add web/package.json "web/src/app/ops-analysis/(pages)/view/dashBoard/hooks/useDashboardLayoutSync.ts" "web/src/app/ops-analysis/(pages)/view/screen/utils/layout.ts" "web/src/app/ops-analysis/(pages)/view/topology/utils/namespaceUtils.ts" web/scripts/ops-analysis-date-range-canvas-binding-test.ts
git commit -m "feat: bind date range filters across canvases"
```

### Task 7: Request-time resolution, omission, precedence, and shared signature context

**Files:**
- Modify: `web/src/app/ops-analysis/utils/widgetDataTransform.ts:354`
- Modify: `web/src/app/ops-analysis/components/widgetDataRenderer.tsx:440`
- Modify: `web/src/app/ops-analysis/hooks/useSingleValueConfig.ts`
- Modify: `web/src/app/ops-analysis/components/widgetConfig/hooks/useTableConfig.ts`
- Create: `web/scripts/ops-analysis-date-range-request-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: `DateRangeResolutionContext`, `validateDateRangeValue`, `resolveDateRange`, and `getDateRangeTimezone`.
- Produces: one pure `formatDataSourceParamValue(type, value, context)` omission-aware conversion used by fixed/filter/params/default branches and both request/signature builders.
- Produces: request and signature arrays resolved from the same `{ referenceNow, timezone }`.

- [ ] **Step 1: Write failing request-construction tests**

Cover fixed, filter override, component params, and default paths:

```ts
const context = { referenceNow: '2026-07-17T03:08:00.176Z', timezone: 'Asia/Shanghai' };
assert.deepEqual(processDataSourceParams({
  sourceParams: [{ name: 'period', type: 'dateRange', filterType: 'fixed', value: { rangeType: 'last_7_days' } }],
  resolutionContext: context,
}), { period: ['2026-07-11', '2026-07-17'] });
assert.deepEqual(processDataSourceParams({
  sourceParams: [{ name: 'period', type: 'dateRange', filterType: 'params', value: { rangeType: 'last_7_days' } }],
  userParams: { period: null },
  resolutionContext: context,
}), {});
```

Add cases for invalid values, disabled bindings, cleared unified overrides, custom dates, no lower-priority fallback after effective null, and exact `timeRange` regression. Assert `buildWidgetRequestParams` and `buildWidgetRequestSignatureParams` return identical resolved date tuples when passed one context.

- [ ] **Step 2: Run RED**

Add `"test:ops-analysis-date-range-request": "pnpm exec tsx scripts/ops-analysis-date-range-request-test.ts"` and run it.

Expected: FAIL because `processDataSourceParams` sends rule objects unchanged.

- [ ] **Step 3: Add one omission-aware conversion boundary**

Use an explicit sentinel so `null`/invalid date ranges delete the key rather than becoming a value:

```ts
export const OMIT_DATA_SOURCE_PARAM = Symbol('omit-data-source-param');

export const formatDataSourceParamValue = (
  type: string,
  value: unknown,
  context: DateRangeResolutionContext,
): unknown | typeof OMIT_DATA_SOURCE_PARAM => {
  if (type === 'dateRange') {
    return resolveDateRange(value, context) ?? OMIT_DATA_SOURCE_PARAM;
  }
  return type === 'timeRange' ? formatTimeRange(value) : value;
};
```

Apply it after precedence chooses the effective value. Do not let a null params/filter value fall through to the data-source default. Keep disabled bindings as omission.

- [ ] **Step 4: Thread one resolution context through every request entry**

Add `resolutionContext` to `processDataSourceParams`, `buildWidgetRequestParams`, and `buildWidgetRequestSignatureParams`. In `widgetDataRenderer.tsx`, memoize one context for a request cycle and pass the same object to both builders:

```ts
const dateRangeResolutionContext = useMemo(() => ({
  referenceNow: Date.now(),
  timezone: getDateRangeTimezone(),
}), [reloadVersion, filterSearchVersion, namespaceSearchVersion, tableQueryKey]);
```

Pass an explicit context from `useSingleValueConfig` and `useTableConfig` where they call `processDataSourceParams`. Do not introduce a midnight timer.

- [ ] **Step 5: Verify request and cache-signature behavior**

Run: `pnpm test:ops-analysis-date-range-request && pnpm test:ops-analysis-date-range-domain`

Expected: PASS, including resolved arrays in both request and signature.

Run existing component-switch and unified-filter tests; expected PASS.

Run: `pnpm exec eslint src/app/ops-analysis/utils/widgetDataTransform.ts src/app/ops-analysis/components/widgetDataRenderer.tsx src/app/ops-analysis/hooks/useSingleValueConfig.ts src/app/ops-analysis/components/widgetConfig/hooks/useTableConfig.ts scripts/ops-analysis-date-range-request-test.ts`

Expected: PASS with no errors.

- [ ] **Step 6: Commit request integration**

```bash
git add web/package.json web/src/app/ops-analysis/utils/widgetDataTransform.ts web/src/app/ops-analysis/components/widgetDataRenderer.tsx web/src/app/ops-analysis/hooks/useSingleValueConfig.ts web/src/app/ops-analysis/components/widgetConfig/hooks/useTableConfig.ts web/scripts/ops-analysis-date-range-request-test.ts
git commit -m "feat: resolve date ranges in widget requests"
```

### Task 8: Import precheck, final scope guard, and full verification

**Files:**
- Modify: `server/apps/operation_analysis/schemas/import_export_schema.py`
- Modify: `server/apps/operation_analysis/services/import_export/precheck_service.py`
- Create: `server/apps/operation_analysis/tests/test_date_range_import_precheck.py`
- Create: `web/scripts/ops-analysis-date-range-scope-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: the same canonical discriminator list and structural rules documented by the frontend validator.
- Produces: import precheck rejection for invalid persisted date-range rules while leaving request execution opaque to the backend.
- Produces: a final regression/scope check proving all required registration sites exist and excluded subsystems remain untouched.

- [ ] **Step 1: Add failing import-precheck tests**

Add data-source YAML cases whose `params` contain a valid quick rule, valid custom rule, null, unknown discriminator, malformed date, reversed date, and conflicting quick/custom fields:

```python
import yaml
import pytest

from apps.operation_analysis.constants.import_export import YAML_SCHEMA_VERSION
from apps.operation_analysis.services.import_export.precheck_service import PrecheckService

def _precheck(value):
    document = {
        "meta": {
            "schema_version": YAML_SCHEMA_VERSION,
            "object_counts": {"total": 1, "by_type": {"datasources": 1}},
        },
        "datasources": [{
            "key": "cost::cloud_cost/query",
            "name": "cost",
            "rest_api": "cloud_cost/query",
            "params": [{
                "name": "period", "alias_name": "Period", "type": "dateRange",
                "filterType": "filter", "value": value,
            }],
        }],
    }
    return PrecheckService.precheck(yaml.safe_dump(document))

@pytest.mark.parametrize("value", [
    {"rangeType": "last_30_days"},
    {"rangeType": "custom", "startDate": "2026-07-01", "endDate": "2026-07-17"},
    None,
])
def test_import_precheck_accepts_valid_date_range_values(value):
    assert _precheck(value)["valid"] is True

@pytest.mark.parametrize("value", [
    {"rangeType": "last30days"},
    {"rangeType": "custom", "startDate": "2026-07-17", "endDate": "2026-07-01"},
    {"rangeType": "last_7_days", "startDate": "2026-07-01", "endDate": "2026-07-17"},
])
def test_import_precheck_rejects_invalid_date_range_values(value):
    result = _precheck(value)
    assert result["valid"] is False
    assert any("dateRange" in error["message"] for error in result["errors"])
```

- [ ] **Step 2: Run backend RED without configured coverage addopts**

Run from `server`: `uv run pytest -o addopts= apps/operation_analysis/tests/test_date_range_import_precheck.py -q`

Expected: FAIL because import precheck does not validate date-range values.

- [ ] **Step 3: Add configuration-only schema validation**

Add a small schema helper that validates only data-source parameter objects with `type == "dateRange"`. Invoke it during precheck before conflict analysis. Keep export pass-through unchanged and do not alter `get_source_data`, NATS services, serializers for request payloads, or backend date conversion.

- [ ] **Step 4: Add the final frontend scope test**

Implement the scope script with `readFileSync` and explicit assertions for:

```ts
assert.equal((paramTableSource.match(/value:\s*["']dateRange["']/g) ?? []).length, 1);
for (const key of DATE_RANGE_TYPES) {
  assert.equal(typeof en.dateRange[key], 'string');
  assert.equal(typeof zh.dateRange[key], 'string');
}
for (const source of [dashboardSyncSource, screenLayoutSource, topologyNamespaceSource]) {
  assert.match(source, /BindableParamType/);
}
assert.match(widgetTransformSource, /resolveDateRange/);
for (const source of [reportSource, compareSource, tableSettingsSource]) {
  assert.doesNotMatch(source, /dateRange/);
}
for (const source of [dateRangeDomainSource, dateRangeSelectorSource]) {
  assert.doesNotMatch(source, /toISOString\(\)|formatTimeRange|TimeSelector/);
}
```

Add `"test:ops-analysis-date-range-scope": "pnpm exec tsx scripts/ops-analysis-date-range-scope-test.ts"`.

- [ ] **Step 5: Run all focused frontend tests**

Run from `web`:

```bash
pnpm test:ops-analysis-date-range-domain
pnpm test:ops-analysis-date-range-selector
pnpm test:ops-analysis-date-range-data-source
pnpm test:ops-analysis-params-date-range
pnpm test:ops-analysis-date-range-unified-filter
pnpm test:ops-analysis-date-range-canvas-binding
pnpm test:ops-analysis-date-range-request
pnpm test:ops-analysis-date-range-scope
pnpm test:ops-analysis-unified-filter-input
pnpm test:ops-analysis-component-param-switch
pnpm exec tsx scripts/ops-analysis-params-time-range-test.ts
```

Expected: every command PASS.

- [ ] **Step 6: Run backend, type, lint, and diff checks**

Run from `server`: `uv run pytest -o addopts= apps/operation_analysis/tests/test_date_range_import_precheck.py -q`

Expected: all date-range import tests PASS.

Run from `web`: `pnpm exec tsc -p tsconfig.lint.json --noEmit`

Expected: no new ops-analysis errors. If unrelated existing errors remain, record them verbatim and verify none point to files in this plan.

Run from repository root:

```bash
git diff --check
rg -n "dateRange" web/src/app/ops-analysis/\(pages\)/view/report web/src/app/ops-analysis/utils/compareQuery.ts web/src/app/ops-analysis/components/widgetConfig/sections/tableSettingsSection.tsx
```

Expected: `git diff --check` passes and the scoped `rg` returns no matches.

- [ ] **Step 7: Commit final validation and scope guard**

```bash
git add server/apps/operation_analysis/schemas/import_export_schema.py server/apps/operation_analysis/services/import_export/precheck_service.py server/apps/operation_analysis/tests/test_date_range_import_precheck.py web/package.json web/scripts/ops-analysis-date-range-scope-test.ts
git commit -m "test: validate date range configuration scope"
```

## Final Acceptance Checklist

- [ ] A new NATS parameter can select `dateRange`, initializes to `last_7_days`, saves a canonical rule, and echoes the same rule on edit.
- [ ] Custom selection persists only strict `YYYY-MM-DD`; clear persists `null`; invalid persisted data remains visible with an error.
- [ ] Component parameters and unified filters use the dedicated selector and never emit timestamps or ISO datetime strings.
- [ ] Dashboard, Screen, and Topology discover and bind `dateRange` by exact name+type; `timeRange` bindings do not cross-match.
- [ ] Fixed, unified-filter, component, and default paths resolve immediately before requests to inclusive date-only arrays.
- [ ] Effective null and invalid values are omitted without lower-priority/default fallback.
- [ ] Request payload and cache signature share one resolved tuple per request cycle.
- [ ] Backend request execution receives an ordinary JSON array and has no `dateRange` request parser.
- [ ] Reports, period comparison, table `time_range`, URL sharing, non-NATS parameter editors, and mandatory-state behavior are unchanged.

## specs: 2026-07-17-date-range-parameter-design.md

## Goal

Add a `dateRange` data-source parameter type for natural business-date ranges without reusing `timeRange` timestamp, minute-offset, or UTC behavior.

This document covers design only. It does not include implementation.

## Scope

The first release supports:

- NATS data-source parameter type selection, configuration, defaults, persistence, validation, and edit echo;
- component-level parameter values and request generation;
- unified-filter configuration, binding, persistence, and runtime override;
- unified-filter hosts currently used by Dashboard, Screen, and Topology;
- data-source import/export validation and generic canvas configuration pass-through.

The first release does not add or extend:

- report-canvas behavior, report filters, report scheduling, or report-specific configuration;
- REST, MySQL, PostgreSQL, or Excel parameter configuration;
- `timeRange` period comparison;
- table `inputType=time_range`;
- URL/shared-link parameters;
- enterprise-specific quick ranges.

## Parameter type registration

The first release adds the exact parameter type identifier:

```ts
type: "dateRange"
```

For supported NATS data-source parameter configuration, `dateRange` participates in the same parameter-type selection mechanism as the existing types. The selectable type list becomes:

```text
string
number
boolean
date
timeRange
dateRange
```

Selecting `dateRange` activates its configuration, persistence, edit-echo, selector, validation, and request-resolution paths. It is not a runtime-only type. Parameter-type lists outside the first-release scope are not expanded automatically.

## Date semantics

`dateRange` represents natural dates and never time instants. Its resolved request value is an inclusive, ordered pair of `YYYY-MM-DD` strings:

```json
["2026-07-01", "2026-07-17"]
```

Both endpoints are included. The frontend does not append start-of-day, end-of-day, timezone offsets, ISO timestamps, or UTC markers. A receiving NATS method owns the business meaning of applying these dates to date or datetime fields.

The generic selector allows same-day ranges, future dates, and arbitrary span lengths. It validates only date format and `startDate <= endDate`. Data-source-specific restrictions belong to separate business validation.

## Quick ranges

The canonical quick-rule discriminator is a closed string union:

```ts
type DateRangeType =
  | "today"
  | "yesterday"
  | "this_week"
  | "last_week"
  | "this_month"
  | "last_month"
  | "last_7_days"
  | "last_30_days"
  | "last_90_days"
  | "custom";
```

`DateRangeValue.rangeType` must use `DateRangeType`. UI options, persisted values, validation, edit echo, and request-time resolution use these exact identifiers; aliases and spelling variants are invalid.

Supported quick rules are:

- today;
- yesterday;
- this week;
- last week;
- this month;
- last month;
- last 7 days;
- last 30 days;
- last 90 days;
- custom.

Their semantics are fixed:

- weeks start on Monday, independent of locale;
- this week is Monday through today;
- last week is the previous complete Monday-through-Sunday week;
- this month is the first day of the current month through today;
- last month is the previous complete calendar month;
- rolling N-day ranges include today and therefore start at `today - (N - 1)` days.

## Value models

Persisted values and resolved request values are separate types.

Quick persisted value:

```json
{
  "rangeType": "last_30_days"
}
```

Custom persisted value:

```json
{
  "rangeType": "custom",
  "startDate": "2026-07-01",
  "endDate": "2026-07-17"
}
```

Empty value:

```json
null
```

Resolved runtime value:

```json
["2026-06-18", "2026-07-17"]
```

The persisted field must never alternate between a rule object and a resolved array. Dayjs values, JavaScript `Date`, timestamps, and ISO datetime strings must not cross the selector boundary or be persisted.

## Defaults and clearing

- `dateRange` is an optional parameter type with no mandatory state, field, configuration switch, or validation dependency.
- A newly initialized `dateRange` defaults to `{ "rangeType": "last_7_days" }`. This is the type's own initial value, not a mandatory-value fallback.
- A user may explicitly clear the selector. Clearing emits and persists `null`, meaning unconfigured, explicitly cleared, or currently without an effective date range.
- A `null` effective value is omitted from request parameters. Request construction does not replace it with `last_7_days`.
- Switching another parameter type to `dateRange` discards the incompatible old value and initializes `last_7_days`.
- Switching `dateRange` to another type discards the rule object and uses the target type's existing initialization behavior.
- No conversion between `timeRange` and `dateRange` is attempted.

## Selector interaction

`DateRangeSelector` is a dedicated control and does not reuse `TimeSelector`.

- When initialized without an existing persisted value, it displays and emits the `last_7_days` default rule.
- Selecting a quick item immediately emits its rule object.
- Selecting custom opens the date-range panel without changing the current business value.
- A one-sided custom selection remains internal UI state and is not emitted or persisted.
- Completing both dates emits one valid custom rule object.
- Cancelling or closing an incomplete custom selection preserves the value that existed before custom was opened.
- Only an explicit clear action emits `null`; opening, cancelling, or closing an incomplete custom selection does not clear the current value.

The selector may use Dayjs internally to drive Ant Design controls, but its external API is `DateRangeValue | null`.

## Validation

Validation is strict and centralized.

Valid custom dates must:

- contain both `startDate` and `endDate`;
- match `YYYY-MM-DD` exactly;
- represent real calendar dates;
- satisfy `startDate <= endDate`.

The validator rejects:

- unknown `rangeType` values;
- incomplete custom values;
- ISO datetime strings;
- timestamps;
- invalid calendar dates;
- reversed ranges;
- conflicting fields on quick-rule objects.

Handling by stage:

- configuration save and import precheck accept `null` but reject invalid non-null values with field-level errors;
- edit echo preserves and displays invalid persisted values rather than silently replacing them;
- runtime omits the invalid parameter from the request and reports a configuration error without blocking unrelated parameters or silently applying a default.

Invalid persisted data is not silently converted to `last_7_days`. Explicit clearing and invalid-data recovery are separate behaviors.

## Timezone and rule resolution

Quick rules are resolved immediately before each request.

The authoritative timezone is the current user's configured timezone. If no reliable configured timezone is available, resolution explicitly falls back to the browser timezone.

`resolveDateRange` accepts the rule, a reference instant, and timezone context. It returns one `ResolvedDateRange`. Centralizing these inputs makes date behavior deterministic and testable.

Resolution must not call `toISOString()` or convert dates through UTC. Week calculations must explicitly use Monday as the first day rather than inheriting a locale default.

## Runtime request flow

```text
DateRangeValue | null
        |
        v
validateDateRangeValue
        |
        +---- null or invalid ----> omit request parameter
        |
        +---- valid rule --------> resolveDateRange(value, referenceNow, timezone)
                                        |
                                        v
                                ResolvedDateRange
                                        |
                                        +----> request parameters
                                        |
                                        +----> request signature/cache key
```

One request build resolves a rule once and shares the resulting tuple between request parameters and request-signature construction. This prevents midnight races where the request and signature represent different dates.

No new midnight timer is introduced. A page crossing midnight updates on its next manual refresh, scheduled refresh, or other real request. Because the request signature uses resolved dates, it changes naturally after the user's local date changes.

The backend remains unaware of the parameter type and receives an ordinary JSON array in the existing NATS request payload.

## Parameter precedence

The existing parameter flow and precedence remain in place:

```text
fixed
  > enabled unified-filter override
  > component params value
  > data-source default
```

Even a fixed quick rule is resolved again for every request; fixed means user read-only, not calendar-static.

Within the mutable parameter chain, the existing precedence remains unified-filter override, then component parameter value, then data-source default. Precedence selects the effective value; it does not add a mandatory-value fallback. If the selected effective value is `null`, request construction omits the parameter instead of falling through to a lower-priority value or synthesizing `last_7_days`.

## Unified-filter integration

Unified-filter discovery expands from `string | timeRange` to `string | timeRange | dateRange`.

Bindings require exact parameter name and exact type:

- `dateRange` binds only to `dateRange`;
- `timeRange` binds only to `timeRange`;
- existing `timeRange` bindings are not migrated;
- changing a parameter's type removes incompatible bindings before normal automatic matching runs.

Dashboard, Screen, and Topology use the same `DateRangeValue`, selector, validation, resolution, and binding rules. Their layout restoration code may recognize the new type, but must not implement separate date calculations.

## Import and export

Data-source export preserves the rule object unchanged. Import precheck validates it with the same centralized validator used by configuration save.

Generic Dashboard, Screen, and Topology configuration import/export may pass valid values through existing structures. No report-canvas import/export behavior is added.

## Relationship to `timeRange`

The new type reuses:

- parameter-type registration and selection;
- data-source configuration and persistence;
- component parameter injection;
- edit echo;
- unified-filter discovery and binding structure;
- request-parameter aggregation.

It does not reuse:

- `TimeSelector`;
- minute-based quick values;
- timestamp or ISO conversion;
- UTC conversion;
- `formatTimeRange`;
- `timeRange` comparison behavior.

The design uses a focused date-range domain module rather than refactoring every parameter type into a new generic plugin registry. A registry-wide refactor is outside scope.

## Testing strategy

### Resolution

Use fixed reference instants and explicit timezones to cover today, yesterday, Monday/Sunday week boundaries, cross-month last weeks, first-of-month behavior, cross-year last months, rolling 7/30/90-day ranges, configured-timezone differences, browser fallback, and daylight-saving transitions.

### Validation

Cover every legal quick rule, valid custom and same-day ranges, future dates, `null`, invalid formats, ISO strings, timestamps, incomplete custom values, reversed ranges, invalid calendar dates, unknown rules, and conflicting fields.

### Configuration and selector behavior

Cover `last_7_days` initialization, quick and custom save/echo, type switching, incomplete-custom cancellation, explicit clearing to `null`, invalid-value display, and fixed read-only behavior.

### Unified filters

Cover exact-type matching, binding cleanup after type changes, clearing to an effective `null` without lower-priority fallback, and definition restoration across Dashboard, Screen, and Topology.

### Request construction

Cover fixed, params, and filter paths; request-time resolution; date-only arrays; omission of `null` and invalid values; shared request/signature resolution; cross-midnight signature changes; and regression coverage proving `timeRange` behavior is unchanged.

## Non-goals

This change does not normalize or refactor the existing `timeRange` mixed model. It does not complete or modify the existing parameter mandatory-state capability. It does not add backend date parsing, business-date-to-datetime conversion, generic date limits, report scheduling, new REST query serialization, or enterprise-only presets.
