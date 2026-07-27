from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.models import MonitorInstance, MonitorObject


class MonitorObjectCleanupPolicyService:
    """清理策略唯一写入口，负责校验并重置累计周期。"""

    @classmethod
    @transaction.atomic
    def configure(cls, monitor_object, *, policy, timeout_days=1):
        target = MonitorObject.objects.select_for_update().get(pk=monitor_object.pk)
        if target.parent_id is not None or target.level != "base":
            raise ValidationAppException("清理策略只能配置在一级监控对象")
        if policy not in dict(MonitorObject.CLEANUP_POLICY_CHOICES):
            raise ValidationAppException("清理策略不合法")
        if type(timeout_days) is not int or not 1 <= timeout_days <= 365:
            raise ValidationAppException("超时清理天数必须是 1～365 的整数")

        target.cleanup_policy = policy
        target.cleanup_timeout_days = timeout_days
        target.cleanup_policy_effective_at = timezone.now()
        target.save(
            update_fields=[
                "cleanup_policy",
                "cleanup_timeout_days",
                "cleanup_policy_effective_at",
                "updated_at",
            ]
        )

        affected_object_ids = list(target.children.values_list("id", flat=True))
        affected_object_ids.append(target.id)
        MonitorInstance.objects.filter(
            auto=True, monitor_object_id__in=affected_object_ids
        ).update(missing_duration_seconds=0)
        return target
