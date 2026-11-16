"""Read persisted snapshots from the latest alarm injection, excluding older runs."""
import json
from pathlib import Path

import django

django.setup()
from apps.log.models.policy import AlertSnapshot
from apps.apm.models import ApmEventSnapshot, ApmEventSnapshotPayload

out = Path("/test/evidence/query-alert-20261115")
from query_run import verified_run

current = verified_run(out)
log_ids = [x["id"] for x in current["alerts"]["log"]]
apm_ids = [x["id"] for x in current["alerts"]["apm"]]
r = {"log": [], "apm": []}
for x in AlertSnapshot.objects.filter(policy__name="C/D 日志错误验证", alert_id__in=log_ids):
    data = x.snapshots
    # Source IDs are opaque (legacy policy-prefixed labels or current hashes).
    # Verify the persisted grouping field, never infer a node from that ID.
    node_ip = data[0]["raw_data"]["query_result"].get("node_ip") if data else None
    r["log"].append(
        {
            "alert_id": x.alert_id,
            "source": x.source_id,
            "entries": len(data),
            "node_ip": node_ip,
            "aggregate_matches_node": bool(data)
            and all(v["raw_data"]["query_result"]["node_ip"] == node_ip and int(v["raw_data"]["query_result"]["count__msg"]) == 1 for v in data),
            "payload": data,
        }
    )
for x in ApmEventSnapshot.objects.filter(alert__service_namespace="cd-query-validation", alert_id__in=apm_ids):
    payload = ApmEventSnapshotPayload.objects.get(snapshot=x).data
    r["apm"].append(
        {
            "event_id": str(x.event_id),
            "action": x.action,
            "service": x.alert.service_name,
            "status": x.payload_status,
            "payload": payload,
        }
    )
(out / "snapshot-readback.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str))
print(json.dumps({k: [{a: b for a, b in x.items() if a != "payload"} for x in rows] for k, rows in r.items()}, ensure_ascii=False))
assert len(r["log"]) == 2 and all(x["aggregate_matches_node"] for x in r["log"])
assert {x["node_ip"] for x in r["log"]} == {"192.168.122.4", "192.168.122.209"}
assert len(r["apm"]) == 4 and all(x["status"] == "available" and x["payload"] for x in r["apm"])
assert {(x["service"], x["action"]) for x in r["apm"]} == {(service, action) for service in ["cd-c", "cd-d"] for action in ["triggered", "recovered"]}
print("__S3_SNAPSHOTS_READ_BACK__")
