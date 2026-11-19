"""事件生成告警和事故后，影响拓扑经 NATS 处理函数走完一层关系和告警分页。"""

import json
from pathlib import Path

import pytest
from django.db import transaction
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.aggregation.builder.alert_builder import AlertBuilder
from apps.alerts.constants.constants import AlertStatus, LevelType, SessionStatus
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event, Incident, Level
from apps.alerts.views.incident import IncidentModelViewSet
from apps.cmdb.models.ci_context import CmdbCiContext
from apps.cmdb.nats.nats import incident_impact_topology
from apps.cmdb.tests.test_incident_impact_topology import _Graph

HOST = "00000000-0000-4000-8000-000000000001"
NIC = "00000000-0000-4000-8000-000000000014"
RACK = "00000000-0000-4000-8000-000000000013"
APP = "00000000-0000-4000-8000-000000000003"
SYSTEM = "00000000-0000-4000-8000-000000000020"
MYSQL = "00000000-0000-4000-8000-000000000016"
FOREIGN = "00000000-0000-4000-8000-000000000099"

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _request(path, user, data):
    request = APIRequestFactory().post(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _render(response):
    if hasattr(response, "render"):
        response.render()
    return json.loads(response.content)


def _event(source, event_id, monitor_id, cmdb_id, resource_type, resource_name, level):
    return Event.objects.create(
        source=source,
        raw_data={},
        title=resource_name,
        description=resource_name,
        level=level,
        start_time=timezone.now(),
        event_id=event_id,
        item="cpu_usage",
        monitor_id=monitor_id,
        cmdb_id=cmdb_id,
        resource_id=monitor_id,
        resource_type=resource_type,
        resource_name=resource_name,
        push_source_id="lite-monitor",
        labels={"sample": event_id},
    )


def _alert(strategy, fingerprint, event, level, title):
    now = timezone.now()
    with transaction.atomic():
        return AlertBuilder.create_or_update_alert(
            {
                "fingerprint": fingerprint,
                "event_ids": [event.event_id],
                "alert_level": level,
                "alert_title": title,
                "alert_description": title,
                "first_event_time": now,
                "last_event_time": now,
            },
            strategy,
        )


def _graph():
    entities = [
        {"inst_uuid": HOST, "inst_name": "web-01", "model_id": "host"},
        {"inst_uuid": NIC, "inst_name": "nic-1", "model_id": "nic"},
        {"inst_uuid": RACK, "inst_name": "rack-1", "model_id": "rack"},
        {"inst_uuid": APP, "inst_name": "支付中台", "model_id": "application"},
        {"inst_uuid": SYSTEM, "inst_name": "交易系统", "model_id": "system"},
    ]
    edges = [
        {
            "src_inst_uuid": NIC,
            "dst_inst_uuid": HOST,
            "asst_id": "belong",
            "model_asst_id": "nic_belong_host",
            "src_model_id": "nic",
            "dst_model_id": "host",
        },
        {
            "src_inst_uuid": HOST,
            "dst_inst_uuid": RACK,
            "asst_id": "belong",
            "model_asst_id": "host_belong_rack",
            "src_model_id": "host",
            "dst_model_id": "rack",
        },
    ]
    associations = [
        {"model_asst_id": "nic_belong_host", "asst_id": "belong", "src_model_id": "nic", "dst_model_id": "host"},
        {"model_asst_id": "host_belong_rack", "asst_id": "belong", "src_model_id": "host", "dst_model_id": "rack"},
    ]
    return _Graph(entities, edges, model_associations=associations)


def test_event_alert_incident_shows_related_alerts_without_merging_them(monkeypatch, superuser):
    AlertBuilder.clear_event_cache()
    AlertBuilder._valid_alert_levels = None
    Level.objects.create(level_id=0, level_name="fatal", level_display_name="致命", level_type=LevelType.ALERT)
    Level.objects.create(level_id=1, level_name="error", level_display_name="错误", level_type=LevelType.ALERT)
    source = AlertSource.objects.create(name="NATS", source_id="nats-impact-chain", source_type="nats", secret="x")
    strategy = AlarmStrategy.objects.create(
        name="影响拓扑链路",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        params={"window_size": 10},
    )
    host_alert = _alert(
        strategy,
        "impact-host",
        _event(source, "EVENT-HOST", "mon-host", HOST, "主机", "web-01", "1"),
        "1",
        "主机宕机",
    )
    nic_alerts = []
    for index in range(21):
        level = "0" if index == 0 else "1"
        nic_alerts.append(
            _alert(
                strategy,
                f"impact-nic-{index}",
                _event(source, f"EVENT-NIC-{index}", f"mon-nic-{index}", NIC, "网卡", f"nic-{index}", level),
                level,
                f"nic-{index}",
            )
        )
    mysql_alert = _alert(
        strategy,
        "impact-mysql",
        _event(source, "EVENT-MYSQL", "mon-mysql", MYSQL, "数据库", "mysql-1", "1"),
        "1",
        "数据库不可用",
    )
    observing = _alert(
        strategy,
        "impact-observing",
        _event(source, "EVENT-OBS", "mon-obs", NIC, "网卡", "observing", "1"),
        "1",
        "观察中的网卡",
    )
    observing.is_session_alert = True
    observing.session_status = SessionStatus.OBSERVING
    observing.save(update_fields=["is_session_alert", "session_status"])
    closed = _alert(
        strategy,
        "impact-closed",
        _event(source, "EVENT-CLOSED", "mon-closed", NIC, "网卡", "closed", "1"),
        "1",
        "已关闭的网卡",
    )
    closed.status = AlertStatus.CLOSED
    closed.save(update_fields=["status"])

    incident = Incident.objects.create(incident_id="INC-CHAIN", level="1", title="主机事故", fingerprint="impact-chain", team=[1])
    incident.alert.add(host_alert)
    before = set(incident.alert.values_list("id", flat=True))

    for ci_uuid, ci_model, layer in ((HOST, "host", 1), (MYSQL, "mysql", 2)):
        CmdbCiContext.objects.create(
            ci_uuid=ci_uuid,
            context="application",
            root_uuid=APP,
            root_model="application",
            ci_model=ci_model,
            organization=[1],
            system_uuid=SYSTEM,
            layer=layer,
        )

    graph = _graph()
    monkeypatch.setattr("apps.cmdb.services.incident_impact_topology.GraphClient", lambda *args, **kwargs: graph)
    monkeypatch.setattr("apps.cmdb.services.incident_impact_topology._viewer", lambda user_info: (lambda entity: True))
    monkeypatch.setattr("apps.cmdb.services.incident_impact_topology._organization_ids", lambda user_info: [1])

    def rpc(self, inst_uuids=None, user_info=None, **kwargs):
        return incident_impact_topology(inst_uuids=inst_uuids, user_info=user_info)

    monkeypatch.setattr("apps.alerts.service.incident_impact_topology.CMDB.incident_impact_topology", rpc)

    response = IncidentModelViewSet.as_view({"post": "impact_topology"})(
        _request(f"/alerts/api/incident/{incident.id}/impact_topology/", superuser, {}),
        pk=str(incident.id),
    )
    payload = _render(response)
    assert response.status_code == 200
    assert payload["result"] is True
    nodes = {item["inst_uuid"]: item for item in payload["data"]["nodes"]}
    assert nodes[HOST]["role"] == "seed"
    assert nodes[HOST]["alert_state"] == "incident"
    assert nodes[HOST]["alert_count"] == 1
    assert nodes[NIC]["role"] == "related"
    assert nodes[NIC]["alert_state"] == "active"
    assert nodes[NIC]["alert_count"] == 21
    assert nodes[RACK]["alert_state"] == "clear"
    assert nodes[RACK]["role"] == "related"
    assert nodes[APP]["role"] == "application"
    assert nodes[APP]["alert_count"] == 2
    assert nodes[SYSTEM]["role"] == "system"
    assert nodes[SYSTEM]["alert_count"] == 2
    assert MYSQL not in nodes
    assert {item["asst_id"] for item in payload["data"]["links"]} >= {"belong", "context_application", "context_system"}

    page = IncidentModelViewSet.as_view({"post": "impact_topology_alerts"})(
        _request(
            f"/alerts/api/incident/{incident.id}/impact_topology_alerts/",
            superuser,
            {"inst_uuid": NIC, "page": 1},
        ),
        pk=str(incident.id),
    )
    first = _render(page)
    assert first["result"] is True
    assert first["data"]["count"] == 21
    assert len(first["data"]["items"]) == 20
    assert first["data"]["page_size"] == 20
    assert first["data"]["items"][0]["title"] == "nic-0"
    assert first["data"]["items"][0]["level"] == "0"
    assert "观察中的网卡" not in {item["title"] for item in first["data"]["items"]}
    assert "已关闭的网卡" not in {item["title"] for item in first["data"]["items"]}

    second = _render(
        IncidentModelViewSet.as_view({"post": "impact_topology_alerts"})(
            _request(
                f"/alerts/api/incident/{incident.id}/impact_topology_alerts/",
                superuser,
                {"inst_uuid": NIC, "page": 2},
            ),
            pk=str(incident.id),
        )
    )
    assert second["data"]["count"] == 21
    assert [item["title"] for item in second["data"]["items"]] == ["nic-20"]

    application = _render(
        IncidentModelViewSet.as_view({"post": "impact_topology_alerts"})(
            _request(
                f"/alerts/api/incident/{incident.id}/impact_topology_alerts/",
                superuser,
                {"inst_uuid": APP, "page": 1},
            ),
            pk=str(incident.id),
        )
    )
    listed = {item["title"]: item for item in application["data"]["items"]}
    assert listed["主机宕机"]["in_incident"] is True
    assert listed["数据库不可用"]["in_incident"] is False
    assert mysql_alert.id not in before

    missing = _render(
        IncidentModelViewSet.as_view({"post": "impact_topology_alerts"})(
            _request(
                f"/alerts/api/incident/{incident.id}/impact_topology_alerts/",
                superuser,
                {"inst_uuid": FOREIGN, "page": 1},
            ),
            pk=str(incident.id),
        )
    )
    assert missing["result"] is False
    assert missing["data"] == {}

    rejected = _render(
        IncidentModelViewSet.as_view({"post": "impact_topology_alerts"})(
            _request(
                f"/alerts/api/incident/{incident.id}/impact_topology_alerts/",
                superuser,
                {"inst_uuid": NIC, "page": 1, "page_size": 10},
            ),
            pk=str(incident.id),
        )
    )
    assert rejected["result"] is False

    incident.refresh_from_db()
    assert set(incident.alert.values_list("id", flat=True)) == before
    source_text = Path(__file__).resolve().parents[1].joinpath("service", "incident_impact_topology.py").read_text(encoding="utf-8")
    assert "apps.cmdb.services" not in source_text
    assert "apps.cmdb.models" not in source_text
