from rest_framework import viewsets
from rest_framework.decorators import action

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.utils.current_team_scope import resolve_current_team_data_scope
from apps.core.utils.web_utils import WebUtils
from apps.monitor.models import MonitorInstance, PolicyGroup, PolicyGroupDefault
from apps.monitor.services.policy_group import PolicyGroupService


class PolicyGroupViewSet(viewsets.ViewSet):
    def list(self, request):
        scope = resolve_current_team_data_scope(request)
        organization = int(scope.current_team)
        object_id = request.query_params.get("monitor_object_id")
        queryset = PolicyGroup.objects.filter(organization=organization).prefetch_related("rules__plugin")
        if object_id not in (None, ""):
            queryset = queryset.filter(monitor_object_id=object_id)
        default_id = None
        if object_id not in (None, ""):
            pointer = PolicyGroupDefault.objects.filter(organization=organization, monitor_object_id=object_id).first()
            default_id = pointer.policy_group_id if pointer else None
        data = []
        for group in queryset.order_by("id"):
            data.append(
                {
                    "id": group.id,
                    "name": group.name,
                    "origin": group.origin,
                    "is_default": group.id == default_id,
                    "rules": [
                        {
                            "name": rule.name,
                            "plugin_id": rule.plugin_id,
                            "plugin_name": rule.plugin.name,
                        }
                        for rule in group.rules.all()
                    ],
                }
            )
        return WebUtils.response_success(data)

    @action(methods=["post"], detail=False)
    def join(self, request):
        scope = resolve_current_team_data_scope(request)
        group = PolicyGroup.objects.filter(id=request.data.get("group_id"), organization=int(scope.current_team)).first()
        if group is None:
            raise BaseAppException("策略组不存在")
        instance_ids = request.data.get("instance_ids") or []
        for instance in MonitorInstance.objects.filter(id__in=instance_ids, monitor_object_id=group.monitor_object_id):
            PolicyGroupService.join(instance=instance, group=group, operator=scope.username or "system")
        return WebUtils.response_success({"count": len(instance_ids)})

    @action(methods=["post"], detail=False)
    def leave(self, request):
        scope = resolve_current_team_data_scope(request)
        instance_ids = request.data.get("instance_ids") or []
        for instance in MonitorInstance.objects.filter(id__in=instance_ids):
            PolicyGroupService.leave(instance=instance, operator=scope.username or "system")
        return WebUtils.response_success({"count": len(instance_ids)})
