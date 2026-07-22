# Historical Superpowers change: 2026-07-08-monitor-formula-result-unit

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-08-monitor-formula-result-unit.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为监控告警策略公式指标增加“结果单位”配置，并让阈值单位以公式结果单位为基准。

**Architecture:** 复用现有 `calculation_unit` 字段表达公式结果单位。把单位筛选、默认值、回退逻辑放到 `strategyDetailUtils.ts` 纯函数中，页面和组件只负责状态传递与展示。公式编辑器新增结果单位下拉，阈值配置改用公式结果单位作为过滤基准。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design、pnpm、tsx 脚本测试。

## Global Constraints

- 只改 `web/` 监控告警策略创建/编辑相关文件。
- 不新增单位体系或单位换算规则。
- 不改变单指标策略的单位推导行为。
- 不改变公式表达式语法、查询构建或后端扫描计算逻辑。
- 不支持自动分析公式并推导单位。
- 公式模式默认结果单位为 `percent`，展示为 `%`。
- 公式策略保存 `calculation_unit`，`metric_unit` 保持为空。
- 单位下拉排除 `none`、`short`。
- 新功能和 bugfix 先写测试，最后运行 `cd web && pnpm lint && pnpm type-check`。

---

## File Structure

- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
  - 新增公式结果单位默认值、有效单位过滤、阈值单位选项计算等纯函数。
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
  - 覆盖新增纯函数，保护默认 `%`、过滤无效单位、公式/单指标单位基准差异。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
  - 在公式表达式右侧渲染“结果单位”下拉。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
  - 接收并透传公式结果单位和单位列表。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`
  - 使用纯函数计算阈值单位选项，公式模式下以 `calculationUnit` 为基准。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
  - 在公式模式初始化、切换、编辑回填、保存时统一维护 `calculationUnit`。
- Modify: `web/package.json`
  - 如现有脚本已包含 `test:monitor-policy-formula-payload`，本任务不新增脚本；用既有 `test:monitor-strategy-detail-logic` 风格时可新增 `"test:monitor-strategy-detail-logic"`。

---

### Task 1: Add Unit Decision Helpers And Tests

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
- Modify: `web/package.json`

**Interfaces:**
- Produces: `FORMULA_DEFAULT_RESULT_UNIT: 'percent'`
- Produces: `getValidThresholdUnitOptions(unitList: UnitListItem[]): UnitListItem[]`
- Produces: `resolveFormulaResultUnit(unit: string | null | undefined, unitList: UnitListItem[]): string`
- Produces: `getThresholdUnitFilterBase(options): string | null`
- Produces: `getThresholdUnitOptions(options): UnitListItem[]`
- Consumes: `UnitListItem` from `@/app/monitor/types`

- [ ] **Step 1: Write failing tests for formula result unit helpers**

Replace `web/scripts/monitor-strategy-detail-logic-test.ts` with:

```ts
import assert from 'node:assert/strict';

import {
  FORMULA_DEFAULT_RESULT_UNIT,
  getThresholdUnitFilterBase,
  getThresholdUnitOptions,
  getValidThresholdUnitOptions,
  resolveFormulaResultUnit,
  resolveInitialMetricPluginId,
} from '../src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils';
import { UnitListItem } from '../src/app/monitor/types';

const plugins = [
  { label: '主机（Telegraf）', value: 1 },
  { label: 'Windows WMI', value: 2 },
  { label: '主机远程采集（Telegraf）', value: 3 },
];

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: 3,
}), 3);

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: '3',
}), 3);

assert.equal(resolveInitialMetricPluginId({
  type: 'add',
  pluginList: plugins,
  policyCollectType: 3,
}), 1);

assert.equal(resolveInitialMetricPluginId({
  type: 'edit',
  pluginList: plugins,
  policyCollectType: 99,
}), 1);

