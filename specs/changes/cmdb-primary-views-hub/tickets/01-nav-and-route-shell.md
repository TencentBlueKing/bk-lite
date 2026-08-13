# 01 — 导航与路由壳

Status: done

Blocked by: None

**What to build:** 一级「视图」展开为资产总览 + 五个专题子项；点父项进资产总览；访问 `/cmdb/views/<viewType>` 打开独立工作台空壳（无详情侧栏）；权限挂现有 `asset_info`。

- [x] zh/en 菜单子项文案与 URL 符合规格（资产总览 + 应用拓扑 / K8S 视图 / 网络拓扑 / IP 视图 / 机房机柜）
- [x] 父级「视图」落地 `/cmdb/assetOverview`；五个专题路由可打开且不包详情左侧菜单
- [x] 子项权限继承 `asset_info`（`withParentPermission` 或同等挂载），无新权限点
- [x] 菜单结构有脚本断言（zh/en 均覆盖）

## Completion evidence

- `web/src/app/cmdb/constants/menu.json` 视图父项 children ×6；`pnpm test:cmdb-views-hub-menu` PASS
- `web/src/app/cmdb/(pages)/views/[viewType]/page.tsx` 空壳；不在 detail layout 下
- Task 1 纯函数核已就绪（`test:cmdb-views-hub-core` PASS）

## Notes

- `viewType`：`application` | `k8s` | `network` | `ip` | `rack-room`
- 本票只需空壳 + 标题占位；实例选择与画布嵌入在后续票
