# 日志聚合策略 · 告警条件编辑器（分行卡）

Status: implemented（2026-10-28 产品确认方案 1，同日实现，未提交）

实现偏差（已接受）：
- 「规则」`Form.Item` 加 `trigger="onCollect"`：条件编辑器成为该字段唯一子节点后，AntD 会把 `onChange` 的条件数组写进表单字段 `rule`；指向一个不存在的触发名后条件仍只走父组件 state，保存载荷与改前一致。
- 栏头与每张卡的 `Radio.Group` 各自带 `name`，否则同一 `Form.Item` 内会合成一组原生单选，点「变化率」会清掉「任意 / 全部」。
- 函数下拉选中态只显示中文名（`optionLabelProp="label"`），下拉项与搜索仍带英文方法名（`optionFilterProp="title"`），避免 140px 内截断。
- Story 内包了一层日志中文 `IntlProvider`，Storybook 全局消息不含 `log` 文案。

产品决策来源：2026-10-28 对日志聚合策略「规则」条件行的设计走查，对照 Monitor「指标编辑器」
（`web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`、`metricConditionCard.tsx`）
与 APM「告警条件」（`web/src/app/apm/events/policies/policy-editor.tsx` 第三步）后确认：
日志策略的条件编辑迁到仓库已有的策略编辑语言，不再发明第二种。
条件模型沿用 `docs/design/product-decisions/log-policy-calc-methods.md`（函数 × 比较方式 × 对照），本次**不改数据契约、不改后端**。

## Problem Statement

`web/src/app/log/(pages)/event/strategy/detail/conditionSelector.tsx` 把一条条件平铺成五个等宽控件：
「选择函数 / 选择字段 / 绝对值 / 选择条件 / 填写阈值」+ 行尾「＋」。问题：

- 五个占位框之间没有连接词，读不成句；用户看不出这一行最后会变成什么。
- 「绝对值」是实现词，默认态直接暴露给用户。
- 「＋ 添加」和「✕ 删除」同形同位，第一条没有删除。
- 「满足下面 [任意条件]」是一个孤立 Select，和条件行之间没有语法关系。
- 仓库里 Monitor、APM 两个策略编辑器已经是「面板 → 条件卡 → 一个决定一行并带标签 → 『当结果 > 阈值』收尾」，日志是唯一例外，视觉上显得粗糙。

## Solution

把「规则」这一项的控件区重做成**条件编辑器面板**：

```
规则 *   ┌──────────────────────────────────────────────────────────┐
         │ 满足 [任意 | 全部] 条件                                   │  ← 面板栏头
         ├──────────────────────────────────────────────────────────┤
         │ ┌ 1 ┐  统计  [计数 ▾] [level ▾]                      ✕  │  ← 条件卡
         │ │   │  比较  [当前值 | 变化量 | 变化率]                   │
         │ └───┘  触发  当结果 [> ▾] [100        ]                  │
         │ ┌ 2 ┐  统计  [平均值 ▾] [duration ▾]                 ✕  │
         │ │   │  比较  [当前值 | 变化量 | 变化率●] 对照 [N 小时前 ▾] [24 小时] │
         │ └───┘  触发  当结果 [> ▾] [20      %]                    │
         │        对照为 0 时不判定                                  │
         │ [＋ 添加条件]                                             │
         └──────────────────────────────────────────────────────────┘
```

- 一条条件 = 一张卡，卡内三行：**统计**（函数 + 字段 + 函数参数）、**比较**（当前值 / 变化量 / 变化率 → 对照）、**触发**（当结果 运算符 阈值 单位）。顺序即用户的思考顺序。
- 不可比较的函数（速率、占比、字节速率）**不渲染**「比较」行，而不是禁用。
- 「满足 任意 / 全部 条件」放在面板栏头左侧，用 `Radio.Group optionType="button" size="small"`。
- 删除是卡右上角的文字图标按钮，只在条件数 > 1 时出现；添加是面板底部的 `type="dashed"` 按钮。
- 提示文字（对照为 0、分母为 0、旧变化量提示）放在该卡三行之下，统一 `text-xs leading-5 text-[var(--color-text-3)]`。

明确不做：公式编辑器、胶囊式 Popover 编辑、改条件数据结构、改后端校验、改 Monitor / APM / 日志分组（`integration/grouping/editInstance.tsx`）的现有条件行。

## 详细设计

