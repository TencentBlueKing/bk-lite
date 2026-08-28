from types import SimpleNamespace

import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.operation_analysis.services.application3d.errors import Application3DCapacityExceeded, Application3DNotFound
from apps.operation_analysis.services.application3d.query_service import Application3DQueryService, _ApplicationScope

APP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
APP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
SYSTEM_A = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _request(data=None):
    return SimpleNamespace(
        user=SimpleNamespace(username="tester", is_superuser=False),
        COOKIES={"current_team": "1", "include_children": "0"},
        data=data if data is not None else {},
    )


def _alert(index):
    return SimpleNamespace(
        id=str(index),
        alert_type="alert",
        level="warning",
        start_event_time=None,
        policy_id=1,
        monitor_instance_id="monitor-1",
        content=f"alert-{index}",
        end_event_time=None,
    )


def _application(app_id, name):
    return {"inst_uuid": app_id, "inst_name": name, "model_id": "application"}


def _scope(applications, *, complete_apps=None, policies=None, hosts_by_app=None):
    return _ApplicationScope(
        applications=applications,
        hosts_by_app=hosts_by_app if hosts_by_app is not None else {item["inst_uuid"]: [] for item in applications},
        policies=policies or {},
        complete_apps=set(complete_apps if complete_apps is not None else [item["inst_uuid"] for item in applications]),
    )


def _filter_definition():
    return (
        [
            {
                "id": "system_status",
                "label": "应用系统运行状态",
                "type": "multiple",
                "options": [{"value": "running", "label": "运行中"}],
            }
        ],
        {"running"},
    )


def test_wall_empty(monkeypatch):
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: []))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, applications: _scope([])))

    result = Application3DQueryService.wall(_request())

    assert result["items"] == []
    assert result["capacity"] == {"actualCount": 0, "supportedCount": None}
    assert result["appliedFilters"] == {"system_status": []}


def test_system_status_filter_excludes_orphan(monkeypatch):
    applications = [_application(APP_A, "associated"), _application(APP_B, "orphan")]
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_systems",
        lambda app_ids: {APP_A: [SYSTEM_A], APP_B: []},
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **kwargs: {},
    )

    def instance_list(**kwargs):
        assert kwargs["model_id"] == "system"
        return ([{"inst_uuid": SYSTEM_A, "inst_name": "system", "status": "running"}], 1)

    monkeypatch.setattr(InstanceManage, "instance_list", instance_list)
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )

    result = Application3DQueryService.wall(
        _request(),
        applied_filters={"system_status": ["running"]},
    )

    assert [item["id"] for item in result["items"]] == [APP_A]


def test_system_status_filter_matches_cmdb_enum_list(monkeypatch):
    """Live CMDB stores single-select enum as list, e.g. status=['1']."""
    applications = [_application(APP_A, "online-app"), _application(APP_B, "testing-app")]
    system_b = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    monkeypatch.setattr(
        Application3DQueryService,
        "_filter_definition",
        classmethod(
            lambda cls: (
                [
                    {
                        "id": "system_status",
                        "label": "运行状态",
                        "type": "multiple",
                        "options": [
                            {"value": "1", "label": "已上线"},
                            {"value": "2", "label": "测试中"},
                        ],
                    }
                ],
                {"1", "2"},
            )
        ),
    )
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_systems",
        lambda app_ids: {APP_A: [SYSTEM_A], APP_B: [system_b]},
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **kwargs: {},
    )

    def instance_list(**kwargs):
        assert kwargs["model_id"] == "system"
        return (
            [
                {"inst_uuid": SYSTEM_A, "inst_name": "sys-online", "status": ["1"]},
                {"inst_uuid": system_b, "inst_name": "sys-testing", "status": ["2"]},
            ],
            2,
        )

    monkeypatch.setattr(InstanceManage, "instance_list", instance_list)
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )

    result = Application3DQueryService.wall(
        _request(),
        applied_filters={"system_status": ["1"]},
    )

    assert [item["id"] for item in result["items"]] == [APP_A]


def test_zero_hosts_is_normal(monkeypatch):
    applications = [_application(APP_A, "empty")]
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )

    result = Application3DQueryService.wall(_request())

    assert result["items"][0]["health"]["state"] == "normal"
    assert result["items"][0]["health"]["activeAlarmCount"] == 0


