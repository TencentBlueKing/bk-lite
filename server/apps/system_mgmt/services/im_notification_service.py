from collections import defaultdict

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.system_mgmt.models import (
    IMNotificationChannel,
    IMNotificationChannelStatusChoices,
    IMNotificationSyncRun,
    IMNotificationSyncRunStatusChoices,
    IMNotificationTriggerModeChoices,
    IMNotificationUserMapping,
    IntegrationInstance,
    User,
)
from apps.system_mgmt.providers import RuntimeApplicationService


CHANNEL_STATUS_PENDING_SYNC = IMNotificationChannelStatusChoices.PENDING_SYNC
CHANNEL_STATUS_READY = IMNotificationChannelStatusChoices.READY
CHANNEL_STATUS_NEEDS_RESYNC = IMNotificationChannelStatusChoices.NEEDS_RESYNC
CHANNEL_STATUS_DISABLED = IMNotificationChannelStatusChoices.DISABLED

SYNC_RUN_STATUS_RUNNING = IMNotificationSyncRunStatusChoices.RUNNING
SYNC_RUN_STATUS_SUCCESS = IMNotificationSyncRunStatusChoices.SUCCESS
SYNC_RUN_STATUS_PARTIAL = IMNotificationSyncRunStatusChoices.PARTIAL
SYNC_RUN_STATUS_FAILED = IMNotificationSyncRunStatusChoices.FAILED

CRITICAL_CHANNEL_FIELDS = (
    "integration_instance_id",
    "platform_match_field",
    "external_match_field",
    "external_receive_field",
)
MAX_DIAGNOSTIC_ISSUES = 50
SENSITIVE_FIELD_TOKENS = ("password", "secret", "token", "credential", "private")


def create_im_notification_sync_run(channel_id: int, trigger_mode: str = IMNotificationTriggerModeChoices.MANUAL):
    try:
        with transaction.atomic():
            channel = IMNotificationChannel.objects.select_related("integration_instance").select_for_update().filter(id=channel_id, enabled=True).first()
            if not channel:
                return {"result": False, "message": "IM notification channel not found"}

            instance = channel.integration_instance
            if not instance.enabled or instance.status != "ready" or instance.capability_status.get("im_notification") != "ready":
                return {"result": False, "message": "IM notification channel is not ready"}

            if IMNotificationSyncRun.objects.filter(channel=channel, status=SYNC_RUN_STATUS_RUNNING).exists():
                return {"result": False, "message": "IM notification sync is already running"}

            run = IMNotificationSyncRun.objects.create(
                channel=channel,
                trigger_mode=trigger_mode,
                status=SYNC_RUN_STATUS_RUNNING,
                summary="IM notification sync started",
                locked_config_snapshot=_build_locked_config_snapshot(channel),
            )
    except IntegrityError:
        return {"result": False, "message": "IM notification sync is already running"}
    return {"result": True, "message": "IM notification sync task has been initiated", "data": {"run_id": run.id}}


def execute_im_notification_sync_run(run_id: int):
    run = IMNotificationSyncRun.objects.select_related("channel", "channel__integration_instance").filter(id=run_id).first()
    if not run:
        return {"result": False, "message": "IM notification sync run not found"}

    config_snapshot = run.locked_config_snapshot or {}
    instance = IntegrationInstance.objects.filter(id=config_snapshot.get("integration_instance_id")).first()
    if not instance:
        return _fail_sync_run(run, "Integration instance not found")

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=config_snapshot.get("provider_key") or instance.provider_key,
        capability_key="im_notification",
        operation="list_external_users",
        config=instance.get_runtime_config(),
        channel=run.channel,
        run=run,
    )
    if not result.success:
        return _fail_sync_run(run, result.summary, payload=result.to_dict())

    manifest = runtime_service.get_provider_manifest(config_snapshot.get("provider_key") or instance.provider_key)
    template = manifest.business_templates.get("im_notification_form")
    external_users = list(result.payload.get("external_users") or [])
    matched_relations, unmatched_issues, conflict_issues = _match_external_users(
        external_users=external_users,
        platform_match_field=config_snapshot.get("platform_match_field") or run.channel.platform_match_field,
        external_match_field=config_snapshot.get("external_match_field") or run.channel.external_match_field,
        external_receive_field=config_snapshot.get("external_receive_field") or run.channel.external_receive_field,
        identity_fields=(template.identity_fields if template else []) or [],
        snapshot_fields=_resolve_external_snapshot_fields(template),
    )

    matched_count = len(matched_relations)
    unmatched_count = len(unmatched_issues)
    conflict_count = len(conflict_issues)
    status = SYNC_RUN_STATUS_SUCCESS if unmatched_count == 0 and conflict_count == 0 else SYNC_RUN_STATUS_PARTIAL
    summary = ""
    now = timezone.now()

    with transaction.atomic():
        IMNotificationUserMapping.objects.filter(channel=run.channel).delete()
        if matched_relations:
            IMNotificationUserMapping.objects.bulk_create(
                [IMNotificationUserMapping(channel=run.channel, synced_at=now, **relation) for relation in matched_relations],
                batch_size=200,
            )

        run.status = status
        run.summary = summary
        run.total_external_user_count = len(external_users)
        run.matched_count = matched_count
        run.unmatched_count = unmatched_count
        run.conflict_count = conflict_count
        run.payload = _build_sync_run_payload(result, unmatched_issues, conflict_issues)
        run.finished_at = now
        run.save(
            update_fields=[
                "status",
                "summary",
                "total_external_user_count",
                "matched_count",
                "unmatched_count",
                "conflict_count",
                "payload",
                "finished_at",
                "updated_at",
            ]
        )

        run.channel.status = CHANNEL_STATUS_READY if matched_count > 0 else CHANNEL_STATUS_NEEDS_RESYNC
        run.channel.save(update_fields=["status", "updated_at"])

    return {"result": True, "message": summary, "data": {"run_id": run.id}}


