"""网关端到端契约测试（integration，需 DB）。

覆盖 spec.md「验证」节：认证、双租户隔离、伪造身份丢弃、锚点注入、
envelope 契约、_me 结构。
"""

import time

import jwt as pyjwt
import pytest

from apps.core.openapi.registry import default_registry
from apps.core.openapi.testing import bearer, create_api_tenant

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

PATCH_URL = "/openapi/v1/patch-mgmt/module-data"
CMDB_URL = "/openapi/v1/cmdb/module-data"
ME_URL = "/openapi/v1/_me"

TEST_SECRET = "openapi-test-secret-key"


@pytest.fixture
def jwt_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")


def make_jwt(user):
    return pyjwt.encode(
        {"user_id": user.id, "login_time": time.time()},
        TEST_SECRET,
        algorithm="HS256",
    )


def make_jwt_tenant(team_id):
    """JWT 登录态用户体系为 system_mgmt.User（_verify_token 按其 id 查询）。"""
    import uuid

    from apps.system_mgmt.models import Group
    from apps.system_mgmt.models import User as SystemUser

    name = f"jwtuser-{uuid.uuid4().hex[:8]}"
    user = SystemUser.objects.create(
        username=name,
        display_name=name,
        email=f"{name}@example.com",
        password="x",
        domain="domain.com",
        group_list=[team_id],
    )
    Group.objects.get_or_create(id=team_id, defaults={"name": f"team-{team_id}"})
    return user


# ---------- 认证与路径 ----------


def test_missing_credential_401(client):
    resp = client.get(PATCH_URL, {"module": "patch_target", "group_id": 1})
    assert resp.status_code == 401
    body = resp.json()
    assert body["result"] is False and body["code"] == "AUTH_INVALID"


def test_invalid_token_401(client):
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 1},
        HTTP_AUTHORIZATION="Bearer " + "f" * 64,
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID"


def test_expired_personal_token_401(client):
    from datetime import timedelta

    from django.utils import timezone

    from apps.base.models.user import UserAPISecret

    _, token = create_api_tenant(1)
    UserAPISecret.objects.filter(api_secret=token).update(
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID"


def test_unknown_path_404(client):
    _, token = create_api_tenant(1)
    resp = client.get("/openapi/v1/patch-mgmt/nonexistent", **bearer(token))
    assert resp.status_code == 404
    assert resp.json()["code"] == "NOT_FOUND"


def test_unregistered_nats_function_not_exposed(client):
    """未打 @openapi_expose 的 nats 函数不可经网关调用。"""
    _, token = create_api_tenant(1)
    resp = client.get("/openapi/v1/patch-mgmt/module-list", **bearer(token))
    assert resp.status_code == 404


# ---------- envelope 与 schema ----------


def test_unknown_field_rejected(client):
    _, token = create_api_tenant(1)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 1, "hack": "1"},
        **bearer(token),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "SCHEMA_INVALID"


def test_client_identity_field_rejected_by_schema(client):
    """全集式端点的 serializer 未声明 team：客户端传入即为未知字段（身份字段无法混入）。"""
    _, token = create_api_tenant(1)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 1, "team": "1"},
        **bearer(token),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "SCHEMA_INVALID"


def test_page_size_clamped_not_rejected(client):
    _, token = create_api_tenant(1)
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 1, "page_size": "99999"},
        **bearer(token),
    )
    assert resp.status_code == 200
    assert resp.json()["result"] is True


# ---------- 双租户隔离（patch_mgmt 真实数据） ----------


@pytest.fixture
def patch_targets():
    from apps.patch_mgmt.models import PatchTarget

    a = PatchTarget.objects.create(name="host-a", ip="10.0.0.1", team=[1])
    b = PatchTarget.objects.create(name="host-b", ip="10.0.0.2", team=[2])
    return a, b


