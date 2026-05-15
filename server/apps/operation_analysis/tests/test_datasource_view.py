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
        groups=list(groups),
        rest_api=rest_api,
        namespaces=SimpleNamespace(all=lambda: []),
    )


def _build_view_response(request, monkeypatch, downstream_result):
    class FakeGetNatsData:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

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
    return response, json.loads(response.rendered_content)


@pytest.mark.django_db
def test_get_source_data_returns_success_data(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_request(authenticated_user, data={"limit": 10})

    response, payload = _build_view_response(
        request,
        monkeypatch,
        {"result": True, "data": {"count": 0, "items": []}, "message": ""},
    )

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["message"] == "success"
    assert payload["data"] == {"count": 0, "items": []}


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

    response, payload = _build_view_response(
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
