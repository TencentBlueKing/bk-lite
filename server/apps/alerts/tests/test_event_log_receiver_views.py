"""事件视图、操作日志视图与告警接收器覆盖测试。

对照 spec/prd/告警中心·集成：外部告警源经接收器校验来源/密钥后归一化入库。
"""

import json

import pytest
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.alerts.models.alert_source import AlertSource
from apps.alerts.models.models import Event
from apps.alerts.models.operator_log import OperatorLog
from apps.alerts.views.event import EventModelViewSet
from apps.alerts.views.operator_log import SystemLogModelViewSet


def _api_request(method, path, user, data=None, team="1"):
    factory = APIRequestFactory()
    fn = getattr(factory, method)
    request = fn(path) if data is None else fn(path, data=data, format="json")
    request.COOKIES["current_team"] = team
    force_authenticate(request, user=user)
    return request


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    return authenticated_user


def _render(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


def _make_source(source_id="src-1", source_type="restful", **over):
    defaults = dict(name="源1", source_id=source_id, source_type=source_type, secret="sec")
    defaults.update(over)
    return AlertSource.objects.create(**defaults)


def _make_event(source, event_id="EVENT-1", **over):
    from django.utils import timezone

    defaults = dict(
        source=source,
        raw_data={},
        title="t",
        level="0",
        start_time=timezone.now(),
        event_id=event_id,
        team=[1],
    )
    defaults.update(over)
    return Event.objects.create(**defaults)


# --------------------------------------------------------------------------
# EventModelViewSet
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_event_list_scoped_by_team(superuser, monkeypatch):
    monkeypatch.setattr(
        "apps.core.utils.viewset_utils.get_permission_rules",
        lambda *a, **k: {"instance": [], "team": ["1"]},
    )
    source = _make_source()
    _make_event(source, event_id="E1", team=[1])
    _make_event(source, event_id="E2", team=[2])
    request = _api_request("get", "/events/", superuser, team="1")
    response = EventModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    # team 过滤后仅 team=1 的事件
    assert len(items) == 1


@pytest.mark.django_db
def test_event_retrieve(superuser):
    source = _make_source()
    event = _make_event(source, event_id="E1", team=[1])
    request = _api_request("get", f"/events/{event.id}/", superuser, team="1")
    response = EventModelViewSet.as_view({"get": "retrieve"})(request, pk=str(event.id))
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    assert payload["data"]["event_id"] == "E1"


# --------------------------------------------------------------------------
# SystemLogModelViewSet
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_operator_log_list_scoped(superuser):
    from apps.alerts.constants.constants import LogTargetType
    from apps.alerts.models.models import Alert

    Alert.objects.create(alert_id="A1", level="0", title="t", content="c", fingerprint="fp", team=[1])
    OperatorLog.objects.create(
        action="add", target_type=LogTargetType.ALERT, operator="u", target_id="A1", overview="x"
    )
    request = _api_request("get", "/log/", superuser, team="1")
    response = SystemLogModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    assert response.status_code == status.HTTP_200_OK
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) == 1


@pytest.mark.django_db
def test_operator_log_list_no_team_returns_empty(superuser):
    from apps.alerts.constants.constants import LogTargetType

    OperatorLog.objects.create(
        action="add", target_type=LogTargetType.SYSTEM, operator="u", target_id="X", overview="x"
    )
    # 不带 current_team → 范围过滤返回空
    factory = APIRequestFactory()
    request = factory.get("/log/")
    force_authenticate(request, user=superuser)
    response = SystemLogModelViewSet.as_view({"get": "list"})(request)
    payload = _render(response)
    data = payload["data"]
    items = data["items"] if isinstance(data, dict) else data
    assert items == []


# --------------------------------------------------------------------------
# receiver function views
# --------------------------------------------------------------------------


def _post_body(body_dict, secret=None):
    factory = APIRequestFactory()
    extra = {"HTTP_SECRET": secret} if secret else {}
    request = factory.post("/receiver/", data=json.dumps(body_dict), content_type="application/json", **extra)
    return request


@pytest.mark.django_db
def test_receiver_data_wrong_method():
    from apps.alerts.views.receiver import receiver_data

    factory = APIRequestFactory()
    request = factory.get("/receiver/")
    response = receiver_data(request)
    assert response.status_code == 400


