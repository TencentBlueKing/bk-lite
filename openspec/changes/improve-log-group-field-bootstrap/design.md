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
