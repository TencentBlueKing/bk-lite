## 1. Backend State and Summary Semantics

- [x] 1.1 Audit existing controller install result shapes for remote success, remote failure, no installer events, partial installer events, installer step failure, connectivity success, and connectivity timeout.
- [x] 1.2 Align installer expected-step semantics so backend summary and frontend progress use one user-facing count.
- [x] 1.3 Add or derive a stable display state for controller install progress, covering success, running, no-report, installer failure, command failure, and connectivity failure.
- [x] 1.4 Ensure `no_installer_events` plus connectivity timeout produces a clear no-report/connectivity failure reason.
- [x] 1.5 Preserve compatibility for historical task results that only contain legacy `steps`.
- [x] 1.6 Add backend tests for no-report running, no-report timeout, success without detail, installer step failure, complete success, and duplicated-event diagnostics.

## 2. Frontend State Derivation

- [x] 2.1 Add a shared frontend utility that derives the four user-facing phases from normalized controller install result data.
- [x] 2.2 Use the shared utility in both the install progress table and log drawer.
- [x] 2.3 Distinguish `下发安装命令` from `安装器执行` in display labels and state tags.
- [x] 2.4 Render `安装器无回报` / `等待安装器回报` as explicit states when no installer events are present after command dispatch.
- [x] 2.5 Show `success_without_detail` as success with a low-severity note instead of a failure.
- [x] 2.6 Keep duplicated-event counts in diagnostics instead of primary success UI.

## 3. User Copy and Guidance

- [x] 3.1 Add Chinese and English i18n strings for the four phases.
- [x] 3.2 Add Chinese and English i18n strings for installer waiting, installer no-report, success without detail, and no-report timeout.
- [x] 3.3 Add phase-specific next-action guidance for credential failure, command failure, installer no-report, installer step failure, and connectivity timeout.
- [x] 3.4 Replace default `0/6` missing-step display with `安装器步骤：未收到` when no installer events exist.
- [x] 3.5 Only show explicit missing installer step names when at least one installer event has been received.

## 4. UI Verification

- [x] 4.1 Add or update frontend tests for table status rendering across success, running, no-report, installer failure, and connectivity timeout.
- [x] 4.2 Add or update frontend tests for log drawer phase rendering and nested installer detail steps.
- [ ] 4.3 Manually verify the successful screenshot case shows clean success and hides duplicated-event diagnostics by default.
- [ ] 4.4 Manually verify the no-step screenshot case shows `安装器无回报` or `等待安装器回报` instead of a misleading completed installer step.
- [ ] 4.5 Run `cd web && pnpm lint && pnpm type-check` for frontend changes.
  - Targeted eslint for changed node-manager files passed. `NEXTAPI_INSTALL_APP=node-manager pnpm precommit && pnpm exec tsc -p tsconfig.lint.json --noEmit` passed.
  - Full `pnpm lint` is currently blocked by pre-existing cmdb/log/monitor/storybook lint errors unrelated to this change.
  - Full `pnpm type-check` is currently blocked by pre-existing `opspilot` message payload type errors unrelated to this change.

## 5. Server Verification

- [x] 5.1 Run targeted node_mgmt installer summary tests.
- [x] 5.2 Run `cd server && make test` or the narrowest reliable node_mgmt test command if full tests are blocked by environment dependencies.