def test_active_alert_aggregation(monkeypatch):
    applications = [_application(APP_A, "alarming")]
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_wall_health_by_application",
        classmethod(
            lambda cls, scope: {
                APP_A: {
                    "state": "alarming",
                    "reason": "active_alarm",
                    "activeAlarmCount": 1,
                    "severityCounts": {"critical": 1, "error": 0, "warning": 0, "info": 0},
                    "noDataAlarmCount": 0,
                    "highestSeverity": {"id": "critical", "label": "严重", "rank": 400, "color": "critical"},
                    "stale": False,
                }
            }
        ),
    )

    result = Application3DQueryService.wall(_request())

    health = result["items"][0]["health"]
    assert health["state"] == "alarming"
    assert health["activeAlarmCount"] == 1
    assert health["highestSeverity"]["id"] == "critical"


def test_wall_health_uses_db_group_counts_without_model_materialization(monkeypatch):
    applications = [_application(APP_A, "alarming")]
    scope = _scope(
        applications,
        hosts_by_app={APP_A: [{"inst_uuid": "host-1", "monitor_id": "monitor-1"}]},
        policies={1: SimpleNamespace(id=1)},
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: scope))

    class _GroupedValues:
        def annotate(self, **kwargs):
            return [
                {"monitor_instance_id": "monitor-1", "alert_type": "alert", "level": "critical", "count": 120},
                {"monitor_instance_id": "monitor-1", "alert_type": "no_data", "level": "", "count": 5},
            ]

    class _AlertQuery:
        def __init__(self):
            self.materialized = 0
            self.values_calls = 0

        def filter(self, **kwargs):
            return self

        def values(self, *args):
            self.values_calls += 1
            assert args == ("monitor_instance_id", "alert_type", "level")
            return _GroupedValues()

        def __iter__(self):
            self.materialized += 1
            raise AssertionError("Wall health must not iterate MonitorAlert model rows")

    tracking = _AlertQuery()
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.MonitorAlert.objects",
        SimpleNamespace(filter=lambda **kwargs: tracking, none=lambda: tracking),
    )

    result = Application3DQueryService.wall(_request())
    health = result["items"][0]["health"]
    assert health["state"] == "alarming"
    assert health["activeAlarmCount"] == 125
    assert health["noDataAlarmCount"] == 5
    assert health["severityCounts"]["critical"] == 120
    assert health["severityCounts"]["warning"] == 5
    assert health["highestSeverity"]["id"] == "critical"
    assert tracking.materialized == 0
    assert tracking.values_calls == 1


def test_wall_and_detail_only_no_data_critical_is_alarming(monkeypatch):
    applications = [_application(APP_A, "nodata")]
    scope = _scope(
        applications,
        hosts_by_app={APP_A: [{"inst_uuid": "host-1", "monitor_id": "monitor-1"}]},
        policies={1: SimpleNamespace(id=1)},
    )
    grouped = [
        {"monitor_instance_id": "monitor-1", "alert_type": "no_data", "level": "critical", "count": 1},
    ]
    monkeypatch.setattr(
        Application3DQueryService,
        "_grouped_alert_counts_by_monitor",
        classmethod(lambda cls, scope, monitor_ids: [row for row in grouped if row["monitor_instance_id"] in monitor_ids]),
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: scope))
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: applications[0]))
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_paged_scoped_alerts",
        classmethod(lambda cls, scope, app_id, *, cursor: ([], False)),
    )

    wall_health = Application3DQueryService.wall(_request())["items"][0]["health"]
    detail_health = Application3DQueryService.application_detail(_request(), APP_A)["application"]["health"]
    for health in (wall_health, detail_health):
        assert health["state"] == "alarming"
        assert health["reason"] == "active_alarm"
        assert health["activeAlarmCount"] == 1
        assert health["noDataAlarmCount"] == 1
        assert health["severityCounts"]["critical"] == 1
        assert health["highestSeverity"]["id"] == "critical"


