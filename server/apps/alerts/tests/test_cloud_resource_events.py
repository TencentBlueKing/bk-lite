"""云资源变化事件的 Webhook 边界。

对照 specs/changes/alert-cloud-resource-events/implementation.md 第 7 节：
固定报文进现有按源 webhook，核对回执和入库字段。CMDB 在查询边界替身。
"""

import json
import logging
from datetime import datetime, timezone

import pytest
from django.core.cache import cache
from rest_framework.test import APIRequestFactory

from apps.alerts.common.source_adapter.cloud_catalog import catalog_text
from apps.alerts.common.source_adapter.cloud_events import AliyunEventBridgeAdapter, TencentEventBusAdapter
from apps.alerts.common.source_adapter.constants import build_cloud_source_config
from apps.alerts.constants.constants import AlarmStrategyType, AlertStatus, LevelType
from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Alert, Event, Level
from apps.alerts.utils.util import encode_team_secret
from apps.alerts.views.receiver import receiver_source_data

ALIYUN = "aliyun_eventbridge"
TENCENT = "tencent_eventbus"
SOURCE_SECRET = "cloud-source-secret"
SENTINEL = "CLOUD-SECRET-SENTINEL"
UTC = timezone.utc


@pytest.fixture
def levels(db):
    for level_id, name in ((0, "严重"), (1, "错误"), (2, "警告"), (3, "提醒")):
        Level.objects.create(
            level_id=level_id,
            level_name=f"L{level_id}",
            level_display_name=name,
            level_type=LevelType.EVENT,
        )


@pytest.fixture
def team_secret():
    return encode_team_secret(SOURCE_SECRET, "1")


@pytest.fixture
def aliyun_source(db, team_secret):
    return _source(ALIYUN, "阿里云 EventBridge", "aliyun", team_secret)


@pytest.fixture
def tencent_source(db, team_secret):
    return _source(TENCENT, "腾讯云事件总线", "tencent", team_secret, query_secret=True)


@pytest.fixture
def instant_strategy(db):
    strategy = AlarmStrategy.objects.create(
        name="云事件即时",
        strategy_type=AlarmStrategyType.INSTANT,
        is_active=True,
        team=[1],
        dispatch_team=[1],
        match_rules=[
            [{"key": "source_name", "operator": "any_of", "value": ["阿里云 EventBridge"]}],
            [{"key": "source_name", "operator": "any_of", "value": ["腾讯云事件总线"]}],
        ],
    )
    from apps.alerts.aggregation.processor.instant_dispatcher import InstantStrategyCache

    InstantStrategyCache.cache_clear()
    cache.clear()
    return strategy


@pytest.fixture(autouse=True)
def stub_cmdb(monkeypatch):
    monkeypatch.setattr(
        "apps.alerts.common.source_adapter.cloud_events.lookup_cloud_instance",
        lambda *_args, **_kwargs: (None, "empty"),
    )


def _source(source_id, name, vendor, team_secret, query_secret=False):
    return AlertSource.objects.create(
        name=name,
        source_id=source_id,
        source_type=source_id,
        secret=SOURCE_SECRET,
        team_secrets={"1": team_secret},
        config=build_cloud_source_config(source_id, catalog_text(vendor), query_secret=query_secret),
        is_active=True,
        is_effective=True,
    )


def _post(source_id, body, secret=None, query=False):
    factory = APIRequestFactory()
    path = f"/api/v1/alerts/api/source/{source_id}/webhook/"
    extra = {}
    if secret and query:
        path = f"{path}?secret={secret}"
    elif secret:
        extra["HTTP_SECRET"] = secret
    request = factory.post(path, data=json.dumps(body), content_type="application/json", **extra)
    return receiver_source_data(request, source_id)


def _aliyun(event_type, status, event_id="e-reboot-1", when="2026-11-26T09:00:00Z", data=None, **extra):
    payload = {
        "id": "delivery-1",
        "source": "acs.ecs",
        "type": event_type,
        "time": when,
        "aliyunaccountid": "1234567890",
        "aliyunregionid": "cn-hangzhou",
        "data": data
        or {
            "eventId": event_id,
            "eventStatus": status,
            "instanceId": "i-test-1",
        },
    }
    payload.update(extra)
    return payload


