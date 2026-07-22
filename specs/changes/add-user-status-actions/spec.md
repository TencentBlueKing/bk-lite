# Add User Status Actions

Status: done

## Migration Context

- Legacy source: `openspec/changes/add-user-status-actions/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

当前用户管理页已经具备禁用、锁定、密码有效期相关的底层数据基础，但列表接口和页面交互还没有把这些状态收敛成统一的管理能力。随着用户管理需求细化，系统需要在不新增数据库状态字段的前提下，为用户列表提供一致的状态展示、状态驱动操作和批量状态处理能力。

## What Changes

- 为用户列表引入派生 `status` 能力，按统一优先级对 `disabled`、锁定窗口和密码到期进行状态归并。
- 为用户管理后端新增统一 `change_status` 接口，支持 `enable`、`disable`、`unlock` 三类单条与批量状态动作。
- 为用户管理前端接入状态列、按状态变化的行内操作，以及“批量操作”下拉菜单。
- 保持现有数据库模型不变，不新增持久化 `status` 字段。
- 密码到期状态沿用系统现有的判定规则，不要求在本次变更中额外扩展到其他既有流程的结构调整。
- 保持现有 `search_user_list` 可见范围语义不变，不处理禁用后在线会话失效逻辑。

## Capabilities

### New Capabilities
- `user-status-management`: Covers derived user status calculation, unified user status change actions, and user management UI behaviors driven by status.

### Modified Capabilities

## Impact

- Affected backend code: `server/apps/system_mgmt/serializers/user_serializer.py`, `server/apps/system_mgmt/viewset/user_viewset.py`
- Affected frontend code: `web/src/app/system-manager/types/user.ts`, `web/src/app/system-manager/api/user/index.ts`, `web/src/app/system-manager/hooks/useUserStructure.ts`, `web/src/app/system-manager/components/user/tableColumns.tsx`, `web/src/app/system-manager/(pages)/user/structure/page.tsx`
- Affected APIs: `/system_mgmt/user/search_user_list/`, `/system_mgmt/user/get_user_detail/`, new `/system_mgmt/user/change_status/`
- Existing unrelated flows remain structurally unchanged in this change.
- No new dependencies and no database schema changes

## Implementation Decisions

## Context

当前仓库已经具备用户禁用、锁定和密码有效期的底层数据与安全配置能力：`User.disabled`、`User.account_locked_until`、`User.password_error_count`、`User.password_last_modified` 以及密码有效期相关系统设置均已存在。但用户管理接口和页面仍直接暴露原始字段，没有形成统一的管理状态模型，导致用户列表无法稳定展示状态，也无法基于状态提供单条和批量操作。

这次变更横跨 Django 用户管理接口与 Next.js 系统管理页面，既要补齐后端契约，也要保持当前系统边界不变：不新增数据库 `status` 字段，不修改 `search_user_list` 现有可见范围语义，不引入禁用后立即踢在线会话的新行为。

## Goals / Non-Goals

**Goals:**
- 为用户列表和详情提供统一的派生 `status` 返回值。
- 提供统一的 `change_status` 接口，支持 `enable`、`disable`、`unlock` 的单条与批量处理。
- 让前端用户管理页按状态显示行内操作和批量操作入口。
- 保持状态规则在后端集中定义，避免前后端重复推导。
- 在满足需求的前提下保持最小改动，不为本次变更额外扩展到无关流程重构。

**Non-Goals:**
- 不新增或持久化数据库 `status` 字段。
- 不修改 `search_user_list` 的现有可见范围过滤语义。
- 不新增独立权限点，继续复用 `user_group-Edit User`。
- 不处理禁用后立即使在线用户会话失效。
- 不扩展“密码到期”的动作集合，密码到期仍通过现有密码重置流程处理。
- 不要求将其他既有流程中的密码到期判断额外重构为统一 helper。

## Decisions

### 1. `status` 作为后端派生字段返回

后端在用户序列化阶段统一计算 `status`，而不是新增数据库字段，也不让前端自行推导。

选择原因：
- 状态依赖多个原始字段与系统设置，属于派生视图而非持久事实。
- 后端集中计算可以避免前端重复实现状态优先级、时间判断和配置依赖。
- 不新增数据库字段可以保持现有数据模型和迁移成本不变。
- 本次只约束用户管理接口中的派生状态行为，不要求顺带调整其他既有流程的实现结构。

备选方案：
- 新增数据库 `status` 字段：会引入冗余状态与同步问题，被拒绝。
- 前端自行推导：会造成规则散落在 UI 层，且难以与现有密码到期判定规则保持一致，被拒绝。

### 2. 状态优先级固定为 `disabled > locked > password_expired > normal`

用户状态按短路顺序派生：
- `disabled = true` → `disabled`
- `account_locked_until > now` → `locked`
- `password_last_modified` 有值且 `pwd_set_validity_period > 0`，并且到期时间不晚于当前时间 → `password_expired`
- 其他情况 → `normal`

补充规则：
- `password_last_modified` 为空时，不参与密码到期判断。
- `pwd_set_validity_period <= 0` 时，不参与密码到期判断。

选择原因：
- 与已对齐的产品规则一致。
- 与现有代码中“密码最后修改时间为空时不做过期判断”的隐含行为一致。
- 与前端安全设置中 `0 = permanent` 的现有配置语义一致。

### 3. 使用统一 `change_status` action 承载状态动作

后端新增 `POST /system_mgmt/user/change_status/`，入参为 `user_ids` 和 `action`，支持 `enable`、`disable`、`unlock`。

选择原因：
- 状态动作和 `update_user` 的资料编辑职责不同，单独接口更清晰。
- 单条和批量可以共用同一套权限校验、适用性校验和返回结构。
- 比拆多个 enable/disable/unlock 接口更容易维护与扩展。

备选方案：
- 将状态动作并入 `update_user`：会混合资料编辑和状态动作，增加请求结构与校验复杂度，被拒绝。
- 拆成多个单独接口：接口数量更多，批量和单条逻辑容易重复，未采用。

### 4. 批量操作采用“部分成功”策略

`change_status` 在请求格式合法时始终执行逐用户处理：
- 适用的用户执行状态变更。
- 不适用、无权限或不存在的用户跳过，并返回原因。

返回结构包含 `action`、`total`、`success_ids`、`skipped`。

选择原因：
- 与需求中“仅对适用账号生效”的描述一致。
- 更适合用户管理页的批量操作反馈。
- 避免因为单个异常目标导致整批不可用。

### 5. 保持现有登录与会话语义

`disable` 只修改 `disabled = true`，不清理锁定状态，也不主动使在线会话失效。
`enable` 只修改 `disabled = false`，不自动解锁。
`unlock` 只清理 `account_locked_until` 和 `password_error_count`。

选择原因：
- 与已对齐的边界一致，避免在本次需求中引入额外安全语义变更。
- 保持字段职责清晰，让派生状态自然反映底层事实。

## Risks / Trade-offs

- [密码到期行为偏差] → 如果列表 `status` 的密码到期判定偏离系统现有规则，会出现管理页与其他既有流程的行为不一致。本次需要复用现有判定规则，但不要求把相关流程重构为同一个 helper。
- [批量结果反馈复杂度增加] → 前端需要处理部分成功和跳过原因，而不是单一成功/失败提示。通过统一返回结构和有限 reason 枚举降低复杂度。
- [保持现有列表可见范围语义] → 本次不调整 `search_user_list` 的可见范围过滤，意味着潜在的历史权限边界问题不会在此次变更中修正。通过在设计中明确保持现状，避免实现阶段误扩范围。
- [禁用与锁定并存] → `disable` 不清锁定状态，启用后用户可能重新显示为锁定。这是有意保留的字段事实语义，需要在前后端实现和验收中明确作为预期行为。

## Migration Plan

- 后端先补派生 `status` 与 `change_status`，保持现有接口兼容，仅新增返回字段和新增 action。
- 前端接入新返回字段与新接口，替换用户页上的固定动作和批量删除入口。
- 若上线后需要回滚，可直接回退前后端代码版本；由于没有数据库 schema 变更，无需执行数据迁移回退。

## Open Questions

- 无。当前实现边界、状态规则、权限模型和批量语义均已在变更准备阶段完成对齐。

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-05-15
```

