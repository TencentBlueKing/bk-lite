"""init_builtin_canvases 管理命令覆盖测试。

对照 specs/capabilities/legacy-prd-运营分析-运营分析.md：内置画布从 YAML 导入并标记为内置只读对象。
"""

from pathlib import Path

import pytest
import yaml
from django.core.management import call_command

from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.models.models import Dashboard, Directory, Screen

BUILTIN_CANVASES_PATH = Path(__file__).resolve().parents[1] / "support-files" / "builtin_canvases.yaml"


def _load_builtin_alert_screen():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))
    return next(screen for screen in payload["screens"] if screen.get("name", "").startswith("告警运营大屏"))


def _count_nested_key(value, target_key):
    if isinstance(value, list):
        return sum(_count_nested_key(item, target_key) for item in value)
    if isinstance(value, dict):
        return (1 if target_key in value else 0) + sum(_count_nested_key(item, target_key) for item in value.values())
    return 0


def test_builtin_yaml_contains_only_new_alert_screen():
    payload = yaml.safe_load(BUILTIN_CANVASES_PATH.read_text(encoding="utf-8"))

    assert payload["meta"]["object_counts"]["screens"] == 1
    assert [screen["key"] for screen in payload["screens"]] == ["screen::告警运营大屏_内置"]
    assert [screen["name"] for screen in payload["screens"]] == ["告警运营大屏_内置"]
    assert "基础资源态势大屏_内置" not in BUILTIN_CANVASES_PATH.read_text(encoding="utf-8")


def test_builtin_alert_screen_yaml_uses_page_configurable_nodes_only():
    screen = _load_builtin_alert_screen()
    nodes = screen["view_sets"]["items"]
    chart_types = {node.get("valueConfig", {}).get("chartType") for node in nodes}

    assert screen["view_sets"]["viewport"] == {
        "theme": "screen-tech-blue",
        "width": 3840,
        "height": 2160,
        "background": {"key": "tech-grid", "type": "builtIn"},
    }
    assert screen["view_sets"]["decorations"] == {"title": "告警运营大屏", "showClock": True, "showTitle": True}
    assert "edges" not in screen["view_sets"]
    assert len(nodes) == 17
    assert all(node["type"] == "widget" for node in nodes)
    assert all("valueConfig" in node for node in nodes)
    assert _count_nested_key(nodes, "config") == 0
    assert {"single", "bar", "line", "pie", "topN", "table"} <= chart_types

    datasource_refs = set(screen["refs"]["datasource_keys"])
    assert "今日告警状态总览::alert/get_alert_today_status_summary" in datasource_refs
    assert "告警状态分布::alert/get_alert_status_distribution" in datasource_refs
    assert "近7日告警等级趋势::alert/get_alert_level_trend" in datasource_refs

    node_by_id = {node["id"]: node for node in nodes}
    kpi_ids = [
        "alert-kpi-created",
        "alert-kpi-closed",
        "alert-kpi-processing",
        "alert-active-total",
        "alert-active-pending",
        "alert-active-processing",
        "alert-event-total",
    ]
    for node_id in kpi_ids:
        node = node_by_id[node_id]
        assert node["type"] == "widget"
        assert node["chartType"] == "single"
        assert node["valueConfig"]["chartType"] == "single"
        assert node.get("title", "")

    assert node_by_id["alert-source-event-top"]["valueConfig"]["topNLabelField"] == "source_name"
    assert node_by_id["alert-source-event-top"]["valueConfig"]["topNValueField"] == "count"
    assert node_by_id["alert-level-trend"]["valueConfig"]["filterBindings"] == {"time__timeRange": True}


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
def test_init_builtin_canvases_creates_builtin_alert_screen():
    from apps.system_mgmt.models.user import Group

    Group.objects.get_or_create(name="Default")
    _ensure_default_namespace()
    call_command("init_builtin_canvases")

    assert not Screen.objects.filter(name__startswith="基础资源态势大屏", is_build_in=True).exists()
    screen = Screen.objects.get(name="告警运营大屏_内置", is_build_in=True)
    nodes = screen.view_sets["items"]
    datasource_names = [node.get("valueConfig", {}).get("dataSource") for node in nodes if node.get("valueConfig", {}).get("dataSource")]
    datasource_ids = set(datasource_names)

    assert screen.view_sets["viewport"]["width"] == 3840
    assert screen.view_sets["viewport"]["height"] == 2160
    assert screen.view_sets["decorations"] == {"title": "告警运营大屏", "showClock": True, "showTitle": True}
    assert "edges" not in screen.view_sets
    assert len(nodes) == 17
    assert all(node.get("type") == "widget" for node in nodes)
    assert _count_nested_key(nodes, "config") == 0
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
