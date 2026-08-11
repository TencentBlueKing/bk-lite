import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.operation_analysis.constants.import_export import SENSITIVE_PLACEHOLDER
from apps.operation_analysis.models.datasource_models import DataSourceAPIModel
from apps.operation_analysis.services.datasource_preview.base import ConnectorError, ExecuteResult, PreviewResult
from apps.operation_analysis.views import datasource_view
from apps.system_mgmt.models.network_white_list import NetworkWhiteList
from apps.system_mgmt.utils.network_whitelist_cache import invalidate_network_whitelist_cache

CHART_PAYLOAD = [
    {"series": "cpu", "name": "2026-01-01T00:00:00Z", "value": 1.0},
    {"series": "cpu", "name": "2026-01-01T00:01:00Z", "value": 2.0},
]


class FakeExecutor:
    def __init__(self, execute_result=None, preview_result=None, test_connection_error=None):
        self.calls = []
        self.test_connection_calls = []
        self.preview_calls = []
        self.execute_result = execute_result or ExecuteResult(data=CHART_PAYLOAD)
        self.preview_result = preview_result or PreviewResult(items=[], count=0, fields=[])
        self.test_connection_error = test_connection_error

    def execute(self, connection_config, params):
        self.calls.append(
            {
                "connection_config": connection_config,
                "params": params,
            }
        )
        return self.execute_result

    def test_connection(self, connection_config):
        if self.test_connection_error is not None:
            raise self.test_connection_error
        self.test_connection_calls.append(connection_config)

    def preview(self, connection_config, query_config, limit=100):
        self.preview_calls.append(
            {
                "connection_config": connection_config,
                "query_config": query_config,
                "limit": limit,
            }
        )
        return self.preview_result


def _build_request(user, path, data=None, *, current_team="1"):
    factory = APIRequestFactory()
    request = factory.post(
        path,
        data=data or {},
        format="json",
    )
    request.COOKIES["current_team"] = str(current_team)
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=user)
    return request


def _build_get_source_data_request(user, data=None):
    return _build_request(
        user,
        "/operation_analysis/api/data_source/get_source_data/1/",
        data=data,
    )


def _prometheus_create_payload(url):
    return {
        "name": "prometheus-policy-check",
        "rest_api": "",
        "groups": [1],
        "source_type": DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
        "connection_config": {"url": url, "auth_type": "none"},
        "query_config": {"query": "up", "query_type": "instant"},
        "params": [{"name": "query", "type": "string", "value": "up", "filterType": "params"}],
    }


@pytest.mark.django_db
def test_create_prometheus_datasource_rejects_target_outside_outbound_whitelist(authenticated_user):
    authenticated_user.is_superuser = True
    request = APIRequestFactory().post(
        "/operation_analysis/api/data_source/",
        data=_prometheus_create_payload("http://10.0.0.1:9090"),
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "create"})(request)

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["connection_config"]["url"][0].code == "NETWORK_WHITELIST_REQUIRED"
    assert not DataSourceAPIModel.objects.filter(name="prometheus-policy-check").exists()


