from django.db import models


class PendingRemoteConfigDeletion(models.Model):
    """本地删除已提交后，尚未确认的 node_mgmt 配置删除。"""

    child_config_ids = models.JSONField(default=list)
    base_config_ids = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "monitor_pending_remote_config_deletion"
