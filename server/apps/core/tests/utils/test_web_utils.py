"""core.utils.web_utils.WebUtils 纯单元测试。

规格：统一响应封装。成功响应 result=True/HTTP200；错误响应 result=False/可定制状态码；
401/403 返回对应状态；文件响应带 attachment 头。这些是全站接口契约的基础，必须稳定。
"""

import json

import pytest
from rest_framework import status

from apps.core.utils.web_utils import WebUtils

pytestmark = pytest.mark.unit


def _body(resp):
    return json.loads(resp.content)


class TestResponseSuccess:
    def test_默认成功响应(self):
        resp = WebUtils.response_success()
        assert resp.status_code == status.HTTP_200_OK
        assert _body(resp) == {"data": {}, "result": True, "message": ""}

    def test_携带数据与消息(self):
        resp = WebUtils.response_success({"id": 1}, message="ok")
        assert _body(resp) == {"data": {"id": 1}, "result": True, "message": "ok"}


class TestResponseError:
    def test_默认错误为_400_且_result_false(self):
        resp = WebUtils.response_error(error_message="bad")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        body = _body(resp)
        assert body["result"] is False
        assert body["message"] == "bad"

    def test_可定制状态码(self):
        resp = WebUtils.response_error(status_code=status.HTTP_409_CONFLICT)
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_首位字符串视为错误文案而不是_data(self):
        """历史调用 response_error(\"实例不存在\", status_code=404) 把文案塞进 data、message 为空。"""
        resp = WebUtils.response_error("实例不存在", status_code=status.HTTP_404_NOT_FOUND)
        assert resp.status_code == status.HTTP_404_NOT_FOUND
        body = _body(resp)
        assert body["result"] is False
        assert body["message"] == "实例不存在"
        assert body["data"] == {}

    def test_两位位置参数仍是_data_加_message(self):
        resp = WebUtils.response_error({"code": "gone"}, "实例已删除")
        body = _body(resp)
        assert body["data"] == {"code": "gone"}
        assert body["message"] == "实例已删除"


class TestAuthResponses:
    def test_401(self):
        resp = WebUtils.response_401("unauth")
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED
        assert _body(resp) == {"result": False, "message": "unauth"}

    def test_403(self):
        resp = WebUtils.response_403("forbidden")
        assert resp.status_code == status.HTTP_403_FORBIDDEN
        assert _body(resp) == {"result": False, "message": "forbidden"}


class TestResponseFile:
    def test_bytes_被包装为附件下载(self):
        resp = WebUtils.response_file(b"hello", "a.txt")
        assert resp["Content-Disposition"] == 'attachment; filename="a.txt"'
        assert b"".join(resp.streaming_content) == b"hello"