@pytest.mark.django_db
def test_update_prometheus_datasource_rejects_target_outside_outbound_whitelist(authenticated_user):
    authenticated_user.is_superuser = True
    datasource = DataSourceAPIModel.objects.create(
        name="prometheus-policy-check",
        rest_api="",
        groups=[1],
        source_type=DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
        connection_config={"url": "https://prom.example.com", "auth_type": "none"},
        query_config={"query": "up", "query_type": "instant"},
        params=[],
    )
    payload = _prometheus_create_payload("http://10.0.0.1:9090")
    request = APIRequestFactory().put(
        f"/operation_analysis/api/data_source/{datasource.pk}/",
        data=payload,
        format="json",
    )
    request.COOKIES["current_team"] = "1"
    force_authenticate(request, user=authenticated_user)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"put": "update"})(
        request,
        pk=str(datasource.pk),
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["connection_config"]["url"][0].code == "NETWORK_WHITELIST_REQUIRED"
    datasource.refresh_from_db()
    assert datasource.connection_config["url"] == "https://prom.example.com"


@pytest.mark.django_db
def test_prometheus_datasource_crud_round_trip(authenticated_user):
    authenticated_user.is_superuser = True
    NetworkWhiteList.objects.create(network="10.11.73.0/24", enabled=True)
    invalidate_network_whitelist_cache()
    factory = APIRequestFactory()
    payload = {
        "name": "prometheus-crud",
        "rest_api": "",
        "groups": [1],
        "source_type": DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
        "connection_config": {"url": "http://10.11.73.15:9090", "auth_type": "none"},
        "query_config": {"query": "up", "query_type": "instant"},
        "params": [{"name": "query", "type": "string", "value": "up", "filterType": "params"}],
        "chart_type": ["line", "bar", "single"],
        "field_schema": [{"key": "value", "type": "number"}],
    }

    create_request = factory.post("/operation_analysis/api/data_source/", data=payload, format="json")
    create_request.COOKIES["current_team"] = "1"
    force_authenticate(create_request, user=authenticated_user)
    create_response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "create"})(create_request)

    assert create_response.status_code == status.HTTP_201_CREATED
    datasource_id = create_response.data["id"]

    payload["query_config"] = {"query": "rate(up[5m])", "query_type": "range", "step": "1m"}
    update_request = factory.put(
        f"/operation_analysis/api/data_source/{datasource_id}/",
        data=payload,
        format="json",
    )
    update_request.COOKIES["current_team"] = "1"
    force_authenticate(update_request, user=authenticated_user)
    update_response = datasource_view.DataSourceAPIModelViewSet.as_view({"put": "update"})(
        update_request,
        pk=str(datasource_id),
    )

    assert update_response.status_code == status.HTTP_200_OK
    assert update_response.data["query_config"] == payload["query_config"]

    retrieve_request = factory.get(f"/operation_analysis/api/data_source/{datasource_id}/")
    retrieve_request.COOKIES["current_team"] = "1"
    force_authenticate(retrieve_request, user=authenticated_user)
    retrieve_response = datasource_view.DataSourceAPIModelViewSet.as_view({"get": "retrieve"})(
        retrieve_request,
        pk=str(datasource_id),
    )

    assert retrieve_response.status_code == status.HTTP_200_OK
    assert retrieve_response.data["source_type"] == DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS
    assert retrieve_response.data["query_config"] == payload["query_config"]

    delete_request = factory.delete(f"/operation_analysis/api/data_source/{datasource_id}/")
    delete_request.COOKIES["current_team"] = "1"
    force_authenticate(delete_request, user=authenticated_user)
    delete_response = datasource_view.DataSourceAPIModelViewSet.as_view({"delete": "destroy"})(
        delete_request,
        pk=str(datasource_id),
    )

    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert not DataSourceAPIModel.objects.filter(pk=datasource_id).exists()
    invalidate_network_whitelist_cache()


def _build_prometheus_instance():
    return SimpleNamespace(
        id=1,
        name="prometheus-demo",
        groups=[1],
        rest_api="",
        source_type=datasource_view.DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
        connection_config={"url": "https://prom.example.com"},
        query_config={
            "query": "up_from_saved_query_config",
            "query_type": "instant",
            "step": "5m",
            "time_range": ["2020-01-01T00:00:00Z", "2020-01-01T01:00:00Z"],
        },
        params=[
            {"name": "query", "type": "string", "value": "", "filterType": "params"},
            {"name": "query_type", "type": "string", "value": "range", "filterType": "params"},
            {"name": "time_range", "type": "timeRange", "value": 60, "filterType": "params"},
            {"name": "step", "type": "string", "value": "1m", "filterType": "params"},
            {"name": "max_series", "type": "number", "value": 20, "filterType": "params"},
        ],
        namespaces=SimpleNamespace(all=lambda: []),
    )


def _invoke_get_source_data(request, monkeypatch, executor):
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: _build_prometheus_instance(),
    )
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)

    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "get_source_data"})(request, pk="1")
    response.render()
    return response, json.loads(response.rendered_content)


@pytest.mark.django_db
def test_get_source_data_prometheus_passes_runtime_params(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_get_source_data_request(
        authenticated_user,
        data={
            "query": "rate(http_requests_total[5m])",
            "query_type": "range",
            "time_range": ["2026-04-19T09:34:13.712Z", "2026-04-20T09:34:13.712Z"],
            "step": "30s",
            "max_series": 10,
        },
    )
    executor = FakeExecutor()

    response, payload = _invoke_get_source_data(request, monkeypatch, executor)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"] == {
        "data": CHART_PAYLOAD,
        "warnings": [],
    }

    captured = executor.calls[0]
    assert captured["connection_config"] == {"url": "https://prom.example.com"}
    assert captured["params"]["query"] == "rate(http_requests_total[5m])"
    assert captured["params"]["query_type"] == "range"
    assert captured["params"]["step"] == "30s"
    assert captured["params"]["max_series"] == 10
    assert captured["params"]["time_range"] == [
        "2026-04-19T09:34:13.712Z",
        "2026-04-20T09:34:13.712Z",
    ]
    assert captured["params"]["query"] != "up_from_saved_query_config"
    assert captured["params"]["query_type"] != "instant"
    assert captured["params"]["step"] != "5m"


