# Tasks: 修复微信登录安全漏洞

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
