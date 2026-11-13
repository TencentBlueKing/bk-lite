import re
from collections import defaultdict

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.logger import system_mgmt_logger as logger
from apps.system_mgmt.models import (
    IMAccountAssociation,
    IMAccountAssociationStatusChoices,
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
from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability

CHANNEL_STATUS_PENDING_SYNC = IMNotificationChannelStatusChoices.PENDING_SYNC
CHANNEL_STATUS_READY = IMNotificationChannelStatusChoices.READY
CHANNEL_STATUS_NEEDS_RESYNC = IMNotificationChannelStatusChoices.NEEDS_RESYNC
CHANNEL_STATUS_DISABLED = IMNotificationChannelStatusChoices.DISABLED
ASSOCIATION_STATUS_READY = IMAccountAssociationStatusChoices.READY
ASSOCIATION_STATUS_NEEDS_RESYNC = IMAccountAssociationStatusChoices.NEEDS_RESYNC

SYNC_RUN_STATUS_RUNNING = IMNotificationSyncRunStatusChoices.RUNNING
_SAFE_LOG_TOKEN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
EXTERNAL_CALL_FAILED = (
    "event=im_account_association_external_call_failed run_id=%s association_id=%s " "failed_stage=%s error_type=%s provider_key=%s request_id=%s"
)
EXTERNAL_SEND_FAILED = (
    "event=im_notification_external_send_failed channel_id=%s association_id=%s " "failed_stage=%s error_type=%s provider_key=%s request_id=%s"
)
EXTERNAL_SEND_SUCCEEDED = (
    "event=im_notification_external_send_succeeded log_name=%s channel_id=%s association_id=%s " "provider_key=%s recipient_count=%s skipped=%s"
)
SYNC_RUN_STATUS_SUCCESS = IMNotificationSyncRunStatusChoices.SUCCESS
SYNC_RUN_STATUS_PARTIAL = IMNotificationSyncRunStatusChoices.PARTIAL
SYNC_RUN_STATUS_FAILED = IMNotificationSyncRunStatusChoices.FAILED
SYNC_WRITE_SKIPPED = "event=im_account_association_sync_write_skipped run_id=%s association_id=%s"
RESULT_DISCARDED = "event=im_account_association_sync_result_discarded run_id=%s association_id=%s failed_stage=%s error_type=%s"
INSTANCE_MISSING = "event=im_account_association_sync_instance_missing run_id=%s association_id=%s failed_stage=%s error_type=%s"
SYNC_COMPLETED = (
    "execute_im_notification_sync_run: sync completed, run_id=%s, association_id=%s, status=%s, "
    "total_external_users=%s, matched=%s, unmatched=%s, conflict=%s"
)
UPDATE_NO_LONGER_RUNNING = "IM account association update is no longer running"

CRITICAL_ASSOCIATION_FIELDS = (
    "platform_match_field",
    "external_match_field",
    "external_receive_field",
)
IDENTITY_FIELDS_BY_PROVIDER = {
    "wecom": ("corp_id", "agent_id"),
    "feishu": ("app_id",),
}
MAX_DIAGNOSTIC_ISSUES = 50
SENSITIVE_FIELD_TOKENS = ("password", "secret", "token", "credential", "private")


def create_account_association_sync_run(association_id: int, trigger_mode: str = IMNotificationTriggerModeChoices.MANUAL):
    try:
        with transaction.atomic():
            association = IMAccountAssociation.objects.select_related("integration_instance").select_for_update().filter(id=association_id).first()
            if not association:
                logger.warning(
                    "create_account_association_sync_run: association not found, association_id=%s, trigger_mode=%s",
                    association_id,
                    trigger_mode,
                )
                return {"result": False, "message": "IM account association not found"}

            instance = association.integration_instance
            if not get_integration_capability_availability(instance, "im_notification")["available"]:
                logger.warning(
                    "create_account_association_sync_run: capability not ready, association_id=%s, provider_key=%s, trigger_mode=%s",
                    association_id,
                    instance.provider_key,
                    trigger_mode,
                )
                return {"result": False, "message": "IM notification capability is not ready"}

            if IMNotificationSyncRun.objects.filter(account_association=association, status=SYNC_RUN_STATUS_RUNNING).exists():
                logger.warning(
                    "create_account_association_sync_run: sync already running, association_id=%s, trigger_mode=%s",
                    association_id,
                    trigger_mode,
                )
                return {"result": False, "message": "IM account association update is already running"}

            run = IMNotificationSyncRun.objects.create(
                account_association=association,
                trigger_mode=trigger_mode,
                status=SYNC_RUN_STATUS_RUNNING,
                summary="IM account association update started",
                locked_config_snapshot=_build_locked_config_snapshot(association),
            )
    except IntegrityError:
        logger.warning(
            "create_account_association_sync_run: sync already running, association_id=%s, trigger_mode=%s",
            association_id,
            trigger_mode,
        )
        return {"result": False, "message": "IM account association update is already running"}
    logger.info(
        "create_account_association_sync_run: update initiated, association_id=%s, run_id=%s, trigger_mode=%s",
        association_id,
        run.id,
        trigger_mode,
    )
    return {"result": True, "message": "IM account association update has been initiated", "data": {"run_id": run.id}}


def _completed_sync_run_status(matched_count: int, unmatched_count: int, conflict_count: int) -> str:
    if unmatched_count == 0 and conflict_count == 0:
        return SYNC_RUN_STATUS_SUCCESS
    if matched_count > 0:
        return SYNC_RUN_STATUS_PARTIAL
    return SYNC_RUN_STATUS_FAILED


def execute_im_notification_sync_run(run_id: int):
    run = IMNotificationSyncRun.objects.select_related("account_association", "account_association__integration_instance").filter(id=run_id).first()
    if not run:
        logger.warning(f"execute_im_notification_sync_run: sync run not found, run_id={run_id}")
        return {"result": False, "message": "IM notification sync run not found"}

    config_snapshot = run.locked_config_snapshot or {}
    instance = IntegrationInstance.objects.filter(id=config_snapshot.get("integration_instance_id")).first()
    if not instance:
        logger.error(
            INSTANCE_MISSING,
            run_id,
            run.account_association_id,
            "load_instance",
            "instance_missing",
        )
        return _fail_sync_run(run, "Integration instance not found")
    if not get_integration_capability_availability(instance, "im_notification")["available"]:
        return _fail_sync_run(run, "IM notification channel is not ready")

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=config_snapshot.get("provider_key") or instance.provider_key,
        capability_key="im_notification",
        operation="list_external_users",
        config=instance.get_runtime_config(),
        account_association=run.account_association,
        run=run,
    )
    if not result.success:
        logger.error(
            EXTERNAL_CALL_FAILED,
            run_id,
            run.account_association_id,
            "list_external_users",
            _external_error_type(result),
            config_snapshot.get("provider_key") or instance.provider_key,
            _log_request_id(result),
        )
        return _fail_sync_run(run, result.summary, payload=result.to_dict())

    manifest = runtime_service.get_provider_manifest(config_snapshot.get("provider_key") or instance.provider_key)
    template = manifest.business_templates.get("im_notification_form")
    external_users = list(result.payload.get("external_users") or [])
    matched_relations, unmatched_issues, conflict_issues = _match_external_users(
        external_users=external_users,
        platform_match_field=config_snapshot.get("platform_match_field") or run.account_association.platform_match_field,
        external_match_field=config_snapshot.get("external_match_field") or run.account_association.external_match_field,
        external_receive_field=config_snapshot.get("external_receive_field") or run.account_association.external_receive_field,
        identity_fields=(template.identity_fields if template else []) or [],
        snapshot_fields=_resolve_external_snapshot_fields(template),
    )

    matched_count = len(matched_relations)
    unmatched_count = len(unmatched_issues)
    conflict_count = len(conflict_issues)
    status = _completed_sync_run_status(matched_count, unmatched_count, conflict_count)
    summary = ""
    now = timezone.now()
    result_applied = False

    with transaction.atomic():
        locked_run = _locked_running_sync_run(run_id)
        if locked_run is None:
            return {"result": False, "message": UPDATE_NO_LONGER_RUNNING}
        association = (
            IMAccountAssociation.objects.select_for_update().select_related("integration_instance").get(pk=locked_run.account_association_id)
        )
        if _snapshot_still_current(association, config_snapshot):
            result_applied = True
            IMNotificationUserMapping.objects.filter(account_association=association).delete()
            if matched_relations:
                IMNotificationUserMapping.objects.bulk_create(
                    [IMNotificationUserMapping(account_association=association, synced_at=now, **relation) for relation in matched_relations],
                    batch_size=200,
                )
            association.status = ASSOCIATION_STATUS_READY if matched_count > 0 else ASSOCIATION_STATUS_NEEDS_RESYNC
            association.save(update_fields=["status", "updated_at"])
            refresh_notification_channel_status(association)
        else:
            if association.status == ASSOCIATION_STATUS_READY:
                association.status = ASSOCIATION_STATUS_NEEDS_RESYNC
                association.save(update_fields=["status", "updated_at"])
                refresh_notification_channel_status(association)
            logger.warning(
                RESULT_DISCARDED,
                run_id,
                association.id,
                "apply_result",
                "config_changed",
            )

        locked_run.status = status
        locked_run.summary = summary
        locked_run.total_external_user_count = len(external_users)
        locked_run.matched_count = matched_count
        locked_run.unmatched_count = unmatched_count
        locked_run.conflict_count = conflict_count
        locked_run.payload = _build_sync_run_payload(result, unmatched_issues, conflict_issues)
        locked_run.finished_at = now
        locked_run.save(
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

    if result_applied:
        logger.info(
            SYNC_COMPLETED,
            run_id,
            run.account_association_id,
            status,
            len(external_users),
            matched_count,
            unmatched_count,
            conflict_count,
        )
    return {"result": True, "message": summary, "data": {"run_id": run.id}}


def send_im_notification(channel_id: int, title: str, content: str, receivers):
    channel, association, blocked = _ready_association_for_send(channel_id)
    if blocked:
        return blocked
    receive_ids, skipped = _receive_ids_for_requested_users(association, receivers)
    if not receive_ids:
        logger.warning(
            "send_im_notification: no usable recipients, channel_id=%s, association_id=%s, skipped=%s",
            channel_id,
            association.id,
            len(skipped),
        )
        return {"result": False, "message": "No usable IM account association recipients", "data": {"skipped": skipped}}
    return _send_association_message(channel, association, title, content, receive_ids, skipped, "send_im_notification")


def send_im_notification_to_users(channel_id: int, user_ids: list[int], title: str, content: str):
    channel, association, blocked = _ready_association_for_send(channel_id)
    if blocked:
        return blocked
    if not user_ids:
        logger.warning("send_im_notification_to_users: no recipients selected, channel_id=%s", channel_id)
        return {"result": False, "message": "No recipients selected"}
    receive_ids, skipped = _receive_ids_for_requested_users(association, user_ids)
    if not receive_ids:
        logger.warning(
            "send_im_notification_to_users: no usable recipients, channel_id=%s, association_id=%s, skipped=%s",
            channel_id,
            association.id,
            len(skipped),
        )
        return {"result": False, "message": "No usable IM account association recipients", "data": {"skipped": skipped}}
    return _send_association_message(channel, association, title, content, receive_ids, skipped, "send_im_notification_to_users")


def _ready_association_for_send(channel_id: int):
    channel = IMNotificationChannel.objects.select_related("integration_instance", "account_association").filter(id=channel_id, enabled=True).first()
    if not channel:
        logger.warning("send_im_notification: channel not found or disabled, channel_id=%s", channel_id)
        return None, None, {"result": False, "message": "IM notification channel not found"}
    association = channel.account_association
    if association is None:
        logger.warning("send_im_notification: account association not selected, channel_id=%s", channel_id)
        return None, None, {"result": False, "message": "IM notification channel has no account association"}
    if association.status != ASSOCIATION_STATUS_READY:
        logger.warning(
            "send_im_notification: account association has no usable result, channel_id=%s, association_id=%s, association_status=%s",
            channel_id,
            association.id,
            association.status,
        )
        return None, None, {"result": False, "message": "IM account association has no usable result"}
    if not get_integration_capability_availability(channel.integration_instance, "im_notification")["available"]:
        return None, None, {"result": False, "message": "IM notification channel is not ready"}
    return channel, association, None


def _receive_ids_for_requested_users(association: IMAccountAssociation, receivers):
    requested = _requested_users(receivers)
    user_ids = [user.id for _, user in requested if user is not None and not user.disabled]
    mappings = {
        mapping.user_id: mapping for mapping in IMNotificationUserMapping.objects.filter(account_association=association, user_id__in=user_ids)
    }
    conflict_user_ids = _conflict_user_ids(association)
    receive_field = association.external_receive_field
    receive_ids = []
    skipped = []
    for label, user in requested:
        if user is None:
            skipped.append({"receiver": label, "reason": "not_found"})
            continue
        if user.disabled:
            skipped.append({"receiver": user.username, "reason": "disabled"})
            continue
        if user.id in conflict_user_ids:
            skipped.append({"receiver": user.username, "reason": "conflict"})
            continue
        mapping = mappings.get(user.id)
        receive_id = str((mapping.external_snapshot or {}).get(receive_field) or "").strip() if mapping else ""
        if not receive_id:
            skipped.append({"receiver": user.username, "reason": "unassociated"})
            continue
        receive_ids.append(receive_id)
    return receive_ids, skipped


def _requested_users(receivers):
    if not receivers:
        return []
    if all(isinstance(item, int) or (isinstance(item, str) and str(item).isdigit()) for item in receivers):
        users = {user.id: user for user in User.objects.filter(id__in=[int(item) for item in receivers])}
        return [(str(item), users.get(int(item))) for item in receivers]
    users = {user.username: user for user in User.objects.filter(username__in=[str(item) for item in receivers])}
    return [(str(item), users.get(str(item))) for item in receivers]


def _conflict_user_ids(association: IMAccountAssociation) -> set[int]:
    run = (
        IMNotificationSyncRun.objects.filter(
            account_association=association,
            status__in=[SYNC_RUN_STATUS_SUCCESS, SYNC_RUN_STATUS_PARTIAL],
        )
        .order_by("-finished_at", "-id")
        .only("payload")
        .first()
    )
    payload = (run.payload if run else {}) or {}
    if "conflict_user_ids" in payload:
        return _parse_user_ids(payload.get("conflict_user_ids"))
    issue_user_ids = (user_id for issue in payload.get("conflict_issues", []) for user_id in (issue or {}).get("platform_user_ids", []))
    return _parse_user_ids(issue_user_ids)


def _send_association_message(channel, association, title, content, receive_ids, skipped, log_name):
    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=channel.integration_instance.provider_key,
        capability_key="im_notification",
        operation="send_message",
        config=channel.integration_instance.get_runtime_config(),
        title=title,
        content=content,
        receive_id_type=association.external_receive_field,
        receive_ids=receive_ids,
    )
    data = result.to_dict()
    data["skipped"] = skipped
    if result.success:
        logger.info(
            EXTERNAL_SEND_SUCCEEDED,
            log_name,
            channel.id,
            association.id,
            channel.integration_instance.provider_key,
            len(receive_ids),
            len(skipped),
        )
    else:
        logger.error(
            EXTERNAL_SEND_FAILED,
            channel.id,
            association.id,
            "send_message",
            _external_error_type(result),
            channel.integration_instance.provider_key,
            _log_request_id(result),
        )
    return {"result": result.success, "message": result.summary, "data": data}


