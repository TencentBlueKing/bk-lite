## Context

`AuthViewSet` 是 bk-lite 后端的核心权限控制基类，位于 `server/apps/core/utils/viewset_utils.py`。它通过 `ORGANIZATION_FIELD`（默认 `team`，可覆盖为 `groups`）字段实现组织级数据隔离。

当前问题：
- `AuthViewSet` 没有覆写 `create` 方法，创建时直接信任客户端提交的组织字段
- `AuthViewSet.update` 方法只校验 `current_team` 是否在旧对象的组织字段中，不校验新提交的组织是否在用户可管理范围内
- 读取时用组织字段做边界过滤，但写入时不校验，导致权限边界失效

## Goals / Non-Goals

**Goals:**
- 在 `AuthViewSet.create` 中校验提交的组织字段是否在用户可管理范围内
- 在 `AuthViewSet.update` 中校验新增的组织是否在用户可管理范围内
- 超级管理员跳过校验
- 复用现有的 `_normalize_org_values` 方法解析组织字段

**Non-Goals:**
- 不修改 `DirectoryModelViewSet` 等直接使用 ORM 的特殊实现
- 不修改读取逻辑
- 不修改删除逻辑

## Decisions

### 1. 校验方法设计

新增 `_validate_org_field_permission(request, org_values)` 方法：
- 获取 `user.group_list` 作为用户可管理的组织集合
- 检查 `org_values` 是否为该集合的子集
- 超级管理员跳过校验
- 校验失败抛出 `PermissionDenied`

**理由**: 与现有的 `_validate_current_team_permission` 方法风格一致，职责单一。

### 2. create 方法实现

新增 `create` 方法：
1. 从 `request.data` 中提取组织字段
2. 调用 `_normalize_org_values` 解析为 int 列表
3. 调用 `_validate_org_field_permission` 校验
4. 调用 `super().create()` 继续原有流程

**理由**: 最小侵入，复用现有方法。

### 3. update 方法修改

在现有 `update` 方法的组织字段处理逻辑中（约 line 460-463），添加对新增组织的校验：
1. 计算 `new_groups = set(org_values) - set(instance_org_value)`
2. 如果有新增组织，调用 `_validate_org_field_permission` 校验

**理由**: 只校验新增的组织，允许用户移除自己有权的组织（现有逻辑已处理）。

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 现有 API 调用方可能依赖无校验行为 | 这是安全修复，应当强制执行。返回 403 错误信息明确 |
| 性能影响（每次写入多一次校验） | `user.group_list` 已在请求上下文中，无额外查询 |
| 子类覆写 create/update 可能绕过校验 | 文档说明，子类应调用 `super()` 或自行校验 |
