from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.decorators.api_permission import HasPermission
from apps.core.logger import opspilot_logger as logger
from apps.core.utils.viewset_utils import AuthViewSet
from apps.opspilot.models import LLMSkill, SkillChannel
from apps.opspilot.serializers.skill_channel_serializer import SkillChannelSerializer
from apps.opspilot.services.skill_channel_chat_service import (
    SkillChannelChatError,
    get_skill_conversation_for_admin,
    list_skill_conversations_for_admin,
    serialize_skill_session_messages,
)
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

    def _parse_optional_int(self, raw, field_name: str):
        if raw in (None, ""):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise SkillChannelChatError(f"{field_name}无效", status=400) from exc

    @HasPermission("skill_setting-View")
    @action(methods=["GET"], detail=False, url_path="admin_conversations")
    def admin_conversations(self, request):
        skill_id = request.query_params.get("skill_id")
        if not skill_id:
            return JsonResponse({"result": False, "message": "skill_id 必填"}, status=400)
        try:
            skill_id_int = int(skill_id)
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "skill_id 无效"}, status=400)
        managed = self._get_managed_skill(request, skill_id_int)
        if isinstance(managed, JsonResponse):
            return managed
        try:
            channel_id = self._parse_optional_int(request.query_params.get("channel_id"), "channel_id")
            page = int(request.query_params.get("page") or 1)
            page_size = int(request.query_params.get("page_size") or 10)
            person = (request.query_params.get("person") or "").strip()
            title = (request.query_params.get("title") or "").strip()
            data = list_skill_conversations_for_admin(
                skill_id=skill_id_int,
                channel_id=channel_id,
                person=person,
                title=title,
                start_time=request.query_params.get("start_time") or "",
                end_time=request.query_params.get("end_time") or "",
                page=page,
                page_size=page_size,
            )
        except (TypeError, ValueError):
            return JsonResponse({"result": False, "message": "分页参数无效"}, status=400)
        except SkillChannelChatError as exc:
            return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
        logger.info(
            "event=skill_admin_conversations_listed skill_id=%s channel_id=%s has_person=%s has_title=%s has_time=%s page=%s page_size=%s count=%s",
            skill_id_int,
            channel_id or 0,
            1 if person else 0,
            1 if title else 0,
            1 if (request.query_params.get("start_time") or request.query_params.get("end_time")) else 0,
            page,
            page_size,
            data["count"],
        )
        return Response({"result": True, "data": data})

    @HasPermission("skill_setting-View")
    @action(methods=["GET"], detail=False, url_path="admin_conversation_messages")
    def admin_conversation_messages(self, request):
        session_id = request.query_params.get("session_id") or ""
        if not session_id:
            return JsonResponse({"result": False, "message": "session_id 必填"}, status=400)
        try:
            conversation = get_skill_conversation_for_admin(session_id=session_id)
        except SkillChannelChatError as exc:
            return JsonResponse({"result": False, "message": exc.message}, status=exc.status)
        managed = self._get_managed_skill(request, conversation.skill_id)
        if isinstance(managed, JsonResponse):
            return managed
        messages = serialize_skill_session_messages(conversation)
        logger.info(
            "event=skill_admin_conversation_messages_read skill_id=%s channel_id=%s session_id=%s",
            conversation.skill_id,
            conversation.channel_id or 0,
            session_id,
        )
        return Response({"result": True, "data": {"messages": messages}})