@pytest.mark.django_db
def test_get_source_data_prometheus_returns_warnings_envelope(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = True
    request = _build_get_source_data_request(
        authenticated_user,
        data={
            "query": "up",
            "time_range": ["2026-04-19T09:34:13.712Z", "2026-04-20T09:34:13.712Z"],
        },
    )
    executor = FakeExecutor(
        execute_result=ExecuteResult(
            data=CHART_PAYLOAD,
            warnings=["series truncated to 20"],
        )
    )

    response, payload = _invoke_get_source_data(request, monkeypatch, executor)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["data"] == CHART_PAYLOAD
    assert payload["data"]["warnings"] == ["series truncated to 20"]

    captured = executor.calls[0]["params"]
    assert captured["query"] == "up"
    assert captured["query"] != "up_from_saved_query_config"


@pytest.mark.django_db
def test_test_connection_config_calls_executor(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_source/test_connection/",
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
            "connection_config": {"url": "https://prom.example.com"},
        },
    )
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "test_connection_config"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["message"] == "连接成功"
    assert executor.test_connection_calls == [{"url": "https://prom.example.com"}]


@pytest.mark.django_db
def test_saved_test_connection_merges_redacted_config(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="prometheus-demo",
            groups=[1],
            source_type=DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
            connection_config={"url": "https://prom.example.com", "token": "saved-token"},
            query_config={},
        ),
    )

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_source/1/test_connection/",
        data={
            "connection_config": {
                "url": "https://prom-new.example.com",
                "token": SENSITIVE_PLACEHOLDER,
            },
        },
    )
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "test_connection"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert executor.test_connection_calls == [
        {
            "url": "https://prom-new.example.com",
            "token": "saved-token",
        }
    ]


@pytest.mark.django_db
def test_preview_config_prometheus_passes_query_config(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Add"}}
    executor = FakeExecutor(
        preview_result=PreviewResult(
            items=CHART_PAYLOAD,
            count=len(CHART_PAYLOAD),
            fields=[{"key": "series", "title": "series", "value_type": "string"}],
            warnings=["series truncated to 20"],
        )
    )
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)

    query_config = {
        "query": "up",
        "query_type": "range",
        "time_range": ["2026-04-19T09:34:13.712Z", "2026-04-20T09:34:13.712Z"],
        "step": "1m",
        "max_series": 20,
    }
    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_source/preview/",
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
            "connection_config": {"url": "https://prom.example.com"},
            "query_config": query_config,
            "limit": 50,
        },
    )
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "preview_config"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_200_OK
    assert payload["result"] is True
    assert payload["data"]["warnings"] == ["series truncated to 20"]
    assert executor.preview_calls[0]["connection_config"] == {"url": "https://prom.example.com"}
    assert executor.preview_calls[0]["query_config"] == query_config
    assert executor.preview_calls[0]["limit"] == 50


@pytest.mark.django_db
def test_test_connection_config_requires_edit_permission(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-View"}}
    executor = FakeExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_source/test_connection/",
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
            "connection_config": {"url": "https://prom.example.com"},
        },
    )
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "test_connection_config"})(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert executor.test_connection_calls == []


@pytest.mark.django_db
def test_saved_test_connection_rejects_team_outside_instance_groups(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor()
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)
    monkeypatch.setattr(
        datasource_view.DataSourceAPIModelViewSet,
        "get_object",
        lambda self: SimpleNamespace(
            id=1,
            name="prometheus-demo",
            groups=[2],
            source_type=DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
            connection_config={"url": "https://prom.example.com"},
            query_config={},
        ),
    )

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_source/1/test_connection/",
        data={},
        current_team="1",
    )
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "test_connection"})(request, pk="1")
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert payload["result"] is False
    assert payload["message"] == "无权访问当前数据源"
    assert executor.test_connection_calls == []


@pytest.mark.django_db
def test_test_connection_config_surfaces_connector_error(authenticated_user, monkeypatch):
    authenticated_user.is_superuser = False
    authenticated_user.permission = {"ops-analysis": {"data_source-Edit"}}
    executor = FakeExecutor(
        test_connection_error=ConnectorError(
            "Prometheus 连接失败",
            code="prometheus_unreachable",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )
    )
    monkeypatch.setattr(datasource_view, "get_preview_executor", lambda source_type: executor)

    request = _build_request(
        authenticated_user,
        "/operation_analysis/api/data_source/test_connection/",
        data={
            "source_type": DataSourceAPIModel.SOURCE_TYPE_PROMETHEUS,
            "connection_config": {"url": "https://prom.example.com"},
        },
    )
    response = datasource_view.DataSourceAPIModelViewSet.as_view({"post": "test_connection_config"})(request)
    response.render()
    payload = json.loads(response.rendered_content)

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    assert payload["result"] is False
    assert payload["message"] == "Prometheus 连接失败"
    assert payload["data"] == {"code": "prometheus_unreachable"}
