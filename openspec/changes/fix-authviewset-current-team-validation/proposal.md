## Why

`AuthViewSet.filter_by_group()` 从 cookie 获取 `current_team` 后直接用于数据筛选，没有验证当前用户是否有权限访问该 team。攻击者可以伪造 cookie 中的 `current_team` 值，越权访问其他团队的数据。这是一个权限提升漏洞，需要立即修复。

## What Changes

- 在 `filter_by_group()` 方法中添加 `current_team` 权限验证
- 验证逻辑：`current_team` 必须存在于 `user.group_list` 的 id 列表中
- 超管用户（`is_superuser=True`）豁免此验证
- 验证失败时抛出 `PermissionDenied` 异常，返回 403

## Capabilities

### New Capabilities

- `current-team-validation`: 验证 cookie 中的 current_team 是否在用户有权限的团队列表中

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **代码**: `server/apps/core/utils/viewset_utils.py` - `GenericViewSetFun.filter_by_group()` 方法
- **API**: 所有继承 `AuthViewSet` 的 ViewSet 的 list 接口
- **行为变更**: 如果 `current_team` cookie 值不在用户的 `group_list` 中，将返回 403 而非之前的（可能越权的）数据
- **依赖**: 需要导入 `rest_framework.exceptions.PermissionDenied`
