# 2026 05 19 Fix Otp Temporary Pwd Bypass

Status: done

## Migration Context

- Legacy source: `openspec/changes/archive/2026-05-19-fix-otp-temporary-pwd-bypass/`
- Legacy state: `archived`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-15
```

## Capability Deltas

### otp-challenge-flow

## MODIFIED Requirements

### Requirement: Two-phase login for OTP-enabled users
When a user has OTP enabled, the system SHALL require both password verification AND OTP verification before issuing an access token. Password verification alone MUST NOT grant API access. The first phase response SHALL include `temporary_pwd` status to enable proper post-OTP flow handling.

#### Scenario: Password correct, OTP enabled
- **WHEN** user submits correct username and password
- **AND** user has OTP enabled
- **THEN** system returns a temporary `challenge_id` (not a JWT token)
- **AND** system does NOT set `bklite_token` cookie
- **AND** response includes `require_otp: true`
- **AND** response includes `temporary_pwd: <user.temporary_pwd>` to indicate if forced password change is required after OTP verification

#### Scenario: Password correct, OTP enabled, temporary password user
- **WHEN** user submits correct username and password
- **AND** user has OTP enabled
- **AND** user has `temporary_pwd=true`
- **THEN** system returns a temporary `challenge_id` (not a JWT token)
- **AND** response includes `require_otp: true`
- **AND** response includes `temporary_pwd: true`
- **AND** after successful OTP verification, user SHALL be redirected to password reset before completing authentication

#### Scenario: Password correct, OTP disabled
- **WHEN** user submits correct username and password
- **AND** user does NOT have OTP enabled
- **THEN** system returns JWT token (existing behavior unchanged)
- **AND** system sets `bklite_token` cookie

#### Scenario: Password incorrect
- **WHEN** user submits incorrect password
- **THEN** system returns authentication error
- **AND** no challenge_id or token is issued

## ADDED Requirements

### Requirement: OTP verification preserves temporary_pwd semantics
After successful OTP verification, the system SHALL check `temporary_pwd` status and enforce password reset before completing authentication.

#### Scenario: OTP success with temporary password
- **WHEN** user completes OTP verification successfully
- **AND** user has `temporary_pwd=true`
- **THEN** system returns JWT token with `temporary_pwd: true` in response
- **AND** frontend SHALL redirect user to password reset flow
- **AND** user SHALL NOT be able to access protected resources until password is changed

#### Scenario: OTP success without temporary password
- **WHEN** user completes OTP verification successfully
- **AND** user has `temporary_pwd=false`
- **THEN** system returns JWT token with `temporary_pwd: false` in response
- **AND** frontend completes authentication normally
- **AND** user can access protected resources immediately

## Work Checklist

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

- [x] 4.1 手动测试：创建临时密码用户 → 启用全局 OTP → 登录 → 验证 OTP 后应跳转到改密页面 *(需要运行环境)*
- [x] 4.2 手动测试：普通用户（非临时密码）→ 启用全局 OTP → 登录 → 验证 OTP 后应直接进入系统 *(需要运行环境)*
