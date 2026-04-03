"""目标管理模型"""

from django.db import models
from django_minio_backend import MinioBackend

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import CredentialSource, ExecutorDriver, OSType, SSHCredentialType, WinRMScheme, WinRMTransport

# SSH 密钥文件存储 bucket
SSH_KEY_BUCKET = "job-mgmt-private"


def ssh_key_upload_path(instance, filename):
    """SSH 密钥文件上传路径"""
    from datetime import datetime

    now = datetime.now()
    return f"ssh_keys/{now.year}/{now.month:02d}/{now.day:02d}/{filename}"


class Target(TimeInfo, MaintainerInfo):
    """
    执行目标（主机）

    手动新增的目标，使用 cloud_region_id + SSH/WinRM 凭据，通过 execute_ssh / download_to_remote 执行。
    """

    name = models.CharField(max_length=128, verbose_name="名称")
    ip = models.GenericIPAddressField(verbose_name="IP地址")
    os_type = models.CharField(max_length=32, choices=OSType.CHOICES, default=OSType.LINUX, verbose_name="操作系统")

    # 云区域（关联 node_mgmt.CloudRegion，不使用外键）
    cloud_region_id = models.BigIntegerField(null=True, blank=True, verbose_name="云区域ID")

    # 节点ID（预留字段）
    node_id = models.CharField(max_length=64, blank=True, default="", verbose_name="节点ID")

    # 执行驱动
    driver = models.CharField(max_length=32, choices=ExecutorDriver.CHOICES, default=ExecutorDriver.ANSIBLE, verbose_name="执行驱动")

    # 凭据来源
    credential_source = models.CharField(max_length=32, choices=CredentialSource.CHOICES, default=CredentialSource.MANUAL, verbose_name="凭据来源")

    # 凭据管理方式时的凭据ID（预留字段）
    credential_id = models.CharField(max_length=64, blank=True, default="", verbose_name="凭据ID")

    # 手动录入时的 SSH 凭据
    ssh_port = models.IntegerField(default=22, verbose_name="SSH端口")
    ssh_user = models.CharField(max_length=64, blank=True, default="", verbose_name="SSH用户名")
    ssh_credential_type = models.CharField(
        max_length=32, choices=SSHCredentialType.CHOICES, default=SSHCredentialType.PASSWORD, verbose_name="SSH凭据类型"
    )
    ssh_password = models.CharField(max_length=256, blank=True, default="", verbose_name="SSH密码")
    ssh_key_passphrase = models.CharField(max_length=256, blank=True, default="", verbose_name="SSH密钥口令")

    # SSH 密钥文件（存储到 MinIO）
    ssh_key_file = models.FileField(
        verbose_name="SSH密钥文件",
        storage=MinioBackend(bucket_name=SSH_KEY_BUCKET),
        upload_to=ssh_key_upload_path,
        blank=True,
        null=True,
    )

    # 手动录入时的 WinRM 凭据 (Windows)
    winrm_port = models.IntegerField(default=5986, verbose_name="WinRM端口")
    winrm_scheme = models.CharField(max_length=16, choices=WinRMScheme.CHOICES, default=WinRMScheme.HTTPS, verbose_name="WinRM协议")
    winrm_transport = models.CharField(max_length=32, choices=WinRMTransport.CHOICES, default=WinRMTransport.NTLM, verbose_name="WinRM传输方式")
    winrm_user = models.CharField(max_length=64, blank=True, default="", verbose_name="WinRM用户名")
    winrm_password = models.CharField(max_length=256, blank=True, default="", verbose_name="WinRM密码")
    winrm_cert_validation = models.BooleanField(default=True, verbose_name="WinRM证书验证")

    # 组织归属（多组织）
    team = models.JSONField(default=list, verbose_name="团队ID列表")

    class Meta:
        verbose_name = "执行目标"
        verbose_name_plural = verbose_name
        db_table = "job_target"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}({self.ip})"

    @property
    def is_manual_credential(self) -> bool:
        """是否为手动录入凭据"""
        return self.credential_source == CredentialSource.MANUAL

    @property
    def is_password_auth(self) -> bool:
        """是否为密码认证"""
        return self.ssh_credential_type == SSHCredentialType.PASSWORD

    @property
    def ssh_key_file_name(self) -> str:
        """SSH密钥文件名（兼容属性）"""
        if self.ssh_key_file:
            return self.ssh_key_file.name.split("/")[-1]
        return ""
