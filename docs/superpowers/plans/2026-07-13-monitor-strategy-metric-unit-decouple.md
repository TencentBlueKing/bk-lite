# Monitor Strategy Metric-Unit vs Threshold-Unit Decouple Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将监控告警策略详情页的「计算指标单位」与「阈值单位」解耦为两个独立 state；单位选择器（计算指标单位、公式结果单位）改用 Cascader（`groupedUnitList` 按 category 分组），与插件指标创建保持一致。

**Architecture:** 拆分 `page.tsx` 中共享的 `calculationUnit` state 为 `metricUnit`（计算指标单位，可由 Cascader 选）与 `thresholdUnit`（阈值单位，仅作 Select 基准）。公式模式保留单 `resultUnit`（仅作为 `calculation_unit`）。新增 `buildMetricUnitCascaderOptions` / `isValidMetricUnit` 纯函数；`getThresholdUnitOptions` 改为以 `metricUnit` 为基准过滤同 system 单位。`params.metric_unit` / `params.calculation_unit` 独立提交，与后端 `monitor_policy` 字段对齐。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design（`Cascader`/`Select`）、pnpm、tsx 脚本测试（`node:assert`）。

**Spec:** `docs/superpowers/specs/2026-07-13-monitor-strategy-metric-unit-decouple-design.md`

## Global Constraints

- 只改 `web/` 监控告警策略创建/编辑相关文件，不动 server。
- 不新增单位体系或单位换算规则。
- 不改公式表达式语法、查询构建、后端扫描计算逻辑。
- 公式模式默认结果单位为 `percent`（沿用 `FORMULA_DEFAULT_RESULT_UNIT`）。
- 公式策略保存 `calculation_unit`，`metric_unit` 保持为空。
- 单位下拉排除 `none`、`short`。
- Cascader 分组依据 `groupedUnitList.category`（与 `metricModal.tsx:68` 范式一致）。
- 新功能 / bugfix 先写测试，提交前跑 `cd web && pnpm lint && pnpm type-check`。
- 中文优先（commit/注释/UI 文案）。

## File Structure

- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
  - 新增 `buildMetricUnitCascaderOptions` / `isValidMetricUnit`；`getThresholdUnitOptions` 签名改为以 `metricUnit` 为基准。
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
  - 覆盖新纯函数；保持既有断言不破坏。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
  - 公式行结果单位改 Cascader；新增 `metricUnit` / `onMetricUnitChange` / `groupedUnitOptions` 透传给上层。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
  - 接收 `metricUnit` / `onMetricUnitChange` / `groupedUnitOptions`，非公式模式渲染「计算指标单位」Cascader。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`
  - `calculationUnit` 重命名为 `thresholdUnit`（语义清晰）；阈值单位选项基准改用 `metricUnit`。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx`
  - prop 重命名（语义清晰），UI 行为不变。
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
  - 拆 state、入参拆分、串联各组件。

---

### Task 1: 新增 Cascader 工具函数 + 单测

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`

**Interfaces:**
- Consumes: `GroupedUnitList`, `CascaderItem` from `@/app/monitor/types`
- Produces: `buildMetricUnitCascaderOptions(groupedUnitList: GroupedUnitList[]): CascaderItem[]`
- Produces: `isValidMetricUnit(unit: string | null | undefined, groupedUnitList: GroupedUnitList[]): boolean`
- Produces (signature change): `getThresholdUnitOptions({ unitList, metricUnit, isEnumMetric }: { unitList: UnitListItem[]; metricUnit: string | null; isEnumMetric: boolean; }): UnitListItem[]`

- [ ] **Step 1: 改旧测试断言为新签名 + 写失败测试**

`web/scripts/monitor-strategy-detail-logic-test.ts` 现有 3 处 `getThresholdUnitFilterBase` 断言（行 202/210/218）和 5 处旧签名 `getThresholdUnitOptions` 断言（行 227/235/243/251/259）。**Task 1 必须同步迁移**：

1. 删除 import 中的 `getThresholdUnitFilterBase`；保留 `getThresholdUnitOptions` 导入。
2. 删除 3 处 `getThresholdUnitFilterBase` 断言（函数随 Task 1 Step 3 一同删除）。
3. 5 处旧签名断言改为新签名：
   - 把每个 `getThresholdUnitOptions({ unitList, unitFilterBase: '...', isEnumMetric: ... })` 改为 `getThresholdUnitOptions({ unitList, metricUnit: '...', isEnumMetric: ... })`，断言期望值不变。
4. 追加 Task 1 末尾的新断言（`buildMetricUnitCascaderOptions` / `isValidMetricUnit` / 新 `getThresholdUnitOptions` 跨 system 测试），import 增补：

```ts
import {
  buildMetricUnitCascaderOptions,
  isValidMetricUnit,
  getThresholdUnitOptions,
} from '../src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils';
import type { GroupedUnitList } from '../src/app/monitor/types';

