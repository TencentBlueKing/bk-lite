## Context

当前 OTP 二阶段登录流程存在安全漏洞：

**现状问题**：
1. 后端 `get_user_login_token` 在 OTP 分支（`skip_token_for_otp=True`）返回的响应中缺少 `temporary_pwd` 字段
2. 前端 `OtpVerificationForm` 在 OTP 验证成功后没有从响应中提取 `temporary_pwd`
3. 前端 `SigninClient.handleOtpVerificationComplete` 直接调用 `completeAuthentication`，没有检查是否需要强制改密

**数据流断裂点**：
```
第一阶段响应 (OTP 分支)     第二阶段响应              前端处理
─────────────────────────  ─────────────────────  ─────────────────────
require_otp: true          token: "..."           ❌ 直接完成认证
challenge_id: "..."        temporary_pwd: true    ❌ 未提取此字段
❌ 缺少 temporary_pwd       ...                    ❌ 未检查是否需要改密
```

## Goals / Non-Goals

**Goals:**
- 确保 `temporary_pwd` 语义在 OTP 二阶段登录全流程中保持完整
- 临时密码用户在 OTP 验证成功后必须先完成改密才能进入系统
- 向后兼容：不破坏现有非临时密码用户的 OTP 登录流程

**Non-Goals:**
- 不修改 OTP 核心验证逻辑
- 不修改临时密码的生成和管理逻辑
- 不修改非 OTP 登录流程

## Decisions

### Decision 1: 后端第一阶段响应添加 temporary_pwd

**选择**: 在 `get_user_login_token` 的 OTP 分支响应中添加 `temporary_pwd: user.temporary_pwd`

**理由**: 
- 前端需要在进入 OTP 验证前就知道用户状态，以便在 OTP 成功后正确处理
- 虽然第二阶段也返回 `temporary_pwd`，但前端当前实现依赖第一阶段数据的继承
- 两阶段都返回此字段可确保数据一致性，无论前端如何实现

**替代方案考虑**:
- 仅依赖第二阶段返回：需要前端大幅重构数据流，风险更高

### Decision 2: 前端 OTP 验证后提取 temporary_pwd

**选择**: 在 `OtpVerificationForm` 中从 `responseData.data.temporary_pwd` 提取并传递

**理由**:
- 第二阶段响应已包含此字段，只需正确提取
- 保持数据来源的权威性（以服务端最新状态为准）

### Decision 3: 前端 OTP 完成回调增加改密检查

**选择**: 在 `handleOtpVerificationComplete` 中检查 `loginData.temporary_pwd`，若为 true 则跳转到 `reset-password` 步骤

**理由**:
- 与现有 `handleSubmit` 中的 `temporary_pwd` 检查逻辑保持一致
- 复用现有的 `PasswordResetForm` 组件

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 前端状态管理复杂度增加 | 复用现有 `authStep` 状态机，仅增加一个条件分支 |
| 向后兼容性 | 新增字段为可选，旧客户端不受影响 |
| 测试覆盖不足 | 新增 `temporary_pwd + enable_otp` 组合测试用例 |
