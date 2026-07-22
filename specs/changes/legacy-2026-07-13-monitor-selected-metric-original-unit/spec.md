# Historical Superpowers change: 2026-07-13-monitor-selected-metric-original-unit

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-13-monitor-selected-metric-original-unit.md

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

## specs: 2026-07-13-monitor-selected-metric-original-unit-design.md

- 日期：2026-07-13
- 状态：已完成方案确认，待书面规格复核
- 适用范围：监控策略详情页指标编辑器

## 背景与目标

用户在组合多个指标编写计算公式时，仅看到指标名称，难以快速判断不同指标的量纲以及公式结果应该选择什么单位。

本次在指标下拉候选项和已选指标中展示指标的原始单位，例如 `磁盘使用率（%）`、`磁盘总空间（B）`。展示只用于辅助判断，不改变指标查询、公式计算或策略保存的数据。

## 产品决策

采用“指标名称 + 展示单位”的统一标签：

- 下拉候选项和已选指标使用同一展示规则，避免选择前后信息不一致。
- 单位取自指标的 `unit`，通过公共单位元数据映射为 `display_unit`，展示 `%`、`B` 等用户可读符号。
- `none`、`short` 和枚举 JSON 单位不展示，只保留指标名称。
- 单位元数据尚未加载或无法匹配时，只展示指标名称，不回退展示 `percent`、`bytes` 等内部单位标识。
- 不在选择框外增加独立单位控件，避免与公式结果单位、阈值单位产生语义混淆。

## 组件与数据流

1. 策略详情页继续从监控公共上下文取得 `unitList`，并将其传给指标编辑器。
2. 纯函数根据 `MetricItem.unit` 和 `unitList` 生成展示单位：
   - 无单位、`none`、`short`、枚举 JSON：返回空字符串；
   - 找到匹配的 `unit_id`：返回该项 `display_unit`；
   - 未匹配：返回空字符串。
3. 指标编辑器构造下拉选项时生成统一展示标签；已选值由同一选项标签渲染。
4. 搜索仍同时支持指标展示名称和单位符号，不改变选项的真实 `value`。

## 异常与降级

- `unitList` 异步加载期间先显示指标名称；加载完成后 React 重新计算选项并补充单位。
- 指标单位字段为脏 JSON、未知单位或空值时不显示括号，也不影响指标选择。
- 展示单位为空字符串时不渲染额外空格或空括号。

## 测试与验收

自动化测试覆盖：

- `percent` 映射为 `%`，`bytes` 映射为 `B`。
- `none`、`short`、枚举 JSON、空单位均不展示单位。
- 未知单位和单位列表未加载时只显示指标名称。
- 单位列表后到时，可从“指标名称”更新为“指标名称（展示单位）”。
- 展示标签变化不改变指标选项的 `value`。

页面验收：

- 公式模式下多个指标分别显示各自原始单位。
- 单指标模式使用相同展示规则。
- 下拉搜索、选择、清空、编辑回填行为保持正常。
- 计算结果单位和阈值单位的既有逻辑不受影响。

## 范围外

- 不修改后端接口或数据库字段。
- 不自动推导公式结果单位。
- 不对未知单位补充新的单位元数据。
- 不调整指标名称、公式布局或单位选择控件样式。
