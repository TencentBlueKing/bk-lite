# 2026 04 27 Ac06 Jwt Blacklist

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-04-27-ac06-jwt-blacklist/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

安全审计 AC-06 发现 JWT 令牌无法被主动撤销：没有 `jti`/`exp` 标准字段、没有黑名单机制、退出后 token 仍然有效直到 24h 自然过期。`bklite_token` Cookie 也缺少 HttpOnly 和 Secure 属性。这些问题直接违反 GB/T 22239-2019 §8.1.4.1 b 和 §8.1.4.8 a 的要求。

## What Changes

- 签发 JWT 时加入 `jti`（uuid4）和 `exp`（基于 `login_expired_time`）标准字段
- 新增 Redis Token 黑名单（key: `jwt:blacklist:{jti}`，TTL = token 剩余存活时间）
- 验证链路加入黑名单检查，被撤销的 token 立即返回 401
- 退出接口（federated-logout、forceLogout）调用后端撤销 token
- `bklite_token` Cookie 改由后端 `Set-Cookie` 写入，加 HttpOnly + Secure 属性
- **BREAKING**: 旧 token（无 jti/exp）在过渡期（24h）后不再被接受

## Capabilities

### New Capabilities
- `token-blacklist`: JWT 令牌黑名单机制——签发含 jti/exp 的 token、Redis 黑名单存储与查询、验证时黑名单拦截、退出时主动撤销
- `secure-token-cookie`: bklite_token Cookie 安全加固——后端 Set-Cookie 签发、HttpOnly/Secure/SameSite 属性、前端读写方式迁移

### Modified Capabilities
（无已有 spec 受影响）

## Impact

- **后端** (`server/`):
  - `apps/system_mgmt/nats_api.py` — 3 处 jwt.encode 改 payload、verify_token 加黑名单检查
  - 新增 `token_blacklist.py` 工具模块（Redis 读写）
  - 新增或修改登录接口以 Set-Cookie 方式返回 bklite_token
  - 新增 token 撤销 NATS RPC 端点
- **前端** (`web/`):
  - `utils/crossDomainAuth.ts` — 不再通过 document.cookie 写入 token
  - `api/auth/federated-logout/route.ts` — 调后端撤销接口
  - `utils/forceLogout.ts` — 同上
- **依赖**: Redis（已有，无新增）
- **兼容性**: 需 24h 过渡期，期间新旧 token 并存；过渡期后移除兼容代码

## Implementation Decisions

## Context

当前 JWT 实现（`server/apps/system_mgmt/nats_api.py`）签发 payload 仅含 `user_id` + `login_time`，无标准 `jti`/`exp` 字段。验证通过手动比较 `login_time` 与 `login_expired_time` 实现过期检查。无任何黑名单机制，退出仅清除前端 cookie。`bklite_token` 通过 `document.cookie` 写入，无 HttpOnly/Secure 属性。

项目已有 Redis 作为 Django cache backend（`django.core.cache`），且 `permission_cache.py` 已封装了基于 cache 的读写模式。

## Goals / Non-Goals

**Goals:**
- JWT 支持标准 `jti` + `exp` 字段，PyJWT 自动校验过期
- 基于 Redis 的 token 黑名单，支持主动撤销
- 退出时 token 立即失效
- `bklite_token` Cookie 具备 HttpOnly + Secure + SameSite 属性
- 24h 过渡期内兼容旧 token

**Non-Goals:**
- 不做 refresh token / 双 token 机制
- 不改 NextAuth 自身的 session 管理
- 不做全量 token 管理后台（如查看所有活跃 token）
- 不改 JWT 签名算法或密钥轮换机制

## Decisions

### D1: 黑名单存储 — Django cache（Redis backend）

**选择**: 使用 `django.core.cache` 操作 Redis，key 格式 `jwt:blacklist:{jti}`，value 为 `1`，TTL 为 token 剩余存活秒数。

**备选**:
- 直接用 `django-redis` 的 raw client → 引入额外依赖路径，与现有 permission_cache 模式不一致
- 数据库表 → 每次请求查 DB，性能差；需定期清理过期记录

**理由**: 与 `permission_cache.py` 保持同一模式；TTL 自动清理无需维护任务；Redis 单次 EXISTS 查询 < 1ms。

### D2: 黑名单检查位置 — verify_token 内部，缓存之后

**选择**: 在 `nats_api.py` 的 `verify_token` 中，decode 成功后、返回用户信息前检查黑名单。`permission_cache` 的 60s TTL 缓存保持不变。

**备选**:
- 缓存之前检查 → 每次请求都查 Redis，高频场景压力大
- 中间件层检查 → 验证逻辑分散到两处，维护困难

