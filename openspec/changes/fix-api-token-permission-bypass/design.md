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