### 组件与文件

| 文件 | 变更 |
|---|---|
| `web/src/app/log/(pages)/event/strategy/detail/conditionSelector.tsx` | 重写为条件编辑器面板（保留文件名与默认导出 `ConditionSelector`，避免无关引用改动）。新增 props `term: string \| null`、`onTermChange: (val: string) => void`。 |
| `web/src/app/log/types/event.ts` | `ConditionFilterProps` 增加上述两个 props。 |
| `web/src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx` | 「规则」`Form.Item` 内删除原「满足下面 + Select」块，把 `term` / `onTermChange` 传给 `ConditionSelector`。其余字段不动。 |
| `web/src/app/log/(pages)/event/strategy/index.module.scss` | 删除不再使用的 `.form .conditions` 样式块（含 `li` 规则）。不新增 SCSS。 |
| `web/src/app/log/locales/zh.json`、`en.json` | 见「文案」。 |
| `web/src/app/log/__tests__/logPolicyCalcMethods.i18n.test.ts` | 该测试按 key 清单校验 zh / en 双语都存在，把本次新增的 12 个 key 加进 `keys` 数组。 |
| `web/src/app/log/(pages)/event/strategy/detail/__tests__/conditionSelector.test.tsx` | 按新结构更新断言并补用例（见「测试」）。 |
| `web/src/stories/log-policy-condition-editor.stories.tsx`（新建） | `ConditionSelector` 的 story 组，title `Business/Log/PolicyConditionEditor`，写法参照 `web/src/stories/multi-threshold-grid.stories.tsx`（见「Storybook」）。 |

不改：`policyFormUtils.ts`（`normalizeCondition` / `hasIncompleteCondition` / `aggregateTemplateVariables`）、`page.tsx` 的状态管理（初始 `term='or'`、一条空条件）、`constants/index.ts` 的列表、`utils/compareTarget.ts`。

### 面板

- 外壳：`rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg-1)] shadow-sm`，与 Monitor 指标编辑器同款。
- 栏头：`flex min-h-11 flex-wrap items-center gap-2 border-b border-[var(--color-border-2)] px-3`。
  内容：`<span>{t('log.event.matchPrefix')}</span>` + `Radio.Group`（`optionType="button" size="small"`，选项在组件内写死 `[{ value: 'or', label: t('log.event.termAny') }, { value: 'and', label: t('log.event.termAll') }]`，value 与现有 `useTermList()` 的 `'or'` / `'and'` 一致）+ `<span>{t('log.event.matchSuffix')}</span>`。
  `Radio.Group` 需要 `aria-label={t('log.integration.rule')}`。`alertConditionsForm.tsx` 不再使用 `useTermList` 时删除该 import（hook 本身保留，日志分组页仍在用）。
- 正文：`flex flex-col gap-3 p-3`。依次渲染条件卡，最后是 `<Button type="dashed" icon={<PlusOutlined />} className="w-fit">{t('log.event.addCondition')}</Button>`。
- `data.length === 0` 时正文只有添加按钮（页面层已保证新建时有一条空条件，这里不做自动补条）。

### 条件卡

- 外壳：`rounded-md border border-[var(--color-border-2)] bg-[var(--color-bg)] p-3`。可输入区域用 `--color-bg`，不要再用 `fill-1` 灰底（`web/DESIGN.md` Inputs 节）。
- 内部：`flex items-start gap-3`。
  - 左：序号徽标 `inline-flex h-7 w-7 shrink-0 items-center justify-center rounded border border-[var(--color-border-2)] font-mono text-xs font-semibold text-[var(--color-primary)]`，内容为 1 起的序号，带 `aria-label={t('log.event.conditionIndex', '条件 {index}', { index })}`（项目 `t` 的签名是 `t(id, defaultMessage?, values?)`，见 `web/src/utils/i18n.ts`）。
  - 中：`flex min-w-0 flex-1 flex-col gap-2.5`，放三行与提示。
  - 右：`data.length > 1` 时渲染 `<Button type="text" size="small" icon={<CloseOutlined />} aria-label={t('log.event.deleteCondition')} />`；只有一条时不渲染任何占位。
- 每一行：`flex flex-wrap items-center gap-2`，行首标签 `<span className="w-10 shrink-0 text-[var(--color-text-2)]">`。三行标签 key：`log.event.statRow`（统计）、`log.event.compareRow`（比较）、`log.event.triggerRow`（触发）。

