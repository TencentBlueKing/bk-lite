"""CMDB 文件对象台账（附件/图片字段的对象存储引用与生命周期记录）。

该表是「方案 C」中的回收台账：每个上传到对象存储的文件一行，记录其
object_key 与生命周期状态，专职服务预上传孤儿追踪与异步 GC。文件本体存
MinIO；字段值的「真相」是图库实例节点上的元数据 JSON 数组。

定位：社区基础设施表（与 ``config_file_version.py`` 同列）。表结构与迁移正常
归属 cmdb app，避免有状态能力下的表/迁移结构错乱；但所有读写**行为**由企业版
``apps.cmdb.enterprise.instance_ops`` 拥有，社区从不主动写它。删除 enterprise 后
此表闲置但无害。
"""

import uuid

from django.db import models


class CmdbFileObjectStatus(object):
    PENDING = "pending"  # 已上传到对象存储、尚未被任何实例提交引用
    COMMITTED = "committed"  # 已被实例保存引用
    ORPHANED = "orphaned"  # 实例/字段删除或文件被移除后待回收

    CHOICES = (
        (PENDING, "待提交"),
        (COMMITTED, "已提交"),
        (ORPHANED, "待回收"),
    )


class CmdbFileObject(models.Model):
    file_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, help_text="文件业务 ID（对外引用）")
    bucket = models.CharField(max_length=128, help_text="对象存储 bucket")
    object_key = models.CharField(max_length=512, unique=True, help_text="对象存储 key")
    file_name = models.CharField(max_length=256, help_text="原始文件名")
    file_size = models.BigIntegerField(default=0, help_text="文件大小（字节）")
    mime_type = models.CharField(max_length=128, blank=True, default="", help_text="MIME 类型")
    model_id = models.CharField(max_length=64, help_text="所属模型 ID")
    attr_id = models.CharField(max_length=128, help_text="所属字段 ID")
    inst_id = models.BigIntegerField(null=True, blank=True, help_text="所属实例 ID（提交前为空）")
    uploader = models.CharField(max_length=128, help_text="上传者用户名")
    status = models.CharField(
        max_length=16,
        choices=CmdbFileObjectStatus.CHOICES,
        default=CmdbFileObjectStatus.PENDING,
        help_text="生命周期状态",
    )
    created_at = models.DateTimeField(auto_now_add=True, help_text="创建时间")
    updated_at = models.DateTimeField(auto_now=True, help_text="更新时间")

    class Meta:
        verbose_name = "CMDB 文件对象"
        verbose_name_plural = "CMDB 文件对象"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["inst_id"]),
            models.Index(fields=["model_id", "attr_id"]),
        ]

    def __str__(self):
        return f"{self.file_name}({self.file_id}:{self.status})"
