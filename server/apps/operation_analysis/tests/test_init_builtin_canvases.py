"""init_builtin_canvases 管理命令覆盖测试。

对照 spec/prd/运营分析：内置画布从 YAML 导入并标记为内置只读对象。
"""

from pathlib import Path

import pytest
import yaml
from django.core.management import call_command

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory, Screen

BUILTIN_CANVASES_PATH = Path(__file__).resolve().parents[1] / "support-files" / "builtin_canvases.yaml"


def _load_builtin_resource_screen():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    return next(screen for screen in payload["screens"] if screen.get("name", "").startswith("基础资源态势大屏"))


def _load_builtin_alert_screen():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    return next(screen for screen in payload["screens"] if screen.get("name", "").startswith("告警运营大屏"))


def test_builtin_resource_screen_yaml_uses_clean_real_data_layout():
    screen = _load_builtin_resource_screen()
    nodes = screen["view_sets"]["items"]
    chart_nodes = [node for node in nodes if node.get("type") in {"chart", "single-value"}]
    node_by_id = {node["id"]: node for node in nodes}

    assert node_by_id["screen-title"]["type"] == "text"
    assert node_by_id["screen-title"]["presentationRole"] == "screen-title"
    assert node_by_id["screen-clock"]["type"] == "text"
    assert node_by_id["screen-clock"]["presentationRole"] == "screen-clock"
    assert node_by_id["screen-title-frame"]["type"] == "basic-shape"
    assert node_by_id["screen-title-left-line"]["type"] == "basic-shape"
    assert node_by_id["screen-title-right-line"]["type"] == "basic-shape"
    assert screen["view_sets"]["decorations"]["chrome"] == {
        "title": "基础资源态势大屏",
        "showTitle": True,
        "showClock": True,
    }
    assert "edges" not in screen["view_sets"]
    assert not any(node.get("name") == "活跃告警详情" for node in nodes)
    assert all(node.get("valueConfig", {}).get("chartType") not in {"list", "presentation-list"} for node in chart_nodes)
    assert all(
        "presentationVariant" not in node.get("valueConfig", {}) and "presentationAdapter" not in node.get("valueConfig", {}) for node in chart_nodes
    )

    assert all("presentationRole" not in node for node in chart_nodes)

    kpi_nodes = [node for node in nodes if node["id"].startswith("kpi-")]
    kpi_x_positions = sorted(node["position"]["x"] for node in kpi_nodes)
    assert len(kpi_x_positions) == 8
    assert kpi_x_positions[0] >= 120
    assert kpi_x_positions[-1] <= 1580
    assert max(right - left for left, right in zip(kpi_x_positions, kpi_x_positions[1:])) <= 220

    assert node_by_id["panel-alert-trend"]["styleConfig"]["height"] <= 200
    assert node_by_id["panel-alert-summary"]["styleConfig"]["height"] <= 150
    assert node_by_id["panel-monitor-overview"]["styleConfig"]["height"] <= 150

    resource_nodes = [node for node in nodes if node["id"].startswith("resource-")]
    assert len(resource_nodes) == 12
    assert all(node["type"] == "icon" for node in resource_nodes)
    assert all("presentationRole" not in node for node in resource_nodes)
    assert all({"x", "y"} <= set(node["position"]) for node in resource_nodes)

    trend_params = {item["name"]: item for item in node_by_id["panel-alert-trend"]["valueConfig"]["dataSourceParams"]}
    assert trend_params["time"]["filterType"] == "fixed"
    assert trend_params["time"]["value"] == 10080


