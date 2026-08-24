import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from django.db import close_old_connections, transaction
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel, NameSpace
from apps.operation_analysis.models.models import Dashboard, Directory, Topology
from apps.operation_analysis.serializers.import_export_serializers import ExportRequestSerializer
from apps.operation_analysis.services.import_export.authorization_service import ImportExportAuthorizationService
from apps.operation_analysis.services.import_export.export_service import ExportService
from apps.operation_analysis.views.import_export_view import ImportExportViewSet
from apps.operation_analysis.views.openapi_import_export_view import OpenImportExportViewSet
from apps.system_mgmt.models import OperationLog


def _build_request(path, user, data=None, *, api_pass=False, current_team="1"):
    factory = APIRequestFactory()
    request = factory.post(path, data=data or {}, format="json")
    request.COOKIES["current_team"] = current_team
    request.COOKIES["include_children"] = "0"
    request.api_pass = api_pass
    request.user = user
    force_authenticate(request, user=user)
    return request


def _build_doc(item):
    return SimpleNamespace(
        namespaces=[],
        datasources=[],
        dashboards=[item],
        topologies=[],
        architectures=[],
    )


def _build_dashboard_yaml(name: str) -> str:
    return yaml.safe_dump(
        {
            "meta": {
                "schema_version": "1.1.0",
                "object_counts": {
                    "dashboards": 1,
                    "topologies": 0,
                    "architectures": 0,
                    "datasources": 0,
                    "namespaces": 0,
                },
            },
            "dashboards": [
                {
                    "key": f"dashboard::{name}",
                    "name": name,
                    "desc": "",
                    "filters": [],
                    "other": {},
                    "view_sets": [],
                    "refs": {"datasource_keys": [], "namespace_keys": []},
                }
            ],
            "topologies": [],
            "architectures": [],
            "datasources": [],
            "namespaces": [],
        },
        allow_unicode=True,
        sort_keys=False,
    )


def _build_raw_datasource_yaml(name: str, rest_api: str = "monitor/mm_query") -> str:
    return yaml.safe_dump(
        {
            "meta": {
                "schema_version": "1.1.0",
                "object_counts": {"datasources": 1},
            },
            "datasources": [
                {
                    "key": f"datasource::{name}::{rest_api}",
                    "name": name,
                    "rest_api": rest_api,
                    "source_type": "nats",
                    "desc": "",
                    "params": [],
                    "tags": [],
                    "chart_type": [],
                    "field_schema": [],
                    "namespace_keys": [],
                }
            ],
        },
        allow_unicode=True,
        sort_keys=False,
    )


def _unwrap_payload(payload: dict):
    return payload.get("data", payload)


def _create_canvas_dependency_graph(*, datasource_groups: list[int]):
    namespace = NameSpace.objects.create(
        name="dependency-namespace",
        domain="nats.internal.example",
        account="dependency-account",
        password="dependency-password",
    )
    datasource = DataSourceAPIModel.objects.create(
        name="dependency-datasource",
        rest_api="monitor/private_query",
        groups=datasource_groups,
        created_by="other-user",
        updated_by="other-user",
    )
    datasource.namespaces.set([namespace.id])
    dashboard = Dashboard.objects.create(
        name="allowed-dashboard-with-dependency",
        groups=[1],
        created_by="other-user",
        view_sets=[{"valueConfig": {"dataSource": datasource.id}}],
    )
    return dashboard, datasource, namespace


def _permission_rules_for_export(*, dashboard_id: int, datasource_ids: list[int]):
    def get_rules(user, current_team, app_name, permission_key, include_children=False):
        del user, current_team, app_name, include_children
        if permission_key == "directory.dashboard":
            return {"instance": [{"id": dashboard_id, "permission": ["View"]}], "team": []}
        if permission_key == "datasource":
            return {
                "instance": [{"id": datasource_id, "permission": ["View"]} for datasource_id in datasource_ids],
                "team": [],
            }
        return {"instance": [], "team": []}

    return get_rules


