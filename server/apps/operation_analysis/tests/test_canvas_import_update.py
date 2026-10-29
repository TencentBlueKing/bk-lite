"""当前画布「导入更新」：按 URL/主键覆盖定义，不走目录冲突页。"""

import uuid

import pytest
import yaml
from rest_framework.test import APIClient

from apps.base.models import User
from apps.operation_analysis.constants.import_export import YAML_SCHEMA_VERSION, ImportExportErrorCode, ImportStatus
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.models.models import Architecture, Dashboard, Directory, NetworkTopology, Report, Screen, Topology
from apps.operation_analysis.services.import_export.canvas_import_update_service import CanvasImportUpdateService
from apps.operation_analysis.services.import_export.import_service import ImportService

CANVAS_MODELS = {
    "dashboard": Dashboard,
    "topology": Topology,
    "architecture": Architecture,
    "screen": Screen,
    "report": Report,
    "networkTopology": NetworkTopology,
}
CANVAS_ENDPOINTS = {
    "dashboard": "/api/v1/operation_analysis/api/dashboard/{id}/import-update/",
    "topology": "/api/v1/operation_analysis/api/topology/{id}/import-update/",
    "architecture": "/api/v1/operation_analysis/api/architecture/{id}/import-update/",
    "screen": "/api/v1/operation_analysis/api/screen/{id}/import-update/",
    "report": "/api/v1/operation_analysis/api/report/{id}/import-update/",
    "networkTopology": "/api/v1/operation_analysis/api/network_topology/{id}/import-update/",
}
CANVAS_SECTIONS = {
    "dashboard": "dashboards",
    "topology": "topologies",
    "architecture": "architectures",
    "screen": "screens",
    "report": "reports",
    "networkTopology": "network_topologies",
}
COUNT_SECTIONS = (
    "dashboards",
    "topologies",
    "architectures",
    "screens",
    "reports",
    "network_topologies",
    "datasources",
    "namespaces",
)


def _yaml(sections: dict) -> str:
    counts = {name: 0 for name in COUNT_SECTIONS}
    counts.update({key: len(value) for key, value in sections.items() if isinstance(value, list)})
    document = {
        "meta": {"schema_version": YAML_SCHEMA_VERSION, "object_counts": counts},
        **sections,
    }
    return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


def _canvas_section(object_type: str, *, name: str, **over) -> dict:
    section = {
        "key": f"{object_type}::origin-{object_type}",
        "name": name,
        "desc": "from-yaml",
    }
    if object_type == "dashboard":
        section.update(other={}, filters=[], view_sets=[{"i": "marker-widget"}])
    elif object_type == "topology":
        section.update(other={}, view_sets={"nodes": [], "edges": [], "filters": []})
    elif object_type == "architecture":
        section.update(other={}, view_sets={"items": [], "views": []})
    elif object_type == "screen":
        section.update(
            other={},
            view_sets={"viewport": {"width": 1920, "height": 1080}, "items": [], "decorations": {}},
        )
    elif object_type == "report":
        section.update(other={}, view_sets={"schema_version": 1, "filters": [], "sections": []})
    elif object_type == "networkTopology":
        section.update(
            base_url="https://weops.example.com/renamed",
            token="******",
            view_sets={"nodes": [], "links": []},
        )
    section.update(over)
    return section


def _datasource_section(**over) -> dict:
    section = {
        "key": "ds-keep::monitor/query",
        "name": "ds-keep",
        "rest_api": "monitor/query",
        "desc": "from-yaml",
        "params": [],
        "tags": [],
        "chart_type": [],
        "field_schema": [],
        "namespace_keys": [],
        "query_config": {"marker": "from-yaml"},
        "connection_config": {},
    }
    section.update(over)
    return section


def _directory(*, groups: list[int]) -> Directory:
    return Directory.objects.create(name=f"dir-{uuid.uuid4()}", groups=groups)


def _canvas(object_type: str, *, groups: list[int], directory: Directory, **over):
    fields = {
        "name": f"origin-{object_type}",
        "desc": "old-desc",
        "groups": groups,
        "directory": directory,
        "created_by": "owner",
        "view_sets": {} if object_type != "dashboard" else [],
    }
    if object_type == "networkTopology":
        fields.update(base_url="https://weops.example.com", token="plain-token", view_sets={"nodes": []})
    fields.update(over)
    return CANVAS_MODELS[object_type].objects.create(**fields)


