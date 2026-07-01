import pydantic.root_model  # noqa
"""alerts-2 切片补充测试：榨取 level/receiver/operator_log 视图与 util 剩余分支。

只针对 term-missing 报告中明确未覆盖的真实分支补真实断言，
不复制被测逻辑、不做透传 mock、外部 adapter/HTTP 边界才打桩。
"""
import json

import pytest
from django.test import RequestFactory
from rest_framework.test import APIRequestFactory

from apps.alerts.utils import util as util_mod


# --------------------------------------------------------------------------
# util.py 剩余分支
# --------------------------------------------------------------------------


def test_parse_time_to_seconds_h_and_s_and_default():
    assert util_mod._parse_time_to_seconds("2h") == 2 * 3600
    assert util_mod._parse_time_to_seconds("45s") == 45
    assert util_mod._parse_time_to_seconds("3") == 3 * 60


def test_parse_time_to_minutes_default_branch():
    assert util_mod._parse_time_to_minutes("7") == 7


def test_window_size_to_int_seconds_floor_to_one_minute():
    assert util_mod.window_size_to_int("30s") == 1
    assert util_mod.window_size_to_int("180s") == 3


def test_window_size_to_int_unknown_unit_raises():
    with pytest.raises(ValueError):
        util_mod.window_size_to_int("5d")


def test_image_to_base64_success_returns_data_uri(tmp_path):
    import base64

    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfakecontent")
    result = util_mod.image_to_base64(str(img))
    assert result.startswith("data:image/png;base64,")
    encoded = result.split(",", 1)[1]
    assert base64.b64decode(encoded) == b"\x89PNG\r\n\x1a\nfakecontent"


def test_image_to_base64_extensionless_uses_output_format(tmp_path):
    img = tmp_path / "noext"
    img.write_bytes(b"datadata")
    result = util_mod.image_to_base64(str(img), output_format="gif")
    assert result.startswith("data:image/gif;base64,")


def test_str_to_md5_known_value():
    assert util_mod.str_to_md5("") == "d41d8cd98f00b204e9800998ecf8427e"
    assert util_mod.str_to_md5("abc") == "900150983cd24fb0d6963f7d28e17f72"


# --------------------------------------------------------------------------
# views/level.py: _get_config_reference_message 未覆盖分支
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_config_ref_alert_assignment_match_rules():
    from apps.alerts.models.alert_operator import AlertAssignment
    from apps.alerts.views.level import LevelModelViewSet

    AlertAssignment.objects.create(
        name="分派RuleRef",
        notification_frequency={},
        match_rules=[[{"key": "level", "value": "1"}]],
    )
    msg = LevelModelViewSet._get_config_reference_message("alert", "1")
    assert "分派策略" in msg
    assert "分派RuleRef" in msg


@pytest.mark.django_db
def test_config_ref_alert_strategy_alert_template():
    from apps.alerts.models.alert_operator import AlarmStrategy
    from apps.alerts.views.level import LevelModelViewSet

    AlarmStrategy.objects.create(
        name="策略TplRef",
        params={"alert_template": {"level": "2"}},
    )
    msg = LevelModelViewSet._get_config_reference_message("alert", "2")
    assert "相关性规则" in msg
    assert "策略TplRef" in msg


@pytest.mark.django_db
def test_config_ref_alert_no_reference_returns_empty():
    from apps.alerts.views.level import LevelModelViewSet

    assert LevelModelViewSet._get_config_reference_message("alert", "99") == ""


@pytest.mark.django_db
def test_config_ref_event_shield_reference():
    from apps.alerts.models.alert_operator import AlertShield
    from apps.alerts.views.level import LevelModelViewSet

    AlertShield.objects.create(
        name="屏蔽EventRef",
        match_rules=[[{"key": "level", "value": "3"}]],
    )
    msg = LevelModelViewSet._get_config_reference_message("event", "3")
    assert "屏蔽策略" in msg
    assert "屏蔽EventRef" in msg


@pytest.mark.django_db
def test_config_ref_event_strategy_reference():
    from apps.alerts.models.alert_operator import AlarmStrategy
    from apps.alerts.views.level import LevelModelViewSet

    AlarmStrategy.objects.create(
        name="策略EventRef",
        match_rules=[[{"key": "level", "value": "4"}]],
    )
    msg = LevelModelViewSet._get_config_reference_message("event", "4")
    assert "相关性规则" in msg
    assert "策略EventRef" in msg


