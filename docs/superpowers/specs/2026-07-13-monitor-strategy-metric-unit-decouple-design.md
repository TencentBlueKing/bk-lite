# 监控策略 — 计算指标单位与阈值单位解耦 + 单位 Cascader 设计

## 背景

监控策略详情页 (`web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`) 当前用单个 React state `calculationUnit` 同时承担两个语义角色：

1. 「计算指标单位」—— 公式结果或单指标的最终展示/转换单位
2. 「阈值单位」—— `ThresholdList` 里 InputNumber addonAfter 的单位 + 阈值过滤的基准

代码现状：

- `page.tsx:727 handleCalculationUnitChange`（来自阈值单位选择器）和 `page.tsx:732 handleFormulaResultUnitChange`（来自公式结果单位）都写同一个 `setCalculationUnit`
- `page.tsx:806` 把这个值原样作为 `params.calculation_unit` 提交
- 阈值单位选项 (`strategyDetailUtils.ts:152 getThresholdUnitOptions`) 用 `metricUnit`（指标自带 unit）的 `system` 过滤；用户改了阈值单位后，因为是同一个 state，反过来会"覆盖"计算指标单位

服务端早就支持两个字段独立（迁移 `0023_monitorpolicy_calculation_unit_and_more`）：

- `metric_unit` —— 指标原生的最小单位（来自指标自带的 `unit`）
- `calculation_unit` —— 展示/转换单位（用于阈值比较、服务端单位换算）

`server/apps/monitor/tasks/services/policy_scan/metric_query.py:50` 用两字段独立判断 `_unit_conversion_enabled`，前端只用 `calculation_unit` 一个字段没有发挥出后端的能力。

样式层面：当前 `metricExpressionEditor.tsx:374` 的"结果单位"选择器是 `<Select>` 把 `unitOptions`（已过滤 `none`/`short`）平铺下拉。插件指标创建 `metricModal.tsx:68` 用 `<Cascader options={groupedUnitList}>`，按 `category`（容量/时间/百分比...）分组展示，与用户体验期望不一致。

## 目标

1. 计算指标单位与阈值单位解耦：前者由 `metricUnit` state 表达，后者由 `thresholdUnit` state 表达，两者互不写回
2. 单位选择器改用 Cascader + `groupedUnitList`，按 `category` 分组，与插件指标创建保持一致
3. 入参 `params.metric_unit` 与 `params.calculation_unit` 独立提交，分别对应两个 state

## 非目标

- 不新增单位体系、不改单位换算规则
- 不改公式表达式语法、查询构建或后端扫描计算逻辑
- 不改 MetricPreview 预览图展示（仍展示 `calculation_unit`，即阈值单位）
- 不动公式模式下的结果单位交互（保持单槽位）
- 不重做指标编辑器其它 Select（如汇聚周期单位）
- 不修改后端迁移 / 模型 / 序列化器

## 方案比较

### 方案 A：拆分 state + Cascader（推荐）

- `page.tsx` 拆为 `metricUnit`（来自 `mertricTarget.unit`，可改） 与 `thresholdUnit`（阈值单位，独立）
- 非公式模式：在指标字段下方加 "计算指标单位" Cascader，数据源 `groupedUnitList`，默认 `mertricTarget.unit`
- 公式模式：`fx = ...` 行右侧结果单位改用 Cascader（保持单槽位语义不变）
- `strategyDetailUtils.ts` 新增 `buildMetricUnitCascaderOptions` / `isValidMetricUnit`，`getThresholdUnitOptions` 重构（基准 = `metricUnit`）
- `params.metric_unit = metricUnit`、`params.calculation_unit = thresholdUnit`（非公式）/ `calculation_unit = resolveFormulaResultUnit(resultUnit, unitList)`（公式）

优点：

- 直接命中两个需求点（联动解耦 + Cascader 分组展示）
- 与现有后端字段语义对齐
- 改动局限在 `strategy/detail` 子目录
- 测试基建 `web/scripts/monitor-strategy-detail-logic-test.ts` 已就绪

缺点：

