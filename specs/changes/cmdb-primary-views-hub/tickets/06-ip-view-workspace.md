# 06 — IP 视图工作台

Status: done

Blocked by: 02 — 实例选择器、记忆与空态

**What to build:** 一级「IP 视图」复用现有 IPAM 矩阵能力；资格与详情一致（subnet / ipam 主题）。

- [x] 合法 subnet 实例可打开 IP 视图
- [x] 与详情 IP 视图同能力面
- [x] 「查看详情」进入该实例基础信息

## Completion evidence

- `ViewCanvasHost` `viewType === 'ip'` 渲染 `IpamMatrix instId={focus.inst_id}`（与详情同组件）
- 资格：`isViewEligible('ip', 'subnet', ['ipam'])`；`test:cmdb-views-hub-core` PASS
- 详情侧 IP Segmented / 渲染：`test:cmdb-app-overview-wiring` PASS；hub wiring PASS
