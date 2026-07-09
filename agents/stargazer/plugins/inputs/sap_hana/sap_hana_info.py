# -*- coding: utf-8 -*-
"""SAP HANA Information Collector (G5.2 占位 stub)。

**硬约束**:SAP HANA 需 SAP 账号 license + hdbcli / sqlalchemy-hana driver 公开渠道拿不到。
- Enterprise / Express Edition 均需 SAP 账号注册获取安装包
- Python driver `hdbcli`(PyHDB 替代)需 SAP 官方下载
- 真采集路径:amd64 CI runner + SAP 账号 + hdbcli 安装包 + license

**fixture 验证**:catalog 注册 + plugin stub 校验通过,真采集阻塞于 license + driver。
"""
import logging

logger = logging.getLogger(__name__)


class SapHanaInfo:
    """采集 sap_hana 实例配置信息 (G5.2 占位 stub;license + driver 阻塞)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 30015))  # HANA SQL port
        self.user = kwargs.get("user", "SYSTEM")
        self.password = kwargs.get("password", "")

    def list_all_resources(self):
        """G5.2 占位实现:SAP HANA license 不可达 + hdbcli driver 未装,返回空 list。

        修复路径(需用户提供 SAP 账号):
        1. SAP 官网下载 HANA Express Edition docker 镜像
        2. 装 hdbcli: `pip install hdbcli`(SAP PyPI 镜像)
        3. 设 SAP_HANA_LICENSE 环境变量
        4. 实现 schema / table / user 列表采集
        """
        logger.warning(
            "G5.2 sap_hana collector blocked: SAP license + hdbcli driver unavailable "
            "from public channels; see phase5-execution-report 2026-07-08"
        )
        return []