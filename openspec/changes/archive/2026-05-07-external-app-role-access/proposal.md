## Why

外部应用（External App）添加后，所有普通用户在 ops-console 和应用切换列表中均看不到该应用——因为当前系统仅为内置应用自动创建角色，且角色分配 UI 硬过滤了非内置应用。管理员无法为组织或用户授予外部应用的访问权限，导致外部应用无法投入实际使用。

## What Changes

- **新增**：创建外部应用时，自动同步创建对应的 `user` 角色（`Role(name='user', app=<app_name>)`），并与应用创建操作保持事务一致性
- **新增**：删除外部应用时，自动级联删除对应的 `user` 角色
- **修改**：`get_role_tree` API 去除 `is_build_in` 硬过滤，返回所有应用（内置 + 外部）的角色供分配 UI 使用
- 授权后，普通用户可在 ops-console 首页卡片和顶部应用切换器中看到该外部应用

## Capabilities

### New Capabilities

- `external-app-role`: 外部应用的角色生命周期管理——创建时自动建立 user 角色，删除时级联清理，角色分配 UI 可见外部应用角色

### Modified Capabilities

<!-- 无现有 spec 需要变更 -->

## Impact

- **后端**：
  - `server/apps/system_mgmt/serializers/app_serializer.py` — `create()` 方法新增 Role 创建逻辑
  - `server/apps/system_mgmt/viewset/app_viewset.py` — `destroy()` 方法新增级联删除 Role 逻辑
  - `server/apps/system_mgmt/viewset/role_viewset.py` — `get_role_tree()` 去除 `is_build_in` 过滤
- **前端**：无需改动（`clientData` 权限过滤和角色树展示逻辑已具备，后端修复后自动生效）
- **数据库**：无 migration（Role 表结构不变，仅数据层面新增记录）
- **已有数据**：历史外部应用不受影响（无 Role 记录），管理员可手动补充授权或通过管理命令修复
