# 日志策略表单 · 关键字 / 聚合分类走查修正

Status: approved（2026-10-28 产品走查并确认决断，待实现）

产品决策来源：2026-10-28 对日志「关键字告警」与「聚合规则告警」两类策略表单的分类走查。
两类策略职责不同：关键字是「查询命中即告警」，聚合是「查询圈定日志 → 规则统计后比阈值」。
本次只改前端与文案，**不改条件数据结构、不改后端校验与扫描**。沿用
`docs/design/product-decisions/log-policy-calc-methods.md` 的既定决策（命名函数、无公式编辑器、
无策略级无数据开关、样本条数不进表单），不重开。

前置：`specs/changes/log-policy-condition-editor/spec.md`（分行卡）已在工作区实现，本次在其之上修正。

## Problem Statement

| 类型 | 问题 | 证据 |
|---|---|---|
| 聚合 | 查询条件说明「一旦命中，将产生告警」是关键字口径 | `alertConditionsForm.tsx` 两类共用 `log.event.queryCriteriaTips` |
| 聚合 | 变化量 / 变化率 / 速率 / 去重计数 / 分位数 / 占比 / 字节速率的阈值是自由文本，`abc` 能过表单、保存才被服务端拒绝 | `conditionSelector.tsx` 阈值用 `Input`；`policyFormUtils.hasIncompleteCondition` 只查非空；服务端 `PolicySerializer._validate_aggregate_condition` 要求 `_is_finite_number` |
| 聚合 | 当前值仍提供「包括 / 不包括」，但比较的是统计结果这个数：`_compare_values` 对 `in`/`nin` 做 `str(expected) in str(actual)`，计数 100「包括 10」会命中 | `server/apps/log/tasks/services/policy_scan.py` `_compare_values` |
| 关键字 | 连续次数说明「都满足才告警」，关键字没有规则可满足 | `log.event.triggerCountTip` 两类共用 |
| 共用 | 展示字段 `timestamp`、`message` 下拉里没有、可以点掉、保存时又被 `getDefaultShowFields` 加回 | `alertConditionsForm.tsx` 展示字段 Select；`buildStrategyPayload` |
| 共用 | 检测频率远稀于检测周期时，一轮最多补扫 `MAX_BACKFILL_COUNT = 10` 个周期，中间日志不会被检测，页面无提示 | `server/apps/log/tasks/policy.py` 补偿逻辑 |
| 共用 | 分组查询 `limit=1000`，超出的分组静默不参与检测，说明未提及 | `policy_scan.py` 关键字 / 聚合分组查询 |

## 决断（已确认）

- **当前值的包括 / 不包括**：新建不再提供；读入旧条件 `op` 为 `in` / `nin` 时原样显示，用户改成别的后不再出现。服务端不动，继续接受旧值。
- **分组 1000 上限**：不提高，只写进说明。一窗 1000 个分组已是告警风暴而非漏报；正确做法是收窄分组字段。
- **频率 / 周期提示**：只提示不拦截。频率密于周期、窗口重叠是正常用法。
- 明确不做：`≥` / `≤` 不进下拉；关键字不加「至少 N 条」门槛；样本条数不进表单；不改 `buildStrategyPayload` 对关键字写 `rule.trigger_count` 的现有契约（`policyFormUtils.test.ts` 已锁定）。

## 详细设计

### 文件

