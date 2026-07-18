"""rpc.base 补充单元测试：RpcClient.run、OperationAnalysisRpc、BaseOperationAnaRpc。

只 mock nats_client 这一外部边界（request / request_v2），断言：
- run() 用 asyncio.wait_for 包裹并尊重 _timeout / 默认超时；
- run() 超时抛 TimeoutError；
- OperationAnalysisRpc.run 转发 server/namespace；
- BaseOperationAnaRpc 按 server/namespace 构造内部 client。
不触达真实 NATS。
"""
import pydantic.root_model  # noqa

import asyncio
from unittest import mock

import pytest

from apps.rpc.base import (
    BaseOperationAnaRpc,
    OperationAnalysisRpc,
    RpcClient,
)

pytestmark = pytest.mark.unit


def _coro(return_value):
    async def _c(*args, **kwargs):
        return return_value
    return _c


class TestRpcClientRun:
    def test_run_返回nats_client_request结果(self):
        client = RpcClient(namespace="ns")
        expected = {"result": True, "data": [1, 2]}
        with mock.patch("apps.rpc.base.nats_client") as m:
            m.request.side_effect = _coro(expected)
            out = client.run("do", "a", key="v")
        assert out == expected
        # namespace + method_name + 位置参数原样转发
        call = m.request.call_args
        assert call.args[0] == "ns"
        assert call.args[1] == "do"
        assert call.args[2] == "a"
        assert call.kwargs["key"] == "v"

    def test_run_尊重显式_timeout(self):
        client = RpcClient(namespace="ns")
        with mock.patch("apps.rpc.base.nats_client") as m, mock.patch(
            "apps.rpc.base.asyncio.wait_for", wraps=asyncio.wait_for
        ) as wait_for:
            m.request.side_effect = _coro({"ok": 1})
            client.run("do", _timeout=12)
        assert wait_for.call_args.kwargs.get("timeout") == 12 or wait_for.call_args.args[1] == 12

    def test_run_超时抛TimeoutError(self):
        client = RpcClient(namespace="ns")

        async def _slow(*a, **k):
            await asyncio.sleep(5)

        with mock.patch("apps.rpc.base.nats_client") as m:
            m.request.side_effect = _slow
            with pytest.raises(TimeoutError, match="RPC request timeout"):
                client.run("do", _timeout=0.01)


class TestOperationAnalysisRpc:
    def test_init_提取namespace与server(self):
        rpc = OperationAnalysisRpc(namespace="ana_ns", server="nats://1.2.3.4")
        assert rpc.namespace == "ana_ns"
        assert rpc.server == "nats://1.2.3.4"

    def test_init_缺省server为空串(self):
        rpc = OperationAnalysisRpc(namespace="ana_ns")
        assert rpc.server == ""

    def test_run_转发server与namespace给request_v2(self):
        rpc = OperationAnalysisRpc(namespace="ana_ns", server="srv")
        with mock.patch("apps.rpc.base.nats_client") as m:
            m.request_v2.side_effect = _coro({"data": 1})
            out = rpc.run("method", "posarg", k="v")
        assert out == {"data": 1}
        call = m.request_v2.call_args
        assert call.args[0] == "ana_ns"
        assert call.args[1] == "method"
        assert call.kwargs["server"] == "srv"
        assert call.kwargs["k"] == "v"

    def test_run_将nats认证参数从业务载荷中分离(self):
        rpc = OperationAnalysisRpc(namespace="ana_ns", server="nats://host:4222")
        with mock.patch("apps.rpc.base.nats_client") as m:
            m.request_v2.side_effect = _coro({"data": 1})
            rpc.run("method", _nats_user="alice", _nats_password="secret", query="value")

        call = m.request_v2.call_args
        assert call.kwargs["user"] == "alice"
        assert call.kwargs["password"] == "secret"
        assert call.kwargs["query"] == "value"
        assert "_nats_user" not in call.kwargs
        assert "_nats_password" not in call.kwargs


class TestBaseOperationAnaRpc:
    def test_构造时传入server与namespace(self):
        base = BaseOperationAnaRpc(server="srv", namespace="ns")
        assert isinstance(base.client, OperationAnalysisRpc)
        assert base.client.namespace == "ns"
        assert base.client.server == "srv"

    def test_构造时无参也能建client(self):
        base = BaseOperationAnaRpc()
        assert isinstance(base.client, OperationAnalysisRpc)
        assert base.client.server == ""
