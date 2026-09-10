"""密钥引用解析（credential: 方案）测试，需 DB。

覆盖：credential: 引用渲染成功、不存在 / 已禁用 / 字段歧义 / 未知字段 /
DB 异常时 fail-closed、env: 行为不变、读侧不在请求路径重新解引用。
"""

from types import SimpleNamespace

import pytest

from apps.core.openapi import renderer
from apps.system_mgmt.models.credential import CredentialType
from apps.system_mgmt.models.user import Group
from apps.system_mgmt.services.credential_service import (
    CredentialServiceError,
    create_credential,
    resolve_secret_field,
    seed_builtin_types,
    set_disabled,
)

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

ENTRY = {
    "schema_version": 1,
    "type": "http",
    "base_url": "http://itsm-svc:8000",
    "auth_mode": "trusted-header",
    "required_roles": [],
    "enabled": True,
}


def _actor(group_id):
    return SimpleNamespace(
        current_team=group_id,
        group_list=[group_id],
        is_superuser=True,
        username="gw-test",
        domain="domain.com",
    )


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("OPENAPI_BASEURL_ALLOWLIST", "itsm-svc")
    monkeypatch.setenv("OPENAPI_AUTH_ADDRESS", "http://server:8000/openapi/v1/_auth")


@pytest.fixture
def owner():
    seed_builtin_types()
    return Group.objects.create(name="gw-owner", parent_id=0, is_delete=False)


def _gateway_secret(owner, value="s3cret-from-db", name="itsm"):
    return create_credential(
        {"name": name, "type": "gateway_secret", "group_id": owner.id, "fields": {"secret": value}},
        _actor(owner.id),
    )


def _render(entry):
    return renderer.render_traefik_config({"itsm": entry}, ())


def test_credential_ref_renders_shared_secret(env, owner):
    cred = _gateway_secret(owner)
    entry = dict(ENTRY, shared_secret_ref=f"credential:{cred.credential_id}")
    config, report = _render(entry)
    assert report["rendered"] == ["itsm"]
    inject = config["http"]["middlewares"]["openapi-itsm-inject"]["headers"]["customRequestHeaders"]
    assert inject["X-BK-Gateway-Auth"] == "s3cret-from-db"
    assert inject["Authorization"] == ""


def test_credential_ref_service_token_mode(env, owner):
    cred = _gateway_secret(owner, value="tok-from-db")
    entry = dict(ENTRY, auth_mode="service-token", token_ref=f"credential:{cred.credential_id}")
    config, report = _render(entry)
    assert report["rendered"] == ["itsm"]
    inject = config["http"]["middlewares"]["openapi-itsm-inject"]["headers"]["customRequestHeaders"]
    assert inject["Authorization"] == "Bearer tok-from-db"


def test_explicit_field_selects_secret_on_multi_secret_type(env, owner):
    typ = CredentialType.objects.create(
        key="two-secrets",
        name="two",
        categories=["other"],
        fields=[
            {"id": "a", "kind": "secret", "required": True},
            {"id": "b", "kind": "secret", "required": True},
        ],
    )
    cred = create_credential(
        {"name": "x", "type": typ.key, "group_id": owner.id, "fields": {"a": "AAA", "b": "BBB"}},
        _actor(owner.id),
    )
    assert resolve_secret_field(cred.credential_id, "b") == "BBB"
    with pytest.raises(CredentialServiceError) as exc:
        resolve_secret_field(cred.credential_id)
    assert exc.value.code == "ambiguous_field"
    with pytest.raises(CredentialServiceError) as exc:
        resolve_secret_field(cred.credential_id, "nope")
    assert exc.value.code == "unknown_field"

    _, report = _render(dict(ENTRY, shared_secret_ref=f"credential:{cred.credential_id}"))
    assert report["skipped"]["itsm"] == "shared_secret_ref unresolvable (credential ambiguous_field)"
    config, report = _render(dict(ENTRY, shared_secret_ref=f"credential:{cred.credential_id}#b"))
    assert report["rendered"] == ["itsm"]
    inject = config["http"]["middlewares"]["openapi-itsm-inject"]["headers"]["customRequestHeaders"]
    assert inject["X-BK-Gateway-Auth"] == "BBB"


@pytest.mark.parametrize(
    "ref, reason",
    [
        ("credential:crd-gateway_secret-missing", "shared_secret_ref unresolvable (credential not_found)"),
        ("credential:", "shared_secret_ref unresolvable (empty credential id)"),
        ("vault:whatever", "shared_secret_ref unresolvable (unknown ref scheme)"),
        ("plain-text-secret", "shared_secret_ref unresolvable (unknown ref scheme)"),
        ("env:GW_TEST_UNSET_VAR", "shared_secret_ref unresolvable (env var unset)"),
    ],
)
def test_unresolvable_refs_skip_entry(env, owner, ref, reason):
    config, report = _render(dict(ENTRY, shared_secret_ref=ref))
    assert report["rendered"] == []
    assert report["skipped"]["itsm"] == reason
    assert "routers" not in config["http"]


def test_disabled_credential_is_fail_closed(env, owner):
    cred = _gateway_secret(owner)
    set_disabled(cred.credential_id, True, actor=_actor(owner.id))
    _, report = _render(dict(ENTRY, shared_secret_ref=f"credential:{cred.credential_id}"))
    assert report["skipped"]["itsm"] == "shared_secret_ref unresolvable (credential disabled)"


def test_db_failure_is_unresolvable_not_crash(env, owner, monkeypatch, caplog):
    cred = _gateway_secret(owner)

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("apps.system_mgmt.services.credential_service.resolve_secret_field", boom)
    with caplog.at_level("WARNING", logger="openapi"):
        _, report = _render(dict(ENTRY, shared_secret_ref=f"credential:{cred.credential_id}"))
    assert report["skipped"]["itsm"] == "shared_secret_ref unresolvable (credential lookup failed)"
    logged = [r for r in caplog.records if "failed_stage=credential_lookup" in r.getMessage()]
    assert logged and "error_type=RuntimeError" in logged[0].getMessage()
    assert "s3cret-from-db" not in caplog.text and "db down" not in caplog.text


def test_env_ref_unchanged(env, owner, monkeypatch):
    monkeypatch.setenv("GW_TEST_SECRET", "from-env")
    config, report = _render(dict(ENTRY, shared_secret_ref="env:GW_TEST_SECRET"))
    assert report["rendered"] == ["itsm"]
    inject = config["http"]["middlewares"]["openapi-itsm-inject"]["headers"]["customRequestHeaders"]
    assert inject["X-BK-Gateway-Auth"] == "from-env"


def test_read_side_uses_rendered_snapshot_without_reresolving(env, owner, monkeypatch):
    cred = _gateway_secret(owner)
    entries = {"itsm": dict(ENTRY, shared_secret_ref=f"credential:{cred.credential_id}")}
    monkeypatch.setattr(renderer, "fetch_entries", lambda: entries)
    renderer.refresh_snapshot()

    calls = []

    def counting(*args, **kwargs):
        calls.append(args)
        raise AssertionError("read path must not resolve secrets")

    monkeypatch.setattr("apps.system_mgmt.services.credential_service.resolve_secret_field", counting)
    monkeypatch.setenv("OPENAPI_REGISTRY_CACHE_TTL", "3600")
    entry = renderer.get_external_entry("itsm")
    assert entry is not None
    assert entry["secrets"]["shared_secret"] == "s3cret-from-db"
    assert renderer.get_external_entry("nope") is None
    assert calls == []
