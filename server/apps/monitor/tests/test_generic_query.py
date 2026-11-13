"""监控通用查询的上限、缺测和告警时间范围。"""

from datetime import datetime, timedelta, timezone

import pytest

from apps.monitor.models.monitor_object import MonitorInstance, MonitorObject
from apps.monitor.models.monitor_policy import MonitorAlert, MonitorPolicy
from apps.monitor.services.generic_query import (
    GenericQueryError,
    _order_instances,
    build_metric_result,
    metric_instance_labels,
    query_alerts,
    query_instances,
    validate_metric_request,
)
from apps.monitor.services.generic_query_limits import (
    ALERT_RANGE_MAX_SECONDS,
    DETAIL_PAGE_SIZE_MAX,
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

    detail = query_instances(MonitorInstance.objects.filter(monitor_object=obj), analysis_mode="detail", order="id")
    stopped = query_instances(
        MonitorInstance.objects.filter(monitor_object=obj),
        analysis_mode="detail",
        status="inactive",
    )

    assert detail["count"] == 2
    assert detail["unit"] == "个"
    assert "一台算一个" in detail["aggregation"]
    assert [field["key"] for field in detail["fields"]] == [
        "instance_id",
        "name",
        "ip",
        "cloud_region",
        "cmdb_id",
        "monitor_object_id",
        "status",
    ]
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
    )
    assert detail["items"][0]["monitor_object_id"] == "主机"

    monkeypatch.setattr(
        "apps.monitor.services.generic_query.LanguageLoader",
        type("EmptyLoader", (), {"__init__": lambda self, app, default_lang: None, "get": lambda self, key, default=None: None}),
    )
    stored = query_instances(MonitorInstance.objects.filter(monitor_object=obj), analysis_mode="detail", locale="en")
    assert stored["items"][0]["monitor_object_id"] == "库内展示名"


def test_monitor_instance_rejects_filters_distribution_and_missing_ids():
    obj = _object()
    _instance(obj, "host-1", name="alpha")
    base = MonitorInstance.objects.filter(monitor_object=obj)
    with pytest.raises(GenericQueryError, match="属性过滤"):
        query_instances(base, analysis_mode="detail", filters={"logic": "AND", "items": [{"field": "name", "op": "eq", "value": "alpha"}]})
    with pytest.raises(GenericQueryError, match="分组"):
        query_instances(base, analysis_mode="detail", group_by="status")
    with pytest.raises(GenericQueryError, match="分析方式不受支持"):
        query_instances(base, analysis_mode="count")
    with pytest.raises(GenericQueryError, match="无权访问"):
        query_instances(base, analysis_mode="detail", instance_ids=["host-1", "gone"])


def test_monitor_instance_page_size_and_statistics_group_limits():
    obj = _object()
    _instance(obj, "host-1")
    with pytest.raises(GenericQueryError, match=str(DETAIL_PAGE_SIZE_MAX)):
        query_instances(
            MonitorInstance.objects.all(),
            analysis_mode="detail",
            page_size=DETAIL_PAGE_SIZE_MAX + 1,
        )


def test_monitor_modes_reject_group_and_order_they_do_not_use():
    with pytest.raises(GenericQueryError, match="不支持分组"):
        query_alerts(None, analysis_mode="detail", group_by="level")


def test_monitor_instance_orders_by_the_ip_people_see():
    obj = _object()
    first = _instance(obj, "host-1", name="b")
    first.summary_facts = {"asset.ip": "10.2.0.1"}
    first.ip = "192.168.0.1"
    first.save(update_fields=["summary_facts", "ip"])
    second = _instance(obj, "host-2", name="a")
    second.ip = "10.1.0.1"
    second.save(update_fields=["ip"])
    queryset = MonitorInstance.objects.filter(monitor_object=obj)
    ordered = query_instances(queryset, analysis_mode="detail", order="ip")
    assert [item["instance_id"] for item in ordered["items"]] == ["host-2", "host-1"]
    assert [item["ip"] for item in ordered["items"]] == ["10.1.0.1", "10.2.0.1"]
    assert "CAST" in str(_order_instances(queryset, "ip").query)


