from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class NetworkWhiteList(MaintainerInfo, TimeInfo):
    """SSRF 出站白名单条目。

    二选一:
    - `network` 为规范化 CIDR（如 10.11.73.0/24）;hostname 解析出的所有 IP 均在 CIDR 内才放行。
    - `domain` 为完整小写 hostname;hostname 字符串等值匹配即放行(不做 DNS 解析)。

    `is_build_in=True` 表示代码内置条目（如官方 IM webhook 域名），
    viewset 层禁止修改/删除该行。
    """

    network = models.CharField(max_length=64, blank=True, default="")  # 规范化 CIDR: 10.11.73.0/24 / 10.11.73.15/32
    domain_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
        help_text="私有化部署域名(如 corp-wecom.example.com)。与 network 二选一。",
    )
    is_build_in = models.BooleanField(default=False, db_index=True)
    remark = models.CharField(max_length=255, blank=True, default="")
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Network White List"
        db_table = "system_mgmt_network_white_list"
        ordering = ["-id"]
