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
