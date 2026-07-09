# -*- coding: utf-8 -*-
"""iris Information Collector (G5.2 占位 stub)。

完整实现待 amd64 CI runner 上验证（spec 已 catalog 化,plugin 当前为占位）。
"""
import logging

logger = logging.getLogger(__name__)


class IrisInfo:
    """采集 iris 实例配置信息 (G5.2 占位 stub)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 0))

    def list_all_resources(self):
        """G5.2 占位实现:返回空 list,等 amd64 CI 跑通后补充真实采集。"""
        logger.warning("G5.2 iris collector is a stub; real implementation pending amd64 CI runner")
        return []
