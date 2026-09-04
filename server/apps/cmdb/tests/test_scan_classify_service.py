import pytest

from apps.cmdb.models.collect_model import OidMapping
from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, ScanTask
from apps.cmdb.services.scan_classify_service import classify_hits, rematch_soid
from apps.core.exceptions.base_app_exception import BaseAppException

pytestmark = pytest.mark.django_db

UNKNOWN_OID = "1.2.3.999"


def _execution(status=ScanExecution.STATUS_COMPLETED, hosts=None):
    task = ScanTask.objects.create(
        name="scan-classify",
        team=[1],
        families=["network"],
        access_point=[{"id": "node-1"}],
        credentials={"network": [{"credential_id": "cred-1", "version": "v2c", "community": "public"}]},
    )
    execution = ScanExecution.objects.create(task=task, status=status)
    family_run = ScanFamilyRun.objects.create(
        execution=execution,
        model_id="network",
        driver_type="protocol",
        admit_status=ScanFamilyRun.ADMIT_ACCEPTED,
    )
    hits = []
    for host in hosts or ["10.0.1.11"]:
        hits.append(
            ScanHit.objects.create(
                execution=execution,
                family_run=family_run,
                protocol="network",
                host=host,
                port=161,
                credential_id="cred-1",
                status=ScanHit.STATUS_SUCCESS,
                soid=UNKNOWN_OID,
                snapshot={"sysname": f"dev-{host}", "sysobjectid": UNKNOWN_OID},
            )
        )
    return execution, family_run, hits


def _capture_cannula(mocker):
    captured = {}

    class FakeCannula:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self.collect_data = {}

        def collect_controller(self):
            metrics = captured.get("default_metrics") or {}
            result = {}
            for model_id, rows in metrics.items():
                success = []
                for row in rows or []:
                    success.append(
                        {
                            "inst_info": {
                                **row,
                                "inst_uuid": f"uuid-{row.get('ip_addr')}",
                                "model_id": model_id,
                            }
                        }
                    )
                result[model_id] = {
                    "add": {"success": success, "failed": []},
                    "update": {"success": [], "failed": []},
                    "delete": {"success": [], "failed": []},
                }
            result["__raw_data__"] = []
            result["all"] = sum(len(rows or []) for rows in metrics.values())
            return result

    mocker.patch("apps.cmdb.services.scan_finalize_service.MetricsCannula", FakeCannula)
    return captured


def test_classify_hits_writes_ci_without_oid_mapping(mocker):
    execution, _family_run, hits = _execution()
    captured = _capture_cannula(mocker)

    result = classify_hits(execution, [hits[0].id], "router")

    assert result["classified"] == 1
    assert result["failed"] == 0
    hit = ScanHit.objects.get(pk=hits[0].pk)
    assert hit.cmdb_model_id == "router"
    assert hit.inst_uuid == "uuid-10.0.1.11"
    assert hit.snapshot.get("device_type") == "router"
    assert captured["default_metrics"]["router"][0]["ip_addr"] == "10.0.1.11"
    assert OidMapping.objects.filter(oid=UNKNOWN_OID).count() == 0


def test_classify_hits_rejects_running_execution():
    execution, _family_run, hits = _execution(status=ScanExecution.STATUS_RUNNING)
    with pytest.raises(BaseAppException, match="尚未收口"):
        classify_hits(execution, [hits[0].id], "switch")


def test_classify_hits_rejects_invalid_type():
    execution, _family_run, hits = _execution()
    with pytest.raises(BaseAppException, match="设备类型"):
        classify_hits(execution, [hits[0].id], "host")


def test_classify_hits_skips_already_matched(mocker):
    execution, family_run, hits = _execution()
    hits[0].cmdb_model_id = "switch"
    hits[0].inst_uuid = "already"
    hits[0].save(update_fields=["cmdb_model_id", "inst_uuid"])
    _capture_cannula(mocker)

    result = classify_hits(execution, [hits[0].id], "router")

    assert result["classified"] == 0
    assert result["skipped"] == 1
    hits[0].refresh_from_db()
    assert hits[0].cmdb_model_id == "switch"


def test_rematch_soid_classifies_from_oid_mapping(mocker):
    execution, _family_run, hits = _execution(hosts=["10.0.1.11", "10.0.1.12"])
    OidMapping.objects.create(oid=UNKNOWN_OID, device_type="firewall", brand="Acme", model="FW1")
    captured = _capture_cannula(mocker)

    result = rematch_soid(execution, UNKNOWN_OID)

    assert result["classified"] == 2
    assert {hit.cmdb_model_id for hit in ScanHit.objects.filter(execution=execution)} == {"firewall"}
    assert captured["default_metrics"]["firewall"][0]["brand"] == "Acme"
    assert ScanHit.objects.get(host="10.0.1.11").snapshot.get("model") == "FW1"


def test_rematch_soid_fails_when_mapping_missing():
    execution, _family_run, _hits = _execution()
    with pytest.raises(BaseAppException, match="没有该 SOID"):
        rematch_soid(execution, UNKNOWN_OID)


def test_rematch_soid_skips_already_classified(mocker):
    execution, _family_run, hits = _execution(hosts=["10.0.1.11", "10.0.1.12"])
    hits[0].cmdb_model_id = "switch"
    hits[0].inst_uuid = "uuid-old"
    hits[0].save(update_fields=["cmdb_model_id", "inst_uuid"])
    OidMapping.objects.create(oid=UNKNOWN_OID, device_type="router", brand="B", model="R1")
    _capture_cannula(mocker)

    result = rematch_soid(execution, UNKNOWN_OID)

    assert result["classified"] == 1
    hits[0].refresh_from_db()
    assert hits[0].cmdb_model_id == "switch"
    assert ScanHit.objects.get(host="10.0.1.12").cmdb_model_id == "router"


def test_rematch_soid_stamps_empty_soid_hits_when_hit_ids_given(mocker):
    execution, _family_run, hits = _execution(hosts=["10.0.1.11", "10.0.1.12"])
    for hit in hits:
        hit.soid = ""
        hit.snapshot = {"sysname": f"dev-{hit.host}"}
        hit.save(update_fields=["soid", "snapshot"])
    OidMapping.objects.create(oid=UNKNOWN_OID, device_type="switch", brand="H3C", model="S2610V2")
    captured = _capture_cannula(mocker)

    result = rematch_soid(execution, UNKNOWN_OID, hit_ids=[hits[0].id])

    assert result["classified"] == 1
    first = ScanHit.objects.get(pk=hits[0].pk)
    second = ScanHit.objects.get(pk=hits[1].pk)
    assert first.soid == UNKNOWN_OID
    assert first.cmdb_model_id == "switch"
    assert first.snapshot.get("sysobjectid") == UNKNOWN_OID
    assert captured["default_metrics"]["switch"][0]["brand"] == "H3C"
    assert second.soid == ""
    assert second.cmdb_model_id == ""


def test_rematch_soid_without_hit_ids_does_not_claim_empty_soid(mocker):
    execution, _family_run, hits = _execution()
    hits[0].soid = ""
    hits[0].save(update_fields=["soid"])
    OidMapping.objects.create(oid=UNKNOWN_OID, device_type="switch", brand="H3C", model="S2610V2")
    _capture_cannula(mocker)

    result = rematch_soid(execution, UNKNOWN_OID)

    assert result["classified"] == 0
    hits[0].refresh_from_db()
    assert hits[0].soid == ""
    assert hits[0].cmdb_model_id == ""
