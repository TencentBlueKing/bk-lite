import os

from apps.rpc.base import RpcClient, AppClient, BaseOperationAnaRpc


class Log(object):
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        self.client = (
            AppClient("apps.log.nats.permission") if is_local_client else RpcClient()
        )

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
        return self.client.run(
            "log_search", query=query, time_range=time_range, limit=limit, **kwargs
        )

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
        return self.client.run(
            "log_hits",
            query=query,
            time_range=time_range,
            field=field,
            fields_limit=fields_limit,
            step=step,
            **kwargs,
        )

    def query_log_alert_segments(self, query_data: dict, **kwargs):
        """查询日志模块策略产生的异常段
        query_data: {
            "collect_type_id": str,
            "start": str,
            "end": str,
            "instance_id": str,
            "instance_ids": list[str],
            "source_id": str,
            "status": str | list[str],
            "level": str | list[str],
            "page": int,
            "page_size": int,
        }
        user_info: {
            team: 当前组织ID
            user: 用户对象或用户名
            include_children: 是否包含子组织
        }
        返回 data: {
            "count": int,
            "page": int,
            "page_size": int,
            "items": list,
        }
        """
        return self.client.run(
            "query_log_alert_segments", query_data=query_data, **kwargs
        )
