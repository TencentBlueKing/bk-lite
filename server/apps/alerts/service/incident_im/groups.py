import uuid

from django.db import IntegrityError, transaction

from apps.alerts.constants.constants import IncidentStatus
from apps.alerts.models import Incident, IncidentIMGroup, IncidentIMMember
from apps.alerts.service.incident_im.errors import IncidentIMError
from apps.alerts.service.incident_im.members import resolve_incident_members
from apps.alerts.service.outbox import enqueue_outbox
from apps.system_mgmt.services.im_group_service import IMGroupChannelError, IMGroupRuntimeService


class IncidentIMGroupService:
    @classmethod
    def create(cls, *, incident_id, actor, channel_id, group_name, owner_username, continuous_sync_enabled):
        with transaction.atomic():
            incident = Incident.objects.select_for_update().filter(pk=incident_id).first()
            if incident is None:
                raise IncidentIMError("IM_INCIDENT_NOT_FOUND", "Incident 不存在", 404)
            cls.require_operator(incident, actor)
            if incident.status not in IncidentStatus.ACTIVATE_STATUS:
                raise IncidentIMError("IM_INCIDENT_NOT_ACTIVE", "Incident 已关闭或已处理，无法创建协作群", 409)
            if IncidentIMGroup.objects.filter(incident=incident, active_slot=1).exists():
                raise IncidentIMError("IM_GROUP_ACTIVE_EXISTS", "Incident 已存在未解绑的协作群", 409)

            channel = cls.require_ready_channel(actor, channel_id)
            member_id_type = str(channel.external_receive_field or "").strip()
            members = resolve_incident_members(incident, channel, member_id_type=member_id_type)
            mapped_operators = {
                member.username: member
                for member in members
                if member.role == IncidentIMMember.Role.OPERATOR
                and member.mapping_status == IncidentIMMember.MappingStatus.MAPPED
            }
            if not mapped_operators:
                raise IncidentIMError("IM_NO_MAPPED_OPERATOR", "至少需要一名已映射的负责人")
            owner = mapped_operators.get(owner_username)
            if owner is None:
                raise IncidentIMError("IM_OWNER_NOT_MAPPED", "所选群主必须是已映射的负责人")

            try:
                with transaction.atomic():
                    group_id = uuid.uuid4()
                    group = IncidentIMGroup.objects.create(
                        id=group_id,
                        incident=incident,
                        channel=channel,
                        provider_key=channel.integration_instance.provider_key,
                        channel_name_snapshot=channel.name,
                        member_id_type=member_id_type,
                        group_name=group_name,
                        external_owner_id=owner.external_id,
                        continuous_sync_enabled=continuous_sync_enabled,
                        idempotency_key=f"bklite-{group_id.hex}",
                    )
                    IncidentIMMember.objects.bulk_create(
                        [
                            IncidentIMMember(
                                group=group,
                                username=member.username,
                                role=member.role,
                                external_id=member.external_id,
                                external_id_type=member.external_id_type,
                                mapping_status=member.mapping_status,
                                sync_status=(
                                    IncidentIMMember.SyncStatus.PENDING
                                    if member.mapping_status == IncidentIMMember.MappingStatus.MAPPED
                                    else IncidentIMMember.SyncStatus.WAITING
                                ),
                                last_error_code=member.error_code,
                                last_error_message=member.error_message,
                            )
                            for member in members
                        ]
                    )
                    enqueue_outbox(
                        "incident_im_group.create",
                        {"group_id": str(group.id)},
                        f"incident-im-group:{group.id}:create",
                    )
            except IntegrityError as exc:
                raise IncidentIMError("IM_GROUP_ACTIVE_EXISTS", "Incident 已存在未解绑的协作群", 409) from exc
            return group

    @staticmethod
    def require_operator(incident, actor):
        if getattr(actor, "username", "") not in (incident.operator or []):
            raise IncidentIMError("IM_OPERATOR_REQUIRED", "只有 Incident 负责人可以管理协作群", 403)

    @staticmethod
    def require_ready_channel(actor, channel_id):
        try:
            return IMGroupRuntimeService.require_ready_channel(actor, channel_id)
        except IMGroupChannelError as exc:
            if exc.code == "im_group.channel_access_denied":
                raise IncidentIMError("IM_CHANNEL_FORBIDDEN", "无权使用该协作群渠道", 403) from exc
            raise IncidentIMError("IM_CHANNEL_NOT_READY", "协作群渠道未就绪或不可用") from exc