def test_monitor_distribution_uses_return_limit_and_rejects_page():
    _alert_row = {
        "monitor_instance_id": "host-1",
        "monitor_instance_name": "host-1",
        "status": "new",
        "alert_type": "alert",
        "start_event_time": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    MonitorAlert.objects.create(level="warning", **_alert_row)
    MonitorAlert.objects.create(level="warning", **{**_alert_row, "monitor_instance_id": "host-2"})
    MonitorAlert.objects.create(level="fatal", **{**_alert_row, "monitor_instance_id": "host-3"})
    alerts = query_alerts(MonitorAlert.objects.all(), analysis_mode="distribution", group_by="level", page_size=1)
    assert alerts["items"] == [{"level": "warning", "alert_count": 2}]
    assert alerts["count"] == 2
    assert alerts["page"] == 1
    assert alerts["page_size"] == 1
    everything = query_alerts(MonitorAlert.objects.all(), analysis_mode="distribution", group_by="level")
    assert {item["level"] for item in everything["items"]} == {"warning", "fatal"}
    assert everything["page_size"] == 2
    with pytest.raises(GenericQueryError, match="页码"):
        query_alerts(MonitorAlert.objects.all(), analysis_mode="distribution", group_by="level", page=2, page_size=1)


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


def test_metric_series_over_limit_missing_and_zero_are_distinct():
    overflow = {"status": "success", "data": {"result": [{"metric": {}, "values": [[1, "1"]]} for _ in range(METRIC_SERIES_MAX + 1)]}}
    with pytest.raises(GenericQueryError, match=str(METRIC_SERIES_MAX)):
        build_metric_result(mode="series", response=overflow, unit="%", aggregation="avg", requested_ids=["a"])

    missing = build_metric_result(
        mode="value",
        response={"status": "success", "data": {"result": []}},
        unit="%",
        aggregation="avg",
        requested_ids=["a"],
    )
    zero = build_metric_result(
        mode="value",
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "a"}, "values": [[1, "0"]]}]}},
        unit="%",
        aggregation="avg",
        requested_ids=["a"],
    )
    assert missing["structure"] == "table"
    assert missing["status"] == "missing"
    assert missing["items"][0]["instance_id"] == "a"
    assert missing["items"][0]["value"] is None
    assert missing["items"][0]["status"] == "missing"
    assert missing["status"] == "missing"
    assert missing["items"][0]["aggregation"] == "平均"
    assert "dimension" not in missing["items"][0]
    assert zero["status"] == "ok"
    assert zero["items"][0]["value"] == 0
    assert zero["items"][0]["unit"] == "%"
    assert zero["items"][0]["aggregation"] == "平均"
    assert zero["items"][0]["status"] == "ok"
    assert [field["key"] for field in zero["fields"]] == [
        "instance_id",
        "value",
        "unit",
        "aggregation",
    ]

    separate = build_metric_result(
        mode="value",
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
        aggregation="sum",
        requested_ids=["a", "b"],
        instance_names={"b": "网卡主机"},
    )
    by_id = {item["instance_id"]: item for item in separate["items"]}
    assert by_id["a"]["value"] == 4
    assert by_id["网卡主机"]["value"] == 10
    assert by_id["网卡主机"]["aggregation"] == "求和"
    assert "dimension" not in by_id["网卡主机"]

    latest = build_metric_result(
        mode="latest",
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "a"}, "values": [[1, "1"], [2, "9"]]}]}},
        unit="%",
        aggregation="avg",
        requested_ids=["a"],
        instance_names={"a": "分块演示-主机-01"},
    )
    assert latest["items"][0]["instance_id"] == "分块演示-主机-01"
    assert latest["items"][0]["value"] == 9
    assert latest["items"][0]["aggregation"] == "平均"
    assert latest["aggregation"] == "平均"
    assert "time" in latest["items"][0]
    assert [field["key"] for field in latest["fields"]] == [
        "instance_id",
        "value",
        "time",
        "unit",
        "aggregation",
    ]

    partial = build_metric_result(
        mode="series",
        response={
            "status": "success",
            "data": {"result": [{"metric": {"instance_id": "a"}, "values": [[1, "1"], [2, "NaN"], [3, "0"]]}]},
        },
        unit="%",
        aggregation="avg",
        requested_ids=["a", "b"],
    )
    assert partial["structure"] == "series"
    assert partial["status"] == "ok"
    assert [point["value"] for point in partial["series"]["a"]] == [1.0, None, 0.0]
    assert [point["time"] for point in partial["series"]["a"]]
    assert "name" not in partial["series"]["a"][0]
    assert partial["fields"][0]["key"] == "time"
    assert partial["fields"][1]["role"] == "measure"
    assert partial["unbound_instance_ids"] == ["b"]
    complete = build_metric_result(
        mode="series",
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "a"}, "values": [[1, "1"]]}]}},
        unit="%",
        aggregation="avg",
        requested_ids=["a"],
    )
    assert complete["unbound_instance_ids"] == []
    split = build_metric_result(
        mode="series",
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
        aggregation="avg",
        requested_ids=["host"],
    )
    assert set(split["series"]) == {"host device=sda, path=/", "host device=sdb, path=/data"}
    assert split["series"]["host device=sda, path=/"][0]["value"] == 40
    assert split["series"]["host device=sdb, path=/data"][0]["value"] == 80
    missing_series = build_metric_result(
        mode="series",
        response={"status": "success", "data": {"result": []}},
        unit="%",
        aggregation="avg",
        requested_ids=["a"],
    )
    assert missing_series["structure"] == "series"
    assert missing_series["status"] == "missing"
    assert missing_series["series"] == {}


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
        mode="value",
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "demo-web-01"}, "values": [[1, "0"]]}]}},
        unit="%",
        aggregation="max",
        requested_ids=["demo-web-01", "blank-name"],
        instance_names=labels,
    )
    by_name = {item["instance_id"]: item for item in named["items"]}
    assert by_name["演示网站"]["value"] == 0
    assert by_name["演示网站"]["aggregation"] == "最大"
    assert by_name["blank-name"]["value"] is None
    assert by_name["blank-name"]["status"] == "missing"


