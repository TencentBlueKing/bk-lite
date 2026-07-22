# Enforce User Group Selection Rules

Status: done

## Migration Context

- Legacy source: `openspec/changes/enforce-user-group-selection-rules/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

User creation and user editing currently allow empty `group_list` values and allow users to be assigned only virtual groups, which conflicts with the intended organization model and can produce invalid user state. This change is needed now to enforce consistent group assignment rules in both backend APIs and frontend forms before more user and permission flows depend on the current lax behavior.

## What Changes

- Require user create and user update flows to reject empty group selections.
- Require user create and user update flows to include at least one non-virtual group in the selected groups.
- Continue allowing `OpsPilotGuest` to appear in the selection, but do not allow it to satisfy the required non-virtual-group constraint by itself.
- Add matching frontend validation so invalid group combinations are blocked before submission and backend validation errors are presented with localized messaging.
- Add localized validation messages in Chinese and English for empty group selection and virtual-only group selection.

## Capabilities

### New Capabilities
- `user-group-assignment-validation`: Validate user group selection rules across backend user create/update APIs and frontend user management forms, including localized error messaging.

### Modified Capabilities
- None.

## Impact

- Backend: `server/apps/system_mgmt/viewset/user_viewset.py` user creation and update endpoints.
- Backend domain model usage: `server/apps/system_mgmt/models/user.py` group virtual flag semantics.
- Frontend: user management create/edit forms and submit-time validation for selected groups.
- Localization: Chinese and English validation messages used by backend responses and frontend form feedback.

## Implementation Decisions

## Context

The current user management flow stores selected group IDs directly into `User.group_list` during create and update operations. `create_user` only validates that submitted group IDs exist, while `update_user` does not currently validate submitted groups at all. On the frontend side, invalid combinations can still be submitted because the rule that a user must belong to at least one non-virtual group is not enforced before request submission.

This change spans backend validation, frontend form behavior, and localized user-facing error messages. The rule is stricter than the current behavior: user group selection cannot be empty, and the selected groups must contain at least one non-virtual group. `OpsPilotGuest` may still be selected together with normal groups, but it must not satisfy the non-virtual-group requirement by itself.

## Goals / Non-Goals

**Goals:**
- Enforce the same group selection rule in backend user create and update flows.
- Reject empty `group_list` values for user create and update.
- Reject group selections composed entirely of virtual groups.
- Allow `OpsPilotGuest` to coexist with valid selections without treating it as a normal group.
- Add matching frontend validation so invalid selections are blocked before submission.
- Return and display localized Chinese and English validation messages consistently.

**Non-Goals:**
- Changing the semantics of `Group.is_virtual`.
- Changing login, permission, or `login_info` behavior.
- Adding validation to `assign_user_groups` or `unassign_user_groups` in this change.
- Changing group creation rules or virtual-group hierarchy behavior.

## Decisions

### 1. Centralize backend group selection validation in shared user-management logic

Both `create_user` and `update_user` need the same rule set, but they currently have inconsistent validation behavior. The backend should use one shared validation path that:
- validates all submitted group IDs exist,
- rejects an empty selection,
- loads the selected `Group` records once,
- checks whether at least one selected group has `is_virtual=False`.

This avoids duplicating business rules and prevents create/update drift.

Alternatives considered:
- Duplicate the validation in both endpoints: simpler short term, but likely to diverge again.
- Push the rule into the model `save()` path: less suitable because updates currently use queryset `.update(...)`, and the validation is request-level business behavior rather than a pure model invariant.

### 2. Treat `OpsPilotGuest` as allowed-but-not-sufficient

The business rule from this change is not "virtual groups are forbidden"; it is "a user must have at least one normal group." That means `OpsPilotGuest` may appear in the submitted selection, but a payload containing only `OpsPilotGuest` remains invalid because it still lacks a non-virtual group.

This keeps the implementation rule simple and aligned with the stated requirement:

```text
valid selection = non-empty AND contains at least one non-virtual group
```

`OpsPilotGuest` therefore needs no special pass condition in validation. It is simply one possible selected group that does not count toward the required normal-group constraint.

Alternatives considered:
- Add a hard-coded exemption allowing `OpsPilotGuest`-only selections: rejected because it conflicts with the clarified requirement that `group_list` must include one normal group.
- Forbid selecting `OpsPilotGuest` entirely: rejected because the requirement explicitly keeps it selectable.

### 3. Mirror the backend rule in the frontend, but keep the backend authoritative

The frontend should validate before submit to improve usability and reduce avoidable failed requests. However, the backend remains the source of truth because requests can bypass the UI.

Frontend validation should use the loaded group metadata to determine whether the current selection includes at least one normal group and should surface localized form-level or field-level errors before submission. Backend responses should return localized error messages for direct API usage and for any stale-client cases.

Alternatives considered:
- Backend-only validation: secure but creates poor UX because users only learn the rule after submission.
- Frontend-only validation: insufficient because API clients and stale UI flows can bypass it.

### 4. Add explicit localized messages for the two invalid states

There are two distinct invalid states with different user guidance:
- no group selected,
- only virtual groups selected.

These should use separate localized messages in Chinese and English so both API responses and frontend validation can present precise feedback.

Alternatives considered:
- Use one generic "invalid group selection" message: rejected because it is less actionable and makes frontend UX worse.

## Risks / Trade-offs

- [Frontend and backend message drift] -> Define stable message keys and reuse the same wording across both layers where practical.
- [Existing users may already have invalid group assignments] -> Scope this change to create/update validation only and avoid retroactive mutation; handle any cleanup separately if needed.
- [Frontend may not currently have enough group metadata for validation] -> Reuse existing group query data if available; if not, validate against the same dataset already used to render the selector rather than introducing a new rule source.
- [Hard-coded `OpsPilotGuest` semantics can spread further] -> Keep the implementation rule centered on "must include a non-virtual group" so `OpsPilotGuest` does not require extra branching in most code paths.

## Migration Plan

1. Add backend validation to user create and update endpoints.
2. Add localized backend error messages for empty selection and virtual-only selection.
3. Add matching frontend validation and error display in user create/edit forms.
4. Verify create/update behavior for mixed selections, normal-only selections, `OpsPilotGuest` + normal selections, empty selections, and virtual-only selections.
5. Deploy with no data migration because the change only affects future edits and creations.

Rollback strategy:
- Revert frontend validation if form behavior causes unexpected UX issues.
- Revert backend validation if the rule blocks required operational workflows, while preserving existing data.

## Open Questions

- Which frontend component owns the user create/edit group selector, and does it already receive `is_virtual` metadata directly?
- Are backend validation message keys already defined in the `system_mgmt` language resources, or do new keys need to be introduced?

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-04-28
```

