# APM 菜单信息架构目录化

Status: implemented

## Completion Evidence

- `getDeepestMatchedMenuItems` 恢复叶子回退父级 children；单测覆盖 Job / CMDB / APM 目录树。
- 正式路由：`/apm/home`、`/apm/services/{topology,slo}`、`/apm/explore/{traces,endpoints,errors}`、`/apm/events/{alerts,policies}`。
- 菜单源已同步：`web/src/app/apm/constants/menu.json`、`web/public/menus/{zh,en}.json`、`server/support-files/system_mgmt/menus/apm.json` 应用入口。
- 旧路径保留 redirect（含 query）：`/apm`、`/apm/topology|slo|traces*|endpoints|errors|events|policies`。
- 工作流脚本与 package.json vitest 路径已对齐。

## Problem Statement

APM 首页挂在短路径 `/apm`，且服务/探索/事件的二级路由大量平铺在 `/apm/*` 旁路，与集成的目录化风格不一致。前缀匹配会误吃子路由；为修 APM 而改全站共用匹配时又丢掉叶子回退，误伤其他 app。

## Solution

1. 统一 APM 菜单约定：首页 `/apm/home`；一级 = 目录前缀；二级挂在前缀下。
2. 旧路径 redirect 兼容一个发布窗口。
3. 全站 `getDeepestMatchedMenuItems` 恢复叶子回退父级 children；匹配不再依赖 APM 特例。

## Target Routes

| 一级 | 正式入口 | 二级 |
|---|---|---|
| 首页 | `/apm/home` | 无 |
| 服务 | `/apm/services` | `/apm/services`、`/apm/services/topology`、`/apm/services/slo` |
| 探索 | `/apm/explore/traces` | `/apm/explore/traces`、`/apm/explore/endpoints`、`/apm/explore/errors` |
| 事件 | `/apm/events/alerts` | `/apm/events/alerts`、`/apm/events/policies` |
| 集成 | `/apm/integration/add` | 保持现有 integration 子路径 |

## Phases

- [x] P0 匹配叶子回退 + 多 app 单测
- [x] P1 `/apm/home`
- [x] P2 服务目录化
- [x] P4 事件目录化
- [x] P3 探索目录化
- [x] P5 收口与回归
