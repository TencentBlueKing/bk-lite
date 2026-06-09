"""rpc.base 纯单元测试。

规格：
- RpcClient.namespace 默认取环境变量 NATS_NAMESPACE，缺省为 "bklite"，显式传参优先；
- AppClient.run 按 path 动态导入模块并调用其同名函数；函数不存在抛 ValueError。
不触达真实 NATS（测试只覆盖不依赖网络的分发/命名空间逻辑）。
"""

import os
from unittest import mock

import pytest

from apps.rpc.base import AppClient, RpcClient

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
