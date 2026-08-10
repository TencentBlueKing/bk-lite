## ADDED Requirements

### Requirement: API Token 认证时填充用户权限信息

当用户通过 API Token 认证时，系统 SHALL 自动填充用户的完整权限信息，包括：
- `roles`: 用户角色列表（格式：`{app}--{role_name}` 或 `{role_name}`）
- `permission`: 菜单权限字典（格式：`{app: set(menu_names)}`）
- `is_superuser`: 超级用户标识
- `role_ids`: 角色 ID 列表

权限信息的计算逻辑 SHALL 与 Web Token 认证（`AuthBackend`）保持一致。

#### Scenario: API Token 认证成功时填充权限

- **WHEN** 用户使用有效的 API Token 发起请求
- **AND** API Token 关联的用户在系统中存在
- **THEN** 系统 SHALL 查询用户的所有角色（个人角色 + 组角色 + 继承角色）
- **AND** 系统 SHALL 根据角色计算用户的菜单权限
- **AND** 系统 SHALL 将权限信息设置到 `request.user` 对象

#### Scenario: 用户是超级管理员

- **WHEN** 用户通过 API Token 认证
- **AND** 用户的角色包含 `admin` 或 `system-manager--admin`
- **THEN** 系统 SHALL 设置 `user.is_superuser = True`

#### Scenario: 用户不是超级管理员

- **WHEN** 用户通过 API Token 认证
- **AND** 用户的角色不包含 `admin` 或 `system-manager--admin`
- **THEN** 系统 SHALL 设置 `user.is_superuser = False`
- **AND** 系统 SHALL 根据用户角色计算具体的菜单权限

### Requirement: 权限信息缓存

系统 SHALL 缓存 API Token 用户的权限信息以提高性能。

#### Scenario: 缓存命中

- **WHEN** 用户使用 API Token 发起请求
- **AND** 缓存中存在该用户的权限信息
- **AND** 缓存未过期
- **AND** 缓存代际与数据库中的用户权限代际一致
- **THEN** 系统 SHALL 直接使用缓存的权限信息
- **AND** 系统 SHALL 只允许查询轻量的权限代际，不再查询角色、菜单或组织权限数据

#### Scenario: 缓存未命中

- **WHEN** 用户使用 API Token 发起请求
- **AND** 缓存中不存在该用户的权限信息或已过期
- **THEN** 系统 SHALL 查询数据库计算权限信息
- **AND** 系统 SHALL 将计算结果按可配置 TTL 缓存（默认 600 秒）

#### Scenario: 缓存 Key 格式

- **WHEN** 系统缓存 API Token 用户的权限信息
- **THEN** 缓存 Key SHALL 为 `api_token_permissions:{username}:{domain}:v{permission_version}:{team}`

#### Scenario: 权限变更与并发鉴权

- **WHEN** 用户角色、组织继承、角色菜单或应用权限发生变更
- **THEN** 系统 SHALL 在同一数据库事务中单调推进独立的用户权限代际
- **AND** 变更前开始的鉴权 SHALL NOT 将旧权限写入新代际缓存
- **AND** 旧代际缓存即使位于其他 Worker 或物理删除失败，也 SHALL NOT 被后续鉴权复用

#### Scenario: 用户删除与重建

- **WHEN** 系统用户被删除
- **THEN** 权限代际 SHALL 独立于用户记录继续保留并推进
- **AND** 仅保留基础用户或 API Secret 时 SHALL NOT 通过 API Token 认证
- **AND** 同名同域用户重建后 SHALL 使用更高的新代际

#### Scenario: Web Token 授权上下文

- **WHEN** Web Token 鉴权读取或写入 `token_info` 授权上下文缓存
- **THEN** 缓存键 SHALL 包含同一个用户权限代际
- **AND** 计算期间代际变化时 SHALL 最多重试一次并拒绝返回旧授权上下文

#### Scenario: 数据权限规则

- **WHEN** 系统读取或写入 `perm_rules` 数据权限缓存
- **THEN** 缓存键 SHALL 包含同一个用户权限代际
- **AND** 计算期间代际变化时 SHALL 最多重试一次，持续变化时返回空权限

#### Scenario: 首次上线版本化缓存

- **WHEN** 从不识别权限代际的旧版本升级到版本化权限缓存
- **THEN** 发布流程 SHALL 按 `docs/operations/api-token-permission-cache-rollout.md` 排空全部旧 Worker
- **AND** SHALL NOT 让旧 Worker 与新 Worker 在权限变更窗口内混合提供 API Token 鉴权
- **AND** 回滚到旧版本前 SHALL 同样排空新 Worker，并执行
  `python manage.py prepare_permission_cache_rollback --confirm` 仅清理权限缓存命名空间中的旧缓存键

### Requirement: 角色继承计算

系统 SHALL 正确计算用户的所有角色，包括通过组织继承获得的角色。

#### Scenario: 用户直接授权的角色

- **WHEN** 用户有直接授权的角色（`user.role_list`）
- **THEN** 这些角色 SHALL 包含在用户的角色列表中

#### Scenario: 用户通过组织获得的角色

- **WHEN** 用户属于某个组织（`user.group_list`）
- **AND** 该组织配置了角色
- **THEN** 组织的角色 SHALL 包含在用户的角色列表中

#### Scenario: 角色继承链

- **WHEN** 用户属于某个组织
- **AND** 该组织的父组织设置了 `allow_inherit_roles = True`
- **THEN** 父组织的角色 SHALL 也包含在用户的角色列表中
- **AND** 系统 SHALL 递归向上追溯直到某层 `allow_inherit_roles = False` 或到达根节点
