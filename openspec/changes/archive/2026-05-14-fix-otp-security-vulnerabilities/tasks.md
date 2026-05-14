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
