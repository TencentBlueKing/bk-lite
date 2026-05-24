# -- coding: utf-8 --
from rest_framework import serializers

from apps.alerts.constants import PERMISSION_EVENT
from apps.alerts.models.models import Event
from apps.alerts.utils.permission_scope import get_authorized_group_ids, normalize_team_ids
from apps.core.utils.serializers import AuthSerializer


class EventModelSerializer(AuthSerializer):
    """
    Serializer for Event model.
    """

    permission_key = PERMISSION_EVENT

    # 格式化时间字段
    start_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_time = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    source_name = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = "__all__"
        extra_kwargs = {
            # "events": {"write_only": True},  # events 字段只读
            "start_time": {"read_only": True},
            "end_time": {"read_only": True},
            "labels": {"write_only": True},
            # "raw_data": {"write_only": True},
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
    def get_source_name(obj):
        """
        Get the names of the sources associated with the alert.
        通过 Alert -> Events -> AlertSource 获取告警源名称
        """
        # 如果使用了注解（推荐）
        return obj.source.name
