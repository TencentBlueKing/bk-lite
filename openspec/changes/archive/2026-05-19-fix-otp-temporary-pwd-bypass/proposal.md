## Why

OTP 二阶段登录流程中丢失了 `temporary_pwd` 语义，导致临时密码用户可以绕过强制改密直接完成登录。这是一个安全漏洞，影响所有启用 OTP 的环境中的临时密码用户。

Issue: https://github.com/TencentBlueKing/bk-lite/issues/2981

## What Changes

- **后端**: OTP 第一阶段响应添加 `temporary_pwd` 字段，确保前端在进入 OTP 验证前能感知用户是否需要强制改密
- **前端**: OTP 验证完成后从响应中提取 `temporary_pwd`，并在完成认证前检查是否需要跳转到改密流程
- **测试**: 添加 `temporary_pwd + enable_otp` 组合场景的测试覆盖

## Capabilities

### New Capabilities

（无新增能力）

### Modified Capabilities

- `otp-challenge-flow`: 第一阶段响应需包含 `temporary_pwd` 字段，OTP 验证成功后需检查 `temporary_pwd` 决定是否进入改密流程

## Impact

- **后端 API**: `get_user_login_token` 函数的 OTP 分支响应结构变更（新增字段，向后兼容）
- **前端组件**: 
  - `SigninClient.tsx` - OTP 完成回调需增加 `temporary_pwd` 检查
  - `OtpVerificationForm.tsx` - 需从第二阶段响应提取 `temporary_pwd`
- **测试**: 需新增 OTP + 临时密码组合场景的端到端测试
