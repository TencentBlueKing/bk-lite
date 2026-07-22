# Improve Log Group Field Bootstrap

Status: done

## Migration Context

- Legacy source: `openspec/changes/improve-log-group-field-bootstrap/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

Log group permissions intentionally gate log search. When the current organization has no accessible log groups, search and dynamic field discovery can return "current organization has no available log group permission"; that is the correct data boundary.

The log group creation page currently loads rule labels from `/log/collect_types/all_attrs/` during page initialization. That endpoint uses recent log field discovery and the same log group access scope. If the recent window has no matching logs, or if the user is creating the first usable group, the label dropdown can show only a generic empty state. Users then have no clear way to author the rule fields needed to create a group.

Creation-time label discovery has a different permission question than log search. Search and normal field discovery read data through existing log groups and must validate log group instance access. The create form is used before a log group may exist, so it should not require existing log group instance permission. It still must require organization-level permission to create/bind log groups so metadata is not exposed to users who cannot manage the organization.

## Goals / Non-Goals

**Goals:**
- Improve the log group creation form so label discovery is helpful but not blocking.
- Use a wider creation-only field discovery time window when the default recent lookup returns no labels.
- Allow manual field entry when dynamic labels are unavailable.
- Provide common log field suggestions as fallback options.
- Keep search and analytics default time windows unchanged.
- Keep existing log group permission checks unchanged.
- Do not require existing log group instance permission for creation-time label suggestions.
- Preserve organization-level create/bind permission checks for creation-time label suggestions.

**Non-Goals:**
- Do not grant log group permission automatically when a new organization is created.
- Do not bypass `LogAccessScopeService` for log search or normal field discovery.
- Do not expose creation-time labels to users who lack log group create/bind organization permission.
- Do not change the global `DEFAULT_TIME_WINDOW_MINUTES` used by shared search service methods.
- Do not introduce a new external dependency or data model.

## Decisions

1. **Add creation-scope field discovery**

   The backend will expose a creation-specific field discovery mode, either through a query parameter on `/log/collect_types/all_attrs/` or a dedicated action. That mode checks whether the user has manageable organizations for `log_group` via `LogAccessScopeService.get_manageable_organization_ids(request)`. It must not call `resolve_scope()` or require existing log group IDs.

   The query used for this mode should be constrained to the current manageable organization context if the log storage exposes an organization field. If the implementation cannot safely constrain by organization, it should return no dynamic labels and let the frontend use manual entry and fallback suggestions.

   Alternative considered: reuse normal `all_attrs` with empty `log_groups`. Rejected because it calls `resolve_scope()` and intentionally fails when no accessible log group exists.

2. **Use frontend-controlled wider lookup for creation only**

   The grouping page will continue to call `getFields()` for initial label discovery. If the result is empty, it will retry `getFields({ start_time, end_time })` with a wider window such as the last 24 hours. This keeps the backend default window stable for search and statistics.

   Alternative considered: change `DEFAULT_TIME_WINDOW_MINUTES` from 15 minutes to 24 hours. Rejected because that would affect search, hits, top stats, and other paths that share `SearchService._apply_default_time_window`.

3. **Manual input is a supported creation path**

   The rule label control in the add/edit modal will support custom field names. Dynamic labels remain suggestions, not the source of truth. Validation should require a non-empty field value, operator, and rule value; it should not require the field to exist in the discovered options.

   Alternative considered: require users to create logs first and refresh labels. Rejected because it keeps the first-log-group flow brittle and makes "No Data" the user's problem.

4. **Fallback suggestions are static and conservative**

   When dynamic discovery is empty or fails, the UI will include common fields such as `_stream`, `host.name`, `service.name`, `container.name`, `kubernetes.namespace`, and `log.file.path`. These are suggestions only; users can still type other fields.

5. **Permission errors stay explicit**

   If normal field discovery fails because the current organization has no accessible log group permission, the UI should not present it as ordinary empty data. For creation-time discovery, lack of organization-level create/bind permission should be shown as a permission state; lack of existing log group instance permission should not block manual field entry.

## Risks / Trade-offs

- Wider field discovery could be slower on large log stores -> Limit it to creation-time fallback and only retry after the default lookup returns no labels.
- Manual field entry can accept typos -> Keep field validation lightweight but make custom entries visually clear; the backend already evaluates rules against actual logs later.
- Static suggestions may not match every deployment -> Treat them as hints, not hidden defaults or required fields.
- Permission errors and empty results can look similar -> Preserve different user-facing messages so "no permission" is not mistaken for "no logs".
- Creation-scope field discovery might accidentally broaden metadata access -> Gate it on organization-level log group manageability and return no dynamic labels if organization-safe log filtering is unavailable.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-16
```

