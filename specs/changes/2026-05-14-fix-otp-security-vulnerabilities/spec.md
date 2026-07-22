# 2026 05 14 Fix Otp Security Vulnerabilities

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-14-fix-otp-security-vulnerabilities/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

系统存在两个严重的 OTP（一次性密码）安全漏洞，导致双因子认证保护形同虚设：

### 漏洞 1: OTP 验证仅在前端执行 (Issue #2846)

**双因子认证的核心原则**：必须**两个因子都通过**才能获得访问权限。

**当前问题**：密码验证通过后，后端直接签发完整权限的 JWT token 并设置 Cookie，然后告诉前端 `enable_otp=true`。前端根据这个标志决定是否显示 OTP 页面，但此时 token 已经有效，攻击者可以直接使用这个 token 访问所有 API，完全绕过 OTP 验证。

```
当前流程：密码正确 → 签发 JWT → 前端判断是否显示 OTP 页面
                        ↑
                   攻击者在这里截获 token，直接使用
```

### 漏洞 2: OTP 管理接口公开暴露 (Issue #2951)

`generate_qr_code` 和 `verify_otp_code` 接口标记为 `@api_exempt`（免认证），且仅凭 `username` 参数操作。任何人只要知道用户名，就能：
- 调用 `generate_qr_code` 重置目标用户的 OTP 密钥
- 获取新的二维码绑定到自己的 Authenticator
- 接管目标用户的双因子认证

这两个漏洞组合使用可导致账户完全被接管，必须立即修复。

## What Changes

### 核心修复：双因子必须都通过才签发 token

```
正确流程：
  阶段1: 密码验证 → 返回临时 challenge_id（不是 JWT，无法访问 API）
  阶段2: OTP 验证 + challenge_id → 签发 JWT + 设置 Cookie

  两个因子都通过，才给访问权限
```

### 具体变更

- **BREAKING**: 登录流程重构
  - 密码验证通过后，如果用户启用了 OTP，只返回临时 `challenge_id`，**不签发 JWT，不设置 Cookie**
  - 新增 `POST /api/verify_otp_login/` 接口，验证 `challenge_id + otp_code`，通过后才签发 JWT
  - 如果用户未启用 OTP，行为不变（密码正确直接签发 token）

- **BREAKING**: OTP 管理接口权限收紧
  - 移除 `generate_qr_code` 和 `verify_otp_code` 的 `@api_exempt`
  - `generate_qr_code`: 需要登录态，只能为**当前登录用户**生成，不再接受 `username` 参数
  - `verify_otp_code`: 需要登录态，只能验证**当前登录用户**的 OTP

- 新增安全措施
  - OTP 验证失败的频率限制（防暴力破解）
  - challenge_id 有效期限制（如 5 分钟）
  - challenge_id 一次性使用（验证后失效）

## Capabilities

### New Capabilities
- `otp-challenge-flow`: 基于临时凭证的两阶段认证流程，确保 OTP 验证在后端强制执行

### Modified Capabilities
- `user-authentication`: 登录流程需要支持两阶段认证，密码验证后返回 challenge_id 而非 JWT
- `otp-management`: OTP 初始化和验证接口需要权限保护，绑定到当前会话用户

## Impact

### 受影响代码
- `server/apps/system_mgmt/nats_api.py`: `login()`, `get_user_login_token()`, `generate_qr_code()`, `verify_otp_code()`
- `server/apps/core/views/index_view.py`: `login()`, `generate_qr_code()`, `verify_otp_code()`
- `server/apps/core/urls.py`: OTP 相关路由配置

### 受影响 API
- `POST /api/login/` - 响应结构变化，启用 OTP 时不再返回 token
- `GET /api/generate_qr_code/` - 移除 username 参数，需要登录态
- `POST /api/verify_otp_code/` - 需要 challenge_id，需要登录态或临时凭证

### 前端影响
- `web/` 登录流程需要适配两阶段认证
- OTP 绑定页面需要在登录后访问

### 兼容性
- **BREAKING**: 现有依赖直接获取 token 的集成需要适配新流程
- 建议提供迁移期：可通过配置开关控制是否强制两阶段认证

## Implementation Decisions

## Context