def test_wall_alert_aggregation_query_count_does_not_scale_with_applications(monkeypatch):
    """MonitorAlert GROUP BY calls are bounded by monitor batches, not Application count."""
    from apps.operation_analysis.services.application3d.constants import APPLICATION3D_ENTITY_BATCH_SIZE

    shared_monitor = "monitor-shared"
    query_counts = []

    class _GroupedValues:
        def annotate(self, **kwargs):
            return [
                {"monitor_instance_id": shared_monitor, "alert_type": "alert", "level": "warning", "count": 2},
                {"monitor_instance_id": shared_monitor, "alert_type": "no_data", "level": "", "count": 1},
                {"monitor_instance_id": "monitor-critical", "alert_type": "alert", "level": "critical", "count": 1},
            ]

    class _AlertQuery:
        def __init__(self):
            self.filter_calls = 0

        def filter(self, **kwargs):
            self.filter_calls += 1
            return self

        def values(self, *args):
            assert args == ("monitor_instance_id", "alert_type", "level")
            return _GroupedValues()

    def run_wall(app_count: int) -> dict:
        apps = [_application(f"{index:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa", f"app-{index}") for index in range(app_count)]
        # All complete apps share one host/monitor; one incomplete app at the end when count>1.
        hosts_by_app = {app["inst_uuid"]: [{"inst_uuid": f"host-{app['inst_uuid']}", "monitor_id": shared_monitor}] for app in apps}
        # Duplicate relation on first app must not double-count.
        hosts_by_app[apps[0]["inst_uuid"]] = [
            {"inst_uuid": "host-dup-a", "monitor_id": shared_monitor},
            {"inst_uuid": "host-dup-b", "monitor_id": shared_monitor},
            {"inst_uuid": "host-critical", "monitor_id": "monitor-critical"},
        ]
        incomplete_id = None
        complete_ids = [app["inst_uuid"] for app in apps]
        if app_count >= 2:
            incomplete_id = apps[-1]["inst_uuid"]
            hosts_by_app[incomplete_id] = [{"inst_uuid": "host-incomplete", "monitor_id": ""}]
            complete_ids = [app["inst_uuid"] for app in apps[:-1]]

        tracking = _AlertQuery()
        monkeypatch.setattr(
            "apps.operation_analysis.services.application3d.query_service.MonitorAlert.objects",
            SimpleNamespace(filter=lambda **kwargs: tracking, none=lambda: tracking),
        )
        monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
        monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: apps))
        monkeypatch.setattr(
            Application3DQueryService,
            "_build_scope",
            classmethod(
                lambda cls, request, visible: _scope(
                    visible,
                    hosts_by_app=hosts_by_app,
                    policies={1: SimpleNamespace(id=1)},
                    complete_apps=complete_ids,
                )
            ),
        )
        result = Application3DQueryService.wall(_request())
        query_counts.append(tracking.filter_calls)
        return {"result": result, "incomplete_id": incomplete_id, "complete_ids": complete_ids, "apps": apps}

    one = run_wall(1)
    twenty = run_wall(20)
    hundred = run_wall(100)

    assert query_counts[0] == query_counts[1] == query_counts[2]
    assert query_counts[0] <= max(1, (2 + APPLICATION3D_ENTITY_BATCH_SIZE - 1) // APPLICATION3D_ENTITY_BATCH_SIZE)
    # Shared monitor contributes to every complete app once (no per-app fan-out inflation).
    for sample in (one, twenty, hundred):
        items = {item["id"]: item["health"] for item in sample["result"]["items"]}
        for app_id in sample["complete_ids"]:
            if app_id == sample["apps"][0]["inst_uuid"]:
                # first app also has critical monitor
                assert items[app_id]["activeAlarmCount"] == 4
                assert items[app_id]["severityCounts"]["critical"] == 1
                # ordinary warning=2 + empty-level no_data → warning
                assert items[app_id]["severityCounts"]["warning"] == 3
                assert items[app_id]["noDataAlarmCount"] == 1
            else:
                assert items[app_id]["activeAlarmCount"] == 3
                assert items[app_id]["severityCounts"]["warning"] == 3
                assert items[app_id]["noDataAlarmCount"] == 1
        if sample["incomplete_id"]:
            assert items[sample["incomplete_id"]]["reason"] == "unavailable"
            assert items[sample["incomplete_id"]]["activeAlarmCount"] is None


def test_wall_and_detail_health_counts_are_consistent(monkeypatch):
    applications = [_application(APP_A, "shared")]
    scope = _scope(
        applications,
        hosts_by_app={
            APP_A: [
                {"inst_uuid": "host-1", "monitor_id": "monitor-1"},
                {"inst_uuid": "host-1-dup", "monitor_id": "monitor-1"},
                {"inst_uuid": "host-2", "monitor_id": "monitor-2"},
            ]
        },
        policies={1: SimpleNamespace(id=1)},
    )
    grouped = [
        {"monitor_instance_id": "monitor-1", "alert_type": "alert", "level": "error", "count": 2},
        {"monitor_instance_id": "monitor-1", "alert_type": "no_data", "level": "", "count": 1},
        {"monitor_instance_id": "monitor-2", "alert_type": "alert", "level": "warning", "count": 3},
    ]
    monkeypatch.setattr(
        Application3DQueryService,
        "_grouped_alert_counts_by_monitor",
        classmethod(lambda cls, scope, monitor_ids: [row for row in grouped if row["monitor_instance_id"] in monitor_ids]),
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: applications))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: scope))
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: applications[0]))
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_paged_scoped_alerts",
        classmethod(lambda cls, scope, app_id, *, cursor: ([], False)),
    )

    wall_health = Application3DQueryService.wall(_request())["items"][0]["health"]
    detail = Application3DQueryService.application_detail(_request(), APP_A)
    detail_health = detail["application"]["health"]

    assert wall_health["activeAlarmCount"] == detail_health["activeAlarmCount"] == 6
    assert wall_health["noDataAlarmCount"] == detail_health["noDataAlarmCount"] == 1
    assert wall_health["severityCounts"] == detail_health["severityCounts"]
    assert wall_health["highestSeverity"]["id"] == detail_health["highestSeverity"]["id"] == "error"


