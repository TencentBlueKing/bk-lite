from copy import deepcopy
from types import SimpleNamespace

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.system_mgmt.models import (
    Group,
    User,
    UserSyncRun,
    UserSyncRunStatusChoices,
    UserSyncSource,
    UserSyncTriggerModeChoices,
)
from apps.system_mgmt.providers import RuntimeApplicationService

DEFAULT_FIELD_MAPPING = {
    "username": "user_id",
    "display_name": "name",
    "email": "email",
    "phone": "mobile",
}
ALL_DEPARTMENT_SELECTION_ID = "__all__"


def get_user_sync_business_value(source, key: str, default=None):
    """Read a provider business parameter from canonical business_config."""
    business_config = getattr(source, "business_config", None) or {}
    return business_config.get(key, default)


def get_user_sync_root_department_input_mode(provider_key: str) -> str:
    """Return the input_mode for root_department_id in the user_sync capability.

    Defaults to department_select when the provider/manifest/field does not declare one.
    """
    runtime_service = RuntimeApplicationService()
    try:
        manifest = runtime_service.get_provider_manifest(provider_key)
    except ValueError:
        return "department_select"

    capability = manifest.get_capability("user_sync")
    if capability is None or not capability.business_template:
        return "department_select"

    business_template = manifest.business_templates.get(capability.business_template)
    if business_template is None:
        return "department_select"

    for group in business_template.groups:
        for field in group.fields:
            if field.key == "root_department_id":
                return field.input_mode or "department_select"
    return "department_select"


def normalize_root_department_selection(selected_value: str, payload: dict) -> str:
    selected_value = str(selected_value or "")
    if selected_value == ALL_DEPARTMENT_SELECTION_ID:
        return str((payload or {}).get("all_department_id") or selected_value)
    return selected_value


def flatten_department_ids(items: list[dict]) -> set[str]:
    flattened_ids: set[str] = set()
    for item in items or []:
        item_id = str((item or {}).get("id") or "")
        if item_id:
            flattened_ids.add(item_id)
        flattened_ids.update(flatten_department_ids((item or {}).get("children") or []))
    return flattened_ids


def execute_user_sync(source_id: int, trigger_mode: str = UserSyncTriggerModeChoices.MANUAL):
    source = UserSyncSource.objects.select_related("integration_instance").filter(id=source_id, enabled=True).first()
    if not source:
        return {"result": False, "message": "User sync source not found"}

    instance = source.integration_instance
    if not instance.enabled or instance.status != "ready" or instance.capability_status.get("user_sync") != "ready":
        return {"result": False, "message": "User sync source is not ready"}

    run = UserSyncRun.objects.create(source=source, trigger_mode=trigger_mode, status=UserSyncRunStatusChoices.RUNNING, summary="User sync started")
    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=instance.provider_key,
        capability_key="user_sync",
        operation="sync_users",
        config=instance.get_runtime_config(),
        source=source,
    )
    input_summary = _extract_input_summary(result.payload)

    run.request_id = result.request_id
    if not result.success:
        run.status = UserSyncRunStatusChoices.FAILED
        run.summary = result.summary
        run.payload = _build_run_payload(result, input_summary)
        run.finished_at = timezone.now()
        run.save(update_fields=["request_id", "status", "summary", "payload", "finished_at", "updated_at"])
        return {"result": False, "message": result.summary, "data": UserSyncRun.objects.filter(id=run.id).values().first()}

    try:
        sync_summary = _apply_user_sync_payload(source, result.payload)
    except Exception as error:
        logger.exception(f"User sync failed for source '{source.name}': {error}")
        run.status = UserSyncRunStatusChoices.FAILED
        run.summary = str(error)
        run.payload = _build_run_payload(result, input_summary)
        run.finished_at = timezone.now()
        run.save(update_fields=["request_id", "status", "summary", "payload", "finished_at", "updated_at"])
        return {"result": False, "message": str(error)}

    run.status = UserSyncRunStatusChoices.SUCCESS
    run.summary = sync_summary["summary"]
    run.synced_user_count = sync_summary["synced_user_count"]
    run.synced_group_count = sync_summary["synced_group_count"]
    run.disabled_user_count = sync_summary["disabled_user_count"]
    run.payload = _build_run_payload(result, input_summary)
    run.finished_at = timezone.now()
    run.save(
        update_fields=[
            "request_id",
            "status",
            "summary",
            "synced_user_count",
            "synced_group_count",
            "disabled_user_count",
            "payload",
            "finished_at",
            "updated_at",
        ]
    )
    return {"result": True, "message": run.summary, "data": {"run_id": run.id}}