| 文件 | 变更 |
|---|---|
| `web/src/app/log/(pages)/event/strategy/detail/alertConditionsForm.tsx` | 查询说明、连续次数说明按 `lockedPolicyType` 选键；展示字段固定项；频率 / 周期提示；规则校验区分「不完整」与「阈值非数值」 |
| `web/src/app/log/(pages)/event/strategy/detail/conditionSelector.tsx` | 数值比较场景阈值改 `InputNumber`；比较符列表去掉包括 / 不包括，仅旧值回显 |
| `web/src/app/log/(pages)/event/strategy/detail/policyFormUtils.ts` | 新增 `isNumericCompare`、`hasNonNumericThreshold`、`FIXED_SHOW_FIELDS` 导出、`getBackfillGapWarning` |
| `web/src/app/log/locales/zh.json`、`en.json` | 见「文案」 |
| `web/src/app/log/__tests__/logPolicyCalcMethods.i18n.test.ts` | `keys` 加新键 |
| `web/src/app/log/(pages)/event/strategy/detail/__tests__/*.test.tsx`、`policyFormUtils.test.ts` | 见「测试」 |
| `specs/changes/log-policy-condition-editor/spec.md` | 「行 3 触发」运算符段落改为本文口径 |

不改：`page.tsx`、`basicInfoForm.tsx`、`notificationForm.tsx`、`types/*`、`constants/index.ts`、任何 `server/` 文件。

### A 聚合

#### A1 查询条件说明

新键 `log.event.aggregateQueryCriteriaTips`。`alertConditionsForm.tsx` 查询条件下方：
`lockedPolicyType === 'aggregate' ? t('log.event.aggregateQueryCriteriaTips') : t('log.event.queryCriteriaTips')`。
`queryCriteriaTips` 文案不改。

#### A2 数值阈值

`policyFormUtils.ts` 新增并导出：

```ts
const NUMERIC_ONLY_FUNCS = new Set(['count_rate', 'count_delta', 'count_uniq', 'quantile', 'ratio', 'bytes_rate']);
/** 与 PolicySerializer 一致：数值函数，或比较方式不是当前值时，阈值必须是有限数。 */
export const isNumericCompare = (func?: string | null, kind?: string | null) =>
  NUMERIC_ONLY_FUNCS.has(String(func)) || (kind || 'absolute') !== 'absolute';
/** 数值比较场景下阈值不是有限数。只在 hasIncompleteCondition 为 false 后调用。 */
export const hasNonNumericThreshold = (conditions: FilterItem[]) =>
  conditions.some((item) => {
    const kind = presentCompare(item.compare).kind || 'absolute';
    return isNumericCompare(item.func, kind) && !Number.isFinite(Number(item.value));
  });
```

`conditionSelector.tsx` 里现有的 `NUMERIC_ONLY_FUNCS` 常量删掉，改从 `policyFormUtils` 引 `isNumericCompare`。

触发行阈值控件：

- `isNumericCompare(func, compareKind)` 为真时渲染 `InputNumber`：`style={{ width: 140 }}`、不设 `min`（骤降要负数）、不设 `precision`（占比、分位数可为小数）、`placeholder={t('log.event.enterThreshold')}`、`addonAfter` 沿用现有 `thresholdAddon`。`value` 为 `Number.isFinite(Number(conditionItem.value)) && conditionItem.value !== '' ? Number(conditionItem.value) : null`；`onChange={(val) => handleNumericValueChange(val, index)}`，写入 `String(val ?? '')`。`FilterItem.value` 类型保持 `string`，载荷不变。
- 否则保持现有 `Input` + `handleValueChange`。
- 旧条件值为 `abc` 的数值比较打开后数字框为空，保存被规则校验拦住，符合预期。

`alertConditionsForm.tsx` `validateConidtion`：

```ts
if (!term || !conditions.length) reject(t('log.event.ruleValidate'));
if (hasIncompleteCondition(conditions)) reject(t('log.event.conditionValidate'));
if (hasNonNumericThreshold(conditions)) reject(t('log.event.thresholdNumberValidate'));
```

#### A3 比较符

