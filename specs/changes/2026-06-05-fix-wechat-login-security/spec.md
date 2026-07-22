# Proposal: 修复微信登录安全漏洞

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-06-05-fix-wechat-login-security/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

### 问题背景
GitHub Issue #2899 报告了一个严重的安全漏洞：

**`/api/wechat_user_register/` 接口可被攻击者直接调用，传入任意 `user_id` 即可获得该账号的登录态，导致任意账号接管。**

### 漏洞原因

当前架构中，微信 OAuth 验证在 Next.js 前端完成，但后端接口是公开的：

```
正常流程：用户 → 微信授权 → Next.js 验证 code → 获取 openid → 调用后端 → 签发 token
攻击流程：攻击者 → 直接调用后端 /api/wechat_user_register/ → 签发 token（绕过验证）
```

### 影响范围
- 任意已存在账号可被接管
- 攻击者可创建新账号并获得 guest 权限
- 如果目标是管理员账号，攻击者获得全站最高权限

## What Changes

### 方案：将微信 OAuth 验证移到后端

1. **新增后端接口** `POST /api/wechat_login/`
   - 接收微信授权 code
   - 后端调用微信 API 验证 code，获取 openid
   - 用 openid 创建/获取本地用户
   - 签发 JWT token

2. **简化前端逻辑**
   - 前端只负责获取微信 code
   - 直接将 code 传给后端新接口
   - 不再直接调用微信 API

3. **废弃旧接口**
   - 移除 `/api/wechat_user_register/` 接口

4. **开发调试支持**
   - 添加 Mock 模式，本地开发时可跳过真实微信验证
   - Mock 返回与真实 API 相同的数据结构，确保行为一致

### 安全保障
- 微信 code 只能使用一次，且必须配合 app_secret 才能换取 openid
- Mock 模式仅在 `DEBUG=True` 时生效，生产环境永不执行
- 上线前必须在测试环境用真实微信扫码验证

## References

- GitHub Issue: https://github.com/TencentBlueKing/bk-lite/issues/2899
- 微信 OAuth 文档: https://developers.weixin.qq.com/doc/oplatform/Website_App/WeChat_Login/Wechat_Login.html

## Implementation Decisions

## 架构变更

### 当前架构（不安全）

```
用户 → 微信授权 → Next.js 前端 → 调用微信 API 获取 openid
                       │
                       ▼
              POST /api/wechat_user_register/
              { user_id: openid }
                       │
                       ▼
              Django 后端（无验证，直接签发 token）
```

**漏洞**：攻击者可直接调用后端接口，绕过前端的微信验证。

### 目标架构（安全）

```
用户 → 微信授权 → Next.js 前端 → POST /api/wechat_login/
                                 { code: "微信授权码" }
                                        │
                                        ▼
                               Django 后端
                                        │
                                        ▼
                               调用微信 API 验证 code
                               获取 openid
                                        │
                                        ▼
                               用 openid 创建/获取用户
                               签发 JWT token
```

**安全**：code 只能使用一次，且必须配合 app_secret 才能换取 openid。

## 后端设计

### 新增接口：`POST /api/wechat_login/`

**Request:**
```json
{
    "code": "微信授权码"
}
```

**Response (成功):**
```json
{
    "result": true,
    "data": {
        "id": 123,
        "username": "oXk8s5xxxxxxxxxxxxxxxxxxx",
        "display_name": "微信昵称",
        "token": "jwt...",
        "is_first_login": true,
        "locale": "zh",
        "timezone": "Asia/Shanghai"
    }
}
```

**Response (失败):**
```json
{
    "result": false,
    "message": "Invalid WeChat code"
}
```

### 核心函数：`verify_wechat_code()`

统一入口，Mock 和真实 API 返回相同结构：

```python
def verify_wechat_code(code: str) -> dict:
    """
    Returns:
        {
            "success": bool,
            "openid": str,       # 成功时
            "nickname": str,     # 成功时
            "unionid": str,      # 成功时（可选）
            "error": str,        # 失败时
            "errcode": int       # 失败时（可选）
        }
    """
```

