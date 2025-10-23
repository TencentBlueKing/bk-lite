from apps.rpc.base import RpcClient, BaseOperationAnaRpc


class Monitor(object):
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
        return_data = self.client.run("get_monitor_module_data", **kwargs)
        return return_data

    def get_module_list(self, **kwargs):
        """
        :param module: 模块
        :return: 模块的枚举值列表
        """
        return_data = self.client.run("get_monitor_module_list", **kwargs)
        return return_data

    def monitor_objects(self):
        """查询监控对象列表"""
        return self.client.run("monitor_objects")


class MonitorOperationAnaRpc(BaseOperationAnaRpc):

    def monitor_objects(self, **kwargs):
        """查询监控对象列表"""
        return self.client.run("monitor_objects", **kwargs)

    def monitor_metrics(self, monitor_obj_id: str, **kwargs):
        """查询指标信息"""
        return self.client.run("monitor_metrics", monitor_obj_id=monitor_obj_id, **kwargs)

    def monitor_object_instances(self, monitor_obj_id: str, **kwargs):
        """查询监控对象实例列表
            monitor_obj_id: 监控对象ID
            permission_data: {
                team: 当前组织ID
                user: 用户对象或用户名
            }
        """
        return self.client.run(
            "monitor_object_instances",
            monitor_obj_id=monitor_obj_id,
            **kwargs
        )

    def query_monitor_data_by_metric(self, query_data: dict, **kwargs):
        """查询监控数据
            query_data: {
                "monitor_object_id": str,
                "metric": str,
                "start_time": int,
                "end_time": int,
                "step": int
            }
            permission_data: {
                team: 当前组织ID
                user: 用户对象或用户名
            }
        """
        return self.client.run(
            "query_monitor_data_by_metric",
            query_data=query_data,
            **kwargs
        )

    def query_range(self, query: str, time_range:str, step="5m", **kwargs):
        """查询时间范围内的指标数据
            query: 指标查询语句
            start: 开始时间（UTC时间戳）
            end: 结束时间（UTC时间戳）
            step: 数据采集间隔，默认为5分钟
        """
        return self.client.run("mm_query_range", query=query, time_range=time_range, step=step, **kwargs)

    def query(self, query: str, step="5m", **kwargs):
        """查询单点指标数据
            query: 指标查询语句
            step: 数据采集间隔，默认为5分钟
            time: 查询时间点（UTC时间戳），默认为当前时间
        """
        return self.client.run("mm_query", query=query, step=step, **kwargs)
