from types import SimpleNamespace

import pytest

from apps.cmdb.services.instance import InstanceManage
from apps.operation_analysis.services.application3d.errors import Application3DCapacityExceeded, Application3DInvalidRequest, Application3DNotFound
from apps.operation_analysis.services.application3d.query_service import Application3DQueryService, _ApplicationScope

APP_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
APP_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
APP_C = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
SYSTEM_A = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SYSTEM_B = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


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


def _system(system_id, name, **fields):
    payload = {"inst_uuid": system_id, "inst_name": name, "model_id": "system"}
    payload.update(fields)
    return payload


def _application(app_id, name, **fields):
    payload = {"inst_uuid": app_id, "inst_name": name, "model_id": "application"}
    payload.update(fields)
    return payload


def _scope(applications, *, complete_apps=None, policies=None, hosts_by_app=None, empty_systems=None, no_host_systems=None):
    return _ApplicationScope(
        applications=applications,
        hosts_by_app=hosts_by_app if hosts_by_app is not None else {item["inst_uuid"]: [] for item in applications},
        policies=policies or {},
        complete_apps=set(complete_apps if complete_apps is not None else [item["inst_uuid"] for item in applications]),
        empty_systems=set(empty_systems or []),
        no_host_systems=set(no_host_systems or []),
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


def test_system_status_filter_uses_system_own_status(monkeypatch):
    systems = [
        _system(SYSTEM_A, "online", status=["1"]),
        _system(SYSTEM_B, "testing", status=["2"]),
        _system(APP_A, "unset"),
    ]
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
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )

    result = Application3DQueryService.wall(
        _request(),
        applied_filters={"system_status": ["1"]},
    )

    assert [item["id"] for item in result["items"]] == [SYSTEM_A]


def test_system_status_filter_matches_cmdb_enum_list(monkeypatch):
    """Live CMDB stores single-select enum as list, e.g. status=['1']."""
    systems = [
        _system(SYSTEM_A, "sys-online", status=["1"]),
        _system(SYSTEM_B, "sys-testing", status=["2"]),
    ]
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
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )

    result = Application3DQueryService.wall(
        _request(),
        applied_filters={"system_status": ["1"]},
    )

    assert [item["id"] for item in result["items"]] == [SYSTEM_A]


def test_unset_system_status_returns_all_visible_systems(monkeypatch):
    systems = [
        _system(SYSTEM_A, "online", status=["1"]),
        _system(SYSTEM_B, "testing", status=["2"]),
    ]
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))
    monkeypatch.setattr(
        Application3DQueryService,
        "_build_scope",
        classmethod(lambda cls, request, apps: _scope(apps)),
    )

    result = Application3DQueryService.wall(_request())

    assert [item["id"] for item in result["items"]] == [SYSTEM_A, SYSTEM_B]
    assert result["appliedFilters"] == {"system_status": []}


def test_system_status_invalid_value_is_rejected(monkeypatch):
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: []))

    with pytest.raises(Application3DInvalidRequest, match="system_status 包含非法值"):
        Application3DQueryService.wall(_request(), applied_filters={"system_status": ["not-an-option"]})


def test_empty_system_wall_and_detail_are_unknown_no_application(monkeypatch):
    systems = [_system(SYSTEM_A, "empty")]
    scope = _scope(systems, complete_apps=[], empty_systems=[SYSTEM_A])
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: scope))
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: systems[0]))
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )

    wall_item = Application3DQueryService.wall(_request())["items"][0]
    detail = Application3DQueryService.application_detail(_request(), SYSTEM_A)

    for health in (wall_item["health"], detail["application"]["health"]):
        assert health["state"] == "unknown"
        assert health["reason"] == "no_application"
        assert health["activeAlarmCount"] is None
        assert health["severityCounts"] is None
        assert health["noDataAlarmCount"] is None
        assert health["highestSeverity"] is None
    assert detail["alarms"] == {"state": "unavailable"}