def test_tenant_can_read_own_org(client, patch_targets):
    _, token = create_api_tenant(1)
    resp = client.get(
        PATCH_URL, {"module": "patch_target", "group_id": 1}, **bearer(token)
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["count"] == 1
    assert data["items"][0]["name"] == "host-a"


def test_tenant_cannot_read_other_org(client, patch_targets):
    """组织 2 的令牌请求组织 1 的数据：注入集合不含组织 1，函数拒绝。

    越权按冻结清单映射为 403 TEAM_OUT_OF_SCOPE，不与普通业务拒绝(400)混淆。
    """
    _, token = create_api_tenant(2)
    resp = client.get(
        PATCH_URL, {"module": "patch_target", "group_id": 1}, **bearer(token)
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["result"] is False
    assert body["code"] == "TEAM_OUT_OF_SCOPE"


def test_non_scope_business_error_stays_400(client, patch_targets):
    """非越权类软错误仍映射为 400 BUSINESS_REJECTED（两者不得混淆）。"""
    _, token = create_api_tenant(1)
    endpoint = default_registry.find("patch-mgmt", "module-data", "GET")
    original = endpoint.func
    try:
        endpoint.func = lambda **kw: {"result": False, "message": "参数组合不支持"}
        resp = client.get(
            PATCH_URL, {"module": "patch_target", "group_id": 1}, **bearer(token)
        )
    finally:
        endpoint.func = original
    assert resp.status_code == 400
    assert resp.json()["code"] == "BUSINESS_REJECTED"


def test_forged_identity_headers_ignored(client, patch_targets):
    """伪造 X-BK-* 与 acting 头对身份推导无效：身份永远来自凭据（红线 2 纵深防御）。"""
    from apps.core.openapi.tests.test_system_token_auth import _create_acting_user

    _, token = create_api_tenant(2)
    other = _create_acting_user(1, username="intruder")
    resp = client.get(
        PATCH_URL,
        {"module": "patch_target", "group_id": 1},
        HTTP_X_BK_USER="admin@domain.com",
        HTTP_X_BK_TEAM="1",
        HTTP_X_BKLITE_ACTING_USER=f"{other.username}@{other.domain}",
        HTTP_X_BKLITE_ACTING_TEAM="1",
        **bearer(token),
    )
    # 伪造头未生效：身份仍取自凭据（组织 2），越权访问组织 1 被拒
    assert resp.status_code == 403
    assert resp.json()["code"] == "TEAM_OUT_OF_SCOPE"


# ---------- 锚点式注入（cmdb，捕获 kwargs 验证注入行为） ----------


@pytest.fixture
def captured_cmdb(monkeypatch):
    endpoint = default_registry.find("cmdb", "module-data", "GET")
    assert endpoint is not None
    captured = {}

    def fake(**kwargs):
        captured.update(kwargs)
        return {"count": 0, "items": []}

    monkeypatch.setattr(endpoint, "func", fake)
    return captured


def test_api_token_anchor_forced_to_bound_team(client, captured_cmdb):
    """API 令牌为单组织收窄凭据：客户端锚点被强制覆盖为绑定组织。"""
    _, token = create_api_tenant(7)
    resp = client.get(
        CMDB_URL,
        {"module": "instances", "child_module": "host", "group_id": 7, "team": "999"},
        **bearer(token),
    )
    assert resp.status_code == 200
    assert captured_cmdb["user_info"]["team"] == 7
    assert "team" not in captured_cmdb  # 锚点已被抽入 user_info，不作为顶层参数


def test_jwt_anchor_passthrough(client, captured_cmdb, jwt_env):
    user = make_jwt_tenant(5)
    resp = client.get(
        CMDB_URL,
        {"module": "instances", "child_module": "host", "group_id": 5, "team": "5"},
        HTTP_AUTHORIZATION=f"Bearer {make_jwt(user)}",
    )
    assert resp.status_code == 200
    assert captured_cmdb["user_info"]["user"] == user.username
    assert captured_cmdb["user_info"]["team"] == 5


def test_jwt_ignores_acting_headers(client, captured_cmdb, jwt_env):
    from apps.core.openapi.tests.test_system_token_auth import _create_acting_user

    user = make_jwt_tenant(5)
    other = _create_acting_user(9, username="jwt-intruder")
    resp = client.get(
        CMDB_URL,
        {"module": "instances", "child_module": "host", "group_id": 5, "team": "5"},
        HTTP_AUTHORIZATION=f"Bearer {make_jwt(user)}",
        HTTP_X_BKLITE_ACTING_USER=f"{other.username}@{other.domain}",
        HTTP_X_BKLITE_ACTING_TEAM="9",
    )
    assert resp.status_code == 200
    assert captured_cmdb["user_info"]["user"] == user.username
    assert captured_cmdb["user_info"]["team"] == 5
    assert captured_cmdb["user_info"]["user"] != other.username


def test_jwt_missing_anchor_rejected(client, captured_cmdb, jwt_env):
    user = make_jwt_tenant(5)
    resp = client.get(
        CMDB_URL,
        {"module": "instances", "child_module": "host", "group_id": 5},
        HTTP_AUTHORIZATION=f"Bearer {make_jwt(user)}",
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "SCHEMA_INVALID"


# ---------- _me ----------


def test_me_api_token(client):
    _, token = create_api_tenant(3)
    resp = client.get(ME_URL, **bearer(token))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["credential_type"] == "api_token"
    assert [g["id"] for g in data["groups"]] == [3]
    assert set(data["groups"][0]) == {"id", "name"}
    assert data["anchor_scopes"][0]["anchor"] == 3
    assert 3 in data["anchor_scopes"][0]["cascaded_group_ids"]
    # anchor_scopes 必须与实际授权同源：不得包含用户无权限的组织（超报）。
    # 该用户仅授权组织 3 且 3 无子组织，故级联集合恰为 {3}
    assert data["anchor_scopes"][0]["cascaded_group_ids"] == [3]
    service_names = {s["name"] for s in data["services"]}
    assert {"patch-mgmt", "cmdb"} <= service_names
    assert all(s["kind"] == "internal" for s in data["services"])
    assert data.get("caller_system") in (None, "")
    assert "token_id" not in data
    assert "token_name" not in data


def test_jwt_access_log_has_no_token_identity(client, caplog, jwt_env):
    from apps.core.openapi.tests.test_system_token_auth import _AUDIT_TEMPLATE, _access_log

    user = make_jwt_tenant(5)
    token = make_jwt(user)
    with caplog.at_level("INFO", logger="openapi"):
        resp = client.get(ME_URL, HTTP_AUTHORIZATION=f"Bearer {token}")
    assert resp.status_code == 200
    rec = _access_log(caplog)
    assert rec.msg == _AUDIT_TEMPLATE
    assert rec.args[0] == user.username
    assert rec.args[2] == "jwt"
    assert rec.args[3] == "-"
    assert rec.args[4] == "-"
    assert rec.args[6] == "-"
    rendered = rec.getMessage()
    assert "credential=jwt" in rendered
    assert "token_id=-" in rendered
    assert "token_name=-" in rendered
    assert "caller=-" in rendered
    assert token not in rendered
    assert token not in caplog.text


def test_me_requires_credential(client):
    resp = client.get(ME_URL)
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_INVALID"