#### 行 1 统计

- 函数 `Select`：`style={{ width: 140 }}`，`showSearch`、`optionLabelProp="label"`、`optionFilterProp="label"`，选项渲染沿用现有「中文名 +（METHOD）」写法与 `functionLabel` 逻辑。placeholder `log.event.selectFunction`。
- 字段 `Select`：`showField` 为真时渲染，`style={{ width: 160 }}`，placeholder `log.event.selectField`。
- 分位 `Select`：`needsQuantile` 时渲染，`style={{ width: 88 }}`，选项 `P50 / P90 / P95 / P99`。
- 占比分子：`needsFilter` 时渲染 `<span className="text-[var(--color-text-2)]">{t('log.event.ratioNumerator')}</span>` + `Input style={{ width: 220 }} placeholder={t('log.event.ratioFilter')}`。
- `showField` / `comparable` / `legacyDelta` 的计算逻辑与现有 `conditionSelector.tsx` 完全一致，不改。

#### 行 2 比较（仅 `comparable` 时渲染）

- `Radio.Group optionType="button" size="small"`，选项来自 `COMPARE_KIND_LIST`（三项），value 为 `compareKind`，onChange 走现有 `handleCompareKind`。需要 `aria-label={t('log.event.compareKind')}`。
- `compareKind !== 'absolute'` 时同一行续：`<span className="text-[var(--color-text-2)]">{t('log.event.compareTo')}</span>` + 对照 `Select`（`style={{ width: 120 }}`，选项 `COMPARE_OFFSET_METHOD_LIST`，`aria-label={t('log.event.compareTo')}`，onChange 走 `handleCompareTarget`）+ 自定义偏移时的 `InputNumber`（`style={{ width: 120 }}`，`min=1`、`max=compareOffsetLimit(to)`、`precision=0`、`addonAfter` 小时 / 天、`aria-label` 沿用现有 `compareOffsetCountHour` / `compareOffsetCountDay`，onChange 走 `handleOffset`）。

#### 行 3 触发

- `<span className="text-[var(--color-text-2)]">{t('log.event.whenResult')}</span>`。
- 运算符 `Select`：`style={{ width: 96 }}`，`optionLabelProp="label"`，选项来自 `useConditionList()`（`=`、`!=`、`>`、`<`、`in`、`nin`，不增不删）。选项内容显示「符号 + 中文」（如 `> 大于`），选中后只显示符号；`in` / `nin` 没有符号，选项与选中态都显示中文。placeholder `log.event.selectCriteria`。
- 阈值 `Input`：`style={{ width: 140 }}`，placeholder `log.event.enterThreshold`。有单位时用 AntD `addonAfter`（不再手写 `Space.Compact + span`）：
  - `count_rate` → `t('log.event.countRateUnit')`（条/秒）
  - `bytes_rate` → `t('log.event.bytesRateUnit')`（字节/秒）
  - `compareKind === 'percent'` 或 `func === 'ratio'` → `%`
  - 其余无 addon。
  `showUnitSuffix` 的判定与现有代码一致。

#### 提示

三行之下按现有条件渲染，class 统一 `text-xs leading-5 text-[var(--color-text-3)]`：
`legacyDelta` → `countDeltaTip`；`percent` → `percentTip`；`ratio` → `ratioFilterTip`。

### 行为（与现状完全一致）

所有 `onChange` 载荷与现有 handler 相同：`handleConditionChange`、`handleCompareKind`、`handleCompareTarget`、`handleOffset`、`handleQuantile`、`handleRatioFilter`、`handleValueChange`、`handleAddCondition`、`handleDeleteCondition`。
唯一的行为差异：删除按钮从「第 2 条起可删」改为「条件数 > 1 时每条都可删」。
`validateConidtion` 不动，校验错误仍由外层 `Form.Item` 展示在面板下方。

### 文案（`log.event.*`）

| key | zh | en |
|---|---|---|
| `matchPrefix` | 满足 | Match |
| `matchSuffix` | 条件 | of the conditions |
| `termAny` | 任意 | any |
| `termAll` | 全部 | all |
| `statRow` | 统计 | Stat |
| `compareRow` | 比较 | Compare |
| `triggerRow` | 触发 | Trigger |
| `whenResult` | 当结果 | When result |
| `ratioNumerator` | 分子 | Numerator |
| `addCondition` | 添加条件 | Add condition |
| `deleteCondition` | 删除条件 | Remove condition |
| `conditionIndex` | 条件 {index} | Condition {index} |

