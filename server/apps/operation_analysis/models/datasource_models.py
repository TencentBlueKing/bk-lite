# -- coding: utf-8 --
# @File: datasource_models.py
# @Time: 2025/11/3 16:07
# @Author: windyzhao
from django.db import models
from django.db.models import JSONField

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.core.models.group_info import Groups
from apps.core.utils.crypto.password_crypto import PasswordCrypto
from apps.operation_analysis.constants.constants import SECRET_KEY


class NameSpace(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, verbose_name="命名空间名称", unique=True)
    namespace = models.CharField(max_length=64, verbose_name="NATS命名空间", default="bklite",
                                  help_text="NATS服务端的命名空间,用于消息主题前缀")
    account = models.CharField(max_length=64, verbose_name="账号")
    password = models.CharField(max_length=128, verbose_name="密码")
    domain = models.CharField(max_length=255, verbose_name="域名")
    enable_tls = models.BooleanField(default=False, verbose_name="启用TLS", 
                                      help_text="是否使用TLS安全连接(tls://)")
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

    def _is_password_encrypted(self):
        """
        判断密码是否已经加密
        加密后的密码特征:
        1. 长度 >= 44 (AES加密后base64编码的最小长度)
        2. 能够成功解密
        
        :return: True 表示已加密，False 表示明文
        """
        if not self.password:
            return False
        
        # 尝试解密，如果成功说明已加密
        try:
            crypto = PasswordCrypto(SECRET_KEY)
            crypto.decrypt(self.password)
            return True
        except Exception:
            # 解密失败，说明是明文密码
            return False

    def save(self, *args, **kwargs):
        # 只有在密码未加密时才进行加密
        if self.password and not self._is_password_encrypted():
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


class DataSourceAPIModel(MaintainerInfo, TimeInfo, Groups):
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
