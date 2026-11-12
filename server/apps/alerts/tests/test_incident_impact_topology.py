import json
import logging
from pathlib import Path

import pytest
from nats.errors import NoRespondersError
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.models import Alert, Incident
from apps.alerts.views.incident import IncidentModelViewSet
from apps.core.logger import SafeLogException
from apps.rpc.exceptions import RpcTimeoutError

HOST_A = "00000000-0000-4000-8000-000000000001"
HOST_B = "00000000-0000-4000-8000-000000000002"
FOREIGN = "00000000-0000-4000-8000-000000000099"


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


@pytest.fixture(autouse=True)
def _grant_permissions(monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *args, **kwargs: {"instance": [], "team": ["1"]},
    )


def _request(path, user, data=None, team="1", include_children="0"):
    request = APIRequestFactory().post(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = team
    request.COOKIES["include_children"] = include_children
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
    return json.loads(response.content)


def _alert(alert_id, objects, team=None):
    return Alert.objects.create(
        alert_id=alert_id,
        level="0",
        title=alert_id,
        content="c",
        fingerprint=alert_id,
        team=team or [1],
        monitor_objects=objects,
    )


def _incident():
    incident = Incident.objects.create(incident_id="INC-1", level="0", title="支付超时", fingerprint="fp", team=[1])
    first = _alert("A1", [{"cmdb_id": HOST_A, "resource_name": "web-01", "resource_type": "主机"}])
    second = _alert(
        "A2",
        [
            {"cmdb_id": HOST_A, "resource_name": "web-01", "resource_type": "主机"},
            {"cmdb_id": HOST_B, "resource_name": "web-02", "resource_type": "主机"},
            {"cmdb_id": "", "resource_name": "未绑定"},
        ],
    )
    incident.alert.add(first, second)
    return incident


def _call(user, incident, data, include_children="0"):
    request = _request(
        f"/alerts/api/incident/{incident.id}/impact_topology/",
        user,
        data=data,
        include_children=include_children,
    )
    response = IncidentModelViewSet.as_view({"post": "impact_topology"})(request, pk=str(incident.id))
    return response, _render(response)


@pytest.mark.django_db
def test_forwards_the_incident_subset_and_user_identity(monkeypatch, superuser):
    incident = _incident()
    captured = {}

    def fake(self, **kwargs):
        captured.update(kwargs)
        return {
            "result": True,
            "data": {
                "truncated": False,
                "nodes": [{"inst_uuid": HOST_B, "role": "seed", "found": True}],
                "links": [],
            },
        }

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", fake)
    response, payload = _call(superuser, incident, {"inst_uuids": [HOST_B.upper(), FOREIGN]}, include_children="1")
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["relation_status"] == "ok"
    assert payload["data"]["nodes"][0]["inst_uuid"] == HOST_B
    assert captured["inst_uuids"] == [HOST_B]
    assert captured["user_info"]["team"] == 1
    assert captured["user_info"]["user"] == "testuser"
    assert captured["user_info"]["domain"] == "domain.com"
    assert captured["user_info"]["locale"] == "en"
    assert captured["user_info"]["include_children"] is True


@pytest.mark.django_db
def test_omitted_subset_uses_every_visible_seed(monkeypatch, superuser):
    incident = _incident()
    captured = {}

    def fake(self, **kwargs):
        captured.update(kwargs)
        return {"result": True, "data": {"truncated": False, "nodes": [], "links": []}}

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", fake)
    response, payload = _call(superuser, incident, {})
    assert response.status_code == 200
    assert payload["data"]["relation_status"] == "ok"
    assert captured["inst_uuids"] == [HOST_A, HOST_B]


@pytest.mark.django_db
def test_no_responders_is_not_purchased_and_still_calls_nats(monkeypatch, superuser, caplog):
    incident = _incident()
    called = {"value": False}
    sentinel = "SECRET-NO-RESPONDER-BODY"

    def fake(self, **kwargs):
        called["value"] = True
        raise NoRespondersError()

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", fake)
    with caplog.at_level(logging.INFO, logger="alert"):
        response, payload = _call(superuser, incident, {"inst_uuids": [HOST_A]})
    assert called["value"] is True
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["relation_status"] == "not_purchased"
    assert payload["data"]["nodes"] == []
    assert "not purchased" in payload["data"]["message"].lower()
    records = [record for record in caplog.records if "incident_impact_topology_not_purchased" in record.msg]
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert records[0].exc_info is None
    assert records[0].args == ("INC-1",)
    assert records[0].getMessage() == "event=incident_impact_topology_not_purchased incident_id=INC-1"
    assert HOST_A not in records[0].getMessage()
    assert sentinel not in caplog.text


@pytest.mark.django_db
def test_timeout_is_unavailable_without_logging_the_exception_text(monkeypatch, superuser, caplog):
    incident = _incident()
    sentinel = "SECRET-TIMEOUT-PAYLOAD"
    error = RpcTimeoutError("bklite", "incident_impact_topology", sentinel)

    def fake(self, **kwargs):
        raise error

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", fake)
    with caplog.at_level(logging.WARNING, logger="alert"):
        response, payload = _call(superuser, incident, {"inst_uuids": [HOST_A]})
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["relation_status"] == "unavailable"
    assert "temporarily unavailable" in payload["data"]["message"].lower()
    records = [record for record in caplog.records if "incident_impact_topology_unavailable" in record.msg]
    assert len(records) == 1
    record = records[0]
    assert record.levelno == logging.WARNING
    assert record.args == ("INC-1", "RpcTimeoutError")
    assert record.getMessage() == "event=incident_impact_topology_unavailable incident_id=INC-1 failed_stage=rpc error_type=RpcTimeoutError"
    assert record.exc_info[0] is SafeLogException
    assert record.exc_info[2] is error.__traceback__
    assert record.exc_info[1] is not error
    assert error.timeout == sentinel
    assert sentinel not in record.getMessage()
    assert sentinel not in caplog.text
    assert HOST_A not in caplog.text


@pytest.mark.django_db
def test_false_result_is_unavailable(monkeypatch, superuser):
    incident = _incident()

    def fake(self, **kwargs):
        return {"result": False, "message": "SECRET-CMDB-MESSAGE", "data": {"nodes": [], "links": []}}

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", fake)
    response, payload = _call(superuser, incident, {"inst_uuids": []})
    assert response.status_code == 200
    assert payload["result"] is True
    assert payload["data"]["relation_status"] == "unavailable"
    assert "SECRET-CMDB-MESSAGE" not in str(payload)


@pytest.mark.django_db
def test_empty_seed_list_still_calls_nats(monkeypatch, superuser):
    incident = Incident.objects.create(incident_id="INC-EMPTY", level="0", title="t", fingerprint="fp", team=[1])
    alert = _alert("A-empty", [{"resource_name": "裸告警"}])
    incident.alert.add(alert)
    captured = {}

    def fake(self, **kwargs):
        captured.update(kwargs)
        return {"result": True, "data": {"truncated": False, "nodes": [], "links": []}}

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", fake)
    response, payload = _call(superuser, incident, {"inst_uuids": None})
    assert response.status_code == 400
    assert payload["result"] is False
    assert "called" not in captured

    response, payload = _call(superuser, incident, {})
    assert response.status_code == 200
    assert payload["data"]["relation_status"] == "ok"
    assert captured["inst_uuids"] == []


@pytest.mark.django_db
def test_invalid_inst_uuids_is_a_client_error(superuser):
    incident = _incident()
    response, payload = _call(superuser, incident, {"inst_uuids": HOST_A})
    assert response.status_code == 400
    assert payload["result"] is False


@pytest.mark.django_db
def test_denied_incident_does_not_call_cmdb(monkeypatch, authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"alarm": {"Incidents-View"}}
    monkeypatch.setattr("apps.core.utils.viewset_utils.AuthViewSet.get_has_permission", lambda self, *args, **kwargs: False)
    monkeypatch.setattr(
        "apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("cmdb called")),
    )
    incident = _incident()
    response, payload = _call(authenticated_user, incident, {})
    assert payload["result"] is False
    assert response.status_code in (200, 400)


def test_alerts_source_does_not_import_cmdb_services_or_probe_purchase():
    alerts_root = Path(__file__).resolve().parents[1]
    service = (alerts_root / "service" / "incident_impact_topology.py").read_text(encoding="utf-8")
    view = (alerts_root / "views" / "incident.py").read_text(encoding="utf-8")
    assert "apps.cmdb.services" not in service
    assert "apps.cmdb.views" not in service
    assert "apps.cmdb" not in view
    assert "is_installed" not in service
    assert "incident_impact_topology" in service


def test_timeout_exception_identity_stays_rpc_timeout():
    error = RpcTimeoutError("bklite", "incident_impact_topology", 3)
    assert type(error) is RpcTimeoutError
    assert error.namespace == "bklite"
    assert not isinstance(error, SafeLogException)
