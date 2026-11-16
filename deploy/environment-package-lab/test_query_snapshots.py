"""Exercise the real verifier with two rounds, without running any service."""
import contextlib
import io
import hashlib
import json
from pathlib import Path
import runpy
import tempfile
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("query-snapshots.py")
START = 1800000000


class Rows:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, **conditions):
        rows = self.rows
        for key, expected in conditions.items():
            parts = key.split("__")
            gte = parts[-1] == "gte"
            member = parts[-1] == "in"
            if gte or member:
                parts.pop()

            def matches(row):
                value = row
                for part in parts:
                    value = getattr(value, part)
                return value >= expected if gte else value in expected if member else value == expected

            rows = [row for row in rows if matches(row)]
        return rows


class SnapshotTest(unittest.TestCase):
    def verify(self, *, missing=False, corrupt=False, hashed=False, bad_ip=False, mixed=False):
        logs, apm = [], []
        for generation, epoch in [("old", START - 3600), ("new", START + 30)]:
            if missing and generation == "new":
                continue
            created = datetime.fromtimestamp(epoch, timezone.utc)
            for node, ip in [("c", "192.168.122.4"), ("d", "192.168.122.209")]:
                alert = SimpleNamespace(created_at=created, service_namespace="cd-query-validation", service_name="cd-" + node)
                payload = [{"raw_data": {"query_result": {"node_ip": ip, "count__msg": 1}}}]
                if corrupt and generation == "new" and node == "d":
                    payload = []
                if bad_ip and generation == "new" and node == "d":
                    payload[0]["raw_data"]["query_result"]["node_ip"] = "192.168.122.4"
                if mixed and generation == "new" and node == "d":
                    payload.append({"raw_data": {"query_result": {"node_ip": "192.168.122.4", "count__msg": 1}}})
                source_id = "policy_1_node_ip=" + ip
                if hashed:
                    canonical = json.dumps({"node_ip": ip}, sort_keys=True, separators=(",", ":"))
                    source_id = "policy_1_" + hashlib.sha256(canonical.encode()).hexdigest()[:16]
                logs.append(
                    SimpleNamespace(
                        policy=SimpleNamespace(name="C/D 日志错误验证"),
                        alert=alert,
                        alert_id=generation + node,
                        source_id=source_id,
                        snapshots=payload,
                    )
                )
                for action in ["triggered", "recovered"]:
                    apm.append(
                        SimpleNamespace(
                            alert_id=generation + node, alert=alert, event_id=generation + node + action, action=action, payload_status="available"
                        )
                    )
        modules = {name: ModuleType(name) for name in ["django", "apps.log.models.policy", "apps.apm.models"]}
        modules["django"].setup = lambda: None
        modules["apps.log.models.policy"].AlertSnapshot = SimpleNamespace(objects=Rows(logs))
        modules["apps.apm.models"].ApmEventSnapshot = SimpleNamespace(objects=Rows(apm))
        modules["apps.apm.models"].ApmEventSnapshotPayload = SimpleNamespace(
            objects=SimpleNamespace(get=lambda **_: SimpleNamespace(data={"stored": True}))
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            traffic = [
                {"marker": f"CD-QUERY-alarm-{START}-env-auto-{node}-20261114", "ip": ip}
                for node, ip in [("c", "192.168.122.4"), ("d", "192.168.122.209")]
            ]
            (root / "alarm-traffic.json").write_text(json.dumps(traffic))
            (root / "final-verification.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "run_id": f"CD-QUERY-alarm-{START}",
                        "alerts": {kind: [{"id": "newc"}, {"id": "newd"}] for kind in ("log", "apm")},
                    }
                )
            )
            original_path = type(root)
            with patch.dict("sys.modules", modules), patch(
                "pathlib.Path",
                lambda p: root / str(p).removeprefix("/test/evidence/query-alert-20261115").lstrip("/")
                if str(p).startswith("/test/evidence/query-alert-20261115")
                else original_path(p),
            ), contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(SCRIPT), run_name="__main__")
            result = json.loads((root / "snapshot-readback.json").read_text())
            return result

    def test_second_round_ignores_history(self):
        result = self.verify()
        self.assertEqual({row["alert_id"] for row in result["log"]}, {"newc", "newd"})
        self.assertEqual({row["source"] for row in result["log"]}, {"policy_1_node_ip=192.168.122.4", "policy_1_node_ip=192.168.122.209"})
        self.assertEqual(len(result["apm"]), 4)

    def test_current_hashed_source_ids_are_opaque(self):
        result = self.verify(hashed=True)
        self.assertEqual({row["node_ip"] for row in result["log"]}, {"192.168.122.4", "192.168.122.209"})

    def test_duplicate_node_cannot_replace_missing_node(self):
        with self.assertRaises(AssertionError):
            self.verify(bad_ip=True)

    def test_mixed_nodes_within_snapshot_fail(self):
        with self.assertRaises(AssertionError):
            self.verify(mixed=True)

    def test_missing_current_round_never_uses_old_success(self):
        with self.assertRaises(AssertionError):
            self.verify(missing=True)

    def test_corrupt_current_payload_still_fails(self):
        with self.assertRaises(AssertionError):
            self.verify(corrupt=True)


if __name__ == "__main__":
    unittest.main()
