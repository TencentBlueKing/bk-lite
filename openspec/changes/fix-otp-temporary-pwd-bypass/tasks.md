## 1. 后端修复

- [x] 1.1 在 `server/apps/system_mgmt/nats_api.py` 的 `get_user_login_token` 函数中，OTP 分支响应（约 line 1398-1407）添加 `"temporary_pwd": user.temporary_pwd` 字段
- [x] 1.2 验证 `verify_otp_login` 函数（约 line 1316-1327）已正确返回 `temporary_pwd`（当前已有，确认无需修改）

## 2. 前端修复

- [x] 2.1 在 `web/src/app/(core)/auth/signin/OtpVerificationForm.tsx` 的 `handleOtpVerification` 函数中（约 line 72-82），从 `responseData.data.temporary_pwd` 提取并添加到 `verifiedLoginData` 对象
- [x] 2.2 在 `web/src/app/(core)/auth/signin/SigninClient.tsx` 的 `handleOtpVerificationComplete` 函数中（约 line 343-345），添加 `temporary_pwd` 检查逻辑：若为 true 则设置 `authStep` 为 `'reset-password'` 并 return，否则继续调用 `completeAuthentication`

## 3. 测试

- [x] 3.1 在 `server/apps/system_mgmt/tests/test_otp_login_flow.py` 中添加测试用例：`temporary_pwd=True` + `enable_otp=True` 组合场景，验证第一阶段响应包含 `temporary_pwd: true`
- [x] 3.2 在 `server/apps/system_mgmt/tests/test_otp_login_flow.py` 中添加测试用例：OTP 验证成功后响应包含正确的 `temporary_pwd` 值
- [x] 3.3 运行 `cd server && make test` 确保所有测试通过

## 4. 验证

- [ ] 4.1 手动测试：创建临时密码用户 → 启用全局 OTP → 登录 → 验证 OTP 后应跳转到改密页面 *(需要运行环境)*
- [ ] 4.2 手动测试：普通用户（非临时密码）→ 启用全局 OTP → 登录 → 验证 OTP 后应直接进入系统 *(需要运行环境)*
