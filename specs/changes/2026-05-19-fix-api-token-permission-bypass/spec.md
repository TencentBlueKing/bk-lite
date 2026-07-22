# 2026 05 19 Fix Api Token Permission Bypass

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-19-fix-api-token-permission-bypass/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

### 当前状态

API Token 认证流程存在权限绕过漏洞：

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         当前 API Token 认证流程                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│   API Token 请求                                                                │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────┐                                  │
│   │  APISecretMiddleware                     │                                  │
│   │  - 验证 token 有效性                      │                                  │
│   │  - 设置 request.api_pass = True          │                                  │
│   │  - 调用 APISecretAuthBackend             │                                  │
│   └─────────────────────────────────────────┘                                  │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────┐                                  │
│   │  APISecretAuthBackend                    │                                  │
│   │  - 只设置 user.group_list = [team]       │                                  │
│   │  - ❌ 缺失: roles, permission            │                                  │
│   └─────────────────────────────────────────┘                                  │
│         │                                                                       │
│         ▼                                                                       │
│   ┌─────────────────────────────────────────┐                                  │
│   │  @HasPermission 装饰器                   │                                  │
│   │  if api_pass: return OK  ← 直接放行！    │                                  │
│   └─────────────────────────────────────────┘                                  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 对比：Web Token 认证

Web Token 认证（`AuthBackend`）会调用 `verify_token` RPC，返回完整的用户信息：
- `roles`: 用户角色列表（如 `["ops-analysis--admin", "system-manager--editor"]`）
- `permission`: 菜单权限（如 `{"ops-analysis": ["view-View", "view-AddView"]}`）
- `is_superuser`: 超级用户标识

### 约束

- 不能破坏现有 API Token 的正常使用场景
- 权限计算逻辑需要与 Web Token 保持一致
- 需要考虑性能影响（避免每次请求都查询数据库）

## Goals / Non-Goals

**Goals:**
- 修复 API Token 权限绕过漏洞，确保所有请求都经过权限校验
- API Token 用户的权限与其关联用户在 system_mgmt 中的配置一致
- 保持与 Web Token 认证相同的权限模型和校验逻辑
- 通过缓存机制保证性能

**Non-Goals:**
- 不引入独立的 API Token 权限模型（如在 UserAPISecret 中配置允许的权限）
- 不修改 UserAPISecret 数据模型
- 不改变 `api_pass` 标志的设置逻辑（仍然用于标识 API Token 请求）

## Decisions

### Decision 1: 在 APISecretAuthBackend 中填充权限信息

**选择**: 在 `APISecretAuthBackend.authenticate()` 中调用新方法 `_populate_user_permissions()` 填充用户权限

**理由**:
- 认证后端是设置用户信息的标准位置
- 与 `AuthBackend` 的实现模式一致
- 只需修改一处代码，所有使用 API Token 的请求都会受益

**替代方案**:
- 在中间件中填充权限 → 职责不清晰，中间件应该只做认证
- 在每个 ViewSet 中检查 → 代码重复，容易遗漏

### Decision 2: 复用 get_user_all_roles 逻辑

**选择**: 将 `system_mgmt/nats_api.py` 中的 `get_user_all_roles` 逻辑复制到 `APISecretAuthBackend`

**理由**:
- 保证权限计算逻辑与 Web Token 完全一致
- 避免跨模块依赖（core 不应该依赖 system_mgmt）
- 逻辑相对简单，复制不会造成维护负担

**替代方案**:
- 调用 RPC 获取权限 → 增加网络开销，API Token 场景不需要
- 直接 import nats_api 函数 → 引入不必要的模块依赖

### Decision 3: 使用 Django Cache 缓存权限信息

**选择**: 使用 `django.core.cache` 缓存权限信息，缓存 key 为 `api_token_permissions:{username}:{domain}:{team}`，TTL 60 秒

**理由**:
- 避免每次 API Token 请求都查询数据库
- 60 秒 TTL 平衡了性能和权限更新的及时性
- 复用现有的缓存基础设施

**替代方案**:
- 不缓存 → 性能影响大，每次请求都要查询多张表
- 更长的 TTL → 权限变更后生效太慢

### Decision 4: 移除 api_pass 直接放行，保留标志本身

**选择**: 移除 `HasRole` 和 `HasPermission` 中的 `api_pass` 直接放行逻辑，但保留 `api_pass` 标志

**理由**:
- `api_pass` 标志仍然有用（如日志、审计、特殊处理）
- 只需要移除"直接放行"的行为，不需要移除标志本身
- 最小化改动范围

## Risks / Trade-offs

### Risk 1: 现有 API Token 集成可能失败

**风险**: 如果 API Token 关联的用户没有配置正确的权限，修复后请求会返回 403

**缓解**:
- 在发布说明中明确说明此变更
- 提供检查脚本，帮助用户验证 API Token 关联用户的权限配置
- 考虑增加日志，记录因权限不足被拒绝的 API Token 请求

### Risk 2: 权限缓存导致权限变更延迟生效

**风险**: 用户权限变更后，最多需要 60 秒才能对 API Token 请求生效

**缓解**:
- 60 秒是可接受的延迟
- 如果需要立即生效，可以手动清除缓存
- 未来可以考虑在权限变更时主动清除相关缓存

### Risk 3: 数据库查询性能

**风险**: 权限计算需要查询 Group、Role、Menu 表

**缓解**:
- 使用 `prefetch_related` 优化查询
- 缓存机制确保同一用户的重复请求不会重复查询
- 查询逻辑与 Web Token 相同，已经过生产验证

## Migration Plan

### 部署步骤

1. 部署代码更新
2. 验证 API Token 请求的权限校验正常工作
3. 监控 403 错误率，识别需要更新权限配置的 API Token

### 回滚策略

如果出现问题，可以通过以下方式快速回滚：
1. 恢复 `api_permission.py` 中的 `api_pass` 直接放行逻辑
2. 或者在 `APISecretAuthBackend` 中设置 `user.is_superuser = True`（临时方案）

## Open Questions

1. **是否需要提供权限检查工具？** 帮助用户验证 API Token 关联用户的权限配置
2. **是否需要在 API Token 创建时验证用户权限？** 防止创建无权限的 API Token
3. **缓存 TTL 是否需要可配置？** 当前硬编码为 60 秒

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-19
```

## Capability Deltas

### api-permission-check

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

### api-token-permission-population

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
- **THEN** 系统 SHALL 直接使用缓存的权限信息
- **AND** 系统 SHALL NOT 查询数据库

#### Scenario: 缓存未命中

- **WHEN** 用户使用 API Token 发起请求
- **AND** 缓存中不存在该用户的权限信息或已过期
- **THEN** 系统 SHALL 查询数据库计算权限信息
- **AND** 系统 SHALL 将计算结果缓存 60 秒

#### Scenario: 缓存 Key 格式

- **WHEN** 系统缓存 API Token 用户的权限信息
- **THEN** 缓存 Key SHALL 为 `api_token_permissions:{username}:{domain}:{team}`

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

## Work Checklist

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