- `conditionSelector.tsx` 删除 `allowsMembershipOp`，`MEMBERSHIP_OPS` 保留只用于回显判断。
- 运算符 `Select` 的 `options`：`conditionList.filter((item) => !MEMBERSHIP_OPS.has(String(item.id)))`；若当前 `conditionItem.op` 是 `in` / `nin` **且** `!isNumericCompare(func, compareKind)`，把对应 `conditionList` 项追加到末尾（旧值回显）。
- `value`：`MEMBERSHIP_OPS.has(op) && isNumericCompare(func, compareKind) ? undefined : op`。
- `handleConditionChange('func')` 与 `handleCompareKind` 里现有「切到数值比较时把 `in`/`nin` 清成 `null`」的逻辑保留，判定改用 `isNumericCompare`。
- 结果：新建任何条件下拉都是 等于 / 不等于 / 大于 / 小于；旧策略 `count` + 当前值 + `in` 打开仍显示「包括」。

### B 关键字

#### B1 连续次数说明

新键 `log.event.keywordTriggerCountTip`。连续次数下方：
`lockedPolicyType === 'keyword' ? t('log.event.keywordTriggerCountTip') : t('log.event.triggerCountTip')`。

### C 共用

#### C1 展示字段固定项

- `policyFormUtils.ts` 导出 `FIXED_SHOW_FIELDS = ['timestamp', 'message'] as const`，`DEFAULT_SHOW_FIELDS` 改为引用它；`getDefaultShowFields` 逻辑不变（固定项在前、去重）。
- `Form.Item name="show_fields"` 加 `normalize={(value) => getDefaultShowFields(value)}`，任何变更都把固定项并回去。
- 展示字段 `Select` 加 `tagRender`：固定项 `closable={false}`、其余 `closable`，其它 props（`label`、`onClose`）透传给 AntD `Tag`。保持 `maxTagCount="responsive"`。
- `log.event.displayFieldsDes` 末尾追加「timestamp、message 固定展示。」（en：`timestamp and message are always shown.`）。

#### C2 频率 / 周期提示

`policyFormUtils.ts` 新增：

```ts
/** 与服务端 AlertConstants.MAX_BACKFILL_COUNT 一致：一轮最多补扫 10 个周期。 */
export const MAX_BACKFILL_COUNT = 10;
const UNIT_SECONDS: Record<string, number> = { min: 60, hour: 3600, day: 86400 };
export const toTimingSeconds = (value: unknown, unit: string) =>
  typeof value === 'number' && Number.isFinite(value) ? value * (UNIT_SECONDS[unit] || 0) : 0;
/** 频率超过周期 × 补扫上限时返回 true。 */
export const hasBackfillGap = (schedule: unknown, unit: string, period: unknown, periodUnit: string) => {
  const s = toTimingSeconds(schedule, unit);
  const p = toTimingSeconds(period, periodUnit);
  return s > 0 && p > 0 && s > MAX_BACKFILL_COUNT * p;
};
```

`alertConditionsForm.tsx`：`const schedule = Form.useWatch('schedule'); const period = Form.useWatch('period');`
（组件在 `<Form>` 内，`useWatch` 走 FormContext，无需传 form）。检测周期说明下方，`hasBackfillGap(schedule, unit, period, periodUnit)` 为真时追加
`<div className="mt-1 text-[var(--color-warning)]">{t('log.event.backfillGapWarning', undefined, { count: MAX_BACKFILL_COUNT })}</div>`。
不加表单校验，不拦保存。

#### C3 分组上限说明

`log.event.groupByFieldsDes` 末尾追加「单次检测最多处理 1000 个分组，超出不参与检测。」（en：`Each run handles at most 1000 groups; the rest are skipped.`）。

### 文案（`log.event.*`）

| key | zh | en |
|---|---|---|
| `aggregateQueryCriteriaTips`（新） | 查询条件只用于圈定参与统计的日志，是否告警由下方规则决定 | The query only selects the logs to aggregate; the rule below decides whether to alert |
| `keywordTriggerCountTip`（新） | 连续 N 个检测窗都有命中才告警 | Alert only after N consecutive detection windows each have a match |
| `thresholdNumberValidate`（新） | 该比较只支持数值阈值 | This comparison only accepts a numeric threshold |
| `backfillGapWarning`（新） | 检测频率超过检测周期的 {count} 倍，每次运行最多补扫 {count} 个周期，中间的日志不会被检测 | Frequency exceeds {count}× the period; each run backfills at most {count} periods, logs in between are not checked |
| `displayFieldsDes`（改） | 原文 + 「timestamp、message 固定展示。」 | 原文 + ` timestamp and message are always shown.` |
| `groupByFieldsDes`（改） | 原文 + 「单次检测最多处理 1000 个分组，超出不参与检测。」 | 原文 + ` Each run handles at most 1000 groups; the rest are skipped.` |

