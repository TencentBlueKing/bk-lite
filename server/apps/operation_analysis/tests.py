# -- coding: utf-8 --
# @File: tests.py
# @Time: 2025/7/14 16:35
# @Author: windyzhao
from types import SimpleNamespace
from unittest.mock import Mock

from apps.operation_analysis.common.get_nats_source_data import GetNatsData
from apps.operation_analysis.views.datasource_view import DataSourceAPIModelViewSet


def _make_request(data=None, current_team="1", include_children="0"):
    return SimpleNamespace(
        user=SimpleNamespace(
            username="alice",
            domain="default",
            is_superuser=False,
            permission={"ops-analysis": {"data_source-View"}},
        ),
        data=data or {},
        COOKIES={"current_team": current_team, "include_children": include_children},
    )


def _make_instance():
    return SimpleNamespace(
        id=1,
        groups=[1],
        rest_api="monitor/query_monitor_alert_segments",
        namespaces=SimpleNamespace(all=lambda: [SimpleNamespace(id=11, name="ns-1", namespace="bklite", enable_tls=False, account="u", decrypt_password="p", domain="nats.local:4222")]),
    )


def test_get_source_data_requires_instance_permission(monkeypatch):
    view = DataSourceAPIModelViewSet()
    view.loader = None
    instance = _make_instance()
    request = _make_request()

    monkeypatch.setattr(view, "get_object", Mock(return_value=instance))
    monkeypatch.setattr(view, "get_has_permission", Mock(return_value=False))
    get_data_mock = Mock()
    monkeypatch.setattr("apps.operation_analysis.views.datasource_view.GetNatsData", Mock(return_value=SimpleNamespace(get_data=get_data_mock)))

    response = view.get_source_data(request, pk="1")

    assert response.status_code == 403
    get_data_mock.assert_not_called()


def test_get_source_data_returns_bad_gateway_on_nats_failure(monkeypatch):
    view = DataSourceAPIModelViewSet()
    view.loader = None
    instance = _make_instance()
    request = _make_request()

    monkeypatch.setattr(view, "get_object", Mock(return_value=instance))
    monkeypatch.setattr(view, "get_has_permission", Mock(return_value=True))
    monkeypatch.setattr(
        "apps.operation_analysis.views.datasource_view.GetNatsData",
        Mock(return_value=SimpleNamespace(get_data=Mock(side_effect=RuntimeError("timeout")))),
    )

    response = view.get_source_data(request, pk="1")

    assert response.status_code == 502
    assert response.data["detail"] == "获取数据源数据失败，请稍后重试"


def test_get_nats_data_forwards_include_children_flag():
    request = _make_request(include_children="1")
    client = GetNatsData(
        namespace="monitor",
        path="query_monitor_alert_segments",
        params={},
        namespace_list=[],
        request=request,
    )

    assert client.params["user_info"] == {
        "team": 1,
        "user": "alice",
        "include_children": True,
    }
