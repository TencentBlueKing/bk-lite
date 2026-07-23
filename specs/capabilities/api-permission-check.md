## MODIFIED Requirements

### Requirement: HasRole 装饰器权限检查

`@HasRole` 装饰器 SHALL 对所有请求（包括 API Token 请求）执行角色检查，不再直接放行 `api_pass=True` 的请求。

#### Scenario: API Token 请求有所需角色

- **WHEN** 用户使用 API Token 发起请求
- **AND** 请求的端点使用 `@HasRole(["role_name"])` 保护
- **AND** 用户的 `roles` 属性包含所需角色
- **THEN** 系统 SHALL 允许请求继续执行

#### Scenario: API Token 请求缺少所需角色

- **WHEN** 用户使用 API Token 发起请求
- **AND** 请求的端点使用 `@HasRole(["role_name"])` 保护
- **AND** 用户的 `roles` 属性不包含所需角色
- **THEN** 系统 SHALL 返回 403 Forbidden
- **AND** 系统 SHALL 记录警告日志，包含所需角色和用户角色

#### Scenario: 超级用户绕过角色检查

- **WHEN** 用户使用 API Token 发起请求
- **AND** 用户的 `is_superuser = True`
- **THEN** 系统 SHALL 允许请求继续执行，无论所需角色是什么

#### Scenario: 无角色要求的端点

- **WHEN** 请求的端点使用 `@HasRole()` 或 `@HasRole(None)` 保护（无角色要求）
- **THEN** 系统 SHALL 允许请求继续执行

### Requirement: HasPermission 装饰器权限检查

`@HasPermission` 装饰器 SHALL 对所有请求（包括 API Token 请求）执行权限检查，不再直接放行 `api_pass=True` 的请求。

#### Scenario: API Token 请求有所需权限

- **WHEN** 用户使用 API Token 发起请求
- **AND** 请求的端点使用 `@HasPermission("permission_name")` 保护
- **AND** 用户的 `permission` 属性包含所需权限
- **THEN** 系统 SHALL 允许请求继续执行

#### Scenario: API Token 请求缺少所需权限

- **WHEN** 用户使用 API Token 发起请求
- **AND** 请求的端点使用 `@HasPermission("permission_name")` 保护
- **AND** 用户的 `permission` 属性不包含所需权限
- **THEN** 系统 SHALL 返回 403 Forbidden
- **AND** 系统 SHALL 记录警告日志，包含 app 名称、所需权限和用户权限

#### Scenario: 超级用户绕过权限检查

- **WHEN** 用户使用 API Token 发起请求
- **AND** 用户的 `is_superuser = True`
- **THEN** 系统 SHALL 允许请求继续执行，无论所需权限是什么

## REMOVED Requirements

### Requirement: API Token 请求直接放行

**Reason**: 此行为导致安全漏洞，任何有效 API Token 可以绕过权限检查执行未授权操作

**Migration**: API Token 关联的用户需要在 system_mgmt 中配置正确的角色和权限。修复后，API Token 请求将使用用户的实际权限进行校验。