## Capability Deltas

### log-group-field-bootstrap

## ADDED Requirements

### Requirement: Creation-time field discovery uses a wider fallback window
The system SHALL keep the shared default log query window unchanged, but the log group creation experience SHALL retry dynamic field discovery with a wider creation-only time window when the default discovery returns no fields.

#### Scenario: Default discovery returns fields
- **WHEN** a user opens the log group creation form and default field discovery returns one or more fields
- **THEN** the form SHALL display those fields without issuing a wider fallback lookup

#### Scenario: Default discovery returns no fields
- **WHEN** a user opens the log group creation form and default field discovery returns no fields
- **THEN** the form SHALL retry field discovery with an explicit wider time range for the creation form
- **AND** the shared default search window SHALL remain unchanged for normal log search and analytics queries

### Requirement: Creation-time field discovery does not require existing log group instance access
The system SHALL allow the log group creation form to request field suggestions without requiring the user to already have access to an existing log group instance, while still requiring organization-level permission to create or bind log groups.

#### Scenario: User has manageable organization but no accessible log group instance
- **WHEN** a user has organization-level permission to create or bind log groups
- **AND** the user has no existing accessible log group instances
- **THEN** creation-time field discovery SHALL NOT fail because of missing log group instance access

#### Scenario: User lacks organization-level create or bind permission
- **WHEN** a user lacks organization-level permission to create or bind log groups
- **THEN** creation-time field discovery SHALL return a permission error or no dynamic labels
- **AND** the system SHALL NOT expose dynamic log field metadata from unauthorized organizations

#### Scenario: Normal field discovery remains scoped by log group permission
- **WHEN** a user performs normal log field discovery outside the log group creation form
- **THEN** the system SHALL continue to enforce existing log group scope validation

### Requirement: Rule labels support manual field entry
The log group rule label control SHALL allow users to enter custom field names even when dynamic field discovery returns no fields.

#### Scenario: User enters custom field
- **WHEN** dynamic field suggestions are empty and the user types a field name into the rule label control
- **THEN** the form SHALL accept the custom field value as the rule field

#### Scenario: Rule validation checks required parts
- **WHEN** a user submits a log group rule
- **THEN** validation SHALL require each condition to include a non-empty field, operator, and value
- **AND** validation SHALL NOT require the field to be present in dynamic field suggestions

### Requirement: Empty label states are actionable
The log group creation form SHALL distinguish between empty dynamic field results and permission-blocked creation-time field discovery, and SHALL provide actionable guidance instead of only showing a generic no-data state.

#### Scenario: Wider discovery returns no fields
- **WHEN** both the default and wider field discovery calls return no fields
- **THEN** the label control SHALL show fallback common field suggestions
- **AND** the UI SHALL tell the user that no recommended labels were found and that manual field entry is available

#### Scenario: Creation-time field discovery is permission-blocked
- **WHEN** creation-time field discovery fails because the user lacks organization-level log group create or bind permission
- **THEN** the UI SHALL explain that dynamic labels cannot be loaded from authorized log data
- **AND** the user SHALL still be able to manually enter a rule field in the creation form

### Requirement: Common field suggestions are available as fallback
The log group creation form SHALL provide conservative common log field suggestions when dynamic discovery cannot provide labels.

#### Scenario: Fallback suggestions are displayed
- **WHEN** dynamic field discovery returns no usable labels or is unavailable
- **THEN** the label control SHALL include common field suggestions such as `_stream`, `host.name`, `service.name`, `container.name`, `kubernetes.namespace`, and `log.file.path`

## Work Checklist

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
