# 04 — 应用拓扑工作台

Status: done

Blocked by: 02 — 实例选择器、记忆与空态

**What to build:** 一级「应用拓扑」复用现有应用资源总览；焦点切换与「查看详情 → 基础信息」行为与规格一致。

- [x] `system` / `application`（app_overview 主题）实例可打开应用拓扑
- [x] 支持设为当前焦点（合法时）与显式查看详情进基础信息
- [x] 与详情入口共用同一组件能力面

## Completion evidence

- `ViewCanvasHost` `viewType === 'application'` 渲染 `ApplicationResourceOverview`（与详情 `relationships/page.tsx` 同组件）
- 资格：`isViewEligible('application', …)` / `eligibleModelIdsForView` 对齐 app_overview；`test:cmdb-views-hub-core` PASS
- Shell「查看详情」走 `buildBaseInfoPath`；详情侧接线 `test:cmdb-app-overview-wiring` PASS
- Hub 接线：`test:cmdb-views-hub-wiring` PASS（ApplicationResourceOverview import）
