from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import LLMSkill, SkillChannel
from apps.opspilot.serializers.skill_channel_serializer import SkillChannelSerializer
from apps.system_mgmt.utils.operation_log_utils import log_operation


class SkillChannelViewSet(viewsets.ModelViewSet):
    """智能体渠道发布绑定 CRUD / 启停。权限：有 Skill 管理组即可（skill_setting-Edit）。"""

    serializer_class = SkillChannelSerializer
    queryset = SkillChannel.objects.all().select_related("skill")
    http_method_names = ["get", "post", "put", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = SkillChannel.objects.all().select_related("skill")
        skill_id = self.request.query_params.get("skill_id") or self.request.data.get("skill")
        if skill_id:
            qs = qs.filter(skill_id=skill_id)
        return qs.order_by("-id")

    def _get_managed_skill(self, request, skill_id) -> LLMSkill | JsonResponse:
        skill = get_object_or_404(LLMSkill, id=skill_id)
        if request.user.is_superuser:
            return skill
        helper = AuthViewSet()
        helper.permission_key = "skill"
        current_team = request.COOKIES.get("current_team", "0")
        include_children = request.COOKIES.get("include_children", "0") == "1"
        if not helper.get_has_permission(request.user, skill, current_team, include_children=include_children):
            return JsonResponse({"result": False, "message": "无权管理该智能体渠道"}, status=403)
        return skill

    @HasPermission("skill_setting-View")
    def list(self, request, *args, **kwargs):
        skill_id = request.query_params.get("skill_id")
        if not skill_id:
            return JsonResponse({"result": False, "message": "skill_id 必填"}, status=400)
        managed = self._get_managed_skill(request, skill_id)
        if isinstance(managed, JsonResponse):
            return managed
        queryset = self.get_queryset().filter(skill_id=skill_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response({"result": True, "data": serializer.data})

    @HasPermission("skill_setting-Edit")
    def create(self, request, *args, **kwargs):
        skill_id = request.data.get("skill")
        if not skill_id:
            return JsonResponse({"result": False, "message": "skill 必填"}, status=400)
        managed = self._get_managed_skill(request, skill_id)
        if isinstance(managed, JsonResponse):
            return managed
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        log_operation(request, "create", "opspilot", f"创建智能体渠道: skill={skill_id} type={serializer.data.get('channel_type')}")
        return Response({"result": True, "data": serializer.data}, status=status.HTTP_201_CREATED)

    @HasPermission("skill_setting-Edit")
    def update(self, request, *args, **kwargs):
        instance: SkillChannel = self.get_object()
        managed = self._get_managed_skill(request, instance.skill_id)
        if isinstance(managed, JsonResponse):
            return managed
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        log_operation(request, "update", "opspilot", f"更新智能体渠道: {instance.id}")
        return Response({"result": True, "data": serializer.data})

    @HasPermission("skill_setting-Edit")
    def destroy(self, request, *args, **kwargs):
        instance: SkillChannel = self.get_object()
        managed = self._get_managed_skill(request, instance.skill_id)
        if isinstance(managed, JsonResponse):
            return managed
        channel_id = instance.id
        instance.delete()
        log_operation(request, "delete", "opspilot", f"删除智能体渠道: {channel_id}")
        return Response({"result": True})

    @HasPermission("skill_setting-Edit")
    @action(methods=["POST"], detail=True)
    def set_enabled(self, request, pk=None):
        instance: SkillChannel = self.get_object()
        managed = self._get_managed_skill(request, instance.skill_id)
        if isinstance(managed, JsonResponse):
            return managed
        enabled = bool(request.data.get("enabled"))
        instance.enabled = enabled
        instance.save(update_fields=["enabled", "updated_at"])
        log_operation(request, "update", "opspilot", f"{'启用' if enabled else '下线'}智能体渠道: {instance.id}")
        return Response({"result": True, "data": self.get_serializer(instance).data})
