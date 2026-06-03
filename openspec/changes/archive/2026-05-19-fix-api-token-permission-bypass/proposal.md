## Why

API Token 认证请求会绕过模块角色校验（`@HasRole`、`@HasPermission` 装饰器），导致任何持有有效 API Token 的用户可以对 `operation_analysis` 等模块执行未授权的增删改操作。这是一个安全漏洞（GitHub Issue #3027），需要立即修复。

## What Changes

- **修改** `APISecretAuthBackend`：在 API Token 认证时填充用户的完整权限信息（`roles`、`permission`、`is_superuser`），与 Web Token 认证行为一致
- **修改** `HasRole` 装饰器：移除 `api_pass` 直接放行逻辑，让 API Token 请求也经过角色检查
- **修改** `HasPermission` 装饰器：移除 `api_pass` 直接放行逻辑，让 API Token 请求也经过权限检查
- 新增权限信息缓存机制，避免每次 API Token 请求都查询数据库

## Capabilities

### New Capabilities

- `api-token-permission-population`: API Token 认证时自动填充用户权限信息的能力，包括角色列表、菜单权限、超级用户标识

### Modified Capabilities

- `api-permission-check`: 修改权限检查逻辑，移除 API Token 请求的直接放行，统一使用基于用户权限的校验

## Impact

### 代码影响

| 文件 | 修改内容 |
|------|----------|
| `apps/core/backends.py` | `APISecretAuthBackend` 增加 `_populate_user_permissions` 方法 |
| `apps/core/decorators/api_permission.py` | `HasRole`、`HasPermission` 移除 `api_pass` 直接放行 |

### API 影响

- 所有使用 `@HasRole` 或 `@HasPermission` 保护的 API 端点，API Token 请求将受到权限校验
- 如果 API Token 关联的用户没有相应权限，请求将返回 403 Forbidden

### 兼容性影响

- **潜在 Breaking Change**：现有使用 API Token 的集成，如果用户没有正确配置权限，将无法访问之前可以访问的接口
- 需要确保 API Token 关联的用户在 `system_mgmt` 中配置了正确的角色和权限

### 依赖

- 复用 `apps/system_mgmt/nats_api.py` 中的 `get_user_all_roles` 逻辑
- 依赖 `apps/system_mgmt/models` 中的 `Group`、`Role`、`Menu` 模型