def send_im_notification(channel_id: int, title: str, content: str, receivers):
    channel = IMNotificationChannel.objects.select_related("integration_instance").filter(id=channel_id, enabled=True).first()
    if not channel:
        return {"result": False, "message": "IM notification channel not found"}
    if channel.status != CHANNEL_STATUS_READY:
        return {"result": False, "message": "IM notification channel requires a successful sync before sending"}

    users = _resolve_users(receivers)
    if not users:
        return {"result": False, "message": "No valid recipients found"}

    mappings = IMNotificationUserMapping.objects.filter(channel=channel, user_id__in=[user.id for user in users])
    receive_ids = []
    for mapping in mappings:
        receive_id = str((mapping.external_snapshot or {}).get(mapping.external_receive_key) or "").strip()
        if receive_id:
            receive_ids.append(receive_id)

    if not receive_ids:
        return {"result": False, "message": "No matched IM recipients found"}

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=channel.integration_instance.provider_key,
        capability_key="im_notification",
        operation="send_message",
        config=channel.integration_instance.get_runtime_config(),
        title=title,
        content=content,
        receive_id_type=channel.external_receive_field,
        receive_ids=receive_ids,
    )
    return {"result": result.success, "message": result.summary, "data": result.to_dict()}


def send_im_notification_to_users(channel_id: int, user_ids: list[int], title: str, content: str):
    channel = IMNotificationChannel.objects.select_related("integration_instance").filter(id=channel_id, enabled=True).first()
    if not channel:
        return {"result": False, "message": "IM notification channel not found"}
    if channel.status != CHANNEL_STATUS_READY:
        return {"result": False, "message": "IM notification channel requires a successful sync before sending"}

    if not user_ids:
        return {"result": False, "message": "No recipients selected"}

    mappings = IMNotificationUserMapping.objects.filter(channel=channel, user_id__in=user_ids)
    receive_ids = []
    for mapping in mappings:
        receive_id = str((mapping.external_snapshot or {}).get(mapping.external_receive_key) or "").strip()
        if receive_id:
            receive_ids.append(receive_id)

    if not receive_ids:
        return {"result": False, "message": "No matched IM recipients found for selected users"}

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=channel.integration_instance.provider_key,
        capability_key="im_notification",
        operation="send_message",
        config=channel.integration_instance.get_runtime_config(),
        title=title,
        content=content,
        receive_id_type=channel.external_receive_field,
        receive_ids=receive_ids,
    )
    return {"result": result.success, "message": result.summary, "data": result.to_dict()}


def critical_config_changed(instance: IMNotificationChannel | None, attrs: dict) -> bool:
    if instance is None:
        return False
    for field_name in CRITICAL_CHANNEL_FIELDS:
        attr_name = "integration_instance" if field_name == "integration_instance_id" else field_name
        if attr_name not in attrs:
            continue
        current_value = getattr(instance, field_name)
        incoming_value = attrs[attr_name].id if attr_name == "integration_instance" else attrs[attr_name]
        if current_value != incoming_value:
            return True
    return False


def _build_locked_config_snapshot(channel: IMNotificationChannel):
    return {
        "integration_instance_id": channel.integration_instance_id,
        "provider_key": channel.integration_instance.provider_key,
        "platform_match_field": channel.platform_match_field,
        "external_match_field": channel.external_match_field,
        "external_receive_field": channel.external_receive_field,
    }


def _fail_sync_run(run: IMNotificationSyncRun, summary: str, payload: dict | None = None):
    now = timezone.now()
    with transaction.atomic():
        run.status = SYNC_RUN_STATUS_FAILED
        run.summary = summary
        run.payload = payload or {}
        run.finished_at = now
        run.save(update_fields=["status", "summary", "payload", "finished_at", "updated_at"])
        if run.channel.status != CHANNEL_STATUS_DISABLED:
            run.channel.status = CHANNEL_STATUS_NEEDS_RESYNC
            run.channel.save(update_fields=["status", "updated_at"])
    return {"result": False, "message": summary}