def _user(*, groups: list[int], permissions: set[str], superuser: bool = False) -> User:
    user = User.objects.create_user(
        username=f"import-update-{uuid.uuid4()}",
        password="testpass123",
        domain="domain.com",
        locale="zh-Hans",
        group_list=[{"id": group_id, "name": f"Team {group_id}"} for group_id in groups],
        roles=[],
    )
    user.permission = {"ops-analysis": permissions}
    user.is_superuser = superuser
    return user


def _client(user: User, current_team: int) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    client.cookies["current_team"] = str(current_team)
    client.cookies["include_children"] = "0"
    return client


def _error_codes(result: dict) -> set[str]:
    return {error["code"] for error in result["errors"]}


@pytest.mark.django_db
@pytest.mark.parametrize("object_type", list(CANVAS_MODELS))
def test_import_update_renames_same_canvas_and_keeps_directory_and_groups(object_type):
    directory = _directory(groups=[1])
    other_directory = _directory(groups=[9])
    canvas = _canvas(object_type, groups=[1, 8], directory=directory)
    original_id = canvas.pk
    payload = _yaml({CANVAS_SECTIONS[object_type]: [_canvas_section(object_type, name=f"renamed-{object_type}")]})

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is True
    canvas.refresh_from_db()
    assert canvas.pk == original_id
    assert canvas.name == f"renamed-{object_type}"
    assert canvas.desc == "from-yaml"
    assert canvas.directory_id == directory.id
    assert canvas.directory_id != other_directory.id
    assert canvas.groups == [1, 8]
    assert CANVAS_MODELS[object_type].objects.count() == 1
    if object_type == "networkTopology":
        assert canvas.base_url == "https://weops.example.com/renamed"
        assert canvas.decrypt_token() == "plain-token"
    if object_type == "dashboard":
        assert canvas.view_sets[0]["i"] == "marker-widget"


@pytest.mark.django_db
def test_import_update_rejects_multiple_canvases_without_writing():
    directory = _directory(groups=[1])
    canvas = _canvas("dashboard", groups=[1], directory=directory)
    payload = _yaml(
        {
            "dashboards": [
                _canvas_section("dashboard", name="renamed-one"),
                _canvas_section("dashboard", name="renamed-two", key="dashboard::second"),
            ],
            "datasources": [_datasource_section(name="should-not-create", key="should-not-create::monitor/query")],
        }
    )

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.IMPORT_UPDATE_CANVAS_COUNT in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-dashboard"
    assert canvas.desc == "old-desc"
    assert not DataSourceAPIModel.objects.filter(name="should-not-create").exists()


@pytest.mark.django_db
def test_import_update_rejects_different_canvas_type_without_writing():
    directory = _directory(groups=[1])
    canvas = _canvas("dashboard", groups=[1], directory=directory)
    payload = _yaml({"screens": [_canvas_section("screen", name="a-screen")]})

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.IMPORT_UPDATE_TYPE_MISMATCH in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-dashboard"
    assert Screen.objects.count() == 0


@pytest.mark.django_db
def test_import_update_ignores_other_canvas_types_and_unreferenced_datasources():
    directory = _directory(groups=[4])
    canvas = _canvas("dashboard", groups=[4, 5], directory=directory)
    payload = _yaml(
        {
            "dashboards": [
                _canvas_section(
                    "dashboard",
                    name="renamed-dashboard",
                    refs={"datasource_keys": ["ds-keep::monitor/query"], "namespace_keys": []},
                    view_sets=[{"i": "w1", "valueConfig": {"dataSource": "ds-keep::monitor/query"}}],
                )
            ],
            "topologies": [_canvas_section("topology", name="ignored-topology")],
            "datasources": [
                _datasource_section(),
                _datasource_section(name="ignored-ds", key="ignored-ds::monitor/query", rest_api="monitor/query"),
            ],
        }
    )

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is True
    assert Topology.objects.count() == 0
    assert not DataSourceAPIModel.objects.filter(name="ignored-ds").exists()
    created = DataSourceAPIModel.objects.get(name="ds-keep")
    assert created.groups == [4, 5]
    canvas.refresh_from_db()
    assert canvas.groups == [4, 5]
    assert canvas.directory_id == directory.id
    assert canvas.view_sets[0]["valueConfig"]["dataSource"] == created.id


