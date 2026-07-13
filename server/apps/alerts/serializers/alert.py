# -- coding: utf-8 --
from django.db.models.query import QuerySet
from django.utils import timezone
from rest_framework import serializers
from rest_framework.fields import empty

from apps.alerts.constants import PERMISSION_ALERT
from apps.alerts.constants.constants import AlertStatus, NotifyResultStatus
from apps.alerts.models.models import Alert
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.core.logger import alert_logger as logger
from apps.core.utils.serializers import AuthSerializer
from apps.system_mgmt.models.user import User


class AlertModelSerializer(AuthSerializer):
    """
    Serializer for Alert model.
    """

    permission_key = PERMISSION_ALERT

    event_count = serializers.SerializerMethodField()
    source_names = serializers.SerializerMethodField()
    # 持续时间
    duration = serializers.SerializerMethodField()
    operator_user = serializers.SerializerMethodField()

    # 格式化时间字段
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    first_event_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    last_event_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    incident_name = serializers.SerializerMethodField()
    notify_status = serializers.SerializerMethodField()
    notify_total = serializers.SerializerMethodField()
    notify_records = serializers.SerializerMethodField()

    def __init__(self, instance=None, data=empty, **kwargs):
        super().__init__(instance=instance, data=data, **kwargs)
        try:
            (
                self.alert_notify_result_map,
                self.alert_notify_total_map,
                self.alert_notify_records_map,
            ) = self.set_alert_notification_maps(instance)
        except Exception:
            logger.warning("初始化告警通知结果映射失败", exc_info=True)
            self.alert_notify_result_map = {}
            self.alert_notify_total_map = {}
            self.alert_notify_records_map = {}

    class Meta:
        model = Alert
        exclude = ["events"]
        extra_kwargs = {
            # "events": {"write_only": True},  # events 字段只读
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
            # "operator": {"write_only": True},
            "labels": {"write_only": True},
        }

    def validate_team(self, value):
        team_ids = normalize_team_ids(value)
        request = self.context.get("request")
        if request is None:
            return team_ids
        user = getattr(request, "user", None)
        if user and getattr(user, "is_superuser", False):
            return team_ids
        authorized_group_ids = get_authorized_group_ids(request)
        unauthorized_teams = sorted(set(team_ids) - set(authorized_group_ids))
        if unauthorized_teams:
            raise serializers.ValidationError(f"You are not authorized to assign teams: {unauthorized_teams}")
        return team_ids

    @staticmethod
    def set_alert_notify_result_map(instance):
        result_map, _, _ = AlertModelSerializer.set_alert_notification_maps(instance)
        return result_map

    @staticmethod
    def set_alert_notification_maps(instance):
        from apps.alerts.models import NotifyResult

        if isinstance(instance, (list, tuple, QuerySet)):
            alert_instances = instance
        elif getattr(instance, "alert_id", None):
            alert_instances = [instance]
        else:
            return {}, {}, {}

        alert_ids = [item.alert_id for item in alert_instances if getattr(item, "alert_id", None)]
        if not alert_ids:
            return {}, {}, {}

        status_map = {}
        total_map = {}
        raw_records_map = {}
        usernames = set()
        notify_results = NotifyResult.objects.filter(
            notify_type="alert",
            notify_object__in=alert_ids,
        ).order_by("notify_object", "-notify_time", "-id")

        for notify_result in notify_results:
            notify_object = notify_result.notify_object
            status_map.setdefault(notify_object, []).append(
                notify_result.notify_result == NotifyResultStatus.SUCCESS
            )
            total_map[notify_object] = total_map.get(notify_object, 0) + 1
            records = raw_records_map.setdefault(notify_object, [])
            if len(records) < 5:
                records.append(notify_result)
                usernames.update(str(user) for user in (notify_result.notify_people or []))

        user_map = dict(
            User.objects.filter(username__in=usernames).values_list("username", "display_name")
        ) if usernames else {}
        records_map = {}
        for notify_object, notify_results in raw_records_map.items():
            records_map[notify_object] = [
                {
                    "notify_time": timezone.localtime(item.notify_time).strftime("%Y-%m-%d %H:%M:%S"),
                    "channel": item.notify_channel or "",
                    "channel_name": item.notify_channel_name or item.notify_channel or "",
                    "recipients": [
                        {
                            "username": str(username),
                            "display_name": user_map.get(str(username)) or str(username),
                        }
                        for username in (item.notify_people or [])
                    ],
                    "result": item.notify_result,
                    "failure_reason": item.failure_reason,
                }
                for item in notify_results
            ]

        return status_map, total_map, records_map

    @staticmethod
    def get_duration(obj):
        """
        当前时间- 创建时间
        """
        if not obj.created_at or obj.status not in AlertStatus.ACTIVATE_STATUS:
            return "--"

        # 计算持续时间
        now = timezone.now()
        duration = now - obj.created_at
        total_seconds = int(duration.total_seconds())

        # 计算各个时间单位
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        # 构建格式化字符串
        result = ""
        if days > 0:
            result += f"{days}d "
        if hours > 0:
            result += f"{hours}h "
        if minutes > 0:
            result += f"{minutes}m "
        if seconds > 0 or result == "":
            result += f"{seconds}s"

        return result

    @staticmethod
    def get_source_names(obj):
        """
        Get the names of the sources associated with the alert.
        通过 Alert -> Events -> AlertSource 获取告警源名称
        """
        # 如果使用了注解（推荐）
        if hasattr(obj, "source_names_annotated") and obj.source_names_annotated:
            return obj.source_names_annotated

        # fallback: 通过关联查询获取
        try:
            # Alert -> Events -> AlertSource
            source_names = set()  # 使用set去重
            for event in obj.events.all():
                if event.source:
                    source_names.add(event.source.name)
            return ", ".join(sorted(source_names))
        except Exception:
            logger.warning("获取告警源名称失败", exc_info=True)
            return ""

    @staticmethod
    def get_event_count(obj):
        """
        Get the count of events associated with the alert.
        """
        # 如果使用了注解（推荐）
        if hasattr(obj, "event_count_annotated"):
            return obj.event_count_annotated

        # fallback: 直接计数
        try:
            return obj.events.count()
        except Exception:
            logger.warning("获取告警事件数量失败", exc_info=True)
            return 0

    def get_operator_user(self, obj):
        if not obj.operator:
            return ""
        operator_user_map = self.context.get("operator_user_map")
        if operator_user_map is not None:
            return ", ".join(operator_user_map.get(u, u) for u in obj.operator)
        user_name_list = User.objects.filter(username__in=obj.operator).values_list("display_name", flat=True)
        return ", ".join(list(user_name_list))

    @staticmethod
    def get_incident_name(obj):
        """
        获取关联的事故标题
        """
        # 如果使用了注解（推荐，PostgreSQL）
        if hasattr(obj, "incident_title_annotated") and obj.incident_title_annotated:
            return obj.incident_title_annotated

        # fallback: 通过预加载的关联查询获取（其他数据库）
        try:
            incident_titles = set()
            for incident in obj.incident_set.all():
                if incident.title:
                    incident_titles.add(incident.title)
            return ", ".join(sorted(incident_titles))
        except Exception:
            return ""

    def get_notify_status(self, obj):
        """
        获取告警通知状态
        """
        alert_result = self.alert_notify_result_map.get(obj.alert_id)
        if not alert_result:
            return ""
        if all(alert_result):
            return NotifyResultStatus.SUCCESS
        if any(alert_result):
            return NotifyResultStatus.PARTIAL_SUCCESS
        return NotifyResultStatus.FAILED

    def get_notify_total(self, obj):
        return self.alert_notify_total_map.get(obj.alert_id, 0)

    def get_notify_records(self, obj):
        return self.alert_notify_records_map.get(obj.alert_id, [])