def test_alarm_detail_no_data_keeps_severity(monkeypatch):
    application = _application(APP_A, "app")
    policy = SimpleNamespace(
        id=1,
        alert_name="告警名称模板-不得出现在指标",
        name="CPU",
        notice=False,
        monitor_object=SimpleNamespace(name="Host"),
        metric_unit="",
        calculation_unit="%",
        threshold_unit="",
        query_condition={"type": "metric", "metric_id": 9},
    )
    alert = SimpleNamespace(
        id="7",
        content="主机无数据",
        alert_type="no_data",
        level="critical",
        start_event_time=None,
        end_event_time=None,
        policy_id=1,
        metric_instance_id="instance-should-not-be-metric-id",
        monitor_instance_id="monitor-1",
        value=None,
        monitor_instance_name="host-1",
        notice_logs=[],
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: application),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(
            lambda cls, request, apps: _scope(
                apps,
                policies={1: policy},
                hosts_by_app={APP_A: [{"inst_uuid": "host-1", "inst_name": "host-1", "monitor_id": "monitor-1"}]},
            )
        ),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_scoped_alert_or_404",
        classmethod(lambda cls, scope, app_id, alarm_id: alert),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_adjacent_scoped_alert_ids",
        classmethod(lambda cls, scope, app_id, current: (None, None)),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.metric_fields.Metric.objects.filter",
        lambda **kwargs: SimpleNamespace(
            only=lambda *fields: SimpleNamespace(
                first=lambda: SimpleNamespace(id=9, display_name="CPU 使用率", name="cpu_usage"),
            )
        ),
    )

    result = Application3DQueryService.alarm_detail(_request(), APP_A, "7")
    assert result["alarm"]["content"] == "主机无数据"
    assert result["alarm"]["isNoData"] is True
    assert result["alarm"]["alertType"] == "no_data"
    assert result["alarm"]["severity"]["id"] == "critical"
    assert result["alarm"]["metric"]["id"] == "9"
    assert result["alarm"]["metric"]["name"] == "CPU 使用率"
    assert result["alarm"]["metric"]["name"] != policy.alert_name
    assert result["alarm"]["resource"]["id"] == "host-1"
    assert result["alarm"]["policy"]["name"] == "CPU"
    assert result["alarm"]["dimensions"] == []