def _external_error_type(result) -> str:
    errors = getattr(result, "errors", None) or []
    code = getattr(errors[0], "code", "") if errors else ""
    if isinstance(code, str) and _SAFE_LOG_TOKEN.fullmatch(code):
        return code
    return "external_failure"


def _log_request_id(result) -> str:
    request_id = getattr(result, "request_id", "") or ""
    if isinstance(request_id, str) and _SAFE_LOG_TOKEN.fullmatch(request_id):
        return request_id
    return "-"


def association_config_changed(instance: IMAccountAssociation | None, attrs: dict) -> bool:
    if instance is None:
        return False
    for field_name in CRITICAL_ASSOCIATION_FIELDS:
        if field_name not in attrs:
            continue
        if getattr(instance, field_name) != attrs[field_name]:
            return True
    return False


def _build_locked_config_snapshot(association: IMAccountAssociation):
    return {
        "integration_instance_id": association.integration_instance_id,
        "provider_key": association.integration_instance.provider_key,
        "platform_match_field": association.platform_match_field,
        "external_match_field": association.external_match_field,
        "external_receive_field": association.external_receive_field,
        "identity": _identity_values(association.integration_instance),
    }


def _fields_match_snapshot(association: IMAccountAssociation, snapshot: dict) -> bool:
    return all(snapshot.get(field_name) == getattr(association, field_name) for field_name in CRITICAL_ASSOCIATION_FIELDS)


