## 1. Field Discovery Flow

- [x] 1.1 Add a creation-form field discovery helper in the grouping page that first calls `getFields()` with the existing default behavior.
- [x] 1.2 Add a fallback lookup that calls `getFields()` with an explicit wider time range when the default lookup returns an empty list.
- [x] 1.3 Ensure the wider lookup is used only by the log group creation/editing field selector and does not change global search defaults.
- [x] 1.4 Track whether fields came from default discovery, wider discovery, fallback suggestions, or manual-only mode.

## 2. Rule Label Input

- [x] 2.1 Update the rule label selector in `editInstance.tsx` to allow custom field names.
- [x] 2.2 Preserve existing validation that each condition has a field, operator, and value.
- [x] 2.3 Ensure custom field names are submitted in the existing `rule.conditions[].field` payload without requiring backend API changes.
- [x] 2.4 Add conservative common field suggestions when dynamic discovery returns no usable labels.

## 3. User Guidance

- [x] 3.1 Replace the generic empty dropdown state with guidance that manual field entry is supported.
- [x] 3.2 Show a distinct message when the wider lookup is being used or has been used.
- [x] 3.3 Show a distinct permission-related message when dynamic label discovery is blocked by log group scope.
- [x] 3.4 Add Chinese and English locale entries for the new guidance text.

## 4. Verification

- [x] 4.1 Add or update frontend tests for default labels, wider fallback labels, empty fallback suggestions, and manual custom fields if a local test harness exists for this area.
- [x] 4.2 Run `cd web && pnpm lint && pnpm type-check`.
  - Full `pnpm lint` is currently blocked by existing unrelated lint errors in CMDB, monitor dashboards, ops-analysis, and Storybook files; targeted ESLint for changed TS/TSX files passed.
  - Full `pnpm type-check` is currently blocked by existing unrelated `src/stories/monitor-disconnect-time.stories.tsx` type errors.
- [x] 4.3 Manually verify the creation modal behavior in the no-label state if a local web server can be started.
  - Dev server started on port 3002 and the target route compiled; browser access redirected to `/auth/signin`, so modal interaction was blocked by missing local login session.
- [x] 4.4 Confirm normal log search still uses the existing backend default time window.
