# Date Range Parameter Design

## Goal

Add a `dateRange` data-source parameter type for natural business-date ranges without reusing `timeRange` timestamp, minute-offset, or UTC behavior.

This document covers design only. It does not include implementation.

## Scope

The first release supports:

- NATS data-source parameter type selection, configuration, defaults, persistence, validation, and edit echo;
- component-level parameter values and request generation;
- unified-filter configuration, binding, persistence, and runtime override;
- unified-filter hosts currently used by Dashboard, Screen, and Topology;
- data-source import/export validation and generic canvas configuration pass-through.

The first release does not add or extend:

- report-canvas behavior, report filters, report scheduling, or report-specific configuration;
- REST, MySQL, PostgreSQL, or Excel parameter configuration;
- `timeRange` period comparison;
- table `inputType=time_range`;
- URL/shared-link parameters;
- enterprise-specific quick ranges.

## Date semantics

`dateRange` represents natural dates and never time instants. Its resolved request value is an inclusive, ordered pair of `YYYY-MM-DD` strings:

```json
["2026-07-01", "2026-07-17"]
```

Both endpoints are included. The frontend does not append start-of-day, end-of-day, timezone offsets, ISO timestamps, or UTC markers. A receiving NATS method owns the business meaning of applying these dates to date or datetime fields.

The generic selector allows same-day ranges, future dates, and arbitrary span lengths. It validates only date format and `startDate <= endDate`. Data-source-specific restrictions belong to separate business validation.

## Quick ranges

Supported quick rules are:

- today;
- yesterday;
- this week;
- last week;
- this month;
- last month;
- last 7 days;
- last 30 days;
- last 90 days;
- custom.

Their semantics are fixed:

- weeks start on Monday, independent of locale;
- this week is Monday through today;
- last week is the previous complete Monday-through-Sunday week;
- this month is the first day of the current month through today;
- last month is the previous complete calendar month;
- rolling N-day ranges include today and therefore start at `today - (N - 1)` days.

## Value models

Persisted values and resolved request values are separate types.

Quick persisted value:

```json
{
  "rangeType": "last_30_days"
}
```

Custom persisted value:

```json
{
  "rangeType": "custom",
  "startDate": "2026-07-01",
  "endDate": "2026-07-17"
}
```

Optional empty value:

```json
null
```

Resolved runtime value:

```json
["2026-06-18", "2026-07-17"]
```

The persisted field must never alternate between a rule object and a resolved array. Dayjs values, JavaScript `Date`, timestamps, and ISO datetime strings must not cross the selector boundary or be persisted.

## Defaults, required values, and clearing

- A required `dateRange` defaults to `{ "rangeType": "last_7_days" }`.
- An optional `dateRange` may be `null`; a null optional value is omitted from the request.
- Explicitly clearing a required value restores `last_7_days`.
- Explicitly clearing an optional value produces `null`.
- Switching another parameter type to `dateRange` discards the incompatible old value and applies the required/optional initialization above.
- Switching `dateRange` to another type discards the rule object and uses the target type's existing initialization behavior.
- No conversion between `timeRange` and `dateRange` is attempted.

## Selector interaction

`DateRangeSelector` is a dedicated control and does not reuse `TimeSelector`.

- Selecting a quick item immediately emits its rule object.
- Selecting custom opens the date-range panel without changing the current business value.
- A one-sided custom selection remains internal UI state and is not emitted or persisted.
- Completing both dates emits one valid custom rule object.
- Cancelling or closing an incomplete custom selection preserves the value that existed before custom was opened.
- Only an explicit clear action applies the required/optional clearing rules.

The selector may use Dayjs internally to drive Ant Design controls, but its external API is `DateRangeValue | null`.

## Validation

Validation is strict and centralized.

Valid custom dates must:

- contain both `startDate` and `endDate`;
- match `YYYY-MM-DD` exactly;
- represent real calendar dates;
- satisfy `startDate <= endDate`.

The validator rejects:

- unknown `rangeType` values;
- incomplete custom values;
- ISO datetime strings;
- timestamps;
- invalid calendar dates;
- reversed ranges;
- conflicting fields on quick-rule objects.

Handling by stage:

- configuration save and import precheck reject invalid values with field-level errors;
- edit echo preserves and displays invalid persisted values rather than silently replacing them;
- runtime blocks a required parameter's component request and reports a configuration error;
- runtime omits an invalid optional parameter and reports a configuration error.

