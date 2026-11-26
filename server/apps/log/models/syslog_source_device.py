from datetime import timedelta

from django.db import models

SYSLOG_SOURCE_DEVICE_ACTIVE_WINDOW = timedelta(hours=24)
SYSLOG_SOURCE_DEVICE_DISCOVER_WINDOW = timedelta(minutes=10)


class SyslogSourceDevice(models.Model):
    CLOUD_REGION_ID_MAX_LENGTH = 64
    SOURCE_IP_MAX_LENGTH = 128
    HOSTNAME_MAX_LENGTH = 255

    cloud_region_id = models.CharField(max_length=CLOUD_REGION_ID_MAX_LENGTH, verbose_name="云区域ID")
    source_ip = models.CharField(max_length=SOURCE_IP_MAX_LENGTH, verbose_name="源IP")
    hostname = models.CharField(max_length=HOSTNAME_MAX_LENGTH, blank=True, default="", verbose_name="主机名")
    first_seen = models.DateTimeField(verbose_name="首次收到")
    last_seen = models.DateTimeField(verbose_name="最近收到")

    class Meta:
        verbose_name = "syslog来源设备"
        verbose_name_plural = "syslog来源设备"
        constraints = [
            models.UniqueConstraint(
                fields=("cloud_region_id", "source_ip", "hostname"),
                name="log_syslog_source_device_identity_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["last_seen"], name="log_syslog_src_last_seen_idx"),
        ]
