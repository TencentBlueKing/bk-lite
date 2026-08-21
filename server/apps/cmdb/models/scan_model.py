from django.db import models
from django.db.models import JSONField

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.encrypt_collect_password import get_collect_model_passwords
from apps.core.models.maintainer_info import MaintainerInfo
from apps.core.models.time_info import TimeInfo

SCAN_ALLOWED_FAMILIES = frozenset(
    {
        "network",
        "host",
        "physcial_server",
        "mysql",
        "postgresql",
        "mssql",
        "influxdb",
    }
)
SCAN_IP_RANGE_MIN_PREFIX = 21
SCAN_IP_RANGE_MAX_SIZE = 2 ** (32 - SCAN_IP_RANGE_MIN_PREFIX)


def scan_driver_type_for_model(model_id: str) -> str:
    if model_id == "host":
        return CollectDriverTypes.JOB
    return CollectDriverTypes.PROTOCOL


def scan_task_type_for_model(model_id: str) -> str:
    if model_id == "network":
        return CollectPluginTypes.SNMP
    if model_id == "host":
        return CollectPluginTypes.HOST
    return CollectPluginTypes.PROTOCOL


class ScanTask(MaintainerInfo, TimeInfo):
    name = models.CharField(max_length=128, help_text="扫描任务名称")
    team = JSONField(default=list, help_text="关联组织")
    access_point = JSONField(default=list, help_text="接入点")
    ip_ranges = JSONField(default=list, help_text="IP 起止范围列表")
    cloud_region = JSONField(default=dict, help_text="主机扫描云区域")
    families = JSONField(default=list, help_text="勾选的凭据族 / 模型")
    credentials = JSONField(default=dict, help_text="按族存储的凭据池")
    auto_push_monitor = models.BooleanField(default=False, help_text="执行后自动推监控")
    auto_generate_collect = models.BooleanField(default=False, help_text="执行后自动生成采集")
    timeout = models.PositiveSmallIntegerField(default=0, help_text="单个 IP 超时秒数")

    class Meta:
        verbose_name = "扫描任务"
        verbose_name_plural = verbose_name

    def _encrypt_credential_item(self, model_id, raw_item):
        if not isinstance(raw_item, dict):
            return raw_item
        item = dict(raw_item)
        encrypted_fields = get_collect_model_passwords(
            collect_model_id=model_id,
            driver_type=scan_driver_type_for_model(model_id),
        )
        for field_name in encrypted_fields:
            value = item.get(field_name)
            if not value:
                continue
            item[field_name] = CollectModels.encrypt_password(value)
        return item

    def _decrypt_credential_item(self, model_id, raw_item):
        if not isinstance(raw_item, dict):
            return raw_item
        item = dict(raw_item)
        encrypted_fields = get_collect_model_passwords(
            collect_model_id=model_id,
            driver_type=scan_driver_type_for_model(model_id),
        )
        for field_name in encrypted_fields:
            value = item.get(field_name)
            if not value:
                continue
            item[field_name] = CollectModels.decrypt_password(value)
        return item

    @property
    def decrypt_credentials(self):
        raw = self.credentials or {}
        if not isinstance(raw, dict):
            return raw
        decrypted = {}
        for model_id, pool in raw.items():
            if isinstance(pool, list):
                decrypted[model_id] = [self._decrypt_credential_item(model_id, item) for item in pool]
            elif isinstance(pool, dict):
                decrypted[model_id] = self._decrypt_credential_item(model_id, pool)
            else:
                decrypted[model_id] = pool
        return decrypted

    def save(self, *args, **kwargs):
        raw = self.credentials or {}
        if isinstance(raw, dict):
            encrypted = {}
            for model_id, pool in raw.items():
                if isinstance(pool, list):
                    encrypted[model_id] = [self._encrypt_credential_item(model_id, item) for item in pool]
                elif isinstance(pool, dict):
                    encrypted[model_id] = self._encrypt_credential_item(model_id, pool)
                else:
                    encrypted[model_id] = pool
            self.credentials = encrypted
        super().save(*args, **kwargs)