### 当前架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           当前登录流程                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   前端                        后端                                           │
│   ┌──────┐                   ┌──────────────────────────────────┐          │
│   │ 登录 │ ─── POST /login ──▶│ nats_api.login()                │          │
│   │ 页面 │                    │   ├─ 验证用户名+密码             │          │
│   └──────┘                    │   └─ get_user_login_token()     │          │
│      │                        │       ├─ 签发 JWT ⚠️             │          │
│      │                        │       └─ 返回 token + enable_otp│          │
│      │                        └──────────────────────────────────┘          │
│      │                                       │                              │
│      │◀──────────────────────────────────────┘                              │
│      │  { token: "xxx", enable_otp: true }                                  │
│      │                                                                      │
│      ▼                                                                      │
│   ┌──────────────────────────────────────────────────────────────────┐     │
│   │ index_view.login() 设置 bklite_token Cookie ⚠️                    │     │
│   │ 前端判断 enable_otp → 显示 OTP 页面（但 token 已有效）             │     │
│   └──────────────────────────────────────────────────────────────────┘     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 涉及组件

| 组件 | 文件 | 职责 |
|------|------|------|
| NATS API | `server/apps/system_mgmt/nats_api.py` | 用户认证逻辑、OTP 管理 |
| Core Views | `server/apps/core/views/index_view.py` | HTTP 接口、Cookie 管理 |
| Auth Middleware | `server/apps/core/middlewares/auth_middleware.py` | 请求认证拦截 |
| URLs | `server/apps/core/urls.py` | 路由配置 |

### 约束

- 必须保持向后兼容：未启用 OTP 的用户登录流程不变
- 不能引入新的外部依赖
- challenge_id 存储需要考虑分布式部署场景（多实例）

## Goals / Non-Goals

**Goals:**
- 修复 Issue #2846：确保 OTP 验证在后端强制执行，两个因子都通过才签发 token
- 修复 Issue #2951：OTP 管理接口需要权限保护，不能任意操作他人账户
- 保持未启用 OTP 用户的登录体验不变
- 提供合理的安全措施（频率限制、有效期）

**Non-Goals:**
- 不重构整个认证系统，只修复 OTP 相关漏洞
- 不引入新的 2FA 方式（如 SMS、Email）
- 不修改 JWT 的签发逻辑和格式
- 不处理 OTP 恢复码（recovery codes）功能

## Decisions

### Decision 1: Challenge 存储方案

**选择：使用 Django Cache（Redis）存储 challenge**

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Django Cache (Redis)** ✅ | 分布式支持、自动过期、已有基础设施 | 需要 Redis 可用 |
| 数据库表 | 持久化、可审计 | 需要清理机制、增加 DB 负载 |
| 内存字典 | 简单 | 不支持多实例、重启丢失 |
| JWT 临时 token | 无状态 | 无法撤销、复杂度高 |

**实现**：
```python
cache_key = f"otp_challenge:{challenge_id}"
cache.set(cache_key, {
    "user_id": user.id,
    "username": username,
    "created_at": now.isoformat(),
}, timeout=300)  # 5 分钟过期
```

### Decision 2: 登录 API 响应结构

**选择：条件返回，启用 OTP 时返回 challenge_id 而非 token**

```python
# 未启用 OTP（行为不变）
{
    "result": True,
    "data": {
        "token": "jwt_xxx",
        "username": "user1",
        # ... 其他字段
    }
}

# 启用 OTP（新行为）
{
    "result": True,
    "data": {
        "require_otp": True,           # 新字段，标识需要 OTP 验证
        "challenge_id": "uuid_xxx",    # 临时凭证
        "username": "user1",
        # 不返回 token
    }
}
```

**理由**：最小化 API 变更，前端通过 `require_otp` 字段判断流程分支。

### Decision 3: OTP 验证接口设计

**选择：新增独立的登录 OTP 验证接口**

```
POST /api/verify_otp_login/
{
    "challenge_id": "uuid_xxx",
    "otp_code": "123456"
}
```

**理由**：
- 与现有 `verify_otp_code`（用于 OTP 绑定验证）职责分离
- 登录场景的 OTP 验证需要 challenge_id，绑定场景需要登录态
- 避免混淆两种不同的验证场景

### Decision 4: OTP 管理接口权限模型

**选择：移除 @api_exempt，绑定当前登录用户**

| 接口 | 当前 | 修复后 |
|------|------|--------|
| `generate_qr_code` | `@api_exempt`，接受 username 参数 | 需要登录态，只能为 `request.user` 生成 |
| `verify_otp_code` | `@api_exempt`，接受 username 参数 | 需要登录态，只能验证 `request.user` |

