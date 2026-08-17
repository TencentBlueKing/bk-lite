"""目标管理模型"""

from django.db import models, transaction
from django_minio_backend import MinioBackend

from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo
from apps.job_mgmt.constants import CredentialSource, ExecutorDriver, OSType, SSHCredentialType, WinRMScheme, WinRMTransport
from apps.job_mgmt.utils.team_authz import normalize_authorized_team_ids, normalize_team

# SSH 密钥文件存储 bucket
SSH_KEY_BUCKET = "job-mgmt-private"


def ssh_key_upload_path(instance, filename):
    """SSH 密钥文件上传路径"""
    from datetime import datetime

    now = datetime.now()
    return f"ssh_keys/{now.year}/{now.month:02d}/{now.day:02d}/{filename}"


class TargetQuerySet(models.QuerySet):
    """确保所有批量团队写入都同步授权投影。"""

    def update(self, **kwargs):
        if "team" not in kwargs:
            return super().update(**kwargs)
        with transaction.atomic():
            target_ids = list(self.select_for_update().values_list("id", flat=True))
            updated = super().update(**kwargs)
            target_teams = list(self.model._base_manager.filter(id__in=target_ids).values_list("id", "team"))
            _replace_target_team_memberships(target_teams)
            return updated

    def bulk_create(self, objs, **kwargs):
        if kwargs.get("ignore_conflicts") or kwargs.get("update_conflicts"):
            raise ValueError("Target.bulk_create 不支持冲突忽略/更新，请使用原子 save 或 update")
        with transaction.atomic():
            created = super().bulk_create(objs, **kwargs)
            if any(target.pk is None for target in created):
                raise RuntimeError("当前数据库不支持安全同步 Target.bulk_create，请逐条 save")
            _replace_target_team_memberships((target.pk, target.team) for target in created)
            return created


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

    objects = TargetQuerySet.as_manager()

    class Meta:
        verbose_name = "执行目标"
        verbose_name_plural = verbose_name
        db_table = "job_target"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}({self.ip})"

    def save(self, *args, **kwargs):
        """将目标主体与团队授权投影作为同一事务提交。"""
        update_fields = kwargs.get("update_fields")
        with transaction.atomic():
            if self.pk and not self._state.adding:
                type(self).objects.select_for_update().filter(pk=self.pk).exists()
            result = super().save(*args, **kwargs)
            if update_fields is None or "team" in update_fields:
                _replace_target_team_memberships([(self.pk, self.team)])
            return result

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


class TargetTeamMembership(models.Model):
    """目标团队 JSON 字段的可索引关系投影。"""

    target = models.ForeignKey(Target, related_name="team_memberships", on_delete=models.CASCADE)
    team_id = models.BigIntegerField()

    class Meta:
        db_table = "job_target_team_membership"
        constraints = [models.UniqueConstraint(fields=["target", "team_id"], name="uniq_job_target_team")]
        indexes = [models.Index(fields=["team_id", "target"], name="job_target_team_idx")]


def _replace_target_team_memberships(target_teams):
    """在调用方事务内用 Target.team 原子替换授权投影。"""
    normalized = []
    target_ids = []
    for target_id, team in target_teams:
        target_ids.append(target_id)
        team_ids = normalize_team(team) | normalize_authorized_team_ids(team if isinstance(team, list) else [team])
        normalized.extend(TargetTeamMembership(target_id=target_id, team_id=team_id) for team_id in team_ids)
    if not target_ids:
        return
    TargetTeamMembership.objects.filter(target_id__in=target_ids).delete()
    TargetTeamMembership.objects.bulk_create(
        normalized,
        ignore_conflicts=True,
    )
