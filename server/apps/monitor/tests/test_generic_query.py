"""监控通用查询的上限、缺测和告警时间范围。"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy
from apps.monitor.services.generic_query import (
    GenericQueryError,
    build_metric_result,
    metric_instance_labels,
    query_alert_counts,
    query_alert_details,
    query_alert_distribution,
    query_instance_counts,
    query_instances,
    validate_metric_request,
)
from apps.monitor.services.generic_query_limits import (
    ALERT_DETAIL_MAX,
    ALERT_RANGE_MAX_SECONDS,
    DETAIL_PAGE_SIZE_MAX,
    INSTANCE_LIST_MAX,
    METRIC_INSTANCE_MAX,
    METRIC_POINTS_MAX,
    METRIC_SERIES_MAX,
)

pytestmark = pytest.mark.django_db


def _object():
    return MonitorObject.objects.create(name="host-object", level="base")


def _instance(obj, instance_id, *, active=True, cmdb_id="", name=""):
    return MonitorInstance.objects.create(
        id=instance_id,
        name=name or instance_id,
        monitor_object=obj,
        is_active=active,
        cmdb_id=cmdb_id or None,
        ip="10.0.0.8",
    )


def test_monitor_instance_detail_keeps_identity_and_the_full_count():
    from apps.node_mgmt.models.cloud_region import CloudRegion

    obj = _object()
    region = CloudRegion.objects.create(name="生产")
    enabled = _instance(obj, "host-1", cmdb_id="cmdb-1", name="web")
    enabled.summary_facts = {"asset.ip": "10.1.1.1"}
    enabled.cloud_region_id = region.id
    enabled.save(update_fields=["summary_facts", "cloud_region_id"])
    _instance(obj, "host-2", active=False, name="idle")

    detail = query_instances(
        MonitorInstance.objects.filter(monitor_object=obj),
        analysis_mode="detail",
        page=1,
        page_size=20,
    )
    stopped = query_instances(
        MonitorInstance.objects.filter(monitor_object=obj),
        analysis_mode="detail",
        status="inactive",
        page=1,
        page_size=20,
    )

    assert detail["count"] == 2
    assert "unit" not in detail
    assert "aggregation" not in detail
    assert "fields" not in detail
    enabled_row = next(item for item in detail["items"] if item["instance_id"] == "host-1")
    assert enabled_row["ip"] == "10.1.1.1"
    assert enabled_row["cloud_region"] == "生产"
    assert enabled_row["cmdb_id"] == "cmdb-1"
    assert enabled_row["monitor_object_id"] == obj.name
    assert enabled_row["status"] == "启用"
    assert "cmdb_bind_status" not in enabled_row
    stopped_row = stopped["items"][0]
    assert stopped["count"] == 1
    assert stopped_row["status"] == "停用"
    assert stopped_row["cmdb_id"] == ""
    assert stopped_row["ip"] == "10.0.0.8"


def test_monitor_instance_column_uses_the_language_display_name(monkeypatch):
    obj = MonitorObject.objects.create(name="Host", display_name="库内展示名", level="base")
    _instance(obj, "host-1", name="web")

    class Loader:
        def __init__(self, app, default_lang):
            self.lang = default_lang

        def get(self, key, default=None):
            if self.lang == "zh-Hans" and key == "monitor_object.Host":
                return "主机"
            return default

    monkeypatch.setattr("apps.monitor.services.generic_query.LanguageLoader", Loader)
    detail = query_instances(
        MonitorInstance.objects.filter(monitor_object=obj),
        analysis_mode="detail",
        locale="zh-Hans",
        page=1,
        page_size=20,
    )
    assert detail["items"][0]["monitor_object_id"] == "主机"

    monkeypatch.setattr(
        "apps.monitor.services.generic_query.LanguageLoader",
        type("EmptyLoader", (), {"__init__": lambda self, app, default_lang: None, "get": lambda self, key, default=None: None}),
    )
    stored = query_instances(
        MonitorInstance.objects.filter(monitor_object=obj),
        analysis_mode="detail",
        locale="en",
        page=1,
        page_size=20,
    )
    assert stored["items"][0]["monitor_object_id"] == "库内展示名"


def test_monitor_instance_rejects_filters_distribution_and_missing_ids():
    obj = _object()
    _instance(obj, "host-1", name="alpha")
    base = MonitorInstance.objects.filter(monitor_object=obj)
    with pytest.raises(GenericQueryError, match="分组"):
        query_instances(base, analysis_mode="detail", group_by="status")
    with pytest.raises(GenericQueryError, match="分析方式不受支持"):
        query_instances(base, analysis_mode="count")
    with pytest.raises(GenericQueryError, match="无权访问"):
        query_instances(base, analysis_mode="detail", instance_ids=["host-1", "gone"])


def test_instance_counts_is_one_row_and_ignores_the_list_cap(monkeypatch):
    obj = _object()
    _instance(obj, "host-1")
    _instance(obj, "host-2", active=False)
    base = MonitorInstance.objects.filter(monitor_object=obj)
    assert query_instance_counts(base) == [{"instance_count": 2}]
    assert query_instance_counts(base, status="inactive") == [{"instance_count": 1}]
    monkeypatch.setattr("apps.monitor.services.generic_query.INSTANCE_LIST_MAX", 1)
    assert query_instance_counts(base) == [{"instance_count": 2}]
    with pytest.raises(GenericQueryError, match="实例状态不受支持"):
        query_instance_counts(base, status="paused")


def test_instance_count_handler_counts_one_object_inside_the_org(monkeypatch):
    from apps.monitor.models.monitor_object import MonitorInstanceOrganization
    from apps.monitor.nats.generic_query import query_monitor_instance_counts

    host = _object()
    other = MonitorObject.objects.create(name="db-object", level="base")
    kept = _instance(host, "host-1", name="web")
    stopped = _instance(host, "host-2", active=False, name="idle")
    deleted = _instance(host, "host-3", name="gone")
    deleted.is_deleted = True
    deleted.save(update_fields=["is_deleted"])
    outsider = _instance(other, "db-1", name="mysql")
    _instance(host, "host-4", name="other-org")
    for item in (kept, stopped, deleted, outsider):
        MonitorInstanceOrganization.objects.create(monitor_instance=item, organization=1)
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        lambda user_info: (user_info, 1, False, [1], True, None),
    )
    user_info = {"user": "ada", "team": 1}
    counted = query_monitor_instance_counts(monitor_object_id=host.id, user_info=user_info)
    assert counted == {"result": True, "data": [{"instance_count": 2}], "message": ""}
    active = query_monitor_instance_counts(monitor_object_id=host.id, status="active", user_info=user_info)
    assert active["data"] == [{"instance_count": 1}]
    empty = query_monitor_instance_counts(monitor_object_id=other.id, status="inactive", user_info=user_info)
    assert empty["data"] == [{"instance_count": 0}]
    missing = query_monitor_instance_counts(monitor_object_id="", user_info=user_info)
    assert missing["result"] is False
    assert "不能为空" in missing["message"]
    absent = query_monitor_instance_counts(monitor_object_id="999999", user_info=user_info)
    assert absent["result"] is False
    assert "不存在或无权访问" in absent["message"]
    paged = query_monitor_instance_counts(monitor_object_id=host.id, page=1, page_size=10, user_info=user_info)
    assert paged["result"] is False
    assert "分页" in paged["message"]
    ordered = query_monitor_instance_counts(monitor_object_id=host.id, order_by="name", user_info=user_info)
    assert ordered["result"] is False
    assert "排序" in ordered["message"]
    ranged = query_monitor_instance_counts(monitor_object_id=host.id, instance_ids=["host-1"], user_info=user_info)
    assert ranged["result"] is False
    assert "实例范围" in ranged["message"]


def test_instance_count_handler_does_not_count_without_permission(monkeypatch):
    from apps.monitor.models.monitor_object import MonitorInstanceOrganization
    from apps.monitor.nats.generic_query import query_monitor_instance_counts

    host = _object()
    item = _instance(host, "host-1")
    MonitorInstanceOrganization.objects.create(monitor_instance=item, organization=1)
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        lambda user_info: (user_info, 1, False, [1], False, None),
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_monitor_instance_permission",
        lambda monitor_object_id, user_info: ({}, None),
    )
    result = query_monitor_instance_counts(monitor_object_id=host.id, user_info={"user": "ada", "team": 1})
    assert result["result"] is False
    assert result["data"] == {"status": "forbidden"}
    assert "无权限" in result["message"]


def test_monitor_instance_page_size_and_statistics_group_limits():
    obj = _object()
    _instance(obj, "host-1")
    with pytest.raises(GenericQueryError, match=str(DETAIL_PAGE_SIZE_MAX)):
        query_instances(
            MonitorInstance.objects.all(),
            analysis_mode="detail",
            page=1,
            page_size=DETAIL_PAGE_SIZE_MAX + 1,
        )


def test_monitor_instance_is_a_list_until_page_is_filled(monkeypatch):
    obj = _object()
    _instance(obj, "host-1", name="web")
    _instance(obj, "host-2", name="db")
    queryset = MonitorInstance.objects.filter(monitor_object=obj)
    rows = query_instances(queryset, analysis_mode="detail")
    assert [item["instance_id"] for item in rows] == ["host-1", "host-2"]
    assert "items" not in rows[0]
    with pytest.raises(GenericQueryError, match="必须同时填写"):
        query_instances(queryset, analysis_mode="detail", page=1)
    paged = query_instances(queryset, analysis_mode="detail", page=1, page_size=1)
    assert paged["count"] == 2
    assert [item["instance_id"] for item in paged["items"]] == ["host-1"]
    monkeypatch.setattr("apps.monitor.services.generic_query.INSTANCE_LIST_MAX", 1)
    with pytest.raises(GenericQueryError, match=str(1)):
        query_instances(queryset, analysis_mode="detail")
    assert INSTANCE_LIST_MAX == 500


def test_alert_detail_is_a_list_until_page_is_filled(monkeypatch):
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index in range(2):
        MonitorAlert.objects.create(
            monitor_instance_id=f"host-{index}",
            monitor_instance_name=f"host-{index}",
            level="warning",
            status="new",
            alert_type="alert",
            start_event_time=moment,
        )
    rows = query_alert_details(MonitorAlert.objects.all())
    assert isinstance(rows, list)
    assert len(rows) == 2
    assert "items" not in rows[0]
    with pytest.raises(GenericQueryError, match="必须同时填写"):
        query_alert_details(MonitorAlert.objects.all(), page=1)
    paged = query_alert_details(MonitorAlert.objects.all(), page=1, page_size=1)
    assert paged["count"] == 2
    assert len(paged["items"]) == 1
    assert paged["page"] == 1
    monkeypatch.setattr("apps.monitor.services.generic_query.ALERT_DETAIL_MAX", 1)
    with pytest.raises(GenericQueryError, match=str(1)):
        query_alert_details(MonitorAlert.objects.all())
    assert ALERT_DETAIL_MAX == 500


def test_monitor_instance_list_stays_in_id_order_and_rejects_sort():
    from apps.monitor.nats.generic_query import query_monitor_instances

    obj = _object()
    _instance(obj, "host-2", name="a")
    _instance(obj, "host-1", name="b")
    rows = query_instances(MonitorInstance.objects.filter(monitor_object=obj), analysis_mode="detail")
    assert [item["instance_id"] for item in rows] == ["host-1", "host-2"]
    rejected = query_monitor_instances(monitor_object_id=obj.id, order_by="name", order_dir="asc")
    assert rejected["result"] is False
    assert "不支持排序" in rejected["message"]


def test_alert_history_requires_time_and_empty_status_means_active():
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    MonitorAlert.objects.create(
        monitor_instance_id="host-1",
        level="warning",
        status="new",
        alert_type="alert",
        start_event_time=moment,
    )
    MonitorAlert.objects.create(
        monitor_instance_id="host-2",
        level="critical",
        status="closed",
        alert_type="alert",
        start_event_time=moment,
    )
    active = query_alert_counts(MonitorAlert.objects.all())
    assert active == [{"alert_count": 1}]
    with pytest.raises(GenericQueryError, match="必须填写时间"):
        query_alert_counts(MonitorAlert.objects.all(), status=["new", "closed"])
    ranged = query_alert_counts(
        MonitorAlert.objects.all(),
        status=["new", "closed"],
        time_field="start_event_time",
        time_range=[moment.isoformat(), (moment + timedelta(days=1)).isoformat()],
    )
    assert ranged == [{"alert_count": 2}]


def test_metric_point_and_instance_limits_fail_before_query():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    step_seconds = 60
    too_long = start + timedelta(seconds=step_seconds * METRIC_POINTS_MAX)
    with pytest.raises(GenericQueryError, match="两端"):
        validate_metric_request(
            instance_ids=["host-1"],
            time_range=[start.isoformat(), too_long.isoformat()],
            step="60s",
        )
    exact = validate_metric_request(
        instance_ids=["host-1"],
        time_range=[start.isoformat(), (start + timedelta(seconds=step_seconds * (METRIC_POINTS_MAX - 1))).isoformat()],
        step="60s",
    )
    assert exact["points"] == METRIC_POINTS_MAX
    with pytest.raises(GenericQueryError, match=str(METRIC_INSTANCE_MAX)):
        validate_metric_request(
            instance_ids=[f"host-{index}" for index in range(METRIC_INSTANCE_MAX + 1)],
            time_range=[start.isoformat(), (start + timedelta(minutes=5)).isoformat()],
            step="60s",
        )
    with pytest.raises(GenericQueryError, match="实例范围不能为空"):
        validate_metric_request(instance_ids=[], time_range=[start.isoformat(), (start + timedelta(minutes=5)).isoformat()], step="60s")
    with pytest.raises(GenericQueryError, match="步长最短 1 秒"):
        validate_metric_request(
            instance_ids=["host-1"],
            time_range=[start.isoformat(), (start + timedelta(minutes=5)).isoformat()],
            step=0.4,
        )
    omitted = validate_metric_request(
        instance_ids=["missing-host"],
        time_range=[start.isoformat(), (start + timedelta(minutes=15)).isoformat()],
        step=None,
    )
    assert omitted["step"] == "9s"
    obj = _object()
    slow = _instance(obj, "slow-host")
    slow.interval = 60
    slow.save(update_fields=["interval"])
    MonitorInstanceOrganization.objects.create(monitor_instance=slow, organization=7)
    foreign = _instance(obj, "foreign-host")
    foreign.interval = 300
    foreign.save(update_fields=["interval"])
    MonitorInstanceOrganization.objects.create(monitor_instance=foreign, organization=9)
    floored = validate_metric_request(
        instance_ids=["slow-host", "foreign-host"],
        time_range=[start.isoformat(), (start + timedelta(minutes=15)).isoformat()],
        step="",
        organization_ids=[7],
    )
    assert floored["step"] == "60s"
    outside = validate_metric_request(
        instance_ids=["foreign-host"],
        time_range=[start.isoformat(), (start + timedelta(minutes=15)).isoformat()],
        step="",
        organization_ids=[7],
    )
    assert outside["step"] == "9s"


def test_metric_rows_keep_each_point_and_open_dimensions():
    overflow = {"status": "success", "data": {"result": [{"metric": {}, "values": [[1, "1"]]} for _ in range(METRIC_SERIES_MAX + 1)]}}
    with pytest.raises(GenericQueryError, match=str(METRIC_SERIES_MAX)):
        build_metric_result(response=overflow, unit="%", requested_ids=["a"])

    missing = build_metric_result(
        response={"status": "success", "data": {"result": []}},
        unit="%",
        requested_ids=["a"],
    )
    assert missing == []

    zero = build_metric_result(
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "a"}, "values": [[1, "0"]]}]}},
        unit="%",
        requested_ids=["a"],
    )
    assert len(zero) == 1
    assert zero[0]["instance_id"] == "a"
    assert zero[0]["value"] == 0
    assert zero[0]["unit"] == "%"
    assert zero[0]["series"] == "a"
    assert "aggregation" not in zero[0]

    separate = build_metric_result(
        response={
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance_id": "a"}, "values": [[1, "1"], [2, "3"]]},
                    {"metric": {"instance_id": "b", "ifDescr": "eth0"}, "values": [[1, "10"]]},
                ]
            },
        },
        unit="%",
        requested_ids=["a", "b"],
        instance_names={"b": "网卡主机"},
    )
    assert [item["value"] for item in separate if item["instance_id"] == "a"] == [1.0, 3.0]
    nic = next(item for item in separate if item["instance_id"] == "b")
    assert nic["instance_name"] == "网卡主机"
    assert nic["series"] == "网卡主机 ifDescr=eth0"
    assert nic["ifDescr"] == "eth0"
    assert nic["value"] == 10

    partial = build_metric_result(
        response={
            "status": "success",
            "data": {"result": [{"metric": {"instance_id": "a"}, "values": [[1, "1"], [2, "NaN"], [3, "0"]]}]},
        },
        unit="%",
        requested_ids=["a", "b"],
        instance_names={"a": "分块演示-主机-01"},
    )
    assert [item["value"] for item in partial] == [1.0, None, 0.0]
    assert partial[0]["series"] == "分块演示-主机-01"
    assert partial[0]["instance_id"] == "a"
    assert partial[0]["instance_name"] == "分块演示-主机-01"
    assert partial[0]["time"]

    split = build_metric_result(
        response={
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance_id": "host", "device": "sda", "path": "/"}, "values": [[1, "40"]]},
                    {"metric": {"instance_id": "host", "device": "sdb", "path": "/data"}, "values": [[1, "80"]]},
                ]
            },
        },
        unit="%",
        requested_ids=["host"],
    )
    by_series = {item["series"]: item for item in split}
    assert set(by_series) == {"host device=sda, path=/", "host device=sdb, path=/data"}
    assert by_series["host device=sda, path=/"]["value"] == 40
    assert by_series["host device=sdb, path=/data"]["device"] == "sdb"


def test_metric_table_uses_the_instance_name():
    obj = _object()
    _instance(obj, "mock-disk-split-01", name="分块演示-主机-01")
    _instance(obj, "('demo-web-01',)", name="演示网站")
    blank = _instance(obj, "blank-name", name="temporary")
    blank.name = ""
    blank.save(update_fields=["name"])

    labels = metric_instance_labels(["mock-disk-split-01", "('demo-web-01',)", "blank-name"])
    assert labels["mock-disk-split-01"] == "分块演示-主机-01"
    assert labels["demo-web-01"] == "演示网站"
    assert labels["blank-name"] == "blank-name"

    named = build_metric_result(
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "demo-web-01"}, "values": [[1, "0"]]}]}},
        unit="%",
        requested_ids=["demo-web-01", "blank-name"],
        instance_names=labels,
    )
    assert len(named) == 1
    assert named[0]["instance_id"] == "demo-web-01"
    assert named[0]["instance_name"] == "演示网站"
    assert named[0]["series"] == "演示网站"
    assert named[0]["value"] == 0


def test_metric_result_matches_storage_key_to_returned_labels():
    names = {"('web-01',)": "网站主机", "web-01": "网站主机", "plain-host": "裸主机"}
    returned = {
        "status": "success",
        "data": {"result": [{"metric": {"instance_id": "web-01"}, "values": [[1700000000, "40"]]}]},
    }
    latest = build_metric_result(
        response=returned,
        unit="percent",
        requested_ids=["('web-01',)"],
        instance_names=names,
    )
    assert latest[0]["instance_id"] == "web-01"
    assert latest[0]["instance_name"] == "网站主机"
    assert latest[0]["series"] == "网站主机"
    assert latest[0]["value"] == 40.0

    plain = build_metric_result(
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "plain-host"}, "values": [[1, "3"]]}]}},
        unit="percent",
        requested_ids=["plain-host"],
        instance_names=names,
    )
    assert [(item["instance_name"], item["value"]) for item in plain] == [("裸主机", 3.0)]

    pod_names = {"('cluster-a', 'nginx-1')": "前端 Pod", "('cluster-a', 'nginx-2')": "后端 Pod"}
    pods = build_metric_result(
        response={
            "status": "success",
            "data": {
                "result": [
                    {"metric": {"instance_id": "cluster-a", "pod": "nginx-1"}, "values": [[1, "12"]]},
                    {"metric": {"instance_id": "cluster-a", "pod": "nginx-2"}, "values": [[1, "8"]]},
                ]
            },
        },
        unit="percent",
        requested_ids=["('cluster-a', 'nginx-1')", "('cluster-a', 'nginx-2')"],
        instance_names=pod_names,
        identity_keys=["instance_id", "pod"],
    )
    assert [(item["instance_name"], item["series"], item["value"]) for item in pods] == [
        ("前端 Pod", "前端 Pod", 12.0),
        ("后端 Pod", "后端 Pod", 8.0),
    ]
    assert "pod" not in pods[0]

    absent = build_metric_result(
        response={"status": "success", "data": {"result": []}},
        unit="percent",
        requested_ids=["('web-01',)"],
        instance_names=names,
    )
    assert absent == []


def test_empty_aggregation_keeps_declared_dimensions(mocker):
    from types import SimpleNamespace

    from apps.monitor.nats.generic_query import query_monitor_metric

    captured = {}

    def prepare(self, payload):
        del self
        captured.update(payload)
        return SimpleNamespace(
            metric=SimpleNamespace(
                dimensions=[{"name": "device"}],
                instance_id_keys=["instance_id"],
                unit="%",
                monitor_object=SimpleNamespace(instance_id_keys=["instance_id"]),
            ),
            query="avg(metric)",
            instance_ids=("mock-disk-split-01",),
        )

    mocker.patch(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        return_value=(SimpleNamespace(username="admin", domain="domain", is_superuser=False), 1, False, frozenset({1}), False, None),
    )
    mocker.patch("apps.monitor.nats.generic_query.AuthorizedMetricQueryService.prepare", prepare)
    mocker.patch("apps.monitor.nats.generic_query.metric_instance_labels", return_value={})
    queried = mocker.patch("apps.monitor.nats.generic_query.VictoriaMetricsAPI")
    queried.return_value.query_range.return_value = {"status": "success", "data": {"result": []}}
    result = query_monitor_metric(
        metric_id="507",
        monitor_object_id="1",
        instance_ids=["mock-disk-split-01"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="5m",
        aggregation="",
        user_info={"user": {"username": "admin"}, "team": "1", "domain": "domain"},
    )
    assert result["result"] is True
    assert captured["aggregation"] == "AVG"
    assert captured["grouping"] is None
    assert captured["step"] == "5m"
    queried.return_value.query_range.assert_called_once()


def test_nats_statistics_uses_persisted_superuser_when_caller_claims_false(mocker):
    from types import SimpleNamespace

    from apps.monitor.nats.generic_query import query_monitor_metric

    captured = {}

    class FakeService:
        def __init__(self, *, user, current_team, include_children, organization_scope=None):
            captured["user"] = user
            captured["scope"] = organization_scope

        def prepare(self, payload):
            captured["grouping"] = payload.get("grouping")
            raise RuntimeError("stop after scope")

    mocker.patch(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        return_value=(SimpleNamespace(username="admin", domain="domain"), 7, True, frozenset({7, 8}), True, None),
    )
    mocker.patch("apps.monitor.nats.generic_query.AuthorizedMetricQueryService", FakeService)
    result = query_monitor_metric(
        metric_id="507",
        instance_ids=["host-1"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="5m",
        analysis_mode="series",
        aggregation="avg",
        user_info={"user": "admin", "domain": "domain", "team": 7, "include_children": True, "is_superuser": False},
    )
    assert result["result"] is False
    assert captured["user"].is_superuser is True
    assert captured["scope"] == frozenset({7, 8})
    assert captured["grouping"] == "instance"


def test_nats_statistics_rejects_forged_superuser_claim_for_object_permissions(mocker):
    from types import SimpleNamespace

    from apps.monitor.nats.generic_query import query_monitor_metric

    captured = {}

    class FakeService:
        def __init__(self, *, user, current_team, include_children, organization_scope=None):
            captured["user"] = user

        def prepare(self, payload):
            raise RuntimeError("stop after scope")

    mocker.patch(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        return_value=(SimpleNamespace(username="admin", domain="domain"), 7, False, frozenset({7}), False, None),
    )
    mocker.patch("apps.monitor.nats.generic_query.AuthorizedMetricQueryService", FakeService)
    query_monitor_metric(
        metric_id="507",
        instance_ids=["host-1"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="5m",
        analysis_mode="series",
        aggregation="avg",
        user_info={"user": "admin", "domain": "domain", "team": 7, "include_children": False, "is_superuser": True},
    )
    assert captured["user"].is_superuser is False


def test_metric_handler_rejects_non_list_filters():
    from apps.monitor.nats.generic_query import query_monitor_metric

    metric = query_monitor_metric(
        metric_id="cpu",
        instance_ids=["host-1"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="60s",
        analysis_mode="series",
        aggregation="avg",
        filters={"label": "cpu"},
    )
    assert metric["result"] is False
    assert "filters" in metric["message"]
    unnamed = query_monitor_metric(
        metric_id="cpu",
        instance_ids=["host-1"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="60s",
        analysis_mode="series",
        aggregation="avg",
        filters={"logic": "AND", "items": [{"op": "eq", "value": "eth0"}]},
    )
    assert unnamed["result"] is False
    assert "维度名" in unnamed["message"]


def test_monitor_alert_range_is_capped_at_90_days_and_failure_is_explicit():
    obj = _object()
    instance = _instance(obj, "host-1")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    MonitorAlert.objects.create(
        monitor_instance_id=instance.id,
        monitor_instance_name=instance.name,
        level="warning",
        status="new",
        alert_type="alert",
        start_event_time=start + timedelta(days=1),
    )
    within = query_alert_counts(
        MonitorAlert.objects.all(),
        time_field="start_event_time",
        time_range=[start.isoformat(), (start + timedelta(seconds=ALERT_RANGE_MAX_SECONDS)).isoformat()],
    )
    assert within == [{"alert_count": 1}]
    with pytest.raises(GenericQueryError, match="90"):
        query_alert_counts(
            MonitorAlert.objects.all(),
            time_field="start_event_time",
            time_range=[start.isoformat(), (start + timedelta(seconds=ALERT_RANGE_MAX_SECONDS + 1)).isoformat()],
        )
    with pytest.raises(GenericQueryError, match="时间字段"):
        query_alert_details(
            MonitorAlert.objects.all(),
            time_field="updated_at",
            time_range=[start.isoformat(), (start + timedelta(days=1)).isoformat()],
        )


def test_alert_handler_keeps_object_optional_and_rejects_removed_params(monkeypatch):
    from apps.monitor.nats.generic_query import query_monitor_alert_counts, query_monitor_alert_distribution, query_monitor_alerts

    legacy = query_monitor_alerts(instance_id="host-1")
    assert legacy["result"] is False
    assert "实例参数" in legacy["message"]
    retired = query_monitor_alerts(analysis_mode="count")
    assert retired["result"] is False
    assert "不支持该参数" in retired["message"]
    grouped = query_monitor_alerts(group_by="level")
    assert grouped["result"] is False
    assert "分组" in grouped["message"]

    obj = _object()
    policy = MonitorPolicy.objects.create(monitor_object=obj, name="主机策略", algorithm="avg")
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="host-1",
        level="warning",
        status="new",
        alert_type="alert",
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        lambda user_info: (user_info, 1, False, [1], False, None),
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_accessible_policy_queryset",
        lambda user_info: (MonitorPolicy.objects.all(), None),
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._filter_nats_visible_alerts",
        lambda queryset, scope_ids, policies: queryset,
    )
    user_info = {"user": "ada", "team": 1, "domain": "example.com"}
    counted = query_monitor_alert_counts(
        user_info=user_info,
        filters={"logic": "AND", "items": [{"field": "level", "op": "eq", "value": "warning"}]},
    )
    assert counted["result"] is True
    assert counted["data"] == [{"alert_count": 1}]
    distributed = query_monitor_alert_distribution(group_by="level", user_info=user_info)
    assert distributed["result"] is True
    assert distributed["data"] == [{"group_value": "警告", "alert_count": 1}]
    paged = query_monitor_alert_distribution(group_by="level", page=1, page_size=10, user_info=user_info)
    assert paged["result"] is False
    assert "分页" in paged["message"]
    missing = query_monitor_alert_counts(monitor_object_id="missing-object", user_info=user_info)
    assert missing["result"] is False
    assert "不存在或无权访问" in missing["message"]


def test_alert_distribution_returns_one_row_per_selected_field():
    host = _object()
    database = MonitorObject.objects.create(name="db-object", level="base")
    host_policy = MonitorPolicy.objects.create(monitor_object=host, name="主机策略", algorithm="avg")
    database_policy = MonitorPolicy.objects.create(monitor_object=database, name="数据库策略", algorithm="avg")
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="host-1",
        level="warning",
        status="new",
        alert_type="alert",
    )
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="host-1",
        level="warning",
        status="new",
        alert_type="alert",
    )
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="host-1",
        level="critical",
        status="new",
        alert_type="no_data",
    )
    MonitorAlert.objects.create(
        policy_id=database_policy.id,
        monitor_instance_id="db-1",
        level="error",
        status="closed",
        alert_type="alert",
    )
    queryset = MonitorAlert.objects.all()
    assert query_alert_distribution(queryset, group_by="level") == [
        {"group_value": "警告", "alert_count": 2},
        {"group_value": "严重", "alert_count": 1},
    ]
    assert query_alert_distribution(queryset, group_by="alert_type") == [
        {"group_value": "阈值告警", "alert_count": 2},
        {"group_value": "无数据告警", "alert_count": 1},
    ]
    now = datetime.now(timezone.utc)
    by_object = query_alert_distribution(
        queryset,
        group_by="monitor_object_id",
        status=["new", "closed"],
        time_field="created_at",
        time_range=[(now - timedelta(days=1)).isoformat(), (now + timedelta(days=1)).isoformat()],
    )
    assert by_object == [
        {"group_value": "host-object", "alert_count": 3},
        {"group_value": "db-object", "alert_count": 1},
    ]
    assert query_alert_distribution(MonitorAlert.objects.none(), group_by="level") == []
    with pytest.raises(GenericQueryError, match="按什么分布"):
        query_alert_distribution(queryset)
    with pytest.raises(GenericQueryError, match="分布字段不受支持"):
        query_alert_distribution(queryset, group_by="status")


def test_monitor_alerts_reject_unknown_choices():
    with pytest.raises(GenericQueryError, match="级别不受支持"):
        query_alert_counts(MonitorAlert.objects.none(), level="info")
    empty = query_alert_counts(MonitorAlert.objects.none())
    assert empty == [{"alert_count": 0}]
    assert "status" not in empty[0]
    assert "unit" not in empty[0]


def test_monitor_alerts_sort_level_by_severity_and_keep_deleted_policy_group(monkeypatch):
    class EmptyLoader:
        def __init__(self, app, default_lang):
            del app, default_lang

        def get(self, key, default=None):
            del key
            return default

    monkeypatch.setattr("apps.monitor.services.generic_query.LanguageLoader", EmptyLoader)
    obj = _object()
    obj.display_name = "主机"
    obj.save(update_fields=["display_name"])
    policy = MonitorPolicy.objects.create(monitor_object=obj, name="主机策略", algorithm="avg")
    moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="host-1",
        monitor_instance_name="alpha",
        level="warning",
        status="new",
        alert_type="alert",
        content="磁盘满了",
        start_event_time=moment,
    )
    MonitorAlert.objects.create(
        policy_id=0,
        monitor_instance_id="host-2",
        monitor_instance_name="beta",
        level="critical",
        status="new",
        alert_type="alert",
        start_event_time=moment,
    )
    MonitorAlert.objects.create(
        policy_id=policy.id,
        monitor_instance_id="host-3",
        monitor_instance_name="gamma",
        level="no_data",
        status="closed",
        alert_type="no_data",
        start_event_time=moment,
    )
    window = [moment.isoformat(), (moment + timedelta(days=1)).isoformat()]
    ordered = query_alert_details(
        MonitorAlert.objects.all(),
        status=["new", "closed"],
        time_field="start_event_time",
        time_range=window,
        order_by="level",
        order_dir="asc",
        page=1,
        page_size=20,
    )
    assert [item["level"] for item in ordered["items"]] == ["无数据", "警告", "严重"]
    warning = next(item for item in ordered["items"] if item["level"] == "警告")
    assert warning["status"] == "未恢复"
    assert warning["alert_type"] == "阈值告警"
    assert warning["content"] == "磁盘满了"
    assert warning["monitor_object_name"] == "主机"
    assert warning["monitor_object_id"] == str(obj.id)
    assert "updated_at" not in warning
    assert "alert_count" not in warning
    orphan = next(item for item in ordered["items"] if item["level"] == "严重")
    assert orphan["monitor_object_id"] == ""
    assert orphan["monitor_object_name"] == "策略已删除"
    active = query_alert_counts(
        MonitorAlert.objects.all(),
        status=["new", "closed"],
        level=["warning", "no_data"],
        time_field="start_event_time",
        time_range=window,
    )
    assert active == [{"alert_count": 2}]


def _patch_alert_access(monkeypatch):
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        lambda user_info: (user_info, 1, False, [1], False, None),
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_accessible_policy_queryset",
        lambda user_info: (MonitorPolicy.objects.all(), None),
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._filter_nats_visible_alerts",
        lambda queryset, scope_ids, policies: queryset,
    )

    def fake_instances(user_info, instance_ids=None):
        queryset = MonitorInstance.objects.filter(is_deleted=False)
        if instance_ids is not None:
            queryset = queryset.filter(id__in=list(instance_ids))
        return queryset, None

    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_nats_accessible_instance_queryset",
        fake_instances,
    )
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_monitor_instance_permission",
        lambda object_id, user_info: ({"instance": [{"id": "*"}], "team": [1]}, None),
    )


def test_alert_distribution_keeps_single_object_and_skips_invalid_instances(monkeypatch):
    from apps.monitor.nats.generic_query import query_monitor_alert_counts, query_monitor_alert_distribution

    host = _object()
    database = MonitorObject.objects.create(name="db-object", level="base")
    _instance(host, "('web-1',)", name="web-1")
    _instance(database, "db-1", name="db-1")
    host_policy = MonitorPolicy.objects.create(monitor_object=host, name="主机策略", algorithm="avg")
    database_policy = MonitorPolicy.objects.create(monitor_object=database, name="数据库策略", algorithm="avg")
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="('web-1',)",
        level="warning",
        status="new",
        alert_type="alert",
    )
    MonitorAlert.objects.create(
        policy_id=database_policy.id,
        monitor_instance_id="db-1",
        level="error",
        status="new",
        alert_type="alert",
    )
    _patch_alert_access(monkeypatch)
    user_info = {"user": "ada", "team": 1, "domain": "example.com"}

    single = query_monitor_alert_distribution(
        group_by="level",
        monitor_object_id=str(host.id),
        instance_ids=["web-1"],
        user_info=user_info,
    )
    assert single["result"] is True
    assert single["data"] == [{"group_value": "警告", "alert_count": 1}]

    skipped = query_monitor_alert_distribution(
        group_by="level",
        monitor_object_id=str(host.id),
        instance_ids=["web-1", "db-1", "gone"],
        user_info=user_info,
    )
    assert skipped["result"] is True
    assert skipped["data"] == [{"group_value": "警告", "alert_count": 1}]

    empty = query_monitor_alert_distribution(
        group_by="level",
        monitor_object_id=str(host.id),
        instance_ids=["gone", "also-gone"],
        user_info=user_info,
    )
    assert empty["result"] is True
    assert empty["data"] == []

    counted = query_monitor_alert_counts(
        monitor_object_id=str(host.id),
        instance_ids=["web-1", "gone"],
        user_info=user_info,
    )
    assert counted["result"] is False
    assert "不存在、已删除或无权访问" in counted["message"]
    assert "gone" in counted["message"]


def test_alert_distribution_supports_multiple_objects_and_cross_object_instances(monkeypatch):
    from apps.monitor.nats.generic_query import query_monitor_alert_distribution, query_monitor_instances

    host = _object()
    database = MonitorObject.objects.create(name="db-object", level="base")
    _instance(host, "host-1", name="web")
    _instance(database, "db-1", name="mysql")
    host_policy = MonitorPolicy.objects.create(monitor_object=host, name="主机策略", algorithm="avg")
    database_policy = MonitorPolicy.objects.create(monitor_object=database, name="数据库策略", algorithm="avg")
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="host-1",
        level="warning",
        status="new",
        alert_type="alert",
    )
    MonitorAlert.objects.create(
        policy_id=database_policy.id,
        monitor_instance_id="db-1",
        level="critical",
        status="new",
        alert_type="alert",
    )
    _patch_alert_access(monkeypatch)
    monkeypatch.setattr(
        "apps.monitor.nats.generic_query._get_authorized_instance_queryset",
        lambda permission, scope_ids=None: MonitorInstance.objects.filter(is_deleted=False),
    )
    user_info = {"user": "ada", "team": 1, "domain": "example.com"}

    distributed = query_monitor_alert_distribution(
        group_by="monitor_object_id",
        monitor_object_id=[str(host.id), str(database.id)],
        instance_ids=["host-1", "db-1", "missing"],
        user_info=user_info,
    )
    assert distributed["result"] is True
    assert {item["group_value"] for item in distributed["data"]} == {"host-object", "db-object"}
    assert {item["alert_count"] for item in distributed["data"]} == {1}

    listed = query_monitor_instances(
        monitor_object_id=[str(host.id), str(database.id)],
        analysis_mode="detail",
        page=1,
        page_size=20,
        user_info=user_info,
    )
    assert listed["result"] is True
    assert {item["instance_id"] for item in listed["data"]["items"]} == {"host-1", "db-1"}


def test_cmdb_alert_distribution_maps_uuids_then_groups_like_alert_distribution(monkeypatch):
    from apps.monitor.nats.generic_query import query_cmdb_alert_distribution
    from apps.monitor.services.cmdb_alert_distribution import normalize_cmdb_uuids
    from apps.monitor.services.generic_query import GenericQueryError

    host = _object()
    database = MonitorObject.objects.create(name="db-object", display_name="MySQL", level="base")
    nginx = MonitorObject.objects.create(name="nginx-object", display_name="Nginx", level="base")
    _instance(host, "('web-1',)", name="web-1")
    _instance(database, "db-1", name="mysql")
    _instance(nginx, "nginx-1", name="nginx")
    host_policy = MonitorPolicy.objects.create(monitor_object=host, name="主机策略", algorithm="avg")
    database_policy = MonitorPolicy.objects.create(monitor_object=database, name="数据库策略", algorithm="avg")
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="('web-1',)",
        level="warning",
        status="new",
        alert_type="alert",
    )
    MonitorAlert.objects.create(
        policy_id=host_policy.id,
        monitor_instance_id="('web-1',)",
        level="critical",
        status="new",
        alert_type="alert",
    )
    MonitorAlert.objects.create(
        policy_id=database_policy.id,
        monitor_instance_id="db-1",
        level="error",
        status="new",
        alert_type="alert",
    )
    _patch_alert_access(monkeypatch)

    host_uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    mysql_uuid = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    missing_uuid = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    mismatch_uuid = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    nginx_uuid = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"

    monkeypatch.setattr(
        "apps.monitor.services.cmdb_alert_distribution.fetch_cmdb_monitor_mappings",
        lambda uuids, user_info: [
            {"inst_uuid": host_uuid, "model_id": "host", "monitor_id": "('web-1',)"},
            {"inst_uuid": mysql_uuid, "model_id": "mysql", "monitor_id": "db-1"},
            {"inst_uuid": nginx_uuid, "model_id": "nginx", "monitor_id": "nginx-1"},
            {"inst_uuid": mismatch_uuid, "model_id": "host", "monitor_id": "gone"},
        ],
    )
    user_info = {"user": "ada", "team": 1, "domain": "example.com", "locale": "zh-Hans"}
    mixed_uuids = [host_uuid, mysql_uuid, nginx_uuid, missing_uuid, mismatch_uuid]

    by_object = query_cmdb_alert_distribution(
        uuids=mixed_uuids,
        group_by="monitor_object_id",
        user_info=user_info,
    )
    assert by_object["result"] is True
    by_name = {item["monitor_object_name"]: item for item in by_object["data"]}
    assert by_name["host-object"]["alert_count"] == 2
    assert by_name["host-object"]["monitor_object_id"] == host.id
    assert by_name["host-object"]["group_value"] == "host-object"
    assert by_name["MySQL"]["alert_count"] == 1
    assert by_name["MySQL"]["monitor_object_id"] == database.id
    by_id = {item["monitor_object_id"]: item for item in by_object["data"]}
    assert by_id[nginx.id]["alert_count"] == 0
    assert by_id[nginx.id]["group_value"] == by_id[nginx.id]["monitor_object_name"]

    by_level = query_cmdb_alert_distribution(
        uuids=mixed_uuids,
        group_by="level",
        user_info=user_info,
    )
    assert by_level["result"] is True
    assert {item["group_value"]: item["alert_count"] for item in by_level["data"]} == {"警告": 1, "严重": 1, "错误": 1}

    rejected_object = query_cmdb_alert_distribution(
        uuids=mixed_uuids,
        group_by="monitor_object_id",
        monitor_object_id=str(host.id),
        user_info=user_info,
    )
    assert rejected_object["result"] is False
    assert "不接收监控对象" in rejected_object["message"]

    empty = query_cmdb_alert_distribution(uuids=[missing_uuid], group_by="level", user_info=user_info)
    assert empty["result"] is True
    assert empty["data"] == []

    unmapped_without_group = query_cmdb_alert_distribution(uuids=[missing_uuid], user_info=user_info)
    assert unmapped_without_group["result"] is False
    assert "请选择按什么分布" in unmapped_without_group["message"]

    with_model = query_cmdb_alert_distribution(
        model_id=["host", "mysql"],
        uuids=[*mixed_uuids, "主机"],
        group_by="level",
        user_info=user_info,
    )
    assert with_model["result"] is True
    assert {item["group_value"]: item["alert_count"] for item in with_model["data"]} == {"警告": 1, "严重": 1, "错误": 1}

    missing_group = query_cmdb_alert_distribution(uuids=mixed_uuids, user_info=user_info)
    assert missing_group["result"] is False
    assert "请选择按什么分布" in missing_group["message"]

    invalid_only = query_cmdb_alert_distribution(uuids=["主机", "mysql"], group_by="level", user_info=user_info)
    assert invalid_only["result"] is False
    assert "实例标识格式错误" in invalid_only["message"]

    with pytest.raises(GenericQueryError, match="实例标识不能为空"):
        normalize_cmdb_uuids([])
    with pytest.raises(GenericQueryError, match="实例标识格式错误"):
        normalize_cmdb_uuids(["主机"])
    assert normalize_cmdb_uuids([host_uuid, "主机", host_uuid.upper()]) == [host_uuid]
