# -- coding: utf-8 --
from copy import deepcopy

from rest_framework import serializers

from apps.alerts.common.notification_target import ORGANIZATION_TARGET, USER_TARGET, VALID_TARGET_TYPES, normalize_notification_target
from apps.alerts.models.alert_operator import AlertAssignment, AlertShield
from apps.system_mgmt.models import Group, User
from apps.system_mgmt.utils.group_filter_mixin import get_unauthorized_group_ids


class AlertAssignmentModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

    def validate_match_rules(self, value):
        for group in value or []:
            for rule in group or []:
                if rule.get("key") == "level" and isinstance(rule.get("value"), list) and not rule["value"]:
                    raise serializers.ValidationError("级别至少选择一个值")
        return value

    def validate_config(self, value):
        """校验升级链配置块（未启用则跳过）。"""
        from apps.alerts.service.escalation_service import EscalationService

        block = (value or {}).get("escalation")
        if not block or not block.get("enabled"):
            return value
        if EscalationService.parse_escalation_config(value) is None:
            raise serializers.ValidationError(
                "升级链配置无效：模式须为 append/替换，至少一层，每层须有处理人且等待时长大于 0"
            )
        return value

    def _normalize_and_validate_target(
        self, raw_target, legacy_personnel, field_label
    ):
        if (
            not isinstance(raw_target, dict)
            or raw_target.get("type") not in VALID_TARGET_TYPES
        ):
            raise serializers.ValidationError(
                {"config": f"{field_label}类型必须为用户或组织"}
            )
        if (
            "include_children" in raw_target
            and not isinstance(raw_target.get("include_children"), bool)
        ):
            raise serializers.ValidationError(
                {"config": f"{field_label}的包含子组织配置必须为布尔值"}
            )
        if (
            raw_target["type"] == USER_TARGET
            and raw_target.get("organization_ids")
        ):
            raise serializers.ValidationError(
                {"config": f"{field_label}不能同时配置用户和组织"}
            )
        if (
            raw_target["type"] == ORGANIZATION_TARGET
            and raw_target.get("usernames")
        ):
            raise serializers.ValidationError(
                {"config": f"{field_label}不能同时配置用户和组织"}
            )

        normalized = normalize_notification_target(
            raw_target,
            legacy_personnel,
        )
        if normalized["type"] == USER_TARGET:
            if not normalized["usernames"]:
                raise serializers.ValidationError(
                    {"config": f"{field_label}的用户模式至少选择一个用户"}
                )
            active_usernames = set(
                User.objects.filter(
                    username__in=normalized["usernames"],
                    disabled=False,
                ).values_list("username", flat=True)
            )
            invalid_usernames = [
                username
                for username in normalized["usernames"]
                if username not in active_usernames
            ]
            if invalid_usernames:
                raise serializers.ValidationError(
                    {
                        "config": (
                            f"{field_label}包含不存在或已禁用的用户: "
                            f"{invalid_usernames}"
                        )
                    }
                )
        elif normalized["type"] == ORGANIZATION_TARGET:
            organization_ids = normalized["organization_ids"]
            if not organization_ids:
                raise serializers.ValidationError(
                    {"config": f"{field_label}的组织模式至少选择一个组织"}
                )
            existing_ids = set(
                Group.objects.filter(id__in=organization_ids).values_list(
                    "id", flat=True
                )
            )
            missing_ids = [
                group_id
                for group_id in organization_ids
                if group_id not in existing_ids
            ]
            if missing_ids:
                raise serializers.ValidationError(
                    {"config": f"{field_label}中的组织不存在: {missing_ids}"}
                )

            request = self.context.get("request")
            if request is not None:
                unauthorized_ids = get_unauthorized_group_ids(
                    request.user, organization_ids
                )
                if unauthorized_ids:
                    raise serializers.ValidationError(
                        {"config": f"{field_label}包含无权选择的组织: {unauthorized_ids}"}
                    )
        return normalized

    def validate(self, attrs):
        attrs = super().validate(attrs)
        config = attrs.get("config")
        if not isinstance(config, dict):
            return attrs

        normalized_config = deepcopy(config)
        changed = False
        if "notification_target" in normalized_config:
            normalized = self._normalize_and_validate_target(
                normalized_config.get("notification_target"),
                attrs.get("personnel"),
                "分派对象",
            )
            normalized_config["notification_target"] = normalized
            attrs["personnel"] = (
                normalized["usernames"]
                if normalized["type"] == USER_TARGET
                else []
            )
            changed = True

        escalation = normalized_config.get("escalation")
        if isinstance(escalation, dict) and isinstance(
            escalation.get("layers"), list
        ):
            normalized_layers = []
            for index, layer in enumerate(escalation["layers"]):
                if not isinstance(layer, dict):
                    normalized_layers.append(layer)
                    continue
                normalized_layer = deepcopy(layer)
                if "notification_target" in normalized_layer:
                    normalized = self._normalize_and_validate_target(
                        normalized_layer.get("notification_target"),
                        normalized_layer.get("personnel"),
                        f"升级层级 {index + 1} 的处理对象",
                    )
                    normalized_layer["notification_target"] = normalized
                    normalized_layer["personnel"] = (
                        normalized["usernames"]
                        if normalized["type"] == USER_TARGET
                        else []
                    )
                    changed = True
                normalized_layers.append(normalized_layer)
            if changed:
                normalized_config["escalation"] = {
                    **escalation,
                    "layers": normalized_layers,
                }

        if changed:
            attrs["config"] = normalized_config
        return attrs

    class Meta:
        model = AlertAssignment
        fields = "__all__"
        extra_kwargs = {
            # 'alert_id': {'read_only': True},
            # 'status': {'required': True},
            # 'operator': {'required': True},
        }


class AlertShieldModelSerializer(serializers.ModelSerializer):
    """
    Serializer for AlertAssignment model.
    This serializer is used to assign alerts to users or teams.
    """

    class Meta:
        model = AlertShield
        fields = "__all__"
        extra_kwargs = {}