def test_zero_hosts_is_unknown_no_host(monkeypatch):
    systems = [_system(SYSTEM_A, "apps-no-hosts")]
    scope = _scope(systems, complete_apps=[], no_host_systems=[SYSTEM_A])
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: scope))
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: systems[0]))
    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", lambda model_id: [])
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: None,
    )

    wall_item = Application3DQueryService.wall(_request())["items"][0]
    detail = Application3DQueryService.application_detail(_request(), SYSTEM_A)

    for health in (wall_item["health"], detail["application"]["health"]):
        assert health["state"] == "unknown"
        assert health["reason"] == "no_host"
        assert health["reason"] != "unavailable"
        assert health["reason"] != "no_application"
        assert health["activeAlarmCount"] is None
    assert detail["alarms"] == {"state": "unavailable"}


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
    seen = {}
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **kwargs: {},
    )

    def instance_list(**kwargs):
        seen.update(kwargs)
        return ([], 501)

    monkeypatch.setattr(InstanceManage, "instance_list", instance_list)

    with pytest.raises(Application3DCapacityExceeded) as exc_info:
        Application3DQueryService._visible_applications(_request())

    assert seen["model_id"] == "system"
    assert seen["order"] == "inst_name"
    assert exc_info.value.extra == {"actualCount": 501, "supportedCount": 500}


def test_visible_application_queries_system_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.CmdbRulesFormatUtil.format_user_groups_permissions",
        lambda **kwargs: {},
    )

    def instance_list(**kwargs):
        seen.update(kwargs)
        return ([_system(SYSTEM_A, "sys")], 1)

    monkeypatch.setattr(InstanceManage, "instance_list", instance_list)

    result = Application3DQueryService._visible_application(_request(), SYSTEM_A)

    assert seen["model_id"] == "system"
    assert result["inst_uuid"] == SYSTEM_A


def test_application_detail_uses_cmdb_visible_fields_and_keeps_allowlist(monkeypatch):
    system = {
        **_system(SYSTEM_A, "sys"),
        "system_code": "SYS-1",
        "status": "1",
        "organization": "ops",
        "operator": "hidden-user",
        "comment": "visible-comment",
        "productor": "pm",
        "developer": "dev",
        "tester": "qa",
        "inst_name": "sys",
        "time_zone": "Asia/Shanghai",
        "secret_token": "must-not-leak",
    }
    attrs = [
        {"attr_id": "system_code", "attr_name": "系统编号", "attr_type": "str"},
        {"attr_id": "status", "attr_name": "运行状态", "attr_type": "str"},
        {"attr_id": "organization", "attr_name": "组织", "attr_type": "str"},
        {"attr_id": "operator", "attr_name": "运维人员", "attr_type": "str"},
        {"attr_id": "comment", "attr_name": "系统描述", "attr_type": "str"},
        {"attr_id": "productor", "attr_name": "产品人员", "attr_type": "str"},
        {"attr_id": "developer", "attr_name": "开发人员", "attr_type": "str"},
        {"attr_id": "tester", "attr_name": "测试人员", "attr_type": "str"},
        {"attr_id": "inst_name", "attr_name": "系统名称", "attr_type": "str"},
        {"attr_id": "time_zone", "attr_name": "时区", "attr_type": "str"},
        {"attr_id": "secret_token", "attr_name": "Secret", "attr_type": "str"},
    ]
    seen_models = []
    monkeypatch.setattr(Application3DQueryService, "_visible_application", classmethod(lambda cls, request, application_id: system))
    monkeypatch.setattr(Application3DQueryService, "_build_scope", classmethod(lambda cls, request, apps: _scope(apps)))

    def search_model_attr(model_id):
        seen_models.append(model_id)
        return attrs

    monkeypatch.setattr("apps.operation_analysis.services.application3d.query_service.ModelManage.search_model_attr", search_model_attr)
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.ApplicationResourceOverviewService._get_show_fields",
        lambda model_id, user: ["system_code", "status", "comment", "productor", "secret_token", "inst_name", "time_zone"],
    )

    result = Application3DQueryService.application_detail(_request(), SYSTEM_A)

    assert seen_models == ["system"]
    assert [item["key"] for item in result["application"]["properties"]] == ["system_code", "status", "comment", "productor"]
    assert "inst_name" not in {item["key"] for item in result["application"]["properties"]}
    assert "time_zone" not in {item["key"] for item in result["application"]["properties"]}
    assert "operator" not in {item["key"] for item in result["application"]["properties"]}


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