const groupedUnitList: GroupedUnitList[] = [
  {
    label: 'Data',
    children: [
      { unit_id: 'bytes', unit_name: '字节', display_unit: 'B', label: '字节', value: 'bytes', unit: 'B' },
      { unit_id: 'kibibytes', unit_name: '千字节', display_unit: 'KiB', label: '千字节', value: 'kibibytes', unit: 'KiB' },
    ],
  },
  {
    label: 'Time',
    children: [
      { unit_id: 'seconds', unit_name: '秒', display_unit: 's', label: '秒', value: 'seconds', unit: 's' },
    ],
  },
  {
    label: 'Base',
    children: [
      { unit_id: 'none', unit_name: '无单位', display_unit: '', label: '无单位', value: 'none', unit: '' },
    ],
  },
];

// buildMetricUnitCascaderOptions:保留全量节点(value=unit_id,label=unit_name)
const cascaderOptions = buildMetricUnitCascaderOptions(groupedUnitList);
assert.equal(cascaderOptions.length, 3);
assert.equal(cascaderOptions[0].value, 'Data');
assert.equal(cascaderOptions[0].children?.length, 2);
assert.equal(cascaderOptions[0].children?.[0].value, 'bytes');

// isValidMetricUnit:含 'none'/'short'/空/undefined 一律 false
assert.equal(isValidMetricUnit('bytes', groupedUnitList), true);
assert.equal(isValidMetricUnit('kibibytes', groupedUnitList), true);
assert.equal(isValidMetricUnit('seconds', groupedUnitList), true);
assert.equal(isValidMetricUnit('none', groupedUnitList), false);
assert.equal(isValidMetricUnit('unknown', groupedUnitList), false);
assert.equal(isValidMetricUnit(null, groupedUnitList), false);
assert.equal(isValidMetricUnit(undefined, groupedUnitList), false);
assert.equal(isValidMetricUnit('', groupedUnitList), false);

// getThresholdUnitOptions(新签名:metricUnit 基准) — 同 system 过滤
const unitList: UnitListItem[] = [
  { unit_id: 'bytes', unit_name: '字节', display_unit: 'B', category: 'Data', system: 'bytes', description: '', is_standalone: false },
  { unit_id: 'kibibytes', unit_name: '千字节', display_unit: 'KiB', category: 'Data', system: 'bytes', description: '', is_standalone: false },
  { unit_id: 'mebibytes', unit_name: '兆字节', display_unit: 'MiB', category: 'Data', system: 'bytes', description: '', is_standalone: false },
  { unit_id: 'seconds', unit_name: '秒', display_unit: 's', category: 'Time', system: 'seconds', description: '', is_standalone: false },
  { unit_id: 'minutes', unit_name: '分钟', display_unit: 'min', category: 'Time', system: 'seconds', description: '', is_standalone: false },
  { unit_id: 'none', unit_name: '无单位', display_unit: '', category: 'Base', system: 'none', description: '', is_standalone: false },
];

const bytesOptions = getThresholdUnitOptions({ unitList, metricUnit: 'bytes', isEnumMetric: false });
assert.deepEqual(
  bytesOptions.map((u) => u.unit_id).sort(),
  ['bytes', 'kibibytes', 'mebibytes']
);

const secondsOptions = getThresholdUnitOptions({ unitList, metricUnit: 'seconds', isEnumMetric: false });
assert.deepEqual(
  secondsOptions.map((u) => u.unit_id).sort(),
  ['seconds', 'minutes']
);

