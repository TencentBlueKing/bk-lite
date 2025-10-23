# -- coding: utf-8 --
# @File: models.py
# @Time: 2025/7/14 16:03
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField
from rest_framework.exceptions import ValidationError

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.operation_analysis.constants import SECRET_KEY


class NameSpace(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, verbose_name="命名空间名称", unique=True)
    account = models.CharField(max_length=64, verbose_name="账号")
    password = models.CharField(max_length=128, verbose_name="密码")
    domain = models.CharField(max_length=255, verbose_name="域名")
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name="是否启用")

    class Meta:
        db_table = "operation_analysis_namespace"
        verbose_name = "命名空间"

    def __str__(self):
        return self.name

    @staticmethod
    def encrypt_password(raw_password):
        """
        加密密码
        :param raw_password: 明文密码
        :return: 加密后的密码
        """
        if not raw_password:
            return raw_password

        crypto = PasswordCrypto(SECRET_KEY)
        return crypto.encrypt(raw_password)

    @property
    def decrypt_password(self):
        """
        解密密码
        :return: 明文密码
        """
        if not self.password:
            return self.password

        try:
            crypto = PasswordCrypto(SECRET_KEY)
            return crypto.decrypt(self.password)
        except Exception:
            # 如果解密失败，可能是明文密码，直接返回
            return self.password

    def set_password(self, raw_password):
        """
        设置加密密码
        :param raw_password: 明文密码
        """
        self.password = self.encrypt_password(raw_password)

    def save(self, *args, **kwargs):
        if self.password:
            self.password = self.encrypt_password(self.password)
        super().save(*args, **kwargs)


class DataSourceTag(MaintainerInfo, TimeInfo):
    tag_id = models.CharField(max_length=64, verbose_name="标签id", unique=True)
    name = models.CharField(max_length=64, verbose_name="标签名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    build_in = models.BooleanField(default=False, verbose_name="是否内置")

    class Meta:
        db_table = "operation_analysis_data_source_tag"
        verbose_name = "数据源标签"

    def __str__(self):
        return f"{self.name}({self.tag_id})"


class DataSourceAPIModel(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=255, verbose_name="数据源名称")
    rest_api = models.CharField(max_length=255, verbose_name="REST API URL")
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    params = JSONField(help_text="API请求参数", verbose_name="请求参数", blank=True, null=True)
    namespaces = models.ManyToManyField(NameSpace, related_name='data_sources', help_text="会话关联的事件",
                                        verbose_name="命名空间", blank=True)
    tag = models.ManyToManyField(to=DataSourceTag, related_name='data_sources', help_text="数据源标签", blank=True)
    chart_type = JSONField(help_text="图表类型", default=list, blank=True, null=True)

    class Meta:
        db_table = "operation_analysis_data_source_api"
        verbose_name = "数据源API"
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'rest_api'],
                name='unique_name_rest_api'
            ),
        ]


class Directory(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, verbose_name="目录名称")
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, related_name="sub_directories", null=True, blank=True, verbose_name="父目录"
    )
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    desc = models.TextField(verbose_name="描述", blank=True, null=True)

    class Meta:
        db_table = "operation_analysis_directory"
        verbose_name = "目录"
        constraints = [
            models.UniqueConstraint(
                fields=['name', 'parent'],
                name='unique_name_parent'
            ),
        ]

    def clean(self):
        # 确保目录层级不超过3层
        if self.parent and self.parent.get_level() >= 2:
            raise ValidationError("Directory hierarchy cannot exceed 3 levels.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def has_children(self):
        return self.sub_directories.exists()

    def get_level(self):
        level = 0
        parent = self.parent
        while parent is not None:
            level += 1
            parent = parent.parent
        return level

    def __str__(self):
        return self.name


class Dashboard(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, verbose_name="仪表盘名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(
        Directory, on_delete=models.CASCADE, related_name="dashboards", verbose_name="所属目录", null=True, blank=True
    )
    filters = JSONField(help_text="仪表盘公共过滤条件", verbose_name="过滤条件", blank=True, null=True)
    other = JSONField(help_text="仪表盘其他配置", verbose_name="其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="仪表盘视图集配置", verbose_name="视图集配置", default=list)

    # 下边这两个字段是在view_sets中配置的
    # type = models.CharField(max_length=64, verbose_name="仪表盘类型", choices=DashboardType.CHOICES, null=True,
    #                         blank=True)
    # data_source = models.ForeignKey(
    #     DataSourceAPIModel, on_delete=models.CASCADE, related_name="dashboards", verbose_name="数据源", null=True,
    #     blank=True
    # )

    class Meta:
        db_table = "operation_analysis_dashboard"
        verbose_name = "仪表盘"

    def __str__(self):
        return self.name


class Topology(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, verbose_name="拓扑图名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(
        Directory, on_delete=models.CASCADE, related_name="topology", verbose_name="所属目录", null=True, blank=True
    )
    other = JSONField(help_text="拓扑图其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="拓扑图视图集配置", default=list)

    class Meta:
        db_table = "operation_analysis_topology"
        verbose_name = "拓扑图"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None


class Architecture(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, verbose_name="架构图名称", unique=True)
    desc = models.TextField(verbose_name="描述", blank=True, null=True)
    directory = models.ForeignKey(
        Directory, on_delete=models.CASCADE, related_name="architecture", verbose_name="所属目录", null=True, blank=True
    )
    other = JSONField(help_text="架构图其他配置", blank=True, null=True)
    view_sets = JSONField(help_text="架构图视图集配置", default=list)

    class Meta:
        db_table = "operation_analysis_architecture"
        verbose_name = "架构图"

    def __str__(self):
        return self.name

    def has_directory(self):
        return self.directory is not None
