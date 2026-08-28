# 04 — 场景导出

Status: done

Blocked by: 02 — 场景视图工作台

**What to build:** 打开场景后可以一次导出一个 Excel：当前用户权限下的全部命中；有命中的模型各占一个 Sheet；列跟该模型展示列走；0 条的模型不出 Sheet。

- [x] 工作台上有导出入口；无命中时不可导出或导出后说明没有匹配的实例
- [x] 一个文件内按模型分 Sheet，Sheet 列与该模型展示列一致
- [x] 导出范围为权限内全部命中，不是当前分页
- [x] 导出仍要求 `asset_info-View`，且只能导出当前用户可见的场景
- [x] 测试断言：两模型有命中则两个 Sheet、第三模型 0 条则无对应 Sheet；无权场景 403

## Notes

- 复用现有按模型实例导出，不要另写一套 Excel 列映射。
- 可与 03 并行。

## Completion evidence

- `test_collect_all_omits_zero_and_pages_through`、`test_merge_model_workbooks_keeps_hit_sheets_only`、`test_export_builds_one_sheet_per_hit_model`、`test_export_empty_is_400`、`test_export_unknown_scene_is_404`
- 工作台导出按钮：`result.total` 为 0 时禁用；`POST /cmdb/api/scene_views/{id}/export/`
- 无权/不可见场景走 queryset 过滤后 `get_object` 404（与 retrieve 一致），测试锁定 404