def test_metric_result_matches_storage_key_to_returned_labels():
    names = {"('web-01',)": "网站主机", "web-01": "网站主机", "plain-host": "裸主机"}
    returned = {
        "status": "success",
        "data": {"result": [{"metric": {"instance_id": "web-01"}, "values": [[1700000000, "40"]]}]},
    }
    latest = build_metric_result(
        mode="latest",
        response=returned,
        unit="percent",
        aggregation="avg",
        requested_ids=["('web-01',)"],
        instance_names=names,
    )
    assert [item["instance_id"] for item in latest["items"]] == ["网站主机"]
    assert latest["items"][0]["value"] == 40.0

    window = build_metric_result(
        mode="value",
        response=returned,
        unit="percent",
        aggregation="avg",
        requested_ids=["('web-01',)"],
        instance_names=names,
    )
    assert [item["value"] for item in window["items"]] == [40.0]
    assert [field["key"] for field in window["fields"]] == ["instance_id", "value", "unit", "aggregation"]

    series = build_metric_result(
        mode="series",
        response=returned,
        unit="percent",
        aggregation="avg",
        requested_ids=["('web-01',)"],
        instance_names=names,
    )
    assert series["status"] == "ok"
    assert series["series"]["web-01"][0]["value"] == 40.0
    assert series["unbound_instance_ids"] == []

    plain = build_metric_result(
        mode="latest",
        response={"status": "success", "data": {"result": [{"metric": {"instance_id": "plain-host"}, "values": [[1, "3"]]}]}},
        unit="percent",
        aggregation="avg",
        requested_ids=["plain-host"],
        instance_names=names,
    )
    assert [(item["instance_id"], item["value"]) for item in plain["items"]] == [("裸主机", 3.0)]

    pod_names = {"('cluster-a', 'nginx-1')": "前端 Pod", "('cluster-a', 'nginx-2')": "后端 Pod"}
    pods = build_metric_result(
        mode="latest",
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
        aggregation="avg",
        requested_ids=["('cluster-a', 'nginx-1')", "('cluster-a', 'nginx-2')"],
        instance_names=pod_names,
        identity_keys=["instance_id", "pod"],
    )
    assert [(item["instance_id"], item["value"]) for item in pods["items"]] == [("前端 Pod", 12.0), ("后端 Pod", 8.0)]

    pod_series = build_metric_result(
        mode="series",
        response={
            "status": "success",
            "data": {"result": [{"metric": {"instance_id": "cluster-a", "pod": "nginx-1"}, "values": [[1, "12"]]}]},
        },
        unit="percent",
        aggregation="avg",
        requested_ids=["('cluster-a', 'nginx-1')"],
        instance_names=pod_names,
        identity_keys=["instance_id", "pod"],
    )
    assert pod_series["series"]["cluster-a pod=nginx-1"][0]["value"] == 12.0
    assert pod_series["unbound_instance_ids"] == []

    absent = build_metric_result(
        mode="latest",
        response={"status": "success", "data": {"result": []}},
        unit="percent",
        aggregation="avg",
        requested_ids=["('web-01',)"],
        instance_names=names,
    )
    assert [(item["instance_id"], item["value"], item["status"]) for item in absent["items"]] == [("网站主机", None, "missing")]


