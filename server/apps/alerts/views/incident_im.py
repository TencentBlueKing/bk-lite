from django.db.models import Case, Count, IntegerField, Value, When
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.serializers.incident_im import (
    IncidentIMGroupCreateSerializer,
    IncidentIMGroupSettingsSerializer,
    IncidentIMGroupUnlinkSerializer,
    IncidentIMMemberSerializer,
    member_display_names,
    serialize_resolved_member,
)
from apps.alerts.service.incident_im.errors import IncidentIMError
from apps.alerts.service.incident_im.groups import IncidentIMGroupService, record_group_audit
from apps.alerts.service.incident_im.members import resolve_incident_members
from apps.alerts.service.incident_im.reconcile import reconcile_incident_im_group
from apps.alerts.utils.permission_scope import filter_incident_queryset_for_request
from apps.core.decorators.api_permission import HasPermission
from apps.system_mgmt.services.im_group_service import IMGroupRuntimeService
from config.drf.pagination import CustomPageNumberPagination
from config.drf.viewsets import ModelViewSet


class IncidentIMMemberPagination(CustomPageNumberPagination):
    page_size = 20
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        # 本接口必须始终分页；全局分页器会在省略 page_size 时返回完整列表。
        return PageNumberPagination.paginate_queryset(self, queryset, request, view)


