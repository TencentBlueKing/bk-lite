# 03 — RUM 告警详情趋势区分无样本与 0

Status: ready

Blocked by: None

**What to build:** RUM 告警详情的指标趋势在无样本处断开，悬停显示「—」；真实的 0 仍画成 0。

- [ ] `web/src/app/rum/api/index.ts` 中告警趋势点的 `value` 类型允许 `null`，解析时保留 `null`
- [ ] `web/src/app/rum/alert-events/page.tsx` 的趋势图不再把空值转成 0：折线在空值处断开，悬停显示「—」；全为空时显示现有空态文案
- [ ] 只改读取与显示，不动布局；颜色用语义 token
- [ ] 测试：vitest 覆盖空值断开、悬停「—」、真实 0；改动文件 eslint 与 `pnpm type-check` 通过
