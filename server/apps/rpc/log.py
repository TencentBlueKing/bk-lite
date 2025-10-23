from apps.rpc.base import RpcClient, BaseOperationAnaRpc


class Log(object):
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
        return_data = self.client.run("get_log_module_data", **kwargs)
        return return_data

    def get_module_list(self, **kwargs):
        """
        :param module: 模块
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("get_log_module_list", **kwargs)
        return return_data


class LogOperationAnaRpc(BaseOperationAnaRpc):

    def search(self, query, time_range, limit=10, **kwargs):
        """
        日志搜索
        query: 日志查询语句
        start_time: 开始时间，eg:2025-08-16T11:52:13.106Z
        end_time: 结束时间，eg:2025-08-16T11:52:13.106Z
        limit: 返回结果条数，默认10
        """
        return self.client.run("log_search", query=query, time_range=time_range, limit=limit, **kwargs)

    def hits(self, query, time_range, field, fields_limit=5, step="5m", **kwargs):
        """
        日志命中
        query: 日志查询语句
        start_time: 开始时间，eg:2025-08-16T11:52:13.106Z
        end_time: 结束时间，eg:2025-08-16T11:52:13.106Z
        field: 要统计的字段
        fields_limit: 返回的字段值个数限制，默认5
        step: 统计粒度，默认5m
        """
        return self.client.run("log_hits", query=query, time_range=time_range, field=field, fields_limit=fields_limit, step=step, **kwargs)
