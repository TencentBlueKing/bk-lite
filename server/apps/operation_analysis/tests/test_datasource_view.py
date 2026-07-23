import json
from types import SimpleNamespace

import pytest
from django.http import Http404
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.views import datasource_view


def _build_request(user, data=None):
    factory = APIRequestFactory()
    request = factory.post(
        "/operation_analysis/api/data_source/get_source_data/1/",
        data=data or {},
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _build_instance(groups=(1,), rest_api="monitor/query_latest_active_alerts"):
    return SimpleNamespace(
        id=1,
        name="test-datasource",
        groups=list(groups),
        rest_api=rest_api,
        source_type=datasource_view.DataSourceAPIModel.SOURCE_TYPE_NATS,
        connection_config={},
        query_config={},
        params=[
            {"name": "limit", "type": "number", "value": 10, "filterType": "params"},
            {"name": "time_range", "type": "timeRange", "value": 10080, "filterType": "params"},
            {"name": "group_by", "type": "string", "value": "day", "filterType": "fixed"},
        ],
        namespaces=SimpleNamespace(all=lambda: []),
    )


def _build_namespace(namespace_id):
    return SimpleNamespace(
        id=namespace_id,
        name=f"ns-{namespace_id}",
        enable_tls=False,
        account="account",
        decrypt_password="password",
        domain="127.0.0.1:4222",
        namespace="bk_lite",
    )


def _build_view_response(request, monkeypatch, downstream_result):
    captured = {}

    class FakeGetNatsData:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["kwargs"] = kwargs

        def get_data(self):
            return downstream_result

    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: _build_instance(),
    )
    monkeypatch.setattr(datasource_view, "GetNatsData", FakeGetNatsData)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    return response, json.loads(response.rendered_content), captured


@pytest.mark.django_db
def test_get_source_data_returns_success_data(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"limit": "12", "group_by": "hour"})

    response, payload, captured = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["message"] == "success"
    assert payload["data"] == {"count": 0, "items": []}
    assert captured["kwargs"]["params"]["limit"] == 12
    assert captured["kwargs"]["params"]["group_by"] == "day"
    assert isinstance(captured["kwargs"]["params"]["time_range"], list)


@pytest.mark.django_db
def test_get_source_data_accepts_decimal_number_param(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"limit": "12.5"})

    response, payload, captured = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert captured["kwargs"]["params"]["limit"] == 12.5


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("message_text", "expected_status"),
    [
        ("没有权限访问指定的实例", status.HTTP_403_FORBIDDEN),
        ("监控对象不存在", status.HTTP_404_NOT_FOUND),
        ("limit 不能大于 100", status.HTTP_400_BAD_REQUEST),
        ("下游服务执行失败", status.HTTP_502_BAD_GATEWAY),
    ],
)
def test_get_source_data_exposes_downstream_business_failures(
    authenticated_user,
    monkeypatch,
    message_text,
    expected_status,
):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"limit": 10})

    response, payload, _ = _build_view_response(
        request,
        monkeypatch,
        {"result": False, "data": [], "message": message_text},
    )

    assert response.status_code == expected_status
    assert payload["result"] is False
    assert payload["message"] == message_text
    assert payload["data"] == []


@pytest.mark.django_db
def test_get_source_data_returns_500_on_client_exception(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"limit": 10})

    class FakeGetNatsData:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_data(self):
            raise RuntimeError("nats unavailable")

    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: _build_instance(),
    )
    monkeypatch.setattr(datasource_view, "GetNatsData", FakeGetNatsData)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert payload["result"] is False
    assert payload["message"] == "数据查询失败"


@pytest.mark.django_db
def test_get_source_data_returns_typed_not_found_for_deleted_datasource(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"limit": 10})

    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: (_ for _ in ()).throw(Http404()),
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert payload["result"] is False
    assert payload["message"] == "数据源不存在或已删除"


@pytest.mark.django_db
def test_get_source_data_rejects_unknown_params(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"unknown_field": "x"})

    response, payload, _ = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "存在未声明参数" in payload["message"]


@pytest.mark.django_db
def test_get_source_data_applies_default_values_when_request_missing(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={})

    response, payload, captured = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert captured["kwargs"]["params"]["limit"] == 10
    assert captured["kwargs"]["params"]["group_by"] == "day"