def _identity_values(instance: IntegrationInstance) -> dict:
    config = instance.get_runtime_config() or {}
    return {field_name: config.get(field_name) for field_name in IDENTITY_FIELDS_BY_PROVIDER.get(instance.provider_key, ())}


def _snapshot_still_current(association: IMAccountAssociation, snapshot: dict) -> bool:
    if not _fields_match_snapshot(association, snapshot):
        return False
    locked_identity = snapshot.get("identity")
    if not isinstance(locked_identity, dict):
        return True
    current_identity = _identity_values(association.integration_instance)
    return all(locked_identity.get(field_name) == current_identity.get(field_name) for field_name in current_identity)


def refresh_notification_channel_status(association: IMAccountAssociation) -> None:
    next_status = CHANNEL_STATUS_READY if association.status == ASSOCIATION_STATUS_READY else CHANNEL_STATUS_NEEDS_RESYNC
    IMNotificationChannel.objects.filter(account_association=association, enabled=True).exclude(status=CHANNEL_STATUS_DISABLED).update(
        status=next_status
    )


def invalidate_account_associations_for_identity_change(instance: IntegrationInstance) -> None:
    associations = list(instance.account_associations.all())
    if not associations:
        return
    IMAccountAssociation.objects.filter(id__in=[item.id for item in associations]).update(status=ASSOCIATION_STATUS_NEEDS_RESYNC)
    for association in associations:
        association.status = ASSOCIATION_STATUS_NEEDS_RESYNC
        refresh_notification_channel_status(association)


