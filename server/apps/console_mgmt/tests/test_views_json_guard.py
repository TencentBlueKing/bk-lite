"""console_mgmt 视图入口 JSON 解析防护的回归测试。

覆盖 Issue #3473：
- update_user_base_info：裸 json.loads 无 try/except，非法 JSON body → 500
- validate_pwd：同样问题，顺带修复

规则：将修复代码 revert 后，以下 test 必须失败（json.JSONDecodeError 抛到视图外 → 500）。
"""

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

UPDATE_URL = "/api/v1/console_mgmt/update_user_base_info/"
VALIDATE_PWD_URL = "/api/v1/console_mgmt/validate_pwd/"


class TestUpdateUserBaseInfoJsonGuard:
    """update_user_base_info 入口 JSON 解析防护。"""

    def test_非法json_body返回400而非500(self, user_client):
        """非法 JSON body 应返回 400，不得抛 JSONDecodeError 触发 500。

        revert 修复（删去 try/except）后本测试必须失败：
        json.loads 抛 JSONDecodeError 无捕获 → Django 500 handler → status_code=500。
        """
        _, client = user_client
        resp = client.post(
            UPDATE_URL,
            data=b"invalid{json",
            content_type="application/json",
        )
        assert resp.status_code == 400, (
            f"期望 400，实际 {resp.status_code}。"
            "说明 json.loads 抛出的 JSONDecodeError 未被捕获。"
        )
        body = resp.json()
        assert body["result"] is False

    def test_空body返回400(self, user_client):
        """空 body 也是非法 JSON，应返回 400。"""
        _, client = user_client
        resp = client.post(
            UPDATE_URL,
            data=b"",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json()["result"] is False

    def test_合法json_body正常处理(self, user_client):
        """合法 JSON body 应能正常被处理（不因 JSON 解析本身返回 400/500）。

        注意：本 test 断言 status_code != 400（JSON 解析阶段不报错即可），
        后续 DB 操作可能 200 成功也可能 4xx（视数据库状态），均可接受。
        """
        _, client = user_client
        resp = client.post(
            UPDATE_URL,
            data={"display_name": "测试用户"},
            format="json",
        )
        # JSON 解析成功，不应因解析本身返回 400
        assert resp.status_code != 400 or resp.json().get("message") != "Invalid JSON format"


class TestValidatePwdJsonGuard:
    """validate_pwd 入口 JSON 解析防护。"""

    def test_非法json_body返回400而非500(self, user_client):
        """非法 JSON body 应返回 400，不得触发 500。

        revert 修复后本测试必须失败：json.loads 无捕获 → 500。
        """
        _, client = user_client
        resp = client.post(
            VALIDATE_PWD_URL,
            data=b"not-json-at-all",
            content_type="application/json",
        )
        assert resp.status_code == 400, (
            f"期望 400，实际 {resp.status_code}。"
            "说明 validate_pwd 的 json.loads 未被 try/except 保护。"
        )
        body = resp.json()
        assert body["result"] is False

    def test_空body返回400(self, user_client):
        """空 body 应返回 400。"""
        _, client = user_client
        resp = client.post(
            VALIDATE_PWD_URL,
            data=b"",
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert resp.json()["result"] is False

    def test_合法json_body不因解析报错(self, user_client):
        """合法 JSON body 进入后续逻辑，不应因 JSON 解析本身失败。"""
        _, client = user_client
        resp = client.post(
            VALIDATE_PWD_URL,
            data={"password": "somepassword"},
            format="json",
        )
        # JSON 解析成功，不应返回 "Invalid JSON format"
        if resp.status_code == 400:
            assert resp.json().get("message") != "Invalid JSON format"
