"""VictoriaMetrics 查询封装的重试行为测试（P2 稳定性修复）。

Collection.query 原本单次请求、非 200 直接抛原始异常、无重试，VM 瞬时抖动
会被放大成整轮采集失败。修复后应对连接异常与 5xx 做有限次退避重试。
"""
from unittest import mock

import pytest
import requests

from apps.cmdb.collection.query_vm import Collection

MODULE = "apps.cmdb.collection.query_vm"


def _ok_response():
    resp = mock.MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "success", "data": {"result": []}}
    return resp


def _bad_response(status_code=503, text="boom"):
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.text = text
    return resp


@pytest.fixture(autouse=True)
def _no_sleep():
    with mock.patch(f"{MODULE}.time.sleep", return_value=None):
        yield


def test_query_retries_on_connection_error_then_succeeds():
    with mock.patch(
        f"{MODULE}.requests.post",
        side_effect=[requests.ConnectionError("reset"), _ok_response()],
    ) as post:
        data = Collection().query("up", retries=3)

    assert data["status"] == "success"
    assert post.call_count == 2


def test_query_retries_on_5xx_then_succeeds():
    with mock.patch(
        f"{MODULE}.requests.post",
        side_effect=[_bad_response(503), _ok_response()],
    ) as post:
        data = Collection().query("up", retries=3)

    assert data["status"] == "success"
    assert post.call_count == 2


def test_query_raises_after_exhausting_retries():
    with mock.patch(
        f"{MODULE}.requests.post",
        side_effect=requests.ConnectionError("reset"),
    ) as post:
        with pytest.raises(Exception):
            Collection().query("up", retries=3)

    assert post.call_count == 3


def test_query_does_not_retry_on_4xx():
    with mock.patch(
        f"{MODULE}.requests.post",
        side_effect=[_bad_response(400, "bad request")],
    ) as post:
        with pytest.raises(Exception):
            Collection().query("up", retries=3)

    # 4xx 是请求本身问题，重试无意义，应只调用一次
    assert post.call_count == 1
