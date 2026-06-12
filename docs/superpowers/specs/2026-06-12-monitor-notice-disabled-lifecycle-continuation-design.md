# Monitor Notice Disabled Lifecycle Continuation Design

## Background

GitHub issue #2793 describes a lifecycle gap in monitor alert notifications. The code already snapshots
`notice_type_ids` and `notice_users` onto each `MonitorAlert` when the alert is created, so changing the
policy notification channels after an alert is active does not lose the original channel selection.

The remaining problem is the policy-level `notice` switch. `AlertLifecycleNotifier.notify_alerts()` currently
returns early when `policy.notice` is false. That early return happens before the notifier reads the alert-level
channel snapshot, so already-notified active alerts cannot send later `recovered` or `closed` lifecycle events.
If one of those old channels is the alert center, the alert center may keep showing a stale active alert.

This also intersects with the #3119 behavior: disabling notifications must not create a broken lifecycle where
a newly created alert is silent, but its later recovery or close is sent to users.

## Product Semantics

The intended rule is:

> Disabling policy notifications stops new notification chains, but already-notified active alerts should be
> allowed to finish their lifecycle on the channels that were successfully notified at creation time.

This gives users a predictable lifecycle:

- New alerts follow the policy's current `notice` state and current notification channel configuration.
- Active alerts that were already notified continue to send terminal lifecycle events to the old channels.
- Alerts that were never notified do not later send recovery or close messages.
- Alert center remains a lifecycle state downstream, while normal channels remain user-facing notifications.

## Detailed Rules

### Created

When `policy.notice` is true, `created` notifications work as they do today. The alert stores the policy's
current `notice_type_ids` and `notice_users` snapshot at creation time.

When `policy.notice` is false, `created` notifications are not sent. The alert may still store the current
snapshot fields for traceability, but those fields alone do not authorize later notification continuation.

### Recovered And Closed

When `policy.notice` is true, `recovered` and `closed` notifications use the existing behavior: resolve channels
from the alert snapshot first, then fall back to the policy configuration if needed.

When `policy.notice` is false, `recovered` and `closed` notifications are allowed only for channels that have a
successful `created` entry in the alert's `notice_logs`.

The successful-created check is:

```text
log.action == "created"
log.channel_id == current channel id
log.success is True
```

This prevents the #3119 lifecycle break: an alert whose creation was never successfully notified cannot later send
a recovery or close notification.

### Upgraded

When `policy.notice` is true, `upgraded` notifications keep the existing behavior.

When `policy.notice` is false:

- Normal notification channels are skipped.
- Alert center channels may continue to receive `upgraded` only when that alert previously had a successful
  `created` push to that same alert center channel.

This keeps alert center state current without continuing user-facing escalation noise after the notification
switch has been disabled.

### Notification Scope

The existing notification scope parameter remains part of the contract:

- `none`: do not notify any channel.
- `alert_center_only`: only send to channels identified as alert center.
- `all_configured`: send to all eligible configured or snapshotted channels.

Scope filtering and notification-continuation filtering both apply. A channel must pass both filters before it is
sent.

For policy configuration change closure from issue #3001, `alert_center_only` remains the correct scope. If
`policy.notice` is false, it should still be able to close stale alert-center records, but only for alerts that
were previously created successfully in alert center.

## Architecture

The change belongs in `server/apps/monitor/services/alert_lifecycle_notify.py`.

`AlertLifecycleNotifier.notify_alerts()` should no longer return immediately for every action when
`policy.notice` is false. Instead, it should build channel groups and filter each alert/channel pair through a
single eligibility function.

Proposed helper responsibilities:

- Resolve candidate channels from the alert snapshot first, with existing fallback behavior when notice is on.
- Determine whether a channel is the alert center using the existing channel-type check.
- Determine whether an alert has a successful `created` notification log for a channel.
- Decide if an alert/channel/action is eligible under the current `policy.notice` state and `notify_scope`.

The eligibility function should be small and explicit because it encodes product semantics:

```text
notify_scope == none:
  skip

policy.notice == true:
  allow if channel passes scope

policy.notice == false and action in [recovered, closed]:
  allow if channel passes scope and alert had successful created on that channel

policy.notice == false and action == upgraded:
  allow only alert center channels that pass scope and had successful created on that channel

policy.notice == false and action == created:
  skip
```

## Data Flow

1. Alert creation stores the selected channels and users in `MonitorAlert.notice_type_ids` and
   `MonitorAlert.notice_users`.
2. Successful notification attempts append entries to `MonitorAlert.notice_logs`.
3. Later lifecycle events call `AlertLifecycleNotifier.notify_alerts()`.
4. The notifier resolves candidate channels, filters by scope, filters by continuation eligibility, sends eligible
   events, and appends new `notice_logs` entries.

No database migration is required.

## Error Handling

Channel lookup failures keep the existing behavior: log the failure and append a failed notice log for the affected
alert/channel pair.

Notification send failures keep the existing behavior: record a failed notice log and continue processing other
groups.

When `notice_logs` is empty or malformed, the safe default under `policy.notice=false` is to skip continuation for
that channel. This favors avoiding unexpected user-facing notifications over guessing.

## Testing

Add focused tests around `AlertLifecycleNotifier`:

- `policy.notice=false` and `action=created` sends nothing.
- `policy.notice=false`, `action=recovered`, and a matching successful `created` log sends to the old channel.
- `policy.notice=false`, `action=closed`, and no matching successful `created` log sends nothing.
- `policy.notice=false`, `action=upgraded`, normal channel with matching `created` log sends nothing.
- `policy.notice=false`, `action=upgraded`, alert center channel with matching `created` log sends.
- `notify_scope=alert_center_only` with `policy.notice=false` sends only matching historical alert center channels.
- Existing policy deletion, disablement, no-data closure, and #3001 policy configuration change tests keep passing.

## Acceptance Criteria

- Closing policy notifications does not send `created` for new alerts.
- Already-notified active alerts can still send `recovered` and `closed` to channels that successfully received
  `created`.
- Alerts that never successfully sent `created` do not send later terminal lifecycle notifications while
  `policy.notice=false`.
- Alert center receives eligible lifecycle continuation events even when policy notifications are disabled.
- Normal notification channels do not receive `upgraded` while policy notifications are disabled.
- #3001 configuration-change closures can still synchronize eligible stale alert-center records.