def _stub_empty_alert_qs(monkeypatch):
    class _EmptyQS:
        def filter(self, **kwargs):
            return self

        def exclude(self, **kwargs):
            return self

        def values_list(self, *args, **kwargs):
            return self

        def distinct(self):
            return []

    empty = _EmptyQS()
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.MonitorAlert.objects",
        SimpleNamespace(filter=lambda **kwargs: empty, none=lambda: empty),
    )


def test_build_scope_empty_system_is_no_application_not_normal(monkeypatch):
    systems = [_system(SYSTEM_A, "empty")]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: []},
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda app_ids: (_ for _ in ()).throw(AssertionError("empty systems must not project application_run_host")),
    )

    scope = Application3DQueryService._build_scope(_request(), systems)

    assert scope.empty_systems == {SYSTEM_A}
    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    assert scope.hosts_by_app[SYSTEM_A] == []


def test_build_scope_hidden_child_applications_are_unavailable(monkeypatch):
    systems = [_system(SYSTEM_A, "partial")]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: [APP_A, APP_B]},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_model_instances",
        classmethod(lambda cls, request, model_id, inst_uuids: [_application(APP_A, "visible")]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda app_ids: (_ for _ in ()).throw(AssertionError("hidden child applications must not project hosts")),
    )

    scope = Application3DQueryService._build_scope(_request(), systems)

    assert SYSTEM_A not in scope.empty_systems
    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    health = Application3DQueryService._health_for_application(scope, SYSTEM_A)
    assert health["reason"] == "unavailable"
    assert health["reason"] != "no_host"
    assert health["state"] == "unknown"


def test_build_scope_unions_child_hosts_and_dedupes_shared_monitor(monkeypatch):
    systems = [_system(SYSTEM_A, "union")]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: [APP_A, APP_B]},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_model_instances",
        classmethod(
            lambda cls, request, model_id, inst_uuids: [
                _application(APP_A, "app-a"),
                _application(APP_B, "app-b"),
            ]
        ),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda app_ids: {APP_A: ["host-1"], APP_B: ["host-1", "host-2"]},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_hosts",
        classmethod(
            lambda cls, request, host_ids: [
                {"inst_uuid": "host-1", "monitor_id": "monitor-shared"},
                {"inst_uuid": "host-2", "monitor_id": "monitor-2"},
            ]
        ),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_authorized_monitor_ids",
        classmethod(lambda cls, request, candidate_ids: set(candidate_ids)),
    )
    _stub_empty_alert_qs(monkeypatch)

    scope = Application3DQueryService._build_scope(_request(), systems)

    assert SYSTEM_A in scope.complete_apps
    assert SYSTEM_A not in scope.empty_systems
    assert [host["inst_uuid"] for host in scope.hosts_by_app[SYSTEM_A]] == ["host-1", "host-2"]
    assert Application3DQueryService._monitor_ids_for_app(scope, SYSTEM_A) == {"monitor-shared", "monitor-2"}


def test_build_scope_zero_host_child_applications_are_no_host(monkeypatch):
    systems = [_system(SYSTEM_A, "apps-no-hosts")]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: [APP_A]},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_model_instances",
        classmethod(lambda cls, request, model_id, inst_uuids: [_application(APP_A, "empty-app")]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda app_ids: {APP_A: []},
    )

    scope = Application3DQueryService._build_scope(_request(), systems)

    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.empty_systems
    assert scope.no_host_systems == {SYSTEM_A}
    health = Application3DQueryService._health_for_application(scope, SYSTEM_A)
    assert health["state"] == "unknown"
    assert health["reason"] == "no_host"
    assert health["activeAlarmCount"] is None
    assert health["reason"] != "unavailable"
    assert health["reason"] != "no_application"
    assert not (health["state"] == "normal" and health["activeAlarmCount"] == 0)


