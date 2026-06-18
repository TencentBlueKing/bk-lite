## Why

Users can legitimately have no available log group permission in the current organization, which should continue to block log search. However, the log group creation form currently depends on the same recent-log field discovery path, so users can hit an empty label selector while trying to create or bootstrap a log group.

This creates a confusing first-use experience: the permissions boundary is correct, but the creation form looks broken because it only says there is no data and offers no practical fallback.

## What Changes

- Keep the existing log search permission boundary unchanged when the current organization has no accessible log groups.
- Improve the log group creation form's label/field discovery flow:
  - First attempt to load labels using the existing default recent time window.
  - If no labels are discovered, retry with a wider creation-only time window.
  - Do not require existing log group instance permission when loading labels for the create form.
  - Keep organization-level create/bind permission checks for creation-time label discovery.
  - If labels are still unavailable or discovery is blocked, allow users to manually enter a field name.
  - Present a clearer empty-state message that explains manual field entry instead of only showing "No Data".
- Provide a small set of common log field suggestions as a fallback when dynamic discovery returns no labels.
- Avoid changing the global default search window used by log search, hit statistics, or dashboard queries.

## Capabilities

### New Capabilities
- `log-group-field-bootstrap`: Covers log group creation-time label discovery, wider fallback lookup, and manual field entry behavior.

### Modified Capabilities

## Impact

- Frontend:
  - `web/src/app/log/(pages)/integration/grouping/page.tsx`
  - `web/src/app/log/(pages)/integration/grouping/editInstance.tsx`
  - log locale files for improved empty-state/help text
- Backend:
  - Add or adjust a creation-specific field discovery path that checks log group create/bind organization permission without requiring existing log group instance permission.
  - Keep existing log search and normal field discovery permission checks unchanged.
- APIs:
  - Existing `/log/collect_types/all_attrs/` may be reused with explicit `start_time` and `end_time` for normal scope.
  - A creation-specific query parameter or endpoint may be added for log group form label discovery.
  - No breaking API changes.