@pytest.mark.django_db
def test_import_update_reuses_existing_datasource_without_changing_definition():
    directory = _directory(groups=[4])
    canvas = _canvas("topology", groups=[4, 5], directory=directory)
    existing = DataSourceAPIModel.objects.create(
        name="ds-keep",
        rest_api="monitor/query",
        desc="keep-desc",
        query_config={"marker": "original"},
        connection_config={"password": "real-secret"},
        groups=[9],
        created_by="owner",
        updated_by="owner",
    )
    payload = _yaml(
        {
            "topologies": [
                _canvas_section(
                    "topology",
                    name="renamed-topology",
                    refs={"datasource_keys": ["ds-keep::monitor/query"], "namespace_keys": []},
                    view_sets={
                        "nodes": [{"id": "n1", "valueConfig": {"dataSource": "ds-keep::monitor/query"}}],
                        "edges": [],
                        "filters": [],
                    },
                )
            ],
            "datasources": [
                _datasource_section(
                    desc="changed-desc",
                    query_config={"marker": "from-yaml"},
                    connection_config={"password": "******"},
                )
            ],
        }
    )

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is True
    existing.refresh_from_db()
    assert existing.desc == "keep-desc"
    assert existing.query_config == {"marker": "original"}
    assert existing.connection_config == {"password": "real-secret"}
    assert existing.groups == [9]
    assert DataSourceAPIModel.objects.filter(name="ds-keep").count() == 1
    canvas.refresh_from_db()
    assert canvas.name == "renamed-topology"
    assert canvas.view_sets["nodes"][0]["valueConfig"]["dataSource"] == existing.id


@pytest.mark.django_db
def test_import_update_keeps_existing_datasource_when_object_key_matches_canvas():
    """数据源键 name::rest_api 可能与画布键 type::name 相同，不能因此覆盖数据源。"""
    directory = _directory(groups=[4])
    canvas = _canvas("dashboard", groups=[4, 5], directory=directory)
    shared_key = "dashboard::renamed-dashboard"
    existing = DataSourceAPIModel.objects.create(
        name="dashboard",
        rest_api="renamed-dashboard",
        desc="keep-desc",
        query_config={"marker": "original"},
        connection_config={"password": "real-secret"},
        groups=[9],
        created_by="owner",
        updated_by="owner",
    )
    payload = _yaml(
        {
            "dashboards": [
                _canvas_section(
                    "dashboard",
                    name="renamed-dashboard",
                    key=shared_key,
                    refs={"datasource_keys": [shared_key], "namespace_keys": []},
                    view_sets=[{"i": "w1", "valueConfig": {"dataSource": shared_key}}],
                )
            ],
            "datasources": [
                _datasource_section(
                    key=shared_key,
                    name="dashboard",
                    rest_api="renamed-dashboard",
                    desc="changed-desc",
                    query_config={"marker": "from-yaml"},
                    connection_config={"password": "******"},
                )
            ],
        }
    )

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is True
    assert result["desc"] == "from-yaml"
    existing.refresh_from_db()
    assert existing.desc == "keep-desc"
    assert existing.query_config == {"marker": "original"}
    assert existing.connection_config == {"password": "real-secret"}
    assert existing.groups == [9]
    datasource_results = [item for item in result["results"] if item["object_type"] == "datasource"]
    assert datasource_results[0]["status"] == ImportStatus.SKIPPED.value
    canvas.refresh_from_db()
    assert canvas.name == "renamed-dashboard"
    assert canvas.view_sets[0]["valueConfig"]["dataSource"] == existing.id