@pytest.mark.unit
def test_export_request_rejects_unbounded_object_id_list():
    serializer = ExportRequestSerializer(
        data={"object_type": "dashboard", "object_ids": list(range(1, ExportRequestSerializer.MAX_OBJECT_IDS + 2))}
    )

    assert not serializer.is_valid()
    assert "object_ids" in serializer.errors


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("object_type", "permissions"),
    [
        ("dashboard", set()),
        ("datasource", {"view-View"}),
        ("namespace", {"view-View", "data_source-View"}),
    ],
)
def test_backend_export_rejects_without_required_module_permission(authenticated_user, object_type, permissions):
    authenticated_user.permission = {"ops-analysis": permissions}
    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": object_type, "object_ids": [1]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_openapi_export_rejects_authenticated_token_without_module_permission(authenticated_user):
    authenticated_user.permission = {"ops-analysis": set()}
    authenticated_user.group_list = [{"id": 1, "name": "Default Team"}]
    request = _build_request(
        "/operation_analysis/open_api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [1]},
        api_pass=True,
    )

    response = OpenImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_canvas_export_rejects_dependency_without_datasource_permission(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "namespace-View"}}
    dashboard, datasource, _ = _create_canvas_dependency_graph(datasource_groups=[1])
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(dashboard_id=dashboard.id, datasource_ids=[datasource.id]),
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_canvas_export_rejects_cross_team_datasource_dependency(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "data_source-View", "namespace-View"}}
    dashboard, datasource, _ = _create_canvas_dependency_graph(datasource_groups=[2])
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(dashboard_id=dashboard.id, datasource_ids=[datasource.id]),
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_canvas_export_rejects_partially_visible_dependency_closure(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "data_source-View", "namespace-View"}}
    dashboard, visible_datasource, _ = _create_canvas_dependency_graph(datasource_groups=[1])
    hidden_datasource = DataSourceAPIModel.objects.create(
        name="hidden-dependency-datasource",
        rest_api="monitor/private_query",
        groups=[2],
        created_by="other-user",
        updated_by="other-user",
    )
    dashboard.view_sets.append({"valueConfig": {"dataSource": hidden_datasource.id}})
    dashboard.save(update_fields=["view_sets"])
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(
            dashboard_id=dashboard.id,
            datasource_ids=[visible_datasource.id, hidden_datasource.id],
        ),
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.integration
def test_openapi_canvas_export_rejects_dependency_without_namespace_permission(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "data_source-View"}}
    authenticated_user.group_list = [{"id": 1, "name": "Default Team"}]
    dashboard, datasource, _ = _create_canvas_dependency_graph(datasource_groups=[1])
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(dashboard_id=dashboard.id, datasource_ids=[datasource.id]),
    )

    request = _build_request(
        "/operation_analysis/open_api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
        api_pass=True,
    )

    response = OpenImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_canvas_export_keeps_authorized_dependency_closure(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "data_source-View", "namespace-View"}}
    dashboard, datasource, namespace = _create_canvas_dependency_graph(datasource_groups=[1])
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(dashboard_id=dashboard.id, datasource_ids=[datasource.id]),
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    exported = yaml.safe_load(_unwrap_payload(payload)["yaml_content"])

    assert response.status_code == status.HTTP_200_OK
    assert exported["meta"]["object_counts"]["datasources"] == 1
    assert exported["meta"]["object_counts"]["namespaces"] == 1
    assert exported["datasources"][0]["name"] == datasource.name
    assert exported["namespaces"][0]["name"] == namespace.name


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_canvas_export_never_expands_past_authorized_dependency_plan(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "data_source-View", "namespace-View"}}
    dashboard, datasource, authorized_namespace = _create_canvas_dependency_graph(datasource_groups=[1])
    hidden_namespace = NameSpace.objects.create(
        name="hidden-after-authorization",
        domain="hidden.internal.example",
        account="hidden-account",
        password="hidden-password",
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(dashboard_id=dashboard.id, datasource_ids=[datasource.id]),
    )
    original_collect = ExportService.collect_export_dependencies
    collect_calls = 0
    lock_values = []

    def collect_then_change_relation(cls, scope_type, object_type, object_ids, *, lock=False):
        nonlocal collect_calls
        del cls
        collect_calls += 1
        lock_values.append(lock)
        dependencies = original_collect(scope_type, object_type, object_ids, lock=lock)
        datasource.namespaces.set([hidden_namespace.id])
        return dependencies

    monkeypatch.setattr(ExportService, "collect_export_dependencies", classmethod(collect_then_change_relation))
    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    exported = yaml.safe_load(_unwrap_payload(payload)["yaml_content"])

    assert response.status_code == status.HTTP_200_OK
    assert collect_calls == 1
    assert lock_values == [True]
    assert [namespace["name"] for namespace in exported["namespaces"]] == [authorized_namespace.name]
    assert exported["datasources"][0]["namespace_keys"] == [authorized_namespace.name]
    assert hidden_namespace.name not in response.rendered_content.decode()


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_canvas_export_legacy_mode_is_an_explicit_rollback(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    dashboard, datasource, namespace = _create_canvas_dependency_graph(datasource_groups=[2])
    monkeypatch.setenv("OPS_ANALYSIS_EXPORT_DEPENDENCY_PERMISSION_MODE", "legacy")
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        _permission_rules_for_export(dashboard_id=dashboard.id, datasource_ids=[]),
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    exported = yaml.safe_load(_unwrap_payload(payload)["yaml_content"])

    assert response.status_code == status.HTTP_200_OK
    assert exported["datasources"][0]["name"] == datasource.name
    assert exported["namespaces"][0]["name"] == namespace.name


@pytest.mark.django_db
def test_precheck_drops_overwrite_when_user_lacks_overwrite_permission(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    request = _build_request(
        "/operation_analysis/api/import_export/import/precheck",
        authenticated_user,
        data={"yaml_content": "version: '1.0.0'\ndashboards: []"},
    )
    item = SimpleNamespace(key="dashboard::demo", name="demo")
    result = {
        "valid": True,
        "counts": {"total": 1, "by_type": {"dashboard": 1}},
        "conflicts": [
            {
                "object_key": item.key,
                "object_type": "dashboard",
                "reason": "name_conflict",
                "suggested_actions": ["overwrite", "skip", "rename"],
            }
        ],
        "warnings": [],
        "errors": [],
    }

    monkeypatch.setattr(
        ImportExportAuthorizationService,
        "get_existing_objects_batch",
        classmethod(lambda cls, object_type, items: {item.name: SimpleNamespace(id=1, groups=[1]) for item in items}),
    )
    monkeypatch.setattr(
        ImportExportAuthorizationService,
        "can_access_existing_object",
        classmethod(lambda cls, request, object_type, existing, current_team: True),
    )

    updated = ImportExportAuthorizationService.apply_precheck_permissions(request, _build_doc(item), result, current_team=1)

    assert updated["conflicts"][0]["suggested_actions"] == ["skip", "rename"]


@pytest.mark.django_db
def test_backend_precheck_does_not_readd_rename_for_existing_raw_monitor_query(authenticated_user, monkeypatch):
    authenticated_user.permission = {
        "ops-analysis": {"data_source-View", "data_source-Add", "data_source-Edit"}
    }
    existing = DataSourceAPIModel.objects.create(
        name="legacy-raw-query",
        rest_api="monitor/mm_query",
        source_type="nats",
        groups=[1],
        created_by="system",
        updated_by="system",
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [existing.id],
            "team": [1],
        },
    )
    request = _build_request(
        "/operation_analysis/api/import_export/import/precheck",
        authenticated_user,
        data={"yaml_content": _build_raw_datasource_yaml("legacy-raw-query")},
    )

    response = ImportExportViewSet.as_view({"post": "import_precheck"})(request)
    response.render()
    payload = _unwrap_payload(json.loads(response.rendered_content))

    assert response.status_code == status.HTTP_200_OK
    assert payload["valid"] is True
    assert payload["conflicts"][0]["suggested_actions"] == ["overwrite", "skip"]


@pytest.mark.django_db
def test_import_submit_rejects_overwrite_without_overwrite_permission(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    request = _build_request(
        "/operation_analysis/api/import_export/import/submit",
        authenticated_user,
        data={"yaml_content": "version: '1.0.0'\ndashboards: []"},
    )
    item = SimpleNamespace(key="dashboard::demo", name="demo")
    conflicts = [
        {
            "object_key": item.key,
            "object_type": "dashboard",
            "reason": "name_conflict",
            "suggested_actions": ["overwrite", "skip", "rename"],
        }
    ]

    monkeypatch.setattr(
        ImportExportAuthorizationService,
        "get_existing_objects_batch",
        classmethod(lambda cls, object_type, items: {item.name: SimpleNamespace(id=1, groups=[1]) for item in items}),
    )

    with pytest.raises(PermissionDenied):
        ImportExportAuthorizationService.validate_import_submit_permissions(
            request,
            _build_doc(item),
            conflicts,
            {item.key: "overwrite"},
            current_team=1,
        )


@pytest.mark.django_db
def test_namespace_access_ignores_groups_for_existing_object(authenticated_user):
    authenticated_user.permission = {"ops-analysis": {"namespace-View", "namespace-Edit"}}
    request = _build_request(
        "/operation_analysis/api/import_export/import/precheck",
        authenticated_user,
        data={"yaml_content": "version: '1.0.0'\nnamespaces: []"},
    )

    existing_namespace = SimpleNamespace(id=1, groups=[999])

    assert (
        ImportExportAuthorizationService.can_access_existing_object(
            request,
            ObjectType.NAMESPACE,
            existing_namespace,
            current_team=1,
        )
        is True
    )


@pytest.mark.django_db
def test_backend_precheck_returns_structured_error_for_invalid_yaml(authenticated_user):
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    request = _build_request(
        "/operation_analysis/api/import_export/import/precheck",
        authenticated_user,
        data={"yaml_content": "dashboards: ["},
    )

    response = ImportExportViewSet.as_view({"post": "import_precheck"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    data = _unwrap_payload(payload)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert data["valid"] is False
    assert data["errors"]
    assert "_doc" not in data


@pytest.mark.django_db
def test_openapi_submit_returns_structured_error_for_invalid_yaml(authenticated_user):
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    authenticated_user.group_list = [{"id": 1, "name": "Default Team"}]
    request = _build_request(
        "/operation_analysis/open_api/import_export/import/submit",
        authenticated_user,
        data={"yaml_content": "dashboards: ["},
        api_pass=True,
    )

    response = OpenImportExportViewSet.as_view({"post": "import_submit"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    response_data = response.data

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert response_data["success"] is False
    assert response_data["errors"]
    assert "_doc" not in response_data


def test_precheck_result_includes_doc_key():
    """回归测试 #3704：_build_precheck_result 必须在返回值中携带 _doc，
    供 import_submit / import_precheck 直接取用，避免第二次 YAML 解析。
    若把 _doc 从返回值去掉，本测试失败。
    """
    import yaml

    from apps.operation_analysis.constants.import_export import YAML_SCHEMA_VERSION
    from apps.operation_analysis.schemas.import_export_schema import YAMLDocument
    from apps.operation_analysis.services.import_export.precheck_service import PrecheckService

    yaml_content = f"meta:\n  schema_version: '{YAML_SCHEMA_VERSION}'\n"
    data = yaml.safe_load(yaml_content)
    doc = YAMLDocument(**data)

    result = PrecheckService._build_precheck_result(True, doc, [], [], [])
    assert "_doc" in result, "precheck_result 缺少 '_doc' 键，import_submit 会触发第二次 YAML 解析"
    assert result["_doc"] is doc, "precheck_result['_doc'] 应与传入的 doc 对象完全相同"

    result_none = PrecheckService._build_precheck_result(False, None, [], [], [{"code": "e", "message": "m"}])
    assert "_doc" in result_none, "precheck 失败时 '_doc' 键也必须存在（值为 None）"
    assert result_none["_doc"] is None


@pytest.mark.django_db
def test_backend_import_submit_logs_success_results_as_create_and_update(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    request = _build_request(
        "/operation_analysis/api/import_export/import/submit",
        authenticated_user,
        data={"yaml_content": "version: '1.0.0'\ndashboards: []"},
    )

    monkeypatch.setattr(
        "apps.operation_analysis.views.import_export_view.PrecheckService.precheck",
        staticmethod(lambda **kwargs: {"valid": True, "conflicts": [], "errors": [], "_doc": None}),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.import_export_view.ImportExportAuthorizationService.apply_precheck_permissions",
        classmethod(lambda cls, request, doc, result, current_team: result),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.import_export_view.ImportExportAuthorizationService.validate_conflict_decisions",
        classmethod(lambda cls, conflicts, conflict_decisions: []),
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.import_export_view.ImportExportAuthorizationService.validate_import_submit_permissions",
        classmethod(lambda cls, request, doc, conflicts, conflict_decisions, current_team: None),
    )

    class FakeImportService:
        def __init__(self, **kwargs):
            pass

        def execute(self):
            return {
                "success": True,
                "results": [
                    {
                        "object_key": "dashboard::new-board",
                        "object_type": "dashboard",
                        "status": "success",
                        "new_id": 10,
                    },
                    {
                        "object_key": "datasource::existing-source",
                        "object_type": "datasource",
                        "status": "overwritten",
                        "new_id": 20,
                    },
                    {
                        "object_key": "namespace::skipped",
                        "object_type": "namespace",
                        "status": "skipped",
                        "new_id": None,
                    },
                ],
                "summary": {"success": 1, "overwritten": 1, "skipped": 1, "failed": 0},
            }

    monkeypatch.setattr("apps.operation_analysis.views.import_export_view.ImportService", FakeImportService)

    response = ImportExportViewSet.as_view({"post": "import_submit"})(request)
    response.render()

    logs = list(OperationLog.objects.filter(app="ops-analysis").order_by("id").values("action_type", "summary"))
    assert response.status_code == status.HTTP_200_OK
    assert logs == [
        {"action_type": "create", "summary": "导入新增仪表盘: dashboard::new-board"},
        {"action_type": "update", "summary": "导入更新数据源: datasource::existing-source"},
    ]


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_export_rejects_partially_authorized_root_set(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    allowed_dashboard = Dashboard.objects.create(name="allowed-dashboard", groups=[1], view_sets=[])
    hidden_dashboard = Dashboard.objects.create(name="hidden-dashboard", groups=[1], view_sets=[])

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [{"id": allowed_dashboard.id, "permission": ["View", "Operate"]}],
            "team": [],
        },
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [allowed_dashboard.id, hidden_dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False


@pytest.mark.django_db
@pytest.mark.integration
@pytest.mark.parametrize(
    ("view", "path", "api_pass"),
    [
        (ImportExportViewSet, "/operation_analysis/api/import_export/export", False),
        (OpenImportExportViewSet, "/operation_analysis/open_api/import_export/export", True),
    ],
)
def test_legacy_export_preserves_partially_authorized_root_set(
    authenticated_user,
    monkeypatch,
    view,
    path,
    api_pass,
):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    authenticated_user.group_list = [{"id": 1, "name": "Default Team"}]
    monkeypatch.setenv("OPS_ANALYSIS_EXPORT_DEPENDENCY_PERMISSION_MODE", "legacy")
    allowed_dashboard = Dashboard.objects.create(name="legacy-allowed-dashboard", groups=[1], view_sets=[])
    hidden_dashboard = Dashboard.objects.create(name="legacy-hidden-dashboard", groups=[1], view_sets=[])

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [{"id": allowed_dashboard.id, "permission": ["View", "Operate"]}],
            "team": [],
        },
    )

    request = _build_request(
        path,
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [allowed_dashboard.id, hidden_dashboard.id]},
        api_pass=api_pass,
    )

    response = view.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    yaml_content = _unwrap_payload(payload)["yaml_content"]
    assert allowed_dashboard.name in yaml_content
    assert hidden_dashboard.name not in yaml_content


@pytest.mark.django_db
@pytest.mark.integration
def test_backend_legacy_export_rechecks_root_after_competing_transaction(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    monkeypatch.setenv("OPS_ANALYSIS_EXPORT_DEPENDENCY_PERMISSION_MODE", "legacy")

    def run_committed(callback):
        def execute():
            close_old_connections()
            try:
                with transaction.atomic():
                    return callback()
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(execute).result(timeout=5)

    dashboard_id = run_committed(
        lambda: Dashboard.objects.create(name="permission-race-dashboard", groups=[1], view_sets=[]).id
    )
    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [{"id": dashboard_id, "permission": ["View"]}],
            "team": [],
        },
    )
    original_collect = ExportService.collect_export_dependencies

    def collect_after_permission_change(cls, scope_type, object_type, object_ids, *, lock=False):
        del cls
        run_committed(lambda: Dashboard.objects.filter(id=dashboard_id).update(groups=[2]))
        return original_collect(scope_type, object_type, object_ids, lock=lock)

    monkeypatch.setattr(ExportService, "collect_export_dependencies", classmethod(collect_after_permission_change))
    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [dashboard_id]},
    )

    try:
        response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
        response.render()
    finally:
        run_committed(lambda: Dashboard.objects.filter(id=dashboard_id).delete())

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_backend_export_rejects_when_all_requested_objects_are_filtered(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    hidden_dashboard = Dashboard.objects.create(
        name="fully-hidden-dashboard",
        groups=[1],
        created_by="someoneelse",
        view_sets=[],
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [],
            "team": [],
        },
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "dashboard", "object_ids": [hidden_dashboard.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False


@pytest.mark.django_db
def test_backend_export_allows_creator_visible_topology_without_instance_rule(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    topology = Topology.objects.create(
        name="creator-visible-topology",
        groups=[1],
        created_by=authenticated_user.username,
        view_sets={"nodes": [{"id": "node-1"}], "edges": []},
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [],
            "team": [],
        },
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "topology", "object_ids": [topology.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    data = _unwrap_payload(payload)
    parsed = yaml.safe_load(data["yaml_content"])

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert parsed["meta"]["object_counts"]["topologies"] == 1
    assert parsed["topologies"][0]["name"] == "creator-visible-topology"


@pytest.mark.django_db
def test_backend_export_allows_builtin_topology_visible_by_team(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View"}}
    topology = Topology.objects.create(
        name="builtin-visible-topology",
        groups=[1],
        created_by="system",
        is_build_in=True,
        build_in_key="builtin-visible-topology",
        view_sets={"nodes": [{"id": "node-1"}], "edges": []},
    )

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {
            "instance": [],
            "team": [],
        },
    )

    request = _build_request(
        "/operation_analysis/api/import_export/export",
        authenticated_user,
        data={"object_type": "topology", "object_ids": [topology.id]},
    )

    response = ImportExportViewSet.as_view({"post": "export_objects"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    data = _unwrap_payload(payload)
    parsed = yaml.safe_load(data["yaml_content"])

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert parsed["meta"]["object_counts"]["topologies"] == 1
    assert parsed["topologies"][0]["name"] == "builtin-visible-topology"


@pytest.mark.django_db
def test_openapi_precheck_limits_existing_dashboard_to_rename_when_rpc_scope_denies_access(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    authenticated_user.group_list = [{"id": 1, "name": "Default Team"}]
    Dashboard.objects.create(name="demo-dashboard", groups=[1], view_sets=[])
    directory = Directory.objects.create(name="demo-dir", groups=[1])

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {"instance": [], "team": []},
    )

    request = _build_request(
        "/operation_analysis/open_api/import_export/import/precheck",
        authenticated_user,
        data={"yaml_content": _build_dashboard_yaml("demo-dashboard"), "target_directory_id": directory.id},
        api_pass=True,
    )

    response = OpenImportExportViewSet.as_view({"post": "import_precheck"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    data = _unwrap_payload(payload)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert data["valid"] is True
    assert data["conflicts"][0]["suggested_actions"] == ["rename"]
    assert "_doc" not in data


@pytest.mark.django_db
def test_openapi_submit_rejects_overwrite_when_rpc_scope_denies_existing_dashboard(authenticated_user, monkeypatch):
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart"}}
    authenticated_user.group_list = [{"id": 1, "name": "Default Team"}]
    Dashboard.objects.create(name="demo-dashboard-submit", groups=[1], view_sets=[])
    directory = Directory.objects.create(name="demo-dir-submit", groups=[1])

    monkeypatch.setattr(
        "apps.operation_analysis.services.import_export.authorization_service.get_permission_rules",
        lambda user, current_team, app_name, permission_key, include_children=False: {"instance": [], "team": []},
    )

    request = _build_request(
        "/operation_analysis/open_api/import_export/import/submit",
        authenticated_user,
        data={
            "yaml_content": _build_dashboard_yaml("demo-dashboard-submit"),
            "target_directory_id": directory.id,
            "conflict_decisions": [{"object_key": "dashboard::demo-dashboard-submit", "action": "overwrite"}],
        },
        api_pass=True,
    )

    response = OpenImportExportViewSet.as_view({"post": "import_submit"})(request)
    response.render()
    payload = json.loads(response.rendered_content)
    response_data = response.data

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert response_data["errors"][0]["object_key"] == "dashboard::demo-dashboard-submit"
    assert response_data["errors"][0]["allowed_actions"] == ["rename"]


@pytest.mark.django_db
def test_get_existing_objects_batch_issues_single_query_for_multiple_dashboards(authenticated_user):
    """批量查询 N 个同类对象应只发出 1 次 DB 查询，而非逐 item N 次。

    若将实现回退为逐 item 调用 get_existing_object()，该测试因 get_existing_objects_batch
    不被调用（或被调用次数 > 1）而失败，从而守住本次 N+1 修复。
    """
    dashboard_a = Dashboard.objects.create(name="batch-dash-a", groups=[1], view_sets=[])
    dashboard_b = Dashboard.objects.create(name="batch-dash-b", groups=[1], view_sets=[])

    items = [
        SimpleNamespace(name="batch-dash-a", key="dashboard::batch-dash-a"),
        SimpleNamespace(name="batch-dash-b", key="dashboard::batch-dash-b"),
        SimpleNamespace(name="nonexistent-dash", key="dashboard::nonexistent-dash"),
    ]

    with patch.object(
        Dashboard.objects.__class__,
        "filter",
        wraps=Dashboard.objects.filter,
    ) as mock_filter:
        result = ImportExportAuthorizationService.get_existing_objects_batch(ObjectType.DASHBOARD, items)

    # 只调用了一次 filter（批量 name__in=...），而非三次逐 item filter
    assert mock_filter.call_count == 1, f"预期批量查询只调用 1 次 filter，实际调用了 {mock_filter.call_count} 次（存在 N+1）"
    assert result["batch-dash-a"].id == dashboard_a.id
    assert result["batch-dash-b"].id == dashboard_b.id
    assert "nonexistent-dash" not in result


@pytest.mark.django_db
def test_apply_precheck_permissions_uses_batch_lookup_not_per_item(authenticated_user, monkeypatch):
    """apply_precheck_permissions 对多个相同 object_type 的 item 应调用 get_existing_objects_batch
    而非每个 item 单独调用 get_existing_object。

    若回退到旧的 N+1 循环，get_existing_objects_batch 调用次数会为 0，断言失败。
    """
    authenticated_user.permission = {"ops-analysis": {"view-View", "view-AddChart", "view-EditChart"}}
    request = _build_request(
        "/operation_analysis/api/import_export/import/precheck",
        authenticated_user,
    )

    items = [SimpleNamespace(key=f"dashboard::dash-{i}", name=f"dash-{i}") for i in range(5)]
    doc = SimpleNamespace(
        namespaces=[],
        datasources=[],
        dashboards=items,
        topologies=[],
        architectures=[],
    )
    result = {"valid": True, "conflicts": [], "warnings": [], "errors": []}

    batch_call_count = []

    original_batch = ImportExportAuthorizationService.get_existing_objects_batch.__func__

    def counting_batch(cls, object_type, batch_items):
        batch_call_count.append(object_type)
        return original_batch(cls, object_type, batch_items)

    monkeypatch.setattr(
        ImportExportAuthorizationService,
        "get_existing_objects_batch",
        classmethod(counting_batch),
    )

    ImportExportAuthorizationService.apply_precheck_permissions(request, doc, result, current_team=1)

    dashboard_calls = [t for t in batch_call_count if t == ObjectType.DASHBOARD]
    assert len(dashboard_calls) == 1, f"预期对 DASHBOARD 批量查询 1 次，实际 {len(dashboard_calls)} 次"
