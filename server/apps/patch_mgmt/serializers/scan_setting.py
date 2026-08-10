"""全局扫描设置序列化器"""

from rest_framework import serializers

from apps.core.utils.celery_utils import CeleryUtils
from apps.patch_mgmt.models import ScanSetting
from apps.patch_mgmt.services.notification_config import load_notification_candidates
from apps.patch_mgmt.tasks import run_periodic_compliance_scan
from apps.patch_mgmt.utils.i18n import serializer_message


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
            "notification_enabled",
            "notification_rules",
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
        notification_enabled = attrs.get(
            "notification_enabled",
            self.instance.notification_enabled if self.instance else False,
        )
        notification_rules = attrs.get(
            "notification_rules",
            self.instance.notification_rules if self.instance else [],
        )
        schedule_enabled = attrs.get(
            "is_enabled", self.instance.is_enabled if self.instance else True
        )

        if schedule_enabled and not self.partial:
            required_fields = {
                "frequency": serializer_message(
                    self, "error.frequency_required", "Assessment frequency is required"
                )
            }
            if frequency == "hourly":
                required_fields["hour_interval"] = serializer_message(
                    self,
                    "error.hour_interval_required",
                    "The hourly interval is required",
                )
            elif frequency == "daily":
                required_fields["time"] = serializer_message(
                    self, "error.assessment_time_required", "Assessment time is required"
                )
            elif frequency == "weekly":
                required_fields.update(
                    {
                        "weekday": serializer_message(
                            self, "error.weekday_required", "The weekday is required"
                        ),
                        "time": serializer_message(
                            self,
                            "error.assessment_time_required",
                            "Assessment time is required",
                        ),
                    }
                )
            missing_fields = {
                field: message
                for field, message in required_fields.items()
                if field not in self.initial_data
                or self.initial_data.get(field) in (None, "")
            }
            if missing_fields:
                raise serializers.ValidationError(missing_fields)

        if frequency == "hourly" and (
            hour_interval is None or hour_interval < 1 or hour_interval > 24
        ):
            raise serializers.ValidationError({"hour_interval": serializer_message(self, "error.hour_interval_range", "The hourly interval must be between 1 and 24")})

        if frequency == "weekly" and (
            weekday is None or weekday < 1 or weekday > 7
        ):
            raise serializers.ValidationError({"weekday": serializer_message(self, "error.weekday_range", "The weekday must be between 1 and 7")})

        if frequency in ("daily", "weekly"):
            if not isinstance(time_value, str) or len(time_value.split(":")) != 2:
                raise serializers.ValidationError({"time": serializer_message(self, "error.invalid_time_format", "Time must use the HH:MM format")})
            try:
                hour, minute = map(int, time_value.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError as exc:
                raise serializers.ValidationError({"time": serializer_message(self, "error.invalid_time_format", "Time must use the HH:MM format")}) from exc

        if schedule_enabled and notification_enabled:
            attrs["notification_rules"] = self._validate_notification_rules(
                True,
                notification_rules,
            )
        else:
            # 关闭只改变生效状态：保留服务端已校验过的规则，也避免普通扫描设置
            # 保存依赖系统管理渠道服务。再次开启时会重新执行授权校验。
            attrs["notification_rules"] = (
                self.instance.notification_rules if self.instance else []
            )
        return attrs

    def _validate_notification_rules(self, enabled: bool, rules) -> list[dict]:
        if not isinstance(rules, list):
            raise serializers.ValidationError(
                {"notification_rules": "通知规则必须是列表"}
            )
        if enabled and not rules:
            raise serializers.ValidationError(
                {"notification_rules": "开启通知后至少添加一种通知方式"}
            )
        if not rules:
            return []

        request = self.context.get("request")
        if request is None:
            raise serializers.ValidationError(
                {"notification_rules": "无法校验通知规则的授权范围"}
            )
        candidates = load_notification_candidates(request)
        channel_map = {
            int(item["id"]): item
            for item in candidates["channels"]
            if item.get("id") is not None
        }
        allowed_user_ids = {
            int(item["id"])
            for item in candidates["users"]
            if item.get("id") is not None
        }
        normalized = []
        seen_channel_ids = set()
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条通知规则格式非法"}
                )
            try:
                channel_id = int(rule.get("channel_id"))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条通知方式无效"}
                ) from exc
            if channel_id in seen_channel_ids:
                raise serializers.ValidationError(
                    {"notification_rules": "同一通知方式不能重复添加"}
                )
            channel = channel_map.get(channel_id)
            if channel is None:
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条通知方式不存在或无权使用"}
                )

            receiver_values = rule.get("receivers", [])
            if not isinstance(receiver_values, list):
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条接收人格式非法"}
                )
            try:
                receivers = list(dict.fromkeys(int(value) for value in receiver_values))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条接收人格式非法"}
                ) from exc

            channel_type = str(channel.get("channel_type") or "")
            if channel_type == "nats":
                receivers = []
            elif not receivers:
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条通知方式至少选择一名接收人"}
                )
            elif any(receiver_id not in allowed_user_ids for receiver_id in receivers):
                raise serializers.ValidationError(
                    {"notification_rules": f"第 {index + 1} 条包含不存在或无权选择的接收人"}
                )

            seen_channel_ids.add(channel_id)
            normalized.append(
                {
                    "channel_id": channel_id,
                    "channel_name": str(channel.get("name") or ""),
                    "channel_type": channel_type,
                    "receivers": receivers,
                    "team_id": int(candidates["team_id"]),
                }
            )
        return normalized

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