@pytest.mark.django_db
def test_import_update_keeps_non_secret_failure_code(monkeypatch):
    directory = _directory(groups=[1])
    canvas = _canvas("dashboard", groups=[1], directory=directory)
    payload = _yaml({"dashboards": [_canvas_section("dashboard", name="renamed-dashboard")]})

    def failed_execute(self):
        return {
            "success": False,
            "results": [
                {
                    "object_key": "dashboard::origin-dashboard",
                    "object_type": "datasource",
                    "status": ImportStatus.FAILED.value,
                    "message": "该监控裸查询接口已退役，禁止继续使用",
                    "code": ImportExportErrorCode.YAML_SCHEMA_INVALID,
                }
            ],
            "summary": {},
        }

    monkeypatch.setattr(ImportService, "execute", failed_execute)

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.YAML_SCHEMA_INVALID in _error_codes(result)
    assert ImportExportErrorCode.IMPORT_SECRET_REQUIRED not in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-dashboard"


@pytest.mark.django_db
def test_import_update_missing_secret_does_not_write():
    directory = _directory(groups=[1])
    canvas = _canvas("screen", groups=[1], directory=directory)
    NameSpace.objects.create(name="kept-ns", domain="old.example", account="old", password="old-secret")
    payload = _yaml(
        {
            "screens": [
                _canvas_section(
                    "screen",
                    name="renamed-screen",
                    refs={"datasource_keys": ["ds-keep::monitor/query"], "namespace_keys": ["new-ns", "kept-ns"]},
                )
            ],
            "datasources": [
                _datasource_section(
                    namespace_keys=["new-ns", "kept-ns"],
                    connection_config={"password": "******"},
                )
            ],
            "namespaces": [
                {
                    "key": "new-ns",
                    "name": "new-ns",
                    "domain": "127.0.0.1:4222",
                    "namespace": "bklite",
                    "account": "admin",
                    "password": "******",
                },
                {
                    "key": "kept-ns",
                    "name": "kept-ns",
                    "domain": "new.example",
                    "namespace": "bklite",
                    "account": "new",
                    "password": "******",
                },
            ],
        }
    )

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.IMPORT_SECRET_REQUIRED in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-screen"
    assert not DataSourceAPIModel.objects.filter(name="ds-keep").exists()
    assert not NameSpace.objects.filter(name="new-ns").exists()
    kept = NameSpace.objects.get(name="kept-ns")
    assert kept.domain == "old.example"


@pytest.mark.django_db
def test_import_update_builtin_service_rejects_without_writing():
    directory = _directory(groups=[1])
    canvas = _canvas("report", groups=[1], directory=directory, is_build_in=True, build_in_key=f"builtin-{uuid.uuid4()}")
    payload = _yaml({"reports": [_canvas_section("report", name="renamed-report")]})

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.IMPORT_UPDATE_BUILTIN in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-report"


@pytest.mark.django_db
def test_import_update_name_conflict_does_not_write():
    directory = _directory(groups=[1])
    canvas = _canvas("architecture", groups=[1], directory=directory)
    _canvas("architecture", groups=[1], directory=directory, name="taken-name")
    payload = _yaml(
        {
            "architectures": [_canvas_section("architecture", name="taken-name")],
            "datasources": [_datasource_section()],
        }
    )

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.IMPORT_UPDATE_NAME_TAKEN in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-architecture"
    assert not DataSourceAPIModel.objects.filter(name="ds-keep").exists()


@pytest.mark.django_db
def test_import_update_write_failure_rolls_back(monkeypatch):
    directory = _directory(groups=[4])
    canvas = _canvas("dashboard", groups=[4, 5], directory=directory)
    payload = _yaml(
        {
            "dashboards": [
                _canvas_section(
                    "dashboard",
                    name="renamed-dashboard",
                    refs={"datasource_keys": ["ds-keep::monitor/query"], "namespace_keys": []},
                )
            ],
            "datasources": [_datasource_section()],
        }
    )

    def broken_save(self, *args, **kwargs):
        raise RuntimeError("forced write failure")

    monkeypatch.setattr(Dashboard, "save", broken_save)

    with pytest.raises(RuntimeError, match="forced write failure"):
        CanvasImportUpdateService.apply(canvas=canvas, yaml_content=payload, updated_by="tester")

    canvas.refresh_from_db()
    assert canvas.name == "origin-dashboard"
    assert canvas.desc == "old-desc"
    assert not DataSourceAPIModel.objects.filter(name="ds-keep").exists()