def test_alarm_detail_includes_dimensions_and_occurred_at(monkeypatch):
    from datetime import datetime, timezone

    application = _application(APP_A, "app")
    started = datetime(2026, 8, 25, 17, 55, 17, tzinfo=timezone.utc)
    policy = SimpleNamespace(
        id=1,
        alert_name="x",
        name="CPU",
        notice=False,
        monitor_object=SimpleNamespace(name="Host"),
        metric_unit="%",
        calculation_unit="%",
        threshold_unit="%",
        query_condition={},
        threshold=[],
    )
    alert = SimpleNamespace(
        id="8",
        content="disk",
        alert_type="alert",
        level="warning",
        start_event_time=started,
        end_event_time=None,
        policy_id=1,
        metric_instance_id="",
        monitor_instance_id="monitor-1",
        value=80,
        monitor_instance_name="host-1",
        notice_logs=[],
        dimensions={"device": "sda1", "mount": "/data"},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: application),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(
            lambda cls, request, apps: _scope(
                apps,
                policies={1: policy},
                hosts_by_app={APP_A: [{"inst_uuid": "host-1", "inst_name": "host-1", "monitor_id": "monitor-1"}]},
            )
        ),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_scoped_alert_or_404",
        classmethod(lambda cls, scope, app_id, alarm_id: alert),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_adjacent_scoped_alert_ids",
        classmethod(lambda cls, scope, app_id, current: (None, None)),
    )
    result = Application3DQueryService.alarm_detail(_request(), APP_A, "8")
    assert result["alarm"]["occurredAt"] == started.isoformat()
    assert result["alarm"]["dimensions"] == [
        {"key": "device", "label": "device", "displayValue": "sda1"},
        {"key": "mount", "label": "mount", "displayValue": "/data"},
    ]
    assert result["alarm"]["metric"]["name"] is None


def test_metric_series_uses_metric_display_name_positive_path(monkeypatch):
    from datetime import datetime, timezone

    policy = SimpleNamespace(
        id=1,
        name="application3D 本地演示策略",
        alert_name="CPU 使用率过高",
        query_condition={"type": "metric", "metric_id": 9},
        metric_unit="%",
        calculation_unit="%",
        threshold_unit="%",
        threshold=[
            {"level": "warning", "value": 70, "method": ">"},
            {"level": "critical", "value": 90, "method": ">="},
        ],
    )
    alert = SimpleNamespace(
        id="16",
        content="[application3d-demo] CPU 持续超过 95%",
        policy_id=1,
        start_event_time=datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_scope_and_alert",
        classmethod(lambda cls, request, application_id, alarm_id: (alert, policy)),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.MonitorAlertMetricSnapshot.objects.filter",
        lambda **kwargs: SimpleNamespace(first=lambda: SimpleNamespace(snapshots=[{"raw_data": {"values": []}}])),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.convert_snapshots_copy",
        lambda raw, source, target: raw,
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_snapshot_points",
        staticmethod(
            lambda snapshots: [
                {"timestamp": "2026-08-25T17:00:00+00:00", "value": 80.0},
                {"timestamp": "2026-08-25T18:00:00+00:00", "value": 96.0},
            ]
        ),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.metric_fields.Metric.objects.filter",
        lambda **kwargs: SimpleNamespace(
            only=lambda *fields: SimpleNamespace(
                first=lambda: SimpleNamespace(id=9, display_name="CPU 使用率", name="cpu_usage"),
            )
        ),
    )

    result = Application3DQueryService.metric_series(_request(), APP_A, "16")
    assert result["series"][0]["name"] == "CPU 使用率"
    assert result["series"][0]["name"] != policy.name
    assert result["series"][0]["name"] != policy.alert_name
    assert [row["level"] for row in result["thresholds"]] == ["warning", "critical"]
    assert result["thresholds"][1]["operator"] == ">="
    assert result["thresholds"][1]["label"] == "严重"


