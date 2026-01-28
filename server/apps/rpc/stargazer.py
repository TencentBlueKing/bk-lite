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
        return_data = self.health_check_client.run(
            "health_check", request_data, _timeout=timeout
        )
        return return_data
