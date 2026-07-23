from django.db.models import Count
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import action
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


class IncidentIMGroupViewSet(ModelViewSet):
    pagination_class = CustomPageNumberPagination
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

    def _serialize_group(self, group, incident):
        summary = group.members.values("sync_status").annotate(count=Count("id"))
        counts = {item["sync_status"]: item["count"] for item in summary}
        can_manage = self.request.user.username in (incident.operator or [])
        return {
            "id": str(group.id),
            "channel_id": group.channel_id,
            "channel_name": group.channel_name_snapshot,
            "group_name": group.group_name,
            "status": group.status,
            "current_stage": group.current_stage,
            "continuous_sync_enabled": group.continuous_sync_enabled,
            "pause_reason": group.pause_reason or None,
            "member_summary": {
                "total": sum(counts.values()),
                "joined": counts.get(IncidentIMMember.SyncStatus.JOINED, 0),
                "waiting": counts.get(IncidentIMMember.SyncStatus.WAITING, 0),
                "failed": counts.get(IncidentIMMember.SyncStatus.FAILED, 0),
            },
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
        group = IncidentIMGroup.objects.filter(incident=incident, active_slot=1).first()
        queryset = IncidentIMMember.objects.none() if group is None else group.members.order_by("id")
        page = self.paginate_queryset(queryset)
        if page is not None:
            return self.get_paginated_response(
                IncidentIMMemberSerializer(page, many=True, context={"display_names": member_display_names(page)},).data
            )
        return Response(IncidentIMMemberSerializer(queryset, many=True, context={"display_names": member_display_names(queryset)},).data)