@pytest.mark.django_db
def test_config_ref_event_no_reference_returns_empty():
    from apps.alerts.views.level import LevelModelViewSet

    assert LevelModelViewSet._get_config_reference_message("event", "77") == ""


# --------------------------------------------------------------------------
# views/operator_log.py: get_queryset request is None 分支
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_operator_log_get_queryset_no_request_returns_all():
    from apps.alerts.models.operator_log import OperatorLog
    from apps.alerts.views.operator_log import SystemLogModelViewSet

    OperatorLog.objects.create(
        action="add",
        target_type="alert",
        operator="sys",
        operator_object="x",
        target_id="T-1",
        overview="ov",
    )
    vs = SystemLogModelViewSet()
    qs = vs.get_queryset()
    assert qs.filter(target_id="T-1").exists()
    assert qs.model is OperatorLog


# --------------------------------------------------------------------------
# views/receiver.py: _receive_events 未覆盖分支
# --------------------------------------------------------------------------


def _post(body, secret=None, raw=None):
    factory = APIRequestFactory()
    extra = {"HTTP_SECRET": secret} if secret else {}
    payload = raw if raw is not None else json.dumps(body)
    return factory.post("/receiver/", data=payload, content_type="application/json", **extra)


def _make_source(source_id="src-al2", source_type="restful", **over):
    from apps.alerts.models.alert_source import AlertSource

    defaults = dict(name="源al2", source_id=source_id, source_type=source_type, secret="sec")
    defaults.update(over)
    return AlertSource.objects.create(**defaults)


@pytest.mark.django_db
def test_receive_events_non_dict_payload_rejected():
    from apps.alerts.views.receiver import _receive_events

    request = _post(None, raw=json.dumps([1, 2, 3]))
    response = _receive_events(request)
    assert response.status_code == 400
    assert "Invalid request payload" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receive_events_wrong_source_type_rejected():
    from apps.alerts.views.receiver import _receive_events

    _make_source(source_id="src-al2", source_type="restful")
    request = _post({"source_id": "src-al2"}, secret="sec")
    response = _receive_events(request, expected_source_type="prometheus")
    assert response.status_code == 400
    assert "Invalid source type" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receive_events_missing_events_rejected(monkeypatch):
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-al2", source_type="restful")

    class EmptyAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            pass

        def normalize_payload(self, data):
            return []

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory,
        "get_adapter",
        staticmethod(lambda src: EmptyAdapter),
    )
    request = _post({"source_id": "src-al2"}, secret="sec")
    response = receiver_module._receive_events(request)
    assert response.status_code == 400
    assert "Missing events" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receive_events_missing_secret_rejected(monkeypatch):
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-al2", source_type="restful")

    class OkAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            pass

        def normalize_payload(self, data):
            return [{"event_id": "E1"}]

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory,
        "get_adapter",
        staticmethod(lambda src: OkAdapter),
    )
    request = _post({"source_id": "src-al2"})
    response = receiver_module._receive_events(request)
    assert response.status_code == 400
    assert "Missing secret" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receive_events_value_error_returns_400(monkeypatch):
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-al2", source_type="restful")

    class RaisingAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            pass

        def normalize_payload(self, data):
            raise ValueError("bad payload format")

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory,
        "get_adapter",
        staticmethod(lambda src: RaisingAdapter),
    )
    request = _post({"source_id": "src-al2"}, secret="sec")
    response = receiver_module._receive_events(request)
    assert response.status_code == 400
    assert json.loads(response.content)["message"] == "bad payload format"


@pytest.mark.django_db
def test_receive_events_generic_exception_returns_500(monkeypatch):
    from apps.alerts.views import receiver as receiver_module

    _make_source(source_id="src-al2", source_type="restful")

    class BoomAdapter:
        def __init__(self, alert_source=None, secret=None, events=None):
            pass

        def normalize_payload(self, data):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        receiver_module.AlertSourceAdapterFactory,
        "get_adapter",
        staticmethod(lambda src: BoomAdapter),
    )
    request = _post({"source_id": "src-al2"}, secret="sec")
    response = receiver_module._receive_events(request)
    assert response.status_code == 500
    assert "Internal server error" in json.loads(response.content)["message"]


@pytest.mark.django_db
def test_receive_events_invalid_json_body_returns_400():
    from apps.alerts.views.receiver import _receive_events

    factory = RequestFactory()
    request = factory.post(
        "/receiver/", data="{not-json", content_type="application/json"
    )
    response = _receive_events(request)
    assert response.status_code == 400
