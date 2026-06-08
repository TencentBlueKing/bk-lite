from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.mixinx import EncryptMixin
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo


class MemorySpace(MaintainerInfo, TimeInfo, EncryptMixin):
    """记忆空间模型"""

    # 需要加密的配置字段
    ENCRYPTED_CONFIG_FIELDS = ["api_key"]

    SCOPE_PERSONAL = "personal"
    SCOPE_TEAM = "team"
    SCOPE_CHOICES = [
        (SCOPE_PERSONAL, "个人"),
        (SCOPE_TEAM, "团队"),
    ]

    STORAGE_LOCAL = "local"
    STORAGE_MEM0 = "mem0"
    STORAGE_ZEP = "zep"
    STORAGE_CUSTOM = "custom"
    STORAGE_CHOICES = [
        (STORAGE_LOCAL, "本地存储"),
        (STORAGE_MEM0, "Mem0"),
        (STORAGE_ZEP, "Zep"),
        (STORAGE_CUSTOM, "自定义 API"),
    ]

    name = models.CharField(max_length=100, db_index=True, verbose_name=_("名称"))
    introduction = models.TextField(blank=True, default="", verbose_name=_("简介"))
    team = models.JSONField(default=list)
    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_TEAM,
        verbose_name=_("可见范围"),
    )
    write_rule = models.TextField(blank=True, default="", verbose_name=_("写入规则"))
    default_model = models.CharField(max_length=100, blank=True, default="", verbose_name=_("默认模型"))
    storage_type = models.CharField(
        max_length=20,
        choices=STORAGE_CHOICES,
        default=STORAGE_LOCAL,
        verbose_name=_("存储类型"),
    )
    storage_config = models.JSONField(default=dict, blank=True, verbose_name=_("存储配置"))

    class Meta:
        db_table = "memory_mgmt_memoryspace"
        verbose_name = "记忆空间"
        verbose_name_plural = "记忆空间"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """保存时加密敏感配置字段"""
        if self.storage_config:
            config = self.storage_config.copy() if isinstance(self.storage_config, dict) else {}
            for field in self.ENCRYPTED_CONFIG_FIELDS:
                if field in config and config[field] and not self._is_encrypted(config[field]):
                    self.encrypt_field(field, config)
            self.storage_config = config
        super().save(*args, **kwargs)

    def _is_encrypted(self, value: str) -> bool:
        """检查值是否已加密（Fernet 加密的值以 gAAAAA 开头）"""
        if not value or not isinstance(value, str):
            return False
        return value.startswith("gAAAAA")

    def get_decrypted_config(self) -> dict:
        """获取解密后的配置"""
        if not self.storage_config:
            return {}
        config = self.storage_config.copy() if isinstance(self.storage_config, dict) else {}
        for field in self.ENCRYPTED_CONFIG_FIELDS:
            if field in config:
                self.decrypt_field(field, config)
        return config

    def get_masked_config(self) -> dict:
        """获取脱敏后的配置（用于 API 返回）"""
        if not self.storage_config:
            return {}
        config = self.storage_config.copy() if isinstance(self.storage_config, dict) else {}
        for field in self.ENCRYPTED_CONFIG_FIELDS:
            if field in config and config[field]:
                # 显示前缀 + ***
                value = config[field]
                if self._is_encrypted(value):
                    config[field] = "***"
                elif len(value) > 3:
                    config[field] = value[:3] + "***"
                else:
                    config[field] = "***"
        return config


class Memory(MaintainerInfo, TimeInfo):
    """记忆条目模型

    个人记忆：owner_username + owner_domain 确定唯一用户，每个用户在每个记忆空间只有一条记忆
    组织记忆：organization_id 确定唯一组织，每个组织在每个记忆空间只有一条记忆
             owner_username 存储组织名称（用于显示）
    """

    memory_space = models.ForeignKey(
        MemorySpace,
        on_delete=models.CASCADE,
        related_name="memories",
        verbose_name=_("记忆空间"),
    )
    title = models.CharField(max_length=255, db_index=True, verbose_name=_("标题"))
    content = models.TextField(verbose_name=_("内容"))
    owner_username = models.CharField(max_length=150, verbose_name=_("创建者用户名/组织名"), db_index=True)
    owner_domain = models.CharField(max_length=255, verbose_name=_("创建者域"), db_index=True, blank=True, default="")
    organization_id = models.IntegerField(verbose_name=_("组织ID"), db_index=True, null=True, blank=True)

    class Meta:
        db_table = "memory_mgmt_memory"
        verbose_name = "记忆"
        verbose_name_plural = "记忆"
        indexes = [
            models.Index(fields=["owner_username", "owner_domain"]),
            models.Index(fields=["organization_id"]),
        ]

    def __str__(self):
        return self.title


class MemoryWriteCache(models.Model):
    """记忆写入缓存项"""

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待处理"),
        (STATUS_PROCESSING, "处理中"),
    ]

    workflow_id = models.IntegerField(verbose_name=_("工作流ID"), db_index=True)
    node_id = models.CharField(max_length=100, verbose_name=_("节点ID"), db_index=True)
    memory_target_id = models.CharField(max_length=255, verbose_name=_("记忆对象ID"), db_index=True)
    content = models.TextField(verbose_name=_("缓存内容"))
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        verbose_name=_("状态"),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("创建时间"), db_index=True)

    class Meta:
        db_table = "memory_mgmt_memorywritecache"
        verbose_name = "记忆写入缓存"
        verbose_name_plural = "记忆写入缓存"
        indexes = [
            models.Index(
                fields=["workflow_id", "node_id", "memory_target_id", "status", "created_at"],
                name="memory_mgmt_workflo_55002b_idx",
            ),
        ]

    def __str__(self):
        return f"{self.workflow_id}:{self.node_id}:{self.memory_target_id}"
