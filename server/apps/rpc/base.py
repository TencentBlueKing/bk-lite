import asyncio
import os

from django.conf import settings

import nats_client

DEFAULT_REQUEST_TIMEOUT = 60


class RpcClient(object):
    def __init__(self, namespace=None):
        if namespace is None:
            # Default namespace is set to 'bk_lite' if not provided
            # This can be overridden by the environment variable NATS_NAMESPACE
            namespace = os.getenv("NATS_NAMESPACE", "bklite")
        self.namespace = namespace

    def run(self, method_name, *args, **kwargs):
        timeout = kwargs.get("_timeout")
        effective_timeout = timeout if timeout is not None else getattr(settings, "NATS_REQUEST_TIMEOUT", DEFAULT_REQUEST_TIMEOUT)
        try:
            request_coro = nats_client.request(self.namespace, method_name, *args, **kwargs)
            if effective_timeout and effective_timeout > 0:
                request_coro = asyncio.wait_for(request_coro, timeout=effective_timeout)
            return asyncio.run(request_coro)
        except TimeoutError:
            raise TimeoutError(f"RPC request timeout: namespace={self.namespace}, method={method_name}, timeout={effective_timeout}s")

    def request(self, method_name, **kwargs):
        return_data = asyncio.run(nats_client.nat_request(self.namespace, method_name, **kwargs))
        return return_data


class AppClient(object):
    def __init__(self, path):
        self.path = path

    def run(self, method_name, *args, **kwargs):
        m = __import__(self.path, globals(), locals(), ["*"])
        method = getattr(m, method_name, None)
        if not method:
            raise ValueError(f"Method {method_name} not found in {self.path}")
        return method(*args, **kwargs)


class OperationAnalysisRpc(RpcClient):
    """
    操作分析专用RPC客户端
    支持自定义服务器地址，独立于框架基础RpcClient实现
    """

    def __init__(self, *args, **kwargs):
        self.namespace = kwargs.pop("namespace", None)
        super().__init__(namespace=self.namespace)
        self.server = kwargs.pop("server", "")

    def run(self, method_name, *args, **kwargs):
        return_data = asyncio.run(nats_client.request_v2(self.namespace, method_name, server=self.server, *args, **kwargs))
        return return_data


class BaseOperationAnaRpc(object):
    def __init__(self, *args, **kwargs):
        params = {}
        server = kwargs.get("server", None)
        namespace = kwargs.get("namespace", None)
        if server:
            params["server"] = server
        if namespace:
            params["namespace"] = namespace
        self.client = OperationAnalysisRpc(**params)