class _AlertQuery:
    """In-memory MonitorAlert queryset stand-in for scope + health aggregation tests."""

    def __init__(self, rows):
        self._rows = list(rows)

    def filter(self, **kwargs):
        rows = self._rows
        if "status" in kwargs:
            rows = [row for row in rows if row.get("status", "new") == kwargs["status"]]
        if "monitor_instance_id__in" in kwargs:
            allowed = set(kwargs["monitor_instance_id__in"])
            rows = [row for row in rows if row["monitor_instance_id"] in allowed]
        if "policy_id__in" in kwargs:
            allowed = set(kwargs["policy_id__in"])
            rows = [row for row in rows if row["policy_id"] in allowed]
        return _AlertQuery(rows)

    def exclude(self, **kwargs):
        rows = self._rows
        if "policy_id__in" in kwargs:
            denied = set(kwargs["policy_id__in"])
            rows = [row for row in rows if row["policy_id"] not in denied]
        return _AlertQuery(rows)

    def values_list(self, field, flat=False):
        return _AlertValues([row[field] for row in self._rows])

    def values(self, *fields):
        return _AlertGrouped(self._rows, fields)

    def distinct(self):
        return list(dict.fromkeys(self._rows))


class _AlertValues:
    def __init__(self, values):
        self._values = list(values)

    def distinct(self):
        return list(dict.fromkeys(self._values))


class _AlertGrouped:
    def __init__(self, rows, fields):
        self._rows = list(rows)
        self._fields = fields

    def annotate(self, **kwargs):
        grouped: dict[tuple, int] = {}
        for row in self._rows:
            key = tuple(row[field] for field in self._fields)
            grouped[key] = grouped.get(key, 0) + 1
        return [{**dict(zip(self._fields, key)), "count": count} for key, count in grouped.items()]


def _stub_monitor_alerts(monkeypatch, rows):
    table = _AlertQuery(rows)
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.MonitorAlert.objects",
        SimpleNamespace(filter=table.filter, none=lambda: _AlertQuery([])),
    )


def _patch_system_host_graph(
    monkeypatch,
    *,
    child_apps,
    hosts_by_app,
    visible_hosts,
    authorized_monitor_ids=None,
    accessible_policy_ids="all",
):
    app_ids = [app["inst_uuid"] for app in child_apps]
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: app_ids},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_model_instances",
        classmethod(lambda cls, request, model_id, inst_uuids: list(child_apps)),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda ids: hosts_by_app,
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_hosts",
        classmethod(lambda cls, request, host_ids: list(visible_hosts)),
    )
    allowed = authorized_monitor_ids
    monkeypatch.setattr(
        Application3DQueryService,
        "_authorized_monitor_ids",
        classmethod(
            lambda cls, request, candidate_ids, permitted=allowed: set(candidate_ids) if permitted is None else set(permitted) & set(candidate_ids)
        ),
    )

    def _policies(request, policy_ids, permitted=accessible_policy_ids):
        selected = set(policy_ids) if permitted == "all" else set(permitted) & set(policy_ids)
        return {pid: SimpleNamespace(id=pid) for pid in selected}

    monkeypatch.setattr(Application3DQueryService, "_accessible_policies", staticmethod(_policies))


def _finance_settlement_children():
    return [
        _application(APP_A, "结算中心"),
        _application(APP_B, "对账服务"),
        _application(APP_C, "财务任务调度"),
    ]


def _finance_settlement_hosts_by_app():
    return {APP_A: ["host-07"], APP_B: ["host-07"], APP_C: ["host-08"]}


