# 03 — 组织共享与全局

Status: done

Blocked by: 02 — 场景视图工作台

**What to build:** 三层可见范围生效。有组织共享权限的人可把场景发给当前组织，组织内只读打开；管理员可发全局场景，出现在「全局」分组且不自动进入「我的」。非创建者不能改原件，只能另存为个人场景。打开后数据仍按打开者实例权限计算。

- [x] 发布组织共享需要 `asset_views_scene-Org Share`；无权限创建/改可见范围返回 403；仍可打开已共享场景并另存
- [x] 创建/改/删全局场景仅超管或 CMDB admin；全局出现在「全局」组，不写入他人「我的」
- [x] 组织共享绑定创建时的当前组织；仅该组织范围内用户能在列表中看到定义
- [x] 非创建者对组织/全局场景：可执行、可另存，更新/删除原件 403
- [x] 另存始终生成可见范围为个人、创建者为当前用户的新场景
- [x] 导航列表同时有三类数据时，分组顺序为我的 → 组织 → 全局；空组仍不出现
- [x] API 测试覆盖两组织隔离、无分享权限 403、另存归属；菜单声明含 Org Share 且 normal 角色默认无此动作

## Notes

- 分享的是查询定义，不是数据。
- 不要做指定人、指定角色或可写协作。

## Completion evidence

- `test_visible_query_isolates_org_and_keeps_global`、`test_org_share_without_permission_is_403`、`test_org_create_binds_current_team`、`test_save_as_always_creates_personal_copy`、`test_menu_declares_org_share_and_normal_role_lacks_it`
- 菜单声明：`server/support-files/system_mgmt/menus/cmdb.json` 增加 `asset_views_scene` / `Org Share`；normal 角色 menus 不含该动作
- 前端：有 `can_org_share` / `can_global` 才显示对应可见范围；非 `can_edit` 只读 + 另存
