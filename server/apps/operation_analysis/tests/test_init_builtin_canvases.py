"""init_builtin_canvases 管理命令覆盖测试。

对照 specs/capabilities/legacy-prd-运营分析-运营分析.md：内置画布从 YAML 导入并标记为内置只读对象。
"""

import json
from pathlib import Path

import pytest
import yaml
from django.core.management import call_command

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory, Screen, Topology

BUILTIN_CANVASES_PATH = Path(__file__).resolve().parents[1] / "support-files" / "builtin_canvases.yaml"
NETWORK_TOPOLOGY_SCREEN_PATH = Path(__file__).resolve().parents[1] / "support-files" / "builtin_network_topology_screen.yaml"
SOURCE_API_PATH = Path(__file__).resolve().parents[1] / "support-files" / "source_api.json"


def _load_builtin_alert_screen():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    return next(screen for screen in payload["screens"] if screen.get("name", "").startswith("告警运营大屏"))


def _load_builtin_room3d_screen():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    return next(screen for screen in payload["screens"] if screen["key"] == "screen::3D机房大屏_内置")


def _load_builtin_alert_dashboard():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    return next(dashboard for dashboard in payload["dashboards"] if dashboard["name"] == "统一告警中心仪表盘")


def _count_nested_key(value, target_key):
    if isinstance(value, list):
        return sum(_count_nested_key(item, target_key) for item in value)
    if isinstance(value, dict):
        return (1 if target_key in value else 0) + sum(_count_nested_key(item, target_key) for item in value.values())
    return 0


def test_builtin_yaml_contains_alert_room3d_and_application3d_screens():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))

    assert payload["meta"]["object_counts"]["screens"] == 3
    assert payload["meta"]["object_counts"]["topologies"] == 0
    assert [screen["key"] for screen in payload["screens"]] == [
        "screen::告警运营大屏_内置",
        "screen::3D机房大屏_内置",
        "screen::3D应用大屏_内置",
    ]
    assert [screen["name"] for screen in payload["screens"]] == ["告警运营大屏", "3D机房大屏", "3D应用大屏"]
    assert "基础资源态势大屏_内置" not in BUILTIN_CANVASES_PATH.read_text(encoding="utf-8")
    assert "运营健康拓扑_内置" not in BUILTIN_CANVASES_PATH.read_text(encoding="utf-8")


def test_builtin_application3d_screen_yaml_contains_only_the_self_fetch_scene_widget():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    screen = next(screen for screen in payload["screens"] if screen["key"] == "screen::3D应用大屏_内置")

    assert screen["view_sets"]["viewport"] == {
        "theme": "screen-dark",
        "width": 1920,
        "height": 1080,
        "background": {"key": "tech-grid", "type": "builtIn"},
    }
    assert screen["view_sets"]["decorations"] == {"title": "3D应用", "showClock": False, "showTitle": False}
    assert screen["refs"] == {"datasource_keys": [], "namespace_keys": []}

    assert screen["view_sets"]["items"] == [
        {
            "h": 1080,
            "w": 1920,
            "x": 0,
            "y": 0,
            "id": "builtin-application3d-main",
            "type": "widget",
            "title": "3D应用",
            "zIndex": 1,
            "chartType": "application3D",
            "valueConfig": {
                "chartType": "application3D",
                "sceneWidgetType": "application3D",
                "appearance": {"frame": "bare"},
            },
        }
    ]


def test_builtin_room3d_screen_yaml_uses_dynamic_room_switch():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    screen = _load_builtin_room3d_screen()
    assert screen["view_sets"]["viewport"] == {
        "theme": "screen-dark",
        "width": 1920,
        "height": 1080,
        "background": {"key": "tech-grid", "type": "builtIn"},
    }
    assert screen["view_sets"]["decorations"] == {"title": "3D机房大屏", "showClock": False, "showTitle": False}
    assert len(screen["view_sets"]["items"]) == 1
    widget = screen["view_sets"]["items"][0]
    assert widget["chartType"] == "room3D"
    assert widget["valueConfig"]["appearance"] == {"frame": "bare"}
    assert widget["valueConfig"]["dataSource"] == "CMDB 3D机房布局::cmdb/get_room3d_layout"

    datasource = next(item for item in payload["datasources"] if item["key"] == widget["valueConfig"]["dataSource"])
    room_param = datasource["params"][0]
    assert room_param["name"] == "server_room_id"
    assert room_param["value"] == ""
    assert room_param["inputConfig"] == {
        "control": "select",
        "componentSwitch": True,
        "optionsSource": {
            "type": "dynamic",
            "sourceRef": {"type": "rest_api", "value": "cmdb/get_room_list"},
            "valueField": "inst_uuid",
            "labelField": "inst_name",
        },
    }


@pytest.mark.unit
def test_cmdb_model_instance_top_limit_is_component_configurable():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    datasource_key = "CMDB模型实例TOPN::cmdb/get_cmdb_model_instance_top"

    datasource = next(item for item in payload["datasources"] if item["key"] == datasource_key)
    datasource_limit = next(param for param in datasource["params"] if param["name"] == "limit")

    dashboard = next(item for item in payload["dashboards"] if item["name"] == "CMDB仪表盘")
    widget = next(item for item in dashboard["view_sets"] if item["name"] == "模型实例 TOP 5")
    widget_limit = next(param for param in widget["valueConfig"]["dataSourceParams"] if param["name"] == "limit")

    assert datasource_limit["value"] == 5
    assert datasource_limit["filterType"] == "params"
    assert widget_limit["value"] == 5
    assert widget_limit["filterType"] == "params"


