# Proposal: 修复日志类 ViewSet 权限缺失安全漏洞

## 关联 Issue

- 源自 Issue #2952 的扩展审计发现

## 问题描述

`system_mgmt` 模块中的三个日志类 ViewSet 仅使用 `IsAuthenticated` 权限，缺少细粒度的 `@HasPermission` 权限控制，任何已登录用户都可以查看和导出敏感日志信息。

### 受影响的 ViewSet

| ViewSet | 当前权限 | 风险等级 | 问题 |
|---------|----------|----------|------|
| `ErrorLogViewSet` | `IsAuthenticated` | 🟡 中 | 任意用户可查看错误日志，可能暴露系统内部信息 |
| `OperationLogViewSet` | `IsAuthenticated` | 🔴 高 | 任意用户可查看/导出操作日志，包含敏感操作记录 |
| `UserLoginLogViewSet` | `IsAuthenticated` | 🔴 高 | 任意用户可查看/导出登录日志，包含用户行为信息 |

### 受影响的接口

#### ErrorLogViewSet
| 接口 | 方法 | 当前权限 | 风险 |
|------|------|----------|------|
| `/api/system_mgmt/error_log/` | GET (list) | 仅登录 | 任意用户可查看错误日志 |

#### OperationLogViewSet
| 接口 | 方法 | 当前权限 | 风险 |
|------|------|----------|------|
| `/api/system_mgmt/operation_log/` | GET (list) | 仅登录 | 任意用户可查看操作日志 |
| `/api/system_mgmt/operation_log/export_excel/` | POST | 仅登录 | 任意用户可导出操作日志 |

#### UserLoginLogViewSet
| 接口 | 方法 | 当前权限 | 风险 |
|------|------|----------|------|
| `/api/system_mgmt/user_login_log/` | GET (list) | 仅登录 | 任意用户可查看登录日志 |
| `/api/system_mgmt/user_login_log/statistics/` | GET | 仅登录 | 任意用户可查看登录统计 |
| `/api/system_mgmt/user_login_log/export_excel/` | POST | 仅登录 | 任意用户可导出登录日志 |

## 解决方案

为三个日志类 ViewSet 添加 `@HasPermission` 权限装饰器，使用已存在的权限点。

### 权限设计

使用 `server/support-files/system_mgmt/menus/system-manager.json` 中已定义的权限点：

| ViewSet | 接口 | 权限点 |
|---------|------|--------|
| `ErrorLogViewSet` | list | `error_logs-View` |
| `OperationLogViewSet` | list | `operation_logs-View` |
| `OperationLogViewSet` | export_excel | `operation_logs-View` |
| `UserLoginLogViewSet` | list | `user_logs-View` |
| `UserLoginLogViewSet` | statistics | `user_logs-View` |
| `UserLoginLogViewSet` | export_excel | `user_logs-View` |

### 权限点参考 (system-manager.json)

```json
{
  "id": "user_logs",
  "name": "Login Logs",
  "operation": ["View", "Delete"]
},
{
  "id": "operation_logs",
  "name": "Operation Logs",
  "operation": ["View"]
},
{
  "id": "error_logs",
  "name": "Error Logs",
  "operation": ["View"]
}
```

## 影响范围

- **后端**:
  - `server/apps/system_mgmt/viewset/error_log_viewset.py`
  - `server/apps/system_mgmt/viewset/operation_log_viewset.py`
  - `server/apps/system_mgmt/viewset/user_login_log_viewset.py`
- **权限配置**: 无需修改，使用已有权限点
- **前端**: 无影响

## 验收标准

1. 未授权用户访问 `error_log` list 返回 403
2. 未授权用户访问 `operation_log` list 返回 403
3. 未授权用户访问 `operation_log/export_excel` 返回 403
4. 未授权用户访问 `user_login_log` list 返回 403
5. 未授权用户访问 `user_login_log/statistics` 返回 403
6. 未授权用户访问 `user_login_log/export_excel` 返回 403
7. 超级管理员可正常访问所有接口
8. 拥有对应权限的用户可正常操作
