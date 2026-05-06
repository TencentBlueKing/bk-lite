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
