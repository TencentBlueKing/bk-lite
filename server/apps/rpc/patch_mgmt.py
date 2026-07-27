"""Patch Management RPC Client"""

import os

from apps.rpc.base import AppClient, RpcClient


class PatchMgmt:
    """补丁管理 RPC 客户端"""

    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = AppClient("apps.patch_mgmt.nats_api") if is_local_client else RpcClient()

    def get_module_list(self):
        """获取模块列表"""
        return self.client.run("get_patch_mgmt_module_list")