def _locked_running_sync_run(run_id: int) -> IMNotificationSyncRun | None:
    run = IMNotificationSyncRun.objects.select_for_update().get(pk=run_id)
    if run.status == SYNC_RUN_STATUS_RUNNING:
        return run
    logger.warning(SYNC_WRITE_SKIPPED, run.id, run.account_association_id)
    return None


def _fail_sync_run(run: IMNotificationSyncRun, summary: str, payload: dict | None = None):
    now = timezone.now()
    with transaction.atomic():
        locked_run = _locked_running_sync_run(run.id)
        if locked_run is None:
            return {"result": False, "message": UPDATE_NO_LONGER_RUNNING}
        locked_run.status = SYNC_RUN_STATUS_FAILED
        locked_run.summary = summary
        locked_run.payload = payload or {}
        locked_run.finished_at = now
        locked_run.save(update_fields=["status", "summary", "payload", "finished_at", "updated_at"])
        association = (
            IMAccountAssociation.objects.select_for_update().select_related("integration_instance").get(pk=locked_run.account_association_id)
        )
        snapshot = locked_run.locked_config_snapshot or {}
        if association.status == ASSOCIATION_STATUS_READY and _snapshot_still_current(association, snapshot):
            return {"result": False, "message": summary}
        association.status = ASSOCIATION_STATUS_NEEDS_RESYNC
        association.save(update_fields=["status", "updated_at"])
        refresh_notification_channel_status(association)
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

    kept, conflict_issues = _without_duplicate_matches(matched_relations, conflict_issues)
    return kept, unmatched_issues, conflict_issues