def sync_source_now(source_id: int):
    from apps.system_mgmt.tasks import execute_user_sync_source

    execute_user_sync_source.delay(source_id, UserSyncTriggerModeChoices.MANUAL)


def preview_user_sync(source: UserSyncSource) -> dict:
    """Fetch provider data without creating a UserSyncRun or persisting users/groups.

    Returns estimated counts and provider result metadata.
    """
    instance = source.integration_instance
    if not instance.enabled or instance.status != "ready" or instance.capability_status.get("user_sync") != "ready":
        return {"result": False, "message": "User sync source is not ready"}

    runtime_service = RuntimeApplicationService()
    result = runtime_service.execute(
        provider_key=instance.provider_key,
        capability_key="user_sync",
        operation="sync_users",
        config=instance.get_runtime_config(),
        source=source,
    )

    if not result.success:
        logger.warning(f"User sync preview failed for source '{getattr(source, 'name', '')}': {result.summary}")
        return {"result": False, "message": result.summary, "data": result.to_dict()}

    group_count = len(result.payload.get("group_list") or [])
    user_count = len(result.payload.get("user_list") or [])
    provider_metadata = {k: v for k, v in result.payload.items() if k not in ("group_list", "user_list")}

    logger.info(
        f"User sync preview completed: estimated {user_count} users, {group_count} groups "
        f"for source '{getattr(source, 'name', '')}'"
    )
    return {
        "result": True,
        "message": f"Preview: estimated {user_count} users, {group_count} groups",
        "data": {
            "estimated_user_count": user_count,
            "estimated_group_count": group_count,
            "provider_metadata": provider_metadata,
        },
    }


def get_user_sync_available_instances():
    return UserSyncSource._meta.get_field("integration_instance").remote_field.model.objects.filter(
        enabled=True,
        status="ready",
    ).order_by("name", "id")


def _extract_input_summary(provider_payload: dict | None):
    payload = provider_payload or {}
    return {
        "fetched_user_count": len(payload.get("user_list") or []),
        "fetched_group_count": len(payload.get("group_list") or []),
    }


def _build_run_payload(result, input_summary: dict):
    provider_payload = result.payload or {}
    return {
        "external_request_id": str(provider_payload.get("external_request_id") or ""),
        "errors": [item.model_dump() for item in result.errors],
        "input_summary": input_summary,
    }


def _apply_user_sync_payload(source: UserSyncSource, payload: dict):
    group_list = deepcopy(payload.get("group_list") or [])
    user_list = deepcopy(payload.get("user_list") or [])
    root_department_id = get_user_sync_business_value(source, "root_department_id", "0") or "0"

    with transaction.atomic():
        root_group = _get_or_create_root_group(source)
        group_id_mapping, active_group_ids = _sync_groups(source, group_list, root_group, root_department_id)
        synced_usernames, disabled_user_count = _sync_users(source, user_list, group_id_mapping, root_group.id, root_department_id)
        stale_group_ids = list(Group.objects.filter(sync_source=source).exclude(id__in=active_group_ids).exclude(id=root_group.id).values_list("id", flat=True))
        if stale_group_ids:
            Group.objects.filter(id__in=stale_group_ids).delete()
        summary = (
            f"User sync completed: {len(synced_usernames)} users, {len(active_group_ids) - 1 if active_group_ids else 0} groups"
        )
        return {
            "summary": summary,
            "synced_user_count": len(synced_usernames),
            "synced_group_count": max(len(active_group_ids) - 1, 0),
            "disabled_user_count": disabled_user_count,
        }


