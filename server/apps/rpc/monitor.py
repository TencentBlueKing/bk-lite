import os

from apps.rpc.base import AppClient, BaseOperationAnaRpc, RpcClient


class Monitor(object):
    def __init__(self, is_local_client=False):
        is_local_client = os.getenv("IS_LOCAL_RPC", "0") == "1" or is_local_client
        if is_local_client:
            self.client = AppClient("apps.monitor.nats.permission")
            # ingest_from_source 注册在 nats.monitor，与 permission 模块分离
            self.ingest_client = AppClient("apps.monitor.nats.monitor")
        else:
            self.client = RpcClient()
            self.ingest_client = self.client

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

    def ingest_from_source(self, **kwargs):
        """跨模块推送写入监控（node_id / cmdb_id 归并）。

        NATS handler 签名为 monitor_ingest_from_source(params)，须整包为 params。
        """
        return self.ingest_client.run("monitor_ingest_from_source", params=kwargs)


class MonitorOperationAnaRpc(BaseOperationAnaRpc):
    def create_monitor_object_type(self, data: dict, **kwargs):
        """创建监控对象类型"""
        return self.client.run("create_monitor_object_type", data=data, **kwargs)

    def create_monitor_object(self, data: dict, **kwargs):
        """创建监控对象"""
        return self.client.run("create_monitor_object", data=data, **kwargs)

    def create_monitor_plugin(self, data: dict, **kwargs):
        """创建监控模板"""
        return self.client.run("create_monitor_plugin", data=data, **kwargs)

    def create_metric_group(self, data: dict, **kwargs):
        """创建指标分组"""
        return self.client.run("create_metric_group", data=data, **kwargs)

    def create_metric(self, data: dict, **kwargs):
        """创建监控指标"""
        return self.client.run("create_metric", data=data, **kwargs)

    def create_monitor_policy(self, data: dict, **kwargs):
        """创建监控告警策略"""
        return self.client.run("create_monitor_policy", data=data, **kwargs)

    def search_monitor_policies(self, name: str, **kwargs):
        """按名称查询监控告警策略（允许同名多条；写操作请用 policy_id）。"""
        return self.client.run("search_monitor_policies", name=name, **kwargs)

    def delete_monitor_policy(self, policy_id, **kwargs):
        """删除监控告警策略"""
        return self.client.run("delete_monitor_policy", policy_id=policy_id, **kwargs)

    def monitor_objects(self, **kwargs):
        """查询监控对象列表"""
        return self.client.run("monitor_objects", **kwargs)

    def monitor_object_instance_count(self, **kwargs):
        """统计全部监控对象实例数量（不过滤权限）"""
        return self.client.run("monitor_object_instance_count", **kwargs)

    def monitor_metrics(self, monitor_obj_id: str, **kwargs):
        """查询指标信息"""
        return self.client.run("monitor_metrics", monitor_obj_id=monitor_obj_id, **kwargs)

    def monitor_object_instances(self, monitor_obj_id: str, **kwargs):
        """查询监控对象实例列表
        monitor_obj_id: 监控对象ID
        user_info: {
            team: 当前组织ID
            user: 用户对象或用户名
        }
        """
        return self.client.run("monitor_object_instances", monitor_obj_id=monitor_obj_id, **kwargs)

    def monitor_instance_metrics(self, query_data: dict, **kwargs):
        """查询实例已监控指标清单
        query_data: {
            "monitor_obj_id": str,
            "instance_id": str,
            "only_with_data": bool,
            "lookback": str | int,
            "page": int,
            "page_size": int,
        }
        user_info: {
            team: 当前组织ID
            user: 用户对象或用户名
        }
        """
        return self.client.run("monitor_instance_metrics", query_data=query_data, **kwargs)

    def query_monitor_data_by_metric(self, query_data: dict, **kwargs):
        """查询监控数据
        query_data: {
            "monitor_obj_id": str,
            "metric": str,
            "start": int,
            "end": int,
            "step": str | int,
            "instance_ids": list[str],
            "dimensions": dict[str, str]
        }
        返回: {
            "result": bool,
            "data": VictoriaMetrics query_range 原始结果,
            "message": str,
        }
        兼容历史字段:
            monitor_object_id -> monitor_obj_id
            start_time -> start
            end_time -> end
        user_info: {
            team: 当前组织ID
            user: 用户对象或用户名
        }
        返回 data: {
            "monitor_obj_id": str,
            "instance_id": str,
            "count": int,
            "page": int,
            "page_size": int,
            "items": list,
        }
        """
        return self.client.run("query_monitor_data_by_metric", query_data=query_data, **kwargs)

    def query_monitor_alert_segments(self, query_data: dict, **kwargs):
        """查询监控模块策略产生的异常段
        query_data: {
            "monitor_obj_id": str,
            "start": str | int,
            "end": str | int,
            "instance_id": str,
            "instance_ids": list[str],
            "status": str | list[str],
            "level": str | list[str],
            "alert_type": str | list[str],
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
        return self.client.run("query_monitor_alert_segments", query_data=query_data, **kwargs)

    def query_latest_active_alerts(self, query_data: dict, **kwargs):
        """查询当前用户可访问范围内最新活跃告警
        query_data: {
            "monitor_obj_id": str,
            "limit": int,
            "instance_id": str,
            "instance_ids": list[str],
            "level": str | list[str],
            "alert_type": str | list[str],
        }
        user_info: {
            team: 当前组织ID,
            user: 用户对象或用户名,
            include_children: 是否包含子组织,
        }
        返回 data: {
            "count": int,
            "items": list,
        }
        monitor_obj_id 为可选，用于收窄到指定监控对象。
        """
        return self.client.run("query_latest_active_alerts", query_data=query_data, **kwargs)

    def query_latest_interface_metrics(self, instance_ids=None, **kwargs):
        """按监控实例批量查询接口最新 IF-MIB 值（含 ifDescr）。"""
        return self.client.run(
            "query_latest_interface_metrics",
            instance_ids=instance_ids,
            **kwargs,
        )

    def get_host_instance_list(self, **kwargs):
        """查询当前组织权限范围内的主机实例，供下拉选项使用。"""
        return self.client.run("get_host_instance_list", **kwargs)

    def get_host_metric_range(self, **kwargs):
        """按所选主机查询单一指标时序，返回 {display_name: [[ts, value], ...]}。"""
        return self.client.run("get_host_metric_range", **kwargs)

    def get_host_resource_snapshot(self, **kwargs):
        """按所选主机返回 CPU/内存/磁盘均值与最高值快照。"""
        return self.client.run("get_host_resource_snapshot", **kwargs)

    def get_host_resource_top(self, metric_type: str, **kwargs):
        """查询主机资源使用率 Top10，可选 instance_ids 收窄。"""
        return self.client.run("get_host_resource_top", metric_type=metric_type, **kwargs)
