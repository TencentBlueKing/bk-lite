# Alert Strategy NATS CRUD Design

## Context

The alerts module already exposes alert statistics and event ingestion through
`server/apps/alerts/nats/nats.py`. Alert strategy CRUD currently exists through
`AlarmStrategyModelViewSet` in `server/apps/alerts/views/strategy.py`, with
validation in `AlarmStrategySerializer`.

This change opens a NATS RPC path for alert strategy CRUD while keeping the
business rules aligned with the REST API path.

## Goals

- Add NATS RPC methods for alert strategy list, detail, create, update, and
  delete.
- Reuse `AlarmStrategySerializer` for create and update validation.
- Preserve REST-side business effects: strategy cache invalidation, session
  timeout cleanup, and operator logs.
- Enforce permissions and team scope at the NATS boundary so RPC cannot bypass
  REST access controls.

## Non-Goals

- Do not add new strategy fields or change alert strategy semantics.
- Do not expose assignment, shield, alert source, or incident CRUD through this
  change.
- Do not introduce a separate NATS-only permission model.

## RPC Surface

Add the following registered NATS methods:

- `list_alarm_strategies(query_data=None, user_info=None)`
- `get_alarm_strategy(strategy_id, user_info=None)`
- `create_alarm_strategy(data, user_info=None)`
- `update_alarm_strategy(strategy_id, data, partial=True, user_info=None)`
- `delete_alarm_strategy(strategy_id, user_info=None)`

All methods return the existing NATS response shape:

```json
{"result": true, "data": {}, "message": ""}
```

Validation, permission, and not-found failures return:

```json
{"result": false, "data": [], "message": "..."}
```

`list_alarm_strategies` supports the same core filtering used by
`AlarmStrategyModelFilter`: `name`, `created_at_after`, and
`created_at_before`. It also supports bounded pagination through `page` and
`page_size`.

## Authorization

NATS RPC authorization must be default-deny.

Required permissions:

- `correlation_rules-View` for list and detail.
- `correlation_rules-Add` for create.
- `correlation_rules-Edit` for update.
- `correlation_rules-Delete` for delete.

`user_info.is_superuser` bypasses permission-name checks but still requires
valid team context for scoped non-global operations where team validation is
needed.

For non-superusers:

- `user_info.team` is required.
- The relevant permission must be present in `user_info.permission`.
- Existing strategies are scoped by `AlarmStrategy.team`.
- `include_children=True` includes child teams from `user_info.group_tree`.
- Create and update must reject `team` or `dispatch_team` values outside the
  authorized team set.

The NATS layer should accept both permission shapes already seen in the alerts
NATS code:

- `{"alarm": ["correlation_rules-View"]}`
- `["correlation_rules-View"]`

It may also tolerate set or tuple values.

## Shared Business Path

Create and update use `AlarmStrategySerializer`. This keeps these REST and NATS
rules aligned:

- Strategy-type validation for smart denoise, missing detection, and instant
  strategies.
- Aggregation dimension whitelist validation.
- Missing detection cron and alert template validation.
- Instant strategy template validation and automatic cleanup of aggregation
  fields.
- `InstantStrategyCache.cache_clear()` from serializer `save()`.

The NATS path should provide a lightweight request-like context to the serializer
so existing `validate_team` and `validate_dispatch_team` checks continue to
work. The request context only needs the user attributes and current team
information required by `apps.alerts.utils.permission_scope`.

## Side Effects

Create:

- Save through `AlarmStrategySerializer`.
- Write an `OperatorLog` equivalent to REST create.

Update:

- Save through `AlarmStrategySerializer`.
- If the update disables a session timeout window, call
  `TimeoutChecker.confirm_observing_alerts_by_strategy(strategy_id)`.
- Write an `OperatorLog` equivalent to REST update.

Delete:

- If the deleted strategy is a session strategy, call
  `TimeoutChecker.close_observing_session_alerts_by_strategy(strategy_id)`.
- Delete the strategy.
- Write an `OperatorLog` equivalent to REST delete.

## Error Handling

- Missing or malformed `data` returns a validation failure.
- Missing `user_info`, missing team, or missing permission returns a permission
  failure.
- Accessing a strategy outside the caller team scope returns a not-found style
  failure so the RPC does not reveal unauthorized strategy existence.
- Serializer validation errors are flattened into a concise message, matching
  the existing monitor NATS create helper style.
- Unexpected exceptions are logged with the alerts logger and returned as
  `result=False`.

## Testing

Use TDD before implementation. Add tests in
`server/apps/alerts/test/test_nats_handlers.py`.

Required coverage:

- List rejects missing permissions.
- List only returns strategies in the authorized team scope.
- Detail rejects cross-team access.
- Create succeeds for an authorized team and persists serializer-normalized data.
- Create rejects unauthorized target teams.
- Update succeeds through serializer and preserves update side effects.
- Delete succeeds and removes only an authorized strategy.
- Delete rejects cross-team access.

Run the focused test file first, then run the alerts-relevant server test target
if feasible.
