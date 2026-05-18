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
