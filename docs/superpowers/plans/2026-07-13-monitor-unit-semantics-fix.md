# 监控策略单位语义修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复监控策略原始单位、计算单位、公式结果单位在编辑、预览和保存路径中的语义分叉，确保预览与实际扫描一致。

**Architecture:** `metric_unit` 只来自指标元数据并作为只读源单位；`calculation_unit` 是单指标阈值单位或公式结果单位。单位 payload 由 `formulaExpressionUtils.ts` 的纯函数统一推导，预览和保存共同调用；公式模式只保留一个结果/阈值单位状态。

**Tech Stack:** Next.js 16、React 19、TypeScript、Ant Design、pnpm、tsx + node:assert。

## Global Constraints

- 仅修改监控策略详情页单位相关文件，不改后端模型和换算规则。
- `metric_unit` 不允许由普通策略页面覆盖为用户选择值。
- `none`、`short` 不进入公式结果单位 Cascader。
- 新行为先写失败测试，再做最小实现。
- 完成后运行 `pnpm lint && pnpm type-check`。

---

### Task 1: 统一预览与保存的单位 payload

**Files:**
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`

**Interfaces:**
- Produces: `resolveMetricExpressionUnits({ queryType, metricUnit, calculationUnit }): { metricUnit: string; calculationUnit: string }`
- Consumes: 指标元数据 `MetricItem.unit` 与页面当前 `thresholdUnit`。

- [x] **Step 1: 写失败测试**

覆盖普通 bytes→megabytes、公式结果 percent、枚举指标和空计算单位。

- [x] **Step 2: 验证测试因 helper 不存在而失败**

Run: `cd web && pnpm test:monitor-strategy-detail-logic`

Expected: FAIL，提示 `resolveMetricExpressionUnits` 未导出。

- [x] **Step 3: 最小实现 helper 并让预览、保存共同调用**

普通指标保留指标元数据单位；公式和枚举指标返回空源单位；计算单位原样归一为空字符串。

- [x] **Step 4: 运行聚焦测试**

Run: `cd web && pnpm test:monitor-strategy-detail-logic`

Expected: PASS。

### Task 2: 收敛公式单位状态并删除可编辑源单位

**Files:**
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/page.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx`
- Modify: `web/src/app/monitor/locales/zh.json`
- Modify: `web/src/app/monitor/locales/en.json`

**Interfaces:**
- Consumes: Task 1 的 `resolveMetricExpressionUnits`。
- Produces: 单一 `thresholdUnit` 状态；公式编辑器结果单位与阈值计算单位共享该状态。

- [x] **Step 1: 删除单指标“计算指标单位”Cascader和 `metricUnit`/`resultUnit` 冗余状态**

单指标源单位始终从所选指标元数据读取；公式结果单位使用 `thresholdUnit`。

- [x] **Step 2: 公式模式隐藏阈值区域的重复单位选择器**

给 `ThresholdList` 增加 `showUnitSelector`，公式模式传 `false`，阈值输入框仍显示当前结果单位。

- [x] **Step 3: 修复编辑、模式切换和预览传参**

编辑时只回填 `calculation_unit`；公式进入默认 percent，退出后恢复主指标单位；预览始终接收同一个 `thresholdUnit`。

- [x] **Step 4: 运行聚焦测试、ESLint 和 TypeScript 检查**

Run: `cd web && pnpm test:monitor-strategy-detail-logic && pnpm exec eslint 'src/app/monitor/(pages)/event/strategy/detail/page.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricDefinitionForm.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx' 'src/app/monitor/(pages)/event/strategy/detail/alertConditionsForm.tsx' 'src/app/monitor/(pages)/event/strategy/detail/thresholdList.tsx' 'src/app/monitor/(pages)/event/strategy/detail/metricPreview.tsx' 'src/app/monitor/(pages)/event/strategy/detail/formulaExpressionUtils.ts' 'src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts' && pnpm exec tsc -p tsconfig.json --noEmit`

Expected: PASS，无新增错误。

### Task 3: 过滤非法单位并收口验证

**Files:**
- Modify: `web/scripts/monitor-strategy-detail-logic-test.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/strategyDetailUtils.ts`
- Modify: `web/src/app/monitor/(pages)/event/strategy/detail/metricExpressionEditor.tsx`

**Interfaces:**
- Produces: `buildMetricUnitCascaderOptions` 只返回可用于计算和阈值的单位。

- [x] **Step 1: 将 Cascader 测试期望改为排除 `none`、`short` 并验证失败**

Run: `cd web && pnpm test:monitor-strategy-detail-logic`

Expected: FAIL，实际选项仍包含非法单位。

- [x] **Step 2: 在构造 Cascader options 时过滤非法单位**

同时删除未接入生产路径的 `isValidMetricUnit`，公式 Cascader 设置 `allowClear={false}`。

- [x] **Step 3: 运行聚焦测试和 Web 全量门禁**

Run: `cd web && pnpm test:monitor-strategy-detail-logic && pnpm lint && pnpm type-check`

Expected: 全部 exit 0。

Actual: 聚焦测试、改动文件 ESLint、`pnpm type-check`、`NEXTAPI_INSTALL_APP=monitor` 模块 TypeScript 检查均 exit 0。全仓 `pnpm lint` 被 44 个任务外既有错误阻断；全量 `tsconfig.json` 也存在多模块既有依赖和脚本类型错误，本任务文件未出现在错误列表。
