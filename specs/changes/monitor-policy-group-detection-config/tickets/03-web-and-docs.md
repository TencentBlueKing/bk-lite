# 03 — 策略组页面与文档

Status: ready

Blocked by: 01 — 组级检测频率与无数据告警（后端）；02 — 规则级字段（后端）

**What to build:** 策略组列表新增「检测配置」抽屉（检测频率 + 无数据告警），「修改规则」抽屉增加告警名称、连续触发周期、连续恢复周期和恢复阈值，规则列表标出承载无数据的规则，列表徽标补频率/无数据不一致。更新产品决策记忆与原策略组 spec 的 Out of Scope。

- [x] API 客户端新增 `updatePolicyGroupDetection`，`updatePolicyGroupRule` payload 扩展可选字段
- [x] 「检测配置」抽屉：检测频率数值 + 单位（复用 `SCHEDULE_UNIT_MAP` 上限），无数据开关；开启后出现告警名称、检测窗、级别、恢复窗；不一致时顶部提示「保存后会写成同一套」；一行说明无数据按插件写到一条承载规则
- [x] 「修改规则」抽屉：阈值下方增加告警名称、连续触发周期、连续恢复周期；非多条件规则再加恢复阈值；只改告警名称时确认框不提示结束告警
- [x] 规则列表承载规则显示「承载无数据」标记
- [x] 名称列徽标补「频率不一致」「无数据不一致」
- [x] payload 组装、徽标判断、一致性文案放进独立纯函数模块，并补测试（同 `policyGroupNotice.test.ts` 的方式）
- [x] 布局用 Tailwind className，不新建 SCSS，不硬编码颜色，复用 Ant Design 控件与页内已有组件
- [x] 更新 `docs/design/product-decisions/monitor-policy-group.md`：替换「组内只修改规则阈值」「无数据等条件保持模板值」「在组里修改无数据等条件」后置三条，记录承载规则决策与日期
- [x] 更新 `specs/changes/monitor-policy-group/spec.md` Out of Scope 中对应一条，指向本 spec
- [ ] `cd web && pnpm lint`、相关 `pnpm test`、`pnpm type-check` 通过

## Notes

- 页面文案沿用本页现有中文直写方式。
- 单策略页（`strategy/detail/**`）工作区已有未提交改动属于另一任务，不要触碰、不要回退。

## Completion evidence

- 相关测试 16 passed，0 failed：`cd web && pnpm exec vitest run 'src/app/monitor/(pages)/event/policy-group/__tests__/policyGroupDetection.test.ts' 'src/app/monitor/(pages)/event/policy-group/__tests__/policyGroupNotice.test.ts'`（policyGroupDetection 10，policyGroupNotice 6）。
- 本次改动文件 eslint 通过（exit 0）：`page.tsx`、`policyGroupDetection.ts`、`policyGroupDetection.test.ts`、`integration.ts`。
- `cd web && pnpm type-check` exit 0。仅有 Node 引擎警告：期望 24.x，当前 v22.16.0。
- `cd web && pnpm lint` exit 1：`✖ 141 problems (42 errors, 99 warnings)`。输出里没有 `policy-group`、`policyGroupDetection`、`integration.ts`。错误在既有或其它任务的文件，例如 `web/src/app/apm/events/policies/notification-target-fields.tsx` 的 indent、`web/src/app/monitor/(pages)/event/strategy/detail/multiThresholdGrid.tsx` 的 indent、`automaticPolicyApply.ts`、`web/src/components/rum-bootstrap.tsx` 与 `web/src/utils/rumBootstrap.ts` 的 `consistent-type-definitions`。未改这些文件。
- 浏览器走查（localhost:3000 策略组页，未点确认保存）：检测配置抽屉有承载说明、频率单位、无数据开关；名称为空时确认禁用，填上名称后确认可用，随后取消。规则列表里 CPU 规则显示「承载无数据」。修改规则抽屉有告警名称、连续触发周期、连续恢复周期、恢复阈值。只改名称时确认框为「修改告警名称 / 保存后新告警使用新名称。正在响的告警不结束。」随后取消。打开规则抽屉时控制台有既有组件 `thresholdList.tsx` 的 antd `InputNumber` `addonAfter` 弃用警告，页面仍可操作。
