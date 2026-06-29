"""ImportService 导入执行覆盖测试。

对照 spec/prd/运营分析：YAML 导入按 namespace→datasource→canvas 顺序，
支持 skip/overwrite/rename 冲突策略，任一失败整体回滚。
"""

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.import_export import YAML_SCHEMA_VERSION, ConflictAction
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, DataSourceTag, NameSpace
from apps.operation_analysis.models.models import Dashboard, Directory, Topology
from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
from apps.operation_analysis.services.import_export.import_service import ImportService
from apps.operation_analysis.views import view as view_module


def _doc(**sections):
    data = {"meta": {"schema_version": YAML_SCHEMA_VERSION}}
    data.update(sections)
    return YAMLDocument(**data)


def _ns_section(key="ns1", name="ns-a", **over):
    base = {
        "key": key,
        "name": name,
        "domain": "127.0.0.1:4222",
        "namespace": "bklite",
        "account": "admin",
        "password": "secret",
        "enable_tls": False,
        "desc": "",
    }
    base.update(over)
    return base


def _ds_section(key="ds1::api/x", name="ds-a", **over):
    base = {
        "key": key,
        "name": name,
        "rest_api": "monitor/query",
        "desc": "",
        "params": [],
        "tags": [],
        "chart_type": [],
        "field_schema": [],
        "namespace_keys": [],
    }
    base.update(over)
    return base


def _dashboard_section(key="dashboard::db-a", name="db-a", **over):
    base = {"key": key, "name": name, "desc": "", "other": {}, "view_sets": [], "filters": []}
    base.update(over)
    return base


def _topology_section(key="topology::topo-a", name="topo-a", **over):
    base = {
        "key": key,
        "name": name,
        "desc": "",
        "other": {},
        "view_sets": {"nodes": [], "edges": [], "filters": []},
    }
    base.update(over)
    return base


def _screen_section(key="screen::screen-a", name="screen-a", **over):
    base = {
        "key": key,
        "name": name,
        "desc": "",
        "other": {},
        "view_sets": {"viewport": {"width": 1920, "height": 1080}, "items": [], "decorations": {}},
        "refs": {"datasource_keys": [], "namespace_keys": []},
    }
    base.update(over)
    return base


def _report_section(key="report::report-a", name="report-a", **over):
    base = {
        "key": key,
        "name": name,
        "desc": "",
        "other": {},
        "view_sets": {"time_range": None, "sections": []},
        "refs": {"datasource_keys": [], "namespace_keys": []},
    }
    base.update(over)
    return base


def _service(doc, **over):
    kwargs = dict(
        doc=doc,
        target_directory_id=None,
        conflict_decisions={},
        secret_supplements={},
        created_by="tester",
        updated_by="tester",
        groups=[1],
    )
    kwargs.update(over)
    return ImportService(**kwargs)


# --------------------------------------------------------------------------
# namespace import
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_import_creates_namespace():
    doc = _doc(namespaces=[_ns_section()])
    result = _service(doc).execute()

    assert result["success"] is True
    assert result["summary"]["success"] == 1
    ns = NameSpace.objects.get(name="ns-a")
    assert ns.decrypt_password == "secret"


@pytest.mark.django_db
def test_import_namespace_missing_password_fails_and_rolls_back():
    doc = _doc(namespaces=[_ns_section(password="")])
    result = _service(doc).execute()

    assert result["success"] is False
    assert result["summary"]["failed"] == 1
    # 事务回滚，未创建
    assert not NameSpace.objects.filter(name="ns-a").exists()


@pytest.mark.django_db
def test_import_namespace_skip_existing():
    NameSpace.objects.create(name="ns-a", domain="d", account="a", password="p")
    doc = _doc(namespaces=[_ns_section()])
    result = _service(doc, conflict_decisions={"ns1": ConflictAction.SKIP.value}).execute()

    assert result["summary"]["skipped"] == 1
    assert NameSpace.objects.filter(name="ns-a").count() == 1


@pytest.mark.django_db
def test_import_namespace_overwrite_existing():
    existing = NameSpace.objects.create(name="ns-a", domain="old", account="old", password="p")
    doc = _doc(namespaces=[_ns_section(domain="newhost:4222", account="newacct")])
    result = _service(doc, conflict_decisions={"ns1": ConflictAction.OVERWRITE.value}).execute()

    assert result["summary"]["overwritten"] == 1
    existing.refresh_from_db()
    assert existing.domain == "newhost:4222"
    assert existing.account == "newacct"


@pytest.mark.django_db
def test_import_namespace_rename_existing():
    NameSpace.objects.create(name="ns-a", domain="d", account="a", password="p")
    doc = _doc(namespaces=[_ns_section()])
    result = _service(doc, conflict_decisions={"ns1": ConflictAction.RENAME.value}).execute()

    assert result["summary"]["success"] == 1
    assert NameSpace.objects.filter(name="ns-a_copy").exists()


# --------------------------------------------------------------------------
# datasource import
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_import_datasource_links_namespace_and_tags():
    DataSourceTag.objects.create(tag_id="cmdb", name="CMDB", created_by="s", updated_by="s")
    doc = _doc(
        namespaces=[_ns_section()],
        datasources=[_ds_section(namespace_keys=["ns1"], tags=["CMDB"])],
    )
    result = _service(doc).execute()

    assert result["success"] is True
    ds = DataSourceAPIModel.objects.get(name="ds-a")
    assert ds.namespaces.count() == 1
    assert ds.tag.count() == 1


@pytest.mark.django_db
def test_import_datasource_skip_existing():
    DataSourceAPIModel.objects.create(name="ds-a", rest_api="monitor/query", created_by="s", updated_by="s")
    doc = _doc(datasources=[_ds_section()])
    result = _service(doc, conflict_decisions={"ds1::api/x": ConflictAction.SKIP.value}).execute()

    assert result["summary"]["skipped"] == 1
    assert DataSourceAPIModel.objects.filter(name="ds-a").count() == 1