- UI 多一个控件（计算指标单位 Cascader），需要前后端默认值约束清晰
- 切换指标时需保证新指标的 `system` 与旧 `metricUnit` 兼容（实现在 `handleMetricChange` 里 reset）

### 方案 B：拆分 state + 保留 Select

- 同方案 A，但单位选择器保留 `<Select>` 平铺

优点：改动最小
缺点：未解决样式问题，不符合需求

### 方案 C：全局重做单位控件

- 把 `MetricExpressionEditor` 里的所有 Select 全换 Cascader

优点：UI 一致性最好
缺点：超出本次需求范围，YAGNI；改动风险面变大

## 推荐

方案 A。

## 详细设计

### 架构

State 拆分：

| 字段 | 类型 | 写入位置 | 读出位置 | 入参 |
|------|------|---------|---------|------|
| `metricUnit` | `string \| null` | `handleMetricChange` / 公式↔单指标切换 | `MetricDefinitionForm` 显示 & Cascader 默认值 | `params.metric_unit` |
| `thresholdUnit` | `string \| null` | `handleThresholdUnitChange` (来自 ThresholdList onUnitChange) | 阈值 InputNumber addonAfter、过滤选项基准 | `params.calculation_unit`（非公式） |
| `resultUnit`（公式） | `string \| null` | `handleResultUnitChange` (Cascader) | 公式结果单位显示 | `params.calculation_unit`（公式） |

非公式模式下：`metricUnit` 与 `thresholdUnit` 解耦，`thresholdUnit` 不回写 `metricUnit`。
公式模式下：仍只有 `resultUnit`，作为 `calculation_unit` 与阈值筛选基准（保持现状）。

### 组件接口

#### `metricExpressionEditor.tsx`

新增 prop：

```ts
metricUnit: string | null;
onMetricUnitChange: (value: string) => void;
groupedUnitOptions: CascaderItem[]; // 由 page.tsx 传入,data source = groupedUnitList
```

公式行（fx）的结果单位改为 Cascader：

```tsx
<Cascader
  options={groupedUnitOptions}
  value={resultUnit ? findCascaderPath(groupedUnitOptions, resultUnit) : []}
  onChange={(path) => onResultUnitChange(path.at(-1))}
  showSearch
/>
```

非公式模式：计算指标单位 Cascader 不放在编辑器内（编辑器的语义是「表达式构建」，单位属于结果配置）；改放在 `metricDefinitionForm.tsx` 的「指标」字段下方，紧挨公式编辑器，标签「计算指标单位」。

#### `thresholdList.tsx`

- `calculationUnit` prop 改名 `thresholdUnit`（语义更清晰）
- `onUnitChange` 改名 `onThresholdUnitChange`
- UI 行为不变（仍是 Select，过滤范围由父级传入的 `unitOptions` 决定）

#### `alertConditionsForm.tsx`

- 把 `metricUnit`（来自指标自带 unit）从 props 里剥离
- 新增 `thresholdUnit` prop（替换旧的 `calculationUnit`）
- `onThresholdUnitChange` 替换旧的 `onCalculationUnitChange`
- `getThresholdUnitOptions` 基准改用 `thresholdUnit || metricUnitFallback`

#### `strategyDetailUtils.ts`

新增：

```ts
// 给 metricUnit Cascader 用:从 groupedUnitList 反查可选项（全量）
export const buildMetricUnitCascaderOptions = (
  groupedUnitList: GroupedUnitList[]
): CascaderItem[];

// 给 metricUnit Cascader 用:校验单位是否合法（不在 none/short 集内）
export const isValidMetricUnit = (
  unit: string | null | undefined,
  groupedUnitList: GroupedUnitList[]
): boolean;
```

`getThresholdUnitOptions` 重构：基准参数从 `unitFilterBase: string | null` 改成 `metricUnit: string | null | undefined`，内部仍按 `system` 过滤。

### 数据流

#### 单指标模式（用户切换指标）

```
用户选 metric = "disk.used"
  ↓
handleMetricRowsChange → handleMetricChange (nextPrimaryMetricName)
  ↓
const target = metrics.find(...);
setMetricUnit(target?.unit ?? null);     // 默认锁定指标自带单位
setThresholdUnit(target?.unit ?? null);  // 默认同步,用户可改
  ↓
MetricDefinitionForm 接收新 metricUnit, Cascader 默认值更新
ThresholdList 接收新 thresholdUnit, Select 默认值更新
```