def test_empty_aggregation_rejects_open_dimensions_before_the_query(mocker):
    from types import SimpleNamespace

    from apps.monitor.nats.generic_query import query_monitor_metric

    mocker.patch(
        "apps.monitor.nats.generic_query._get_nats_actor_scope",
        return_value=(SimpleNamespace(username="admin", domain="domain", is_superuser=False), 1, False, frozenset({1}), False, None),
    )
    mocker.patch(
        "apps.monitor.nats.generic_query.AuthorizedMetricQueryService.prepare",
        return_value=SimpleNamespace(
            metric=SimpleNamespace(
                dimensions=[{"name": "device"}, {"name": "path"}, {"name": "fstype"}],
                instance_id_keys=["instance_id"],
                monitor_object=SimpleNamespace(instance_id_keys=["instance_id"]),
            ),
            query="unused",
        ),
    )
    queried = mocker.patch("apps.monitor.nats.generic_query.VictoriaMetricsAPI")
    result = query_monitor_metric(
        metric_id="507",
        instance_ids=["mock-disk-split-01"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="5m",
        analysis_mode="series",
        aggregation="",
        user_info={"user": {"username": "admin"}, "team": "1", "domain": "domain"},
    )
    assert result["result"] is False
    assert result["message"] == "这个指标在同一时间点可能有多个数，请选择聚合方式，或用维度过滤指定其中某一个。"
    queried.assert_not_called()


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
        user_info={"user": "admin", "domain": "domain", "team": 7, "include_children": False, "is_superuser": True},
    )
    assert captured["user"].is_superuser is False


