# OTP 安全漏洞修复

版本发布时间：2026年5月

## 安全修复

### Issue #2846: OTP 绕过漏洞修复

**问题描述**: 启用 OTP 的用户在密码验证通过后即获得 JWT token，OTP 验证仅在前端执行，可被绕过。

**修复方案**: 实现两阶段认证流程
- 密码验证通过后返回临时 `challenge_id` 而非 JWT token
- 新增 `/api/verify_otp_login/` 接口，验证 OTP 后才签发 token
- Challenge 存储在 Redis 中，5 分钟过期，一次性使用
- **首次绑定场景**: QR 码数据直接包含在登录响应中，无需额外请求

### Issue #2951: OTP 管理接口权限漏洞修复

**问题描述**: `generate_qr_code` 和 `verify_otp_code` 接口使用 `@api_exempt` 装饰器，允许未认证用户通过 `username` 参数操作任意账户的 OTP。

**修复方案**: 
- 移除 `@api_exempt` 装饰器，要求登录态
- 接口改为使用 `request.user.id` 而非 `username` 参数
- 用户只能操作自己的 OTP 配置

## API 变更

### 登录接口 `/api/login/` 响应变更

**已配置 OTP 用户的响应格式**:
```json
{
  "result": true,
  "data": {
    "require_otp": true,
    "challenge_id": "uuid-string",
    "username": "user1",
    "display_name": "User One",
    "id": 123,
    "domain": "domain.com",
    "locale": "en",
    "timezone": "UTC"
  }
}
```

**首次绑定 OTP 用户的响应格式**:
```json
{
  "result": true,
  "data": {
    "require_otp": true,
    "challenge_id": "uuid-string",
    "qr_code": "base64-encoded-qr-image",
    "need_binding": true,
    "username": "user1",
    "display_name": "User One",
    "id": 123,
    "domain": "domain.com",
    "locale": "en",
    "timezone": "UTC"
  }
}
```

**注意**: 当 `require_otp: true` 时，响应中不包含 `token` 字段。

### 新增接口 `/api/verify_otp_login/`

**请求方式**: POST

**请求参数**:
```json
{
  "challenge_id": "uuid-string",
  "otp_code": "123456"
}
```

**成功响应**:
```json
{
  "result": true,
  "data": {
    "token": "jwt-token",
    "username": "user1",
    "id": 123,
    "locale": "en",
    "timezone": "UTC"
  }
}
```

**错误响应**:
```json
{
  "result": false,
  "message": "Invalid OTP code"
}
```

### OTP 管理接口变更

| 接口 | 变更前 | 变更后 |
|------|--------|--------|
| `GET /api/generate_qr_code/` | 接受 `username` 参数，无需认证 | 需要登录态，使用 `request.user` |
| `POST /api/verify_otp_code/` | 接受 `username` 参数，无需认证 | 需要登录态，使用 `request.user` |

## 频率限制

OTP 验证接口实现了频率限制：
- 基于 IP + 用户名组合
- 5 分钟内最多 5 次失败尝试
- 超过限制后返回 429 错误

## 前端适配

前端登录流程已更新：
1. 检测 `require_otp` 响应字段
2. 如果包含 `qr_code`，显示 QR 码供用户扫描绑定
3. 使用 `challenge_id` 调用 `/api/verify_otp_login/`
4. 验证成功后获取 token 完成登录

## BREAKING CHANGES

1. **OTP 管理接口需要登录态**: 之前使用 `username` 参数调用 `generate_qr_code` 或 `verify_otp_code` 的客户端需要更新为使用认证态。

2. **登录响应结构变更**: 启用 OTP 的用户登录时，响应中不再包含 `token`，而是返回 `challenge_id`。客户端需要调用 `/api/verify_otp_login/` 完成认证。

3. **首次 OTP 绑定流程变更**: QR 码数据现在直接包含在登录响应的 `qr_code` 字段中，无需单独调用 `generate_qr_code` 接口。
