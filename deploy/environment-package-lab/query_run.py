"""Identity contracts shared by the isolated query acceptance scripts."""
import json
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlencode


def alarm_run(out):
    traffic = json.loads((out / "alarm-traffic.json").read_text())
    assert len(traffic) == 2 and {x["ip"] for x in traffic} == {"192.168.122.4", "192.168.122.209"}
    runs = set()
    for item in traffic:
        match = re.fullmatch(r"(CD-QUERY-alarm-(\d+))-env-auto-[cd]-20261114", item["marker"])
        assert match, "Invalid alarm injection marker"
        runs.add((match[1], int(match[2])))
    assert len(runs) == 1, "Mixed alarm injection runs"
    run_id, timestamp = runs.pop()
    return run_id, datetime.fromtimestamp(timestamp, timezone.utc)


def receipt_key(pusher, event):
    return (pusher, *(str(event.get(k, "")) for k in ("external_id", "event_key", "action", "start_time", "end_time", "resource_id", "rule_id")))


def match_receipts(expected, receipts):
    """Join persisted event IDs to the actual wire identity; ignore other runs."""
    assert len(expected) == 8, "Current run must have eight lifecycle events"
    keys = {receipt_key(x["pusher"], x["payload"]): x for x in expected}
    assert len(keys) == len(expected), "Ambiguous current event identities"
    current_alerts = {(x["pusher"], str(x["payload"]["external_id"])) for x in expected}
    matched = []
    for receipt in receipts:
        event = receipt["event"]
        if (receipt["pusher"], str(event.get("external_id", ""))) not in current_alerts:
            continue
        key = receipt_key(receipt["pusher"], event)
        assert key in keys, "Unexpected event for a current alert"
        identity = keys[key]
        matched.append({**receipt, "alert_id": identity["alert_id"], "event_id": identity["event_id"]})
    assert Counter(receipt_key(x["pusher"], x["event"]) for x in matched) == Counter(keys.keys()), "Missing or duplicate current event receipt"
    return matched


def verified_run(out):
    run_id, _ = alarm_run(out)
    result = json.loads((out / "final-verification.json").read_text())
    assert result.get("passed") is True and result.get("run_id") == run_id, "Missing or stale current-run verification"
    for kind in ("log", "apm"):
        assert len(result["alerts"][kind]) == 2
        assert len({x["id"] for x in result["alerts"][kind]}) == 2
    return result


def find_alert_row(page, alert_id):
    """Select an exact AntD row key, including subsequent history pages."""
    assert re.fullmatch(r"[a-fA-F0-9-]+", alert_id), "Invalid alert ID"
    for _ in range(100):
        row = page.locator(f'tr[data-row-key="{alert_id}"]')
        if row.count() == 1:
            return row
        assert row.count() == 0, "Duplicate alert row key"
        next_button = page.locator("li.ant-pagination-next:not(.ant-pagination-disabled) button")
        if next_button.count() != 1:
            break
        next_button.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
    raise AssertionError("Current alert is absent from history")


def enable_log_policy_for_run(policy_model, defaults, now):
    """Start a re-enabled lab policy at this run, retaining all old alerts."""
    existing = policy_model.objects.filter(name="C/D 日志错误验证").first()
    values = dict(defaults)
    if existing is None or not existing.enable:
        values["last_run_time"] = now
    return policy_model.objects.update_or_create(name="C/D 日志错误验证", defaults=values)


def log_query_route(out):
    """Keep delayed page verification inside the current injection window."""
    _, started = alarm_run(out)
    timestamp = int(started.timestamp())
    return "/log/search?" + urlencode({
        "log_groups": "cd-query-validation",
        "query": 'verification:="CD-QUERY"',
        "startTime": (timestamp - 60) * 1000,
        "endTime": (timestamp + 120) * 1000,
    })
