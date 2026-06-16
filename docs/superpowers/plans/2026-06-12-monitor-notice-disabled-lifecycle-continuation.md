# Monitor Notice Disabled Lifecycle Continuation Implementation Plan

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