### Mock 模式设计

**触发条件**：`DEBUG=True` 且 `WECHAT_MOCK_MODE=True`

**Mock 数据格式**：与真实微信 API 返回格式一致
- openid: 28位，以 `o` 开头
- nickname: 支持 emoji
- 支持模拟错误场景（code=invalid, code=expired, code=timeout）

**安全保障**：
- 双重条件检查，生产环境 `DEBUG=False` 时永不执行
- Mock 模式打 warning 日志，便于发现误配置

## 前端设计

### 修改 `web/src/app/api/wechat-popup-login/route.ts`

**Before:**
```typescript
// 1. 获取微信配置
// 2. 用 code 换 access_token（调用微信 API）
// 3. 用 access_token 获取用户信息（调用微信 API）
// 4. 调用后端 /api/wechat_user_register/
```

**After:**
```typescript
// 1. 直接将 code 传给后端
const response = await fetch(`${NEXTAPI_URL}/api/v1/core/api/wechat_login/`, {
    method: 'POST',
    body: JSON.stringify({ code }),
});
// 2. 返回后端响应
```

### 修改 `web/src/lib/wechatProvider.ts`

调整 `authorize` 回调逻辑，使用新的后端接口。

## 废弃接口

| 接口 | 处理方式 |
|------|----------|
| `POST /api/wechat_user_register/` | 移除路由和视图函数 |

## 测试策略

| 层级 | 测试内容 | 方法 |
|------|----------|------|
| 单元测试 | `verify_wechat_code()` 函数 | Mock 微信 API 响应 |
| 单元测试 | Mock 模式返回结构 | 验证与真实 API 一致 |
| 单元测试 | 错误处理 | 覆盖所有错误码 |
| 集成测试 | 完整登录流程 | Mock 模式 |
| E2E 测试 | 真实微信扫码 | 测试环境手动验证 |

## 上线验证清单

