# -- coding: utf-8 --
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.alerts.constants.constants import IncidentUpdateType, LogAction, LogTargetType
from apps.alerts.models.models import Incident, IncidentUpdate
from apps.alerts.utils.operator_log import record_operator_log
from apps.alerts.serializers.incident_update import IncidentUpdateSerializer
from apps.alerts.utils.permission_scope import filter_incident_queryset_for_request
from apps.core.decorators.api_permission import HasPermission
from apps.core.utils.web_utils import WebUtils
from apps.system_mgmt.models.user import User
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class IncidentUpdateViewSet(ModelViewSet):
    serializer_class = IncidentUpdateSerializer
    pagination_class = CustomPageNumberPagination
    ordering = ["-created_at"]

    def _get_incident(self):
        incident_pk = self.kwargs.get("incident_pk")
        queryset = filter_incident_queryset_for_request(Incident.objects.all(), self.request)
        return queryset.filter(pk=incident_pk).first()

    def _check_collaborator_permission(self, incident):
        username = self.request.user.username
        operators = incident.operator or []
        collaborators = incident.collaborators or []
        return username in operators or username in collaborators

    def get_queryset(self):
        incident_pk = self.kwargs.get("incident_pk")
        # 列表只返回顶层更新（非回复），回复通过 replies 嵌套返回
        return IncidentUpdate.objects.filter(incident_id=incident_pk, parent__isnull=True).prefetch_related("replies")

    def _build_author_user_map(self, updates):
        usernames = set()
        for u in updates:
            usernames.add(u.author)
            for reply in u.replies.all():
                usernames.add(reply.author)
        if not usernames:
            return {}
        return dict(User.objects.filter(username__in=usernames).values_list("username", "display_name"))

    @HasPermission("Incidents-View")
    def list(self, request, *args, **kwargs):
        incident = self._get_incident()
        if not incident:
            return WebUtils.response_error(error_message="事故不存在或无权限访问")

        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            author_user_map = self._build_author_user_map(page)
            serializer = self.get_serializer(page, many=True, context={**self.get_serializer_context(), "author_user_map": author_user_map})
            return self.get_paginated_response(serializer.data)

        author_user_map = self._build_author_user_map(queryset)
        serializer = self.get_serializer(queryset, many=True, context={**self.get_serializer_context(), "author_user_map": author_user_map})
        return WebUtils.response_success(serializer.data)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        incident = self._get_incident()
        if not incident:
            return WebUtils.response_error(error_message="事故不存在或无权限访问")

        if not self._check_collaborator_permission(incident):
            return Response({"detail": "只有负责人或协作者可以发布更新"}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        save_kwargs = {"incident": incident, "author": request.user.username}

        # 处理回复
        parent_id = request.data.get("parent")
        if parent_id:
            try:
                parent_update = IncidentUpdate.objects.get(id=parent_id, incident=incident, parent__isnull=True)
                save_kwargs["parent"] = parent_update
            except IncidentUpdate.DoesNotExist:
                return Response({"detail": "回复的目标更新不存在"}, status=status.HTTP_400_BAD_REQUEST)

        serializer.save(**save_kwargs)

        action_label = "协作回复-添加" if parent_id else "协作更新-添加"
        record_operator_log(
            action=LogAction.ADD,
            target_type=LogTargetType.INCIDENT,
            operator=request.user.username,
            operator_object=action_label,
            target_id=incident.incident_id,
            overview=f"添加了协作更新（{serializer.validated_data.get('update_type')}）：{serializer.validated_data.get('content', '')[:50]}",
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        incident = self._get_incident()
        if not incident:
            return WebUtils.response_error(error_message="事故不存在或无权限访问")

        instance = self.get_object()
        if instance.author != request.user.username:
            return Response({"detail": "只有作者可以编辑更新"}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @HasPermission("Incidents-Edit")
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        incident = self._get_incident()
        if not incident:
            return WebUtils.response_error(error_message="事故不存在或无权限访问")

        instance = self.get_object()
        if instance.author != request.user.username:
            return Response({"detail": "只有作者可以删除更新"}, status=status.HTTP_403_FORBIDDEN)

        record_operator_log(
            action=LogAction.DELETE,
            target_type=LogTargetType.INCIDENT,
            operator=request.user.username,
            operator_object="协作更新-删除",
            target_id=incident.incident_id,
            overview=f"删除了协作更新（{instance.get_update_type_display()}）",
        )

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @HasPermission("Incidents-Edit")
    @action(methods=["post"], detail=True, url_path="key_info", url_name="key_info")
    @transaction.atomic
    def toggle_key_info(self, request, *args, **kwargs):
        incident = self._get_incident()
        if not incident:
            return WebUtils.response_error(error_message="事故不存在或无权限访问")

        username = request.user.username
        if username not in (incident.operator or []):
            return Response({"detail": "只有负责人可以标记关键信息"}, status=status.HTTP_403_FORBIDDEN)

        instance = self.get_object()
        instance.is_key_info = not instance.is_key_info
        instance.save(update_fields=["is_key_info", "updated_at"])

        action_text = "标记为关键信息" if instance.is_key_info else "取消关键信息标记"
        record_operator_log(
            action=LogAction.MODIFY,
            target_type=LogTargetType.INCIDENT,
            operator=username,
            operator_object="协作更新-关键信息",
            target_id=incident.incident_id,
            overview=f"{action_text}：{instance.content[:50]}",
        )

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @HasPermission("Incidents-View")
    @action(methods=["get"], detail=False, url_path="diagnosis", url_name="diagnosis")
    def diagnosis(self, request, *args, **kwargs):
        incident = self._get_incident()
        if not incident:
            return WebUtils.response_error(error_message="事故不存在或无权限访问")

        key_updates = IncidentUpdate.objects.filter(incident=incident, is_key_info=True)

        result = {}
        type_mapping = {
            IncidentUpdateType.OBSERVATION: "current_hypothesis",
            IncidentUpdateType.CONCLUSION: "confirmed_facts",
            IncidentUpdateType.NEXT_STEP: "next_actions",
        }

        for update_type, key in type_mapping.items():
            update = key_updates.filter(update_type=update_type).first()
            if update:
                result[key] = {
                    "id": update.id,
                    "content": update.content,
                    "author": update.author,
                    "created_at": update.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            else:
                result[key] = None

        return Response(result)
