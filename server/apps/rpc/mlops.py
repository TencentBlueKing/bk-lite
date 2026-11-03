import os

from apps.rpc.base import AppClient, RpcClient


class MLOps:
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = AppClient("apps.mlops.nats_api") if is_local_client else RpcClient()

    def get_module_data(self, **kwargs):
        return self.client.run("get_mlops_module_data", **kwargs)

    def get_module_list(self, **kwargs):
        return self.client.run("get_mlops_module_list", **kwargs)

    def predict_timeseries_serving(self, **kwargs):
        timeout = kwargs.pop("_timeout", None)
        if timeout is not None and not isinstance(self.client, AppClient):
            kwargs["_timeout"] = timeout
        return self.client.run("predict_timeseries_serving", **kwargs)