#### 用户改 metricUnit（计算指标单位）

```
MetricDefinitionForm.onMetricUnitChange(newUnit)
  ↓
page.setMetricUnit(newUnit)
  ↓
不影响 thresholdUnit,不影响 calculation_unit
  ↓
params.metric_unit = newUnit (提交时)
```

#### 用户改 thresholdUnit（阈值单位）

```
ThresholdList.onThresholdUnitChange(newUnit)
  ↓
page.setThresholdUnit(newUnit)
  ↓
不影响 metricUnit
  ↓
params.calculation_unit = newUnit (提交时)
```

#### 公式模式

```
handleResultUnitChange (Cascader onChange)
  ↓
page.setResultUnit(newUnit)
  ↓
metricUnit = '' (提交时)
calculation_unit = resolveFormulaResultUnit(newUnit, unitList)
```

#### 公式 ↔ 单指标 切换

- 单指标 → 公式：`metricUnit` 清空，`thresholdUnit` 由 `getCalculationUnitOnMetricRowsChange` 接管（保留当前逻辑）
- 公式 → 单指标：`metricUnit = target?.unit`，`thresholdUnit = target?.unit`（用户后续可独立调整）

### 错误处理

- **Cascader 选了非法单位**：`isValidMetricUnit` 拦截，不写 state
- **指标切换后，旧 `metricUnit` 不在新指标的 system 内**：`handleMetricChange` 重置 `metricUnit = target?.unit`（沿用旧逻辑）
- **阈值单位在切换指标后失效**：`getThresholdUnitOptions` 用新 `metricUnit` 重新过滤；若旧的 `thresholdUnit` 不在新过滤集内，UI 上 Select 选不中（保留旧值不报错，让用户手动改）
- **公式模式无 `resultUnit`**：`resolveFormulaResultUnit` 返回 `null`，`params.calculation_unit = ''`，阈值校验 `validateThreshold` 报错

### 改动文件

| 文件 | 变更 |
|------|------|
| `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx` | 拆 state、加 `metricUnit` 流向、入参拆分 |
| `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx` | 加 `metricUnit` prop、"计算指标单位" Cascader |
| `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx` | 公式行结果单位改 Cascader、新增 prop |
| `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx` | `calculationUnit`→`thresholdUnit` 重命名、`metricUnit` prop 注入 |
| `web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx` | prop 重命名（语义更清晰） |
| `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts` | 新增 `buildMetricUnitCascaderOptions` / `isValidMetricUnit`，`getThresholdUnitOptions` 重构 |
| `web/scripts/monitor-strategy-detail-logic-test.ts` | 加新断言 |

### 测试

#### 单元（`scripts/monitor-strategy-detail-logic-test.ts` 扩展）

- `buildMetricUnitCascaderOptions(groupedUnitList)` —— 输入包含 `none/short`，输出 Cascader options 全部保留
- `isValidMetricUnit('bytes', groupedUnitList)` → true
- `isValidMetricUnit('none', groupedUnitList)` → false
- `isValidMetricUnit('unknown', groupedUnitList)` → false
- `getThresholdUnitOptions` 新签名：以 `metricUnit='bytes'` 为基准，返回 bytes system 内所有单位；切到 `metricUnit='seconds'`，只返回 seconds system

#### 手动 / e2e

- 新建策略：选容量类指标（如 disk.used，bytes）
  - 仅改阈值单位为 MB → 提交后 `metric_unit=bytes, calculation_unit=MB`
  - 改 metricUnit 为 KB → 提交后 `metric_unit=KB, calculation_unit` 保持之前选择
  - 都改 → 提交后两字段独立
- 公式模式：选公式并改结果单位 → 提交后 `metric_unit='', calculation_unit=...`
- 编辑已有策略：来回切换指标 / 单位，确认无脏值残留
- 跨系统单位（容量 vs 时间）：Cascader 不应跨 category 串