const unitList: UnitListItem[] = [
  {
    unit_id: 'none',
    unit_name: '无单位',
    display_unit: '',
    category: 'Base',
    system: 'none',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'short',
    unit_name: '短数字',
    display_unit: '',
    category: 'Base',
    system: 'short',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'percent',
    unit_name: '百分比',
    display_unit: '%',
    category: 'Base',
    system: 'percent',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'bytes',
    unit_name: '字节',
    display_unit: 'B',
    category: 'Data',
    system: 'bytes',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'kilobytes',
    unit_name: '千字节',
    display_unit: 'KB',
    category: 'Data',
    system: 'bytes',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'milliseconds',
    unit_name: '毫秒',
    display_unit: 'ms',
    category: 'Time',
    system: 'time',
    description: '',
    is_standalone: false,
  },
  {
    unit_id: 'watts',
    unit_name: '瓦特',
    display_unit: 'W',
    category: 'Power',
    system: null as unknown as string,
    description: '',
    is_standalone: true,
  },
];

assert.equal(FORMULA_DEFAULT_RESULT_UNIT, 'percent');
assert.deepEqual(
  getValidThresholdUnitOptions(unitList).map((item) => item.unit_id),
  ['percent', 'bytes', 'kilobytes', 'milliseconds', 'watts']
);

assert.equal(resolveFormulaResultUnit(null, unitList), 'percent');
assert.equal(resolveFormulaResultUnit('', unitList), 'percent');
assert.equal(resolveFormulaResultUnit('none', unitList), 'percent');
assert.equal(resolveFormulaResultUnit('short', unitList), 'percent');
assert.equal(resolveFormulaResultUnit('bytes', unitList), 'bytes');
assert.equal(resolveFormulaResultUnit('unknown-unit', unitList), 'percent');

assert.equal(
  getThresholdUnitFilterBase({
    isFormulaMode: true,
    formulaResultUnit: 'percent',
    selectedMetricUnit: 'bytes',
  }),
  'percent'
);
assert.equal(
  getThresholdUnitFilterBase({
    isFormulaMode: false,
    formulaResultUnit: 'percent',
    selectedMetricUnit: 'bytes',
  }),
  'bytes'
);
assert.equal(
  getThresholdUnitFilterBase({
    isFormulaMode: false,
    formulaResultUnit: 'percent',
    selectedMetricUnit: null,
  }),
  null
);

assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'percent',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['percent']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'bytes',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['bytes', 'kilobytes']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'watts',
    isEnumMetric: false,
  }).map((item) => item.unit_id),
  ['watts']
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'bytes',
    isEnumMetric: true,
  }),
  []
);
assert.deepEqual(
  getThresholdUnitOptions({
    unitList,
    unitFilterBase: 'none',
    isEnumMetric: false,
  }),
  []
);

console.log('monitor-strategy-detail logic validation passed');
```

- [ ] **Step 2: Add or confirm package script**

If `web/package.json` does not already contain this script, add it under `"scripts"`:

```json
"test:monitor-strategy-detail-logic": "pnpm exec tsx scripts/monitor-strategy-detail-logic-test.ts"
```

- [ ] **Step 3: Run test and verify it fails**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
```

Expected: FAIL because `FORMULA_DEFAULT_RESULT_UNIT` and the new helper functions are not exported yet.

- [ ] **Step 4: Implement unit helper functions**

Append these exports to `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts` after `resolveInitialMetricPluginId`:

```ts
import { UnitListItem } from '@/app/monitor/types';

export const FORMULA_DEFAULT_RESULT_UNIT = 'percent';

const INVALID_THRESHOLD_UNIT_IDS = new Set(['none', 'short']);

export const getValidThresholdUnitOptions = (
  unitList: UnitListItem[]
): UnitListItem[] =>
  unitList.filter((item) => !INVALID_THRESHOLD_UNIT_IDS.has(item.unit_id));

export const resolveFormulaResultUnit = (
  unit: string | null | undefined,
  unitList: UnitListItem[]
): string => {
  const validUnits = getValidThresholdUnitOptions(unitList);
  const unitIds = new Set(validUnits.map((item) => item.unit_id));

  if (unit && unitIds.has(unit)) {
    return unit;
  }

  return FORMULA_DEFAULT_RESULT_UNIT;
};

export const getThresholdUnitFilterBase = ({
  isFormulaMode,
  formulaResultUnit,
  selectedMetricUnit,
}: {
  isFormulaMode: boolean;
  formulaResultUnit: string | null;
  selectedMetricUnit: string | null;
}): string | null => {
  if (isFormulaMode) {
    return formulaResultUnit || FORMULA_DEFAULT_RESULT_UNIT;
  }
  return selectedMetricUnit;
};

export const getThresholdUnitOptions = ({
  unitList,
  unitFilterBase,
  isEnumMetric,
}: {
  unitList: UnitListItem[];
  unitFilterBase: string | null;
  isEnumMetric: boolean;
}): UnitListItem[] => {
  if (isEnumMetric || !unitFilterBase) return [];

  const validUnits = getValidThresholdUnitOptions(unitList);
  const baseUnit = validUnits.find((item) => item.unit_id === unitFilterBase);
  if (!baseUnit) return [];

  if (baseUnit.system === null) {
    return validUnits.filter((item) => item.unit_id === baseUnit.unit_id);
  }

  return validUnits.filter((item) => item.system === baseUnit.system);
};
```

