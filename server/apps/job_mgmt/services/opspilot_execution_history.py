"""OpsPilot 查询作业记录时只加载列表字段，按作业号继续翻页。"""

from datetime import timedelta

from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from apps.core.utils.license_capacity import filter_permission_map
from apps.core.utils.permission_utils import get_instance_permission_map, get_permission_rules
from apps.core.utils.user_group import normalize_user_group_ids
from apps.core.utils.viewset_utils import build_json_membership_query
from apps.job_mgmt.models import JobExecution
from apps.system_mgmt.services.user_access import is_account_expired


class ExecutionHistoryFilter(serializers.Serializer):
    script_id = serializers.IntegerField(required=False, min_value=1, max_value=2**63 - 1)
    scheduled_task_id = serializers.IntegerField(required=False, min_value=1, max_value=2**63 - 1)
    start_time = serializers.DateTimeField(required=False)
    end_time = serializers.DateTimeField(default=timezone.now)
    days = serializers.IntegerField(default=7, min_value=1, max_value=3650)
    limit = serializers.IntegerField(default=20, min_value=1, max_value=100)
    cursor = serializers.IntegerField(required=False, min_value=1, max_value=2**63 - 1)

    def validate(self, attrs):
        if "start_time" not in attrs:
            try:
                attrs["start_time"] = attrs["end_time"] - timedelta(days=attrs["days"])
            except OverflowError:
                raise serializers.ValidationError("查询起始时间超出范围") from None
        if attrs["start_time"] >= attrs["end_time"]:
            raise serializers.ValidationError("start_time 必须早于 end_time")
        return attrs


def _visible_executions(queryset, actor):
    from apps.system_mgmt.models import User
    from apps.system_mgmt.nats.auth import build_user_authorization_context

    team = actor["team"]
    user = User.objects.filter(username=actor["user"], domain=actor["domain"], disabled=False).first()
    if user is None or is_account_expired(user):
        return None
    user.group_list = normalize_user_group_ids(user.group_list)
    auth = build_user_authorization_context(user)
    if team not in normalize_user_group_ids(auth["group_list"]):
        return None
    if not auth["is_superuser"] and "job_record-View" not in filter_permission_map(auth["permission"]).get("job", ()):
        return None
    scoped = queryset.filter(build_json_membership_query(queryset, "team", [team]))
    if auth["is_superuser"]:
        return scoped
    rules = get_permission_rules(user, team, "job_mgmt", "job")
    if not isinstance(rules, dict):
        return scoped.none()
    if team in normalize_user_group_ids(rules.get("team")):
        return scoped
    return scoped.filter(pk__in=get_instance_permission_map(rules))


def list_executions(actor, body):
    filters = ExecutionHistoryFilter(data=body)
    if not filters.is_valid():
        field, messages = next(iter(filters.errors.items()))
        return {"result": False, "message": f"{field}: {messages[0]}"}
    params = filters.validated_data
    queryset = JobExecution.objects.filter(created_at__gte=params["start_time"], created_at__lt=params["end_time"])
    for field in ("script_id", "scheduled_task_id"):
        if field in params:
            queryset = queryset.filter(**{field: params[field]})
    if "cursor" in params:
        queryset = queryset.filter(pk__lt=params["cursor"])
    queryset = _visible_executions(queryset, actor)
    if queryset is None:
        return {"result": False, "message": "无权查看当前组织的作业记录"}
    limit = params["limit"]
    summaries = queryset.order_by("-pk").values(
        "name",
        "script_id",
        "scheduled_task_id",
        "job_type",
        "trigger_source",
        "status",
        "created_at",
        "started_at",
        "finished_at",
        "total_count",
        "success_count",
        "failed_count",
        task_id=F("pk"),
    )
    rows = list(summaries[: limit + 1])
    items = rows[:limit]
    for item in items:
        for field in ("created_at", "started_at", "finished_at"):
            if item[field] is not None:
                item[field] = item[field].isoformat()
    return {
        "result": True,
        "data": {
            "items": items,
            "next_cursor": items[-1]["task_id"] if len(rows) > limit else None,
            "start_time": params["start_time"].isoformat(),
            "end_time": params["end_time"].isoformat(),
        },
    }