## Capability Deltas

### user-group-assignment-validation

## ADDED Requirements

### Requirement: User create and update require at least one normal group
The system SHALL reject user create and user update requests when the submitted `group_list` is empty or when all selected groups are virtual groups. A valid selection MUST contain at least one existing group with `is_virtual=False`.

#### Scenario: Reject empty group selection on create
- **WHEN** a client submits a user create request with an empty `group_list`
- **THEN** the system returns a validation error indicating that at least one group must be selected

#### Scenario: Reject empty group selection on update
- **WHEN** a client submits a user update request with an empty `group_list`
- **THEN** the system returns a validation error indicating that at least one group must be selected

#### Scenario: Reject virtual-only group selection
- **WHEN** a client submits a user create or update request whose selected groups are all existing groups with `is_virtual=True`
- **THEN** the system returns a validation error indicating that at least one normal group is required

#### Scenario: Accept selection containing a normal group
- **WHEN** a client submits a user create or update request whose selected groups include at least one existing group with `is_virtual=False`
- **THEN** the system accepts the group selection if all other request validation passes

### Requirement: OpsPilotGuest can be selected but does not satisfy the normal-group requirement
The system SHALL allow `OpsPilotGuest` to appear in a user's selected groups, but `OpsPilotGuest` alone or together with other virtual groups MUST NOT satisfy the requirement that the user belong to at least one normal group.