If the file already has imports, merge `UnitListItem` into the existing import block instead of creating a second import below executable code.

- [ ] **Step 5: Run helper test and verify it passes**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic
```

Expected: PASS and prints `monitor-strategy-detail logic validation passed`.

- [ ] **Step 6: Commit task 1**

Run:

```bash
git add web/src/app/monitor/'(pages)'/event/strategy/detail/strategyDetailUtils.ts web/scripts/monitor-strategy-detail-logic-test.ts web/package.json
git commit -m "test(monitor): 覆盖公式结果单位决策"
```

---

### Task 2: Wire Formula Result Unit Through UI

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`

**Interfaces:**
- Consumes: `FORMULA_DEFAULT_RESULT_UNIT`, `getThresholdUnitFilterBase`, `getThresholdUnitOptions`, `getValidThresholdUnitOptions`, `resolveFormulaResultUnit`
- Produces: `MetricExpressionEditor` props `resultUnit`, `unitOptions`, `onResultUnitChange`
- Produces: `MetricDefinitionForm` props `resultUnit`, `unitOptions`, `onResultUnitChange`
- Produces: `AlertConditionsForm` prop `isFormulaMode`

- [ ] **Step 1: Extend `MetricExpressionEditor` props**

In `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`, import `UnitListItem` and extend props:

```ts
import {
  FilterItem,
  IndexViewItem,
  ListItem,
  MetricItem,
  UnitListItem
} from '@/app/monitor/types';
```

```ts
interface MetricExpressionEditorProps {
  rows: MetricExpressionRow[];
  mode: MetricExpressionMode;
  resultName: string;
  expression: string;
  resultUnit: string | null;
  unitOptions: UnitListItem[];
  labelsByRef: Record<string, string[]>;
  originMetricData: IndexViewItem[];
  groupByOptions: string[];
  groupMethods: ListItem[];
  conditionMethods: ListItem[];
  metricsLoading: boolean;
  onRowsChange: (rows: MetricExpressionRow[]) => void;
  onResultNameChange: (value: string) => void;
  onExpressionChange: (value: string) => void;
  onResultUnitChange: (value: string) => void;
}
```

Destructure the new props:

```ts
  resultUnit,
  unitOptions,
  onResultUnitChange
```

- [ ] **Step 2: Render result unit select beside expression**

Replace the formula footer grid with:

```tsx
<div className="grid grid-cols-[2rem_minmax(0,220px)_16px_minmax(0,1fr)_96px] items-center gap-2 border-t border-[var(--color-border-2)] bg-[rgba(255,255,255,0.68)] px-3 py-3">
  <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]">
    fx
  </span>
  <Input
    className="min-w-0"
    value={resultName}
    placeholder={t('monitor.events.formulaResultNamePlaceholder')}
    onChange={(event) => onResultNameChange(event.target.value)}
  />
  <span className="text-center text-[var(--color-text-3)]">=</span>
  <Input
    className="min-w-0"
    value={expression}
    placeholder="a / b * 100"
    onChange={(event) => onExpressionChange(event.target.value)}
  />
  <Select
    className="w-full"
    showSearch
    value={resultUnit}
    aria-label={translateWithFallback('monitor.events.formulaResultUnit', '结果单位')}
    placeholder={translateWithFallback('monitor.events.formulaResultUnit', '结果单位')}
    options={unitOptions.map((option) => ({
      label: option.display_unit || option.unit_name,
      value: option.unit_id
    }))}
    filterOption={(input, option) =>
      (option?.label || '')
        .toString()
        .toLowerCase()
        .includes(input.toLowerCase())
    }
    onChange={onResultUnitChange}
  />
</div>
```