@pytest.mark.unit
def test_builtin_alert_cmdb_datasource_contracts_are_complete():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    source_api = json.loads(SOURCE_API_PATH.read_text(encoding="utf-8"))
    datasources = source_api + payload["datasources"]
    by_api = {item["rest_api"]: item for item in datasources}

    assert "get_alert_trend_data" not in by_api
    assert "alert/get_alert_statistics" not in by_api
    assert by_api["alert/get_alert_trend_data"]["chart_type"] == ["line", "bar"]

    numeric_fields = {
        "alert/get_alert_period_statistics": {
            "new_alert_count",
            "linked_event_count",
            "affected_alert_count",
            "new_incident_count",
            "session_alert_count",
            "session_alert_rate",
            "aggregation_ratio",
        },
        "alert/get_alert_snapshot_statistics": {
            "active_count",
            "unassigned_count",
            "pending_count",
            "processing_count",
            "auto_recovery_count",
            "auto_recovery_rate",
        },
    }
    for rest_api, expected_fields in numeric_fields.items():
        fields = {field["key"]: field for field in by_api[rest_api]["field_schema"]}
        assert set(fields) == expected_fields
        assert {field["value_type"] for field in fields.values()} == {"number"}
        assert all(field["description"] for field in fields.values())

    source_stats = by_api["alert/get_alert_source_statistics"]
    assert {field["key"] for field in source_stats["field_schema"]} == {
        "total_count",
        "enabled_count",
        "enabled_rate",
        "active_count",
    }
    channel_stats = by_api["alert/get_notification_channel_stats"]
    assert {field["key"] for field in channel_stats["field_schema"]} == {"name", "value"}
    quality = by_api["alert/get_alert_data_quality"]
    assert len(quality["field_schema"]) == 12

    collect_stats = by_api["cmdb/get_cmdb_collect_statistics"]
    assert "partial_success_count" in {field["key"] for field in collect_stats["field_schema"]}
    change_trend = by_api["cmdb/get_change_trend"]
    assert {param["name"] for param in change_trend["params"]} == {"time", "model_id"}
    for rest_api in ("alert/get_alert_trend_data", "alert/get_alert_level_trend", "cmdb/get_change_trend"):
        assert all(param.get("name") != "group_by" for param in by_api[rest_api]["params"])
    assert all(
        item.get("desc")
        for item in datasources
        if item.get("rest_api", "").startswith(("alert/", "cmdb/"))
        or item.get("rest_api") in {"get_alert_level_distribution", "get_active_alert_top", "get_instance_group_by", "get_model_inst_statistics"}
    )

    expected_names = {
        "alert/get_alert_period_statistics": "告警与事件汇总",
        "alert/get_alert_snapshot_statistics": "活跃告警状态快照",
        "alert/get_alert_data_quality": "告警与事件字段缺失率",
        "alert/get_alert_source_statistics": "告警源配置与活跃数",
        "alert/get_alert_source_distribution": "告警按来源分布",
        "alert/get_alert_source_event_top": "告警关联事件来源 TOP",
        "alert/get_alert_status_distribution": "活跃告警状态分布",
        "alert/get_alert_today_status_summary": "今日产生关闭与当前处理中",
        "alert/get_notification_statistics": "通知发送汇总",
        "alert/get_notification_channel_stats": "渠道通知成功率",
        "alert/get_alert_trend_data": "告警与关联事件趋势",
        "alert/get_alert_level_trend": "告警等级趋势",
        "cmdb/get_cmdb_statistics": "CMDB 覆盖概览",
        "get_model_inst_statistics": "CMDB 模型实例明细",
        "cmdb/get_cmdb_model_instance_top": "CMDB 模型实例排行",
        "cmdb/get_classification_model_instance_counts": "分类下模型实例数",
        "cmdb/get_region_resource_overview": "地区分类实例数",
        "cmdb/get_cmdb_collect_statistics": "CMDB 采集任务状态",
        "get_instance_group_by": "主机操作系统分布",
        "cmdb/get_room_list": "CMDB 机房列表（选项）",
        "cmdb/get_model_classification_options": "CMDB 模型分类列表（选项）",
        "cmdb/get_region_options": "CMDB 地区列表（选项）",
        "cmdb/get_change_trend": "CMDB 变更趋势",
    }
    for rest_api, expected_name in expected_names.items():
        assert by_api[rest_api]["name"] == expected_name
    source_api_by_rest = {item["rest_api"]: item for item in source_api}
    assert source_api_by_rest["alert/get_alert_trend_data"]["key"] == "告警趋势::alert/get_alert_trend_data"
    assert source_api_by_rest["alert/get_alert_source_distribution"]["key"] == "告警来源分布::alert/get_alert_source_distribution"


@pytest.mark.unit
def test_all_builtin_canvas_datasource_references_resolve_after_merge():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    source_api = json.loads(SOURCE_API_PATH.read_text(encoding="utf-8"))
    available_keys = {item.get("key") or f'{item["name"]}::{item["rest_api"]}' for item in source_api + payload["datasources"]}

    referenced_keys = set()
    configured_keys = set()
    for canvas_type in ("dashboards", "screens"):
        for canvas in payload[canvas_type]:
            referenced_keys.update(canvas.get("refs", {}).get("datasource_keys", []))
            view_sets = canvas.get("view_sets", [])
            views = view_sets if isinstance(view_sets, list) else view_sets.get("items", [])
            configured_keys.update(view["valueConfig"]["dataSource"] for view in views if view.get("valueConfig", {}).get("dataSource"))

    assert referenced_keys <= available_keys
    assert configured_keys <= available_keys


