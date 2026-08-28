# 02 — 场景视图工作台

Status: done

Blocked by: 01 — 跨模型标签活查询 + 个人场景存取

**What to build:** 用户从 CMDB「视图 → 场景视图」进入独立工作台：同一导航列表按「我的 / 组织 / 全局」分组（空组不出现）；能按先模型后标签创建个人场景并打开；看到总数、按模型数量、有命中的分表；列复用该模型展示列；只读；点击进现有资产详情；全 0 显示没有匹配的实例。

- [x] 「视图」下新增「场景视图」，父级仍落地资产总览；zh/en 菜单与 URL 有脚本断言
- [x] 路由为 `/cmdb/views/scene`，不复用专题视图的实例选择器壳
- [x] 创建抽屉：先选模型范围，再选标签，AND/OR 默认 AND，可见范围本票只提供「仅自己」
- [x] 打开后渲染总数 + 按模型数量；点模型数量滚到对应分表
- [x] 只渲染有命中的模型表；列跟打开者在该模型上的展示列（无则模型默认列）
- [x] 行点击进入该实例现有基础信息页；表上无编辑/删除/批量
- [x] 组织/全局分组在没有数据时不出现；有个人场景时「我的」可见

## Notes

- 权限继承 `asset_info`，本票不挂组织共享动作。
- 列表分组是纯展示：接口仍返回扁平列表，前端按可见范围分组。
- 有组织共享/全局权限时，创建抽屉会多出对应可见范围（03）；无权限时仍只有「仅自己」。

## Completion evidence

- `web/src/app/cmdb/(pages)/views/scene/page.tsx` 独立工作台；不引用 `ViewsWorkspaceShell` / `ViewInstancePicker`
- 菜单：zh/en 在资产总览后插入 `asset_views_scene` → `/cmdb/views/scene`，`withParentPermission: true`
- 脚本：`pnpm exec tsx scripts/cmdb-views-hub-menu-test.ts` 与 `pnpm exec tsx scripts/cmdb-scene-view-groups-test.ts` 均 PASS