@pytest.mark.django_db
def test_import_datasource_rename_existing():
    DataSourceAPIModel.objects.create(name="ds-a", rest_api="monitor/query", created_by="s", updated_by="s")
    doc = _doc(datasources=[_ds_section()])
    result = _service(doc, conflict_decisions={"ds1::api/x": ConflictAction.RENAME.value}).execute()

    assert result["summary"]["success"] == 1
    assert DataSourceAPIModel.objects.filter(name="ds-a_copy").exists()


@pytest.mark.django_db
def test_import_datasource_overwrite_existing():
    existing = DataSourceAPIModel.objects.create(name="ds-a", rest_api="monitor/query", desc="old", created_by="s", updated_by="s")
    doc = _doc(datasources=[_ds_section(desc="new desc")])
    result = _service(doc, conflict_decisions={"ds1::api/x": ConflictAction.OVERWRITE.value}).execute()

    assert result["summary"]["overwritten"] == 1
    existing.refresh_from_db()
    assert existing.desc == "new desc"


# --------------------------------------------------------------------------
# canvas (dashboard) import
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_import_dashboard_into_target_directory():
    directory = Directory.objects.create(name="目标目录", groups=[1], created_by="s")
    doc = _doc(dashboards=[_dashboard_section()])
    result = _service(doc, target_directory_id=directory.id).execute()

    assert result["success"] is True
    db = Dashboard.objects.get(name="db-a")
    assert db.directory_id == directory.id


@pytest.mark.django_db
def test_import_topology_into_target_directory_inherits_directory_groups_and_can_save(authenticated_user):
    directory = Directory.objects.create(name="跨组织目标目录", groups=[4], created_by="s")
    doc = _doc(topologies=[_topology_section()])

    result = _service(doc, target_directory_id=directory.id, groups=[1]).execute()

    assert result["success"] is True
    topology = Topology.objects.get(name="topo-a")
    assert topology.directory_id == directory.id
    assert topology.groups == [4]

    user = authenticated_user
    user.is_superuser = True
    request = APIRequestFactory().patch(
        f"/topology/{topology.id}/",
        data={"view_sets": topology.view_sets},
        format="json",
    )
    request.COOKIES["current_team"] = "4"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)

    response = view_module.TopologyModelViewSet.as_view({"patch": "partial_update"})(request, pk=str(topology.id))

    assert response.status_code == 200


@pytest.mark.django_db
def test_import_screen_and_report_into_target_directory():
    from apps.operation_analysis.models.models import Report, Screen

    directory = Directory.objects.create(name="展示输出目录", groups=[3], created_by="s")
    doc = _doc(screens=[_screen_section()], reports=[_report_section()])

    result = _service(doc, target_directory_id=directory.id, groups=[1]).execute()

    assert result["success"] is True
    assert result["summary"]["success"] == 2
    screen = Screen.objects.get(name="screen-a")
    report = Report.objects.get(name="report-a")
    assert screen.directory_id == directory.id
    assert screen.groups == [3]
    assert screen.view_sets["viewport"]["width"] == 1920
    assert report.directory_id == directory.id
    assert report.groups == [3]
    assert report.view_sets == {"time_range": None, "sections": []}


@pytest.mark.django_db
def test_import_dashboard_skip_existing():
    Dashboard.objects.create(name="db-a", groups=[1], created_by="s")
    doc = _doc(dashboards=[_dashboard_section()])
    result = _service(doc, conflict_decisions={"dashboard::db-a": ConflictAction.SKIP.value}).execute()

    assert result["summary"]["skipped"] == 1
    assert Dashboard.objects.filter(name="db-a").count() == 1


@pytest.mark.django_db
def test_import_dashboard_rename_existing():
    Dashboard.objects.create(name="db-a", groups=[1], created_by="s")
    doc = _doc(dashboards=[_dashboard_section()])
    result = _service(doc, conflict_decisions={"dashboard::db-a": ConflictAction.RENAME.value}).execute()

    assert result["summary"]["success"] == 1
    assert Dashboard.objects.filter(name="db-a_copy").exists()


@pytest.mark.django_db
def test_import_dashboard_overwrite_existing():
    existing = Dashboard.objects.create(name="db-a", groups=[1], desc="old", created_by="s")
    doc = _doc(dashboards=[_dashboard_section(desc="new")])
    result = _service(doc, conflict_decisions={"dashboard::db-a": ConflictAction.OVERWRITE.value}).execute()

    assert result["summary"]["overwritten"] == 1
    existing.refresh_from_db()
    assert existing.desc == "new"


# --------------------------------------------------------------------------
# 多对象 + 统计
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_import_full_document_links_datasource_to_imported_namespace():
    doc = _doc(
        namespaces=[_ns_section()],
        datasources=[_ds_section(namespace_keys=["ns1"])],
        dashboards=[_dashboard_section()],
    )
    result = _service(doc).execute()

    assert result["success"] is True
    assert result["summary"]["total"] == 3
    ds = DataSourceAPIModel.objects.get(name="ds-a")
    assert ds.namespaces.filter(name="ns-a").exists()


@pytest.mark.django_db
def test_generate_rename_name_increments_on_repeated_conflict():
    NameSpace.objects.create(name="ns-a", domain="d", account="a", password="p")
    NameSpace.objects.create(name="ns-a_copy", domain="d", account="a", password="p")
    svc = _service(_doc())
    new_name = svc._generate_rename_name("ns-a", NameSpace)
    assert new_name == "ns-a_copy_copy"
