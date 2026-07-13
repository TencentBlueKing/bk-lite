"""ExportService 与 view_sets 归一/改写工具的覆盖测试。

对照 spec/prd/运营分析：导出按业务键收敛依赖、敏感字段脱敏、稳定排序。
"""

import pytest
import yaml

from apps.operation_analysis.constants.import_export import ObjectType, ScopeType
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.models.models import Dashboard
from apps.operation_analysis.services.import_export import view_sets as vs
from apps.operation_analysis.services.import_export.export_service import ExportService

# --------------------------------------------------------------------------
# view_sets 归一化
# --------------------------------------------------------------------------


def test_normalize_dashboard_returns_list():
    assert vs.normalize_canvas_view_sets_for_storage([{"a": 1}], ObjectType.DASHBOARD) == [{"a": 1}]
    assert vs.normalize_canvas_view_sets_for_storage("bad", ObjectType.DASHBOARD) == []


def test_normalize_topology_fills_keys():
    out = vs.normalize_canvas_view_sets_for_storage({}, ObjectType.TOPOLOGY)
    assert out == {"nodes": [], "edges": [], "filters": []}
    out2 = vs.normalize_canvas_view_sets_for_storage("bad", ObjectType.TOPOLOGY)
    assert out2 == {"nodes": [], "edges": [], "filters": []}


def test_normalize_topology_drops_presentation_fields():
    view_sets = {
        "nodes": [{"id": "n1"}],
        "edges": [],
        "filters": [],
        "viewport": {"width": 1920, "height": 1080, "letterboxColor": "#000000"},
        "presentation": {
            "templateKey": "custom-screen",
            "templateVersion": 1,
            "theme": "tech-blue",
            "background": {"type": "preset", "key": "circuit-blue"},
            "chrome": {"title": "基础资源态势大屏", "showClock": True},
        },
    }

    out = vs.normalize_canvas_view_sets_for_storage(view_sets, ObjectType.TOPOLOGY)

    assert out == {"nodes": [{"id": "n1"}], "edges": [], "filters": []}


def test_normalize_screen_requires_complete_contract():
    with pytest.raises(ValueError, match="view_sets.viewport"):
        vs.normalize_canvas_view_sets_for_storage({}, ObjectType.SCREEN)


def test_normalize_screen_keeps_valid_view_sets_without_ui_defaults():
    out = vs.normalize_canvas_view_sets_for_storage(
        {
            "viewport": {"width": 1920, "height": 1080},
            "items": [],
            "decorations": {},
        },
        ObjectType.SCREEN,
    )

    assert out == {
        "viewport": {"width": 1920, "height": 1080},
        "items": [],
        "decorations": {},
    }


def test_normalize_screen_keeps_unified_filters():
    out = vs.normalize_canvas_view_sets_for_storage(
        {
            "viewport": {"width": 1920, "height": 1080},
            "items": [],
            "decorations": {},
            "filters": [{"id": "time", "name": "时间范围"}],
        },
        ObjectType.SCREEN,
    )

    assert out["filters"] == [{"id": "time", "name": "时间范围"}]


def test_normalize_report_fills_sections():
    out = vs.normalize_canvas_view_sets_for_storage({}, ObjectType.REPORT)

    assert out == {"time_range": None, "sections": []}


def test_normalize_architecture_fills_keys():
    out = vs.normalize_canvas_view_sets_for_storage({"items": [1]}, ObjectType.ARCHITECTURE)
    assert out == {"items": [1], "views": []}
    out2 = vs.normalize_canvas_view_sets_for_storage("bad", ObjectType.ARCHITECTURE)
    assert out2 == {"items": [], "views": []}


def test_normalize_for_yaml_dashboard_and_other():
    assert vs.normalize_canvas_view_sets_for_yaml([1], ObjectType.DASHBOARD) == [1]
    assert vs.normalize_canvas_view_sets_for_yaml({}, ObjectType.TOPOLOGY) == {
        "nodes": [],
        "edges": [],
        "filters": [],
    }


def test_rewrite_datasource_refs_in_dashboard():
    view_sets = [{"valueConfig": {"dataSource": 7, "chartType": "single"}}]
    out = vs.rewrite_canvas_view_sets_refs_for_storage(view_sets, ObjectType.DASHBOARD, {7: "ds::api"})
    assert out[0]["valueConfig"]["dataSource"] == "ds::api"


