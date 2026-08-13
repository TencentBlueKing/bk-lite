from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.core.utils.database_constraints import ConstraintValidatedQuerySet


class NetworkWhiteListQuerySet(ConstraintValidatedQuerySet):
    protected_fields = frozenset({"network"})


class NetworkWhiteList(MaintainerInfo, TimeInfo):
    """SSRF 出站白名单条目。

    二选一:
    - `network` 为规范化 CIDR（如 10.11.73.0/24）：纯 IP 必须命中；域名解析到
      黑名单网段时也可作为例外。
    - `domain_name` 为小写 hostname 全等，或 ``*.example.com`` 后缀通配：仅当
      解析到黑名单网段（含内网）时作为例外放行，不能覆盖云 metadata 硬挡。

    `is_build_in=True` 表示内置条目，viewset 层禁止修改/删除。
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

    objects = NetworkWhiteListQuerySet.as_manager()

    class Meta:
        verbose_name = "Network White List"
        db_table = "system_mgmt_network_white_list"
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                check=~models.Q(network__in=("0.0.0.0/0", "::/0")),
                name="network_whitelist_forbid_universal_cidr",
            )
        ]

    def clean(self):
        super().clean()
        self._validate_database_constraints()

    def _validate_database_constraints(self):
        if self.network in {"0.0.0.0/0", "::/0"}:
            raise ValidationError({"network": "不允许配置全网段白名单"})

    def save(self, *args, **kwargs):
        self._validate_database_constraints()
        return super().save(*args, **kwargs)