Invalid persisted data is not silently converted to `last_7_days`. Explicit clearing and invalid-data recovery are separate behaviors.

## Timezone and rule resolution

Quick rules are resolved immediately before each request.

The authoritative timezone is the current user's configured timezone. If no reliable configured timezone is available, resolution explicitly falls back to the browser timezone.

`resolveDateRange` accepts the rule, a reference instant, and timezone context. It returns one `ResolvedDateRange`. Centralizing these inputs makes date behavior deterministic and testable.

Resolution must not call `toISOString()` or convert dates through UTC. Week calculations must explicitly use Monday as the first day rather than inheriting a locale default.

## Runtime request flow

```text
DateRangeValue | null
        |
        v
validateDateRangeValue
        |
        v
resolveDateRange(value, referenceNow, timezone)
        |
        v
ResolvedDateRange
        |
        +----> request parameters
        |
        +----> request signature/cache key
```

One request build resolves a rule once and shares the resulting tuple between request parameters and request-signature construction. This prevents midnight races where the request and signature represent different dates.

No new midnight timer is introduced. A page crossing midnight updates on its next manual refresh, scheduled refresh, or other real request. Because the request signature uses resolved dates, it changes naturally after the user's local date changes.

The backend remains unaware of the parameter type and receives an ordinary JSON array in the existing NATS request payload.

## Parameter precedence

The existing parameter flow and precedence remain in place:

```text
fixed
  > enabled unified-filter override
  > component params value
  > data-source default
```

Even a fixed quick rule is resolved again for every request; fixed means user read-only, not calendar-static.

When a unified filter bound to a required `dateRange` is cleared, request construction falls back to the data-source parameter's valid default rule, then to `last_7_days` if that default is invalid. Clearing a bound optional `dateRange` omits the request parameter.

## Unified-filter integration

Unified-filter discovery expands from `string | timeRange` to `string | timeRange | dateRange`.

Bindings require exact parameter name and exact type:

- `dateRange` binds only to `dateRange`;
- `timeRange` binds only to `timeRange`;
- existing `timeRange` bindings are not migrated;
- changing a parameter's type removes incompatible bindings before normal automatic matching runs.

Dashboard, Screen, and Topology use the same `DateRangeValue`, selector, validation, resolution, and binding rules. Their layout restoration code may recognize the new type, but must not implement separate date calculations.

## Import and export

Data-source export preserves the rule object unchanged. Import precheck validates it with the same centralized validator used by configuration save.

Generic Dashboard, Screen, and Topology configuration import/export may pass valid values through existing structures. No report-canvas import/export behavior is added.

## Relationship to `timeRange`

The new type reuses:

- parameter-type registration and selection;
- data-source configuration and persistence;
- component parameter injection;
- edit echo;
- unified-filter discovery and binding structure;
- request-parameter aggregation.

It does not reuse:

- `TimeSelector`;
- minute-based quick values;
- timestamp or ISO conversion;
- UTC conversion;
- `formatTimeRange`;
- `timeRange` comparison behavior.

The design uses a focused date-range domain module rather than refactoring every parameter type into a new generic plugin registry. A registry-wide refactor is outside scope.

## Testing strategy

### Resolution

Use fixed reference instants and explicit timezones to cover today, yesterday, Monday/Sunday week boundaries, cross-month last weeks, first-of-month behavior, cross-year last months, rolling 7/30/90-day ranges, configured-timezone differences, browser fallback, and daylight-saving transitions.

### Validation

Cover every legal quick rule, valid custom and same-day ranges, future dates, null optional values, invalid formats, ISO strings, timestamps, incomplete custom values, reversed ranges, invalid calendar dates, unknown rules, and conflicting fields.

### Configuration and selector behavior

Cover required and optional initialization, quick and custom save/echo, type switching, incomplete-custom cancellation, explicit clearing, invalid-value display, and fixed read-only behavior.

### Unified filters

Cover exact-type matching, binding cleanup after type changes, required and optional clearing behavior, and definition restoration across Dashboard, Screen, and Topology.

### Request construction

Cover fixed, params, and filter paths; request-time resolution; date-only arrays; shared request/signature resolution; cross-midnight signature changes; invalid required and optional values; and regression coverage proving `timeRange` behavior is unchanged.

## Non-goals

This change does not normalize or refactor the existing `timeRange` mixed model. It does not add backend date parsing, business-date-to-datetime conversion, generic date limits, report scheduling, new REST query serialization, or enterprise-only presets.
