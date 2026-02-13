import os

from apps.rpc.base import RpcClient, AppClient


class CMDB(object):
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = (
            AppClient("apps.cmdb.nats.nats") if is_local_client else RpcClient()
        )

    def get_module_data(self, **kwargs):
        """
        :param module: 模块
        :param child_module: 子模块
        :param page: 页码
        :param page_size: 页条目数
        :param group_id: 组ID
        """
        return_data = self.client.run("get_cmdb_module_data", **kwargs)
        return return_data

    def get_module_list(self, **kwargs):
        """
        :param module: 模块
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("get_cmdb_module_list", **kwargs)
        return return_data

    def search_instances(self, **kwargs):
        """
        告警丰富查询CMDB接口
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("search_instances", **kwargs)
        return return_data

    def sync_display_fields(self, **kwargs):
        """
        同步组织/用户的 _display 字段
        :param organizations: 组织变更数据列表 [{"id": 1, "name": "新组织名"}]
        :param users: 用户变更数据列表 [{"id": 1, "username": "admin", "display_name": "新显示名"}]
        :return: 任务提交结果 {"task_id": "uuid", "status": "submitted"}
        """
        return_data = self.client.run("sync_display_fields", **kwargs)
        return return_data
