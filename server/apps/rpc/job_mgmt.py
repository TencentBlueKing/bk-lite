"""Job Management RPC Client"""

import os

from apps.rpc.base import AppClient, RpcClient


class JobMgmt:
    """作业管理 RPC 客户端"""

    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = AppClient("apps.job_mgmt.nats_api") if is_local_client else RpcClient()

    def get_module_data(self, **kwargs):
        """
        获取模块数据

        :param module: 模块
        :param child_module: 子模块
        :param page: 页码
        :param page_size: 页条目数
        :param group_id: 组ID
        """
        return self.client.run("get_job_mgmt_module_data", **kwargs)

    def get_module_list(self):
        """获取模块列表"""
        return self.client.run("get_job_mgmt_module_list")

    def job_script_execute(self, data):
        """触发脚本执行（NATS）。data 见 apps.job_mgmt.nats_api.job_script_execute。"""
        return self.client.run("job_script_execute", data)

    def get_script(self, script_id):
        """读取单个脚本模板（content/params/script_type/timeout）。"""
        result = self.client.run(
            "get_job_mgmt_module_data",
            {"module": "script", "id": script_id},
        ) or {}
        items = result.get("items") or result.get("data") or []
        for it in items:
            if str(it.get("id")) == str(script_id):
                return it
        return None

    def list_scripts(self, params):
        """脚本列表（供告警动作选择作业）。"""
        data = {"module": "script"}
        data.update(params or {})
        return self.client.run("get_job_mgmt_module_data", data)