def _executing(**kwargs):
    return _aliyun("ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executing]", "Executing", **kwargs)


def _events():
    return Event.objects.all()


@pytest.mark.django_db
def test_aliyun_executing_is_stored(levels, aliyun_source, team_secret, instant_strategy):
    response = _post(ALIYUN, _executing(), team_secret)

    assert response.status_code == 200
    event = _events().get()
    assert "i-test-1" in event.title
    assert "因系统错误实例重启" in event.title
    assert "发生" in event.description
    assert "cn-hangzhou" in event.description
    assert "1234567890" in event.description
    assert "恢复" not in event.description
    assert event.level == "0"
    assert event.action == "created"
    assert event.item == "SystemFailure.Reboot"
    assert event.resource_id == "i-test-1"
    assert event.resource_type == "aliyun_ecs"
    assert event.location == "cn-hangzhou"
    assert event.labels["account"] == "1234567890"
    assert event.external_id == "1234567890:e-reboot-1"
    assert event.push_source_id == "default"
    assert event.raw_data["original"]["id"] == "delivery-1"
    assert "_parsed_time" not in event.raw_data["original"]
    assert event.start_time == datetime(2026, 11, 26, 9, 0, tzinfo=UTC)
    assert event.team == [1]
    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_duplicate_delivery_stays_one_row(levels, aliyun_source, team_secret):
    body = _executing()
    assert _post(ALIYUN, body, team_secret).status_code == 200
    response = _post(ALIYUN, body, team_secret)

    assert response.status_code == 200
    assert _events().count() == 1


