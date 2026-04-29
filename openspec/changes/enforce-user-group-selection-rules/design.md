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
