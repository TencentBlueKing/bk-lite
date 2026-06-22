"""rpc.base 纯单元测试。

规格：
- RpcClient.namespace 默认取环境变量 NATS_NAMESPACE，缺省为 "bklite"，显式传参优先；
- AppClient.run 按 path 动态导入模块并调用其同名函数；函数不存在抛 ValueError；
- RpcClient.request() 必须有超时保护，遵循 NATS_REQUEST_TIMEOUT 设置，并在超时时抛出 TimeoutError。
不触达真实 NATS（测试只覆盖不依赖网络的分发/命名空间逻辑）。
"""

import asyncio
import os
from unittest import mock

import pytest

from apps.rpc.base import AppClient, DEFAULT_REQUEST_TIMEOUT, RpcClient

pytestmark = pytest.mark.unit


class TestRpcClientNamespace:
    def test_默认命名空间为_bklite(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NATS_NAMESPACE", None)
            assert RpcClient().namespace == "bklite"

    def test_环境变量覆盖默认(self):
        with mock.patch.dict(os.environ, {"NATS_NAMESPACE": "custom_ns"}):
            assert RpcClient().namespace == "custom_ns"

    def test_显式传参优先(self):
        with mock.patch.dict(os.environ, {"NATS_NAMESPACE": "env_ns"}):
            assert RpcClient(namespace="explicit").namespace == "explicit"


class TestAppClientDispatch:
    def test_动态导入并调用同名函数(self):
        # 指向真实标准库模块的真实函数，验证 import+getattr+调用链路
        client = AppClient("math")
        assert client.run("sqrt", 16) == 4.0

    def test_函数不存在抛_valueerror(self):
        client = AppClient("math")
        with pytest.raises(ValueError, match="not found"):
            client.run("no_such_function")


class TestRpcClientRequestTimeout:
    """验证 request() 有超时保护，修复 Issue #3485。"""

    def _make_mock_coro(self, return_value):
        """返回一个可以被 asyncio.run / asyncio.wait_for 使用的真实协程。"""
        async def _coro(*args, **kwargs):
            return return_value
        return _coro

    def test_request_使用_wait_for_包裹_nat_request(self):
        """asyncio.wait_for 必须被调用——revert 修复后此测试应失败。"""
        client = RpcClient(namespace="test_ns")
        expected = {"result": True, "data": {}}

        with mock.patch("apps.rpc.base.nats_client") as mock_nc, \
             mock.patch("apps.rpc.base.asyncio.wait_for", wraps=asyncio.wait_for) as mock_wait_for, \
             mock.patch("apps.rpc.base.asyncio.run", wraps=asyncio.run):
            mock_nc.nat_request = self._make_mock_coro(expected)
            client.request("some_method", key="val")

        mock_wait_for.assert_called_once()

    def test_request_使用默认超时(self):
        """未传 _timeout 时使用 NATS_REQUEST_TIMEOUT 设置值。"""
        client = RpcClient(namespace="test_ns")
        expected = {"result": True, "data": {}}

        with mock.patch("apps.rpc.base.nats_client") as mock_nc, \
             mock.patch("apps.rpc.base.asyncio.wait_for", wraps=asyncio.wait_for) as mock_wait_for, \
             mock.patch("apps.rpc.base.asyncio.run", wraps=asyncio.run), \
             mock.patch("apps.rpc.base.settings") as mock_settings:
            mock_settings.NATS_REQUEST_TIMEOUT = 30
            mock_nc.nat_request = self._make_mock_coro(expected)
            client.request("some_method")

        _, call_kwargs = mock_wait_for.call_args
        assert call_kwargs.get("timeout") == 30

    def test_request_尊重调用方传入的_timeout(self):
        """调用方通过 _timeout 传入的值必须生效（如 stargazer.collection_tool_debug）。"""
        client = RpcClient(namespace="test_ns")
        expected = {"result": True, "data": {}}

        with mock.patch("apps.rpc.base.nats_client") as mock_nc, \
             mock.patch("apps.rpc.base.asyncio.wait_for", wraps=asyncio.wait_for) as mock_wait_for, \
             mock.patch("apps.rpc.base.asyncio.run", wraps=asyncio.run):
            mock_nc.nat_request = self._make_mock_coro(expected)
            client.request("some_method", _timeout=15)

        _, call_kwargs = mock_wait_for.call_args
        assert call_kwargs.get("timeout") == 15

    def test_request_超时时抛出_TimeoutError(self):
        """NATS 不可达时 request() 必须抛出 TimeoutError，不得永久挂起。"""
        client = RpcClient(namespace="test_ns")

        async def _never_return(*args, **kwargs):
            await asyncio.sleep(9999)

        with mock.patch("apps.rpc.base.nats_client") as mock_nc, \
             mock.patch("apps.rpc.base.settings") as mock_settings:
            mock_settings.NATS_REQUEST_TIMEOUT = 0.01
            mock_nc.nat_request = _never_return
            with pytest.raises(TimeoutError):
                client.request("some_method")