// 枚举类型:返回空
const enumOptions = getThresholdUnitOptions({ unitList, metricUnit: 'bytes', isEnumMetric: true });
assert.equal(enumOptions.length, 0);
```

- [ ] **Step 2: 运行测试，验证失败**

Run:
```bash
cd web && pnpm tsx scripts/monitor-strategy-detail-logic-test.ts
```
Expected: 失败（旧的 `getThresholdUnitFilterBase` import/断言因函数未实现而 fail；新增的 `buildMetricUnitCascaderOptions` / `isValidMetricUnit` 也因未定义而 fail；旧的 5 处 `getThresholdUnitOptions` 断言因参数已迁移到新签名而抛错）。

- [ ] **Step 3: 在 strategyDetailUtils.ts 实现新函数**

在 `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts` 顶部 import 增补：

```ts
import { SegmentedItem, UnitListItem, GroupedUnitList, CascaderItem } from '@/app/monitor/types';
```

在文件末尾追加（替换旧的 `getThresholdUnitOptions`）：

```ts
export const buildMetricUnitCascaderOptions = (
  groupedUnitList: GroupedUnitList[]
): CascaderItem[] =>
  groupedUnitList.map((group) => ({
    label: group.label,
    value: group.label,
    children: (group.children || []).map((item) => ({
      label: item.label,
      value: item.value
    }))
  }));

// 有效 metric 单位:必须能在 groupedUnitList 中找到, 且不在 'none' / 'short' 集内
export const isValidMetricUnit = (
  unit: string | null | undefined,
  groupedUnitList: GroupedUnitList[]
): boolean => {
  if (!unit) return false;
  if (unit === 'none' || unit === 'short') return false;
  return groupedUnitList.some((group) =>
    (group.children || []).some((item) => item.value === unit)
  );
};

// 新签名:阈值单位选项以 metricUnit 同 system 为基准过滤;isEnumMetric 时返回空
export const getThresholdUnitOptions = ({
  unitList,
  metricUnit,
  isEnumMetric
}: {
  unitList: UnitListItem[];
  metricUnit: string | null;
  isEnumMetric: boolean;
}): UnitListItem[] => {
  if (isEnumMetric || !metricUnit) return [];

  const validUnits = getValidThresholdUnitOptions(unitList);
  const baseUnit = validUnits.find((item) => item.unit_id === metricUnit);
  if (!baseUnit) return [];

  if (baseUnit.system === null) {
    return validUnits.filter((item) => item.unit_id === baseUnit.unit_id);
  }

  return validUnits.filter((item) => item.system === baseUnit.system);
};
```

并删除旧的 `getThresholdUnitFilterBase` 导出函数（整段删除，行号 137–150）。alertConditionsForm.tsx 唯一非测试调用方将在 Task 4 改为直接传入 `metricUnit`。

- [ ] **Step 4: 运行测试，验证通过**

Run:
```bash
cd web && pnpm tsx scripts/monitor-strategy-detail-logic-test.ts
```
Expected: 全部断言通过（既有 5 个 `getThresholdUnitOptions` 断言改为新签名后通过 + 新增 3 组断言通过；既有的 9 个其他 utils 断言不破坏）。

- [ ] **Step 5: 提交**

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/strategyDetailUtils.ts web/scripts/monitor-strategy-detail-logic-test.ts
git commit -m "feat(monitor): add metric-unit cascader helpers and new threshold-unit signature"
```

---

### Task 2: metricExpressionEditor 公式行结果单位改 Cascader + 透传 metricUnit

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`

**Interfaces:**
- Consumes: `GroupedUnitList` from `@/app/monitor/types`（经 page.tsx 转为 `CascaderItem[]` 传入）
- Produces (新增 prop): `metricUnit: string | null; onMetricUnitChange: (value: string) => void; groupedUnitOptions: CascaderItem[];`

- [ ] **Step 1: 在 props 接口新增字段并 import 必要类型**

修改 `metricExpressionEditor.tsx` 顶部 import：

```ts
import { FilterItem, IndexViewItem, ListItem, MetricItem, UnitListItem, CascaderItem } from '@/app/monitor/types';
import { findCascaderPath } from '@/app/monitor/utils/common';
```

`MetricExpressionEditorProps` 新增：

```ts
metricUnit: string | null;
onMetricUnitChange: (value: string) => void;
groupedUnitOptions: CascaderItem[];
```

组件解构中加：

```ts
metricUnit,
onMetricUnitChange,
groupedUnitOptions,
```

- [ ] **Step 2: 公式行 resultUnit 改 Cascader**

替换 `metricExpressionEditor.tsx:374-397` 处的 `<Select>` 为：

```tsx
<Cascader
  className="w-full"
  showSearch
  value={resultUnit ? findCascaderPath(groupedUnitOptions, resultUnit) : []}
  aria-label={translateWithFallback('monitor.events.formulaResultUnit', '结果单位')}
  placeholder={translateWithFallback('monitor.events.formulaResultUnit', '结果单位')}
  options={groupedUnitOptions}
  onChange={(path) => onResultUnitChange((path as (string | number)[]).at(-1) as string)}