@pytest.mark.django_db
def test_get_source_data_accepts_iso8601_time_range(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(
        authenticated_user,
        data={"time_range": ["2026-04-19T09:34:13.712Z", "2026-04-20T09:34:13.712Z"]},
    )

    response, payload, captured = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert isinstance(captured["kwargs"]["params"]["time_range"], list)
    assert len(captured["kwargs"]["params"]["time_range"]) == 2


@pytest.mark.django_db
def test_get_source_data_allows_runtime_query_fields(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(
        authenticated_user,
        data={
            "page": 2,
            "page_size": 50,
            "query_list": [{"field": "name", "type": "str*", "value": "bk"}],
            "namespace_id": 3,
        },
    )

    response, payload, captured = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert captured["kwargs"]["params"]["page"] == 2
    assert captured["kwargs"]["params"]["page_size"] == 50
    assert isinstance(captured["kwargs"]["params"]["query_list"], list)
    assert captured["kwargs"]["params"]["namespace_id"] == 3


@pytest.mark.django_db
def test_get_source_data_rejects_invalid_runtime_query_fields(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(
        authenticated_user,
        data={"page": 0, "page_size": "oops", "query_list": "bad"},
    )

    response, payload, _ = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert "page 必须大于 0" in payload["message"]


@pytest.mark.django_db
def test_get_source_data_rejects_namespace_when_datasource_has_no_namespaces(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"namespace_id": 3})

    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: _build_instance(),
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert payload["message"] == "数据源未关联命名空间"


@pytest.mark.django_db
def test_get_source_data_rejects_unassociated_namespace(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"namespace_id": 3})

    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="test-datasource",
            groups=[1],
            rest_api="monitor/query_latest_active_alerts",
            source_type=datasource_view.DataSourceAPIModel.SOURCE_TYPE_NATS,
            connection_config={},
            query_config={},
            params=[
                {"name": "limit", "type": "number", "value": 10, "filterType": "params"},
                {"name": "time_range", "type": "timeRange", "value": 10080, "filterType": "params"},
                {"name": "group_by", "type": "string", "value": "day", "filterType": "fixed"},
            ],
            namespaces=SimpleNamespace(all=lambda: [_build_namespace(9)]),
        ),
    )

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert payload["result"] is False
    assert payload["message"] == "数据源未关联所选命名空间"


# --- Tests for issue #3394: NameSpaceModelViewSet.partial_update permission enforcement ---


def _build_patch_request(user, data=None):
    factory = APIRequestFactory()
    request = factory.patch(
        "/operation_analysis/api/namespace/1/",
        data=data or {},
        format="json",
    )
    force_authenticate(request, user=user)
    return request


def test_namespace_partial_update_blocked_without_permission(authenticated_user):
    """PATCH /namespace/{id}/ must return 403 when user lacks namespace-Edit permission.

    Regression test for issue #3394: before the fix, partial_update had no @HasPermission
    decorator and any authenticated user could PATCH a namespace.
    If this fix is reverted, the HasPermission wrapper disappears and the method goes
    straight to the DRF default, which does NOT return 403 — so this test would fail.
    """
    authenticated_user.is_superuser = False
    # User has no namespace-Edit permission
    authenticated_user.permission = {"ops-analysis": set()}

    request = _build_patch_request(authenticated_user, data={"domain": "attacker.example.com:4222"})

    view = datasource_view.NameSpaceModelViewSet.as_view({"patch": "partial_update"})
    response = view(request, pk="1")

    assert response.status_code == 403, "PATCH /namespace/{id}/ must be blocked for users without namespace-Edit permission"


def test_namespace_partial_update_allowed_with_permission(authenticated_user, monkeypatch):
    """PATCH /namespace/{id}/ must proceed past permission check when user has namespace-Edit."""
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"namespace-Edit"}}

    # Monkeypatch update to avoid hitting DB so we can verify the permission gate passes
    update_called = []

    def fake_update(self, request, *args, **kwargs):
        update_called.append(True)
        from rest_framework.response import Response

        return Response({"id": 1, "name": "test"})

    monkeypatch.setattr(datasource_view.NameSpaceModelViewSet, "update", fake_update)

    request = _build_patch_request(authenticated_user, data={"domain": "new.example.com:4222"})
    view = datasource_view.NameSpaceModelViewSet.as_view({"patch": "partial_update"})
    response = view(request, pk="1")

    assert update_called, "update() must be called when user has namespace-Edit permission"
    assert response.status_code != 403, "User with namespace-Edit permission must not be blocked"


# --- Tests for issue #3393: DataSourceTagModelViewSet read permission enforcement ---


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["list", "retrieve"])
def test_datasource_tag_read_blocked_without_permission(authenticated_user, action):
    """标签列表和详情必须拒绝缺少 data_source-View 权限的用户。"""
    tag = datasource_view.DataSourceTag.objects.create(
        tag_id="security",
        name="Security",
        created_by="system",
        updated_by="system",
    )
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": set()}

    factory = APIRequestFactory()
    request = factory.get("/operation_analysis/api/tag/")
    force_authenticate(request, user=authenticated_user)
    view = datasource_view.DataSourceTagModelViewSet.as_view({"get": action})

    kwargs = {"pk": str(tag.pk)} if action == "retrieve" else {}
    response = view(request, **kwargs)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
@pytest.mark.parametrize("action", ["list", "retrieve"])
def test_datasource_tag_read_allowed_with_permission(authenticated_user, action):
    """拥有 data_source-View 权限的用户仍可读取标签列表和详情。"""
    tag = datasource_view.DataSourceTag.objects.create(
        tag_id="cmdb",
        name="CMDB",
        created_by="system",
        updated_by="system",
    )
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-View"}}

    factory = APIRequestFactory()
    request = factory.get("/operation_analysis/api/tag/")
    force_authenticate(request, user=authenticated_user)
    view = datasource_view.DataSourceTagModelViewSet.as_view({"get": action})

    kwargs = {"pk": str(tag.pk)} if action == "retrieve" else {}
    response = view(request, **kwargs)

    assert response.status_code == status.HTTP_200_OK