def test_metric_series_name_null_without_policy_name_fallback(monkeypatch):
    from datetime import datetime, timezone

    policy = SimpleNamespace(
        id=1,
        name="application3D 本地演示策略",
        alert_name="CPU 使用率过高",
        query_condition={},
        metric_unit="%",
        calculation_unit="%",
        threshold_unit="%",
        threshold=[{"level": "critical", "value": 90, "method": ">"}],
    )
    alert = SimpleNamespace(
        id="15",
        content="内存使用率异常",
        policy_id=1,
        start_event_time=datetime(2026, 8, 25, 18, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_scope_and_alert",
        classmethod(lambda cls, request, application_id, alarm_id: (alert, policy)),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.MonitorAlertMetricSnapshot.objects.filter",
        lambda **kwargs: SimpleNamespace(
            first=lambda: SimpleNamespace(
                snapshots=[{"raw_data": {"values": [[1724601600, 80.0], [1724601900, 91.0]]}}],
            )
        ),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_snapshot_points",
        staticmethod(
            lambda snapshots: [
                {"timestamp": "2026-08-25T17:00:00+00:00", "value": 80.0},
                {"timestamp": "2026-08-25T18:00:00+00:00", "value": 91.0},
            ]
        ),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.convert_snapshots_copy",
        lambda raw, source, target: raw,
    )

    result = Application3DQueryService.metric_series(_request(), APP_A, "15")
    assert result["state"] == "available"
    assert result["series"][0]["name"] is None
    assert result["series"][0]["name"] != policy.name
    assert result["thresholds"] == [
        {"level": "critical", "value": 90.0, "operator": ">", "label": "严重"},
    ]
    assert result["alarmMarker"]["timestamp"] == alert.start_event_time.isoformat()


def test_alarm_detail_notification_execution_states(monkeypatch):
    application = _application(APP_A, "app")

    def _detail(notice: bool, logs):
        policy = SimpleNamespace(
            id=1,
            alert_name="x",
            name="CPU",
            notice=notice,
            monitor_object=SimpleNamespace(name="Host"),
            metric_unit="",
            calculation_unit="",
            threshold_unit="",
            query_condition={},
        )
        alert = SimpleNamespace(
            id="7",
            content="c",
            alert_type="alert",
            level="warning",
            start_event_time=None,
            end_event_time=None,
            policy_id=1,
            metric_instance_id=None,
            monitor_instance_id="monitor-1",
            value=None,
            monitor_instance_name="host-1",
            notice_logs=logs,
        )
        monkeypatch.setattr(
            Application3DQueryService,
            "_visible_application",
            classmethod(lambda cls, request, application_id: application),
        )
        monkeypatch.setattr(
            Application3DQueryService,
            "_build_scope",
            classmethod(
                lambda cls, request, apps: _scope(
                    apps,
                    policies={1: policy},
                    hosts_by_app={APP_A: [{"inst_uuid": "host-1", "inst_name": "host-1", "monitor_id": "monitor-1"}]},
                )
            ),
        )
        monkeypatch.setattr(
            Application3DQueryService,
            "_scoped_alert_or_404",
            classmethod(lambda cls, scope, app_id, alarm_id: alert),
        )
        monkeypatch.setattr(
            Application3DQueryService,
            "_adjacent_scoped_alert_ids",
            classmethod(lambda cls, scope, app_id, current: (None, None)),
        )
        return Application3DQueryService.alarm_detail(_request(), APP_A, "7")["alarm"]["notification"]

    assert _detail(False, [{"success": True}]) == {"configured": False, "state": "not_configured"}
    assert _detail(True, [{"success": True}, {"success": True}]) == {"configured": True, "state": "delivered"}
    assert _detail(True, [{"success": True}, {"success": False}]) == {
        "configured": True,
        "state": "partially_delivered",
    }


def test_alarm_detail_cross_application_idor_fails_closed(monkeypatch):
    application = _application(APP_A, "app")
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: application),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps, policies={1: SimpleNamespace(id=1)})),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_scoped_alert_or_404",
        classmethod(lambda cls, scope, app_id, alarm_id: (_ for _ in ()).throw(Application3DNotFound("告警不存在"))),
    )

    with pytest.raises(Application3DNotFound):
        Application3DQueryService.alarm_detail(_request(), APP_A, "other-alarm")