def test_metric_handler_rejects_non_list_filters():
    from apps.monitor.nats.generic_query import query_monitor_instances, query_monitor_metric

    instances = query_monitor_instances(monitor_object_id="1", filters={"label": "cpu"})
    assert instances["result"] is False
    assert "属性过滤" in instances["message"]
    metric = query_monitor_metric(
        metric_id="cpu",
        instance_ids=["host-1"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="60s",
        filters={"label": "cpu"},
    )
    assert metric["result"] is False
    assert "filters" in metric["message"]
    unnamed = query_monitor_metric(
        metric_id="cpu",
        instance_ids=["host-1"],
        time_range=["2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"],
        step="60s",
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
    within = query_alerts(
        MonitorAlert.objects.all(),
        analysis_mode="count",
        time_field="start_event_time",
        time_range=[start.isoformat(), (start + timedelta(seconds=ALERT_RANGE_MAX_SECONDS)).isoformat()],
    )
    assert within["alert_count"] == 1
    grouped = query_alerts(
        MonitorAlert.objects.all(),
        analysis_mode="distribution",
        time_field="start_event_time",
        time_range=[start.isoformat(), (start + timedelta(days=2)).isoformat()],
        group_by="level",
    )
    assert grouped["items"] == [{"level": "warning", "alert_count": 1}]
    assert "name" not in grouped["items"][0]
    assert "value" not in grouped["items"][0]
    with pytest.raises(GenericQueryError, match="90"):
        query_alerts(
            MonitorAlert.objects.all(),
            analysis_mode="count",
            time_field="start_event_time",
            time_range=[start.isoformat(), (start + timedelta(seconds=ALERT_RANGE_MAX_SECONDS + 1)).isoformat()],
        )
    with pytest.raises(GenericQueryError, match="时间字段"):
        query_alerts(
            MonitorAlert.objects.all(),
            analysis_mode="detail",
            time_field="updated_at",
            time_range=[start.isoformat(), (start + timedelta(days=1)).isoformat()],
        )


def test_alert_handler_keeps_object_optional_and_rejects_removed_params(monkeypatch):
    from apps.monitor.nats.generic_query import query_monitor_alerts

    rejected = query_monitor_alerts(filters={"logic": "AND", "items": [{"field": "level", "op": "eq", "value": "warning"}]})
    assert rejected["result"] is False
    assert "条件过滤" in rejected["message"]
    legacy = query_monitor_alerts(instance_id="host-1")
    assert legacy["result"] is False
    assert "实例参数" in legacy["message"]

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
    counted = query_monitor_alerts(analysis_mode="count", user_info=user_info)
    assert counted["result"] is True
    assert counted["data"]["alert_count"] == 1
    missing = query_monitor_alerts(monitor_object_id="missing-object", analysis_mode="count", user_info=user_info)
    assert missing["result"] is False
    assert "不存在或无权访问" in missing["message"]


def test_monitor_alerts_reject_unknown_choices_filters_and_missing_group():
    with pytest.raises(GenericQueryError, match="级别不受支持"):
        query_alerts(MonitorAlert.objects.none(), analysis_mode="count", level="info")
    with pytest.raises(GenericQueryError, match="条件过滤"):
        query_alerts(
            MonitorAlert.objects.none(),
            analysis_mode="count",
            filters={"logic": "AND", "items": [{"field": "level", "op": "eq", "value": "warning"}]},
        )
    with pytest.raises(GenericQueryError, match="必须选择分组"):
        query_alerts(MonitorAlert.objects.none(), analysis_mode="distribution")
    empty = query_alerts(MonitorAlert.objects.none(), analysis_mode="count")
    assert empty["alert_count"] == 0
    assert empty["status"] == "ok"
    assert empty["unit"] == "条"


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
    ordered = query_alerts(MonitorAlert.objects.all(), analysis_mode="detail", order="level")
    assert [item["level"] for item in ordered["items"]] == ["no_data", "warning", "critical"]
    warning = next(item for item in ordered["items"] if item["level"] == "warning")
    assert warning["content"] == "磁盘满了"
    assert warning["monitor_object_name"] == "主机"
    assert warning["monitor_object_id"] == str(obj.id)
    assert "updated_at" not in warning
    grouped = query_alerts(MonitorAlert.objects.all(), analysis_mode="distribution", group_by="monitor_object_id", page_size=100)
    assert sum(item["alert_count"] for item in grouped["items"]) == 3
    orphan = next(item for item in grouped["items"] if item["monitor_object_id"] == "")
    assert orphan["monitor_object_name"] == "策略已删除"
    assert orphan["alert_count"] == 1
    active = query_alerts(MonitorAlert.objects.all(), analysis_mode="count", status=["new", "closed"], level=["warning", "no_data"])
    assert active["alert_count"] == 2
