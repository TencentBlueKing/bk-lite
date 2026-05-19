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