class IncidentIMGroupViewSet(ModelViewSet):
    pagination_class = IncidentIMMemberPagination
    queryset = IncidentIMGroup.objects.all()
    serializer_class = IncidentIMGroupCreateSerializer

    def _incident(self):
        return filter_incident_queryset_for_request(Incident.objects.all(), self.request).filter(pk=self.kwargs["incident_pk"]).first()

    def _read_incident_or_response(self):
        incident = self._incident()
        if incident is None:
            return (
                None,
                self._error("IM_INCIDENT_NOT_FOUND", "Incident 不存在或无权限访问", status.HTTP_404_NOT_FOUND,),
            )
        return incident, None

    def _manage_incident_or_response(self):
        incident, error = self._read_incident_or_response()
        if error is not None:
            return None, error
        try:
            IncidentIMGroupService.require_operator(incident, self.request.user)
        except IncidentIMError as exc:
            return None, self._incident_error(exc)
        return incident, None

    @staticmethod
    def _error(code, message, http_status=status.HTTP_400_BAD_REQUEST, details=None):
        return JsonResponse({"result": False, "code": code, "message": message, "data": {"details": details or {}}}, status=http_status)

    def _incident_error(self, exc):
        return self._error(exc.code, exc.message, exc.http_status)

    @staticmethod
    def _default_group_name(incident):
        return f"[{incident.incident_id}] {incident.title}"[:255]

    @staticmethod
    def _status_message(group, member_summary):
        if group.status in (IncidentIMGroup.Status.PENDING_CREATE, IncidentIMGroup.Status.CREATING):
            return "正在创建群并邀请首批成员"
        if group.status == IncidentIMGroup.Status.PAUSED:
            if group.pause_reason == IncidentIMGroup.PauseReason.INCIDENT_CLOSED:
                return "Incident 已关闭，重新打开后按原配置恢复"
            return "新增人员暂不自动入群"
        if group.status == IncidentIMGroup.Status.CREATE_FAILED:
            return "飞书群尚未创建"
        if group.status == IncidentIMGroup.Status.DEGRADED:
            return "飞书群配置异常，请重新检查"

        messages = []
        if member_summary["waiting"]:
            messages.append(f'{member_summary["waiting"]} 人待映射')
        if member_summary["failed"]:
            messages.append(f'{member_summary["failed"]} 人加入失败')
        syncing = member_summary["total"] - member_summary["joined"] - member_summary["waiting"] - member_summary["failed"]
        if syncing:
            messages.append(f"{syncing} 人待同步")
        if messages:
            return "，".join(messages)
        return "新增人员将按当前配置同步"

    def _serialize_group(self, group, incident):
        summary = group.members.values("sync_status").annotate(count=Count("id"))
        counts = {item["sync_status"]: item["count"] for item in summary}
        can_manage = self.request.user.username in (incident.operator or [])
        member_summary = {
            "total": sum(counts.values()),
            "joined": counts.get(IncidentIMMember.SyncStatus.JOINED, 0),
            "waiting": counts.get(IncidentIMMember.SyncStatus.WAITING, 0),
            "failed": counts.get(IncidentIMMember.SyncStatus.FAILED, 0),
        }
        return {
            "id": str(group.id),
            "provider": group.provider_key,
            "channel_id": group.channel_id,
            "channel_name": group.channel_name_snapshot,
            "group_name": group.group_name,
            "external_chat_id": group.external_chat_id or "",
            # 飞书 Provider 当前没有权威的群聊跳转链接来源，禁止猜测 URL。
            "open_chat_url": None,
            "status": group.status,
            "current_stage": group.current_stage,
            "status_message": self._status_message(group, member_summary),
            "continuous_sync_enabled": group.continuous_sync_enabled,
            "pause_reason": group.pause_reason or None,
            "member_summary": member_summary,
            "permissions": {
                "can_manage": can_manage,
                "can_retry": can_manage
                and group.status
                in (
                    IncidentIMGroup.Status.ACTIVE,
                    IncidentIMGroup.Status.ACTIVE_PARTIAL,
                    IncidentIMGroup.Status.DEGRADED,
                    IncidentIMGroup.Status.CREATE_FAILED,
                ),
                "can_pause": can_manage and group.status in (IncidentIMGroup.Status.ACTIVE, IncidentIMGroup.Status.ACTIVE_PARTIAL,),
                "can_resume": can_manage
                and group.status == IncidentIMGroup.Status.PAUSED
                and group.pause_reason == IncidentIMGroup.PauseReason.MANUAL,
                "can_unlink": can_manage
                and group.status not in (IncidentIMGroup.Status.PENDING_CREATE, IncidentIMGroup.Status.CREATING,)
                and group.current_stage == IncidentIMGroup.Stage.COMPLETED
                and not group.members.filter(sync_status=IncidentIMMember.SyncStatus.ADDING).exists(),
            },
            "last_sync_at": group.last_sync_at,
        }

    @HasPermission("Incidents-View")
    def list(self, request, *args, **kwargs):
        incident, error = self._read_incident_or_response()
        if error is not None:
            return error
        group = IncidentIMGroup.objects.filter(incident=incident, active_slot=1).first()
        return Response(self._serialize_group(group, incident) if group else None)

    @HasPermission("Incidents-Edit")
    def create(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        serializer = IncidentIMGroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            group = IncidentIMGroupService.create(incident_id=incident.id, actor=request.user, **serializer.validated_data,)
        except IncidentIMError as exc:
            return self._incident_error(exc)
        group.refresh_from_db()
        return Response(self._serialize_group(group, incident), status=status.HTTP_202_ACCEPTED)

    @HasPermission("Incidents-Edit")
    def partial_update(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        group = IncidentIMGroup.objects.filter(incident=incident, active_slot=1).first()
        if group is None:
            return self._error("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", status.HTTP_404_NOT_FOUND)
        serializer = IncidentIMGroupSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enabled = serializer.validated_data["continuous_sync_enabled"]
        try:
            group = IncidentIMGroupService.set_continuous_sync(incident_id=incident.id, actor_username=request.user.username, enabled=enabled,)
        except IncidentIMError as exc:
            return self._incident_error(exc)
        if enabled:
            reconcile_incident_im_group(incident.id)
            group.refresh_from_db()
        return Response(self._serialize_group(group, incident))

    @HasPermission("Incidents-Edit")
    def destroy(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        serializer = IncidentIMGroupUnlinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            IncidentIMGroupService.unlink(
                incident_id=incident.id, actor_username=request.user.username, group_name=serializer.validated_data["group_name"],
            )
        except IncidentIMError as exc:
            return self._incident_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @HasPermission("Incidents-Edit")
    @action(methods=["post"], detail=False, url_path="pause")
    def pause(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        try:
            group = IncidentIMGroupService.pause(incident_id=incident.id, actor_username=request.user.username,)
        except IncidentIMError as exc:
            return self._incident_error(exc)
        return Response(self._serialize_group(group, incident))

    @HasPermission("Incidents-Edit")
    @action(methods=["post"], detail=False, url_path="resume")
    def resume(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        try:
            group = IncidentIMGroupService.resume(incident_id=incident.id, actor_username=request.user.username,)
        except IncidentIMError as exc:
            return self._incident_error(exc)
        reconcile_incident_im_group(incident.id, resume_create=True)
        group.refresh_from_db()
        return Response(self._serialize_group(group, incident))

    @HasPermission("Incidents-Edit")
    @action(methods=["post"], detail=False, url_path="retry")
    def retry(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        group = IncidentIMGroup.objects.filter(incident=incident, active_slot=1).first()
        if group is None:
            return self._error("IM_GROUP_NOT_FOUND", "Incident 尚未创建协作群", status.HTTP_404_NOT_FOUND)
        try:
            if group.status == IncidentIMGroup.Status.DEGRADED:
                group = IncidentIMGroupService.retry_degraded(incident_id=incident.id, actor_username=request.user.username,)
                if group.status == IncidentIMGroup.Status.ACTIVE_PARTIAL:
                    reconcile_incident_im_group(incident.id, force_delivery=True)
            elif group.status == IncidentIMGroup.Status.CREATE_FAILED:
                IncidentIMGroupService.prepare_create_retry(
                    incident_id=incident.id, actor_username=request.user.username,
                )
            elif group.status in (IncidentIMGroup.Status.ACTIVE, IncidentIMGroup.Status.ACTIVE_PARTIAL,):
                record_group_audit(group, request.user.username, "重试飞书群待处理成员")
                reconcile_incident_im_group(incident.id, force_delivery=True)
            else:
                raise IncidentIMError("IM_GROUP_STATE_INVALID", "当前群状态不允许重试", 409)
        except IncidentIMError as exc:
            return self._incident_error(exc)
        group.refresh_from_db()
        return Response(self._serialize_group(group, incident))

    @HasPermission("Incidents-Edit")
    @action(methods=["get"], detail=False, url_path="options")
    def group_options(self, request, *args, **kwargs):
        incident, error = self._manage_incident_or_response()
        if error is not None:
            return error
        channels = IMGroupRuntimeService.list_ready_channels(request.user)
        payload = {
            "channels": [{"id": channel.id, "name": channel.name} for channel in channels],
            "default_group_name": self._default_group_name(incident),
        }
        channel_id = request.query_params.get("channel_id")
        if channel_id in (None, ""):
            return Response(payload)
        try:
            channel = IncidentIMGroupService.require_ready_channel(request.user, int(channel_id))
        except (TypeError, ValueError):
            return self._error("IM_CHANNEL_NOT_READY", "协作群渠道未就绪或不可用")
        except IncidentIMError as exc:
            return self._incident_error(exc)
        members = resolve_incident_members(incident, channel, member_id_type=channel.external_receive_field)
        payload["members"] = [serialize_resolved_member(member) for member in members]
        payload["owner_candidates"] = [
            {"username": member.username, "display_name": member.display_name}
            for member in members
            if member.role == IncidentIMMember.Role.OPERATOR and member.mapping_status == IncidentIMMember.MappingStatus.MAPPED
        ]
        return Response(payload)

    @HasPermission("Incidents-View")
    @action(methods=["get"], detail=False, url_path="members")
    def members(self, request, *args, **kwargs):
        incident, error = self._read_incident_or_response()
        if error is not None:
            return error
        member_filter = request.query_params.get("filter") or "all"
        if member_filter not in {"all", "pending", "joined"}:
            return self._error("IM_MEMBER_FILTER_INVALID", "成员筛选仅支持 all、pending 或 joined",)
        page_size = request.query_params.get("page_size")
        if page_size is not None and page_size not in {"10", "20", "50", "100"}:
            return self._error("IM_MEMBER_PAGE_SIZE_INVALID", "成员分页大小仅支持 10、20、50 或 100",)
        group = IncidentIMGroup.objects.filter(incident=incident, active_slot=1).first()
        queryset = IncidentIMMember.objects.none() if group is None else group.members.all()
        if member_filter == "pending":
            queryset = queryset.exclude(sync_status=IncidentIMMember.SyncStatus.JOINED)
        elif member_filter == "joined":
            queryset = queryset.filter(sync_status=IncidentIMMember.SyncStatus.JOINED)
        queryset = queryset.annotate(
            _ui_order=Case(
                When(sync_status=IncidentIMMember.SyncStatus.FAILED, then=Value(0)),
                When(mapping_status=IncidentIMMember.MappingStatus.CONFLICT, then=Value(1)),
                When(mapping_status=IncidentIMMember.MappingStatus.UNMAPPED, then=Value(2)),
                When(
                    sync_status__in=(IncidentIMMember.SyncStatus.WAITING, IncidentIMMember.SyncStatus.PENDING, IncidentIMMember.SyncStatus.ADDING,),
                    then=Value(3),
                ),
                When(sync_status=IncidentIMMember.SyncStatus.JOINED, then=Value(4)),
                default=Value(5),
                output_field=IntegerField(),
            )
        ).order_by("_ui_order", "username")
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(
                IncidentIMMemberSerializer(page, many=True, context={"display_names": member_display_names(page)},).data
            )
        return Response(IncidentIMMemberSerializer(queryset, many=True, context={"display_names": member_display_names(queryset)},).data)