class ScanExecution(TimeInfo):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_FINALIZING = "finalizing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_TIMED_OUT = "timed_out"
    STATUS_CHOICES = (
        (STATUS_PENDING, "待执行"),
        (STATUS_RUNNING, "执行中"),
        (STATUS_FINALIZING, "收口中"),
        (STATUS_COMPLETED, "已完成"),
        (STATUS_FAILED, "失败"),
        (STATUS_TIMED_OUT, "超时"),
    )

    task = models.ForeignKey(ScanTask, on_delete=models.CASCADE, related_name="executions")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_PENDING)
    claim_token = models.CharField(max_length=128, blank=True, default="", help_text="执行领取令牌")
    started_at = models.DateTimeField(blank=True, null=True)
    deadline_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    target_count = models.PositiveIntegerField(default=0)
    received_count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "扫描执行"
        verbose_name_plural = verbose_name
        indexes = [
            models.Index(fields=["task", "status"], name="cmdb_scan_exec_task_status_idx"),
        ]


class ScanFamilyRun(TimeInfo):
    ADMIT_PENDING = "pending"
    ADMIT_ACCEPTED = "accepted"
    ADMIT_DUPLICATE = "duplicate"
    ADMIT_FAILED = "failed"
    ADMIT_CHOICES = (
        (ADMIT_PENDING, "待接纳"),
        (ADMIT_ACCEPTED, "已接纳"),
        (ADMIT_DUPLICATE, "去重跳过"),
        (ADMIT_FAILED, "接纳失败"),
    )

    execution = models.ForeignKey(ScanExecution, on_delete=models.CASCADE, related_name="family_runs")
    model_id = models.CharField(max_length=64)
    driver_type = models.CharField(max_length=32, choices=CollectDriverTypes.CHOICE)
    target_count = models.PositiveIntegerField(default=0)
    received_count = models.PositiveIntegerField(default=0)
    progress_hosts = JSONField(
        default=list,
        help_text="已计入进度的主机（含失败/不可达）；清单仅保留 success",
    )
    admit_status = models.CharField(max_length=32, choices=ADMIT_CHOICES, default=ADMIT_PENDING)

    class Meta:
        verbose_name = "扫描族执行"
        verbose_name_plural = verbose_name
        unique_together = (("execution", "model_id", "driver_type"),)


class ScanHit(TimeInfo):
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_UNREACHABLE = "unreachable"
    STATUS_CHOICES = (
        (STATUS_SUCCESS, "成功"),
        (STATUS_FAILED, "失败"),
        (STATUS_UNREACHABLE, "不可达"),
    )

    execution = models.ForeignKey(ScanExecution, on_delete=models.CASCADE, related_name="hits")
    family_run = models.ForeignKey(ScanFamilyRun, on_delete=models.CASCADE, related_name="hits")
    protocol = models.CharField(max_length=32)
    host = models.CharField(max_length=64)
    port = models.PositiveIntegerField(default=0)
    credential_id = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=32, choices=STATUS_CHOICES)
    soid = models.CharField(max_length=256, blank=True, default="")
    cmdb_model_id = models.CharField(max_length=64, blank=True, default="")
    inst_uuid = models.CharField(max_length=36, blank=True, default="")
    attached_inst_uuid = models.CharField(max_length=36, blank=True, default="")
    # 扫描「生成采集」成功后回写，用于重复点击时按 ID 幂等跳过。
    collect_task_id = models.PositiveIntegerField(null=True, blank=True, default=None, help_text="已生成的采集任务ID")
    error_code = models.CharField(max_length=64, blank=True, default="")
    snapshot = JSONField(default=dict)

    class Meta:
        verbose_name = "扫描命中"
        verbose_name_plural = verbose_name
        unique_together = (("family_run", "host", "port", "credential_id"),)
        indexes = [
            models.Index(fields=["execution", "status"], name="cmdb_scan_hit_exec_status_idx"),
            models.Index(fields=["execution", "host"], name="cmdb_scan_hit_exec_host_idx"),
        ]