def test_builtin_alert_screen_yaml_uses_page_configurable_nodes_only():
    screen = _load_builtin_alert_screen()
    nodes = screen["view_sets"]["items"]
    ordinary_nodes = [
        node for node in nodes if node.get("type") in {"chart", "single-value", "icon", "basic-shape"} and not node["id"].startswith("screen-")
    ]
    chart_nodes = [node for node in nodes if node.get("type") == "chart"]
    data_nodes = [node for node in nodes if node.get("type") in {"chart", "single-value"}]
    chart_types = {node.get("valueConfig", {}).get("chartType") for node in data_nodes}

    assert screen["view_sets"]["decorations"]["templateKey"] == "custom-screen"
    assert screen["view_sets"]["decorations"]["chrome"] == {
        "title": "告警运营大屏",
        "showTitle": True,
        "showClock": True,
    }
    assert "edges" not in screen["view_sets"]
    assert all("presentationRole" not in node for node in ordinary_nodes)
    assert {"single", "bar", "line", "pie", "topN", "table"} <= chart_types
    assert not any(node.get("valueConfig", {}).get("chartType") in {"list", "presentation-list"} for node in chart_nodes)

    datasource_refs = set(screen["refs"]["datasource_keys"])
    assert "今日告警状态总览::alert/get_alert_today_status_summary" in datasource_refs
    assert "告警状态分布::alert/get_alert_status_distribution" in datasource_refs
    assert "近7日告警等级趋势::alert/get_alert_level_trend" in datasource_refs

    node_by_id = {node["id"]: node for node in nodes}
    kpi_ids = [
        "alert-today-created",
        "alert-today-closed",
        "alert-today-processing",
        "alert-active-total",
        "alert-active-pending",
        "alert-active-processing",
        "alert-event-total",
    ]
    for node_id in kpi_ids:
        node = node_by_id[node_id]
        assert node["type"] == "single-value"
        assert node["valueConfig"]["chartType"] == "single"
        assert node.get("name", "")
        assert "presentationRole" not in node
        assert node.get("styleConfig", {}).get("borderColor")

    frame_nodes = [node for node in nodes if node["id"].startswith("alert-frame-")]
    assert len(frame_nodes) == 9
    assert all(node["type"] == "basic-shape" for node in frame_nodes)
    assert all(node["zIndex"] == 1 for node in frame_nodes)
    assert all(node.get("styleConfig", {}).get("frameVariant") == "tech" for node in frame_nodes)


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
def test_init_builtin_canvases_creates_builtin_presentation_screen():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")

    screen = Screen.objects.get(name__startswith="基础资源态势大屏", is_build_in=True)

    assert screen.view_sets["decorations"]["templateKey"] == "custom-screen"
    assert screen.view_sets["decorations"]["chrome"] == {
        "title": "基础资源态势大屏",
        "showTitle": True,
        "showClock": True,
    }
    assert screen.view_sets["viewport"]["width"] == 1920
    assert "edges" not in screen.view_sets
    node_by_id = {node["id"]: node for node in screen.view_sets["items"]}
    assert node_by_id["screen-title"]["type"] == "text"
    assert node_by_id["screen-title"]["presentationRole"] == "screen-title"
    assert node_by_id["screen-title"]["name"] == "基础资源态势大屏"
    assert node_by_id["screen-clock"]["type"] == "text"
    assert node_by_id["screen-clock"]["presentationRole"] == "screen-clock"

    chart_nodes = [node for node in screen.view_sets["items"] if node.get("type") in {"chart", "single-value"}]
    ordinary_nodes = [node for node in screen.view_sets["items"] if node.get("type") in {"chart", "single-value", "icon"}]
    allowed_chart_types = {"single", "topN", "line", "pie", "bar", "gauge", "barGauge", "stateTimeline", "text"}
    assert all("presentationRole" not in node for node in ordinary_nodes)
    assert all(node.get("valueConfig", {}).get("chartType") in allowed_chart_types for node in chart_nodes)
    assert all(node.get("valueConfig", {}).get("chartType") != "list" for node in chart_nodes)
    assert all(node.get("valueConfig", {}).get("chartType") != "presentation-list" for node in chart_nodes)
    assert all(node.get("valueConfig", {}).get("chartThemeMode") == "screen-dark" for node in chart_nodes)
    assert all("presentationVariant" not in node.get("valueConfig", {}) for node in chart_nodes)
    assert all("presentationAdapter" not in node.get("valueConfig", {}) for node in chart_nodes)
    assert not any(node.get("name") == "活跃告警详情" for node in screen.view_sets["items"])

    datasource_names = [
        node.get("valueConfig", {}).get("dataSource") for node in screen.view_sets["items"] if node.get("valueConfig", {}).get("dataSource")
    ]
    datasource_ids = set(datasource_names)
    assert DataSourceAPIModel.objects.get(name="活跃告警 TOP N").id not in datasource_ids
    assert DataSourceAPIModel.objects.get(name="模型/实例/分类总数统计").id in datasource_ids
    assert DataSourceAPIModel.objects.get(name="监控中心总览统计").id in datasource_ids
    assert DataSourceAPIModel.objects.get(name="告警统计概览").id in datasource_ids


@pytest.mark.django_db
def test_init_builtin_canvases_creates_builtin_alert_screen():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")

    screen = Screen.objects.get(name__startswith="告警运营大屏", is_build_in=True)
    nodes = screen.view_sets["items"]
    ordinary_nodes = [node for node in nodes if node.get("type") in {"chart", "single-value", "icon"}]
    datasource_names = [node.get("valueConfig", {}).get("dataSource") for node in nodes if node.get("valueConfig", {}).get("dataSource")]
    datasource_ids = set(datasource_names)

    assert screen.view_sets["decorations"]["templateKey"] == "custom-screen"
    assert "edges" not in screen.view_sets
    assert all("presentationRole" not in node for node in ordinary_nodes)
    assert DataSourceAPIModel.objects.get(name="今日告警状态总览").id in datasource_ids
    assert DataSourceAPIModel.objects.get(name="告警状态分布").id in datasource_ids
    assert DataSourceAPIModel.objects.get(name="近7日告警等级趋势").id in datasource_ids

    node_by_id = {node["id"]: node for node in nodes}
    source_top_node = node_by_id["alert-source-event-top"]
    assert source_top_node["valueConfig"]["topNLabelField"] == "source_name"
    assert source_top_node["valueConfig"]["topNValueField"] == "count"

    source_top_datasource = DataSourceAPIModel.objects.get(name="告警源事件数 TOP N")
    source_top_fields = {field["key"]: field["title"] for field in source_top_datasource.field_schema}
    assert source_top_fields["source_name"] == "告警源"
    assert source_top_fields["count"] == "事件数"

    alert_dashboard = Dashboard.objects.get(name="统一告警中心仪表盘", is_build_in=True)
    dashboard_widget_by_id = {widget["id"]: widget for widget in alert_dashboard.view_sets}
    dashboard_source_top_widget = dashboard_widget_by_id["ad522899-2fc5-4b7a-875e-19004c33a425"]
    assert dashboard_source_top_widget["valueConfig"]["topNLabelField"] == "source_name"
    assert dashboard_source_top_widget["valueConfig"]["topNValueField"] == "count"


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
