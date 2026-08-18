"""渲染器契约测试（unit，无 DB / 无 NATS）。

覆盖 spec.md「验证」节：四类坏条目跳过、未知字段前向兼容、
gateway_versions 过滤、fail-closed 各分支、Traefik 配置结构。
"""

import pytest

from apps.core.openapi import renderer

pytestmark = pytest.mark.unit

GOOD = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "strip_prefix": True,
    "paths": ["/tickets/*"],
    "auth_mode": "trusted-header",
    "shared_secret_ref": "env:TEST_ITSM_SECRET",
    "required_roles": [],
    "rate_limit": {"average": 50, "burst": 100},
    "enabled": True,
}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc,.internal")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")
    monkeypatch.setenv("TEST_ITSM_SECRET", "s3cret")
    monkeypatch.setenv("TEST_ITSM_TOKEN", "tok-abc")


def render_one(entry, name="itsm", internal=()):
    return renderer.render_traefik_config({name: entry}, internal)


def test_good_entry_full_structure(env):
    config, report = render_one(dict(GOOD))
    assert report["rendered"] == ["itsm"]
    http = config["http"]

    router = http["routers"]["openapi-v1-itsm"]
    assert router["rule"] == "PathPrefix(`/openapi/v1/itsm/tickets`)"
    assert router["service"] == "openapi-itsm"
    assert router["middlewares"][0] == "openapi-clear-headers"
    assert "openapi-itsm-ratelimit" in router["middlewares"]
    assert "openapi-auth" in router["middlewares"]
    assert router["middlewares"][-1] == "openapi-itsm-strip-v1"

    clear = http["middlewares"]["openapi-clear-headers"]["headers"]["customRequestHeaders"]
    assert set(clear) == {"X-BK-User", "X-BK-Team", "X-BK-Gateway-Auth"}
    assert all(value == "" for value in clear.values())

    auth = http["middlewares"]["openapi-auth"]["forwardAuth"]
    assert auth["address"].endswith("/_auth")
    assert auth["authResponseHeaders"] == ["X-BK-User", "X-BK-Team", "X-On-Behalf-Of"]

    inject = http["middlewares"]["openapi-itsm-inject"]["headers"]["customRequestHeaders"]
    assert inject == {"X-BK-Gateway-Auth": "s3cret"}

    assert http["middlewares"]["openapi-itsm-strip-v1"]["stripPrefix"]["prefixes"] == [
        "/openapi/v1/itsm"
    ]
    assert http["services"]["openapi-itsm"]["loadBalancer"]["servers"] == [
        {"url": "http://itsm-svc:8000"}
    ]


def test_service_token_mode_injects_authorization(env):
    entry = dict(GOOD, auth_mode="service-token", token_ref="env:TEST_ITSM_TOKEN")
    entry.pop("shared_secret_ref")
    config, report = render_one(entry)
    assert report["rendered"] == ["itsm"]
    inject = config["http"]["middlewares"]["openapi-itsm-inject"]["headers"][
        "customRequestHeaders"
    ]
    assert inject == {"Authorization": "Bearer tok-abc"}


def test_no_paths_renders_whole_prefix(env):
    entry = dict(GOOD)
    entry.pop("paths")
    config, _ = render_one(entry)
    assert (
        config["http"]["routers"]["openapi-v1-itsm"]["rule"]
        == "PathPrefix(`/openapi/v1/itsm`)"
    )


def test_unknown_fields_ignored(env):
    entry = dict(GOOD, future_field={"x": 1})
    _, report = render_one(entry)
    assert report["rendered"] == ["itsm"]


@pytest.mark.parametrize(
    "mutation, reason_part",
    [
        ({"schema_version": 2}, "schema_version"),
        ({"type": "grpc"}, "type"),
        ({"auth_mode": "magic"}, "auth_mode"),
        ({"base_url": "http://evil.example.com"}, "allowlist"),
        ({"base_url": "ftp://itsm-svc"}, "base_url"),
        ({"shared_secret_ref": "env:NOT_SET_VAR"}, "shared_secret_ref"),
        ({"paths": "not-a-list"}, "paths"),
        ({"rate_limit": {"average": "50"}}, "rate_limit"),
        ({"required_roles": "admin"}, "required_roles"),
        ({"gateway_versions": ["v9"]}, "gateway version"),
    ],
)
def test_bad_entries_skipped(env, mutation, reason_part):
    entry = dict(GOOD, **mutation)
    config, report = render_one(entry)
    assert report["rendered"] == []
    assert reason_part in report["skipped"]["itsm"]
    assert config["http"]["routers"] == {}


def test_disabled_entry_skipped_quietly(env):
    _, report = render_one(dict(GOOD, enabled=False))
    assert report["skipped"]["itsm"] == "disabled"


def test_non_dict_entry_skipped(env):
    _, report = render_one("garbage")
    assert "not an object" in report["skipped"]["itsm"]


def test_internal_name_conflict_skipped(env):
    _, report = render_one(dict(GOOD), name="cmdb", internal=("cmdb",))
    assert "internal" in report["skipped"]["cmdb"]


def test_reserved_name_rejected(env):
    _, report = render_one(dict(GOOD), name="_me")
    assert "invalid service name" in report["skipped"]["_me"]


@pytest.mark.parametrize(
    "host, allowed",
    [
        ("itsm-svc", True),           # 精确匹配
        ("a.itsm-svc", True),         # 点边界后缀
        ("evil-itsm-svc", False),     # 同尾但非点边界，必须拒绝
        ("xitsm-svc", False),
        ("svc.internal", True),       # allowlist 中的 .internal 后缀
        ("evilinternal", False),
    ],
)
def test_base_url_allowlist_requires_dot_boundary(env, host, allowed):
    entry = dict(GOOD, base_url=f"http://{host}:8000")
    _, report = render_one(entry)
    if allowed:
        assert report["rendered"] == ["itsm"], f"{host} 应被放行"
    else:
        assert "allowlist" in report["skipped"]["itsm"], f"{host} 应被拒绝"


def test_missing_allowlist_rejects_everything(env, monkeypatch):
    monkeypatch.delenv("OPENAPI_BASEURL_ALLOWLIST")
    _, report = render_one(dict(GOOD))
    assert "allowlist" in report["skipped"]["itsm"]


def test_missing_auth_address_renders_nothing(env, monkeypatch):
    monkeypatch.delenv("OPENAPI_AUTH_ADDRESS")
    config, report = render_one(dict(GOOD))
    assert config["http"]["routers"] == {}
    assert report["skipped"]["itsm"] == "auth address unconfigured"


def test_gateway_versions_default_active(env):
    entry = dict(GOOD)
    entry.pop("paths")
    entry["gateway_versions"] = ["v1", "v9"]
    config, report = render_one(entry)
    assert report["rendered"] == ["itsm"]
    assert set(config["http"]["routers"]) == {"openapi-v1-itsm"}
