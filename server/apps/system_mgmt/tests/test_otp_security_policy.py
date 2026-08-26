import json
import types
from unittest.mock import patch

import pytest
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.system_mgmt.models import SystemSettings, User
from apps.system_mgmt.utils.otp_settings import DEFAULT_OTP_RECOMMENDED_APPS, parse_otp_whitelist_ids
from apps.system_mgmt.viewset.system_settings_viewset import SystemSettingsViewSet
from apps.system_mgmt.viewset.user_viewset import UserViewSet


def _security_admin(permission):
    return types.SimpleNamespace(
        username="otp-policy-admin",
        domain="domain.com",
        locale="zh-Hans",
        is_superuser=True,
        is_authenticated=True,
        permission={"system-manager": {permission}},
    )


def _update(data):
    factory = APIRequestFactory()
    request = factory.post("/system_mgmt/system_settings/update_sys_set/", data, format="json")
    force_authenticate(request, user=_security_admin("security_settings-Edit"))
    response = SystemSettingsViewSet.as_view({"post": "update_sys_set"})(request)
    return response, json.loads(response.content)


def _get():
    factory = APIRequestFactory()
    request = factory.get("/system_mgmt/system_settings/get_sys_set/")
    force_authenticate(request, user=_security_admin("security_settings-View"))
    response = SystemSettingsViewSet.as_view({"get": "get_sys_set"})(request)
    return response, json.loads(response.content)


def test_parse_otp_whitelist_ids_coerces_numeric_strings_and_skips_bools():
    assert parse_otp_whitelist_ids('[1, "2", true, "x"]') == {1, 2}
    assert parse_otp_whitelist_ids("") == set()
    assert parse_otp_whitelist_ids("{1}") == set()


@pytest.mark.django_db
def test_update_sys_set_without_otp_keys_does_not_require_them():
    response, payload = _update({"login_expired_time": "12"})
    assert response.status_code == 200, payload
    assert payload["result"] is True
    assert not SystemSettings.objects.filter(key="otp_recommended_apps").exists()


@pytest.mark.django_db
def test_update_sys_set_rejects_empty_recommended_apps_when_otp_enabled():
    response, payload = _update({"enable_otp": "1", "otp_recommended_apps": "  ,  "})
    assert response.status_code == 400
    assert "不能为空" in payload["message"]
    assert not SystemSettings.objects.filter(key="otp_recommended_apps").exists()
    assert not SystemSettings.objects.filter(key="enable_otp").exists()


@pytest.mark.django_db
def test_update_sys_set_allows_empty_recommended_apps_when_otp_disabled():
    response, payload = _update({"enable_otp": "0", "otp_recommended_apps": "  ,  "})
    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="otp_recommended_apps").value == ""


@pytest.mark.django_db
def test_update_sys_set_rejects_enabling_otp_without_recommended_apps():
    response, payload = _update({"enable_otp": "1"})
    assert response.status_code == 400
    assert "不能为空" in payload["message"]
    assert not SystemSettings.objects.filter(key="enable_otp").exists()


@pytest.mark.django_db
def test_update_sys_set_allows_other_keys_when_otp_enabled_with_existing_apps():
    SystemSettings.objects.create(key="enable_otp", value="1")
    SystemSettings.objects.create(key="otp_recommended_apps", value=DEFAULT_OTP_RECOMMENDED_APPS)
    response, payload = _update({"login_expired_time": "12"})
    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="login_expired_time").value == "12"
    assert SystemSettings.objects.get(key="otp_recommended_apps").value == DEFAULT_OTP_RECOMMENDED_APPS


@pytest.mark.django_db
def test_update_sys_set_persists_trimmed_recommended_apps():
    response, payload = _update({"otp_recommended_apps": " Microsoft Authenticator , FreeOTP "})
    assert response.status_code == 200, payload
    assert SystemSettings.objects.get(key="otp_recommended_apps").value == "Microsoft Authenticator,FreeOTP"


@pytest.mark.django_db
def test_update_sys_set_rejects_duplicate_whitelist_ids():
    user = User.objects.create(username="otp-dup", password=make_password("x"), domain="domain.com")
    response, payload = _update({"otp_whitelist": [user.id, user.id]})
    assert response.status_code == 400
    assert "重复" in payload["message"]
    assert not SystemSettings.objects.filter(key="otp_whitelist").exists()


@pytest.mark.django_db
def test_update_sys_set_rejects_missing_whitelist_user():
    response, payload = _update({"otp_whitelist": [999999]})
    assert response.status_code == 400
    assert "不存在" in payload["message"]
    assert not SystemSettings.objects.filter(key="otp_whitelist").exists()


