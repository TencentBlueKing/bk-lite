# -*- coding: utf-8 -*-
"""Tongrds (东方通 RDS) Information Collector (G5.2 占位 stub)。

**硬约束**:东方通 RDS 私有协议,公开渠道无 Python SDK。
- 数据库:东方通关系型数据库(国产替代)
- 协议:私有,可能仅提供 C / Java 驱动
- 真采集路径:amd64 CI runner + 用户提供 SDK / JDBC jar + Java 桥接

**fixture 验证**:catalog 注册 + plugin stub 校验通过,真采集阻塞于私有协议 SDK。
"""
import logging

logger = logging.getLogger(__name__)


class TongrdsInfo:
    """采集 tongrds 实例配置信息 (G5.2 占位 stub;私有协议 SDK 不可达)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 0))
        self.user = kwargs.get("user", "")
        self.password = kwargs.get("password", "")

    def list_all_resources(self):
        """G5.2 占位实现:东方通 RDS 私有协议,公开 SDK 不可达,返回空 list。

        修复路径(需用户提供):
        1. 东方通技术支持索取 Python driver 或 JDBC jar
        2. 用 jpype1 桥接 JDBC → Python 调用
        3. 采集数据库 / 表空间 / 用户列表
        """
        logger.warning(
            "G5.2 tongrds collector blocked: 东方通 RDS 私有协议,公开 SDK 不可达; "
            "see phase5-execution-report 2026-07-08"
        )
        return []