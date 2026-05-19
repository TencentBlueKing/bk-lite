## 1. APISecretAuthBackend 权限填充

- [x] 1.1 在 `apps/core/backends.py` 中添加 `_get_user_all_roles` 方法，复用 `system_mgmt/nats_api.py` 中的角色计算逻辑
- [x] 1.2 在 `apps/core/backends.py` 中添加 `_populate_user_permissions` 方法，计算并设置用户的 roles、permission、is_superuser、role_ids
- [x] 1.3 在 `APISecretAuthBackend.authenticate` 方法中调用 `_populate_user_permissions`
- [x] 1.4 添加权限信息缓存逻辑，使用 Django cache，TTL 60 秒，key 格式为 `api_token_permissions:{username}:{domain}:{team}`

## 2. 权限装饰器修改

- [x] 2.1 修改 `apps/core/decorators/api_permission.py` 中的 `HasRole.__call__` 方法，移除 `api_pass` 直接放行逻辑
- [x] 2.2 修改 `apps/core/decorators/api_permission.py` 中的 `HasPermission.__call__` 方法，移除 `api_pass` 直接放行逻辑

## 3. 单元测试

- [x] 3.1 为 `APISecretAuthBackend._get_user_all_roles` 添加单元测试，覆盖直接角色、组织角色、继承角色场景
- [x] 3.2 为 `APISecretAuthBackend._populate_user_permissions` 添加单元测试，覆盖普通用户和超级用户场景
- [x] 3.3 为 `HasRole` 装饰器添加 API Token 请求的单元测试，覆盖有权限、无权限、超级用户场景
- [x] 3.4 为 `HasPermission` 装饰器添加 API Token 请求的单元测试，覆盖有权限、无权限、超级用户场景
- [x] 3.5 添加缓存命中和缓存未命中的单元测试

## 4. 集成测试

- [x] 4.1 在 `apps/operation_analysis/tests/` 中添加 API Token 权限校验的集成测试
- [x] 4.2 测试 API Token 用户有权限时可以正常访问 operation_analysis 接口
- [x] 4.3 测试 API Token 用户无权限时访问 operation_analysis 接口返回 403

## 5. 文档和清理

- [ ] 5.1 更新 API Token 相关文档，说明权限要求
- [x] 5.2 运行完整测试套件，确保没有回归
- [x] 5.3 运行 linter 和 type check，确保代码质量