def test_build_scope_mixed_mapped_and_unmapped_hosts_aggregates_mapped_alerts(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children(),
        hosts_by_app=_finance_settlement_hosts_by_app(),
        visible_hosts=[
            {"inst_uuid": "host-07", "monitor_id": "app3d-demo-host-07"},
            {"inst_uuid": "host-08", "monitor_id": ""},
        ],
    )
    _stub_monitor_alerts(
        monkeypatch,
        [
            {"monitor_instance_id": "app3d-demo-host-07", "policy_id": 1, "alert_type": "alert", "level": "critical", "status": "new"},
            {"monitor_instance_id": "app3d-demo-host-07", "policy_id": 1, "alert_type": "alert", "level": "error", "status": "new"},
        ],
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))

    scope = Application3DQueryService._build_scope(_request(), systems)
    result = Application3DQueryService.wall(_request())

    assert SYSTEM_A in scope.complete_apps
    assert Application3DQueryService._monitor_ids_for_app(scope, SYSTEM_A) == {"app3d-demo-host-07"}
    assert [host["inst_uuid"] for host in scope.hosts_by_app[SYSTEM_A]] == ["host-07", "host-08"]
    health = result["items"][0]["health"]
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["activeAlarmCount"] == 2
    assert health["severityCounts"]["critical"] == 1
    assert health["severityCounts"]["error"] == 1


