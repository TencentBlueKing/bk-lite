from django.db import transaction
from django.utils import timezone

from apps.core.exceptions.base_app_exception import ValidationAppException
from apps.monitor.models import MonitorInstance, MonitorObject


class MonitorObjectCleanupPolicyService:
    """清理策略唯一写入口，负责校验并重置累计周期。"""

    @classmethod
    @transaction.atomic
    def configure(
        cls,
        monitor_object,
        *,
        policy,
        timeout_value=None,
        timeout_unit=None,
        timeout_days=None,
    ):
        target = MonitorObject.objects.select_for_update().get(pk=monitor_object.pk)
        if target.parent_id is not None or target.level != "base":
            raise ValidationAppException("清理策略只能配置在一级监控对象")
        if policy not in dict(MonitorObject.CLEANUP_POLICY_CHOICES):
            raise ValidationAppException("清理策略不合法")
        if timeout_value is None:
            timeout_value = timeout_days if timeout_days is not None else 1
        if timeout_unit is None:
            timeout_unit = MonitorObject.CLEANUP_TIMEOUT_UNIT_DAY
        max_value = MonitorObject.CLEANUP_TIMEOUT_MAX_BY_UNIT.get(timeout_unit)
        if max_value is None:
            raise ValidationAppException("超时时间单位不合法")
        if type(timeout_value) is not int or not 1 <= timeout_value <= max_value:
            unit_label = MonitorObject.CLEANUP_TIMEOUT_UNIT_LABELS[timeout_unit]
            raise ValidationAppException(f"超时时间必须是 1～{max_value} {unit_label}的整数")

        target.cleanup_policy = policy
        target.cleanup_timeout_days = timeout_value
        target.cleanup_timeout_unit = timeout_unit
        target.cleanup_policy_effective_at = timezone.now()
        target.save(
            update_fields=[
                "cleanup_policy",
                "cleanup_timeout_days",
                "cleanup_timeout_unit",
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
