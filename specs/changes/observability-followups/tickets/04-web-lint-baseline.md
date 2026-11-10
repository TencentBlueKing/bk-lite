# 04 — 清掉 web 既有的 3 个 lint 错误

Status: ready

Blocked by: None

**What to build:** 全仓 `pnpm lint` 退出码为 0。

- [ ] 修复 `@typescript-eslint/consistent-type-definitions` 报的 3 处（`type` 改为 `interface`）：
      `web/src/app/monitor/(pages)/integration/list/detail/configure/automaticPolicyApply.ts`、
      `web/src/components/rum-bootstrap.tsx`、`web/src/utils/rumBootstrap.ts`
- [ ] 只改这 3 处，不顺带格式化或改其他文件；行为不变
- [ ] `pnpm lint` 与 `pnpm type-check` 通过
