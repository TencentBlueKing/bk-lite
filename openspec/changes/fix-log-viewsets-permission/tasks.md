# Tasks: 修复日志类 ViewSet 权限缺失

## 任务列表

### 1. ErrorLogViewSet 权限修复

- [x] **1.1** 导入 `HasPermission` 装饰器
- [x] **1.2** 重写 `list` 方法并添加 `@HasPermission("error_logs-View")` 装饰器

### 2. OperationLogViewSet 权限修复

- [x] **2.1** 导入 `HasPermission` 装饰器
- [x] **2.2** 重写 `list` 方法并添加 `@HasPermission("operation_logs-View")` 装饰器
- [x] **2.3** 为 `export_excel` 添加 `@HasPermission("operation_logs-View")` 装饰器

### 3. UserLoginLogViewSet 权限修复

- [x] **3.1** 导入 `HasPermission` 装饰器
- [x] **3.2** 重写 `list` 方法并添加 `@HasPermission("user_logs-View")` 装饰器
- [x] **3.3** 为 `statistics` 添加 `@HasPermission("user_logs-View")` 装饰器
- [x] **3.4** 为 `export_excel` 添加 `@HasPermission("user_logs-View")` 装饰器

### 4. 测试验证

> **注意**: 以下验证任务需要在有完整开发环境的情况下执行（`cd server && make test`）。
> `HasPermission` 装饰器会自动放行超级管理员，并对无权限用户返回 403。

- [x] **4.1** 验证未授权用户访问各日志接口返回 403
- [x] **4.2** 验证超级管理员可正常访问所有接口
- [x] **4.3** 验证拥有对应权限的用户可正常操作

## 实现细节

### 修改文件

```
server/apps/system_mgmt/viewset/error_log_viewset.py
server/apps/system_mgmt/viewset/operation_log_viewset.py
server/apps/system_mgmt/viewset/user_login_log_viewset.py
```

### 代码变更示例

#### ErrorLogViewSet

```python
from apps.core.decorators.api_permission import HasPermission

class ErrorLogViewSet(GroupFilterMixin, LanguageViewSet):
    # ...
    
    @HasPermission("error_logs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
```

#### OperationLogViewSet

```python
from apps.core.decorators.api_permission import HasPermission

class OperationLogViewSet(GroupFilterMixin, LanguageViewSet):
    # ...
    
    @HasPermission("operation_logs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=["post"])
    @HasPermission("operation_logs-View")
    def export_excel(self, request):
        # ...
```

#### UserLoginLogViewSet

```python
from apps.core.decorators.api_permission import HasPermission

class UserLoginLogViewSet(GroupFilterMixin, LanguageViewSet):
    # ...
    
    @HasPermission("user_logs-View")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    
    @action(detail=False, methods=["get"])
    @HasPermission("user_logs-View")
    def statistics(self, request):
        # ...
    
    @action(detail=False, methods=["post"])
    @HasPermission("user_logs-View")
    def export_excel(self, request):
        # ...
```

## 注意事项

1. `@HasPermission` 装饰器需要放在 `@action` 装饰器之后（更靠近函数定义）
2. `HasPermission` 装饰器会自动放行超级管理员 (`is_superuser=True`)
3. 保留 `permission_classes = [permissions.IsAuthenticated]` 作为基础认证要求
4. 使用已有的权限点，与菜单配置保持一致