- [ ] **Step 3: Extend `MetricDefinitionForm` props and pass through**

In `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`, import `UnitListItem`:

```ts
import { SegmentedItem, IndexViewItem, UnitListItem } from '@/app/monitor/types';
```

Extend props:

```ts
  resultUnit: string | null;
  unitOptions: UnitListItem[];
  onResultUnitChange: (value: string) => void;
```

Destructure the new props and pass them to `MetricExpressionEditor`:

```tsx
<MetricExpressionEditor
  rows={metricRows}
  mode={metricExpressionMode}
  resultName={resultName}
  expression={expression}
  resultUnit={resultUnit}
  unitOptions={unitOptions}
  labelsByRef={labelsByRef}
  originMetricData={originMetricData}
  groupByOptions={groupByOptions}
  groupMethods={GROUP_METHOD_LIST}
  conditionMethods={CONDITION_LIST}
  metricsLoading={metricsLoading}
  onRowsChange={onMetricRowsChange}
  onResultNameChange={onResultNameChange}
  onExpressionChange={onExpressionChange}
  onResultUnitChange={onResultUnitChange}
/>
```

- [ ] **Step 4: Update threshold unit option logic**

In `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`, import helpers:

```ts
import {
  getThresholdUnitFilterBase,
  getThresholdUnitOptions
} from './strategyDetailUtils';
```

Extend props:

```ts
  isFormulaMode: boolean;
```

Destructure `isFormulaMode`, then replace `filteredUnitOptions` with:

```ts
const unitFilterBase = useMemo(
  () =>
    getThresholdUnitFilterBase({
      isFormulaMode,
      formulaResultUnit: calculationUnit,
      selectedMetricUnit: metricUnit
    }),
  [isFormulaMode, calculationUnit, metricUnit]
);

const filteredUnitOptions = useMemo(
  () =>
    getThresholdUnitOptions({
      unitList,
      unitFilterBase,
      isEnumMetric
    }),
  [unitList, unitFilterBase, isEnumMetric]
);
```

- [ ] **Step 5: Wire page state defaults and edit fallback**

In `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`, import helpers:

```ts
import {
  FORMULA_DEFAULT_RESULT_UNIT,
  getValidThresholdUnitOptions,
  resolveFormulaResultUnit,
  resolveInitialMetricPluginId
} from './strategyDetailUtils';
```

Create unit options near existing `commonContext` usage:

```ts
const unitList = commonContext?.unitList || [];
const validThresholdUnitOptions = useMemo(
  () => getValidThresholdUnitOptions(unitList),
  [unitList]
);
```

In `dealDetail`, replace:

```ts
setCalculationUnit(filterInvalidUnit(calculation_unit));
```

with:

```ts
setCalculationUnit(filterInvalidUnit(calculation_unit));
```

Keep this unchanged for now; formula-specific fallback happens after query condition is known in `processMetricData`.

In `processMetricData`, inside the formula branch after setting `setMetricExpressionMode('formula');`, add:

```ts
setCalculationUnit(
  resolveFormulaResultUnit(data.calculation_unit as string | null, unitList)
);
```

In `handleMetricRowsChange`, compute next mode and default formula unit:

```ts
const nextMode = getMetricExpressionModeForRows(rows);
setMetricExpressionMode(nextMode);
setMetricRows(rows);

if (nextMode === 'formula') {
  setCalculationUnit((current) =>
    resolveFormulaResultUnit(current, unitList)
  );
}
```

Use `nextMode` instead of calling `getMetricExpressionModeForRows(rows)` twice.

Add a handler:

```ts
const handleFormulaResultUnitChange = (unit: string) => {
  setCalculationUnit(unit);
  form.validateFields(['threshold']);
};
```

Pass formula result unit props to `MetricDefinitionForm`:

