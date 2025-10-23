# -- coding: utf-8 --
# @File: alerts.py
# @Time: 2025/7/22 18:29
# @Author: windyzhao
from apps.rpc.base import BaseOperationAnaRpc


class AlertOperationAnaRpc(BaseOperationAnaRpc):
    """
    告警操作分析的NATS接口
    继承自BaseOperationAnaRpc，提供获取告警趋势数据的功能
    通过NATS客户端与后端服务进行通信
    """

    def get_alert_trend_data(self, *args, **kwargs):
        """
        :param group_by: 分组方式
        :param filters: 过滤条件，字典格式
        :return: 告警趋势数据
        """
        return_data = self.client.run("get_alert_trend_data", *args, **kwargs)
        return return_data
