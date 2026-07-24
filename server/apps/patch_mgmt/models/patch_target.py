"""补丁管理独立目标模型"""

from django.db import models
from django_minio_backend import MinioBackend

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.patch_mgmt.constants import (
    ConnectivityStatus,
    OSType,
    PatchTargetSource,
    SSHCredentialType,
    WinRMScheme,
    WinRMTransport,
)

SSH_KEY_BUCKET = "patch-mgmt-private"


def patch_ssh_key_upload_path(instance, filename):
    """SSH 密钥文件上传路径"""
    from datetime import datetime

    now = datetime.now()
    return f"ssh_keys/{now.year}/{now.month:02d}/{now.day:02d}/{filename}"


class PatchTarget(TimeInfo, MaintainerInfo):
    """
    补丁管理独立目标（主机）

    只支持 Ansible 型目标，不复用 job_mgmt.Target 表。
    凭据字段采用密文存储（与 Job Target 一致）。

    SSH 私钥固定存入 patch-mgmt-private，不落本地 media。
    """

    name = models.CharField(max_length=128, verbose_name="名称")
    ip = models.GenericIPAddressField(verbose_name="IP地址")
    os_type = models.CharField(
        max_length=32, choices=OSType.CHOICES, default=OSType.LINUX, verbose_name="操作系统"
    )

    # 云区域（关联 node_mgmt.CloudRegion，不使用外键）
    cloud_region_id = models.BigIntegerField(null=True, blank=True, verbose_name="云区域ID")

    # 目标来源：手动录入 / 节点管理纳入
    source_type = models.CharField(
        max_length=32,
        choices=PatchTargetSource.CHOICES,
        default=PatchTargetSource.MANUAL,
        verbose_name="目标来源",
    )

    # 节点管理来源的节点 ID，用于 Sidecar 路由
    node_id = models.CharField(max_length=64, blank=True, default="", verbose_name="节点ID")

    # CPU 架构（节点管理同步而来；手动录入可留空）
    arch = models.CharField(max_length=32, blank=True, default="", verbose_name="架构")

    # SSH 凭据
    ssh_port = models.IntegerField(default=22, verbose_name="SSH端口")
    ssh_user = models.CharField(max_length=64, blank=True, default="", verbose_name="SSH用户名")
    ssh_credential_type = models.CharField(
        max_length=32,
        choices=SSHCredentialType.CHOICES,
        default=SSHCredentialType.PASSWORD,
        verbose_name="SSH凭据类型",
    )
    ssh_password = models.CharField(max_length=256, blank=True, default="", verbose_name="SSH密码")
    ssh_key_passphrase = models.CharField(max_length=256, blank=True, default="", verbose_name="SSH密钥口令")
    ssh_key_file = models.FileField(
        verbose_name="SSH密钥文件",
        storage=MinioBackend(bucket_name=SSH_KEY_BUCKET),
        upload_to=patch_ssh_key_upload_path,
        blank=True,
        null=True,
    )

    # WinRM 凭据（Windows 目标）
    winrm_port = models.IntegerField(default=5986, verbose_name="WinRM端口")
    winrm_scheme = models.CharField(
        max_length=16, choices=WinRMScheme.CHOICES, default=WinRMScheme.HTTPS, verbose_name="WinRM协议"
    )
    winrm_transport = models.CharField(
        max_length=32, choices=WinRMTransport.CHOICES, default=WinRMTransport.NTLM, verbose_name="WinRM传输方式"
    )
    winrm_user = models.CharField(max_length=64, blank=True, default="", verbose_name="WinRM用户名")
    winrm_password = models.CharField(max_length=256, blank=True, default="", verbose_name="WinRM密码")
    winrm_cert_validation = models.BooleanField(default=True, verbose_name="WinRM证书验证")

    connectivity_status = models.CharField(
        max_length=32,
        choices=ConnectivityStatus.CHOICES,
        default=ConnectivityStatus.UNKNOWN,
        verbose_name="连通性状态",
    )
    last_checked_at = models.DateTimeField(null=True, blank=True, verbose_name="最后连通性检测时间")

    # 组织归属（多组织）
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "补丁管理目标"
        verbose_name_plural = verbose_name
        db_table = "patch_target"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name}({self.ip})"
