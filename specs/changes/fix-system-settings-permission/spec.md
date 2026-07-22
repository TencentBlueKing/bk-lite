# Proposal: 修复 SystemSettingsViewSet 权限缺失安全漏洞

Status: done

## Migration Context

- Legacy source: `openspec/changes/fix-system-settings-permission/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## 关联 Issue

- GitHub Issue: [#2952](https://github.com/TencentBlueKing/bk-lite/issues/2952)

## 问题描述

`SystemSettingsViewSet` 的多个接口缺少权限控制，任何已登录用户都可以读取和修改全局系统设置，存在安全风险。

### 受影响的接口

| 接口 | 方法 | 当前权限 | 风险 |
|------|------|----------|------|
| `/api/system_mgmt/system_settings/get_sys_set/` | GET | 无 | 任意用户可读取所有系统配置 |
| `/api/system_mgmt/system_settings/update_sys_set/` | POST | 无 | 任意用户可修改全局配置 |
| `/api/system_mgmt/system_settings/get_password_settings/` | GET | 无 | 任意用户可读取密码策略 |
| `/api/system_mgmt/system_settings/public_portal_branding/` | GET | AllowAny | 正确（公开接口） |

### 敏感配置项

`SystemSettings` 存储的敏感配置包括：

1. **门户品牌设置**: `portal_name`, `portal_logo_url`, `portal_favicon_url`
2. **水印设置**: `watermark_enabled`, `watermark_text`
3. **敏感信息保护**: `sensitive_info_protection_enabled`, `sensitive_info_types`
4. **密码策略**: `pwd_set_min_length`, `pwd_set_max_length`, `pwd_set_required_char_types` 等

### 攻击场景

1. 普通用户可通过 `update_sys_set` 接口修改全局密码策略，降低安全要求
2. 普通用户可禁用敏感信息保护功能
3. 普通用户可修改门户品牌信息

## 解决方案

为 `SystemSettingsViewSet` 的敏感接口添加 `@HasPermission` 权限装饰器，与其他 ViewSet 保持一致的权限控制模式。

### 权限设计

使用已有的 `security_settings` 权限点（定义于 `server/support-files/system_mgmt/menus/system-manager.json`）：

| 接口 | 权限点 |
|------|--------|
| `get_sys_set` | `security_settings-View` |
| `update_sys_set` | `security_settings-Edit` |
| `get_password_settings` | `security_settings-View` |
| `public_portal_branding` | 保持 `AllowAny`（公开接口） |

### 对比参考

项目中其他 ViewSet 的权限控制模式：

```python
# LoginModuleViewSet - 认证源管理
@HasPermission("auth_sources-View")
def list(self, request, *args, **kwargs): ...

@HasPermission("auth_sources-Add")
def create(self, request, *args, **kwargs): ...

# ChannelViewSet - 渠道管理
@HasPermission("channel-View")
def list(self, request, *args, **kwargs): ...

@HasPermission("channel-Edit")
def update(self, request, *args, **kwargs): ...
```

## 影响范围

- **后端**: `server/apps/system_mgmt/viewset/system_settings_viewset.py`
- **权限配置**: 无需修改，使用已有的 `security_settings` 权限点
- **前端**: 无影响（前端已有系统设置页面，只是后端缺少权限校验）

## 验收标准

1. 未授权用户访问 `get_sys_set` 返回 403
2. 未授权用户访问 `update_sys_set` 返回 403
3. 未授权用户访问 `get_password_settings` 返回 403
4. `public_portal_branding` 仍可匿名访问
5. 超级管理员可正常访问所有接口
6. 拥有 `security_settings-View/Edit` 权限的用户可正常操作

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-14
```

## Work Checklist

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
