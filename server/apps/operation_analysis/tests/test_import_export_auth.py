import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import yaml
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.import_export import ObjectType
from apps.operation_analysis.models.models import Dashboard, Directory, Topology
from apps.operation_analysis.services.import_export.authorization_service import ImportExportAuthorizationService
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
                "schema_version": "1.0.0",
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


def _unwrap_payload(payload: dict):
    return payload.get("data", payload)


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
        staticmethod(lambda **kwargs: {"valid": True, "conflicts": [], "errors": []}),
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
def test_backend_export_filters_to_instance_permissions_with_real_dashboards(authenticated_user, monkeypatch):
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
    data = _unwrap_payload(payload)
    yaml_content = data["yaml_content"]

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert "allowed-dashboard" in yaml_content
    assert "hidden-dashboard" not in yaml_content


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
    assert mock_filter.call_count == 1, (
        f"预期批量查询只调用 1 次 filter，实际调用了 {mock_filter.call_count} 次（存在 N+1）"
    )
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

    items = [
        SimpleNamespace(key=f"dashboard::dash-{i}", name=f"dash-{i}")
        for i in range(5)
    ]
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
    assert len(dashboard_calls) == 1, (
        f"预期对 DASHBOARD 批量查询 1 次，实际 {len(dashboard_calls)} 次"
    )
