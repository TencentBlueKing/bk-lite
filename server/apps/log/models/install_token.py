from django.db import models
from django.db.models import F, Q


class K8sInstallToken(models.Model):
    """跨进程共享的 K8s 日志采集安装令牌。"""

    token_hash = models.CharField(max_length=64, primary_key=True, verbose_name="令牌摘要")
    cluster_name = models.CharField(max_length=200, verbose_name="集群名称")
    cloud_region_id = models.CharField(max_length=200, verbose_name="云区域 ID")
    config_type = models.CharField(max_length=20, default="log", verbose_name="配置类型")
    usage_count = models.PositiveSmallIntegerField(default=0, verbose_name="已使用次数")
    max_usage = models.PositiveSmallIntegerField(default=5, verbose_name="最大使用次数")
    expires_at = models.DateTimeField(db_index=True, verbose_name="过期时间")

    class Meta:
        db_table = "log_k8s_install_token"
        verbose_name = "K8s 日志采集安装令牌"
        verbose_name_plural = "K8s 日志采集安装令牌"
        constraints = [
            models.CheckConstraint(
                check=Q(max_usage__gt=0),
                name="log_k8s_token_max_usage_gt_0",
            ),
            models.CheckConstraint(
                check=Q(usage_count__lte=F("max_usage")),
                name="log_k8s_token_usage_lte_max",
            ),
        ]