def _match_external_users(
    *,
    external_users,
    platform_match_field: str,
    external_match_field: str,
    external_receive_field: str,
    identity_fields: list[str],
    snapshot_fields: set[str],
):
    platform_lookup: dict[str, list[User]] = defaultdict(list)
    for user in User.objects.filter(disabled=False):
        value = str(getattr(user, platform_match_field, "") or "").strip()
        if value:
            platform_lookup[value].append(user)

    matched_relations = []
    unmatched_issues = []
    conflict_issues = []

    for external_user in external_users:
        match_value = str(external_user.get(external_match_field, "") or "").strip()
        safe_external_user = _sanitize_external_snapshot(external_user, snapshot_fields)
        if not match_value:
            unmatched_issues.append({"reason": "missing_external_match_value", "external_user": safe_external_user})
            continue

        matched_users = platform_lookup.get(match_value, [])
        if not matched_users:
            unmatched_issues.append(
                {
                    "reason": "platform_user_not_found",
                    "external_user": safe_external_user,
                    "external_match_field": external_match_field,
                    "external_match_value": match_value,
                }
            )
            continue
        if len(matched_users) > 1:
            conflict_issues.append(
                {
                    "reason": "multiple_platform_users",
                    "external_user": safe_external_user,
                    "platform_user_ids": [item.id for item in matched_users],
                    "external_match_field": external_match_field,
                    "external_match_value": match_value,
                }
            )
            continue

        external_snapshot = _sanitize_external_snapshot(external_user, snapshot_fields)
        identity_key = _resolve_identity_key(external_snapshot, identity_fields, external_receive_field, external_match_field)
        identity_value = str(external_snapshot.get(identity_key, "") or "").strip()
        receive_value = str(external_snapshot.get(external_receive_field, "") or "").strip()
        if not identity_key or not identity_value or not receive_value:
            unmatched_issues.append(
                {
                    "reason": "invalid_external_identity",
                    "external_user": safe_external_user,
                    "identity_key": identity_key,
                    "external_receive_field": external_receive_field,
                }
            )
            continue

        matched_user = matched_users[0]
        matched_relations.append(
            {
                "user": matched_user,
                "external_identity_key": identity_key,
                "external_identity_value": identity_value,
                "external_receive_key": external_receive_field,
                "external_display_name": str(external_snapshot.get("name", "") or ""),
                "match_context": {
                    "platform_field": platform_match_field,
                    "platform_value": match_value,
                    "external_field": external_match_field,
                    "external_value": match_value,
                },
                "external_snapshot": external_snapshot,
            }
        )

    return matched_relations, unmatched_issues, conflict_issues


def _resolve_identity_key(external_snapshot: dict, identity_fields: list[str], external_receive_field: str, external_match_field: str):
    candidates = list(identity_fields) + [external_receive_field, external_match_field]
    for field_name in candidates:
        value = str(external_snapshot.get(field_name, "") or "").strip()
        if value:
            return field_name
    return ""


def _resolve_external_snapshot_fields(template) -> set[str]:
    if template is None:
        return {"user_id", "open_id", "email", "mobile", "name"}
    return set(template.available_external_fields or []) | set(template.identity_fields or []) | set(
        template.matchable_fields or []
    ) | set(template.receivable_fields or []) | {"name"}


def _sanitize_external_snapshot(external_user: dict, allowed_fields: set[str]) -> dict:
    if not isinstance(external_user, dict):
        return {}
    return {
        key: value
        for key, value in external_user.items()
        if key in allowed_fields and not _is_sensitive_field(key) and _is_safe_scalar(value)
    }


def _build_sync_run_payload(result, unmatched_issues: list[dict], conflict_issues: list[dict]) -> dict:
    result_payload = result.to_dict()
    safe_payload = _sanitize_result_payload(result_payload.get("payload") or {})
    result_payload["payload"] = safe_payload
    result_payload["unmatched_issues"] = unmatched_issues[:MAX_DIAGNOSTIC_ISSUES]
    result_payload["conflict_issues"] = conflict_issues[:MAX_DIAGNOSTIC_ISSUES]
    result_payload["unmatched_issue_count"] = len(unmatched_issues)
    result_payload["conflict_issue_count"] = len(conflict_issues)
    return result_payload


def _sanitize_result_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    safe_payload = {}
    for key, value in payload.items():
        if key == "external_users" or _is_sensitive_field(key):
            continue
        if _is_safe_scalar(value):
            safe_payload[key] = value
    return safe_payload


def _is_sensitive_field(field_name: str) -> bool:
    normalized = str(field_name or "").lower()
    return any(token in normalized for token in SENSITIVE_FIELD_TOKENS)


def _is_safe_scalar(value) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _resolve_users(receivers):
    if not receivers:
        return []
    if all(isinstance(item, int) or (isinstance(item, str) and item.isdigit()) for item in receivers):
        return list(User.objects.filter(id__in=[int(item) for item in receivers], disabled=False))
    return list(User.objects.filter(username__in=receivers, disabled=False))
