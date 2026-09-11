# 控制台 iframe 屏显高度收口（S1）

Status: implemented

本阶段交付：**屏显壳层高度链对齐**。不改透传、不藏对象树、不改分享锁、不扩 login backup、不扫业务页 `calc(100vh - Npx)`。

一期 `console-iframe-screen-mode` 把高度对齐标为延期，并禁止 `lockConsoleViewport || screenMode ? 'h-screen'` 单行开关。本阶段按对照分享的定向链收口，而不是盲目满高实验。

## Completion Evidence

- 2026-09-11 本地：`cd web && ./node_modules/.bin/vitest run src/console-layout/__tests__/appTopOverflow.test.ts src/console-layout/__tests__/screenMode.test.ts src/console-layout/__tests__/resolve.test.ts src/console-layout/__tests__/useScreenAwareRouter.test.tsx src/app/ops-analysis/\(pages\)/view/__tests__/screenMode.view.test.ts src/app/ops-analysis/\(pages\)/settings/__tests__/screenMode.layout.test.ts src/components/sub-layout/__tests__/screenMode.layout.test.tsx src/app/cmdb/\(pages\)/assetData/components/sub-layout/__tests__/screenMode.layout.test.tsx src/app/system-manager/\(pages\)/application/manage/__tests__/screenMode.layout.test.tsx` → **9 files, 49 passed**
- 同次：`pnpm exec tsx scripts/apm-menu-route-test.ts` → `APM menu route checks passed`；`pnpm exec tsx scripts/ops-analysis-dashboard-share-test.ts` → `ops-analysis dashboard share contracts passed`
- 用法说明：`docs/operations/console-iframe-screen-mode.md`

## 本阶段合同

1. `screen=true|1` 下所有路由有确定视口高度：外层 `h-screen`，main `min-h-0` + `h-full` + `flex-col p-0`，workspace 为 `flex h-full min-h-0` 的默认滚动口。
2. 不要整页 `overflow-hidden`，不要把 `screenMode` 并进 `lockConsoleViewport`。外层允许 `overflow-x-hidden`。
3. 屏显 main 设 `--custom-height: 100%`（对齐 app-top），修 settings 假 90px；禁止 `--custom-height: 100vh`。
4. Watermark 保持现有包装；禁止 `display: contents`。OA view / 大屏 / X6 / Isoflow 不叠业务满高壳。
5. 页头与画布工具条屏显保留。无参日常壳层、分享/沉浸锁视口不回归。

## 布局与滚动

- 高度链：外层 → main → `data-console-screen-workspace` → 业务根 `h-full`。
- 滚动只放在 workspace（列表）或画布/表自己的内部容器。外层/main 不再加 `overflow-auto`。
- iframe 内 `h-screen` 等于 iframe 视口。宿主把 iframe 裁矮时，锁的是矮视口。
- 业务页自写的 `calc(100vh - Npx)` 仍按日常壳估算，属已知残留，本阶段不扫。

## Testing Decisions

- 锁根 layout 三层 class 与分享/日常对照；继续禁止合并 `lockConsoleViewport || screenMode`。
- 不测、不改大屏/拓扑/架构组件内部渲染逻辑。
- 手工验收：屏显大屏铺满、网络拓扑/架构可见、仪表盘与分享不回归、settings 或会长列表可滚完全部。
