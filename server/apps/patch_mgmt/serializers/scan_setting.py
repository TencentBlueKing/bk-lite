"""全局扫描设置序列化器"""

from rest_framework import serializers

from apps.core.utils.celery_utils import CeleryUtils
from apps.patch_mgmt.models import ScanSetting
from apps.patch_mgmt.tasks import run_periodic_compliance_scan


class ScanSettingSerializer(serializers.ModelSerializer):
    """全局扫描设置序列化器"""

    class Meta:
        model = ScanSetting
        fields = [
            "id",
            "frequency",
            "hour_interval",
            "weekday",
            "time",
            "is_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        frequency = attrs.get(
            "frequency", self.instance.frequency if self.instance else "daily"
        )
        hour_interval = attrs.get(
            "hour_interval", self.instance.hour_interval if self.instance else 1
        )
        weekday = attrs.get("weekday", self.instance.weekday if self.instance else 1)
        time_value = attrs.get("time", self.instance.time if self.instance else "02:00")

        if frequency == "hourly" and (
            hour_interval is None or hour_interval < 1 or hour_interval > 24
        ):
            raise serializers.ValidationError({"hour_interval": "小时间隔必须在 1-24 之间"})

        if frequency == "weekly" and (
            weekday is None or weekday < 1 or weekday > 7
        ):
            raise serializers.ValidationError({"weekday": "周几必须在 1-7 之间"})

        if frequency in ("daily", "weekly"):
            if not isinstance(time_value, str) or len(time_value.split(":")) != 2:
                raise serializers.ValidationError({"time": "时间格式必须为 HH:MM"})
            try:
                hour, minute = map(int, time_value.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError as exc:
                raise serializers.ValidationError({"time": "时间格式必须为 HH:MM"}) from exc

        return attrs

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)
        self._sync_periodic_task(instance)
        return instance

    def _sync_periodic_task(self, instance: ScanSetting):
        """根据配置同步 Celery 周期任务"""
        task_name = "patch_mgmt_periodic_compliance_scan"
        if not instance.is_enabled:
            CeleryUtils.disable_periodic_task(task_name)
            return

        crontab = self._build_crontab(instance)
        CeleryUtils.create_or_update_periodic_task(
            name=task_name,
            crontab=crontab,
            task=run_periodic_compliance_scan.name,
            enabled=True,
        )

    @staticmethod
    def _build_crontab(instance: ScanSetting):
        """将 ScanSetting 转换为平台调度器使用的五段 crontab。"""
        if instance.frequency == "hourly":
            return f"0 */{instance.hour_interval} * * *"
        if instance.frequency == "daily":
            hour, minute = instance.time.split(":")
            return f"{minute} {hour} * * *"
        # weekly
        hour, minute = instance.time.split(":")
        return f"{minute} {hour} * * {instance.weekday % 7}"