/>
```

- [ ] **Step 3: 跑 lint + type-check**

Run:
```bash
cd web && pnpm lint && pnpm type-check
```
Expected: 通过（仅公式行 Cascader 替换，未引入未使用变量）。`metricUnit` / `onMetricUnitChange` 暂未在组件内使用，TS 会警告——用一行注释 + `// eslint-disable-next-line @typescript-eslint/no-unused-vars` 暂压一下：

```ts
// 透传 metricUnit 给上层(由 MetricDefinitionForm 渲染 Cascader)
void metricUnit;
void onMetricUnitChange;
```

- [ ] **Step 4: 提交**

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/metricExpressionEditor.tsx
git commit -m "feat(monitor): switch formula result unit to Cascader"
```

---

### Task 3: metricDefinitionForm 渲染「计算指标单位」Cascader

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`

**Interfaces:**
- Consumes: `CascaderItem[]` (groupedUnitOptions), `metricUnit`, `onMetricUnitChange` from page.tsx
- Produces: 在「指标」Form.Item 之后、非 Trap 模式下渲染 Cascader

- [ ] **Step 1: 扩展 props**

修改 `metricDefinitionForm.tsx` 顶部 import：

```ts
import { SegmentedItem, IndexViewItem, UnitListItem, CascaderItem } from '@/app/monitor/types';
```

`MetricDefinitionFormProps` 新增：

```ts
metricUnit: string | null;
onMetricUnitChange: (value: string) => void;
groupedUnitOptions: CascaderItem[];
```

组件解构中加 `metricUnit, onMetricUnitChange, groupedUnitOptions`。

- [ ] **Step 2: 在 MetricExpressionEditor 之后插入 Cascader 渲染**

定位到 `metricDefinitionForm.tsx` 内 `</>` 包裹的 `Form.Item<StrategyFields>` name="metric" 块，找到 `</Form.Item>` 后、`{/* 汇聚周期 */}` 前。插入：

```tsx
{/* 计算指标单位 - 仅在非 Trap 模式下展示 */}
<Form.Item<StrategyFields>
  label={
    <span className="w-[100px]">
      {t('monitor.events.metricUnit')}
    </span>
  }
>
  <Cascader
    className="w-full"
    showSearch
    value={metricUnit ? findCascaderPath(groupedUnitOptions, metricUnit) : []}
    placeholder={t('monitor.events.metricUnitPlaceholder')}
    options={groupedUnitOptions}
    onChange={(path) =>
      onMetricUnitChange((path as (string | number)[]).at(-1) as string)
    }
  />
  <div className="text-[var(--color-text-3)] mt-[10px]">
    {t('monitor.events.metricUnitTip')}
  </div>
</Form.Item>
```

import 增补：

```ts
import { Cascader } from 'antd';
import { findCascaderPath } from '@/app/monitor/utils/common';
```

- [ ] **Step 3: 跑 lint + type-check**

Run:
```bash
cd web && pnpm lint && pnpm type-check
```
Expected: 通过（仍依赖 page.tsx 注入新 prop，TS 可能在 page.tsx 报错；属于 Task 5 范畴，本任务先放过）。

- [ ] **Step 4: 提交**

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/metricDefinitionForm.tsx
git commit -m "feat(monitor): render metric-unit Cascader in definition form"
```

---

### Task 4: alertConditionsForm + thresholdList 重命名为 thresholdUnit

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx`