#### Scenario: Reject OpsPilotGuest-only selection
- **WHEN** a client submits a user create or update request whose `group_list` contains only the `OpsPilotGuest` group
- **THEN** the system returns a validation error indicating that at least one normal group is required

#### Scenario: Accept OpsPilotGuest with a normal group
- **WHEN** a client submits a user create or update request whose `group_list` includes `OpsPilotGuest` and at least one existing group with `is_virtual=False`
- **THEN** the system accepts the group selection if all other request validation passes

### Requirement: Backend validation responses are localized
The system SHALL return localized validation messages in Chinese and English for invalid group selections in user create and user update flows.

#### Scenario: Localize empty-selection error
- **WHEN** a client submits an invalid empty `group_list` and the active language is Chinese or English
- **THEN** the system returns the corresponding localized message for the empty-selection validation error

#### Scenario: Localize virtual-only-selection error
- **WHEN** a client submits a virtual-only `group_list` and the active language is Chinese or English
- **THEN** the system returns the corresponding localized message for the normal-group-required validation error

### Requirement: Frontend blocks invalid group selections before submission
The user management frontend SHALL validate selected groups before submitting create or update requests and MUST block submission when no group is selected or when the selection lacks a normal group.

#### Scenario: Frontend blocks empty selection
- **WHEN** a user attempts to submit the create or edit form without selecting any group
- **THEN** the frontend prevents submission and displays the localized empty-selection validation message

#### Scenario: Frontend blocks virtual-only selection
- **WHEN** a user attempts to submit the create or edit form with only virtual groups selected
- **THEN** the frontend prevents submission and displays the localized normal-group-required validation message

#### Scenario: Frontend allows mixed selection with a normal group
- **WHEN** a user selects at least one normal group, with or without additional virtual groups, and submits the create or edit form
- **THEN** the frontend allows submission to proceed

## Work Checklist

## 1. Backend Validation

- [x] 1.1 Identify the user create and update handlers that write `group_list` and confirm the existing validation differences between them.
- [x] 1.2 Add shared backend validation for submitted group IDs so create and update both reject missing or non-existent groups consistently.
- [x] 1.3 Add backend validation that rejects empty `group_list` selections in user create and update flows.
- [x] 1.4 Add backend validation that rejects selections lacking any non-virtual group while still allowing mixed selections that include `OpsPilotGuest` plus a normal group.

## 2. Localized Error Messages

- [x] 2.1 Add Chinese and English backend message entries for the empty-group-selection validation error.
- [x] 2.2 Add Chinese and English backend message entries for the normal-group-required validation error.
- [x] 2.3 Wire the new localized messages into the backend validation response path for both create and update flows.

## 3. Frontend Validation

- [x] 3.1 Locate the user create/edit form and confirm what group metadata is available to the group selector and submit path.
- [x] 3.2 Add frontend validation that blocks submission when no group is selected.
- [x] 3.3 Add frontend validation that blocks submission when the selected groups do not include any normal group.
- [x] 3.4 Ensure the frontend accepts selections that include at least one normal group, including combinations with `OpsPilotGuest`.
- [x] 3.5 Surface localized validation feedback in the form for both invalid states and preserve backend error handling as a fallback.

## 4. Verification

- [x] 4.1 Verify backend create/update behavior for empty selections, virtual-only selections, `OpsPilotGuest`-only selections, normal-only selections, and mixed selections containing a normal group.
- [x] 4.2 Verify frontend create/edit behavior for the same selection combinations and confirm invalid submissions are blocked before request submission.
- [x] 4.3 Run the relevant module checks for the touched backend and frontend code paths and address any failures.
