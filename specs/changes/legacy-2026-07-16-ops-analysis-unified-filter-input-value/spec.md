# Historical Superpowers change: 2026-07-16-ops-analysis-unified-filter-input-value

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-16-ops-analysis-unified-filter-input-value.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让普通统一筛选器把用户输入的实际值写入状态并进入组件请求参数。

**Architecture:** 在事件第一次错误进入值链路的 `ParamInputControl` fallback 边界做一次通用归一化。保留 select、radio、organization、timeRange 现有行为，请求转换层无需改动。

**Tech Stack:** React 19、TypeScript、Ant Design、Node assert/tsx

## Global Constraints

- 不针对页面、`department` 或任何筛选 ID 硬编码。
- 不改变后端接口协议或时间筛选行为。
- 清空和重置后不得残留旧值。
- 不进行无关重构。

---

### Task 1: 修复 fallback 输入值适配

**Files:**
- Create: `web/scripts/ops-analysis-unified-filter-input-test.ts`
- Create: `web/src/app/ops-analysis/components/normalizeParamInputChangeValue.ts`
- Modify: `web/src/app/ops-analysis/components/paramInputControl.tsx`
- Modify: `web/package.json`

**Interfaces:**
- Consumes: Ant Design `Input` 的 `ChangeEvent` 或现有控件的直接 `string | number | null` 值。
- Produces: `normalizeParamInputChangeValue(value): string | number | null`，供 fallback 回调向统一筛选状态传递实际值。

- [ ] **Step 1: 写失败测试**

创建脚本，断言 `{ target: { value: '数据部' } }` 被归一化为 `'数据部'`，并断言 `''`、字符串、数字、null 保持原值；同时通过 `processDataSourceParams` 验证 `'数据部'` 最终生成 `{ department: '数据部' }`，空字符串删除 department。

- [ ] **Step 2: 运行测试并确认失败原因**

Run: `pnpm exec tsx scripts/ops-analysis-unified-filter-input-test.ts`

Expected: FAIL，因为 `normalizeParamInputChangeValue` 尚未导出或事件对象仍原样进入状态。

- [ ] **Step 3: 写最小实现**

在 `paramInputControl.tsx` 导出值归一化函数，并让 `renderFallback` 覆盖的 `onChange` 调用该函数后再通知上游。仅识别包含 `target.value` 的输入事件，其余直接值保持不变。

- [ ] **Step 4: 运行聚焦与现有回归测试**

Run: `pnpm exec tsx scripts/ops-analysis-unified-filter-input-test.ts`

Expected: PASS，输出统一筛选输入测试通过。

Run: `pnpm test:ops-analysis-component-param-switch`

Expected: PASS，输出现有运营分析组件参数切换测试通过。

- [ ] **Step 5: 静态检查**

Run: `pnpm exec eslint src/app/ops-analysis/components/paramInputControl.tsx scripts/ops-analysis-unified-filter-input-test.ts`

Expected: exit code 0。

- [ ] **Step 6: 记录项目修复信息**

使用 `pjm attempt` 记录事件对象复现，使用 `pjm fix` 记录 fallback 边界适配及验证结果，不记录业务数据或秘密。

## specs: 2026-07-16-ops-analysis-unified-filter-input-value-design.md

## 问题与根因

普通字符串筛选器由 `UnifiedFilterBar` 生成 Ant Design `Input` fallback。该输入框原本把 `ChangeEvent` 转换为 `event.target.value`，但 `ParamInputControl.renderFallback` 使用 `cloneElement` 再次覆盖 `onChange`，把其“直接值”回调传给了 Ant Design `Input`。因此用户输入“数据部”后，筛选本地状态第一次写入的是事件对象而非字符串；该对象序列化到请求中表现为 `{}`。

时间筛选器直接调用 `handleTimeRangeChange`，不经过 `ParamInputControl` fallback，所以 `billing_period` 正常。下拉与单选控件本身也已显式提取值。

## 修复设计

在 `ParamInputControl` 的 fallback 边界统一适配输入回调：如果回调参数具有 DOM 输入事件的 `target.value`，向上游传递 `target.value`；否则保留原来的直接值。这一修改作用于所有使用 input fallback 的普通筛选器，不依赖页面、筛选 ID 或参数名。

值为清空后的空字符串时必须原样传递，使搜索参数转换继续删除空筛选值；重置仍由 `UnifiedFilterBar` 按定义生成 `null` 或默认值，不改变现有逻辑。时间、select、radio、organization 分支不修改。

## 验证

增加一条聚焦回归测试，证明 DOM 输入事件被转换为“数据部”，直接字符串/数字/null 仍保持原值。随后运行该测试、现有运营分析参数控件测试及 TypeScript/ESLint 的相关文件检查。

## 范围

仅修改公共参数输入控件的 fallback 值适配及对应测试，不修改后端协议，不过滤请求中的空对象，不硬编码 `department`，不调整筛选绑定或时间筛选实现。
