import json
from types import SimpleNamespace

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

import apps.cmdb.services.instance  # noqa: F401  INSTALL_APPS 需含 cmdb
import apps.monitor.models  # noqa: F401  INSTALL_APPS 需含 monitor
import apps.node_mgmt.models  # noqa: F401  INSTALL_APPS 需含 node_mgmt（monitor.apps.ready → nats.monitor）

from apps.operation_analysis.serializers.scene_widget_serializers import (
    Application3DAlarmDetailRequestSerializer,
    Application3DMetricRequestSerializer,
)
from apps.operation_analysis.views.scene_widget_view import SceneWidgetViewSet

APPLICATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
BIGINT_MAX = 9223372036854775807
SERIALIZERS = (
    Application3DAlarmDetailRequestSerializer,
    Application3DMetricRequestSerializer,
)
VIEW_ACTIONS = (
    ("application3d_alarm_detail", "/operation_analysis/api/scene_widgets/application3d/alarm_detail/"),
    ("application3d_metric", "/operation_analysis/api/scene_widgets/application3d/metric/"),
)


def _payload(alarm_id):
    return {"application_id": APPLICATION_ID, "alarm_id": alarm_id}


def _user():
    return SimpleNamespace(
        is_authenticated=True,
        is_superuser=True,
        username="testuser",
        domain="domain.com",
        locale="zh-CN",
        timezone="Asia/Shanghai",
        permission={},
        group_tree=[],
    )


def _post_request(path, data):
    request = APIRequestFactory().post(path, data=data, format="json")
    request.COOKIES["current_team"] = "1"
    request.COOKIES["include_children"] = "0"
    force_authenticate(request, user=_user())
    return request


def _render(response):
    response.render()
    return json.loads(response.rendered_content)


def _patch_service(monkeypatch, handler):
    monkeypatch.setattr(
        "apps.operation_analysis.views.scene_widget_view.Application3DQueryService.alarm_detail",
        handler,
    )
    monkeypatch.setattr(
        "apps.operation_analysis.views.scene_widget_view.Application3DQueryService.metric_series",
        handler,
    )


def test_non_numeric_alarm_id_returns_400_without_calling_service(monkeypatch):
    accepted = [
        serializer_cls.__name__
        for serializer_cls in SERIALIZERS
        if serializer_cls(data=_payload("not-an-integer")).is_valid()
    ]
    calls = []

    def _raise_value_error(*args, **kwargs):
        calls.append(kwargs.get("alarm_id", args[2] if len(args) > 2 else None))
        raise ValueError("Field 'id' expected a number but got 'not-an-integer'.")

    _patch_service(monkeypatch, _raise_value_error)
    escaped = []
    for action, path in VIEW_ACTIONS:
        request = _post_request(path, _payload("not-an-integer"))
        try:
            response = SceneWidgetViewSet.as_view({"post": action})(request)
        except ValueError as exc:
            escaped.append(f"{action} ValueError escaped: {exc}")
            continue
        if response.status_code != status.HTTP_400_BAD_REQUEST:
            escaped.append(f"{action} status={response.status_code}")
            continue
        message = _render(response).get("message", "")
        if "alarm_id" not in str(message):
            escaped.append(f"{action} message={message}")
    problems = []
    if accepted:
        problems.append("accepted non-numeric alarm_id: " + ",".join(accepted))
    problems.extend(escaped)
    if calls:
        problems.append("service called: " + ",".join(str(item) for item in calls))
    assert not problems, "; ".join(problems)


@pytest.mark.parametrize("serializer_cls", SERIALIZERS)
@pytest.mark.parametrize(
    "alarm_id",
    [
        "not-an-integer",
        "",
        1.5,
        "1.5",
        " 7",
        "7 ",
        " ",
        "+7",
        "-1",
        0,
        "0",
        BIGINT_MAX + 1,
        str(BIGINT_MAX + 1),
    ],
)
def test_alarm_id_serializers_reject_non_canonical_values(serializer_cls, alarm_id):
    serializer = serializer_cls(data=_payload(alarm_id))
    assert serializer.is_valid() is False
    assert "alarm_id" in serializer.errors


@pytest.mark.parametrize("serializer_cls", SERIALIZERS)
@pytest.mark.parametrize(
    ("alarm_id", "expected"),
    [
        (7, "7"),
        ("7", "7"),
        ("007", "7"),
        (BIGINT_MAX, str(BIGINT_MAX)),
        (str(BIGINT_MAX), str(BIGINT_MAX)),
    ],
)
def test_alarm_id_serializers_return_canonical_digit_string(serializer_cls, alarm_id, expected):
    serializer = serializer_cls(data=_payload(alarm_id))
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["alarm_id"] == expected
    assert isinstance(serializer.validated_data["alarm_id"], str)


def test_canonical_alarm_id_reaches_service_as_digit_string(monkeypatch):
    seen = []

    def _ok(*args, **kwargs):
        alarm_id = kwargs["alarm_id"]
        seen.append(alarm_id)
        return {"alarmId": alarm_id}

    _patch_service(monkeypatch, _ok)
    for alarm_id in (7, "7", "007"):
        seen.clear()
        for action, path in VIEW_ACTIONS:
            request = _post_request(path, _payload(alarm_id))
            response = SceneWidgetViewSet.as_view({"post": action})(request)
            payload = _render(response)
            assert response.status_code == status.HTTP_200_OK
            assert payload["result"] is True
            assert payload["data"]["alarmId"] == "7"
        assert seen == ["7", "7"]
