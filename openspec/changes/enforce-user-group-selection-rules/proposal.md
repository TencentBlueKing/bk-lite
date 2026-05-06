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
