# -*- coding: utf-8 -*-
"""Couchbase Information Collector (G5.2 占位 stub)。

**硬约束**:Couchbase Enterprise 需 license + Python SDK `couchbase` 不在 pyproject.toml 默认依赖中。
- SDK 安装:`pip install couchbase` 需 libcouchbase 系统库(license 限制)
- Cluster 连接:Enterprise Edition 需 license 文件
- 真采集路径:amd64 CI runner + 自备 license + 装 couchbase SDK

**fixture 验证**:catalog 注册 + plugin stub 校验通过(validate 不报错),真采集阻塞于 SDK + license。
"""
import logging

logger = logging.getLogger(__name__)


class CouchbaseInfo:
    """采集 couchbase 实例配置信息 (G5.2 占位 stub;license + SDK 阻塞)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.port = int(kwargs.get("port", 0))
        self.user = kwargs.get("user", "")
        self.password = kwargs.get("password", "")
        self.bucket = kwargs.get("bucket", "")

    def list_all_resources(self):
        """G5.2 占位实现:couchbase SDK 未装 + Enterprise license 不可达,返回空 list。

        修复路径:
        1. 在 amd64 CI runner 装系统依赖 `apt install -y libcouchbase-dev`
        2. `pip install couchbase`
        3. 用户在 GitHub Secrets 设 COUCHBASE_LICENSE
        4. 启动容器时挂载 license 文件
        5. 实现 bucket / cluster / node 列表采集
        """
        logger.warning(
            "G5.2 couchbase collector blocked: SDK `couchbase` not installed "
            "(requires libcouchbase system lib, license-restricted) + "
            "Enterprise license unavailable; see phase5-execution-report 2026-07-08"
        )
        return []