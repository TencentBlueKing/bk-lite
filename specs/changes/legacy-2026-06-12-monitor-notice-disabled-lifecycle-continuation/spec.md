# Historical Superpowers change: 2026-06-12-monitor-notice-disabled-lifecycle-continuation

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-12-monitor-notice-disabled-lifecycle-continuation.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve lifecycle close/recovery synchronization for already-notified active alerts after a policy's notification switch is disabled.

**Architecture:** Keep the behavior centralized in `AlertLifecycleNotifier`. Replace the current `policy.notice == false` early return with per-alert/per-channel eligibility filtering based on action, notify scope, alert-center detection, and historical successful `created` notice logs.

**Tech Stack:** Python 3.12, pytest, Django-adjacent service module tested with lightweight dependency stubs.

---

### Task 1: Failing Tests For Notice-Disabled Continuation

**Files:**
- Modify: `server/apps/monitor/tests/test_policy_scan_failure_handling.py`

- [ ] **Step 1: Add tests covering notice-disabled continuation**

Append focused tests near the existing `AlertLifecycleNotifier` scope tests:

```python
def _build_alert_for_notice_disabled_continuation(notice_type_ids, notice_logs):
    alert = _build_alert_for_notify_scope(notice_type_ids)
    alert.notice_logs = notice_logs
    return alert


def test_alert_lifecycle_notifier_notice_disabled_created_sends_nothing(monkeypatch):
    send_calls = []
    channels_by_id = {
        2: types.SimpleNamespace(id=2, name="wechat", channel_type="wechat", config={}),
    }
    module = _load_alert_lifecycle_notifier_module(monkeypatch, channels_by_id, send_calls)
    alert = _build_alert_for_notice_disabled_continuation([2], [])
    policy = types.SimpleNamespace(id=42, name="Disk Policy", notice=False)

    module.AlertLifecycleNotifier(policy).notify_alerts([alert], action="created")

    assert send_calls == []
    assert alert.notice_logs == []


def test_alert_lifecycle_notifier_notice_disabled_recovered_uses_successful_created_channel(monkeypatch):
    send_calls = []
    channels_by_id = {
        2: types.SimpleNamespace(id=2, name="wechat", channel_type="wechat", config={}),
    }
    module = _load_alert_lifecycle_notifier_module(monkeypatch, channels_by_id, send_calls)
    alert = _build_alert_for_notice_disabled_continuation(
        [2],
        [{"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 2, "success": True}],
    )
    policy = types.SimpleNamespace(id=42, name="Disk Policy", notice=False)

    module.AlertLifecycleNotifier(policy).notify_alerts([alert], action="recovered", operator="system", reason="auto_recovered")

    channel_send_calls = [call for call in send_calls if "channel_id" in call]
    assert [call["channel_id"] for call in channel_send_calls] == [2]
    assert channel_send_calls[0]["notice_users"] == ["alice"]
    assert alert.notice_logs[-1]["action"] == "recovered"


def test_alert_lifecycle_notifier_notice_disabled_closed_skips_without_successful_created_channel(monkeypatch):
    send_calls = []
    channels_by_id = {
        2: types.SimpleNamespace(id=2, name="wechat", channel_type="wechat", config={}),
    }
    module = _load_alert_lifecycle_notifier_module(monkeypatch, channels_by_id, send_calls)
    alert = _build_alert_for_notice_disabled_continuation(
        [2],
        [{"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 2, "success": False}],
    )
    policy = types.SimpleNamespace(id=42, name="Disk Policy", notice=False)

    module.AlertLifecycleNotifier(policy).notify_alerts([alert], action="closed", operator="alice", reason="policy_disabled")

    assert send_calls == []
    assert alert.notice_logs == [{"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 2, "success": False}]


def test_alert_lifecycle_notifier_notice_disabled_upgraded_skips_normal_channel(monkeypatch):
    send_calls = []
    channels_by_id = {
        2: types.SimpleNamespace(id=2, name="wechat", channel_type="wechat", config={}),
    }
    module = _load_alert_lifecycle_notifier_module(monkeypatch, channels_by_id, send_calls)
    alert = _build_alert_for_notice_disabled_continuation(
        [2],
        [{"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 2, "success": True}],
    )
    policy = types.SimpleNamespace(id=42, name="Disk Policy", notice=False)

    module.AlertLifecycleNotifier(policy).notify_alerts([alert], action="upgraded")

    assert send_calls == []


def test_alert_lifecycle_notifier_notice_disabled_upgraded_sends_alert_center_with_successful_created(monkeypatch):
    send_calls = []
    channels_by_id = {
        1: types.SimpleNamespace(id=1, name="alert-center", channel_type="nats", config={"method_name": "receive_alert_events"}),
    }
    module = _load_alert_lifecycle_notifier_module(monkeypatch, channels_by_id, send_calls)
    alert = _build_alert_for_notice_disabled_continuation(
        [1],
        [{"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 1, "success": True}],
    )
    policy = types.SimpleNamespace(id=42, name="Disk Policy", notice=False)

    module.AlertLifecycleNotifier(policy).notify_alerts([alert], action="upgraded")

    channel_send_calls = [call for call in send_calls if "channel_id" in call]
    assert [call["channel_id"] for call in channel_send_calls] == [1]
    assert channel_send_calls[0]["title"] == ""


def test_alert_lifecycle_notifier_notice_disabled_alert_center_scope_requires_successful_alert_center_created(monkeypatch):
    send_calls = []
    channels_by_id = {
        1: types.SimpleNamespace(id=1, name="alert-center", channel_type="nats", config={"method_name": "receive_alert_events"}),
        2: types.SimpleNamespace(id=2, name="wechat", channel_type="wechat", config={}),
    }
    module = _load_alert_lifecycle_notifier_module(monkeypatch, channels_by_id, send_calls)
    alert = _build_alert_for_notice_disabled_continuation(
        [1, 2],
        [
            {"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 1, "success": True},
            {"time": "2026-04-21T08:00:00+00:00", "action": "created", "channel_id": 2, "success": True},
        ],
    )
    policy = types.SimpleNamespace(id=42, name="Disk Policy", notice=False)

    module.AlertLifecycleNotifier(policy).notify_alerts(
        [alert],
        action="closed",
        operator="alice",
        reason="policy_scope_changed",
        notify_scope="alert_center_only",
    )

    channel_send_calls = [call for call in send_calls if "channel_id" in call]
    assert [call["channel_id"] for call in channel_send_calls] == [1]
```

