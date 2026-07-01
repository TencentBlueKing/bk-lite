"""opspilot-biz 切片: services/ding_talk_client.DingTalkClient 真实测试。

只 mock requests.Session（真实外部 HTTP 边界），返回真实形态的钉钉响应字典，
断言真实的 token 缓存逻辑、入参契约、结果整形与异常分支。
"""

import time

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.services.ding_talk_client import DingTalkClient


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


@pytest.fixture
def client(mocker):
    c = DingTalkClient("ak", "sk")
    # 替换真实 session（外部 HTTP 边界）
    c.session = mocker.MagicMock()
    return c


class TestGetAccessToken:
    def test_成功换取token并缓存过期时间(self, client):
        client.session.get.return_value = _FakeResponse({"errcode": 0, "access_token": "tok-1", "expires_in": 7200})
        before = time.time()
        token = client.get_access_token()
        assert token == "tok-1"
        assert client._access_token == "tok-1"
        # 过期时间 = now + (7200 - 60 缓冲)
        assert client._access_token_expire_at >= before + 7200 - 60 - 1
        # 校验真实入参契约
        _, kwargs = client.session.get.call_args
        assert kwargs["params"] == {"appkey": "ak", "appsecret": "sk"}
        assert kwargs["timeout"] == (5, 10)

    def test_命中未过期缓存不再请求(self, client):
        client._access_token = "cached"
        client._access_token_expire_at = time.time() + 1000
        token = client.get_access_token()
        assert token == "cached"
        client.session.get.assert_not_called()

    def test_缓存过期则重新请求(self, client):
        client._access_token = "old"
        client._access_token_expire_at = time.time() - 10
        client.session.get.return_value = _FakeResponse({"errcode": 0, "access_token": "new", "expires_in": 7200})
        assert client.get_access_token() == "new"
        client.session.get.assert_called_once()

    def test_缺省expires_in走默认7200(self, client):
        client.session.get.return_value = _FakeResponse({"errcode": 0, "access_token": "t"})
        now = time.time()
        client.get_access_token()
        assert client._access_token_expire_at >= now + 7200 - 60 - 1

    def test_errcode非0抛异常且不缓存(self, client):
        client.session.get.return_value = _FakeResponse({"errcode": 40001, "errmsg": "invalid"})
        with pytest.raises(Exception) as exc:
            client.get_access_token()
        assert "invalid" in str(exc.value)
        assert client._access_token is None


class TestGetUserInfo:
    def test_成功返回result(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        client.session.get.return_value = _FakeResponse({"errcode": 0, "result": {"name": "张三", "userid": "u1"}})
        result = client.get_user_info("u1")
        assert result == {"name": "张三", "userid": "u1"}
        _, kwargs = client.session.get.call_args
        assert kwargs["params"] == {"access_token": "tok", "userid": "u1"}

    def test_errcode非0抛异常(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        client.session.get.return_value = _FakeResponse({"errcode": 1, "errmsg": "no user"})
        with pytest.raises(Exception) as exc:
            client.get_user_info("x")
        assert "no user" in str(exc.value)


class TestGetUserDepartment:
    def test_扁平化父部门并去重(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        payload = {
            "errcode": 0,
            "result": {
                "parent_list": [
                    {"parent_dept_id_list": [1, 2]},
                    {"parent_dept_id_list": [2, 3]},
                ]
            },
        }
        client.session.post.return_value = _FakeResponse(payload)
        depts = client.get_user_department("u1")
        assert sorted(depts) == [1, 2, 3]
        _, kwargs = client.session.post.call_args
        assert kwargs["json"] == {"userid": "u1"}
        assert kwargs["params"] == {"access_token": "tok"}

    def test_空parent_list返回空(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        client.session.post.return_value = _FakeResponse({"errcode": 0, "result": {}})
        assert client.get_user_department("u1") == []

    def test_errcode非0抛异常(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        client.session.post.return_value = _FakeResponse({"errcode": 7, "errmsg": "boom"})
        with pytest.raises(Exception) as exc:
            client.get_user_department("u1")
        assert "boom" in str(exc.value)


class TestGetDepartmentName:
    def test_成功返回部门名(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        client.session.post.return_value = _FakeResponse({"errcode": 0, "result": {"name": "研发部"}})
        assert client.get_department_name(100) == "研发部"
        _, kwargs = client.session.post.call_args
        assert kwargs["json"] == {"dept_id": 100}

    def test_errcode非0抛异常(self, client, mocker):
        mocker.patch.object(client, "get_access_token", return_value="tok")
        client.session.post.return_value = _FakeResponse({"errcode": 9, "errmsg": "dept err"})
        with pytest.raises(Exception) as exc:
            client.get_department_name(1)
        assert "dept err" in str(exc.value)


class TestSessionLifecycle:
    def test_close_关闭session(self, client):
        client.close()
        client.session.close.assert_called_once()

    def test_context_manager_退出时关闭(self, mocker):
        c = DingTalkClient("a", "b")
        c.session = mocker.MagicMock()
        with c as ctx:
            assert ctx is c
        c.session.close.assert_called_once()
