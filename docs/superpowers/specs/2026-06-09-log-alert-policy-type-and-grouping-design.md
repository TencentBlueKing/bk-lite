# Log Alert Policy Type Selection and Grouping Design

## Context

The current log alert policy flow is usable but hard to extend:

- Policy type is selected inside the create form.
- Keyword alerts cannot split alerts by log fields.
- Alert names do not consistently support dynamic variables.

This change keeps the implementation small. It improves the create entry and adds keyword grouping without restructuring the whole policy editor.

## Goals

- Move policy type selection before entering the create form.
- Keep policy type immutable after creation.
- Add optional grouping fields to keyword alert policies.
- Preserve existing keyword behavior when no grouping field is configured.
- Support alert name variables with `${level}` and `${log.fieldName}`.
- Add a log preview area that reuses the existing log search behavior.

## Non-Goals

- No database migration.
- No full rewrite into separate physical pages per strategy type.
- No change to the existing notification model.
- No change to the log preview time-window semantics.

## Frontend Design

The strategy list page keeps the existing table, search, enable switch, edit, and delete behavior.

Clicking Add opens a "select policy type" modal. The modal offers:

- Keyword Alert
- Aggregate Rule Alert

After selecting a type, the app navigates to the existing strategy detail page with the selected type in the URL, for example:

```text
/log/event/strategy/detail?type=add&alert_type=keyword
/log/event/strategy/detail?type=add&alert_type=aggregate
```

The create form initializes `alert_type` from the URL and does not render the in-form policy type selector. Editing loads the type from policy detail and also does not allow changing it.

The existing form components remain the base:

- `BasicInfoForm`
- `AlertConditionsForm`
- `NotificationForm`

`AlertConditionsForm` becomes type-aware:

- Keyword alert: query, display fields, optional grouping fields, frequency, period, level.
- Aggregate alert: query, display fields, optional grouping fields, rule, frequency, period, level.

Display fields default to `timestamp` and `message`.

## Alert Name Variables

Alert name supports variables:

- `${level}` is always available.
- `${log.fieldName}` is available for configured grouping fields.

The right-side variable panel lists available variables and provides a "use" action. Clicking it inserts the variable into the alert name input at the cursor position. If cursor position is unavailable, it appends the variable to the end.

The variable format is always `${...}`. Log field variables use the full log field name, such as `${log.service.name}`.

## Log Preview

The right side of the form includes a log preview area.

- If query is empty, show guidance instead of querying.
- If query is present and log groups are selected, call the existing log search API with `limit=10`.
- Keep the existing search default time window.
- Render columns from selected display fields, defaulting to `timestamp` and `message`.
- Empty results show an empty state.

## Backend Data Model

No database schema changes are required.

Policy data continues to use existing fields:

- `Policy.alert_type`
- `Policy.alert_name`
- `Policy.alert_condition`
- `Policy.show_fields`
- `Policy.schedule`
- `Policy.period`

`alert_condition` stores shared alert-condition data:

```json
{
  "query": "error",
  "group_by": ["log.service.name"],
  "rule": {
    "mode": "and",
    "conditions": []
  }
}
```

Keyword alerts do not store `rule`. Aggregate alerts store `rule`.

## Keyword Alert Execution

Keyword alert execution has two paths.

When `group_by` is empty, the current behavior is preserved:

- Build the final query with log group filters.
- Query a limited set of sample logs.
- Query total count with `stats count()`.
- Create or update one alert using `source_id = policy_{policy.id}`.

When `group_by` is configured, VictoriaLogs performs the grouping:

```text
<final_query> | stats by (log.service.name, ...) count() as total_count
```

For each grouped result:

- Build a group key from the configured grouping field values.
- Create or update one alert using `source_id = policy_{policy.id}_{group_key}`.
- Set alert value from `total_count`.
- Render alert content from the alert name template.
- Query a small sample of raw logs for that group and save it as raw data.

This avoids pulling all matched raw logs into Python just to group them.

## Aggregate Alert Execution

Aggregate alert execution keeps the existing `stats by (...)` and rule-checking flow.

The implementation should extend alert-name template rendering so aggregate alerts also support `${level}` in addition to log grouping variables.

## Template Rendering

Rendering context contains:

- `level`: policy alert level.
- Configured grouping fields, such as `log.service.name`.

Because Django template variables do not naturally support dotted keys, rendering should use a small formatter for `${...}` tokens instead of relying on plain Django variable lookup for dotted log fields.

Missing variables should render as an empty string. Invalid or malformed templates should fall back to the original alert name rather than blocking policy execution.

## Validation

Required fields:

- Strategy name
- Alert name
- Organization
- Log group
- Query
- Display fields
- Detection frequency
- Detection period
- Alert level

Optional fields:

- Grouping fields

Aggregate-only required fields:

- Rule

Keyword alerts must not require rule configuration.

## Error Handling

- Preview API failures should show an inline error or empty state and must not block saving.
- Policy save validation failures should continue using existing form validation and backend error responses.
- Keyword grouped scans should log and skip malformed group rows where the group key cannot be built.
- Sample-log lookup failure for one group should not prevent other grouped alerts from being created.

## Testing Strategy

Implementation should follow TDD.

Backend tests:

- Keyword alert without `group_by` preserves current single-alert `source_id` behavior.
- Keyword alert with `group_by` uses a VictoriaLogs `stats by (...)` query.
- Keyword grouped results produce separate alert events and source IDs.
- Alert name renders `${level}` and `${log.fieldName}`.
- Missing variables do not crash scanning.

Frontend tests or focused validation:

- Add button opens the policy type modal instead of navigating immediately.
- Selecting a type initializes and locks `alert_type`.
- Edit mode does not allow changing policy type.
- Keyword alert shows optional grouping fields and no rule section.
- Aggregate alert shows grouping fields and the rule section.
- Variable "use" inserts into the alert name.
- Preview skips query when query is empty and requests `limit=10` when query is present.

## Rollout

This change is backward compatible for existing policies:

- Existing keyword policies without `group_by` keep the old single-alert behavior.
- Existing aggregate policies keep their current rule behavior.
- Existing alert names remain valid plain text templates.