@pytest.mark.unit
def test_builtin_network_topology_screen_refs_monitor_overlay_datasources():
    payload = yaml.safe_load(NETWORK_TOPOLOGY_SCREEN_PATH.read_text(encoding="utf-8"))
    source_api = json.loads(SOURCE_API_PATH.read_text(encoding="utf-8"))
    screens = {item["key"]: item for item in payload["screens"]}
    screen = screens["screen::网络状态拓扑大屏_内置"]
    overlay_keys = {
        "CMDB 实例监控ID映射::cmdb/get_monitor_ids_by_inst_uuids",
        "监控活跃告警::monitor/query_latest_active_alerts",
        "监控接口最新指标::monitor/query_latest_interface_metrics",
    }
    assert set(screen["refs"]["datasource_keys"]) == overlay_keys
    widget = screen["view_sets"]["items"][0]
    assert widget["valueConfig"]["networkStatusTopology"]["instUuids"] == []
    assert widget["valueConfig"]["networkStatusTopology"]["nodeLimit"] == 100
    available_keys = {item.get("key") or f'{item["name"]}::{item["rest_api"]}' for item in source_api}
    assert overlay_keys <= available_keys


def test_builtin_alert_screen_yaml_uses_page_configurable_nodes_only():
    screen = _load_builtin_alert_screen()
    nodes = screen["view_sets"]["items"]
    chart_types = {node.get("valueConfig", {}).get("chartType") for node in nodes}

    assert screen["view_sets"]["viewport"] == {
        "theme": "screen-dark",
        "width": 3840,
        "height": 2160,
        "background": {"key": "tech-grid", "type": "builtIn"},
    }
    assert screen["view_sets"]["decorations"] == {"title": "告警运营大屏", "showClock": True, "showTitle": True}
    assert "edges" not in screen["view_sets"]
    assert len(nodes) == 15
    assert all(node["type"] == "widget" for node in nodes)
    assert all("valueConfig" in node for node in nodes)
    assert _count_nested_key(nodes, "config") == 0
    assert {"single", "bar", "line", "pie", "topN", "table"} <= chart_types

    datasource_refs = set(screen["refs"]["datasource_keys"])
    assert "今日告警状态总览::alert/get_alert_today_status_summary" in datasource_refs
    assert "告警状态分布::alert/get_alert_status_distribution" in datasource_refs
    assert "告警等级趋势::alert/get_alert_level_trend" in datasource_refs
    assert "告警期间统计::alert/get_alert_period_statistics" in datasource_refs
    assert "告警趋势::alert/get_alert_trend_data" in datasource_refs
    assert "按渠道通知成功率::alert/get_notification_channel_stats" in datasource_refs

    node_by_id = {node["id"]: node for node in nodes}
    kpi_ids = [
        "alert-kpi-created",
        "alert-kpi-closed",
        "alert-kpi-processing",
        "alert-active-total",
        "alert-active-pending",
        "f9156f59-ac47-48b9-b071-da3289f769af",
        "2bdee93c-3a75-49a6-93b2-bd0d448967b3",
    ]
    for node_id in kpi_ids:
        node = node_by_id[node_id]
        assert node["type"] == "widget"
        assert node["chartType"] == "single"
        assert node["valueConfig"]["chartType"] == "single"
        assert node.get("title", "")

    assert node_by_id["alert-source-event-top"]["valueConfig"]["topNLabelField"] == "source_name"
    assert node_by_id["alert-source-event-top"]["valueConfig"]["topNValueField"] == "count"
    filter_bound_node_ids = {
        "alert-level-trend",
        "alert-access-trend",
        "alert-source-event-top",
        "081f2a79-debe-4825-9d4d-1aeb02d9702e",
        "f9156f59-ac47-48b9-b071-da3289f769af",
        "2bdee93c-3a75-49a6-93b2-bd0d448967b3",
    }
    for node_id in filter_bound_node_ids:
        value_config = node_by_id[node_id]["valueConfig"]
        time_param = next(param for param in value_config["dataSourceParams"] if param["name"] == "time")
        assert time_param["value"] == 10080
        assert time_param["filterType"] == "filter"
        assert value_config["filterBindings"] == {"time__timeRange": True}
    assert all("conversionFactor" not in node["valueConfig"] for node in nodes)


@pytest.mark.unit
def test_builtin_alert_dashboard_separates_period_and_snapshot_bindings():
    widgets = _load_builtin_alert_dashboard()["view_sets"]
    widget_by_name = {widget["name"]: widget for widget in widgets}

    period_names = {
        "告警关联事件数",
        "新增告警数",
        "新增事故数",
        "事件聚合倍率",
        "会话告警占比",
        "告警关联事件来源 TOP 5",
    }
    snapshot_names = {
        "活跃告警数",
        "自动恢复告警数",
        "自动恢复占比",
        "告警源总数",
        "已启用告警源数",
        "告警源启用率",
    }
    for name in period_names:
        assert widget_by_name[name]["valueConfig"]["filterBindings"]["time__timeRange"] is True
    for name in snapshot_names:
        assert "time__timeRange" not in widget_by_name[name]["valueConfig"].get("filterBindings", {})

    notification_widgets = [widget for widget in widgets if "通知" in widget["name"]]
    assert notification_widgets
    assert all(widget["valueConfig"]["filterBindings"]["time__timeRange"] is True for widget in notification_widgets)
    assert all("conversionFactor" not in widget["valueConfig"] for widget in widgets)
    corrected_percentage_fields = {
        "alert_quality.missing_resource_id_rate",
        "event_quality.missing_item_rate",
    }
    percentage_widgets = [widget for widget in widgets if corrected_percentage_fields.intersection(widget["valueConfig"].get("selectedFields", []))]
    assert len(percentage_widgets) == len(corrected_percentage_fields)
    assert all(
        0 <= float(threshold["value"]) <= 100 for widget in percentage_widgets for threshold in widget["valueConfig"].get("thresholdColors", [])
    )