def test_build_scope_all_unmapped_hosts_stay_unavailable_not_normal(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children(),
        hosts_by_app=_finance_settlement_hosts_by_app(),
        visible_hosts=[
            {"inst_uuid": "host-07", "monitor_id": None},
            {"inst_uuid": "host-08", "monitor_id": ""},
        ],
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService.wall(_request())["items"][0]["health"]

    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.empty_systems
    assert health["state"] == "unknown"
    assert health["reason"] == "unavailable"
    assert health["activeAlarmCount"] is None
    assert health["reason"] != "no_application"
    assert health["reason"] != "no_host"
    assert SYSTEM_A not in scope.no_host_systems
    assert not (health["state"] == "normal" and health["activeAlarmCount"] == 0)


def test_build_scope_hidden_policy_on_mapped_host_still_unavailable(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children() + [_application("ffffffff-ffff-4fff-8fff-ffffffffffff", "报表服务")],
        hosts_by_app={
            APP_A: ["host-07"],
            APP_B: ["host-07"],
            APP_C: ["host-08"],
            "ffffffff-ffff-4fff-8fff-ffffffffffff": ["host-09"],
        },
        visible_hosts=[
            {"inst_uuid": "host-07", "monitor_id": "app3d-demo-host-07"},
            {"inst_uuid": "host-08", "monitor_id": ""},
            {"inst_uuid": "host-09", "monitor_id": "app3d-demo-host-09"},
        ],
        accessible_policy_ids={2},
    )
    _stub_monitor_alerts(
        monkeypatch,
        [
            {"monitor_instance_id": "app3d-demo-host-07", "policy_id": 1, "alert_type": "alert", "level": "critical", "status": "new"},
            {"monitor_instance_id": "app3d-demo-host-09", "policy_id": 2, "alert_type": "alert", "level": "warning", "status": "new"},
        ],
    )

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService._health_for_application(scope, SYSTEM_A)

    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    assert health["reason"] == "unavailable"
    assert health["reason"] != "no_host"
    assert health["state"] == "unknown"
    assert health["activeAlarmCount"] is None


def test_build_scope_unauthorized_mapped_monitor_still_unavailable(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children() + [_application("ffffffff-ffff-4fff-8fff-ffffffffffff", "报表服务")],
        hosts_by_app={
            APP_A: ["host-07"],
            APP_B: ["host-07"],
            APP_C: ["host-08"],
            "ffffffff-ffff-4fff-8fff-ffffffffffff": ["host-09"],
        },
        visible_hosts=[
            {"inst_uuid": "host-07", "monitor_id": "app3d-demo-host-07"},
            {"inst_uuid": "host-08", "monitor_id": ""},
            {"inst_uuid": "host-09", "monitor_id": "app3d-demo-host-09"},
        ],
        authorized_monitor_ids={"app3d-demo-host-09"},
    )
    _stub_empty_alert_qs(monkeypatch)

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService._health_for_application(scope, SYSTEM_A)

    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    assert health["reason"] == "unavailable"
    assert health["reason"] != "no_host"
    assert health["activeAlarmCount"] is None


def test_build_scope_invisible_host_still_unavailable(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children(),
        hosts_by_app=_finance_settlement_hosts_by_app(),
        visible_hosts=[{"inst_uuid": "host-07", "monitor_id": "app3d-demo-host-07"}],
    )
    _stub_empty_alert_qs(monkeypatch)

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService._health_for_application(scope, SYSTEM_A)

    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    assert health["reason"] == "unavailable"
    assert health["reason"] != "no_host"
    assert health["activeAlarmCount"] is None


def test_build_scope_mixed_children_union_hosts_that_exist(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children(),
        hosts_by_app={APP_A: ["host-07"], APP_B: ["host-07"], APP_C: []},
        visible_hosts=[{"inst_uuid": "host-07", "monitor_id": "app3d-demo-host-07"}],
    )
    _stub_monitor_alerts(
        monkeypatch,
        [
            {
                "monitor_instance_id": "app3d-demo-host-07",
                "policy_id": 1,
                "alert_type": "alert",
                "level": "critical",
                "status": "new",
            }
        ],
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService.wall(_request())["items"][0]["health"]

    assert SYSTEM_A in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["activeAlarmCount"] == 1
    assert health["severityCounts"]["critical"] == 1


def test_build_scope_wrong_peer_does_not_fail_whole_system(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=_finance_settlement_children(),
        hosts_by_app={APP_A: ["host-07"], APP_B: [], APP_C: ["host-07"]},
        visible_hosts=[{"inst_uuid": "host-07", "monitor_id": "app3d-demo-host-07"}],
    )
    _stub_monitor_alerts(
        monkeypatch,
        [
            {
                "monitor_instance_id": "app3d-demo-host-07",
                "policy_id": 1,
                "alert_type": "alert",
                "level": "critical",
                "status": "new",
            }
        ],
    )
    monkeypatch.setattr(Application3DQueryService, "_filter_definition", classmethod(lambda cls: _filter_definition()))
    monkeypatch.setattr(Application3DQueryService, "_visible_applications", classmethod(lambda cls, request: systems))

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService.wall(_request())["items"][0]["health"]

    assert SYSTEM_A in scope.complete_apps
    assert SYSTEM_A not in scope.no_host_systems
    assert health["state"] == "alarming"
    assert health["reason"] == "active_alarm"
    assert health["reason"] != "unavailable"
    assert health["activeAlarmCount"] == 1
    assert health["severityCounts"]["critical"] == 1


def test_build_scope_only_wrong_peer_edges_are_no_host(monkeypatch):
    systems = [_system(SYSTEM_A, "财务结算平台")]
    _patch_system_host_graph(
        monkeypatch,
        child_apps=[_application(APP_A, "结算中心")],
        hosts_by_app={APP_A: []},
        visible_hosts=[],
    )

    scope = Application3DQueryService._build_scope(_request(), systems)
    health = Application3DQueryService._health_for_application(scope, SYSTEM_A)

    assert scope.no_host_systems == {SYSTEM_A}
    assert SYSTEM_A not in scope.complete_apps
    assert SYSTEM_A not in scope.empty_systems
    assert health["state"] == "unknown"
    assert health["reason"] == "no_host"
    assert health["reason"] != "unavailable"
    assert health["activeAlarmCount"] is None


def test_architecture_request_uses_system_uuid_and_dedupes_shared_host(monkeypatch):
    systems = [_system(SYSTEM_A, "union")]
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(
            lambda cls, request, application_id: systems[0] if application_id == SYSTEM_A else (_ for _ in ()).throw(Application3DNotFound("应用系统不存在"))
        ),
    )
    _patch_system_host_graph(
        monkeypatch,
        child_apps=[_application(APP_A, "app-a"), _application(APP_B, "app-b")],
        hosts_by_app={APP_A: ["host-1"], APP_B: ["host-1", "host-2"]},
        visible_hosts=[
            {"inst_uuid": "host-1", "inst_name": "shared", "monitor_id": "monitor-shared"},
            {"inst_uuid": "host-2", "inst_name": "only-b", "monitor_id": "monitor-2"},
        ],
    )
    _stub_empty_alert_qs(monkeypatch)

    result = Application3DQueryService.architecture(_request(), SYSTEM_A)

    assert result["systemId"] == SYSTEM_A
    assert [node["id"] for node in result["nodes"] if node["kind"] == "system"] == [SYSTEM_A]
    assert [node["id"] for node in result["nodes"] if node["kind"] == "application"] == [APP_A, APP_B]
    assert [node["id"] for node in result["nodes"] if node["kind"] == "host"] == ["host-1", "host-2"]
    shared_edges = [
        (edge["sourceId"], edge["targetId"])
        for edge in result["edges"]
        if edge["targetId"] == "host-1" and edge["relation"] == "application_run_host"
    ]
    assert set(shared_edges) == {(APP_A, "host-1"), (APP_B, "host-1")}
    assert not any(edge["sourceId"] == SYSTEM_A and edge["targetId"].startswith("host-") for edge in result["edges"])


def test_architecture_empty_system_is_root_without_fake_children(monkeypatch):
    systems = [_system(SYSTEM_A, "empty")]
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: systems[0]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: []},
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda app_ids: (_ for _ in ()).throw(AssertionError("empty systems must not project application_run_host")),
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_model_instances",
        classmethod(lambda cls, request, model_id, inst_uuids: []),
    )

    result = Application3DQueryService.architecture(_request(), SYSTEM_A)

    assert [node["id"] for node in result["nodes"]] == [SYSTEM_A]
    assert result["nodes"][0]["kind"] == "system"
    assert result["nodes"][0]["health"]["reason"] == "no_application"
    assert result["nodes"][0]["health"]["state"] != "normal"
    assert result["edges"] == []