@pytest.mark.django_db
def test_update_sys_set_persists_whitelist_ids():
    user = User.objects.create(username="otp-ok", password=make_password("x"), domain="domain.com")
    response, payload = _update({"otp_whitelist": [str(user.id)]})
    assert response.status_code == 200, payload
    assert json.loads(SystemSettings.objects.get(key="otp_whitelist").value) == [user.id]


@pytest.mark.django_db
def test_get_sys_set_seeds_whitelist_with_builtin_admin():
    admin = User.objects.create(username="admin", password=make_password("x"), domain="domain.com")
    SystemSettings.objects.filter(key="otp_whitelist").delete()

    response, payload = _get()

    assert response.status_code == 200
    assert json.loads(payload["data"]["otp_whitelist"]) == [admin.id]
    assert payload["data"]["otp_recommended_apps"] == DEFAULT_OTP_RECOMMENDED_APPS


@pytest.mark.django_db
def test_get_sys_set_seeds_empty_whitelist_when_admin_missing():
    User.objects.filter(username="admin", domain="domain.com").delete()
    SystemSettings.objects.filter(key="otp_whitelist").delete()

    response, payload = _get()

    assert response.status_code == 200
    assert json.loads(payload["data"]["otp_whitelist"]) == []


@pytest.mark.django_db
def test_get_sys_set_does_not_overwrite_existing_empty_whitelist():
    User.objects.create(username="admin", password=make_password("x"), domain="domain.com")
    SystemSettings.objects.update_or_create(key="otp_whitelist", defaults={"value": "[]"})

    response, payload = _get()

    assert json.loads(payload["data"]["otp_whitelist"]) == []


@pytest.mark.django_db
def test_init_login_settings_defaults_and_is_idempotent():
    admin = User.objects.create(username="admin", password=make_password("x"), domain="domain.com")
    call_command("init_login_settings")
    first = SystemSettings.objects.get(key="otp_whitelist").value
    assert json.loads(first) == [admin.id]
    assert SystemSettings.objects.get(key="otp_recommended_apps").value == DEFAULT_OTP_RECOMMENDED_APPS

    SystemSettings.objects.filter(key="otp_whitelist").update(value="[]")
    call_command("init_login_settings")
    assert SystemSettings.objects.get(key="otp_whitelist").value == "[]"


@pytest.mark.django_db
def test_init_login_settings_empty_whitelist_when_admin_missing():
    User.objects.filter(username="admin", domain="domain.com").delete()
    SystemSettings.objects.filter(key="otp_whitelist").delete()
    call_command("init_login_settings")
    assert json.loads(SystemSettings.objects.get(key="otp_whitelist").value) == []


@pytest.mark.django_db
def test_search_user_list_includes_has_otp_without_secret():
    bound = User.objects.create(
        username="otp-bound",
        password=make_password("x"),
        domain="domain.com",
        otp_secret="JBSWY3DPEHPK3PXP",
    )
    User.objects.create(username="otp-unbound", password=make_password("x"), domain="domain.com")

    factory = APIRequestFactory()
    request = factory.get("/system_mgmt/user/search_user_list/", {"search": "otp-", "page": 1, "page_size": 10})
    force_authenticate(request, user=_security_admin("user_group-View"))
    response = UserViewSet.as_view({"get": "search_user_list"})(request)
    payload = json.loads(response.content)
    users = {item["username"]: item for item in payload["data"]["users"]}

    assert response.status_code == 200
    assert users["otp-bound"]["has_otp"] is True
    assert users["otp-unbound"]["has_otp"] is False
    assert "otp_secret" not in users["otp-bound"]
    assert bound.otp_secret == "JBSWY3DPEHPK3PXP"


@pytest.mark.django_db
def test_unbind_otp_clears_secret_skips_unbound_and_logs():
    bound = User.objects.create(
        username="otp-unbind-bound",
        password=make_password("x"),
        domain="domain.com",
        otp_secret="JBSWY3DPEHPK3PXP",
    )
    unbound = User.objects.create(
        username="otp-unbind-free",
        password=make_password("x"),
        domain="domain.com",
    )

    factory = APIRequestFactory()
    request = factory.post(
        "/system_mgmt/user/change_status/",
        {"user_ids": [bound.id, unbound.id], "action": "unbind_otp"},
        format="json",
    )
    force_authenticate(request, user=_security_admin("user_group-Edit User"))
    with patch("apps.system_mgmt.viewset.user_viewset.log_operation") as mock_log:
        response = UserViewSet.as_view({"post": "change_status"})(request)
    payload = json.loads(response.content)
    bound.refresh_from_db()
    unbound.refresh_from_db()

    assert response.status_code == 200
    assert payload["data"]["success_ids"] == [bound.id]
    assert payload["data"]["skipped"] == [{"id": unbound.id, "reason": "otp_not_bound"}]
    assert bound.otp_secret is None
    assert not unbound.otp_secret
    mock_log.assert_called_once()
    assert "unbind_otp" in mock_log.call_args.args[3]