@pytest.mark.django_db
def test_aliyun_recovery_closes_the_open_alert(levels, aliyun_source, team_secret, instant_strategy, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        assert _post(ALIYUN, _executing(), team_secret).status_code == 200
        response = _post(
            ALIYUN,
            _aliyun("ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executed]", "Executed", when="2026-11-26T10:00:00Z"),
            team_secret,
        )

    assert response.status_code == 200
    recovery = _events().get(action="recovery")
    assert "恢复" in recovery.description
    assert "发生" not in recovery.description
    assert recovery.external_id == "1234567890:e-reboot-1"
    alert = Alert.objects.get()
    assert alert.status == AlertStatus.AUTO_RECOVERY
    assert alert.events.filter(action="recovery").exists()
    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_failed_firing_attaches_to_the_open_alert(levels, aliyun_source, team_secret, instant_strategy):
    assert _post(ALIYUN, _executing(), team_secret).status_code == 200
    response = _post(
        ALIYUN,
        _aliyun("ecs:CloudMonitor:Instance[SystemFailure.Reboot:Failed]", "Failed", when="2026-11-26T09:30:00Z"),
        team_secret,
    )

    assert response.status_code == 200
    failed = _events().get(action="created", start_time=datetime(2026, 11, 26, 9, 30, tzinfo=UTC))
    assert "发生" in failed.description
    assert "失败" in failed.description
    assert failed.level == "0"
    alert = Alert.objects.get()
    assert alert.status in AlertStatus.ACTIVATE_STATUS
    assert set(alert.events.values_list("action", flat=True)) == {"created"}
    assert alert.events.count() == 2


@pytest.mark.django_db
def test_recovery_without_open_alert_does_not_create_one(levels, aliyun_source, team_secret, instant_strategy, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = _post(
            ALIYUN,
            _aliyun("ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executed]", "Executed"),
            team_secret,
        )
    assert response.status_code == 200
    assert _events().count() == 1
    assert Alert.objects.count() == 0

    assert _post(ALIYUN, _executing(when="2026-11-26T11:00:00Z"), team_secret).status_code == 200
    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_stateless_event_does_not_open_alert(levels, aliyun_source, team_secret, instant_strategy):
    body = _aliyun(
        "ecs:Instance:StateChange",
        "",
        data={"resourceId": "i-test-1"},
    )
    response = _post(ALIYUN, body, team_secret)

    assert response.status_code == 200
    event = _events().get()
    assert event.action == "record"
    assert event.level == "3"
    assert "无状态" in event.description
    assert "i-test-1" in event.title
    assert Alert.objects.count() == 0


@pytest.mark.django_db
def test_catalog_skip_returns_200_and_logs_without_payload(levels, aliyun_source, team_secret, caplog):
    caplog.set_level(logging.INFO, logger="alert")
    body = _aliyun("ecs:Snapshot:SnapshotDeleted", "", data={"token": SENTINEL, "snapshotId": "s-1"})
    response = _post(ALIYUN, body, team_secret)

    assert response.status_code == 200
    assert _events().count() == 0
    assert SENTINEL not in response.content.decode()
    skip = [record for record in caplog.records if record.msg == "cloud event skipped source_id=%s event_type=%s outcome=%s"]
    assert skip
    assert skip[0].args == (ALIYUN, "ecs:Snapshot:SnapshotDeleted", "catalog_skip")
    assert SENTINEL not in skip[0].getMessage()
    assert team_secret not in caplog.text
    assert SENTINEL not in caplog.text


@pytest.mark.django_db
def test_array_keeps_recognized_events_and_skips_the_rest(levels, aliyun_source, team_secret, instant_strategy):
    body = [
        _executing(),
        _aliyun("ecs:Instance:StateChange", "", data={"resourceId": "i-state-1"}, id="delivery-state"),
        _aliyun("ecs:Snapshot:SnapshotDeleted", "", data={"snapshotId": "s-1"}, id="delivery-skip"),
    ]
    response = _post(ALIYUN, body, team_secret)

    assert response.status_code == 200
    assert _events().count() == 2
    assert _events().filter(action="created").count() == 1
    assert _events().filter(action="record", resource_id="i-state-1").count() == 1
    assert Alert.objects.count() == 1


@pytest.mark.django_db
def test_non_object_array_is_rejected(levels, aliyun_source, team_secret):
    response = _post(ALIYUN, [_executing(), "bad"], team_secret)
    assert response.status_code == 400
    assert _events().count() == 0


@pytest.mark.django_db
def test_missing_or_source_secret_is_forbidden(levels, aliyun_source, team_secret):
    missing = _post(ALIYUN, _executing())
    source_secret = _post(ALIYUN, _executing(), SOURCE_SECRET)
    assert missing.status_code == 403
    assert source_secret.status_code == 403
    assert _events().count() == 0


@pytest.mark.django_db
def test_unrecognized_body_is_rejected(levels, aliyun_source, tencent_source, team_secret):
    aliyun = _post(ALIYUN, {"hello": "world"}, team_secret)
    tencent = _post(TENCENT, {"business": "bgp-ip"}, team_secret)
    assert aliyun.status_code == 400
    assert tencent.status_code == 400
    assert _events().count() == 0


@pytest.mark.django_db
def test_tencent_cvm_firing_and_recovery(levels, tencent_source, team_secret, instant_strategy, django_capture_on_commit_callbacks):
    firing = {
        "sessionId": "sess-cvm-1",
        "alarmStatus": "1",
        "alarmType": "event",
        "alarmObjInfo": {"region": "ap-guangzhou", "dimensions": {"unInstanceId": "ins-test-1"}},
        "alarmPolicyInfo": {"policyName": "cvm-reboot", "conditions": {"productName": "cvm", "eventName": "guest_reboot"}},
        "firstOccurTime": "2026-11-26 17:00:00",
    }
    with django_capture_on_commit_callbacks(execute=True):
        opened = _post(TENCENT, firing, team_secret)
        firing["alarmStatus"] = "0"
        firing["firstOccurTime"] = "2026-11-26 18:00:00"
        closed = _post(TENCENT, firing, team_secret)

    assert opened.status_code == 200
    assert closed.status_code == 200
    created = _events().get(action="created")
    assert "ins-test-1" in created.title
    assert "发生" in created.description
    assert "ap-guangzhou" in created.description
    assert created.level == "0"
    assert created.item == "guest_reboot"
    assert created.resource_type == "qcloud_cvm"
    assert created.external_id == ":sess-cvm-1"
    assert created.start_time == datetime(2026, 11, 26, 9, 0, tzinfo=UTC)
    assert created.push_source_id == "default"
    assert Alert.objects.get().status == AlertStatus.AUTO_RECOVERY


@pytest.mark.django_db
def test_tencent_query_secret_and_non_cvm_skip(levels, tencent_source, team_secret):
    skipped = {
        "sessionId": "sess-redis-1",
        "alarmStatus": "1",
        "alarmType": "event",
        "alarmPolicyInfo": {"conditions": {"productName": "redis", "eventName": "master_down"}},
        "firstOccurTime": "2026-11-26 17:00:00",
    }
    assert _post(TENCENT, skipped, team_secret).status_code == 200
    assert _events().count() == 0

    firing = {
        "sessionId": "sess-cvm-2",
        "alarmStatus": "1",
        "alarmType": "event",
        "alarmObjInfo": {"region": "ap-guangzhou", "dimensions": {"unInstanceId": "ins-test-2"}},
        "alarmPolicyInfo": {"conditions": {"productName": "cvm", "eventName": "guest_reboot"}},
        "firstOccurTime": "2026-11-26 17:00:00",
    }
    response = _post(TENCENT, firing, team_secret, query=True)
    assert response.status_code == 200
    assert _events().get().resource_id == "ins-test-2"


@pytest.mark.django_db
def test_cmdb_match_outcomes(levels, aliyun_source, team_secret, monkeypatch):
    uuid = "123e4567-e89b-42d3-a456-426614174000"
    monkeypatch.setattr(
        "apps.alerts.common.source_adapter.cloud_events.lookup_cloud_instance",
        lambda *_args, **_kwargs: (uuid, "matched"),
    )
    assert _post(ALIYUN, _executing(), team_secret).status_code == 200
    assert _events().get().cmdb_id == uuid

    Event.objects.all().delete()
    monkeypatch.setattr(
        "apps.alerts.common.source_adapter.cloud_events.lookup_cloud_instance",
        lambda *_args, **_kwargs: (None, "empty"),
    )
    assert _post(ALIYUN, _executing(event_id="e-empty"), team_secret).status_code == 200
    assert not _events().get().cmdb_id

    Event.objects.all().delete()
    monkeypatch.setattr(
        "apps.alerts.common.source_adapter.cloud_events.lookup_cloud_instance",
        lambda *_args, **_kwargs: (None, "ambiguous"),
    )
    assert _post(ALIYUN, _executing(event_id="e-many"), team_secret).status_code == 200
    assert not _events().get().cmdb_id


@pytest.mark.django_db
def test_cmdb_lookup_failure_keeps_event_and_omits_the_error_text(levels, aliyun_source, team_secret, monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="alert")

    def explode(*_args, **_kwargs):
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr("apps.alerts.common.source_adapter.cloud_events.lookup_cloud_instance", explode)
    response = _post(ALIYUN, _executing(), team_secret)

    assert response.status_code == 200
    event = _events().get()
    assert not event.cmdb_id
    failed = [record for record in caplog.records if record.msg.startswith("cloud cmdb lookup failed")]
    assert failed
    assert failed[0].args[-1] == "RuntimeError"
    assert SENTINEL not in failed[0].getMessage()
    assert SENTINEL not in caplog.text
    assert SENTINEL not in response.content.decode()


@pytest.mark.django_db
def test_disk_event_keeps_disk_id_and_looks_up_parent(levels, aliyun_source, team_secret, monkeypatch):
    seen = {}

    def capture(model_id, resource_id, organization_ids):
        seen["call"] = (model_id, resource_id, list(organization_ids))
        return "parent-uuid", "matched"

    monkeypatch.setattr("apps.alerts.common.source_adapter.cloud_events.lookup_cloud_instance", capture)
    body = _aliyun(
        "ecs:CloudMonitor:Disk[ErrorDetected:Executing]",
        "Executing",
        event_id="e-disk-1",
        data={"eventId": "e-disk-1", "eventStatus": "Executing", "diskId": "d-test-1", "ecsInstanceId": "i-parent-1"},
    )
    assert _post(ALIYUN, body, team_secret).status_code == 200
    event = _events().get()
    assert event.resource_id == "d-test-1"
    assert event.resource_type == "aliyun_disk"
    assert event.cmdb_id == "parent-uuid"
    assert event.level == "0"
    assert seen["call"] == ("aliyun_ecs", "i-parent-1", [1])


@pytest.mark.django_db
def test_internal_failure_returns_500(levels, aliyun_source, team_secret, monkeypatch):
    monkeypatch.setattr(
        AliyunEventBridgeAdapter,
        "main",
        lambda self, events=None: {"received": 1, "accepted": 0, "skipped": 0, "errored": 1},
    )
    response = _post(ALIYUN, _executing(), team_secret)
    assert response.status_code == 500
    assert _events().count() == 0


@pytest.mark.django_db
def test_integration_guide_lists_webhook_and_catalog(levels, aliyun_source, tencent_source):
    from apps.alerts.common.source_adapter.cloud_catalog import parse_body
    from apps.alerts.common.source_adapter.cloud_guide import (
        ALIYUN_FIRING_BODY,
        ALIYUN_RECOVERY_BODY,
        ALIYUN_STATE_BODY,
        TENCENT_CLOUDEVENT_BODY,
        TENCENT_FIRING_BODY,
        TENCENT_RECOVERY_BODY,
    )

    aliyun_source.config["url"] = "/api/v1/alerts/api/receiver_data/"
    aliyun = AliyunEventBridgeAdapter(alert_source=aliyun_source)
    guide = aliyun.get_integration_guide("https://alerts.example.com")
    curl = guide["examples"]["CURL"]
    assert guide["webhook_url"] == "https://alerts.example.com/api/v1/alerts/api/source/aliyun_eventbridge/webhook/"
    assert guide["base_info"]["url"] == "/api/v1/alerts/api/source/aliyun_eventbridge/webhook/"
    assert guide["base_info"]["method"] == "POST"
    assert "127.0.0.1" not in guide["webhook_url"]
    loopback = aliyun.get_integration_guide("http://127.0.0.1:8000")
    assert loopback["webhook_url"] == "{url}/api/v1/alerts/api/source/aliyun_eventbridge/webhook/"
    assert "127.0.0.1" not in loopback["examples"]["CURL"]
    from django.test import override_settings

    with override_settings(WEB_BASE_URL="http://10.11.27.147"):
        configured = aliyun.get_integration_guide("http://127.0.0.1:8000")
    assert configured["webhook_url"] == "http://10.11.27.147/api/v1/alerts/api/source/aliyun_eventbridge/webhook/"
    with override_settings(WEB_BASE_URL="http://127.0.0.1:3000"):
        ignored = aliyun.get_integration_guide("http://localhost:8000")
    assert ignored["webhook_url"].startswith("{url}/")
    assert "receiver_data" not in guide["webhook_url"]
    assert guide["headers"]["SECRET"] == "{{TEAM_SECRET}}"
    assert any(row["event"] == "SystemFailure.Reboot" for row in guide["report_fields"])
    assert "report_catalog" in aliyun_source.config["event_fields_desc_mapping"]
    assert "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executing]" in curl
    assert "ecs:CloudMonitor:Instance[SystemFailure.Reboot:Executed]" in curl
    assert "ecs:Instance:StateChange" in curl
    assert "{{TEAM_SECRET}}" in curl
    assert "Jenkins" not in curl
    assert "receiver_data" not in curl
    assert '"source_id": "restful"' not in curl
    assert "ActionTrail" in " ".join(guide["steps"])
    mapping = {row["field"]: row for row in guide["field_mapping"]}
    assert "data.eventId" in mapping["external_id"]["from"]
    assert "data.diskId" in mapping["resource_id"]["from"]
    assert mapping["title"]["field"] == "title"
    firing = next(item for item in guide["example_items"] if item["title"].startswith("发生"))
    assert "title = 因系统错误实例重启" in "\n".join(firing["lands"])
    assert "action = created" in firing["lands"]
    assert "resource_name = web-a" in firing["lands"]
    disk = next(item for item in guide["example_items"] if "磁盘" in item["title"])
    assert "resource_id = d-bp15esw9c01fh0001" in disk["lands"]
    assert "resource_type = aliyun_disk" in disk["lands"]
    assert parse_body("aliyun", ALIYUN_FIRING_BODY)["outcome"] == "accept"
    assert parse_body("aliyun", ALIYUN_RECOVERY_BODY)["event"]["action"] == "recovery"
    assert parse_body("aliyun", ALIYUN_STATE_BODY)["event"]["action"] == "record"

    stored = build_cloud_source_config("aliyun_eventbridge", "catalog")
    assert stored["params"] == {}
    assert "SystemFailure.Reboot:Executing" in stored["examples"]["CURL"]
    assert "Jenkins" not in stored["examples"]["CURL"]
    assert stored["event_fields_mapping"]["title"] == "title"

    tencent = TencentEventBusAdapter(alert_source=tencent_source)
    tencent_guide = tencent.get_integration_guide("https://alerts.example.com", credential="{{TEAM_SECRET}}")
    tencent_curl = tencent_guide["examples"]["CURL"]
    assert tencent_guide["query_secret"] == "secret"
    assert tencent_guide["webhook_url_with_secret"].endswith("?secret={{TEAM_SECRET}}")
    assert "unInstanceId" in tencent_curl
    assert '"alarmStatus": "0"' in tencent_curl
    assert "cvm:ErrorEvent:guest_reboot" in tencent_curl
    assert "?secret={{TEAM_SECRET}}" in tencent_curl
    assert "receiver_data" not in tencent_curl
    assert '"source_id": "restful"' not in tencent_curl
    tencent_mapping = {row["field"]: row for row in tencent_guide["field_mapping"]}
    assert "unInstanceId" in tencent_mapping["resource_id"]["from"]
    assert "subject" in tencent_mapping["resource_id"]["from"]
    tencent_firing = next(item for item in tencent_guide["example_items"] if "监控告警模板" in item["title"])
    cloud_event = next(item for item in tencent_guide["example_items"] if item["title"].startswith("发生：CloudEvent"))
    assert "external_id = 1250000000:sess-cvm-0001" in tencent_firing["lands"]
    assert "external_id = 1250000000:sess-cvm-0001" in cloud_event["lands"]
    alarm_time = parse_body("tencent", TENCENT_FIRING_BODY)["event"]["start_time"]
    cloud_time = parse_body("tencent", TENCENT_CLOUDEVENT_BODY)["event"]["start_time"]
    assert alarm_time == cloud_time
    assert f"start_time = {alarm_time}" in tencent_firing["lands"]
    assert parse_body("tencent", TENCENT_FIRING_BODY)["outcome"] == "accept"
    assert parse_body("tencent", TENCENT_RECOVERY_BODY)["event"]["action"] == "recovery"
    assert parse_body("tencent", TENCENT_CLOUDEVENT_BODY)["outcome"] == "accept"

    stored_tencent = build_cloud_source_config("tencent_eventbus", "catalog", query_secret=True)
    assert stored_tencent["params"] == {}
    assert "?secret={{TEAM_SECRET}}" in stored_tencent["examples"]["CURL"]


def test_lookup_cloud_instance_keeps_a_single_org_match(monkeypatch):
    from apps.alerts.common.source_adapter.cloud_events import _lookup_cloud_instance_impl

    rows = [
        {"inst_uuid": "uuid-1", "organization": [1], "resource_id": "i-test-1"},
        {"inst_uuid": "uuid-2", "organization": [2], "resource_id": "i-test-1"},
    ]

    class Client:
        def __init__(self):
            self.kwargs = {}

        def query_entity(self, label, params, **kwargs):
            self.kwargs = {"label": label, "params": params, **kwargs}
            return rows, len(rows)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    client = Client()
    monkeypatch.setattr("apps.cmdb.graph.drivers.graph_client.GraphClient", lambda **_kwargs: client)
    inst_uuid, outcome = _lookup_cloud_instance_impl("aliyun_ecs", "i-test-1", [1])
    assert (inst_uuid, outcome) == ("uuid-1", "matched")
    assert {"field": "resource_id", "type": "str=", "value": "i-test-1"} in client.kwargs["params"]
    assert 1 in client.kwargs["format_permission_dict"]

    client.query_entity = lambda *_args, **_kwargs: (
        [
            {"inst_uuid": "uuid-1", "organization": [1]},
            {"inst_uuid": "uuid-2", "organization": [1]},
        ],
        2,
    )
    assert _lookup_cloud_instance_impl("aliyun_ecs", "i-test-1", [1]) == (None, "ambiguous")

    client.query_entity = lambda *_args, **_kwargs: ([], 0)
    assert _lookup_cloud_instance_impl("aliyun_ecs", "i-test-1", [1]) == (None, "empty")