@pytest.mark.django_db
def test_import_update_invalid_yaml_does_not_write():
    directory = _directory(groups=[1])
    canvas = _canvas("dashboard", groups=[1], directory=directory)

    result = CanvasImportUpdateService.apply(canvas=canvas, yaml_content=": :", updated_by="tester")

    assert result["success"] is False
    assert ImportExportErrorCode.YAML_PARSE_ERROR in _error_codes(result)
    canvas.refresh_from_db()
    assert canvas.name == "origin-dashboard"


@pytest.mark.django_db
@pytest.mark.parametrize("object_type", list(CANVAS_MODELS))
def test_import_update_api_renames_current_canvas(object_type):
    directory = _directory(groups=[1])
    canvas = _canvas(object_type, groups=[1], directory=directory)
    user = _user(groups=[1], permissions={"view-EditChart", "view-View"})
    client = _client(user, 1)
    payload = _yaml({CANVAS_SECTIONS[object_type]: [_canvas_section(object_type, name=f"renamed-{object_type}")]})

    response = client.post(CANVAS_ENDPOINTS[object_type].format(id=canvas.pk), {"yaml_content": payload}, format="json")

    assert response.status_code == 200
    assert response.data["canvas_id"] == canvas.pk
    assert response.data["name"] == f"renamed-{object_type}"
    assert response.data["desc"] == "from-yaml"
    canvas.refresh_from_db()
    assert canvas.name == f"renamed-{object_type}"
    assert canvas.directory_id == directory.id
    assert canvas.groups == [1]


@pytest.mark.django_db
@pytest.mark.parametrize("object_type", ["dashboard", "networkTopology"])
def test_import_update_api_rejects_builtin_canvas(object_type):
    directory = _directory(groups=[1])
    canvas = _canvas(
        object_type,
        groups=[1],
        directory=directory,
        is_build_in=True,
        build_in_key=f"builtin-{object_type}-{uuid.uuid4()}",
    )
    user = _user(groups=[1], permissions={"view-EditChart", "view-View"})
    client = _client(user, 1)
    payload = _yaml({CANVAS_SECTIONS[object_type]: [_canvas_section(object_type, name=f"renamed-{object_type}")]})

    response = client.post(CANVAS_ENDPOINTS[object_type].format(id=canvas.pk), {"yaml_content": payload}, format="json")

    assert response.status_code == 403
    canvas.refresh_from_db()
    assert canvas.name == f"origin-{object_type}"


@pytest.mark.django_db
@pytest.mark.parametrize("object_type", ["dashboard", "networkTopology"])
def test_import_update_api_requires_edit_permission(object_type):
    directory = _directory(groups=[1])
    canvas = _canvas(object_type, groups=[1], directory=directory)
    user = _user(groups=[1], permissions={"view-View"})
    client = _client(user, 1)
    payload = _yaml({CANVAS_SECTIONS[object_type]: [_canvas_section(object_type, name=f"renamed-{object_type}")]})

    response = client.post(CANVAS_ENDPOINTS[object_type].format(id=canvas.pk), {"yaml_content": payload}, format="json")

    assert response.status_code == 403
    canvas.refresh_from_db()
    assert canvas.name == f"origin-{object_type}"
    assert canvas.desc == "old-desc"


@pytest.mark.django_db
def test_import_update_api_rejects_canvas_outside_current_team():
    directory = _directory(groups=[1])
    canvas = _canvas("dashboard", groups=[1], directory=directory)
    user = _user(groups=[9], permissions={"view-EditChart", "view-View"})
    client = _client(user, 9)
    payload = _yaml({"dashboards": [_canvas_section("dashboard", name="renamed-dashboard")]})

    response = client.post(CANVAS_ENDPOINTS["dashboard"].format(id=canvas.pk), {"yaml_content": payload}, format="json")

    # 与画布 update 相同：当前组织不在画布 groups 时 value_error 拒绝，且不写库。
    assert response.json()["result"] is False
    canvas.refresh_from_db()
    assert canvas.name == "origin-dashboard"
    assert canvas.desc == "old-desc"