**特殊情况**：首次绑定 OTP 时用户尚未完成 OTP 验证，如何访问这些接口？

**解决方案**：引入"待 OTP 绑定"的中间状态
- 用户首次启用 OTP 时，密码验证通过后返回一个特殊的 `setup_token`
- `setup_token` 只允许访问 OTP 绑定相关接口，不能访问其他 API
- 绑定完成后，`setup_token` 失效，用户需要用新绑定的 OTP 完成登录

### Decision 5: 频率限制策略

**选择：基于 IP + 用户名的组合限制**

```python
# OTP 验证失败限制
MAX_OTP_ATTEMPTS = 5
LOCKOUT_DURATION = 300  # 5 分钟

# 限制键
rate_limit_key = f"otp_attempts:{ip}:{username}"
```

**理由**：
- 仅限制 IP 可能误伤 NAT 后的合法用户
- 仅限制用户名可能被用于 DoS 攻击（锁定他人账户）
- 组合限制平衡安全性和可用性

## Risks / Trade-offs

### Risk 1: 前端适配工作量
**风险**：登录流程变更需要前端配合修改
**缓解**：
- 提供详细的 API 变更文档
- 前端可通过 `require_otp` 字段判断新旧流程
- 未启用 OTP 的用户完全不受影响

### Risk 2: Challenge 存储依赖 Redis
**风险**：Redis 不可用时 OTP 登录失败
**缓解**：
- Redis 已是系统核心依赖（Celery、缓存）
- 可配置降级策略：Redis 不可用时临时禁用 OTP 强制验证（需管理员确认）

### Risk 3: 现有集成中断
**风险**：依赖直接获取 token 的第三方集成会失败
**缓解**：
- 文档明确标注 BREAKING CHANGE
- 提供迁移指南
- 考虑提供 API 版本或配置开关（不推荐长期保留）

### Risk 4: OTP 绑定流程复杂化
**风险**：首次绑定 OTP 的用户体验变复杂
**缓解**：
- `setup_token` 机制确保流程可行
- 前端引导用户完成绑定流程
- 绑定完成后立即生效，无需重新登录

## Migration Plan

### 阶段 1: 后端实现（本次变更）
1. 实现 challenge 存储机制
2. 修改 `login()` 返回逻辑
3. 新增 `verify_otp_login()` 接口
4. 收紧 OTP 管理接口权限
5. 添加频率限制

### 阶段 2: 前端适配
1. 登录页面适配两阶段流程
2. OTP 绑定页面适配新接口
3. 错误处理和用户提示

### 回滚策略
- 代码回滚：`git revert` 相关提交
- 数据回滚：无数据库 schema 变更，无需数据回滚
- 配置回滚：如有配置开关，可临时禁用新流程

## Open Questions

1. **setup_token 是否需要？**
   - 如果用户必须先完成 OTP 绑定才能启用 OTP，则不需要
   - 如果允许管理员为用户强制启用 OTP，则需要 setup_token 机制
   - **建议**：先实现简单方案（用户自行绑定后启用），后续按需扩展

