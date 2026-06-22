"""rpc.system_mgmt.SystemMgmt 转发契约测试。

规格：每个方法把固定的 method_name 与参数原样转发给底层传输（client.run）。
这是 RPC 调用面的契约，能抓到方法名/参数名拼写回归。
做法：替换传输 seam（self.client）为记录器，不 mock 被测的转发逻辑本身。
"""

import pytest

from apps.rpc.system_mgmt import SystemMgmt

pytestmark = pytest.mark.unit


class _Recorder:
    def __init__(self):
        self.calls = []

    def run(self, method_name, *args, **kwargs):
        self.calls.append((method_name, args, kwargs))
        return {"ok": True}


@pytest.fixture
def client():
    c = SystemMgmt()
    c.client = _Recorder()
    return c


def test_login_转发方法名与参数(client):
    result = client.login("alice", "pw")
    assert result == {"ok": True}
    assert client.client.calls == [("login", (), {"username": "alice", "password": "pw"})]


def test_verify_token_转发(client):
    client.verify_token("tok")
    assert client.client.calls[0] == ("verify_token", (), {"token": "tok"})


def test_reset_pwd_转发全部具名参数(client):
    client.reset_pwd("alice", "domain.com", "newpw", caller_token="tok123")
    assert client.client.calls[0] == (
        "reset_pwd",
        (),
        {"username": "alice", "domain": "domain.com", "password": "newpw", "caller_token": "tok123"},
    )


def test_reset_pwd_缺省caller_token时转发空字符串(client):
    client.reset_pwd("alice", "domain.com", "newpw")
    assert client.client.calls[0] == (
        "reset_pwd",
        (),
        {"username": "alice", "domain": "domain.com", "password": "newpw", "caller_token": ""},
    )


def test_get_user_menus_转发(client):
    client.get_user_menus("cid", ["admin"], "alice", True)
    assert client.client.calls[0] == (
        "get_user_menus",
        (),
        {"client_id": "cid", "roles": ["admin"], "username": "alice", "is_superuser": True},
    )


def test_get_client_detail_位置参数转发(client):
    # 该方法以位置参数转发 client_id
    client.get_client_detail("cid")
    assert client.client.calls[0] == ("get_client_detail", ("cid",), {})


def test_verify_otp_login_默认_client_ip(client):
    client.verify_otp_login("chal", "123456")
    assert client.client.calls[0] == (
        "verify_otp_login",
        (),
        {"challenge_id": "chal", "otp_code": "123456", "client_ip": ""},
    )
