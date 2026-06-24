from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NetworkWhiteList(MaintainerInfo, TimeInfo):
    """SSRF 内网白名单条目（CIDR）。

    命中条目的解析 IP 可绕过私网阻断（云元数据除外）。
    """

    network = models.CharField(max_length=64, unique=True)  # 规范化 CIDR: 10.11.73.0/24 / 10.11.73.15/32
    remark = models.CharField(max_length=255, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Network White List"
        db_table = "system_mgmt_network_white_list"
        ordering = ["-id"]