def test_adjacent_scoped_alert_ids_returns_immediate_neighbors(monkeypatch):
    """previous is the closest more-recent alert (not the newest in the whole scope)."""
    from datetime import datetime, timedelta, timezone

    from django.db.models import Q

    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    alerts = [
        SimpleNamespace(id="a", start_event_time=now),
        SimpleNamespace(id="b", start_event_time=now - timedelta(minutes=1)),
        SimpleNamespace(id="c", start_event_time=now - timedelta(minutes=2)),
    ]

    def eval_q(q: Q, alert) -> bool:
        parts = []
        for child in q.children:
            if isinstance(child, Q):
                parts.append(eval_q(child, alert))
                continue
            field, expected = child
            value = alert.start_event_time
            if field == "start_event_time__gt":
                parts.append(value is not None and value > expected)
            elif field == "start_event_time__lt":
                parts.append(value is not None and value < expected)
            elif field == "start_event_time":
                parts.append(value == expected)
            elif field == "start_event_time__isnull":
                parts.append((value is None) is bool(expected))
            elif field == "id__gt":
                parts.append(str(alert.id) > str(expected))
            elif field == "id__lt":
                parts.append(str(alert.id) < str(expected))
            else:
                parts.append(False)
        if not parts:
            return True
        ok = all(parts) if q.connector == Q.AND else any(parts)
        return (not ok) if q.negated else ok

    class _QS:
        def __init__(self, rows):
            self.rows = list(rows)

        def filter(self, *args, **kwargs):
            q = Q()
            for arg in args:
                q &= arg
            for key, value in kwargs.items():
                q &= Q(**{key: value})
            return _QS([row for row in self.rows if eval_q(q, row)])

        def order_by(self, *args, **kwargs):
            descending = any(getattr(arg, "descending", False) for arg in args) or any(isinstance(arg, str) and arg.startswith("-") for arg in args)
            rows = list(self.rows)
            if descending:
                rows.sort(
                    key=lambda item: (
                        item.start_event_time is None,
                        -(item.start_event_time.timestamp() if item.start_event_time else 0),
                        str(item.id),
                    )
                )
            else:
                # asc(nulls_first), id
                rows.sort(
                    key=lambda item: (
                        item.start_event_time is not None,
                        item.start_event_time.timestamp() if item.start_event_time else 0,
                        str(item.id),
                    )
                )
            return _QS(rows)

        def first(self):
            return self.rows[0] if self.rows else None

    monkeypatch.setattr(
        Application3DQueryService,
        "_scoped_active_alerts_qs",
        classmethod(lambda cls, scope, monitor_ids: _QS(alerts)),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_monitor_ids_for_app",
        classmethod(lambda cls, scope, app_id: {"m1"}),
    )

    scope = _scope([_application(APP_A, "app")])
    prev, nxt = Application3DQueryService._adjacent_scoped_alert_ids(scope, APP_A, alerts[1])
    assert (prev, nxt) == ("a", "c")
    prev_head, nxt_head = Application3DQueryService._adjacent_scoped_alert_ids(scope, APP_A, alerts[0])
    assert (prev_head, nxt_head) == (None, "b")


def test_capacity_exceeded_is_not_truncated(monkeypatch):
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **kwargs: {},
    )
    monkeypatch.setattr(
        InstanceManage,
        "instance_list",
        lambda **kwargs: ([], 501),
    )

    with pytest.raises(Application3DCapacityExceeded) as exc_info:
        Application3DQueryService._visible_applications(_request())

    assert exc_info.value.extra == {"actualCount": 501, "supportedCount": 500}


def test_application_detail_uses_cmdb_visible_fields_and_keeps_allowlist(monkeypatch):
    application = {
        **_application(APP_A, "app"),
        "app_id": "A-1",
        "operator": "hidden-user",
        "bak_operator": "sensitive-user",
        "comment": "visible-comment",
        "secret_token": "must-not-leak",
    }
    attrs = [
        {"attr_id": "app_id", "attr_name": "ID", "attr_type": "str"},
        {"attr_id": "operator", "attr_name": "Operator", "attr_type": "str"},
        {"attr_id": "bak_operator", "attr_name": "Backup", "attr_type": "password"},
        {"attr_id": "comment", "attr_name": "Comment", "attr_type": "str"},
        {"attr_id": "secret_token", "attr_name": "Secret", "attr_type": "str"},
    ]
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: application))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: _scope(apps)))
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: attrs)
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: ["app_id", "bak_operator", "comment", "secret_token"],
    )

    result = Application3DQueryService.application_detail(_request(), APP_A)

    assert [item["key"] for item in result["application"]["properties"]] == ["app_id", "comment"]


