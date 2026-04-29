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