def _get_or_create_root_group(source: UserSyncSource):
    root_department_id = get_user_sync_business_value(source, "root_department_id", "0") or "0"
    defaults = {
        "description": f"user_sync_source_{source.id}",
        "sync_source": source,
        "external_id": _scoped_external_id(source.id, root_department_id),
    }
    root_group, created = Group.objects.get_or_create(parent_id=0, name=source.root_group_name, defaults=defaults)
    changed = False
    if root_group.sync_source_id != source.id:
        root_group.sync_source = source
        changed = True
    if root_group.external_id != defaults["external_id"]:
        root_group.external_id = defaults["external_id"]
        changed = True
    if created:
        return root_group
    if changed:
        root_group.save(update_fields=["sync_source", "external_id"])
    return root_group


def _sync_groups(source: UserSyncSource, group_list: list[dict], root_group: Group, root_department_id: str):
    group_lookup = {str(item.get("id")): item for item in group_list if item.get("id") not in (None, "")}
    child_map: dict[str, list[dict]] = {}
    for item in group_list:
        item_id = str(item.get("id", ""))
        if not item_id:
            continue
        parent_id = str(item.get("parent_id") or "")
        child_map.setdefault(parent_id, []).append(item)

    group_id_mapping = {root_department_id: root_group.id}
    active_group_ids = {root_group.id}

    def walk(parent_external_id: str, parent_group: Group):
        current_items = child_map.get(parent_external_id, [])
        scoped_ids = {_scoped_external_id(source.id, str(item["id"])) for item in current_items}
        existing_groups = Group.objects.filter(parent_id=parent_group.id, sync_source=source)
        existing_by_external_id = {group.external_id: group for group in existing_groups if group.external_id}

        stale_ids = [group.id for group in existing_groups if group.external_id not in scoped_ids]
        if stale_ids:
            Group.objects.filter(id__in=stale_ids).delete()

        for item in current_items:
            external_id = str(item["id"])
            scoped_external_id = _scoped_external_id(source.id, external_id)
            group = existing_by_external_id.get(scoped_external_id)
            if group is None:
                group = Group.objects.create(
                    name=item.get("name", external_id),
                    parent_id=parent_group.id,
                    external_id=scoped_external_id,
                    description=f"user_sync_source_{source.id}",
                    sync_source=source,
                )
            else:
                update_fields = []
                if group.name != item.get("name", external_id):
                    group.name = item.get("name", external_id)
                    update_fields.append("name")
                if group.sync_source_id != source.id:
                    group.sync_source = source
                    update_fields.append("sync_source")
                if update_fields:
                    group.save(update_fields=update_fields)
            group_id_mapping[external_id] = group.id
            active_group_ids.add(group.id)
            walk(external_id, group)

    walk(root_department_id, root_group)
    return group_id_mapping, list(active_group_ids)


