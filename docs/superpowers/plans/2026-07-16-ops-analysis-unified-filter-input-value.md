# 运营分析统一筛选器输入值修复 Implementation Plan

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