## Capability Deltas

### user-status-management

## ADDED Requirements

### Requirement: User APIs SHALL expose a derived management status
The system SHALL expose a derived `status` value in user management API responses without persisting a separate database `status` field. The derived value SHALL follow the priority order `disabled > locked > password_expired > normal`.
The `password_expired` classification in user management APIs SHALL remain consistent with the system's existing configured password-expiry rules.

#### Scenario: Disabled user status takes precedence over all other conditions
- **WHEN** a user has `disabled = true`, regardless of lock state or password expiry state
- **THEN** the user management API SHALL return `status = "disabled"`

#### Scenario: Locked user status is returned when the account is not disabled
- **WHEN** a user has `disabled = false` and `account_locked_until` is later than the current time
- **THEN** the user management API SHALL return `status = "locked"`

#### Scenario: Password-expired status is returned when password validity has elapsed
- **WHEN** a user has `disabled = false`, is not currently locked, `password_last_modified` has a value, `pwd_set_validity_period > 0`, and `password_last_modified + pwd_set_validity_period` is not later than the current time
- **THEN** the user management API SHALL return `status = "password_expired"`

#### Scenario: Normal status is returned when no higher-priority state applies
- **WHEN** a user is not disabled, is not currently locked, and is not password-expired under the configured validity rules
- **THEN** the user management API SHALL return `status = "normal"`