**Interfaces:**
- Produces (prop rename): `ThresholdListProps.calculationUnit` → `thresholdUnit`；`onUnitChange` → `onThresholdUnitChange`
- Produces (prop rename): `AlertConditionsFormProps.calculationUnit` → `thresholdUnit`；`onCalculationUnitChange` → `onThresholdUnitChange`
- 内部过滤逻辑（`getThresholdUnitOptions`）改用 `metricUnit` 作基准

- [ ] **Step 1: thresholdList.tsx 改名 prop + onChange**

将 `thresholdList.tsx`：

```ts
interface ThresholdListProps {
  data: ThresholdItem[];
  onChange?: (data: ThresholdItem[]) => void;
  calculationUnit: string | null;
  onUnitChange: (unit: string) => void;
  unitOptions?: any[];
  isEnumMetric?: boolean;
  enumOptions?: EnumOption[];
}
```

改为：

```ts
interface ThresholdListProps {
  data: ThresholdItem[];
  onChange?: (data: ThresholdItem[]) => void;
  thresholdUnit: string | null;
  onThresholdUnitChange: (unit: string) => void;
  unitOptions?: any[];
  isEnumMetric?: boolean;
  enumOptions?: EnumOption[];
}
```

组件内全部 `calculationUnit` → `thresholdUnit`；`onUnitChange` → `onThresholdUnitChange`；`handleUnitChange` → `handleThresholdUnitChange`（实现里调用 `onThresholdUnitChange(value)`）；`getUnitLabel` 内 `calculationUnit` → `thresholdUnit`；JSX 里 `value={calculationUnit}` → `value={thresholdUnit}`、`onChange={handleUnitChange}` → `onChange={handleThresholdUnitChange}`。

- [ ] **Step 2: alertConditionsForm.tsx 改名 prop + onChange + 用 metricUnit 过滤**

修改 `AlertConditionsFormProps`：

```ts
thresholdUnit: string | null;
metricUnit: string | null;
onThresholdUnitChange: (val: string) => void;
```

替换 `getThresholdUnitFilterBase` 逻辑为直接 `metricUnit`（已无旧函数）。

组件内 `unitFilterBase` 改为 `metricUnit`，`filteredUnitOptions` 调用改为新签名：

```tsx
const filteredUnitOptions = useMemo(
  () =>
    getThresholdUnitOptions({
      unitList,
      metricUnit,
      isEnumMetric
    }),
  [unitList, metricUnit, isEnumMetric]
);
```

JSX 渲染部分：

```tsx
<ThresholdList
  data={threshold}
  onChange={onThresholdChange}
  thresholdUnit={thresholdUnit}
  onThresholdUnitChange={onThresholdUnitChange}
  unitOptions={filteredUnitOptions}
  isEnumMetric={isEnumMetric}
  enumOptions={enumOptions}
/>
```

`validateThreshold` 中 `calculationUnit` → `thresholdUnit`。

- [ ] **Step 3: 跑 lint + type-check（预计 page.tsx 报错）**

Run:
```bash
cd web && pnpm lint && pnpm type-check
```
Expected: page.tsx 报 prop 缺失 / 类型不匹配（属于 Task 5）。本任务文件应无新错误。

- [ ] **Step 4: 提交**

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/alertConditionsForm.tsx web/src/app/monitor/\(pages\)/event/strategy/detail/thresholdList.tsx
git commit -m "refactor(monitor): rename calculationUnit to thresholdUnit in alert form"
```

---

### Task 5: page.tsx 拆 state + 入参拆分

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`

**Interfaces:**
- Produces: 新增 state `metricUnit: string | null`；`calculationUnit` 重命名为 `thresholdUnit`
- Produces: 新增 callback `handleMetricUnitChange(value: string)`；`handleCalculationUnitChange` 重命名为 `handleThresholdUnitChange`
- Produces: 新增 prop 透传 `metricUnit / onMetricUnitChange / groupedUnitOptions` 给 `MetricDefinitionForm`；`thresholdUnit / onThresholdUnitChange` 替换原 `calculationUnit / onCalculationUnitChange` 给 `AlertConditionsForm` 和 `MetricPreview`

- [ ] **Step 1: 新增 metricUnit state + 切换 metric 时初始化**

