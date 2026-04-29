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
