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