def test_application_detail_cursor_returns_second_page_without_duplicates(monkeypatch):
    application = _application(APP_A, "app")
    alerts = [_alert(index) for index in range(25, 0, -1)]
    request = _request()
    request.data = {}
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: application))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps, policies={1: SimpleNamespace(id=1, alert_name="p", name="p", notice=False)})),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_health_for_application",
        classmethod(
            lambda cls, scope, app_id: {
                "state": "alarming",
                "reason": "active_alarm",
                "activeAlarmCount": 25,
                "severityCounts": {"critical": 0, "error": 0, "warning": 25, "info": 0},
                "noDataAlarmCount": 0,
                "highestSeverity": {"id": "warning"},
                "stale": False,
            }
        ),
    )

    def paged(cls, scope, app_id, *, cursor):
        ordered = alerts
        if cursor:
            padding = "=" * (-len(cursor) % 4)
            decoded = __import__("json").loads(__import__("base64").urlsafe_b64decode(cursor + padding).decode())
            start = next(i for i, item in enumerate(ordered) if str(item.id) == str(decoded[1])) + 1
            ordered = ordered[start:]
        page = ordered[:21]
        return page[:20], len(page) > 20

    monkeypatch.setattr(Application3DQueryService, "_paged_scoped_alerts", classmethod(paged))
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )

    first = Application3DQueryService.application_detail(request, APP_A)
    request.data = {"cursor": first["alarms"]["page"]["nextCursor"]}
    second = Application3DQueryService.application_detail(request, APP_A)

    first_ids = [item["id"] for item in first["alarms"]["items"]]
    second_ids = [item["id"] for item in second["alarms"]["items"]]
    assert len(first_ids) == 20
    assert len(second_ids) == 5
    assert set(first_ids).isdisjoint(second_ids)


def test_application_detail_rejects_tampered_and_stale_cursors(monkeypatch):
    from apps.operation_analysis.services.application3d.errors import Application3DInvalidRequest

    application = _application(APP_A, "app")
    request = _request()
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: application))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps, policies={1: SimpleNamespace(id=1)})),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_health_for_application",
        classmethod(
            lambda cls, scope, app_id: {
                "state": "normal",
                "reason": "no_active_alarm",
                "activeAlarmCount": 0,
                "severityCounts": {"critical": 0, "error": 0, "warning": 0, "info": 0},
                "noDataAlarmCount": 0,
                "highestSeverity": {"id": "normal"},
                "stale": False,
            }
        ),
    )
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )

    def paged_invalid(cls, scope, app_id, *, cursor):
        if cursor == "not-a-valid-cursor":
            raise Application3DInvalidRequest("cursor 无效")
        raise Application3DInvalidRequest("cursor 已失效")

    monkeypatch.setattr(Application3DQueryService, "_paged_scoped_alerts", classmethod(paged_invalid))

    request.data = {"cursor": "not-a-valid-cursor"}
    with pytest.raises(Application3DInvalidRequest, match="cursor 无效"):
        Application3DQueryService.application_detail(request, APP_A)

    request.data = {"cursor": Application3DQueryService._encode_cursor(_alert(999))}
    with pytest.raises(Application3DInvalidRequest, match="cursor 已失效"):
        Application3DQueryService.application_detail(request, APP_A)


def test_visible_hosts_uses_bounded_batches(monkeypatch):
    host_ids = [f"host-{index}" for index in range(205)]
    calls = []
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **kwargs: {},
    )

    def instance_list(**kwargs):
        calls.append(kwargs)
        values = kwargs["params"][0]["value"]
        return ([{"inst_uuid": value} for value in values], len(values))

    monkeypatch.setattr(InstanceManage, "instance_list", instance_list)

    result = Application3DQueryService._visible_hosts(_request(), host_ids)

    assert len(result) == 205
    assert len(calls) == 3
    assert all(call["page_size"] == 100 for call in calls)
    assert max(len(call["params"][0]["value"]) for call in calls) <= 100


def test_accessible_policies_queries_only_referenced_ids(monkeypatch):
    class Queryset:
        def filter(self, **kwargs):
            assert kwargs == {"id__in": {7, 9}}
            return self

        def select_related(self, value):
            assert value == "monitor_object"
            return [SimpleNamespace(id=7)]

    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service._AlertPolicyScope.get_accessible_policy_queryset",
        lambda self, request: Queryset(),
    )

    result = Application3DQueryService._accessible_policies(_request(), {7, 9})

    assert set(result) == {7}
