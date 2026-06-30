from typing import Optional

from apps.rpc.base import RpcClient


class StargazerRpcClient(RpcClient):
    def __init__(self, namespace):
        self.namespace = namespace


class Stargazer(object):
    def __init__(self, instance_id: Optional[str] = None):
        self.instance_id = instance_id or "stargazer"
        self.client = RpcClient(namespace=self.instance_id)
        self.health_check_client = StargazerRpcClient(self.instance_id)

    def list_regions(self, params):
        return_data = self.client.request("list_regions", **params)
        return return_data

    def health_check(self, timeout: int = 5):
        request_data = {"execute_timeout": timeout}
        return_data = self.health_check_client.run("health_check", request_data, _timeout=timeout)
        return return_data

    def collection_tool_debug(self, payload: dict, timeout: int) -> dict:
        """
        通过 NATS request 调用 Stargazer 协议诊断 handler。
        handler 按 protocol 区分：debug_snmp / debug_ipmi。
        nats_timeout = timeout + 5s（缓冲）
        """
        protocol = payload.get("protocol", "snmp")
        handler = f"debug_{protocol}"
        nats_timeout = timeout + 5
        return_data = self.client.request(handler, _timeout=nats_timeout, **payload)
        return return_data