def _without_duplicate_matches(matched_relations: list[dict], conflict_issues: list[dict]):
    by_user: dict[int, list[dict]] = defaultdict(list)
    by_identity: dict[tuple, list[dict]] = defaultdict(list)
    for relation in matched_relations:
        by_user[relation["user"].id].append(relation)
        by_identity[(relation["external_identity_key"], relation["external_identity_value"])].append(relation)
    rejected = set()
    for relations in list(by_user.values()) + list(by_identity.values()):
        if len(relations) < 2:
            continue
        for relation in relations:
            rejected.add(id(relation))
        conflict_issues.append(
            {
                "reason": "duplicate_match",
                "platform_user_ids": sorted({relation["user"].id for relation in relations}),
                "external_identity_key": relations[0]["external_identity_key"],
                "external_identity_value": relations[0]["external_identity_value"],
            }
        )
    return [relation for relation in matched_relations if id(relation) not in rejected], conflict_issues


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
    return (
        set(template.available_external_fields or [])
        | set(template.identity_fields or [])
        | set(template.matchable_fields or [])
        | set(template.receivable_fields or [])
        | {"name"}
    )


def _sanitize_external_snapshot(external_user: dict, allowed_fields: set[str]) -> dict:
    if not isinstance(external_user, dict):
        return {}
    return {key: value for key, value in external_user.items() if key in allowed_fields and not _is_sensitive_field(key) and _is_safe_scalar(value)}


def _build_sync_run_payload(result, unmatched_issues: list[dict], conflict_issues: list[dict]) -> dict:
    result_payload = result.to_dict()
    safe_payload = _sanitize_result_payload(result_payload.get("payload") or {})
    result_payload["payload"] = safe_payload
    result_payload["unmatched_issues"] = unmatched_issues[:MAX_DIAGNOSTIC_ISSUES]
    result_payload["conflict_issues"] = conflict_issues[:MAX_DIAGNOSTIC_ISSUES]
    result_payload["unmatched_issue_count"] = len(unmatched_issues)
    result_payload["conflict_issue_count"] = len(conflict_issues)
    result_payload["conflict_user_ids"] = sorted(
        _parse_user_ids(user_id for issue in conflict_issues for user_id in (issue or {}).get("platform_user_ids", []))
    )
    return result_payload


def _parse_user_ids(values) -> set[int]:
    user_ids = set()
    for user_id in values:
        try:
            user_ids.add(int(user_id))
        except (TypeError, ValueError):
            continue
    return user_ids


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