@pytest.mark.django_db
def test_receiver_data_missing_source_id():
    from apps.alerts.views.receiver import receiver_data

    request = _post_body({"events": [{}]})
    response = receiver_data(request)
    assert response.status_code == 400
    assert "source_id" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receiver_data_invalid_source():
    from apps.alerts.views.receiver import receiver_data

    request = _post_body({"source_id": "missing"})
    response = receiver_data(request)
    assert response.status_code == 400
    assert "Invalid source_id" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receiver_source_data_wrong_method():
    from apps.alerts.views.receiver import receiver_source_data

    factory = APIRequestFactory()
    request = factory.get("/source/x/webhook/")
    response = receiver_source_data(request, source_id="x")
    assert response.status_code == 400


@pytest.mark.django_db
def test_receiver_source_id_mismatch():
    from apps.alerts.views.receiver import receiver_source_data

    _make_source(source_id="src-1")
    request = _post_body({"source_id": "different"})
    response = receiver_source_data(request, source_id="src-1")
    assert response.status_code == 400
    assert "mismatch" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receiver_full_flow_success(monkeypatch):
    """模拟 adapter 成功归一化并入库"""
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-1", source_type="restful")

    class FakeAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            self.alert_source = alert_source
            self.secret = secret
            self.events = events

        def normalize_payload(self, data):
            return [{"event_id": "E1"}]

        def authenticate(self):
            return True

        def main(self):
            return None

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory, "get_adapter", staticmethod(lambda src: FakeAdapter)
    )

    request = _post_body({"source_id": "src-1"}, secret="sec")
    response = receiver_module.receiver_data(request)
    assert response.status_code == 200
    assert json.loads(response.content)["status"] == "success"


@pytest.mark.django_db
def test_receiver_reports_partial_ingestion(monkeypatch):
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-partial", source_type="restful")

    class FakeAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            self.events = events

        def normalize_payload(self, data):
            return [{"title": "ok"}, {"bad": True}]

        def authenticate(self):
            return True

        def main(self):
            return {"received": 2, "accepted": 1, "skipped": 1, "errored": 0}

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory,
        "get_adapter",
        staticmethod(lambda src: FakeAdapter),
    )

    response = receiver_module.receiver_data(
        _post_body({"source_id": "src-partial"}, secret="sec")
    )
    payload = json.loads(response.content)

    assert response.status_code == 207
    assert payload["status"] == "partial"
    assert payload["ingestion"] == {
        "received": 2, "accepted": 1, "skipped": 1, "errored": 0
    }


@pytest.mark.django_db
def test_receiver_invalid_secret(monkeypatch):
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-1", source_type="restful")

    class FakeAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            pass

        def normalize_payload(self, data):
            return [{"event_id": "E1"}]

        def authenticate(self):
            return False

        def main(self):
            return None

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory, "get_adapter", staticmethod(lambda src: FakeAdapter)
    )

    request = _post_body({"source_id": "src-1"}, secret="wrong")
    response = receiver_module.receiver_data(request)
    assert response.status_code == 403


@pytest.mark.django_db
def test_receiver_authentication_source_error_returns_403(monkeypatch):
    """authenticate() 抛出 AuthenticationSourceError 时应返回 403 而非 500。

    验证修复点：AuthenticationSourceError 被显式捕获并映射到 403，
    revert 该 except 子句后此测试将失败。
    """
    from apps.alerts.error import AuthenticationSourceError
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-auth-err", source_type="restful")

    class FakeAdapterAuthError:
        def __init__(self, alert_source=None, secret=None, events=None):
            pass

        def normalize_payload(self, data):
            return [{"event_id": "E1"}]

        def authenticate(self):
            raise AuthenticationSourceError("Authentication failed")

        def main(self):
            return None

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory, "get_adapter", staticmethod(lambda src: FakeAdapterAuthError)
    )

    request = _post_body({"source_id": "src-auth-err"}, secret="bad-key")
    response = receiver_module.receiver_data(request)
    assert response.status_code == 403
    payload = json.loads(response.content)
    assert payload["status"] == "error"
    assert "Invalid secret" in payload["message"]


def test_request_test_returns_success():
    from apps.alerts.views.receiver import request_test

    response = request_test(None)
    assert response.status_code == 200
