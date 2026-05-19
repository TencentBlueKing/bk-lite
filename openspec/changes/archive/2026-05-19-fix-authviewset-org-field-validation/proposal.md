## Why

`operation_analysis` 模块的写接口（创建/更新）直接信任客户端提交的 `groups`/`team` 组织字段，没有校验目标组织是否在当前用户的可管理范围内。这导致用户可以将对象发布到自己无权管理的组织，造成跨组织数据泄露和配置漂移。

关联 Issue: https://github.com/TencentBlueKing/bk-lite/issues/3028

## What Changes

- 在 `AuthViewSet` 中添加 `_validate_org_field_permission` 方法，校验组织字段是否在用户可管理范围内
- 在 `AuthViewSet` 中新增 `create` 方法，创建时校验提交的组织字段
- 修改 `AuthViewSet.update` 方法，更新时校验新增的组织字段
- 超级管理员跳过校验

## Capabilities

### New Capabilities

- `org-field-validation`: AuthViewSet 组织字段写入权限校验能力

### Modified Capabilities

<!-- 无需修改现有 spec -->

## Impact

- **代码**: `server/apps/core/utils/viewset_utils.py` 的 `AuthViewSet` 类
- **API**: 所有继承 `AuthViewSet` 的 ViewSet 的 create/update 接口将增加组织字段校验
- **行为变更**: 用户尝试写入无权管理的组织时，将收到 403 PermissionDenied 错误
