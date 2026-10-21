import json
import logging
import traceback
import types
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.core.logger import SafeLogException
from apps.core.services.gm_transport import reset_degrade_state
from apps.core.tests.test_gm_transport_envelope import KID, PRIVATE_KEY, PUBLIC_KEY
from apps.core.views.gm_transport_view import gm_transport_public
from apps.system_mgmt.models import SystemSettings
from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet

SETTING = "enable_gm_transport"


def _security_admin(permission):
    return types.SimpleNamespace(
        username="gm-policy-admin",
        domain="domain.com",
        locale="zh-Hans",
        is_superuser=True,
        is_authenticated=True,
        permission={"system-manager": {permission}},
    )


def _update(data):
    request = APIRequestFactory().post("/system_mgmt/system_settings/update_sys_set/", data, format="json")
    force_authenticate(request, user=_security_admin("security_settings-Edit"))
    response = SystemSettingsViewSet.as_view({"post": "update_sys_set"})(request)
    return response, json.loads(response.content)


def _get():
    request = APIRequestFactory().get("/system_mgmt/system_settings/get_sys_set/")
    force_authenticate(request, user=_security_admin("security_settings-View"))
    response = SystemSettingsViewSet.as_view({"get": "get_sys_set"})(request)
    return response, json.loads(response.content)


def _public():
    response = gm_transport_public(RequestFactory().get("/api/v1/core/api/gm_transport_public/"))
    return json.loads(response.content)["data"]


def _prepare_settings(value="0"):
    SystemSettings.objects.update_or_create(key="enable_otp", defaults={"value": "0"})
    SystemSettings.objects.update_or_create(key="user_create_initial_password_mode", defaults={"value": "none"})
    SystemSettings.objects.update_or_create(key=SETTING, defaults={"value": value})


@pytest.fixture(autouse=True)
def _reset_degrade():
    reset_degrade_state()
    yield
    reset_degrade_state()


def test_public_view_is_api_exempt():
    assert gm_transport_public.api_exempt is True


@pytest.mark.django_db
def test_get_sys_set_creates_the_switch_default(monkeypatch):
    monkeypatch.delenv("GM_SM2_PRIVATE_KEY", raising=False)
    SystemSettings.objects.filter(key=SETTING).delete()
    response, body = _get()
    assert response.status_code == 200
    assert body["data"][SETTING] == "0"


@pytest.mark.django_db
def test_public_payload_follows_the_switch_and_degrades(monkeypatch, caplog):
    _prepare_settings("0")
    monkeypatch.delenv("GM_SM2_PRIVATE_KEY", raising=False)
    assert _public() == {"enabled": "0"}

    SystemSettings.objects.filter(key=SETTING).update(value="1")
    with caplog.at_level(logging.DEBUG, logger="app"):
        first = _public()
        second = _public()
    assert first == {"enabled": "0", "degraded": "1"}
    assert "public_key" not in first
    assert second == first
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == "event=gm_transport_degraded failed_stage=%s error_type=gm_transport_unavailable"
    assert errors[0].args == ("private_key",)
    assert PRIVATE_KEY not in caplog.text

    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: False)
    with caplog.at_level(logging.DEBUG, logger="app"):
        degraded_cache = _public()
    assert degraded_cache == {"enabled": "0", "degraded": "1"}
    cache_errors = [record for record in caplog.records if record.levelno == logging.ERROR and record.args == ("cache",)]
    assert len(cache_errors) == 1

    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    with caplog.at_level(logging.DEBUG, logger="app"):
        ready = _public()
        ready_again = _public()
    assert ready == {"enabled": "1", "kid": KID, "public_key": PUBLIC_KEY}
    assert ready_again == ready
    assert any(record.msg == "event=gm_transport_ready" for record in caplog.records)


@pytest.mark.django_db
def test_enabling_requires_a_passing_self_check(monkeypatch):
    _prepare_settings("0")
    monkeypatch.delenv("GM_SM2_PRIVATE_KEY", raising=False)
    response, body = _update({SETTING: "1"})
    assert response.status_code == 400
    assert body["code"] == "gm_transport_private_key_missing"
    assert SystemSettings.objects.get(key=SETTING).value == "0"

    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", "zz" * 32)
    response, body = _update({SETTING: "1"})
    assert body["code"] == "gm_transport_private_key_invalid"
    assert SystemSettings.objects.get(key=SETTING).value == "0"


@pytest.mark.django_db
@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "gm-transport-self-check",
        }
    }
)
def test_enabling_rejects_locmem_and_keeps_the_old_value(monkeypatch):
    _prepare_settings("0")
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    response, body = _update({SETTING: "1"})
    assert response.status_code == 400
    assert body["code"] == "gm_transport_cache_unavailable"
    assert SystemSettings.objects.get(key=SETTING).value == "0"