`page.tsx:171` 附近，把

```ts
const [calculationUnit, setCalculationUnit] = useState<string | null>(null);
```

改为：

```ts
const [metricUnit, setMetricUnit] = useState<string | null>(null);
const [thresholdUnit, setThresholdUnit] = useState<string | null>(null);
```

- [ ] **Step 2: 替换所有 `calculationUnit` → `thresholdUnit`，新增 metricUnit 维护**

`grep -n "calculationUnit" web/src/app/monitor/\(pages\)/event/strategy/detail/page.tsx`，逐处替换：

- `:405 setCalculationUnit(filterInvalidCalculationUnit(calculation_unit))` → `setThresholdUnit(filterInvalidCalculationUnit(calculation_unit))`，并在其后新增 `setMetricUnit(filterInvalidCalculationUnit(calculation_unit))`（首屏编辑回填时指标单位也填同值；切换指标时会被覆盖）。
- `:493-495 setCalculationUnit(resolveFormulaResultUnit(...))` → `setThresholdUnit(...)` 并 `setMetricUnit(null)`（公式模式 metricUnit 留空）。
- `:566-586 handleMetricChange` 中：替换所有 `setCalculationUnit(...)` 为 `setThresholdUnit(...)`，并在第一次 `setThresholdUnit(filteredUnit)` 之前 `setMetricUnit(filteredUnit)`；兜底分支同理。
- `:640-660 handleMetricRowsChange` 中：`getCalculationUnitOnMetricRowsChange` 的输出写入 `thresholdUnit`；`getReverseModeCalculationUnit` 写入 `metricUnit` 与 `thresholdUnit`（两者都设回主指标 unit，用户可独立调整）。
- `:727-735 handleCalculationUnitChange` → `handleThresholdUnitChange`，写入 `thresholdUnit`；新增 `handleMetricUnitChange`，写入 `metricUnit`。
- `:806-810 params.calculation_unit = nextCalculationUnit` 改用 `thresholdUnit`。
- `:790-795 params.metric_unit = ...` 改用 `metricUnit`（在公式模式 / 多指标 / 枚举时为空，否则取 `metricUnit ?? mertricTarget?.unit`）。
- JSX 渲染处：`metricDefinitionForm` 新增 `metricUnit={metricUnit} onMetricUnitChange={handleMetricUnitChange} groupedUnitOptions={groupedUnitOptions}`；`alertConditionsForm` 把 `calculationUnit={calculationUnit}` 改为 `thresholdUnit={thresholdUnit}` 并把 `onCalculationUnitChange={handleCalculationUnitChange}` 改为 `onThresholdUnitChange={handleThresholdUnitChange}`，新增 `metricUnit={...}`（用 `metrics.find(...).unit` 或 `metricUnit`，统一用 `metricUnit`）；`metricPreview` 同步：`calculationUnit={calculationUnit}` → `calculationUnit={thresholdUnit}`。

- [ ] **Step 3: 注入 groupedUnitOptions**

`page.tsx` 顶部 import 增补：

```ts
import { buildMetricUnitCascaderOptions } from './strategyDetailUtils';
import { useCommon } from '@/app/monitor/context/common';
```

组件内（已有 `const commonContext = useCommon();` 之后）：

```ts
const groupedUnitOptions = useMemo(
  () => buildMetricUnitCascaderOptions(commonContext?.groupedUnitList || []),
  [commonContext?.groupedUnitList]
);
```

- [ ] **Step 4: 跑 lint + type-check 全量**

Run:
```bash
cd web && pnpm lint && pnpm type-check
```
Expected: 全部通过。

- [ ] **Step 5: 跑既有逻辑测试**

Run:
```bash
cd web && pnpm tsx scripts/monitor-strategy-detail-logic-test.ts
```
Expected: 既有断言 + Task 1 新增断言全部通过。

- [ ] **Step 6: 提交**

```bash
git add web/src/app/monitor/\(pages\)/event/strategy/detail/page.tsx
git commit -m "feat(monitor): split metricUnit and thresholdUnit state in strategy detail"
```

---

### Task 6: 手动 / e2e 验证

**Files:** 无（仅手动测试）

- [ ] **Step 1: 启动 dev server**