def _ensure_default_namespace():
    from apps.operation_analysis.models.datasource_models import NameSpace

    namespace, _ = NameSpace.objects.get_or_create(
        name="默认命名空间",
        defaults={
            "domain": "127.0.0.1:4222",
            "namespace": "bklite",
            "account": "admin",
            "enable_tls": False,
            "created_by": "system",
            "updated_by": "system",
        },
    )
    namespace.set_password("test-password")
    namespace.save()
    return namespace


def _configure_minimal_builtin_dashboard(monkeypatch, tmp_path, *, name="Issue 4743 内置仪表盘", desc="初始内容"):
    from apps.operation_analysis.management.commands import init_builtin_canvases as command_module

    yaml_path = tmp_path / "builtin-canvases.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "meta": {
                    "object_counts": {
                        "dashboards": 1,
                        "topologies": 0,
                        "architectures": 0,
                        "screens": 0,
                        "reports": 0,
                        "datasources": 0,
                        "namespaces": 0,
                    }
                },
                "dashboards": [
                    {
                        "key": "dashboard::issue-4743",
                        "name": name,
                        "desc": desc,
                        "view_sets": [],
                    }
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(command_module, "_get_builtin_canvas_file_paths", lambda: [yaml_path])
    monkeypatch.setattr(command_module, "_load_source_api_document", lambda: {"datasources": []})
    monkeypatch.setattr(command_module, "_ensure_builtin_tags", lambda: None)
    return yaml_path


def _configure_minimal_builtin_datasource(monkeypatch, tmp_path):
    from apps.operation_analysis.management.commands import init_builtin_canvases as command_module

    yaml_path = tmp_path / "builtin-datasource.yaml"
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "meta": {
                    "object_counts": {
                        "dashboards": 0,
                        "topologies": 0,
                        "architectures": 0,
                        "screens": 0,
                        "reports": 0,
                        "datasources": 1,
                        "namespaces": 0,
                    }
                },
                "datasources": [
                    {
                        "key": "datasource::issue-4743",
                        "name": "Issue 4743 内置数据源",
                        "rest_api": "/issue-4743",
                        "source_type": "rest_api",
                        "desc": "初始内容",
                    }
                ],
                "dashboards": [],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(command_module, "_get_builtin_canvas_file_paths", lambda: [yaml_path])
    monkeypatch.setattr(command_module, "_load_source_api_document", lambda: {"datasources": []})
    monkeypatch.setattr(command_module, "_ensure_builtin_tags", lambda: None)
    return yaml_path


@pytest.mark.django_db
def test_init_builtin_canvases_creates_builtin_directory():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")

    # 命令应创建内置目录
    assert Directory.objects.filter(build_in_key="__builtin__").exists()


@pytest.mark.django_db
def test_init_builtin_canvases_rerun_is_idempotent():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")
    call_command("init_builtin_canvases")

    # 内置目录唯一
    assert Directory.objects.filter(build_in_key="__builtin__").count() == 1


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_rerun_preserves_identity_references_and_visibility(monkeypatch, tmp_path):
    from apps.operation_analysis.models.share_models import DashboardShareLink
    from apps.operation_analysis.models.subscription_models import DashboardReportSubscription
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    extra = Group.objects.create(name="Issue 4743 Extra")
    yaml_path = _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    call_command("init_builtin_canvases")

    dashboard = Dashboard.objects.get(build_in_key="dashboard::issue-4743")
    directory = Directory.objects.get(build_in_key="__builtin__")
    original_id = dashboard.pk
    expected_groups = [default.pk, extra.pk]
    Dashboard.objects.filter(pk=dashboard.pk).update(groups=expected_groups)
    Directory.objects.filter(pk=directory.pk).update(groups=expected_groups)
    share = DashboardShareLink.objects.create(
        dashboard=dashboard,
        dashboard_instance_id=dashboard.pk,
        tenant_domain=dashboard.domain,
        space_id=default.pk,
        sharer_username="tester",
        sharer_domain=dashboard.domain,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=dashboard,
        creator="tester",
        team_id=default.pk,
        name="Issue 4743 订阅",
        recipient_email="tester@example.com",
    )
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "dashboards": [
                    {
                        "key": "dashboard::issue-4743",
                        "name": "Issue 4743 内置仪表盘（新版）",
                        "desc": "新版内容",
                        "view_sets": [],
                    }
                ]
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    call_command("init_builtin_canvases")

    dashboard = Dashboard.objects.get(build_in_key="dashboard::issue-4743")
    directory.refresh_from_db()
    share.refresh_from_db()
    subscription.refresh_from_db()
    assert dashboard.pk == original_id
    assert dashboard.name == "Issue 4743 内置仪表盘（新版）"
    assert dashboard.desc == "新版内容"
    assert set(dashboard.groups) == set(expected_groups)
    assert set(directory.groups) == set(expected_groups)
    assert share.status == DashboardShareLink.Status.ACTIVE
    assert share.dashboard_id == original_id
    assert share.dashboard_instance_id == original_id
    assert subscription.status == DashboardReportSubscription.Status.ACTIVE
    assert subscription.dashboard_id == original_id
    assert subscription.resource_id == original_id


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_rerun_preserves_datasource_identity_and_visibility(monkeypatch, tmp_path):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    extra = Group.objects.create(name="Issue 4743 Datasource Extra")
    yaml_path = _configure_minimal_builtin_datasource(monkeypatch, tmp_path)
    call_command("init_builtin_canvases")

    datasource = DataSourceAPIModel.objects.get(build_in_key="datasource::issue-4743")
    original_id = datasource.pk
    expected_groups = [default.pk, extra.pk]
    DataSourceAPIModel.objects.filter(pk=datasource.pk).update(groups=expected_groups)
    yaml_path.write_text(
        yaml.safe_dump(
            {
                "datasources": [
                    {
                        "key": "datasource::issue-4743",
                        "name": "Issue 4743 内置数据源（新版）",
                        "rest_api": "/issue-4743-v2",
                        "source_type": "rest_api",
                        "desc": "新版内容",
                    }
                ],
                "dashboards": [],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    call_command("init_builtin_canvases")

    datasource = DataSourceAPIModel.objects.get(build_in_key="datasource::issue-4743")
    assert datasource.pk == original_id
    assert datasource.name == "Issue 4743 内置数据源（新版）"
    assert datasource.rest_api == "/issue-4743-v2"
    assert datasource.desc == "新版内容"
    assert set(datasource.groups) == set(expected_groups)


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_preserves_user_canvas_on_name_conflict(monkeypatch, tmp_path):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    user_dashboard = Dashboard.objects.create(
        name="Issue 4743 内置仪表盘",
        desc="用户内容",
        groups=[default.pk],
        created_by="tester",
        updated_by="tester",
    )
    _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)

    call_command("init_builtin_canvases")

    user_dashboard.refresh_from_db()
    assert user_dashboard.desc == "用户内容"
    assert user_dashboard.is_build_in is False
    assert user_dashboard.build_in_key is None
    assert not Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_reclaims_renamed_builtin_key_by_name(monkeypatch, tmp_path):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    legacy = Dashboard.objects.create(
        name="Issue 4743 内置仪表盘",
        desc="旧版本内容",
        groups=[default.pk],
        is_build_in=True,
        build_in_key="dashboard::issue-4743-old-key",
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    legacy.refresh_from_db()
    assert legacy.build_in_key == "dashboard::issue-4743"
    assert legacy.desc == "初始内容"
    assert Dashboard.objects.filter(name="Issue 4743 内置仪表盘").count() == 1


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_does_not_rebind_another_active_key_with_same_name(monkeypatch, tmp_path):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    yaml_path = _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    payload["dashboards"].insert(
        0,
        {
            "key": "dashboard::already-active",
            "name": "Issue 4743 内置仪表盘",
            "desc": "活跃定义内容",
            "view_sets": [],
        },
    )
    payload["meta"]["object_counts"]["dashboards"] = 2
    yaml_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    existing = Dashboard.objects.create(
        name="Issue 4743 内置仪表盘",
        desc="旧内容",
        groups=[default.pk],
        is_build_in=True,
        build_in_key="dashboard::already-active",
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    existing.refresh_from_db()
    assert existing.build_in_key == "dashboard::already-active"
    assert existing.desc == "活跃定义内容"
    assert not Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_removes_retired_builtin_topology_only():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    retired = Topology.objects.create(
        name="运营健康拓扑_内置",
        is_build_in=True,
        build_in_key="topology::运营健康拓扑_内置",
        created_by="system",
        updated_by="system",
    )
    custom = Topology.objects.create(
        name="用户运营拓扑",
        created_by="user",
        updated_by="user",
    )
    unknown_legacy_builtin = Topology.objects.create(
        name="缺少稳定键的历史内置拓扑",
        is_build_in=True,
        build_in_key=None,
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    assert not Topology.objects.filter(pk=retired.pk).exists()
    assert not Topology.objects.filter(build_in_key="topology::运营健康拓扑_内置").exists()
    assert Topology.objects.filter(pk=custom.pk, is_build_in=False).exists()
    assert Topology.objects.filter(pk=unknown_legacy_builtin.pk, is_build_in=True).exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_retires_dashboard_references_explicitly(monkeypatch, tmp_path):
    from apps.operation_analysis.models.share_models import DashboardShareLink
    from apps.operation_analysis.models.subscription_models import DashboardReportSubscription
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    retired = Dashboard.objects.create(
        name="Issue 4743 已退役仪表盘",
        is_build_in=True,
        build_in_key="dashboard::issue-4743-retired",
        groups=[default.pk],
        created_by="system",
        updated_by="system",
    )
    share = DashboardShareLink.objects.create(
        dashboard=retired,
        dashboard_instance_id=retired.pk,
        tenant_domain=retired.domain,
        space_id=default.pk,
        sharer_username="tester",
        sharer_domain=retired.domain,
    )
    subscription = DashboardReportSubscription.objects.create(
        dashboard=retired,
        creator="tester",
        team_id=default.pk,
        name="Issue 4743 退役订阅",
        recipient_email="tester@example.com",
    )

    call_command("init_builtin_canvases")

    share.refresh_from_db()
    subscription.refresh_from_db()
    assert not Dashboard.objects.filter(pk=retired.pk).exists()
    assert share.status == DashboardShareLink.Status.DASHBOARD_INVALID
    assert share.dashboard_id is None
    assert subscription.status == DashboardReportSubscription.Status.TERMINATED
    assert subscription.termination_reason == "dashboard_deleted"
    assert subscription.terminated_by == "system"
    assert subscription.dashboard_id is None


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_skips_retirement_when_definition_file_is_missing(monkeypatch, tmp_path):
    from apps.operation_analysis.management.commands import init_builtin_canvases as command_module
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    yaml_path = _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    missing_path = tmp_path / "temporarily-missing.yaml"
    monkeypatch.setattr(command_module, "_get_builtin_canvas_file_paths", lambda: [yaml_path, missing_path])
    retired_candidate = Dashboard.objects.create(
        name="Issue 4743 缺失文件中的仪表盘",
        is_build_in=True,
        build_in_key="dashboard::from-missing-file",
        groups=[default.pk],
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()
    assert Dashboard.objects.filter(pk=retired_candidate.pk).exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_skips_retirement_when_declared_counts_do_not_match(monkeypatch, tmp_path):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    yaml_path = _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    payload["meta"]["object_counts"]["dashboards"] = 2
    yaml_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    retired_candidate = Dashboard.objects.create(
        name="Issue 4743 截断快照中的仪表盘",
        is_build_in=True,
        build_in_key="dashboard::from-truncated-snapshot",
        groups=[default.pk],
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()
    assert Dashboard.objects.filter(pk=retired_candidate.pk).exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_invalid_section_shape_is_fail_open(monkeypatch, tmp_path):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    yaml_path = _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    payload["dashboards"] = 1
    yaml_path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    existing = Dashboard.objects.create(
        name="Issue 4743 结构错误时保留",
        is_build_in=True,
        build_in_key="dashboard::preserved-on-shape-error",
        groups=[default.pk],
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(pk=existing.pk).exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_retirement_dry_run_has_no_side_effects(monkeypatch, tmp_path, capsys):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    retired_candidate = Dashboard.objects.create(
        name="Issue 4743 退役预检仪表盘",
        is_build_in=True,
        build_in_key="dashboard::dry-run-candidate",
        groups=[default.pk],
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases", dry_run=True)

    output = capsys.readouterr().out
    assert "预检待退役内置对象" in output
    assert "dashboard::dry-run-candidate" in output
    assert Dashboard.objects.filter(pk=retired_candidate.pk).exists()
    assert not Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_retirement_limit_rolls_back_before_sync(monkeypatch, tmp_path, settings):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    settings.OPERATION_ANALYSIS_BUILTIN_RETIRE_LIMIT = 1
    candidates = [
        Dashboard.objects.create(
            name=f"Issue 4743 超限退役仪表盘 {index}",
            is_build_in=True,
            build_in_key=f"dashboard::over-limit-{index}",
            groups=[default.pk],
            created_by="system",
            updated_by="system",
        )
        for index in range(2)
    ]

    call_command("init_builtin_canvases")

    assert all(Dashboard.objects.filter(pk=item.pk).exists() for item in candidates)
    assert not Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_malformed_yaml_is_fail_open_and_retryable(monkeypatch, tmp_path, capsys):
    from apps.system_mgmt.models.user import Group

    default, _ = Group.objects.get_or_create(name="Default")
    yaml_path = _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    existing = Dashboard.objects.create(
        name="Issue 4743 解析失败时保留",
        is_build_in=True,
        build_in_key="dashboard::preserved-on-parse-error",
        groups=[default.pk],
        created_by="system",
        updated_by="system",
    )
    yaml_path.write_text("dashboards: [", encoding="utf-8")

    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(pk=existing.pk).exists()
    output = capsys.readouterr().out
    assert "ParserError" in output
    assert "expected" in output

    _configure_minimal_builtin_dashboard(monkeypatch, tmp_path)
    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(build_in_key="dashboard::issue-4743").exists()


@pytest.mark.django_db
def test_init_builtin_canvases_creates_builtin_alert_screen():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")

    assert not Screen.objects.filter(name__startswith="基础资源态势大屏", is_build_in=True).exists()
    screen = Screen.objects.get(name="告警运营大屏", is_build_in=True)
    nodes = screen.view_sets["items"]
    datasource_names = [node.get("valueConfig", {}).get("dataSource") for node in nodes if node.get("valueConfig", {}).get("dataSource")]
    datasource_ids = set(datasource_names)

    assert screen.view_sets["viewport"]["width"] == 3840
    assert screen.view_sets["viewport"]["height"] == 2160
    assert screen.view_sets["viewport"]["theme"] == "screen-dark"
    assert screen.view_sets["decorations"] == {"title": "告警运营大屏", "showClock": True, "showTitle": True}
    assert "edges" not in screen.view_sets
    assert len(nodes) == 15
    assert all(node.get("type") == "widget" for node in nodes)
    assert _count_nested_key(nodes, "config") == 0
    assert DataSourceAPIModel.objects.get(name="今日产生关闭与当前处理中").id in datasource_ids
    assert DataSourceAPIModel.objects.get(name="活跃告警状态分布").id in datasource_ids
    assert DataSourceAPIModel.objects.get(name="告警等级趋势").id in datasource_ids

    node_by_id = {node["id"]: node for node in nodes}
    assert screen.view_sets["filters"] == [
        {
            "id": "time__timeRange",
            "key": "time",
            "name": "时间范围",
            "type": "timeRange",
            "order": 0,
            "enabled": True,
            "defaultValue": {
                "start": "2026-07-28T00:00:00.000Z",
                "end": "2026-08-04T00:00:00.000Z",
                "selectValue": 10080,
            },
        }
    ]
    period_node_ids = {
        "alert-level-trend",
        "alert-access-trend",
        "alert-source-event-top",
        "081f2a79-debe-4825-9d4d-1aeb02d9702e",
        "f9156f59-ac47-48b9-b071-da3289f769af",
        "2bdee93c-3a75-49a6-93b2-bd0d448967b3",
    }
    for node_id in period_node_ids:
        value_config = node_by_id[node_id]["valueConfig"]
        assert value_config["filterBindings"] == {"time__timeRange": True}
        time_param = next(param for param in value_config["dataSourceParams"] if param["name"] == "time")
        assert time_param["filterType"] == "filter"

    assert node_by_id["f9156f59-ac47-48b9-b071-da3289f769af"]["valueConfig"]["selectedFields"] == ["linked_event_count"]
    assert node_by_id["2bdee93c-3a75-49a6-93b2-bd0d448967b3"]["valueConfig"]["selectedFields"] == ["new_incident_count"]

    source_top_node = node_by_id["alert-source-event-top"]
    assert source_top_node["valueConfig"]["topNLabelField"] == "source_name"
    assert source_top_node["valueConfig"]["topNValueField"] == "count"

    source_top_datasource = DataSourceAPIModel.objects.get(name="告警关联事件来源 TOP")
    source_top_fields = {field["key"]: field["title"] for field in source_top_datasource.field_schema}
    assert source_top_fields["source_name"] == "告警源"
    assert source_top_fields["count"] == "告警关联事件数"

    room3d_screen = Screen.objects.get(name="3D机房大屏", is_build_in=True)
    assert room3d_screen.build_in_key == "screen::3D机房大屏_内置"
    assert room3d_screen.directory.build_in_key == "__builtin__"
    assert room3d_screen.view_sets["decorations"] == {"title": "3D机房大屏", "showClock": False, "showTitle": False}
    room3d_widget = room3d_screen.view_sets["items"][0]
    room3d_datasource = DataSourceAPIModel.objects.get(name="CMDB 3D机房布局")
    assert room3d_widget["chartType"] == "room3D"
    assert room3d_widget["valueConfig"]["dataSource"] == room3d_datasource.id
    assert room3d_widget["valueConfig"]["appearance"] == {"frame": "bare"}
    room_param = room3d_datasource.params[0]
    assert room_param["inputConfig"]["componentSwitch"] is True

    application3d_screen = Screen.objects.get(name="3D应用大屏", is_build_in=True)
    assert application3d_screen.build_in_key == "screen::3D应用大屏_内置"
    assert application3d_screen.directory.build_in_key == "__builtin__"
    assert application3d_screen.view_sets["decorations"] == {"title": "3D应用", "showClock": False, "showTitle": False}
    assert application3d_screen.view_sets["items"] == [
        {
            "h": 1080,
            "w": 1920,
            "x": 0,
            "y": 0,
            "id": "builtin-application3d-main",
            "type": "widget",
            "title": "3D应用",
            "zIndex": 1,
            "chartType": "application3D",
            "valueConfig": {
                "chartType": "application3D",
                "sceneWidgetType": "application3D",
                "appearance": {"frame": "bare"},
            },
        }
    ]

    alert_dashboard = Dashboard.objects.get(name="统一告警中心仪表盘", is_build_in=True)
    dashboard_widget_by_id = {widget["id"]: widget for widget in alert_dashboard.view_sets}
    dashboard_source_top_widget = dashboard_widget_by_id["ad522899-2fc5-4b7a-875e-19004c33a425"]
    assert dashboard_source_top_widget["valueConfig"]["topNLabelField"] == "source_name"
    assert dashboard_source_top_widget["valueConfig"]["topNValueField"] == "count"
    assert dashboard_source_top_widget["valueConfig"]["filterBindings"] == {"time__timeRange": True}
    dashboard_source_top_time = next(param for param in dashboard_source_top_widget["valueConfig"]["dataSourceParams"] if param["name"] == "time")
    assert dashboard_source_top_time["filterType"] == "filter"


@pytest.mark.django_db
def test_init_builtin_canvases_marks_existing_directory_builtin():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    # 预先存在同名根目录（非内置）
    existing = Directory.objects.create(name="内置目录", parent=None, groups=[], created_by="u")
    call_command("init_builtin_canvases")

    existing.refresh_from_db()
    assert existing.is_build_in is True
    assert existing.build_in_key == "__builtin__"


@pytest.mark.django_db
def test_init_builtin_canvases_merges_extra_yaml_files(tmp_path, settings, monkeypatch):
    from apps.operation_analysis.management.commands import init_builtin_canvases
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    base_yaml = tmp_path / "builtin_canvases.yaml"
    enterprise_yaml = tmp_path / "enterprise_builtin_canvases.yaml"
    missing_yaml = tmp_path / "missing.yaml"

    base_yaml.write_text(
        """
meta:
  schema_version: 1.1.0
dashboards:
- key: dashboard::社区内置仪表盘
  name: 社区内置仪表盘
  view_sets: []
  filters: []
datasources: []
namespaces:
- key: 默认命名空间
  name: 默认命名空间
  domain: 127.0.0.1:4222
  namespace: bklite
  account: admin
  password: test-password
  enable_tls: false
topologies: []
architectures: []
""",
        encoding="utf-8",
    )
    enterprise_yaml.write_text(
        """
meta:
  schema_version: 1.1.0
dashboards:
- key: dashboard::企业内置仪表盘
  name: 企业内置仪表盘
  view_sets: []
  filters: []
datasources: []
namespaces:
- key: 默认命名空间
  name: 默认命名空间
  domain: 127.0.0.1:4222
  namespace: bklite
  account: admin
  password: test-password
  enable_tls: false
topologies: []
architectures: []
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(init_builtin_canvases, "YAML_FILE_PATH", str(base_yaml))
    settings.OPERATION_ANALYSIS_BUILTIN_CANVAS_FILES = [str(enterprise_yaml), str(missing_yaml)]

    call_command("init_builtin_canvases")

    assert Dashboard.objects.filter(name="社区内置仪表盘", is_build_in=True).exists()
    assert Dashboard.objects.filter(name="企业内置仪表盘", is_build_in=True).exists()


@pytest.mark.unit
def test_merge_builtin_datasource_definitions_rejects_drift():
    from apps.operation_analysis.management.commands.init_builtin_canvases import _merge_yaml_documents

    base = {"datasources": [{"key": "source-key", "name": "source", "rest_api": "alert/query", "params": []}]}
    drifted = {
        "datasources": [
            {
                "key": "source-key",
                "name": "source",
                "rest_api": "alert/query",
                "params": [{"name": "time", "type": "timeRange", "filterType": "filter"}],
            }
        ]
    }

    with pytest.raises(ValueError, match="source-key"):
        _merge_yaml_documents([base, drifted])


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_overwrites_and_prunes_only_builtin_datasources():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    legacy = DataSourceAPIModel.objects.create(
        name="告警状态分布",
        rest_api="alert/get_alert_status_distribution",
        params=[{"name": "legacy"}],
        created_by="system",
        updated_by="system",
    )
    stale = DataSourceAPIModel.objects.create(
        name="removed builtin",
        rest_api="removed/query",
        is_build_in=True,
        build_in_key="removed::removed/query",
        created_by="system",
        updated_by="system",
    )
    preserved_raw_queries = [
        DataSourceAPIModel.objects.create(
            name=name,
            rest_api=rest_api,
            source_type="nats",
            is_build_in=True,
            build_in_key=f"{name}::{rest_api}",
            created_by="system",
            updated_by="system",
        )
        for name, rest_api in (
            ("查询时间范围内的指标数据", "monitor/mm_query_range"),
            ("查询单个指标数据", "monitor/mm_query"),
        )
    ]
    unknown_legacy_builtin = DataSourceAPIModel.objects.create(
        name="unknown legacy builtin",
        rest_api="unknown/legacy/query",
        is_build_in=True,
        build_in_key=None,
        created_by="system",
        updated_by="system",
    )
    custom = DataSourceAPIModel.objects.create(
        name="custom",
        rest_api="custom/query",
        created_by="user",
        updated_by="user",
    )

    call_command("init_builtin_canvases")

    legacy.refresh_from_db()
    assert legacy.is_build_in is True
    assert legacy.build_in_key == "告警状态分布::alert/get_alert_status_distribution"
    assert legacy.params != [{"name": "legacy"}]
    assert not DataSourceAPIModel.objects.filter(pk=stale.pk).exists()
    assert all(DataSourceAPIModel.objects.filter(pk=item.pk).exists() for item in preserved_raw_queries)
    assert DataSourceAPIModel.objects.filter(pk=unknown_legacy_builtin.pk, is_build_in=True).exists()
    assert DataSourceAPIModel.objects.filter(pk=custom.pk, is_build_in=False).exists()


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_reclaims_exact_legacy_identity_regardless_of_creator():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    legacy = DataSourceAPIModel.objects.create(
        name="CMDB 变更趋势",
        rest_api="cmdb/get_change_trend",
        desc="曾由管理员编辑的旧内置数据源",
        created_by="admin",
        updated_by="admin",
    )

    call_command("init_builtin_canvases")

    legacy.refresh_from_db()
    assert legacy.is_build_in is True
    assert legacy.build_in_key == "CMDB 变更趋势::cmdb/get_change_trend"
    assert legacy.updated_by == "system"
    assert legacy.desc != "曾由管理员编辑的旧内置数据源"


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_reclaims_renamed_source_via_stable_key_legacy_name():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    legacy = DataSourceAPIModel.objects.create(
        name="告警趋势",
        rest_api="alert/get_alert_trend_data",
        params=[{"name": "legacy"}],
        created_by="system",
        updated_by="system",
    )

    call_command("init_builtin_canvases")

    legacy.refresh_from_db()
    assert legacy.is_build_in is True
    assert legacy.name == "告警与关联事件趋势"
    assert legacy.build_in_key == "告警趋势::alert/get_alert_trend_data"
    assert legacy.params != [{"name": "legacy"}]


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_does_not_claim_custom_source_with_same_rest_api_only():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    custom = DataSourceAPIModel.objects.create(
        name="我的告警状态统计",
        rest_api="alert/get_alert_status_distribution",
        desc="用户自定义同接口数据源",
        created_by="user",
        updated_by="user",
    )

    call_command("init_builtin_canvases")

    custom.refresh_from_db()
    assert custom.is_build_in is False
    assert custom.build_in_key in (None, "")
    assert custom.name == "我的告警状态统计"
    assert custom.desc == "用户自定义同接口数据源"
    builtin = DataSourceAPIModel.objects.get(build_in_key="告警状态分布::alert/get_alert_status_distribution")
    assert builtin.pk != custom.pk
    assert builtin.name == "活跃告警状态分布"


@pytest.mark.unit
def test_legacy_name_from_stable_key_parses_history_name():
    from apps.operation_analysis.common.builtin_datasource_identity import legacy_name_from_stable_key

    assert legacy_name_from_stable_key("告警趋势::alert/get_alert_trend_data", "alert/get_alert_trend_data") == "告警趋势"
    assert legacy_name_from_stable_key("告警与关联事件趋势::alert/get_alert_trend_data", "alert/get_alert_trend_data") == "告警与关联事件趋势"
    assert legacy_name_from_stable_key("unrelated", "alert/get_alert_trend_data") is None
    assert legacy_name_from_stable_key("::alert/get_alert_trend_data", "alert/get_alert_trend_data") is None


@pytest.mark.django_db
@pytest.mark.integration
def test_init_builtin_canvases_rolls_back_canvas_and_datasource_sync_on_failure(monkeypatch):
    from apps.operation_analysis.services.import_export.import_service import ImportService
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")
    screen = Screen.objects.get(build_in_key="screen::告警运营大屏_内置")
    datasource = DataSourceAPIModel.objects.get(build_in_key="告警状态分布::alert/get_alert_status_distribution")
    screen_id = screen.pk
    original_params = datasource.params

    monkeypatch.setattr(ImportService, "execute", lambda self: (_ for _ in ()).throw(RuntimeError("forced failure")))

    call_command("init_builtin_canvases")

    assert Screen.objects.filter(pk=screen_id, build_in_key="screen::告警运营大屏_内置").exists()
    datasource.refresh_from_db()
    assert datasource.params == original_params