**理由**: 最差情况下，撤销后 60s 内旧缓存仍可用。对于退出场景这是可接受的延迟（用户退出后不会立即用同一 token 再请求）。若后续需要更严格，可单独将黑名单检查提到缓存前，改动隔离。

**补充**: 退出时同步调用 `clear_token_info_cache(username, domain)` 清除该用户的验证缓存，将实际延迟降至接近 0。

### D3: Cookie 安全加固 — 后端 Set-Cookie

**选择**: 登录成功后，后端在 HTTP 响应中通过 `Set-Cookie` 头写入 `bklite_token`，属性为 `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400`。前端 `crossDomainAuth.ts` 改为仅负责清除（调后端接口），不再写入。

**备选**:
- 保持前端写入，仅加 Secure → 无法实现 HttpOnly，审计不通过
- 使用 NextAuth session token 替代 bklite_token → 改动范围过大，涉及整个认证架构

**理由**: HttpOnly 是审计硬性要求，只能由服务端设置。改动集中在登录响应和前端 crossDomainAuth 模块。

### D4: 过渡兼容策略

**选择**: `verify_token` 中根据 payload 是否含 `jti`+`exp` 字段分支处理：
- 新 token: PyJWT 强制 `exp` 校验 + 黑名单检查
- 旧 token: 走原有 `login_time` 手动校验，不检查黑名单（因为无 jti）

旧 token 最长存活 24h 后自然过期。一个版本周期后移除兼容分支。

### D5: 撤销端点 — NATS RPC

**选择**: 在 `nats_api.py` 新增 `revoke_token` RPC 方法，接收 token 字符串，decode 取 `jti` 和 `exp`，写入黑名单并清除用户验证缓存。

**理由**: 现有 `verify_token` 已通过 NATS RPC 暴露，撤销接口保持同一通信模式。前端 `federated-logout` route 通过 Next.js API → 后端 REST → NATS RPC 调用链完成撤销。

## Risks / Trade-offs

| Risk | Impact | Mitigation |
|------|--------|------------|
| Redis 不可用时黑名单失效 | token 无法被撤销，但仍受 exp 自然过期保护 | exp 字段确保最大存活 24h；Redis 高可用由运维保障 |
| 60s 缓存延迟窗口 | 撤销后极短时间内 token 仍可用 | 退出时主动清除 verify 缓存，实际延迟接近 0 |
| 旧 token 过渡期无法撤销 | 24h 内旧 token 不受黑名单保护 | 可接受：部署后旧 token 24h 内全部过期 |
| Set-Cookie 跨域限制 | 如果前后端不同域，Secure + SameSite=Lax 可能受限 | 当前部署架构前后端同域（Next.js proxy）；若跨域需调整为 SameSite=None + Secure |

## Migration Plan

1. **部署后端** — 新 token 签发含 jti/exp，verify_token 支持新旧双模式，黑名单模块就绪
2. **部署前端** — 退出流程调用撤销接口，cookie 写入改为读取后端 Set-Cookie
3. **等待 24h** — 旧 token 全部自然过期
4. **清理** — 移除 verify_token 中旧 token 兼容分支（可在下一版本）

**回滚**: 后端代码回滚后，已签发的新 token（含 exp）仍能被旧 verify_token 解析（多余字段被忽略），不影响服务。

## Open Questions

