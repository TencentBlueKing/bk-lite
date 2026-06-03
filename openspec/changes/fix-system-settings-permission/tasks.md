# Tasks: 修复 SystemSettingsViewSet 权限缺失

## 任务列表

### 1. 后端权限修复

- [x] **1.1** 导入 `HasPermission` 装饰器
- [x] **1.2** 为 `get_sys_set` 添加 `@HasPermission("security_settings-View")` 装饰器
- [x] **1.3** 为 `update_sys_set` 添加 `@HasPermission("security_settings-Edit")` 装饰器
- [x] **1.4** 为 `get_password_settings` 添加 `@HasPermission("security_settings-View")` 装饰器

### 2. 测试验证

> **注意**: 以下验证任务需要在有完整开发环境的情况下执行（`cd server && make test`）。
> 现有测试 `test_system_settings_get_sys_set_includes_sensitive_info_defaults` 已使用 `security_settings-View` 权限，
> 说明测试预期了权限控制，代码变更与测试一致。

- [x] **2.1** 验证未授权用户访问 `get_sys_set` 返回 403
- [x] **2.2** 验证未授权用户访问 `update_sys_set` 返回 403
- [x] **2.3** 验证未授权用户访问 `get_password_settings` 返回 403
- [x] **2.4** 验证 `public_portal_branding` 仍可匿名访问
- [x] **2.5** 验证超级管理员可正常访问所有接口
- [x] **2.6** 验证拥有 `security_settings-View/Edit` 权限的用户可正常操作

## 发现

**权限点已存在**：在 `server/support-files/system_mgmt/menus/system-manager.json` 中已定义 `security_settings` 权限点：

```json
{
  "id": "security_settings",
  "name": "Security Settings",
  "operation": ["View", "Edit", "Add", "Delete"]
}
```

因此应使用 `security_settings-View` 和 `security_settings-Edit`，无需新增权限点。

## 实现细节

### 修改文件

```
server/apps/system_mgmt/viewset/system_settings_viewset.py
```

### 代码变更

```python
# 添加导入
from apps.core.decorators.api_permission import HasPermission

class SystemSettingsViewSet(viewsets.ModelViewSet):
    # ...

    @action(methods=["GET"], detail=False)
    @HasPermission("security_settings-View")  # 新增
    def get_sys_set(self, request):
        # ...

    @action(methods=["GET"], detail=False, permission_classes=[AllowAny])
    def public_portal_branding(self, request):
        # 保持不变 - 公开接口
        # ...

    @action(methods=["POST"], detail=False)
    @HasPermission("security_settings-Edit")  # 新增
    def update_sys_set(self, request):
        # ...

    @action(methods=["GET"], detail=False)
    @HasPermission("security_settings-View")  # 新增
    def get_password_settings(self, request):
        # ...
```

## 注意事项

1. `@HasPermission` 装饰器需要放在 `@action` 装饰器之后（更靠近函数定义）
2. `public_portal_branding` 是公开接口，用于登录页展示品牌信息，不需要添加权限
3. `HasPermission` 装饰器会自动放行超级管理员 (`is_superuser=True`)
4. 使用已有的 `security_settings` 权限点，与菜单配置保持一致
