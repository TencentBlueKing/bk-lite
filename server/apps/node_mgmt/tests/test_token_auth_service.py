"""Sidecar Token 认证：解析 Authorization、节点不匹配、签名错误。"""
import base64
from types import SimpleNamespace

import pytest

from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.node_mgmt.utils import token_auth
from config.components.drf import AUTH_TOKEN_HEADER_NAME

pytestmark = pytest.mark.unit


def test_get_client_token_parses_basic_and_rejects_bad_header():
    assert token_auth.get_client_token(SimpleNamespace(META={})) is None

    raw = base64.b64encode(b"node-token:ignored-password").decode()
    request = SimpleNamespace(META={AUTH_TOKEN_HEADER_NAME: f"Basic {raw}"})
    assert token_auth.get_client_token(request) == "node-token"

    bad = SimpleNamespace(META={AUTH_TOKEN_HEADER_NAME: "Basic not-base64!!!"})
    assert token_auth.get_client_token(bad) is None


def test_check_token_auth_rejects_missing_node_token_and_mismatch(monkeypatch):
    request = SimpleNamespace(META={})
    with pytest.raises(UnauthorizedException, match="节点ID为空"):
        token_auth.check_token_auth("", request)

    monkeypatch.setattr(token_auth, "get_client_token", lambda req: None)
    with pytest.raises(UnauthorizedException, match="未获取到有效的认证Token"):
        token_auth.check_token_auth("n1", request)

    monkeypatch.setattr(token_auth, "get_client_token", lambda req: "tok")
    monkeypatch.setattr(token_auth, "decode_token", lambda token, node_id="": {"node_id": "other"})
    with pytest.raises(UnauthorizedException, match="节点ID与Token不匹配"):
        token_auth.check_token_auth("n1", request)

    monkeypatch.setattr(token_auth, "decode_token", lambda token, node_id="": {"node_id": "n1"})
    monkeypatch.setattr(token_auth, "get_node_cache_token", lambda node_id: None)
    with pytest.raises(UnauthorizedException, match="服务端无此节点"):
        token_auth.check_token_auth("n1", request)

    monkeypatch.setattr(token_auth, "get_node_cache_token", lambda node_id: "different")
    with pytest.raises(UnauthorizedException, match="与服务端记录不一致"):
        token_auth.check_token_auth("n1", request)


def test_check_token_auth_accepts_matching_token(monkeypatch):
    monkeypatch.setattr(token_auth, "get_client_token", lambda req: "tok")
    monkeypatch.setattr(token_auth, "decode_token", lambda token, node_id="": {"node_id": "n1"})
    monkeypatch.setattr(token_auth, "get_node_cache_token", lambda node_id: "tok")
    token_auth.check_token_auth("n1", SimpleNamespace(META={}))


def test_decode_token_rejects_tampered_signature_and_short_payload():
    with pytest.raises(BaseAppException, match="格式错误"):
        token_auth.decode_token(base64.urlsafe_b64encode(b"short").decode())

    good = token_auth.hmac.new(token_auth.SECRET_KEY.encode(), b'{"node_id":"n"}', token_auth.hashlib.sha256).digest()
    tampered = base64.urlsafe_b64encode(b"\x00" * 32 + b"." + b'{"node_id":"n"}').decode()
    with pytest.raises(BaseAppException, match="无效的 token"):
        token_auth.decode_token(tampered)
    valid = base64.urlsafe_b64encode(good + b"." + b'{"node_id":"n"}').decode()
    assert token_auth.decode_token(valid) == {"node_id": "n"}