- 是否需要支持"踢出用户"（管理员主动撤销某用户所有 token）？当前方案按单 jti 撤销，批量撤销需额外设计（如 `jwt:blacklist:user:{user_id}` key）。
- `bklite_token` 在 mobile 端（Tauri WebView）的 cookie 行为是否与浏览器一致？需验证 HttpOnly cookie 在 Tauri 中的读写表现。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-24
```

## Capability Deltas

### secure-token-cookie

## ADDED Requirements

### Requirement: bklite_token cookie SHALL be set by the server with secure attributes
The backend SHALL set the `bklite_token` cookie via `Set-Cookie` response header on successful login. The cookie SHALL include the attributes: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, and `Max-Age` equal to the configured `login_expired_time` in seconds.

#### Scenario: Login response sets secure cookie
- **WHEN** a user successfully authenticates via the login endpoint
- **THEN** the HTTP response includes a `Set-Cookie` header for `bklite_token` with `HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=86400` (default)

#### Scenario: Cookie is not accessible to JavaScript
- **WHEN** client-side JavaScript attempts to read `document.cookie` for `bklite_token`
- **THEN** the cookie is not visible because it has the `HttpOnly` attribute

### Requirement: Frontend SHALL NOT write bklite_token via document.cookie
The frontend `crossDomainAuth.ts` module SHALL NOT set the `bklite_token` cookie via `document.cookie`. The `saveAuthToken` function SHALL be removed or refactored to rely on the server-set cookie. The `clearAuthToken` function SHALL call the backend logout endpoint which clears the cookie via `Set-Cookie` with `Max-Age=0`.

#### Scenario: Frontend login flow does not write cookie directly
- **WHEN** a user completes login on the frontend
- **THEN** the frontend does not execute `document.cookie = "bklite_token=..."` and instead relies on the backend `Set-Cookie` header

#### Scenario: Frontend logout clears cookie via backend
- **WHEN** a user logs out
- **THEN** the backend response includes `Set-Cookie: bklite_token=; Max-Age=0; HttpOnly; Secure; SameSite=Lax; Path=/` to clear the cookie

### Requirement: Backend SHALL clear bklite_token cookie on logout
The logout/revocation endpoint SHALL include a `Set-Cookie` header that expires the `bklite_token` cookie (setting `Max-Age=0` with the same attributes).

#### Scenario: Logout response clears the cookie
- **WHEN** the token revocation endpoint is called
- **THEN** the HTTP response includes a `Set-Cookie` header that sets `bklite_token` with `Max-Age=0` to delete the cookie from the browser

### token-blacklist

## ADDED Requirements

### Requirement: JWT payload SHALL contain jti and exp standard claims
The system SHALL include a `jti` claim (UUID4 hex string) and an `exp` claim (UNIX timestamp) in every JWT token issued at login. The `exp` value SHALL equal the current time plus the configured `login_expired_time` (in seconds). The `login_time` claim SHALL be retained for backward compatibility during the transition period.

#### Scenario: New token contains jti and exp
- **WHEN** a user successfully authenticates and a JWT is issued
- **THEN** the token payload contains `user_id`, `login_time`, `jti` (32-char hex string), and `exp` (integer UNIX timestamp equal to current time + login_expired_time)

#### Scenario: Each token has a unique jti
- **WHEN** two tokens are issued for the same user in sequence
- **THEN** each token has a distinct `jti` value

### Requirement: Token verification SHALL use PyJWT exp auto-validation
The system SHALL decode tokens with PyJWT's built-in `exp` verification enabled for tokens that contain an `exp` claim. Tokens with an expired `exp` SHALL be rejected with a 401 response.

#### Scenario: Expired new-format token is rejected
- **WHEN** a request includes a JWT whose `exp` is in the past
- **THEN** the system returns HTTP 401 and does not process the request

#### Scenario: Valid new-format token is accepted
- **WHEN** a request includes a JWT whose `exp` is in the future and `jti` is not blacklisted
- **THEN** the system processes the request normally

### Requirement: System SHALL maintain a Redis-based token blacklist
The system SHALL store revoked token identifiers in Redis using `django.core.cache` with key format `jwt:blacklist:{jti}`, value `1`, and TTL equal to the token's remaining time until `exp`. A token SHALL be considered blacklisted if its `jti` key exists in Redis.

#### Scenario: Blacklisted token entry auto-expires
- **WHEN** a token with `jti=abc` and 3600 seconds remaining until `exp` is blacklisted
- **THEN** Redis key `jwt:blacklist:abc` is set with TTL=3600 and automatically deleted after 3600 seconds

### Requirement: Token verification SHALL check the blacklist
The system SHALL check whether a token's `jti` exists in the blacklist during verification. If the `jti` is blacklisted, the system SHALL reject the request with HTTP 401. The blacklist check SHALL occur after JWT decode and before returning user info.

#### Scenario: Request with blacklisted token is rejected
- **WHEN** a request includes a valid JWT whose `jti` is present in the blacklist
- **THEN** the system returns HTTP 401

#### Scenario: Request with non-blacklisted token proceeds
- **WHEN** a request includes a valid JWT whose `jti` is not in the blacklist
- **THEN** the system proceeds with normal authentication

### Requirement: Logout SHALL revoke the current token
The system SHALL provide a token revocation endpoint (NATS RPC `revoke_token`). When invoked, the endpoint SHALL decode the token, write its `jti` to the blacklist with appropriate TTL, and clear the user's verify_token cache. The frontend logout flows (federated-logout, forceLogout) SHALL call this endpoint before clearing client-side state.

#### Scenario: User logs out and token is immediately revoked
- **WHEN** a user triggers logout
- **THEN** the backend adds the token's `jti` to the blacklist, clears the user's token info cache, and subsequent requests with that token receive HTTP 401

#### Scenario: Force logout revokes token
- **WHEN** a forced logout is triggered (e.g., on 401/460 response)
- **THEN** the system attempts to call the revocation endpoint before clearing client state

### Requirement: Legacy tokens SHALL be accepted during transition period
The system SHALL accept tokens without `jti`/`exp` claims by falling back to the existing `login_time`-based expiry check. Legacy tokens SHALL NOT be subject to blacklist checks. This compatibility behavior SHALL be removed after one release cycle.

#### Scenario: Old-format token is accepted during transition
- **WHEN** a request includes a JWT with `user_id` and `login_time` but no `jti` or `exp`
- **THEN** the system verifies the token using the legacy `login_time` comparison and processes the request if valid

#### Scenario: Old-format token naturally expires
- **WHEN** a legacy token's `login_time` is older than `login_expired_time`
- **THEN** the system rejects the token with HTTP 401

## Work Checklist

## 1. Token 黑名单模块（后端）

- [x] 1.1 新建 `server/apps/system_mgmt/utils/token_blacklist.py`，实现 `blacklist_token(jti, exp_timestamp)` 和 `is_blacklisted(jti)` 函数，使用 `django.core.cache` 操作 Redis，key 格式 `jwt:blacklist:{jti}`，TTL 为 token 剩余秒数
- [x] 1.2 为 `token_blacklist.py` 编写单元测试，覆盖：写入黑名单、查询已黑名单 jti 返回 True、查询未黑名单 jti 返回 False、TTL 过期后自动清除

## 2. JWT 签发补全 jti + exp（后端）

- [x] 2.1 修改 `server/apps/system_mgmt/nats_api.py` 中 3 处 `jwt.encode` 调用（约 L1044、L1153、L1283），payload 新增 `jti=uuid4().hex` 和 `exp=int(time.time()) + login_expired_time_seconds`
- [x] 2.2 编写测试验证新签发的 token payload 包含 `jti`（32 字符 hex）和 `exp`（整数时间戳），且两次签发的 jti 不同

## 3. Token 验证加入黑名单检查（后端）

- [x] 3.1 修改 `nats_api.py` 中 `verify_token`（约 L100-116），对含 `jti`+`exp` 的新 token 启用 PyJWT 自动 exp 校验 + 调用 `is_blacklisted(jti)` 检查；对旧 token（无 jti/exp）保持原有 `login_time` 逻辑
- [x] 3.2 编写测试覆盖：新 token 正常通过、新 token 过期被拒、新 token 被黑名单拒绝、旧 token 走兼容路径通过、旧 token 过期被拒

## 4. Token 撤销端点（后端）

- [x] 4.1 在 `nats_api.py` 新增 `revoke_token` NATS RPC 方法：decode token 取 jti/exp → 调用 `blacklist_token` → 调用 `clear_token_info_cache(username, domain)` 清除验证缓存
- [x] 4.2 在 `server/apps/system_mgmt/` 中暴露 REST 端点（如 `POST /system_mgmt/token/revoke/`）供前端调用，内部调 NATS RPC `revoke_token`
- [x] 4.3 编写测试验证：撤销后 token 的 jti 出现在黑名单中，且后续 verify_token 返回 401

## 5. Cookie 安全加固（后端）

- [x] 5.1 在登录成功的响应中（涉及 `nats_api.py` 中签发 token 后返回的 HTTP 响应），添加 `Set-Cookie: bklite_token=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=<login_expired_time>`
- [x] 5.2 在撤销端点（4.2）的响应中添加 `Set-Cookie: bklite_token=; Max-Age=0; HttpOnly; Secure; SameSite=Lax; Path=/` 清除 cookie
- [x] 5.3 编写测试验证登录响应的 Set-Cookie 头包含 HttpOnly、Secure、SameSite=Lax 属性

## 6. 前端退出流程对接（前端）

- [x] 6.1 修改 `web/src/app/(core)/api/auth/federated-logout/route.ts`：在返回成功前调用后端撤销接口 `POST /system_mgmt/token/revoke/`，传入当前 token
- [x] 6.2 修改 `web/src/utils/forceLogout.ts`：在 `forceLogoutAndRedirect` 中调用撤销接口（best-effort，失败不阻塞退出流程）
- [x] 6.3 修改 `web/src/utils/crossDomainAuth.ts`：移除 `saveAuthToken` 中的 `document.cookie` 写入逻辑（改为依赖后端 Set-Cookie），`clearAuthToken` 改为调后端接口清除
- [x] 6.4 检查并更新所有 `saveAuthToken` 调用点（`auth.tsx`、`SigninClient.tsx`、`PopupAuthBridge.tsx`、`wechat-popup bridge page.tsx`），确保登录流程不再前端写 cookie

## 7. 验证与清理

- [x] 7.1 运行 `cd server && make test` 确认所有后端测试通过
- [x] 7.2 运行 `cd web && pnpm lint && pnpm type-check` 确认前端无类型/lint 错误
- [x] 7.3 手动验证：登录 → 检查 cookie 属性 → 退出 → 用旧 token 请求确认返回 401
