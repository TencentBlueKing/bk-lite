from dataclasses import dataclass

from django.utils import timezone

from apps.alerts.models import IncidentIMMember
from apps.system_mgmt.models import IMNotificationSyncRun, IMNotificationUserMapping, User


@dataclass(frozen=True)
class ResolvedIncidentMember:
    username: str
    role: str
    display_name: str
    mapping_status: str
    external_id: str
    external_id_type: str
    error_code: str
    error_message: str


def resolve_incident_members(incident, channel, member_id_type: str = "") -> list[ResolvedIncidentMember]:
    desired_roles = _collect_desired_roles(incident)
    if not desired_roles:
        return []

    users = list(User.objects.filter(username__in=desired_roles).only("id", "username", "display_name"))
    users_by_username = {user.username: user for user in users}
    mappings = IMNotificationUserMapping.objects.filter(channel=channel, user_id__in=[user.id for user in users])
    mappings_by_user_id = {mapping.user_id: mapping for mapping in mappings}
    conflict_user_ids = _latest_conflict_user_ids(channel)

    resolved = []
    for username, role in desired_roles.items():
        user = users_by_username.get(username)
        mapping = mappings_by_user_id.get(user.id) if user else None
        resolved.append(_resolve_member(username, role, user, mapping, conflict_user_ids, member_id_type))
    return sorted(resolved, key=lambda item: (item.role != IncidentIMMember.Role.OPERATOR, item.username))


def reconcile_member_snapshots(group, incident) -> list[ResolvedIncidentMember]:
    resolved_members = resolve_incident_members(incident, group.channel, member_id_type=group.member_id_type)
    existing_members = {member.username: member for member in group.members.all()}
    now = timezone.now()
    creates = []
    updates = []

    for resolved in resolved_members:
        member = existing_members.get(resolved.username)
        if member is None:
            creates.append(
                IncidentIMMember(
                    group=group,
                    username=resolved.username,
                    role=resolved.role,
                    external_id=resolved.external_id,
                    external_id_type=resolved.external_id_type,
                    mapping_status=resolved.mapping_status,
                    sync_status=(
                        IncidentIMMember.SyncStatus.PENDING
                        if resolved.mapping_status == IncidentIMMember.MappingStatus.MAPPED
                        else IncidentIMMember.SyncStatus.WAITING
                    ),
                    last_error_code=resolved.error_code,
                    last_error_message=resolved.error_message,
                )
            )
            continue

        tracked_fields = (
            "role",
            "external_id",
            "external_id_type",
            "mapping_status",
            "sync_status",
            "last_error_code",
            "last_error_message",
        )
        previous_values = tuple(getattr(member, field) for field in tracked_fields)
        member.role = resolved.role
        member.external_id = resolved.external_id
        member.external_id_type = resolved.external_id_type
        member.mapping_status = resolved.mapping_status
        member.last_error_code = resolved.error_code
        member.last_error_message = resolved.error_message
        if (
            member.sync_status == IncidentIMMember.SyncStatus.WAITING
            and resolved.mapping_status == IncidentIMMember.MappingStatus.MAPPED
        ):
            member.sync_status = IncidentIMMember.SyncStatus.PENDING
        current_values = tuple(getattr(member, field) for field in tracked_fields)
        if current_values == previous_values:
            continue
        member.updated_at = now
        updates.append(member)

    if creates:
        IncidentIMMember.objects.bulk_create(creates)
    if updates:
        IncidentIMMember.objects.bulk_update(
            updates,
            [
                "role",
                "external_id",
                "external_id_type",
                "mapping_status",
                "sync_status",
                "last_error_code",
                "last_error_message",
                "updated_at",
            ],
        )
    return resolved_members


def get_pending_members(group):
    return group.members.filter(sync_status=IncidentIMMember.SyncStatus.PENDING).order_by("id")


def _collect_desired_roles(incident) -> dict[str, str]:
    roles = {}
    for username in incident.operator or []:
        normalized = str(username or "").strip()
        if normalized:
            roles[normalized] = IncidentIMMember.Role.OPERATOR
    for username in incident.collaborators or []:
        normalized = str(username or "").strip()
        if normalized and normalized not in roles:
            roles[normalized] = IncidentIMMember.Role.COLLABORATOR
    return roles


def _latest_conflict_user_ids(channel) -> set[int]:
    run = IMNotificationSyncRun.objects.filter(channel=channel).only("payload").first()
    conflict_user_ids = set()
    for issue in ((run.payload if run else {}) or {}).get("conflict_issues", []):
        for user_id in (issue or {}).get("platform_user_ids", []):
            try:
                conflict_user_ids.add(int(user_id))
            except (TypeError, ValueError):
                continue
    return conflict_user_ids


def _resolve_member(username, role, user, mapping, conflict_user_ids, member_id_type) -> ResolvedIncidentMember:
    display_name = (getattr(user, "display_name", "") or username).strip()
    if mapping is None:
        if user and user.id in conflict_user_ids:
            return ResolvedIncidentMember(
                username=username,
                role=role,
                display_name=display_name,
                mapping_status=IncidentIMMember.MappingStatus.CONFLICT,
                external_id="",
                external_id_type="",
                error_code="IM_USER_MAPPING_CONFLICT",
                error_message="用户映射存在冲突",
            )
        return ResolvedIncidentMember(
            username=username,
            role=role,
            display_name=display_name,
            mapping_status=IncidentIMMember.MappingStatus.UNMAPPED,
            external_id="",
            external_id_type="",
            error_code="IM_USER_MAPPING_NOT_FOUND",
            error_message="用户未完成外部映射",
        )

    configured_id_type = str(mapping.external_receive_key or "").strip()
    external_id_type = str(member_id_type or configured_id_type).strip()
    if member_id_type and configured_id_type != external_id_type:
        return _missing_receive_id_member(username, role, mapping, display_name)
    external_id = str((mapping.external_snapshot or {}).get(external_id_type) or "").strip()
    if not external_id_type or not external_id:
        return _missing_receive_id_member(username, role, mapping, display_name)
    return ResolvedIncidentMember(
        username=username,
        role=role,
        display_name=(mapping.external_display_name or display_name).strip(),
        mapping_status=IncidentIMMember.MappingStatus.MAPPED,
        external_id=external_id,
        external_id_type=external_id_type,
        error_code="",
        error_message="",
    )


def _missing_receive_id_member(username, role, mapping, display_name) -> ResolvedIncidentMember:
    return ResolvedIncidentMember(
        username=username,
        role=role,
        display_name=(mapping.external_display_name or display_name).strip(),
        mapping_status=IncidentIMMember.MappingStatus.UNMAPPED,
        external_id="",
        external_id_type="",
        error_code="IM_USER_RECEIVE_ID_MISSING",
        error_message="外部接收标识缺失",
    )
