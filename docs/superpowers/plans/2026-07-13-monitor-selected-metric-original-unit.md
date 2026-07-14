# 监控策略指标原始单位展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在监控策略指标编辑器的下拉候选项和已选值中展示可读的原始单位，并隐藏无意义、枚举或未知单位。

**Architecture:** 在 `strategyDetailUtils.ts` 中增加纯函数，将指标 `unit` 通过公共 `unitList` 映射为 `display_unit`，并生成保持原 `value` 不变的 Select 选项。`page.tsx` 将已有 `unitList` 经 `MetricDefinitionForm` 传给 `MetricExpressionEditor`，编辑器只消费统一构造后的字符串标签。

**Tech Stack:** TypeScript、React 19、Next.js 16、Ant Design Select、Node `assert` 专项逻辑测试。

## Global Constraints

- 下拉候选项和已选指标统一显示 `指标名称（display_unit）`。
- `none`、`short`、枚举 JSON、未知单位、空单位及单位列表未加载时只显示指标名称。
- 单位展示不得改变指标选项 `value`、查询条件、公式计算或保存 payload。
- 使用中文全角括号，与已确认截图格式一致。
- 新行为必须按 TDD 先红后绿；只修改需求相关文件。

---

### Task 1: 构建并接入指标原始单位展示标签

**Files:**
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`

**Interfaces:**
- Consumes: `MetricItem.unit`、`MetricItem.display_name`、`MetricItem.name` 和 `UnitListItem[]`。
- Produces: `resolveMetricDisplayUnit(unit, unitList): string`，返回可展示符号或空字符串。
- Produces: `buildMetricSelectOption(metric, unitList): { label: string; value: string }`，供 Ant Design Select 直接消费。
- Produces: `unitList: UnitListItem[]` 组件属性，从 `page.tsx` 逐层传到 `MetricExpressionEditor`。

- [ ] **Step 1: 写入失败的纯函数行为测试**

在 `web/scripts/monitor-strategy-detail-logic-test.ts` 导入 `buildMetricSelectOption` 和 `resolveMetricDisplayUnit`，加入以下断言：

```ts
assert.equal(resolveMetricDisplayUnit('percent', unitList), '%');
assert.equal(resolveMetricDisplayUnit('bytes', unitList), 'B');
assert.equal(resolveMetricDisplayUnit('none', unitList), '');
assert.equal(resolveMetricDisplayUnit('short', unitList), '');
assert.equal(
  resolveMetricDisplayUnit('[{"id":1,"name":"up"}]', unitList),
  ''
);
assert.equal(resolveMetricDisplayUnit('unknown-unit', unitList), '');
assert.equal(resolveMetricDisplayUnit('percent', []), '');

assert.deepEqual(
  buildMetricSelectOption(
    {
      id: 1,
      metric_group: 1,
      metric_object: 1,
      name: 'disk_usage',
      type: 'gauge',
      display_name: '磁盘使用率',
      dimensions: [],
      unit: 'percent'
    },
    unitList
  ),
  { label: '磁盘使用率（%）', value: 'disk_usage' }
);
assert.deepEqual(
  buildMetricSelectOption(
    {
      id: 2,
      metric_group: 1,
      metric_object: 1,
      name: 'disk_state',
      type: 'gauge',
      display_name: '磁盘状态',
      dimensions: [],
      unit: '[{"id":1,"name":"up"}]'
    },
    unitList
  ),
  { label: '磁盘状态', value: 'disk_state' }
);
```

- [ ] **Step 2: 运行专项测试并确认因新函数缺失而失败**

Run: `cd web && pnpm test:monitor-strategy-detail-logic`

Expected: FAIL，错误明确指出 `buildMetricSelectOption` 或 `resolveMetricDisplayUnit` 尚未导出/实现。

- [ ] **Step 3: 实现最小单位解析与 Select 选项构造函数**

在 `strategyDetailUtils.ts` 引入 `MetricItem`，并新增：

```ts
export const resolveMetricDisplayUnit = (
  unit: string | null | undefined,
  unitList: UnitListItem[]
): string => {
  if (!unit || INVALID_THRESHOLD_UNIT_IDS.has(unit) || isStringArray(unit)) {
    return '';
  }

  return (
    unitList.find((item) => item.unit_id === unit)?.display_unit || ''
  );
};

export const buildMetricSelectOption = (
  metric: MetricItem,
  unitList: UnitListItem[]
): { label: string; value: string } => {
  const displayName = metric.display_name || metric.name;
  const displayUnit = resolveMetricDisplayUnit(metric.unit, unitList);
  return {
    label: displayUnit
      ? `${displayName}（${displayUnit}）`
      : displayName,
    value: metric.name
  };
};
```

- [ ] **Step 4: 运行专项测试并确认纯函数行为转绿**

Run: `cd web && pnpm test:monitor-strategy-detail-logic`

Expected: PASS，输出 `monitor-strategy-detail logic validation passed`。

- [ ] **Step 5: 将 unitList 传入指标编辑器并使用统一选项构造函数**

在 `MetricDefinitionFormProps` 和 `MetricExpressionEditorProps` 中增加：

```ts
unitList: UnitListItem[];
```

在 `page.tsx` 的 `MetricDefinitionForm` 调用处传入：

```tsx
unitList={unitList}
```

在 `metricDefinitionForm.tsx` 继续传给 `MetricExpressionEditor`：

```tsx
unitList={unitList}
```

在 `metricExpressionEditor.tsx` 导入 `buildMetricSelectOption`，将叶子选项构造改为：

```ts
options: (group.child || []).map((metric: MetricItem) =>
  buildMetricSelectOption(metric, unitList)
)
```

同时把 `unitList` 加入 `metricOptions` 的 `useMemo` 依赖，使公共单位列表异步到达后标签自动更新。保留当前基于字符串 `option.label` 的搜索逻辑，从而同时支持按指标名和单位符号搜索。

- [ ] **Step 6: 运行专项测试、触及文件 ESLint 和 monitor TypeScript 门禁**

Run:

```bash
cd web
pnpm test:monitor-strategy-detail-logic
pnpm exec eslint --no-ignore \
  scripts/monitor-strategy-detail-logic-test.ts \
  'src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' \
  'src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx' \
  'src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' \
  'src/app/monitor/(pages)/event/strategy/detail/page.tsx'
NEXTAPI_INSTALL_APP=monitor pnpm precommit
pnpm exec tsc -p tsconfig.lint.json --noEmit
pnpm type-check
```

Expected: 所有命令退出码均为 `0`。若全仓 `pnpm lint` 仍出现已记录的任务外错误，只记录基线，不修改无关文件。

- [ ] **Step 7: 自检 diff 并提交实现**

Run:

```bash
git diff --check
git status --short
git diff -- web/scripts/monitor-strategy-detail-logic-test.ts \
  'web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' \
  'web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx' \
  'web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' \
  'web/src/app/monitor/(pages)/event/strategy/detail/page.tsx'
git add web/scripts/monitor-strategy-detail-logic-test.ts \
  'web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' \
  'web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx' \
  'web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' \
  'web/src/app/monitor/(pages)/event/strategy/detail/page.tsx'
git commit -m '优化监控策略指标原始单位展示'
```

Expected: `git diff --check` 无输出；提交只包含上述五个文件。