def _sync_users(source: UserSyncSource, user_list: list[dict], group_id_mapping: dict, root_group_id: int, root_department_id: str):
    field_mapping = {**DEFAULT_FIELD_MAPPING, **(source.field_mapping or {})}
    normalized_users = []
    for raw_user in user_list:
        username = str(_mapped_value(raw_user, field_mapping, "username") or raw_user.get("user_id") or raw_user.get("open_id") or "").strip()
        if not username:
            continue
        departments = [str(item) for item in raw_user.get("department_ids") or raw_user.get("departments") or []]
        local_group_ids = []
        for department_id in departments:
            local_group_id = group_id_mapping.get(department_id)
            if local_group_id:
                local_group_ids.append(local_group_id)
            elif department_id == root_department_id:
                local_group_ids.append(root_group_id)
        if not local_group_ids:
            local_group_ids = [root_group_id]
        normalized_users.append(
            {
                "username": username,
                "display_name": str(_mapped_value(raw_user, field_mapping, "display_name") or username),
                "email": str(_mapped_value(raw_user, field_mapping, "email") or ""),
                "phone": str(_mapped_value(raw_user, field_mapping, "phone") or ""),
                "group_list": sorted(set(local_group_ids)),
            }
        )

    usernames = [item["username"] for item in normalized_users]
    existing_users = User.objects.select_related("sync_source").filter(username__in=usernames, domain="domain.com")
    existing_user_map = {user.username: user for user in existing_users}
    synced_usernames = []
    create_users = []
    update_users = []

    for item in normalized_users:
        synced_usernames.append(item["username"])
        user = existing_user_map.get(item["username"])
        if user is None:
            create_users.append(
                User(
                    username=item["username"],
                    display_name=item["display_name"],
                    email=item["email"],
                    phone=item["phone"],
                    password=make_password(""),
                    domain="domain.com",
                    disabled=False,
                    group_list=item["group_list"],
                    sync_source=source,
                )
            )
            continue

        _ensure_user_sync_source_match(user, source, item["username"])

    if create_users:
        User.objects.bulk_create(create_users, ignore_conflicts=True, batch_size=100)

    synced_users = User.objects.select_related("sync_source").filter(username__in=usernames, domain="domain.com")
    synced_user_map = {user.username: user for user in synced_users}

    for item in normalized_users:
        user = synced_user_map.get(item["username"])
        if user is None:
            continue

        _ensure_user_sync_source_match(user, source, item["username"])

        changed = False
        for field in ("display_name", "email", "phone", "group_list"):
            if getattr(user, field) != item[field]:
                setattr(user, field, item[field])
                changed = True
        if user.disabled:
            user.disabled = False
            changed = True
        if user.sync_source_id != source.id:
            user.sync_source = source
            changed = True
        if changed:
            update_users.append(user)

    if update_users:
        User.objects.bulk_update(update_users, ["display_name", "email", "phone", "group_list", "disabled", "sync_source"], batch_size=100)

    disabled_user_count = 0
    stale_users = User.objects.filter(sync_source=source, domain="domain.com").exclude(username__in=synced_usernames)
    for user in stale_users:
        if not user.disabled or user.group_list:
            user.disabled = True
            user.group_list = []
            user.save(update_fields=["disabled", "group_list"])
            disabled_user_count += 1

    affected_usernames = {user.username for user in create_users + update_users}
    affected_usernames.update(user.username for user in stale_users)
    if affected_usernames:
        clear_users_permission_cache([{"username": username, "domain": "domain.com"} for username in affected_usernames])

    return synced_usernames, disabled_user_count


def _ensure_user_sync_source_match(user: User, source: UserSyncSource, username: str):
    owner_source = None
    if user.sync_source_id not in (None, source.id):
        owner_source = user.sync_source
    elif user.group_list:
        owner_source = (
            Group.objects.select_related("sync_source")
            .filter(id__in=user.group_list)
            .exclude(sync_source__isnull=True)
            .exclude(sync_source=source)
            .values_list("sync_source__name", "sync_source_id")
            .first()
        )

    if owner_source is None:
        return

    if isinstance(owner_source, tuple):
        owner_name = owner_source[0] or f"source-{owner_source[1]}"
    else:
        owner_name = getattr(owner_source, "name", f"source-{owner_source.id}")
    raise ValueError(
        f"User '{username}' already belongs to user sync source '{owner_name}' "
        f"and cannot be synced by '{source.name}'"
    )


def _mapped_value(raw_user: dict, field_mapping: dict, logical_key: str):
    source_key = field_mapping.get(logical_key, DEFAULT_FIELD_MAPPING.get(logical_key, logical_key))
    return raw_user.get(source_key)


def _scoped_external_id(source_id: int, external_id: str):
    return f"user-sync:{source_id}:{external_id}"