@pytest.mark.django_db
def test_self_check_logs_one_traceback_and_keeps_the_switch_off(monkeypatch, caplog):
    _prepare_settings("0")
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    caught = {}

    class BrokenCache:
        def add(self, key, value, timeout=None):
            exc = ConnectionError("redis://REDIS_PASSWORD_SENTINEL")
            caught["error"] = exc
            raise exc

    monkeypatch.setattr("apps.core.services.gm_transport.cache", BrokenCache())
    with caplog.at_level(logging.DEBUG, logger="app"):
        response, body = _update({SETTING: "1"})
    assert response.status_code == 400
    assert body["code"] == "gm_transport_cache_unavailable"
    assert SystemSettings.objects.get(key=SETTING).value == "0"
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == "event=gm_transport_self_check_failed failed_stage=%s error_type=%s"
    assert errors[0].args == ("cache", "ConnectionError")
    assert errors[0].exc_info[0] is SafeLogException
    assert str(errors[0].exc_info[1]) == "ConnectionError"
    assert errors[0].exc_info[2] is caught["error"].__traceback__
    formatted = "".join(traceback.format_exception(*errors[0].exc_info))
    rendered = errors[0].getMessage() + formatted
    assert "REDIS_PASSWORD_SENTINEL" not in rendered
    assert PRIVATE_KEY not in rendered

    caplog.clear()
    secret = "ALGORITHM_SENTINEL"

    def boom(private_key):
        raise RuntimeError(secret)

    monkeypatch.setattr("apps.core.services.gm_transport.cache", _ProbeCache())
    monkeypatch.setattr("apps.core.services.gm_transport._algorithm_roundtrip", boom)
    with caplog.at_level(logging.DEBUG, logger="app"):
        response, body = _update({SETTING: "1"})
    assert body["code"] == "gm_transport_self_check_failed"
    assert SystemSettings.objects.get(key=SETTING).value == "0"
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].args == ("algorithm", "RuntimeError")
    formatted = "".join(traceback.format_exception(*errors[0].exc_info))
    assert secret not in errors[0].getMessage() + formatted


@pytest.mark.django_db
def test_self_check_delete_failure_logs_one_traceback_and_keeps_the_switch_off(monkeypatch, caplog):
    _prepare_settings("0")
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    caught = {}

    class DeleteBrokenCache:
        def add(self, key, value, timeout=None):
            return True

        def delete(self, key):
            exc = ConnectionError("redis://REDIS_PASSWORD_SENTINEL")
            caught["error"] = exc
            raise exc

    monkeypatch.setattr("apps.core.services.gm_transport.cache", DeleteBrokenCache())
    with caplog.at_level(logging.DEBUG, logger="app"):
        response, body = _update({SETTING: "1"})
    assert response.status_code == 400
    assert body["code"] == "gm_transport_cache_unavailable"
    assert SystemSettings.objects.get(key=SETTING).value == "0"
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].msg == "event=gm_transport_self_check_failed failed_stage=%s error_type=%s"
    assert errors[0].args == ("cache", "ConnectionError")
    assert errors[0].exc_info[0] is SafeLogException
    assert str(errors[0].exc_info[1]) == "ConnectionError"
    assert errors[0].exc_info[2] is caught["error"].__traceback__
    formatted = "".join(traceback.format_exception(*errors[0].exc_info))
    rendered = errors[0].getMessage() + formatted
    assert "REDIS_PASSWORD_SENTINEL" not in rendered
    assert PRIVATE_KEY not in rendered
    assert not any(record.msg == "event=gm_transport_degraded failed_stage=%s error_type=gm_transport_unavailable" for record in caplog.records)


@pytest.mark.django_db
def test_enabling_rejects_an_hmac_that_ignores_its_inputs(monkeypatch):
    _prepare_settings("0")
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    monkeypatch.setattr("apps.core.services.gm_transport.cache", _ProbeCache())
    monkeypatch.setattr("apps.core.services.gm_transport.hmac_sm3", lambda key, message: b"\x00" * 32)
    response, body = _update({SETTING: "1"})
    assert response.status_code == 400
    assert body["code"] == "gm_transport_self_check_failed"
    assert SystemSettings.objects.get(key=SETTING).value == "0"


@pytest.mark.django_db
def test_enabling_succeeds_when_self_check_passes_and_repeat_save_skips_it(monkeypatch):
    _prepare_settings("0")
    monkeypatch.setenv("GM_SM2_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: True)
    monkeypatch.setattr("apps.core.services.gm_transport.cache", _ProbeCache())
    response, body = _update({SETTING: "1"})
    assert response.status_code == 200
    assert body["result"] is True
    assert SystemSettings.objects.get(key=SETTING).value == "1"

    monkeypatch.setattr("apps.core.services.gm_transport.cache_is_redis", lambda: False)
    response, body = _update({SETTING: "1", "login_expired_time": "24"})
    assert response.status_code == 200
    assert SystemSettings.objects.get(key=SETTING).value == "1"

    response, body = _update({SETTING: "0"})
    assert response.status_code == 200
    assert SystemSettings.objects.get(key=SETTING).value == "0"


@pytest.mark.django_db
def test_disable_command_is_idempotent(caplog):
    SystemSettings.objects.filter(key=SETTING).delete()
    out = StringIO()
    with caplog.at_level(logging.INFO, logger="system-manager"):
        call_command("disable_gm_transport", stdout=out)
    assert out.getvalue().strip() == "0 -> 0"
    assert SystemSettings.objects.get(key=SETTING).value == "0"

    SystemSettings.objects.filter(key=SETTING).update(value="1")
    again = StringIO()
    call_command("disable_gm_transport", stdout=again)
    assert again.getvalue().strip() == "1 -> 0"
    assert SystemSettings.objects.get(key=SETTING).value == "0"
    record = next(record for record in caplog.records if record.msg == "event=gm_transport_disabled before=%s after=0")
    assert record.args == ("0",)


class _ProbeCache:
    def add(self, key, value, timeout=None):
        assert key.startswith("gm_transport:selfcheck:")
        return True

    def delete(self, key):
        return True