- [ ] **Step 2: Run tests to verify they fail for the missing behavior**

Run:

```bash
cd server
uv run pytest -c /dev/null --confcutdir=apps/monitor/tests -p no:cacheprovider apps/monitor/tests/test_policy_scan_failure_handling.py -q
```

Expected: the new notice-disabled continuation tests fail because `notify_alerts()` returns early when `policy.notice` is false.

### Task 2: Implement Eligibility Filtering

**Files:**
- Modify: `server/apps/monitor/services/alert_lifecycle_notify.py`

- [ ] **Step 1: Replace the global notice-disabled return with per-channel filtering**

Implement the smallest production change:

```python
        alert_log_entries = defaultdict(list)

        groups = defaultdict(list)
        for alert in alerts:
            channel_ids = self._resolve_notice_type_ids(alert)
            notice_users = self._resolve_notice_users(alert)
            if not channel_ids:
                logger.warning(f"Alert {alert.id} has no notice_type_ids configured, skip notification")
                continue
            for channel_id in channel_ids:
                channel = Channel.objects.filter(id=channel_id).first()
                if not self._should_notify_channel(alert, channel, channel_id, action, notify_scope):
                    continue
                groups[(channel_id, tuple(notice_users) if notice_users else ())].append((alert, channel))
```

Then update the send loop to pass the already-loaded channel objects to `_send_to_channel`.

- [ ] **Step 2: Add helpers**

Add helpers with this behavior:

```python
    def _should_notify_channel(self, alert, channel, channel_id, action, notify_scope):
        if notify_scope == NOTIFY_SCOPE_ALERT_CENTER_ONLY and not self._is_alert_center_channel(channel):
            return False
        if self.policy and self.policy.notice:
            return True
        if action == "created":
            return False
        had_created = self._has_successful_created_notice(alert, channel_id)
        if not had_created:
            return False
        if action == "upgraded":
            return self._is_alert_center_channel(channel)
        return action in {"recovered", "closed"}

    def _has_successful_created_notice(self, alert, channel_id):
        for log_entry in alert.notice_logs or []:
            if not isinstance(log_entry, dict):
                continue
            if log_entry.get("action") != "created":
                continue
            if str(log_entry.get("channel_id")) != str(channel_id):
                continue
            if log_entry.get("success") is True:
                return True
        return False
```

Keep `NOTIFY_SCOPE_NONE` as an early return.

- [ ] **Step 3: Preserve missing-channel logging behavior**

If `Channel.objects.filter(id=channel_id).first()` returns `None`, keep the existing `_send_to_channel` behavior by treating it as eligible when normal policy notifications are enabled. When `policy.notice` is false, missing channels are not eligible because they cannot have a known alert-center type and should not be guessed.

- [ ] **Step 4: Run tests to verify green**

Run:

```bash
cd server
uv run pytest -c /dev/null --confcutdir=apps/monitor/tests -p no:cacheprovider apps/monitor/tests/test_policy_scan_failure_handling.py -q
```

Expected: all tests in the file pass.

### Task 3: Final Verification And Commit

**Files:**
- Modify: `server/apps/monitor/services/alert_lifecycle_notify.py`
- Modify: `server/apps/monitor/tests/test_policy_scan_failure_handling.py`
- Create: `docs/superpowers/plans/2026-06-12-monitor-notice-disabled-lifecycle-continuation.md`

- [ ] **Step 1: Compile touched Python files**

Run:

```bash
cd server
uv run python -m py_compile apps/monitor/services/alert_lifecycle_notify.py apps/monitor/tests/test_policy_scan_failure_handling.py
```

Expected: command exits 0.

- [ ] **Step 2: Run the focused pytest file**

Run:

```bash
cd server
uv run pytest -c /dev/null --confcutdir=apps/monitor/tests -p no:cacheprovider apps/monitor/tests/test_policy_scan_failure_handling.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Inspect diff**

Run:

```bash
git diff -- server/apps/monitor/services/alert_lifecycle_notify.py server/apps/monitor/tests/test_policy_scan_failure_handling.py docs/superpowers/plans/2026-06-12-monitor-notice-disabled-lifecycle-continuation.md
```

Expected: diff only contains the plan, tests, and notifier eligibility logic.

- [ ] **Step 4: Commit**

Run:

```bash
git add server/apps/monitor/services/alert_lifecycle_notify.py server/apps/monitor/tests/test_policy_scan_failure_handling.py docs/superpowers/plans/2026-06-12-monitor-notice-disabled-lifecycle-continuation.md
git commit -m "fix(monitor): continue notified alert lifecycle after notice disabled"
```

Expected: commit succeeds.

## specs: 2026-06-12-monitor-notice-disabled-lifecycle-continuation-design.md

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