def test_architecture_no_host_keeps_apps_without_host_nodes(monkeypatch):
    systems = [_system(SYSTEM_A, "apps-no-hosts")]
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: systems[0]),
    )
    _patch_system_host_graph(
        monkeypatch,
        child_apps=[_application(APP_A, "empty-app"), _application(APP_B, "isolated-app")],
        hosts_by_app={APP_A: [], APP_B: []},
        visible_hosts=[],
    )

    result = Application3DQueryService.architecture(_request(), SYSTEM_A)

    assert [node["kind"] for node in result["nodes"]] == ["system", "application", "application"]
    assert [node["id"] for node in result["nodes"]] == [SYSTEM_A, APP_A, APP_B]
    assert {edge["relation"] for edge in result["edges"]} == {"system_contains_application"}
    assert result["nodes"][0]["health"]["reason"] == "no_host"
    assert result["nodes"][0]["health"]["state"] != "normal"


def test_architecture_omits_invisible_apps_and_hosts(monkeypatch):
    systems = [_system(SYSTEM_A, "partial")]
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_application",
        classmethod(lambda cls, request, application_id: systems[0]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_system_applications",
        lambda system_ids: {SYSTEM_A: [APP_A, APP_B]},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_model_instances",
        classmethod(lambda cls, request, model_id, inst_uuids: [_application(APP_A, "visible")]),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.application3d.query_service.project_application_hosts",
        lambda app_ids: {app_id: ["host-visible", "host-hidden"] for app_id in app_ids},
    )
    monkeypatch.setattr(
        Application3DQueryService,
        "_visible_hosts",
        classmethod(lambda cls, request, host_ids: [{"inst_uuid": "host-visible", "inst_name": "可见主机", "monitor_id": "m1"}]),
    )

    result = Application3DQueryService.architecture(_request(), SYSTEM_A)

    ids = {node["id"] for node in result["nodes"]}
    assert ids == {SYSTEM_A, APP_A, "host-visible"}
    assert APP_B not in ids
    assert "host-hidden" not in ids
    assert result["nodes"][0]["health"]["reason"] == "unavailable"