2. **是否需要 OTP 恢复码？**
   - 用户丢失 OTP 设备时如何恢复？
   - **建议**：本次不实现，作为后续增强功能

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-14
```

## Capability Deltas

### otp-challenge-flow

## ADDED Requirements

### Requirement: Two-phase login for OTP-enabled users
When a user has OTP enabled, the system SHALL require both password verification AND OTP verification before issuing an access token. Password verification alone MUST NOT grant API access.

#### Scenario: Password correct, OTP enabled
- **WHEN** user submits correct username and password
- **AND** user has OTP enabled
- **THEN** system returns a temporary `challenge_id` (not a JWT token)
- **AND** system does NOT set `bklite_token` cookie
- **AND** response includes `require_otp: true`

#### Scenario: Password correct, OTP disabled
- **WHEN** user submits correct username and password
- **AND** user does NOT have OTP enabled
- **THEN** system returns JWT token (existing behavior unchanged)
- **AND** system sets `bklite_token` cookie

#### Scenario: Password incorrect
- **WHEN** user submits incorrect password
- **THEN** system returns authentication error
- **AND** no challenge_id or token is issued

### Requirement: Challenge-based OTP verification
The system SHALL provide an endpoint to verify OTP code with a challenge_id, and only issue JWT token after successful verification.

#### Scenario: Valid OTP with valid challenge
- **WHEN** user submits valid `challenge_id` and correct `otp_code` to `/api/verify_otp_login/`
- **THEN** system issues JWT token
- **AND** system sets `bklite_token` cookie
- **AND** system invalidates the `challenge_id` (one-time use)

#### Scenario: Invalid OTP code
- **WHEN** user submits valid `challenge_id` but incorrect `otp_code`
- **THEN** system returns OTP verification error
- **AND** no token is issued
- **AND** `challenge_id` remains valid for retry (until expiry or max attempts)

#### Scenario: Expired challenge
- **WHEN** user submits `challenge_id` that has expired (>5 minutes)
- **THEN** system returns challenge expired error
- **AND** user must restart login process

#### Scenario: Invalid or already-used challenge
- **WHEN** user submits `challenge_id` that does not exist or was already used
- **THEN** system returns invalid challenge error

### Requirement: Challenge storage and expiration
The system SHALL store challenges in a distributed cache with automatic expiration.

#### Scenario: Challenge creation
- **WHEN** password verification succeeds for OTP-enabled user
- **THEN** system generates a unique `challenge_id` (UUID)
- **AND** stores challenge data in cache with 5-minute TTL
- **AND** challenge data includes: user_id, username, created_at

#### Scenario: Challenge auto-expiration
- **WHEN** challenge reaches 5-minute TTL
- **THEN** cache automatically removes the challenge
- **AND** subsequent verification attempts with this challenge_id fail

### Requirement: OTP verification rate limiting
The system SHALL limit OTP verification attempts to prevent brute-force attacks.

#### Scenario: Rate limit exceeded
- **WHEN** user exceeds 5 failed OTP attempts within 5 minutes (per IP + username)
- **THEN** system blocks further OTP verification attempts
- **AND** returns rate limit error with retry-after time

#### Scenario: Rate limit reset
- **WHEN** user successfully verifies OTP
- **THEN** system resets the failure counter for that IP + username

#### Scenario: Rate limit expiry
- **WHEN** 5 minutes pass since last failed attempt
- **THEN** rate limit counter resets automatically

### otp-management

## ADDED Requirements

### Requirement: OTP QR code generation requires authentication
The system SHALL require user authentication before generating OTP QR codes, and MUST only generate for the authenticated user.

#### Scenario: Authenticated user generates own QR code
- **WHEN** authenticated user calls `GET /api/generate_qr_code/`
- **THEN** system generates new OTP secret for `request.user`
- **AND** returns QR code for the authenticated user
- **AND** does NOT accept `username` parameter

#### Scenario: Unauthenticated request to generate QR code
- **WHEN** unauthenticated user calls `GET /api/generate_qr_code/`
- **THEN** system returns 401 Unauthorized
- **AND** no OTP secret is generated or modified

#### Scenario: Attempt to generate QR code for another user
- **WHEN** authenticated user attempts to specify another username
- **THEN** system ignores the parameter and generates for `request.user` only

### Requirement: OTP verification requires authentication
The system SHALL require user authentication before verifying OTP codes for binding purposes, and MUST only verify for the authenticated user.

#### Scenario: Authenticated user verifies own OTP
- **WHEN** authenticated user calls `POST /api/verify_otp_code/` with valid OTP code
- **THEN** system verifies OTP for `request.user`
- **AND** does NOT accept `username` parameter

#### Scenario: Unauthenticated request to verify OTP
- **WHEN** unauthenticated user calls `POST /api/verify_otp_code/`
- **THEN** system returns 401 Unauthorized

#### Scenario: Invalid OTP code during binding verification
- **WHEN** authenticated user submits incorrect OTP code
- **THEN** system returns verification failed error
- **AND** user can retry with correct code

### Requirement: OTP management endpoints remove api_exempt
The system SHALL NOT exempt OTP management endpoints from authentication middleware.

#### Scenario: generate_qr_code without api_exempt
- **WHEN** `generate_qr_code` view is defined
- **THEN** it MUST NOT have `@api_exempt` decorator
- **AND** AuthMiddleware processes the request normally

#### Scenario: verify_otp_code without api_exempt
- **WHEN** `verify_otp_code` view is defined
- **THEN** it MUST NOT have `@api_exempt` decorator
- **AND** AuthMiddleware processes the request normally

### Requirement: OTP secret regeneration overwrites existing
The system SHALL overwrite existing OTP secret when generating a new QR code, invalidating previous authenticator bindings.

#### Scenario: Regenerate QR code for user with existing OTP
- **WHEN** user with existing OTP binding calls `generate_qr_code`
- **THEN** system generates new `otp_secret`
- **AND** overwrites the previous `otp_secret`
- **AND** previous authenticator app binding becomes invalid
- **AND** user must scan new QR code to rebind

## Work Checklist

## 1. Challenge 存储基础设施

- [x] 1.1 在 `server/apps/system_mgmt/` 创建 `otp_challenge.py` 模块，实现 challenge 的创建、验证、删除功能
- [x] 1.2 实现 `create_challenge(user_id, username)` 函数：生成 UUID、存储到 Django Cache、设置 5 分钟 TTL
- [x] 1.3 实现 `verify_challenge(challenge_id)` 函数：从 Cache 获取并验证 challenge 数据
- [x] 1.4 实现 `invalidate_challenge(challenge_id)` 函数：验证成功后删除 challenge（一次性使用）

## 2. 登录流程重构 (Issue #2846)

- [x] 2.1 修改 `nats_api.py` 的 `login()` 函数：OTP 启用时返回 `challenge_id` 而非 `token`
- [x] 2.2 修改 `nats_api.py` 的 `get_user_login_token()` 函数：新增参数控制是否签发 token
- [x] 2.3 修改 `index_view.py` 的 `login()` 函数：OTP 启用时不设置 `bklite_token` Cookie
- [x] 2.4 新增 NATS API `verify_otp_login(challenge_id, otp_code)`：验证 OTP 后签发 token
- [x] 2.5 新增 HTTP 接口 `POST /api/verify_otp_login/`：调用 NATS API 并设置 Cookie
- [x] 2.6 在 `urls.py` 添加 `/api/verify_otp_login/` 路由

## 3. OTP 管理接口权限收紧 (Issue #2951)

- [x] 3.1 移除 `index_view.py` 中 `generate_qr_code()` 的 `@api_exempt` 装饰器
- [x] 3.2 移除 `index_view.py` 中 `verify_otp_code()` 的 `@api_exempt` 装饰器
- [x] 3.3 修改 `generate_qr_code()` 使用 `request.user` 而非 `username` 参数
- [x] 3.4 修改 `verify_otp_code()` 使用 `request.user` 而非 `username` 参数
- [x] 3.5 修改 `nats_api.py` 的 `generate_qr_code()` 接受 `user_id` 而非 `username`
- [x] 3.6 修改 `nats_api.py` 的 `verify_otp_code()` 接受 `user_id` 而非 `username`

## 4. 频率限制

- [x] 4.1 在 `otp_challenge.py` 实现 OTP 验证失败计数器（基于 IP + username）
- [x] 4.2 实现 `check_rate_limit(ip, username)` 函数：检查是否超过 5 次失败限制
- [x] 4.3 实现 `record_failed_attempt(ip, username)` 函数：记录失败尝试
- [x] 4.4 实现 `reset_rate_limit(ip, username)` 函数：验证成功后重置计数器
- [x] 4.5 在 `verify_otp_login` 接口中集成频率限制检查

## 5. 前端适配

- [x] 5.1 修改 `web/` 登录页面：检测 `require_otp` 响应字段
- [x] 5.2 实现 OTP 验证页面：提交 `challenge_id + otp_code` 到 `/api/verify_otp_login/`
- [x] 5.3 修改 OTP 绑定页面：移除 `username` 参数，依赖登录态

## 6. 测试

- [x] 6.1 编写 `test_otp_challenge.py`：测试 challenge 创建、验证、过期、一次性使用
- [x] 6.2 编写登录流程测试：OTP 启用时不返回 token、OTP 禁用时正常返回
- [x] 6.3 编写 OTP 验证测试：正确 OTP 签发 token、错误 OTP 拒绝、challenge 过期
- [ ] 6.4 编写权限测试：未登录访问 `generate_qr_code` 返回 401
- [x] 6.5 编写频率限制测试：超过 5 次失败后被锁定

## 7. 文档和清理

- [x] 7.1 更新 API 文档：记录 `/api/login/` 响应结构变化
- [x] 7.2 更新 API 文档：记录新增 `/api/verify_otp_login/` 接口
- [x] 7.3 添加 BREAKING CHANGE 说明到 CHANGELOG
