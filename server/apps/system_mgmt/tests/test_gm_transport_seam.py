import builtins
import json
import types
from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import SystemSettings
from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet

SETTING = "enable_gm_transport"


def _block_enterprise_gm(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "apps.core.enterprise.gm_transport":
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)


def _admin():
    return types.SimpleNamespace(
        username="gm-seam",
        domain="domain.com",
        locale="zh-Hans",
        is_superuser=True,
        is_authenticated=True,
        permission={"system-manager": {"security_settings-Edit"}},
    )


def test_public_route_is_absent_when_enterprise_is_absent(monkeypatch):
    real_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "apps.core.enterprise.gm_transport_view":
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    from apps.core.urls import _gm_transport_public_routes

    assert _gm_transport_public_routes() == []


def test_middleware_is_absent_when_the_enterprise_file_is_missing(monkeypatch):
    import config.components.app as app_settings

    monkeypatch.setattr(app_settings.os.path, "isfile", lambda _path: False)
    assert app_settings._gm_transport_middleware() == ()


@pytest.mark.django_db
def test_disable_command_leaves_the_switch_when_enterprise_is_absent(monkeypatch):
    SystemSettings.objects.update_or_create(key=SETTING, defaults={"value": "1"})
    _block_enterprise_gm(monkeypatch)
    out = StringIO()
    call_command("disable_gm_transport", stdout=out)
    assert out.getvalue() == ""
    assert SystemSettings.objects.get(key=SETTING).value == "1"


@pytest.mark.django_db
def test_enabling_is_rejected_when_enterprise_is_absent(monkeypatch):
    SystemSettings.objects.update_or_create(key="user_create_initial_password_mode", defaults={"value": "none"})
    SystemSettings.objects.update_or_create(key=SETTING, defaults={"value": "0"})
    _block_enterprise_gm(monkeypatch)
    request = APIRequestFactory().post("/system_mgmt/system_settings/update_sys_set/", {SETTING: "1"}, format="json")
    force_authenticate(request, user=_admin())
    response = SystemSettingsViewSet.as_view({"post": "update_sys_set"})(request)
    body = json.loads(response.content)
    assert response.status_code == 400
    assert body["message"] == "系统发生错误"
    assert "code" not in body
    assert SystemSettings.objects.get(key=SETTING).value == "0"


@pytest.mark.django_db
def test_existing_enabled_switch_is_left_unchanged_without_enterprise(monkeypatch):
    SystemSettings.objects.update_or_create(key="user_create_initial_password_mode", defaults={"value": "none"})
    SystemSettings.objects.update_or_create(key=SETTING, defaults={"value": "1"})
    _block_enterprise_gm(monkeypatch)
    request = APIRequestFactory().post("/system_mgmt/system_settings/update_sys_set/", {SETTING: "1"}, format="json")
    force_authenticate(request, user=_admin())
    response = SystemSettingsViewSet.as_view({"post": "update_sys_set"})(request)
    assert response.status_code == 200
    assert SystemSettings.objects.get(key=SETTING).value == "1"