`queryCriteriaTips`、`triggerCountTip`、`conditionValidate` 不改。
四个新键加进 `logPolicyCalcMethods.i18n.test.ts` 的 `keys`。

### 测试

`conditionSelector.test.tsx`（`t` mock 为 `key => key`）：

- 变化率：阈值是 `spinbutton`（`InputNumber`），输入 `-30` 触发 `onChange`，`value` 为 `'-30'`；`%` addon 仍在。
- 当前值 + 计数（新建，`op: null`）：运算符下拉只有 `log.equalto`、`log.notequalTo`、`log.moreThan`、`log.lessThan`；阈值仍是 `textbox`。
- 旧条件 `count` + 当前值 + `op: 'in'`：收起态显示 `log.include`（按 `useConditionList` 实际 key），下拉含它。
- 旧条件 `count` + `op: 'in'` 切到变化量：`onChange` 收到 `op: null`（现有用例保留）。
- 现有 11 条用例保持通过，按新结构调整 combobox / textbox 计数。

`alertConditionsForm.test.tsx`（Harness 支持传 `policyType`）：

- `policyType="aggregate"`：出现 `log.event.aggregateQueryCriteriaTips` 与 `log.event.triggerCountTip`。
- `policyType="keyword"`：出现 `log.event.queryCriteriaTips` 与 `log.event.keywordTriggerCountTip`；不渲染规则区。
- 展示字段：初值 `['timestamp','message','level']`，模拟去掉 `message` 后 `form.getFieldValue('show_fields')` 仍含 `timestamp`、`message`；固定项 tag 无关闭图标。
- 频率 1 `day` + 周期 5 `min` → 出现 `log.event.backfillGapWarning`；5 `min` + 5 `min` → 不出现。
- 规则校验：条件完整但阈值 `abc` 且比较为变化率 → `validateFields` 失败信息为 `log.event.thresholdNumberValidate`。

`policyFormUtils.test.ts`：

- `isNumericCompare('count','absolute') === false`、`('count','percent') === true`、`('count_rate','absolute') === true`。
- `hasNonNumericThreshold`：percent + `'abc'` → true；absolute `count` + `'error'` → false；percent + `'-30'` → false。
- `hasBackfillGap(1,'day',5,'min') === true`、`(5,'min',5,'min') === false`、`(1,'hour',5,'min') === true`、`(50,'min',5,'min') === false`。
- `getDefaultShowFields(['level','message'])` → `['timestamp','message','level']`。

### 验收

- `cd web && pnpm exec vitest run 'src/app/log/(pages)/event/strategy/detail/__tests__' src/app/log/__tests__/logPolicyCalcMethods.i18n.test.ts` 全绿。
- `cd web && pnpm lint` 对改动文件无新增告警；`cd web && pnpm type-check` 通过。
- 本机前端在跑时，走查 `/log/event/strategy/detail?type=add&alert_type=keyword` 与 `?alert_type=aggregate`：
  两页查询说明、连续次数说明不同；展示字段 `timestamp`、`message` 无关闭图标；频率 1 天 + 周期 5 分钟出现警告色提示；
  聚合页选变化率后阈值为数字框、下拉无包括 / 不包括。
- `git status` 中与本次无关的脏文件（`web/next-env.d.ts`、`deploy/bk-lite-deploy-local.tgz`、`server/apps/apm/**`、`web/src/app/apm/**`、`specs/changes/apm-*`）保持原状，不提交。