```tsx
resultUnit={
  metricExpressionMode === 'formula'
    ? calculationUnit || FORMULA_DEFAULT_RESULT_UNIT
    : calculationUnit
}
unitOptions={validThresholdUnitOptions}
onResultUnitChange={handleFormulaResultUnitChange}
```

Pass formula mode to `AlertConditionsForm`:

```tsx
isFormulaMode={metricExpressionMode === 'formula'}
```

In `createStrategy`, replace metric unit assignment with:

```ts
params.metric_unit =
  metricExpressionMode === 'formula' ||
  metricRows.length > 1 ||
  isStringArray(mertricTarget?.unit)
    ? ''
    : mertricTarget?.unit;
```

Before assigning `params.calculation_unit`, add:

```ts
const nextCalculationUnit =
  metricExpressionMode === 'formula'
    ? resolveFormulaResultUnit(calculationUnit, unitList)
    : calculationUnit || '';
```

Then set:

```ts
params.calculation_unit = nextCalculationUnit;
```

- [ ] **Step 6: Run targeted TypeScript scripts**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic && pnpm test:monitor-policy-formula-payload
```

Expected: both PASS.

- [ ] **Step 7: Commit task 2**

Run:

```bash
git add web/src/app/monitor/'(pages)'/event/strategy/detail/metricExpressionEditor.tsx web/src/app/monitor/'(pages)'/event/strategy/detail/metricDefinitionForm.tsx web/src/app/monitor/'(pages)'/event/strategy/detail/alertConditionsForm.tsx web/src/app/monitor/'(pages)'/event/strategy/detail/page.tsx
git commit -m "feat(monitor): 配置公式结果单位"
```

---

### Task 3: Gate Verification

**Files:**
- Verify: `web/src/app/monitor/(pages)/event/strategy/detail/*`
- Verify: `web/scripts/monitor-strategy-detail-logic-test.ts`
- Verify: `web/scripts/monitor-policy-formula-payload-test.ts`

**Interfaces:**
- Consumes: completed Task 1 and Task 2.
- Produces: verified implementation ready for review.

- [ ] **Step 1: Run focused monitor tests**

Run:

```bash
cd web && pnpm test:monitor-strategy-detail-logic && pnpm test:monitor-policy-formula-payload
```

Expected: both PASS.

- [ ] **Step 2: Run module gate**

Run:

```bash
cd web && pnpm lint && pnpm type-check
```

Expected: both PASS.

- [ ] **Step 3: Inspect final diff**

Run:

```bash
git diff --stat HEAD~2..HEAD
git diff --check HEAD~2..HEAD
```

Expected: changed files are limited to the strategy detail UI, helper test/script, and package script if needed; `git diff --check` prints no whitespace errors.

- [ ] **Step 4: Commit verification note if any fix was needed**

If Step 1 or Step 2 required a fix, commit the fix:

```bash
git add web/src/app/monitor/'(pages)'/event/strategy/detail web/scripts/monitor-strategy-detail-logic-test.ts web/package.json
git commit -m "fix(monitor): 收口公式结果单位校验"
```

If no fix was needed, do not create an empty commit.

---

## Self-Review

- Spec coverage: plan covers formula result unit selector, default `%`, threshold unit base switch, edit fallback, `calculation_unit` save semantics, `metric_unit` remaining empty for formula, and single-metric non-regression.
- Placeholder scan: no deferred implementation placeholders are present.
- Type consistency: helper names and component prop names are consistent across tasks.
- Scope check: implementation is limited to the web strategy detail flow and existing script tests.

## specs: 2026-07-08-monitor-formula-result-unit-design.md

## 背景

告警策略创建页支持通过多个指标组合公式生成计算指标，例如：

```text
a = 磁盘使用量
b = 磁盘总容量
公式 = a / b * 100
```

当前公式编辑器已经有结果名称和表达式输入，但缺少结果单位配置。阈值配置仍按参与公式的第一条指标单位推导单位范围，导致上例中第一条指标为容量单位时，阈值单位无法正确配置为百分比。

## 目标

在公式指标模式下，让用户显式声明公式计算结果的单位，并让告警阈值配置使用该单位作为基准。

## 非目标

- 不新增单位体系或单位换算规则。
- 不改变单指标策略的单位推导行为。
- 不改变公式表达式语法、查询构建或后端扫描计算逻辑。
- 不支持自动分析公式并推导单位。

## 方案比较

### 方案 A：公式结果单位显式配置（推荐）

在公式右侧增加“结果单位”下拉。默认选中百分比，保存到策略的 `calculation_unit`。阈值配置使用该结果单位作为单位基准。

优点：
- 与用户心智一致：公式结果是什么单位，由配置者声明。
- 与现有 `calculation_unit` 字段吻合，改动范围小。
- 避免从第一个指标单位错误推导阈值单位。

缺点：
- 需要用户理解公式结果单位，系统不自动校验公式量纲。

### 方案 B：沿用第一条指标单位

继续使用公式第一条指标的单位作为阈值单位基准。

优点：
- 几乎不改现有数据流。

缺点：
- 对 `a / b * 100`、成功率、错误率、利用率等公式明显错误。
- 用户无法配置与第一条指标不同体系的公式结果单位。

### 方案 C：自动推导公式单位

基于参与指标单位和表达式运算推导结果单位。

优点：
- 理论上最智能。

缺点：
- 需要量纲计算规则，涉及乘除、常量、百分比缩放、无单位比值等复杂语义。
- 当前单位体系只提供转换能力，不提供公式量纲推理能力。
- 风险和成本明显超过本需求。

## 推荐设计

采用方案 A。

公式模式下新增“结果单位”字段，UI 放在公式表达式输入框右侧，也就是现有截图红框位置。字段默认值为 `percent`，展示为 `%`。用户可以从单位库中选择任意有效单位，排除 `none`、`short` 等无实际阈值含义的单位。

文案使用“结果单位”，不使用“原始单位”。原因是公式输出已经不是单个原始指标，叫“结果单位”更准确，也能避免误解为参与公式指标的采集原始单位。

## 前端数据流

```text
MetricExpressionEditor
  resultName
  expression
  resultUnit
        |
        v
Strategy detail page state
  calculationUnit = resultUnit
        |
        v
AlertConditionsForm
  unitFilterBase = formula ? resultUnit : selectedMetric.unit
        |
        v
ThresholdList
  value + unit
```

规则：
- 单指标模式：保持现有行为，按指标单位推导 `calculationUnit` 和阈值单位范围。
- 公式模式：`calculationUnit` 来自公式“结果单位”，默认 `percent`。
- 公式模式切换结果单位后，阈值单位选择器立即按新单位所属体系刷新。
- 编辑已有策略时，若 `calculation_unit` 有值则回填；若为空且为公式策略，则默认 `percent`。

## 后端数据语义

对公式策略：
- `calculation_unit` 表示公式结果单位，用于阈值对比展示和事件结果记录。
- `metric_unit` 保持为空，避免后端把公式结果误认为某个原始指标并执行原始单位到计算单位的转换。

对单指标策略：
- 继续沿用现有 `metric_unit -> calculation_unit` 语义。

## 错误处理与校验

- 公式模式且启用阈值告警时，`calculation_unit` 必须有值。
- 单位下拉只展示单位库中的有效单位。
- 若编辑历史策略时 `calculation_unit` 已不在当前单位库中，前端应回退到 `percent` 并触发阈值字段重新校验。
- 枚举指标策略不展示单位选择；公式模式不支持枚举单位作为阈值单位基准。

## 测试建议

前端测试覆盖：
- 新建公式策略默认结果单位为 `%`。
- 修改公式结果单位后，阈值单位选项按结果单位所属体系变化。
- `a / b * 100` 场景中，即使 `a` 是容量单位，阈值单位仍可配置为 `%`。
- 编辑已有公式策略能回填 `calculation_unit`。
- 单指标策略现有单位推导行为不变。

后端测试覆盖：
- 公式策略保存 `calculation_unit=percent`、`metric_unit=""` 时，序列化和扫描查询不报错。
- 单指标策略单位换算逻辑保持现状。

## 验收标准

- 公式编辑器右侧出现结果单位下拉，默认展示 `%`。
- 用户选择结果单位后，阈值配置单位使用该结果单位作为基准。
- 保存后再次编辑策略，公式结果单位正确回填。
- 普通单指标策略行为不回归。
