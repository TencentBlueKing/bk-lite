# 03 — RUM 告警详情趋势区分无样本与 0

Status: done

Blocked by: None

**What to build:** RUM 告警详情的指标趋势在无样本处断开，悬停显示「—」；真实的 0 仍画成 0。

- [x] `web/src/app/rum/api/index.ts` 中告警趋势点的 `value` 类型允许 `null`，解析时保留 `null`
- [x] `web/src/app/rum/alert-events/page.tsx` 的趋势图不再把空值转成 0：折线在空值处断开，悬停显示「—」；全为空时显示现有空态文案
- [x] 只改读取与显示，不动布局；颜色用语义 token
- [x] 测试：vitest 覆盖空值断开、悬停「—」、真实 0；改动文件 eslint 与 `pnpm type-check` 通过

## Completion evidence

- `cd web && pnpm exec vitest run src/app/rum/alert-events/alert-metric-trend.test.tsx src/app/rum/__tests__/api-queries.test.ts`：8 passed。空值把面积折线拆成两段；悬停空桶为「—」；真实 0 仍画出并显示 `0ms`；全为 `null` 时显示 `该时间窗内暂无样本`。解析保留 `null` 和 `0`，`undefined`、缺字段、非数字和 `NaN` 不变成 0。
- `cd web && pnpm test:rum`：25 files，118 passed。
- `cd web && pnpm lint`：退出码 0，0 errors（既有 warnings）。
- `cd web && pnpm type-check`：退出码 0。
