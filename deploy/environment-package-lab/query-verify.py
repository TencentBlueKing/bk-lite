"""Verify this injection's persisted event IDs and their real notification receipts."""
import collections
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

import django
from query_run import alarm_run, match_receipts

django.setup()
from apps.log.models.policy import Alert, Event
from apps.log.services.alert_lifecycle_notify import LogAlertLifecycleNotifier
from apps.apm.models import ApmAlert, ApmEvent, ApmAlertOutbox, ApmEventSnapshot

out = Path("/test/evidence/query-alert-20261115")
run_id, started_at = alarm_run(out)
# Invalidate old success before doing any checks, including a same-run retry.
(out / "final-verification.json").write_text(json.dumps({"passed": False, "run_id": run_id}))
logs = list(Alert.objects.filter(policy__name="C/D 日志错误验证", created_at__gte=started_at))
apm = list(ApmAlert.objects.filter(service_namespace="cd-query-validation", created_at__gte=started_at))
assert len(logs) == 2 and all(x.status == "closed" for x in logs), "Missing current log alerts or closure"
assert len(apm) == 2 and all(x.status == "recovered" and x.current_value == 1 for x in apm), "Missing current APM recovery"
assert {x.service_name for x in apm} == {"cd-c", "cd-d"}
expected = []
for alert in logs:
    created = list(Event.objects.filter(alert=alert, action="", event_time=alert.start_event_time, notified=True))
    closed = list(Event.objects.filter(alert=alert, action="closed", notified=True))
    assert len(created) == len(closed) == 1, "Missing or ambiguous current log lifecycle event"
    notifier = LogAlertLifecycleNotifier(alert.policy)
    for event, payload in [(created[0], notifier.build_created_event(created[0])), (closed[0], notifier.build_closed_event(alert))]:
        expected.append({"pusher": "lite-log", "alert_id": str(alert.id), "event_id": str(event.id), "payload": payload})
for alert in apm:
    events = list(ApmEvent.objects.filter(alert=alert))
    assert len(events) == 2 and {x.action for x in events} == {"triggered", "recovered"}
    for event in events:
        deliveries = list(ApmAlertOutbox.objects.filter(event_id=event.id))
        assert len(deliveries) == 1 and deliveries[0].delivery_status == "delivered" and deliveries[0].attempts == 1
        payload = deliveries[0].payload
        assert payload["event_key"] == event.event_id and payload["external_id"] == alert.external_id and payload["action"] == event.action
        assert ApmEventSnapshot.objects.filter(event_id=event.id, payload_status="available").count() == 1
        expected.append({"pusher": "lite-apm", "alert_id": str(alert.id), "event_id": str(event.id), "payload": payload})
receipts = []
for line in (out / "notification-receipts.jsonl").read_text().splitlines():
    record = json.loads(line)
    kwargs = record["request"].get("kwargs", {})
    for event in kwargs.get("events", []):
        receipts.append({"received_at": record["received_at"], "subject": record["subject"], "pusher": kwargs.get("pusher"), "event": event})
matched = match_receipts(expected, receipts)
(out / "business-notification-receipts.json").write_text(json.dumps(matched, ensure_ascii=False, indent=2))
query = 'verification:="CD-QUERY" AND level:="error" AND (node_ip:"192.168.122.4" OR node_ip:"192.168.122.209") | stats count() as count'
params = urllib.parse.urlencode({"query": query, "start": str(int(time.time()) - 60), "end": str(int(time.time()))})
body = urllib.request.urlopen(os.environ["VICTORIALOGS_HOST"] + "/select/logsql/query?" + params, timeout=15).read().decode()
rows = [json.loads(x) for x in body.splitlines() if x]
assert all(int(x["count"]) == 0 for x in rows), rows
counts = collections.Counter((x["pusher"], x["event"]["action"]) for x in matched)
result = {
    "passed": True,
    "run_id": run_id,
    "alerts": {"log": [{"id": str(x.id)} for x in logs], "apm": [{"id": str(x.id), "service": x.service_name} for x in apm]},
    "events": [{k: x[k] for k in ("pusher", "alert_id", "event_id")} for x in expected],
    "log_closed": len(logs),
    "apm_recovered": len(apm),
    "business_receipts": len(matched),
    "receipt_counts": {"/".join(k): v for k, v in counts.items()},
    "apm_outbox_delivered_once": 4,
    "last_minute_error_count": 0,
    "log_recovery_semantics": "manual closure via UI",
    "notification_scope": "isolated NATS receiver, no external channel",
}
(out / "final-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
print("__QUERY_ALERT_LIFECYCLE_VERIFIED__")
