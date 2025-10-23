from apps.rpc.base import RpcClient


class CMDB(object):
    def __init__(self):
        self.client = RpcClient()

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