def test_rewrite_datasource_refs_in_topology():
    view_sets = {
        "nodes": [{"valueConfig": {"dataSource": 3}}],
        "edges": [],
        "filters": [{"x": 1}],
        "viewport": {"width": 1920, "height": 1080, "letterboxColor": "#000000"},
    }
    out = vs.rewrite_canvas_view_sets_refs_for_storage(view_sets, ObjectType.TOPOLOGY, {3: "ds::k"})
    assert out["nodes"][0]["valueConfig"]["dataSource"] == "ds::k"
    assert out["filters"] == [{"x": 1}]
    assert "viewport" not in out


def test_rewrite_topology_refs_drops_presentation():
    view_sets = {
        "nodes": [{"valueConfig": {"dataSource": 3}}],
        "edges": [],
        "filters": [],
        "viewport": {"width": 1600, "height": 900, "letterboxColor": "#050b18"},
        "presentation": {
            "templateKey": "custom-screen",
            "templateVersion": 1,
            "theme": "tech-blue",
            "viewportPreset": "1600x900",
        },
    }

    out = vs.rewrite_canvas_view_sets_refs_for_storage(
        view_sets,
        ObjectType.TOPOLOGY,
        {3: "监控中心总览统计::monitor/get_monitor_statistics"},
    )

    assert out["nodes"][0]["valueConfig"]["dataSource"] == "监控中心总览统计::monitor/get_monitor_statistics"
    assert "presentation" not in out


def test_rewrite_datasource_refs_in_screen_items():
    view_sets = {
        "viewport": {"width": 1920, "height": 1080, "theme": "screen-dark"},
        "items": [{"valueConfig": {"dataSource": 8, "chartType": "line"}}],
        "decorations": {"title": "大屏"},
    }
    out = vs.rewrite_canvas_view_sets_refs_for_storage(view_sets, ObjectType.SCREEN, {8: "ds::screen"})

    assert out["items"][0]["valueConfig"]["dataSource"] == "ds::screen"


def test_rewrite_datasource_refs_in_report_sections():
    view_sets = {
        "time_range": None,
        "sections": [{"valueConfig": {"dataSource": 6, "chartType": "table"}}],
    }
    out = vs.rewrite_canvas_view_sets_refs_for_storage(view_sets, ObjectType.REPORT, {6: "ds::report"})

    assert out["sections"][0]["valueConfig"]["dataSource"] == "ds::report"


def test_rewrite_datasource_refs_for_yaml_architecture():
    view_sets = {"items": [{"valueConfig": {"dataSource": 9}}], "views": []}
    out = vs.rewrite_canvas_view_sets_refs_for_yaml(view_sets, ObjectType.ARCHITECTURE, {9: "ds::z"})
    assert out["items"][0]["valueConfig"]["dataSource"] == "ds::z"


# --------------------------------------------------------------------------
# ExportService 纯函数
# --------------------------------------------------------------------------


def test_generate_business_key_variants():
    from types import SimpleNamespace

    ns = SimpleNamespace(name="ns-a")
    ds = SimpleNamespace(name="ds-a", rest_api="monitor/q")
    db = SimpleNamespace(name="db-a")
    assert ExportService.generate_business_key(ns, ObjectType.NAMESPACE) == "ns-a"
    assert ExportService.generate_business_key(ds, ObjectType.DATASOURCE) == "ds-a::monitor/q"
    assert ExportService.generate_business_key(db, ObjectType.DASHBOARD) == "dashboard::db-a"


def test_mask_sensitive_fields_nested():
    data = {"password": "p", "nested": {"token": "t", "ok": 1}, "list": [{"secret": "s"}, 2]}
    out = ExportService.mask_sensitive_fields(data)
    assert out["password"] == "******"
    assert out["nested"]["token"] == "******"
    assert out["nested"]["ok"] == 1
    assert out["list"][0]["secret"] == "******"
    assert out["list"][1] == 2


def test_extract_canvas_dependencies_collects_datasource_ids():
    view_sets = [
        {"valueConfig": {"dataSource": 1}},
        {"valueConfig": {"dataSource": 2}},
        {"valueConfig": {"dataSource": "non-int"}},
    ]
    ds_ids, ns_ids = ExportService.extract_canvas_dependencies(view_sets, ObjectType.DASHBOARD)
    assert ds_ids == {1, 2}
    assert ns_ids == set()