#### Scenario: Missing password modification time does not produce password-expired status
- **WHEN** a user has no `password_last_modified` value and is neither disabled nor locked
- **THEN** the user management API SHALL NOT classify the user as `password_expired`

#### Scenario: Non-positive validity period disables password-expired classification
- **WHEN** `pwd_set_validity_period` is less than or equal to `0` and a user is neither disabled nor locked
- **THEN** the user management API SHALL NOT classify the user as `password_expired`

### Requirement: User management SHALL support unified status change actions
The system SHALL provide a unified user status change API that accepts one or more user IDs and an action of `enable`, `disable`, or `unlock`.

#### Scenario: Enable action clears only the disabled flag
- **WHEN** the unified status change API receives `action = "enable"` for a disabled user
- **THEN** the system SHALL set `disabled = false`
- **THEN** the system SHALL NOT clear lock state as part of the enable action

#### Scenario: Disable action sets only the disabled flag
- **WHEN** the unified status change API receives `action = "disable"` for a non-disabled user
- **THEN** the system SHALL set `disabled = true`
- **THEN** the system SHALL NOT clear lock state as part of the disable action

#### Scenario: Unlock action clears the active lock state
- **WHEN** the unified status change API receives `action = "unlock"` for a currently locked user
- **THEN** the system SHALL set `account_locked_until = null`
- **THEN** the system SHALL reset `password_error_count` to `0`

#### Scenario: Unified status change requires edit-user permission
- **WHEN** the caller does not have `user_group-Edit User` permission
- **THEN** the system SHALL deny access to the unified status change API

### Requirement: Batch status changes SHALL support partial success
The unified status change API SHALL process batch requests per user and SHALL allow valid targets to succeed even when other targets are skipped.

#### Scenario: Batch request succeeds for applicable users and skips inapplicable users
- **WHEN** the unified status change API receives a valid request containing a mix of applicable and inapplicable users
- **THEN** the system SHALL apply the requested action to each applicable user
- **THEN** the system SHALL skip each inapplicable user without failing the entire request

#### Scenario: Batch response reports successful and skipped users separately
- **WHEN** the unified status change API completes a batch request
- **THEN** the response SHALL include the requested action, the total number of requested users, the successful user IDs, and the skipped users with reasons

#### Scenario: Enable skips users that are not currently disabled
- **WHEN** the unified status change API receives `action = "enable"` for a user that is not disabled
- **THEN** the system SHALL skip that user and return a reason indicating the user is not disabled

#### Scenario: Disable skips users that are already disabled
- **WHEN** the unified status change API receives `action = "disable"` for a user that is already disabled
- **THEN** the system SHALL skip that user and return a reason indicating the user is already disabled

#### Scenario: Unlock skips users that are not currently locked
- **WHEN** the unified status change API receives `action = "unlock"` for a user whose lock window is not active
- **THEN** the system SHALL skip that user and return a reason indicating the user is not locked

