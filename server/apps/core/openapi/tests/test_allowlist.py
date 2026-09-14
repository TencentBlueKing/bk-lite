"""base_url 允许清单的 DB 存储与 fail-closed 行为，需 DB。

覆盖：env 与 DB 取并集、DB 侧增删幂等、非法主机拒绝、点边界匹配、
DB 不可达时沿用快照而非下发收缩后的清单、一次渲染只查一次库。
"""

import pytest

from apps.core.openapi import allowlist as allowlist_mod
from apps.core.openapi import renderer
from apps.core.openapi.allowlist import SETTINGS_KEY, AllowlistError, add_host, db_hosts, load_allowlist, normalize_host, remove_host
from apps.system_mgmt.models.system_settings import SystemSettings

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ENTRY = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "auth_mode": "trusted-header",
    "shared_secret_ref": "env:TEST_GW_SECRET",
    "required_roles": [],
    "enabled": True,
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_GW_SECRET", "s3cret")
    monkeypatch.delenv("OPENAPI_BASEURL_ALLOWLIST", raising=False)


def test_db_host_allows_entry_without_env(env):
    add_host("itsm-svc")
    config, report = renderer.render_traefik_config({"itsm": ENTRY}, ())
    assert report["rendered"] == ["itsm"]
    assert "openapi-v1-itsm" in config["http"]["routers"]


def test_env_and_db_are_merged(env, monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "legacy-svc")
    add_host("itsm-svc")
    hosts, db_ok = load_allowlist()
    assert db_ok is True
    assert set(hosts) == {"legacy-svc", "itsm-svc"}


def test_empty_allowlist_rejects_everything(env):
    _, report = renderer.render_traefik_config({"itsm": ENTRY}, ())
    assert report["rendered"] == []
    assert report["skipped"]["itsm"] == "base_url not in allowlist"


def test_add_and_remove_are_idempotent(env):
    add_host("itsm-svc")
    assert add_host("itsm-svc") == ["itsm-svc"]
    assert remove_host("itsm-svc") == []
    assert remove_host("itsm-svc") == []


def test_host_is_normalized_and_validated(env):
    assert add_host("  ITSM-SVC  ") == ["itsm-svc"]
    assert normalize_host(".internal") == ".internal"
    for bad in ["", "has space", "bad_underscore", "http://itsm-svc", None]:
        with pytest.raises(AllowlistError):
            normalize_host(bad)


@pytest.mark.parametrize(
    "listed, host, allowed",
    [
        ("itsm-svc", "itsm-svc", True),
        ("itsm-svc", "evil-itsm-svc", False),
        (".internal", "svc.internal", True),
        (".internal", "notinternal", False),
        ("*", "anything.example.com", True),
    ],
)
def test_suffix_match_respects_dot_boundary(env, listed, host, allowed):
    add_host(listed)
    entry = dict(ENTRY, base_url=f"http://{host}:8000")
    _, report = renderer.render_traefik_config({"itsm": entry}, ())
    assert (report["rendered"] == ["itsm"]) is allowed


def test_db_failure_keeps_previous_snapshot(env, monkeypatch):
    add_host("itsm-svc")
    monkeypatch.setattr(renderer, "fetch_entries", lambda: {"itsm": ENTRY})
    good = renderer.refresh_snapshot()
    assert "openapi-v1-itsm" in good["http"]["routers"]

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(allowlist_mod, "db_hosts", boom)
    monkeypatch.setenv("OPENAPI_REGISTRY_CACHE_TTL", "0")
    again = renderer.refresh_snapshot()
    assert again == good, "DB 不可达时必须沿用快照，不得下发收缩后的清单"


def test_db_failure_on_cold_start_falls_back_to_env(env, monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc")

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(allowlist_mod, "db_hosts", boom)
    hosts, db_ok = load_allowlist()
    assert db_ok is False
    assert hosts == ("itsm-svc",)
    monkeypatch.setattr(renderer, "fetch_entries", lambda: {"itsm": ENTRY})
    config = renderer.refresh_snapshot()
    assert "openapi-v1-itsm" in config["http"]["routers"]


def test_render_loads_allowlist_once_regardless_of_entry_count(env, monkeypatch):
    add_host("itsm-svc")
    calls = []
    original = allowlist_mod.db_hosts
    monkeypatch.setattr(allowlist_mod, "db_hosts", lambda: (calls.append(1), original())[1])
    entries = {f"svc{i}": ENTRY for i in range(5)}
    renderer.render_traefik_config(entries, ())
    assert len(calls) == 1


def test_stored_value_is_comma_separated(env):
    add_host("a-svc")
    add_host("b-svc")
    assert SystemSettings.objects.get(key=SETTINGS_KEY).value == "a-svc,b-svc"
    assert db_hosts() == ["a-svc", "b-svc"]


def test_management_command_roundtrip(env):
    from io import StringIO

    from django.core.management import call_command
    from django.core.management.base import CommandError

    def run(*args):
        out = StringIO()
        call_command("openapi_allowlist", *args, stdout=out)
        return out.getvalue()

    assert "清单为空" in run("list")
    assert "已加入 itsm-svc" in run("add", "itsm-svc")
    assert "itsm-svc" in run("list")
    assert "已移除 itsm-svc" in run("remove", "itsm-svc")
    with pytest.raises(CommandError):
        run("add", "bad host")
    with pytest.raises(CommandError):
        run("add")
