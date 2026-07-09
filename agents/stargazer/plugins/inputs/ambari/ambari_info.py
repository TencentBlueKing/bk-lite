# -*- coding: utf-8 -*-
"""Ambari Information Collector (G5.2 占位 stub)。

**硬约束**:Apache Ambari 无官方 docker 镜像,需手动 apt 装 + 大量 JDK 依赖 + 集群初始化。
- 镜像:无官方 Docker Hub,需 ubuntu + wget + 安装包 + ambari-server setup
- 配置:Ambari Server 启动需 PostgreSQL 存元数据 + 配置 admin 密码
- 真采集路径:amd64 CI runner + Apache Ambari 2.7 安装包 + 完整初始化流程

**fixture 验证**:catalog 注册 + plugin stub 校验通过,真采集阻塞于镜像初始化复杂度。
"""
import logging

logger = logging.getLogger(__name__)


class AmbariInfo:
    """采集 ambari 实例配置信息 (G5.2 占位 stub;镜像初始化复杂)。"""

    def __init__(self, kwargs):
        self.kwargs = kwargs
        self.host = kwargs.get("host", "localhost")
        self.ambari_port = int(kwargs.get("ambari_port", 8080))
        self.user = kwargs.get("user", "admin")
        self.password = kwargs.get("password", "")

    def list_all_resources(self):
        """G5.2 占位实现:Ambari 无官方 docker,需手动安装,返回空 list。

        修复路径(amd64 CI):
        1. apt install openjdk-8-jdk postgresql
        2. wget https://archive.apache.org/dist/ambari/ambari-2.7.5/apache-ambari-2.7.5-bin.tar.gz
        3. ambari-server setup -s (接受 GPL)
        4. ambari-server start
        5. 实现 cluster / host / service 列表采集
        """
        logger.warning(
            "G5.2 ambari collector blocked: Ambari needs manual install on "
            "ubuntu + JDK + PostgreSQL; see phase5-execution-report 2026-07-08"
        )
        return []