# -- coding: utf-8 --
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
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


def _format_alert_duration(total_seconds: int) -> str:
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

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


class AlertModelSerializer(AuthSerializer):
    """
    Serializer for Alert model.
    """

    permission_key = PERMISSION_ALERT

    event_count = serializers.SerializerMethodField()
    # 持续时间
    duration = serializers.SerializerMethodField()
    operator_user = serializers.SerializerMethodField()

    # 格式化时间字段
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    first_event_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    last_event_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    closed_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True, allow_null=True)
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
            "closed_at": {"read_only": True},
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
        notify_result_filter = NotifyResult.objects.filter(
            notify_type="alert",
            notify_object__in=alert_ids,
        )

        aggregate_rows = notify_result_filter.values("notify_object").annotate(
            total=Count("id"),
            success=Count("id", filter=Q(notify_result=NotifyResultStatus.SUCCESS)),
        )
        for row in aggregate_rows:
            notify_object = row["notify_object"]
            total = row["total"]
            success = row["success"]
            total_map[notify_object] = total
            if success == total:
                status_map[notify_object] = [True]
            elif success == 0:
                status_map[notify_object] = [False]
            else:
                status_map[notify_object] = [True, False]

        latest_notify_results = (
            notify_result_filter.annotate(
                row_number=Window(
                    expression=RowNumber(),
                    partition_by=[F("notify_object")],
                    order_by=[F("notify_time").desc(), F("id").desc()],
                )
            )
            .filter(row_number__lte=5)
            .order_by("notify_object", "-notify_time", "-id")
        )

        for notify_result in latest_notify_results:
            notify_object = notify_result.notify_object
            records = raw_records_map.setdefault(notify_object, [])
            records.append(notify_result)
            usernames.update(str(user) for user in (notify_result.notify_people or []))

        user_map = dict(User.objects.filter(username__in=usernames).values_list("username", "display_name")) if usernames else {}
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
        """初次事件时间到关闭时间；未关闭则到当前时间。"""
        start_at = getattr(obj, "first_event_time", None) or getattr(obj, "created_at", None)
        if not start_at:
            return "--"

        closed_at = getattr(obj, "closed_at", None)
        if closed_at:
            end_at = closed_at
        elif obj.status in AlertStatus.ACTIVATE_STATUS or obj.status == AlertStatus.RESOLVED:
            end_at = timezone.now()
        else:
            return "--"

        total_seconds = int((end_at - start_at).total_seconds())
        return _format_alert_duration(max(total_seconds, 0))

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
