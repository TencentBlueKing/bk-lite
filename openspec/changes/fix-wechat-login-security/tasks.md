# Tasks: 修复微信登录安全漏洞

## 后端任务

- [x] **Task 1**: 新增 `verify_wechat_code()` 函数
  - 文件：`server/apps/core/views/index_view.py`
  - 实现 `_mock_wechat_verify()` - Mock 模式验证
  - 实现 `_real_wechat_verify()` - 真实微信 API 验证
  - 实现 `verify_wechat_code()` - 统一入口，根据配置选择模式
  - Mock 返回格式与真实 API 一致（openid 28位，支持 emoji 等）

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

- [x] **Task 4**: 添加 `WECHAT_MOCK_MODE` 配置
  - 文件：`server/config/components/base.py` 或相关配置文件
  - 添加 `WECHAT_MOCK_MODE = env.bool("WECHAT_MOCK_MODE", default=False)`

- [x] **Task 5**: 移除旧接口 `api/wechat_user_register/`
  - 文件：`server/apps/core/urls.py` - 移除路由 ✓
  - 文件：`server/apps/core/views/index_view.py` - 移除视图函数 ✓

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

## 测试任务

- [x] **Task 8**: 添加单元测试
  - 文件：`server/apps/core/tests/views/test_wechat_login.py`
  - 测试 `_mock_wechat_verify()` 函数 ✓ (8 tests)
  - 测试 `verify_wechat_code()` 函数 ✓ (4 tests)
  - 测试 `_real_wechat_verify()` 函数 ✓ (5 tests)
  - 测试 `wechat_login()` 视图 ✓ (5 tests)
  - 所有 22 个测试通过 ✓

## 验证任务

- [ ] **Task 9**: 本地 Mock 模式验证
  - 设置环境变量：`DEBUG=True`, `WECHAT_MOCK_MODE=True`
  - 启动服务：`cd server && make dev`
  - 运行验证脚本：`uv run python scripts/verify_wechat_mock.py`
  - 或手动测试：
    ```bash
    curl -X POST http://localhost:8001/api/v1/core/api/wechat_login/ \
      -H "Content-Type: application/json" \
      -d '{"code": "test_code_123"}'
    ```
  - 预期结果：返回 `{"result": true, "data": {"token": "...", "openid": "oXk8s5..."}}`

- [ ] **Task 10**: 测试环境真实微信扫码验证
  - 部署到测试环境
  - 使用真实微信扫码完成登录流程
  - 确认 token 和 cookie 正确设置
