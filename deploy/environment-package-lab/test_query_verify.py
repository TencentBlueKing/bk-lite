"""Execute the complete verifier with old/current DB rows and delivery receipts."""
import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace as S
from unittest.mock import patch
import unittest
import urllib.request

SCRIPT = Path(__file__).with_name("query-verify.py")
START = 1800000000


class Rows(list):
    def filter(self, **conditions):
        result = list(self)
        for key, expected in conditions.items():
            parts = key.split("__")
            gte = parts[-1] == "gte"
            if gte:
                parts.pop()

            def match(item):
                value = item
                for part in parts:
                    value = getattr(value, part)
                return value >= expected if gte else value == expected

            result = [x for x in result if match(x)]
        return Rows(result)

    def count(self):
        return len(self)


def payload(alert, action):
    return {
        "external_id": alert.external_id,
        "action": action,
        "start_time": str(int(alert.created_at.timestamp())),
        "end_time": None,
        "resource_id": alert.id,
        "rule_id": "1",
    }


class VerifyTest(unittest.TestCase):
    def execute(self, *, missing=False, stale_receipts=False):
        logs, apm, log_events, apm_events, deliveries, snapshots, receipts = [Rows() for _ in range(7)]
        for generation, timestamp in [("old", START - 3600), ("new", START + 30)]:
            if missing and generation == "new":
                continue
            for node in ["c", "d"]:
                created = datetime.fromtimestamp(timestamp, timezone.utc)
                log = S(
                    id=generation + "log" + node,
                    external_id=generation + "log" + node,
                    status="closed",
                    created_at=created,
                    start_event_time=created,
                    policy=S(name="C/D 日志错误验证"),
                )
                alert = S(
                    id=generation + "apm" + node,
                    external_id=generation + "external" + node,
                    status="recovered",
                    current_value=1,
                    created_at=created,
                    service_namespace="cd-query-validation",
                    service_name="cd-" + node,
                )
                logs.append(log)
                apm.append(alert)
                for action in ["created", "closed"]:
                    event = S(id=log.id + action, alert=log, action="" if action == "created" else action, event_time=created, notified=True)
                    log_events.append(event)
                    if not stale_receipts or generation == "old":
                        receipts.append({"pusher": "lite-log", "event": payload(log, action)})
                for action in ["triggered", "recovered"]:
                    event = S(id=alert.id + action, event_id=alert.external_id + ":" + action, alert=alert, action=action)
                    apm_events.append(event)
                    body = {**payload(alert, action), "event_key": event.event_id}
                    deliveries.append(S(event_id=event.id, delivery_status="delivered", attempts=1, payload=body))
                    snapshots.append(S(event_id=event.id, payload_status="available"))
                    if not stale_receipts or generation == "old":
                        receipts.append({"pusher": "lite-apm", "event": body})
        modules = {
            name: ModuleType(name) for name in ["django", "apps.log.models.policy", "apps.log.services.alert_lifecycle_notify", "apps.apm.models"]
        }
        modules["django"].setup = lambda: None
        modules["apps.log.models.policy"].Alert = S(objects=logs)
        modules["apps.log.models.policy"].Event = S(objects=log_events)
        modules["apps.log.services.alert_lifecycle_notify"].LogAlertLifecycleNotifier = lambda policy: S(
            build_created_event=lambda e: payload(e.alert, "created"), build_closed_event=lambda a: payload(a, "closed")
        )
        for name, rows in [("ApmAlert", apm), ("ApmEvent", apm_events), ("ApmAlertOutbox", deliveries), ("ApmEventSnapshot", snapshots)]:
            setattr(modules["apps.apm.models"], name, S(objects=rows))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            concrete = type(out)
            (out / "alarm-traffic.json").write_text(
                json.dumps(
                    [
                        {"ip": ip, "marker": f"CD-QUERY-alarm-{START}-env-auto-{n}-20261114"}
                        for n, ip in [("c", "192.168.122.4"), ("d", "192.168.122.209")]
                    ]
                )
            )
            (out / "final-verification.json").write_text(json.dumps({"passed": True, "run_id": "old"}))
            (out / "notification-receipts.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "received_at": "previous-or-current",
                            "subject": "test",
                            "request": {"kwargs": {"pusher": r["pusher"], "events": [r["event"]]}},
                        }
                    )
                    for r in receipts
                )
            )
            with patch.dict("sys.modules", modules), patch(
                "pathlib.Path", lambda p: out if str(p) == "/test/evidence/query-alert-20261115" else concrete(p)
            ), patch.dict(os.environ, {"VICTORIALOGS_HOST": "http://mock.invalid"}), patch(
                "urllib.request.urlopen", return_value=io.BytesIO(b'{"count":"0"}\n')
            ), contextlib.redirect_stdout(
                io.StringIO()
            ):
                if missing or stale_receipts:
                    with self.assertRaises(AssertionError):
                        runpy.run_path(str(SCRIPT), run_name="__main__")
                else:
                    runpy.run_path(str(SCRIPT), run_name="__main__")
            result = json.loads((out / "final-verification.json").read_text())
            self.assertEqual(result["passed"], not (missing or stale_receipts))
            if result["passed"]:
                self.assertEqual(result["business_receipts"], 8)
                self.assertTrue(all(x["event_id"].startswith("new") for x in result["events"]))
                matched = json.loads((out / "business-notification-receipts.json").read_text())
                self.assertEqual({x["event_id"] for x in matched}, {x["event_id"] for x in result["events"]})

    def test_second_run_full_verifier_joins_current_ids(self):
        self.execute()

    def test_old_success_without_current_alerts_fails(self):
        self.execute(missing=True)

    def test_old_receipts_cannot_satisfy_current_alerts(self):
        self.execute(stale_receipts=True)


if __name__ == "__main__":
    unittest.main()
