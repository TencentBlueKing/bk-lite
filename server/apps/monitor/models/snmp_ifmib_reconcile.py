from django.db import models


class SnmpIfmibReconcileState(models.Model):
    """IF-MIB 存量配置补偿的持久游标与数据库所有权凭证。"""

    version = models.PositiveIntegerField(primary_key=True)
    owner_token = models.CharField(max_length=64, blank=True, default="")
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    cursor_created_at = models.DateTimeField(null=True, blank=True)
    cursor_config_id = models.CharField(max_length=255, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "monitor_snmp_ifmib_reconcile_state"
