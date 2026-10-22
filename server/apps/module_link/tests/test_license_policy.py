import json
import logging
from types import SimpleNamespace

from django.http import HttpResponse

from apps.module_link.license_policy import (
    APP_GUARD_MIDDLEWARE,
    INHERIT_MIDDLEWARE,
    LICENSE_DENIED_TEMPLATE,
    MODULE_LINK_API_PREFIX,
    apply_module_link_license_exempt,
    inject_inherit_middleware,
    is_module_link_api,
    missing_parent_licenses,
)
from apps.module_link.middleware import ModuleLinkLicenseInheritMiddleware

DENIED = "event=module_link_license_inherit_denied missing=%s"
LOOKUP_FAILED = "event=module_link_license_inherit_lookup_failed error_type=%s"
SECRET = "SECRET-PAYLOAD-DO-NOT-LOG"


def test_missing_parent_licenses_requires_both():
    assert missing_parent_licenses({"cmdb", "monitor", "log"}) == ()
    assert missing_parent_licenses({"cmdb"}) == ("monitor",)
    assert missing_parent_licenses({"monitor"}) == ("cmdb",)
    assert missing_parent_licenses(None) == ("cmdb", "monitor")


def test_is_module_link_api():
    assert is_module_link_api("/api/v1/module_link/api/cmdb_monitor_tasks/") is True
    assert is_module_link_api("/api/v1/cmdb/api/instance/") is False
    assert is_module_link_api("") is False


def test_apply_exempt_appends_once():
    guard = SimpleNamespace(LICENSE_EXEMPT_PREFIXES=("/api/v1/core/", "/api/v1/system_mgmt/"))
    assert apply_module_link_license_exempt(guard) is True
    assert guard.LICENSE_EXEMPT_PREFIXES[-1] == MODULE_LINK_API_PREFIX
    assert apply_module_link_license_exempt(guard) is True
    assert guard.LICENSE_EXEMPT_PREFIXES.count(MODULE_LINK_API_PREFIX) == 1


def test_apply_exempt_skips_unknown_guard():
    assert apply_module_link_license_exempt(SimpleNamespace()) is False
    assert apply_module_link_license_exempt(SimpleNamespace(LICENSE_EXEMPT_PREFIXES="nope")) is False


def test_inject_inherit_middleware_before_app_guard():
    settings_obj = SimpleNamespace(MIDDLEWARE=("a", APP_GUARD_MIDDLEWARE, "b"))
    assert inject_inherit_middleware(settings_obj) is True
    assert settings_obj.MIDDLEWARE == ("a", INHERIT_MIDDLEWARE, APP_GUARD_MIDDLEWARE, "b")
    assert inject_inherit_middleware(settings_obj) is True
    assert settings_obj.MIDDLEWARE.count(INHERIT_MIDDLEWARE) == 1


def test_inject_inherit_middleware_skips_without_guard():
    settings_obj = SimpleNamespace(MIDDLEWARE=("a", "b"))
    assert inject_inherit_middleware(settings_obj) is False
    assert settings_obj.MIDDLEWARE == ("a", "b")


def test_apply_exempt_import_error(monkeypatch):
    monkeypatch.setattr("django.apps.apps.is_installed", lambda name: name == "apps.license_mgmt")

    def _boom():
        raise ImportError("no license_mgmt")

    monkeypatch.setattr("apps.module_link.license_policy._load_license_guard", _boom)
    assert apply_module_link_license_exempt() is False


def test_urls_empty_when_cmdb_not_installed(monkeypatch):
    from apps.module_link.urls import build_urlpatterns

    monkeypatch.setattr("django.apps.apps.is_installed", lambda name: False)
    assert build_urlpatterns() == []


def test_apply_exempt_skips_when_license_app_not_installed(monkeypatch):
    monkeypatch.setattr("django.apps.apps.is_installed", lambda name: False)

    def _boom():
        raise AssertionError("should not import")

    monkeypatch.setattr("apps.module_link.license_policy._load_license_guard", _boom)
    assert apply_module_link_license_exempt() is False


def _mw(monkeypatch, *, active=True, names=None, names_error=None):
    monkeypatch.setattr("apps.module_link.middleware._license_guard_active", lambda: active)
    if names_error is not None:

        def _fail():
            raise names_error

        monkeypatch.setattr("apps.module_link.middleware._licensed_names", _fail)
    else:
        monkeypatch.setattr("apps.module_link.middleware._licensed_names", lambda: names or ())
    monkeypatch.setattr("apps.module_link.middleware.apply_module_link_license_exempt", lambda: True)
    reached = []

    def nxt(request):
        reached.append(request.path)
        return HttpResponse("ok")

    return ModuleLinkLicenseInheritMiddleware(nxt), reached


def _body(response):
    return json.loads(response.content)


def test_middleware_skips_other_paths(rf, monkeypatch):
    mw, reached = _mw(monkeypatch, names=set())
    response = mw(rf.get("/api/v1/cmdb/api/instance/"))
    assert response.status_code == 200
    assert reached == ["/api/v1/cmdb/api/instance/"]


def test_middleware_skips_when_license_guard_inactive(rf, monkeypatch):
    mw, reached = _mw(monkeypatch, active=False, names=set())
    response = mw(rf.post("/api/v1/module_link/api/cmdb_monitor_tasks/"))
    assert response.status_code == 200
    assert reached == ["/api/v1/module_link/api/cmdb_monitor_tasks/"]


def test_middleware_passes_when_both_parents_licensed(rf, monkeypatch):
    mw, reached = _mw(monkeypatch, names={"cmdb", "monitor"})
    response = mw(rf.post("/api/v1/module_link/api/cmdb_monitor_tasks/"))
    assert response.status_code == 200
    assert reached == ["/api/v1/module_link/api/cmdb_monitor_tasks/"]


def test_middleware_denies_without_monitor(rf, monkeypatch, caplog):
    mw, reached = _mw(monkeypatch, names={"cmdb"})
    with caplog.at_level(logging.DEBUG, logger="module-link"):
        response = mw(rf.post("/api/v1/module_link/api/cmdb_monitor_tasks/"))
    assert response.status_code == 403
    assert reached == []
    body = _body(response)
    assert body["result"] is False
    assert body["message"] == LICENSE_DENIED_TEMPLATE % "monitor"
    records = [row for row in caplog.records if row.msg == DENIED]
    assert records[0].args == ("monitor",)


def test_middleware_denies_without_cmdb(rf, monkeypatch):
    mw, reached = _mw(monkeypatch, names={"monitor"})
    response = mw(rf.get("/api/v1/module_link/api/access_drafts/1/"))
    assert response.status_code == 403
    assert reached == []
    assert _body(response)["message"] == LICENSE_DENIED_TEMPLATE % "cmdb"


def test_middleware_lookup_failure_is_fail_closed(rf, monkeypatch, caplog):
    mw, reached = _mw(monkeypatch, names_error=RuntimeError(SECRET))
    with caplog.at_level(logging.DEBUG, logger="module-link"):
        response = mw(rf.post("/api/v1/module_link/api/cmdb_monitor_tasks/"))
    assert response.status_code == 403
    assert reached == []
    records = [row for row in caplog.records if row.msg == LOOKUP_FAILED]
    assert records[0].args == ("RuntimeError",)
    formatted = logging.Formatter().format(records[0])
    assert SECRET not in formatted
    assert _body(response)["message"] == LICENSE_DENIED_TEMPLATE % "cmdb"