修改既有 key：`compareKindAbsolute` zh「绝对值」→「当前值」，en「Absolute」→「Current value」。
该 key 同时被试算结果和告警只读摘要使用，改后三处口径一致（与 APM「当前值」同词）。
`log.integration.meetRule`（满足下面）仍被日志分组页使用，**不改不删**。

### Storybook

新建 `web/src/stories/log-policy-condition-editor.stories.tsx`，用受控 `useState` 包一层 `ConditionSelector`（`term` 与 `data` 都受控）：

1. 默认：一条 `count` + `_msg` + `>` + 空值（新建态）。
2. 多条件：`count / level` 当前值、`avg / duration` 变化率 + `offset_hours: 24`、`quantile P95 / duration`、`ratio` 带分子、`count_rate`，共 5 条，验证最宽的一条在 820px 容器内的折行。
3. 窄容器：同上数据放进 `max-w-[560px]`。
4. 只有一条时无删除按钮。
与 `web/DESIGN.md` §7 一致：亮色、暗色都要看一遍。

### 测试

更新 `conditionSelector.test.tsx`（`vi.mock('@/utils/i18n')` 保持 `t: key => key`，注意带参数的 `t(key, params)` 也返回 key）：

- 速率：不渲染字段、不渲染比较 Radio；阈值 addon 显示 `log.event.countRateUnit`；输入 `0.5` 触发 `onChange`（现有断言，更新 combobox 计数：函数 + 运算符 = 2）。
- 旧 `count_delta`：显示 `countDeltaTip`。
- 变化率 + `offset_24h`：比较 Radio 选中 `compareKindPercent`；出现对照下拉、小时数 `InputNumber`（`getByLabelText('log.event.compareOffsetCountHour')`）、`%` addon、`percentTip`。
- 分位：显示 `P95` 与字段。
- 计数：渲染字段下拉（combobox：函数 + 字段 + 运算符 = 3）。
- 占比：分子输入、`ratioFilterTip`、`%`，改分子触发 `onChange`。
- 新增：栏头 Radio 渲染 `log.event.termAny` / `log.event.termAll`，点击「全部」触发 `onTermChange('and')`。
- 新增：只有一条时查不到 `log.event.deleteCondition`；两条时每条都有，点第一条触发 `onChange` 得到只剩第二条。
- 新增：点击 `log.event.addCondition` 触发 `onChange`，新数组末尾为 `{ field: null, op: null, value: '' }`。
- 新增：序号徽标文本 `1`、`2`。

`alertConditionsForm.test.tsx` 现有用例应保持通过；若 Harness 需要补 `term` 相关断言，加一条「栏头显示 matchPrefix」。

### 验收

- `cd web && pnpm exec vitest run 'src/app/log/(pages)/event/strategy/detail/__tests__' src/app/log/__tests__/logPolicyCalcMethods.i18n.test.ts` 全绿。
- `cd web && pnpm lint` 对改动文件无新增告警。
- `cd web && pnpm type-check` 通过（慢，可最后跑一次）。
- Storybook 四个 story 在亮 / 暗主题下：面板、卡、徽标、Radio 按钮、addon 单位颜色均来自 token，无硬编码色；窄容器下三行各自折行，不横向溢出。
- 页面走查（本机前端已在跑时）：日志 → 事件 → 策略 → 新建聚合策略 → 第一步「规则」区块与本文 ASCII 图一致；选速率后「比较」行消失；选变化率后同一行出现对照；删除只在多条时出现；保存载荷与改前相同。

### 交付说明（按 `web/DESIGN.md` §7 要求）

- 复用：AntD `Radio.Group(button)` / `Select` / `Input addonAfter` / `InputNumber` / `Button(dashed, text)`；面板与卡的 class 直接取自 Monitor `metricExpressionEditor.tsx` 与 `metricConditionCard.tsx`。
- 未新建 shared：Monitor 的 `MetricConditionCard` 带「指标 / 计算指标」切换，与日志卡头语义不同；日志卡结构内联在 `conditionSelector.tsx`，仍是 log app-local。若后续 Monitor 过滤行也迁到同一卡结构，再按 `web/COMPONENT_GOVERNANCE.md` 升 shared。