### Requirement: User management UI SHALL present status-driven actions
The user management UI SHALL display the derived status and SHALL present row and batch actions that align with the current user state.

#### Scenario: User list displays the derived status
- **WHEN** the user management page loads user records
- **THEN** the user list SHALL display a status column based on the derived `status` value returned by the backend

#### Scenario: Normal users expose disable and delete actions
- **WHEN** a user row has `status = "normal"`
- **THEN** the UI SHALL present `edit`, `password`, `disable`, and `delete` actions for that row

#### Scenario: Disabled users expose enable and delete actions
- **WHEN** a user row has `status = "disabled"`
- **THEN** the UI SHALL present `edit`, `password`, `enable`, and `delete` actions for that row

#### Scenario: Locked users expose unlock and disable actions
- **WHEN** a user row has `status = "locked"`
- **THEN** the UI SHALL present `edit`, `password`, `unlock`, `disable`, and `delete` actions for that row

#### Scenario: Password-expired users expose disable and delete actions
- **WHEN** a user row has `status = "password_expired"`
- **THEN** the UI SHALL present `edit`, `password`, `disable`, and `delete` actions for that row

#### Scenario: Batch operation menu exposes all supported bulk actions
- **WHEN** one or more users are selected in the user management page
- **THEN** the UI SHALL provide a batch operation entry that includes `batch enable`, `batch disable`, `batch unlock`, and `batch delete`

#### Scenario: Batch operation feedback supports partial success
- **WHEN** a batch status change completes with both successful and skipped users
- **THEN** the UI SHALL present feedback that distinguishes successful updates from skipped users

## Work Checklist

## 1. Backend status derivation

- [x] 1.1 Add a reusable derived user status helper based on `disabled > locked > password_expired > normal`
- [x] 1.2 Update user serialization to return the derived `status` field in user management responses
- [x] 1.3 Ensure password-expired derivation treats missing `password_last_modified` as not expired
- [x] 1.4 Ensure password-expired derivation treats `pwd_set_validity_period <= 0` as not expired
- [x] 1.5 Ensure derived `password_expired` status follows the system's existing password-expiry rules
- [x] 1.6 Scope: no helper refactoring of unrelated existing flows is required

## 2. Backend unified status action API

- [x] 2.1 Add `change_status` to `UserViewSet` as a `POST` action under `/system_mgmt/user/change_status/`
- [x] 2.2 Validate request shape for `user_ids` and `action`
- [x] 2.3 Reuse `user_group-Edit User` permission for the new action
- [x] 2.4 Apply `enable` by clearing only the `disabled` flag for applicable users
- [x] 2.5 Apply `disable` by setting only the `disabled` flag for applicable users
- [x] 2.6 Apply `unlock` by clearing `account_locked_until` and resetting `password_error_count` for applicable users
- [x] 2.7 Return partial-success results with `action`, `total`, `success_ids`, and `skipped` reasons
- [x] 2.8 Add operation logging for status changes

## 3. Frontend user management integration

- [x] 3.1 Extend user management frontend types to include the derived `status`
- [x] 3.2 Add a `changeUserStatus` API helper in the user API module
- [x] 3.3 Update the user management hook to consume backend `status` values
- [x] 3.4 Update the user management hook to execute single-user status changes and refresh the list
- [x] 3.5 Update the user management hook to execute batch status changes and surface partial-success feedback
- [x] 3.6 Add a status column to the user management table
- [x] 3.7 Render row actions conditionally for `normal`, `disabled`, `locked`, and `password_expired`
- [x] 3.8 Replace the current batch delete entry with a batch operation menu containing enable, disable, unlock, and delete

## 4. Localization and verification

- [x] 4.1 Add user status and status-action localization strings needed by the updated UI
- [x] 4.2 Add or update backend tests covering derived status and unified status action behavior
- [x] 4.3 Verify single-user and mixed batch status changes against the aligned rules
- [x] 4.4 Run `cd server && make test`
- [x] 4.5 Verify the web user-management changes with the accepted frontend checks for the current environment (including the TypeScript check path used on Windows)