Run:
```bash
cd server && make dev
```
（另开终端）`cd web && pnpm dev`，浏览器打开监控策略新建页（`/monitor/event/strategy?type=add&...`）。

- [ ] **Step 2: 验证「计算指标单位」Cascader 渲染**

- 选容量类指标（如 disk.used，bytes）
- 确认「计算指标单位」Cascader 默认显示 `B`
- 点开 Cascader，按 category 分组（Data / Time / Percent 等），节点可搜索
- 选 `KiB` → Cascader 关闭，状态写 `metricUnit=kibibytes`

- [ ] **Step 3: 验证「阈值单位」Select 解耦**

- 改阈值单位为 `MB` → `thresholdUnit=mebibytes`
- 此时 `metricUnit` 仍为 `kibibytes`，`thresholdUnit` 不应回写
- 提交（前端 mock 或开发环境真实提交），检查后端 `monitor_policy` 的 `metric_unit=kibibytes, calculation_unit=mebibytes`

- [ ] **Step 4: 验证切换指标重置**

- 改指标为另一个不同 system 的指标（如 cpu.usage，seconds 类）
- 确认 `metricUnit` 自动 reset 为该指标的 unit；旧的 `metricUnit=kibibytes` 不应保留
- 阈值单位 Select 选项随 `metricUnit` 切换刷新

- [ ] **Step 5: 验证公式模式**

- 进入公式模式（`fx = ...`）
- 「结果单位」Cascader 按 category 分组展示
- 选 `percent` → 提交后 `metric_unit='', calculation_unit=percent`
- 切回单指标模式 → `metricUnit` 与 `thresholdUnit` 恢复

- [ ] **Step 6: 验证预览图单位**

- MetricPreview 图表 Y 轴单位 = `thresholdUnit`（阈值单位）
- 与 threshold 标注单位一致
- 与服务端 `_unit_conversion_enabled` 行为对齐（`metric_unit != calculation_unit` 时启用换算）

- [ ] **Step 7: 记录手动验证结果**

如发现异常，新增 issue 并记录在 plan 文件底部 `## 验证记录` 段。

---

## Self-Review

**1. Spec 覆盖检查**

| Spec 节 | 覆盖 Task |
|---------|----------|
| State 拆分（metricUnit / thresholdUnit / resultUnit） | Task 1（utils）、Task 5（page 状态） |
| 公式行 Cascader | Task 2 |
| 非公式「计算指标单位」Cascader（位于 metricDefinitionForm） | Task 3 |
| thresholdList / alertConditionsForm 重命名 | Task 4 |
| 工具函数 buildMetricUnitCascaderOptions / isValidMetricUnit / getThresholdUnitOptions | Task 1 |
| 入参 metric_unit / calculation_unit 独立 | Task 5 |
| 测试扩展 | Task 1（单测）+ Task 6（手动） |
| MetricPreview 不变 | Task 5（仅改 prop 名） |
| 错误处理 | Task 5（handleMetricChange 复用旧 reset 逻辑）+ Task 1（isValidMetricUnit 拦截） |
| 改动文件清单 | Task 1-5 全部对齐 |

**2. 占位扫描**：plan 内无 TBD / TODO / "implement later"。

**3. 类型一致性**：
- `getThresholdUnitOptions` 新签名 `{ unitList, metricUnit, isEnumMetric }` 在 Task 1 定义、Task 4 调用，签名一致。
- `thresholdUnit` prop 名在 Task 4 定义、Task 5 注入，命名一致。
- `metricUnit` prop 名在 Task 1 utils / Task 3 form / Task 5 page 三处一致。
- `groupedUnitOptions: CascaderItem[]` 在 Task 2/3/5 一致。

**4. 已知遗留**：
- `getCalculationUnitOnMetricRowsChange` 与 `getReverseModeCalculationUnit` 现有实现都返回单一值；Task 5 Step 2 提到"两者都设回主指标 unit"是基于"两者都设回主指标 unit"——具体取值要按 utils 实际返回决定。Task 5 Step 2 给出明确写法：把 `getReverseModeCalculationUnit` 返回值同时写入 `metricUnit` 和 `thresholdUnit`，把 `getCalculationUnitOnMetricRowsChange` 返回值写入 `thresholdUnit`，进入 formula 时 `metricUnit = null`。