- [ ] Mock 返回结构与真实 API 一致
- [ ] openid 格式正确（28位，以 `o` 开头）
- [ ] nickname 支持 emoji（数据库能存储）
- [ ] 错误处理完整（覆盖所有错误码）
- [ ] 超时处理正确（10秒超时返回错误）
- [ ] **测试环境真实微信扫码验证通过**

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-12
```

## Work Checklist

## 后端任务

- [x] **Task 1**: 新增 `verify_wechat_code()` 函数
  - 文件：`server/apps/core/views/index_view.py`
  - 直接查询 `LoginModule` 数据库获取 `app_id` 和 `app_secret`（不再通过 NATS 接口）
  - 调用微信 API 验证 code 并获取用户信息
  - 返回格式：`{success, openid, nickname, unionid?, headimgurl?, error?, errcode?}`

- [x] **Task 2**: 新增 `wechat_login()` 视图
  - 文件：`server/apps/core/views/index_view.py`
  - 接收 code 参数
  - 调用 `verify_wechat_code()` 验证
  - 用 openid 创建/获取用户（复用现有 nats_api 逻辑）
  - 签发 JWT token
  - 设置 cookie（使用 `_set_auth_cookie_on_response()`）

- [x] **Task 3**: 新增路由 `api/wechat_login/`
  - 文件：`server/apps/core/urls.py`
  - 添加 `re_path(r"api/wechat_login/", index_view.wechat_login)`

- [x] **Task 4**: ~~添加 `WECHAT_MOCK_MODE` 配置~~ (已移除，不需要 Mock 模式)

- [x] **Task 5**: 移除旧接口 `api/wechat_user_register/`
  - 文件：`server/apps/core/urls.py` - 移除路由 ✓
  - 文件：`server/apps/core/views/index_view.py` - 移除视图函数 ✓

- [x] **Task 10**: 禁止 NATS 接口返回 `app_secret`
  - 文件：`server/apps/system_mgmt/nats_api.py`
  - `get_wechat_settings()` 不再返回 `app_secret` 字段
  - 前端只能获取 `app_id` 和 `redirect_uri`

- [x] **Task 11**: `verify_wechat_code()` 改用数据库直接查询
  - 文件：`server/apps/core/views/index_view.py`
  - 添加 `from apps.system_mgmt.models.login_module import LoginModule`
  - 使用 `LoginModule.objects.filter(source_type="wechat", enabled=True).first()` 获取配置
  - 使用 `login_module.decrypted_app_secret` 获取解密后的 `app_secret`
  - 不再依赖 NATS 接口获取敏感信息

## 前端任务

- [x] **Task 6**: 修改 `wechat-popup-login/route.ts`
  - 文件：`web/src/app/api/wechat-popup-login/route.ts`
  - 移除微信 API 调用逻辑（getWeChatSettings, 换 access_token, 获取 userinfo）✓
  - 直接将 code 传给后端新接口 `/api/wechat_login/` ✓
  - 返回后端响应 ✓

- [x] **Task 7**: 检查并更新 `wechatProvider.ts`
  - 文件：`web/src/lib/wechatProvider.ts`
  - 修改 token 请求逻辑，调用后端 `/api/wechat_login/` 而非直接调用微信 API ✓
  - 修改 userinfo 请求逻辑，使用后端返回的数据 ✓
  - 移除 profile() 中对 `wechat_user_register` 的调用 ✓
  - 注意：clientSecret 仍在前端配置中，但不再用于 API 调用

- [x] **Task 12**: 更新 `authOptions.ts` 移除 `app_secret` 依赖
  - 文件：`web/src/constants/authOptions.ts`
  - L164: 条件检查从 `wechatConfig.app_id && wechatConfig.app_secret` 改为 `wechatConfig.app_id`
  - L168: `clientSecret` 传空字符串 `""`（不再需要，OAuth 验证已移至后端）

## 测试任务

- [x] **Task 8**: 添加单元测试
  - 文件：`server/apps/core/tests/views/test_wechat_login.py`
  - 测试 `verify_wechat_code()` 函数 ✓ (6 tests)
  - 测试 `wechat_login()` 视图 ✓ (6 tests)
  - 所有 12 个测试通过 ✓
  - 更新 mock 从 `_create_system_mgmt_client` 改为 `LoginModule` ✓

## 验证任务

- [x] **Task 9**: 测试环境真实微信扫码验证
  - 部署到测试环境
  - 使用真实微信扫码完成登录流程
  - 确认 token 和 cookie 正确设置

## 安全修复总结

### 修复前（存在漏洞）
```
前端 → NATS API (get_wechat_settings) → 返回 app_secret → 前端可获取 ❌
前端 → 直接调用微信 API（携带 app_secret）→ 敏感信息暴露 ❌
```

### 修复后（安全）
```
前端 → NATS API (get_wechat_settings) → 只返回 app_id + redirect_uri ✓
前端 → 后端 /api/wechat_login/ (只传 code) → 后端查询数据库获取 app_secret → 后端调用微信 API ✓
```

### 关键文件变更
| 文件 | 变更 |
|------|------|
| `server/apps/core/views/index_view.py` | 新增 `verify_wechat_code()`, `wechat_login()`；导入 `LoginModule`；直接查询数据库 |
| `server/apps/core/urls.py` | 新增 `api/wechat_login/` 路由；移除 `api/wechat_user_register/` |
| `server/apps/system_mgmt/nats_api.py` | `get_wechat_settings()` 不再返回 `app_secret` |
| `server/apps/core/tests/views/test_wechat_login.py` | 12 个单元测试，mock `LoginModule` |
| `web/src/app/api/wechat-popup-login/route.ts` | 简化为只传 code 到后端 |
| `web/src/lib/wechatProvider.ts` | 使用后端 `/api/wechat_login/` |
| `web/src/constants/authOptions.ts` | 移除 `app_secret` 检查，`clientSecret` 传空字符串 |