def test_extract_screen_dependencies_uses_value_config_contract():
    view_sets = {
        "viewport": {"width": 1920, "height": 1080},
        "items": [
            {
                "id": "alert-kpi",
                "type": "widget",
                "valueConfig": {"dataSource": 8, "chartType": "single"},
            }
        ],
        "decorations": {},
    }

    ds_ids, ns_ids = ExportService.extract_canvas_dependencies(view_sets, ObjectType.SCREEN)

    assert ds_ids == {8}
    assert ns_ids == set()


def test_extract_canvas_dependencies_empty():
    assert ExportService.extract_canvas_dependencies([], ObjectType.DASHBOARD) == (set(), set())


# --------------------------------------------------------------------------
# ExportService.export_objects 端到端
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_export_config_namespace():
    ns = NameSpace.objects.create(name="ns-a", domain="d", account="a", password=NameSpace.encrypt_password("p"))
    result = ExportService.export_objects(ScopeType.CONFIG.value, ObjectType.NAMESPACE.value, [ns.id])

    parsed = yaml.safe_load(result["yaml_content"])
    assert parsed["meta"]["object_counts"]["namespaces"] == 1
    assert parsed["namespaces"][0]["password"] == "******"
    assert result["summary"]["exported"]["namespaces"] == 1


@pytest.mark.django_db
def test_export_config_datasource_pulls_in_namespace():
    ns = NameSpace.objects.create(name="ns-a", domain="d", account="a", password="p")
    ds = DataSourceAPIModel.objects.create(name="ds-a", rest_api="monitor/q", created_by="s", updated_by="s")
    ds.namespaces.set([ns.id])
    tag = DataSourceTag.objects.create(tag_id="t1", name="Tag1", created_by="s", updated_by="s")
    ds.tag.set([tag.id])

    result = ExportService.export_objects(ScopeType.CONFIG.value, ObjectType.DATASOURCE.value, [ds.id])
    parsed = yaml.safe_load(result["yaml_content"])
    assert parsed["meta"]["object_counts"]["datasources"] == 1
    # 数据源关联的命名空间被一并导出
    assert parsed["meta"]["object_counts"]["namespaces"] == 1
    assert parsed["datasources"][0]["namespace_keys"] == ["ns-a"]
    assert parsed["datasources"][0]["tags"] == ["Tag1"]


@pytest.mark.django_db
def test_export_canvas_dashboard_with_datasource_dependency():
    ds = DataSourceAPIModel.objects.create(name="ds-a", rest_api="monitor/q", created_by="s", updated_by="s")
    dashboard = Dashboard.objects.create(
        name="db-a",
        groups=[1],
        created_by="s",
        view_sets=[{"valueConfig": {"dataSource": ds.id}}],
    )

    result = ExportService.export_objects(ScopeType.CANVAS.value, ObjectType.DASHBOARD.value, [dashboard.id])
    parsed = yaml.safe_load(result["yaml_content"])
    assert parsed["meta"]["object_counts"]["dashboards"] == 1
    # 依赖收敛：引用的数据源被一并导出
    assert parsed["meta"]["object_counts"]["datasources"] == 1
    db_yaml = parsed["dashboards"][0]
    # view_sets 中的 dataSource 被改写为业务键
    assert db_yaml["view_sets"][0]["valueConfig"]["dataSource"] == "ds-a::monitor/q"
    assert "ds-a::monitor/q" in db_yaml["refs"]["datasource_keys"]


@pytest.mark.django_db
def test_export_canvas_screen_and_report_sections():
    from apps.operation_analysis.models.models import Report, Screen

    screen = Screen.objects.create(
        name="screen-a",
        groups=[1],
        created_by="s",
        view_sets={"viewport": {"width": 1920, "height": 1080}, "items": [], "decorations": {"title": "大屏"}},
    )
    report = Report.objects.create(
        name="report-a",
        groups=[1],
        created_by="s",
        view_sets={"time_range": None, "sections": []},
    )

    screen_result = ExportService.export_objects(ScopeType.CANVAS.value, ObjectType.SCREEN.value, [screen.id])
    report_result = ExportService.export_objects(ScopeType.CANVAS.value, ObjectType.REPORT.value, [report.id])

    screen_yaml = yaml.safe_load(screen_result["yaml_content"])
    report_yaml = yaml.safe_load(report_result["yaml_content"])
    assert screen_yaml["meta"]["object_counts"]["screens"] == 1
    assert screen_yaml["screens"][0]["key"] == "screen::screen-a"
    assert report_yaml["meta"]["object_counts"]["reports"] == 1
    assert report_yaml["reports"][0]["key"] == "report::report-a"
