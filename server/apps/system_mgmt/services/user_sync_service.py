import hashlib
from copy import deepcopy
from types import SimpleNamespace
import uuid

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.db.utils import NotSupportedError
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

    root_scope_field = get_user_sync_root_scope_field(provider_key)
    for group in business_template.groups:
        for field in group.fields:
            if field.key == root_scope_field:
                return field.input_mode or "department_select"
    return "department_select"


def get_user_sync_root_scope_field(provider_key: str) -> str:
    """Resolve the provider-specific root scope field for user sync."""
    runtime_service = RuntimeApplicationService()
    try:
        manifest = runtime_service.get_provider_manifest(provider_key)
    except ValueError:
        return "root_department_id"

    capability = manifest.get_capability("user_sync")
    if capability is None or not capability.business_template:
        return "root_department_id"

    business_template = manifest.business_templates.get(capability.business_template)
    if business_template is None:
        return "root_department_id"

    for group in business_template.groups:
        for field in group.fields:
            if str(field.key or "").startswith("root_"):
                return field.key
    return "root_department_id"


def get_user_sync_root_scope_value(source, default=None):
    """Read the provider-specific root scope value from business_config."""
    integration_instance = getattr(source, "integration_instance", None)
    provider_key = getattr(integration_instance, "provider_key", "")
    root_scope_field = get_user_sync_root_scope_field(provider_key) if provider_key else "root_department_id"
    business_config = getattr(source, "business_config", None) or {}
    if root_scope_field in business_config:
        return business_config.get(root_scope_field, default)
    return business_config.get("root_department_id", default)


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
    source = UserSyncSource.objects.select_related("integration_instance").filter(id=source_id).first()
    if not source:
        return {"result": False, "message": "User sync source not found"}
    if not source.enabled:
        return _create_failed_user_sync_run(source, trigger_mode, "User sync source is disabled")

    instance = source.integration_instance
    if not instance.enabled or instance.status != "ready" or instance.capability_status.get("user_sync") != "ready":
        return {"result": False, "message": "User sync source is not ready"}

    if UserSyncRun.objects.filter(source=source, status=UserSyncRunStatusChoices.RUNNING).exists():
        return {"result": False, "message": "User sync is already running"}

    try:
        run = UserSyncRun.objects.create(source=source, trigger_mode=trigger_mode, status=UserSyncRunStatusChoices.RUNNING, summary="User sync started")
    except IntegrityError:
        return {"result": False, "message": "User sync is already running"}
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
        run.payload = _build_run_payload(result, input_summary, current_run=run)
        run.finished_at = timezone.now()
        run.save(update_fields=["request_id", "status", "summary", "payload", "finished_at", "updated_at"])
        return {"result": False, "message": result.summary, "data": UserSyncRun.objects.filter(id=run.id).values().first()}

    try:
        sync_summary = _apply_user_sync_payload(source, result.payload, current_run=run)
    except Exception as error:
        logger.exception(f"User sync failed for source '{source.name}': {error}")
        run.status = UserSyncRunStatusChoices.FAILED
        run.summary = str(error)
        run.payload = _build_run_payload(result, input_summary, current_run=run)
        run.finished_at = timezone.now()
        run.save(update_fields=["request_id", "status", "summary", "payload", "finished_at", "updated_at"])
        return {"result": False, "message": str(error)}

    if sync_summary["conflict_usernames"]:
        run.status = (
            UserSyncRunStatusChoices.FAILED
            if sync_summary["synced_user_count"] == 0
            else UserSyncRunStatusChoices.PARTIAL
        )
    else:
        run.status = UserSyncRunStatusChoices.SUCCESS
    run.summary = sync_summary["summary"]
    run.synced_user_count = sync_summary["synced_user_count"]
    run.synced_group_count = sync_summary["synced_group_count"]
    run.disabled_user_count = sync_summary["disabled_user_count"]
    run.payload = _build_run_payload(result, input_summary, sync_summary, current_run=run)
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


def _create_failed_user_sync_run(source: UserSyncSource, trigger_mode: str, summary: str):
    run = UserSyncRun.objects.create(
        source=source,
        trigger_mode=trigger_mode,
        status=UserSyncRunStatusChoices.FAILED,
        summary=summary,
        finished_at=timezone.now(),
    )
    return {"result": False, "message": summary, "data": {"run_id": run.id}}

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


def _build_run_payload(
    result,
    input_summary: dict,
    sync_summary: dict | None = None,
    current_run: "UserSyncRun | None" = None,
):
    """组装 run.payload。

    2026-07-15 修:之前会整个覆盖 payload,导致 _sync_users 内
    password_init_service._stash_to_vault 写入的 password_vault /
    email_status 被清空,Celery 任务看到 vault 缺。
    现在从 current_run.payload 继承 password_vault / email_status /
    email_dispatch，避免异步批量邮件任务丢失待领取条目。
    """
    provider_payload = result.payload or {}
    payload = {
        "external_request_id": str(provider_payload.get("external_request_id") or ""),
        "errors": [item.model_dump() for item in result.errors],
        "input_summary": input_summary,
    }
    if sync_summary is not None:
        payload["conflict_usernames"] = list(sync_summary.get("conflict_usernames") or [])
        payload["conflict_user_count"] = len(payload["conflict_usernames"])
    # 继承 service 之前写入的密码邮件状态(避免被同步结果覆盖)
    if current_run is not None:
        existing = current_run.payload or {}
        for key in ("password_vault", "email_status", "email_dispatch"):
            if key in existing and key not in payload:
                payload[key] = existing[key]
    return payload


def _apply_user_sync_payload(source: UserSyncSource, payload: dict, current_run: "UserSyncRun | None" = None):
    group_list = deepcopy(payload.get("group_list") or [])
    user_list = deepcopy(payload.get("user_list") or [])
    root_scope_value = str(get_user_sync_root_scope_value(source, "0") or "0")

    with transaction.atomic():
        root_group = _get_or_create_root_group(source)
        group_id_mapping, active_group_ids = _sync_groups(source, group_list, root_group, root_scope_value)
        synced_usernames, disabled_user_count, conflict_usernames = _sync_users(
            source,
            user_list,
            group_id_mapping,
            root_group.id,
            root_scope_value,
            current_run=current_run,
        )
        stale_group_ids = list(Group.objects.filter(sync_source=source).exclude(id__in=active_group_ids).exclude(id=root_group.id).values_list("id", flat=True))
        if stale_group_ids:
            Group.objects.filter(id__in=stale_group_ids).delete()

        synced_group_count = max(len(active_group_ids) - 1, 0)
        if conflict_usernames:
            if not synced_usernames:
                summary = (
                    f"User sync failed: all {len(conflict_usernames)} users conflicted, "
                    f"{synced_group_count} groups"
                )
            else:
                summary = (
                    f"User sync partially completed: {len(synced_usernames)} users, "
                    f"{synced_group_count} groups, {len(conflict_usernames)} conflicts"
                )
        else:
            summary = f"User sync completed: {len(synced_usernames)} users, {synced_group_count} groups"
        return {
            "summary": summary,
            "synced_user_count": len(synced_usernames),
            "synced_group_count": synced_group_count,
            "disabled_user_count": disabled_user_count,
            "conflict_usernames": conflict_usernames,
        }


def _get_or_create_root_group(source: UserSyncSource):
    root_scope_value = str(get_user_sync_root_scope_value(source, "0") or "0")
    defaults = {
        "description": f"user_sync_source_{source.id}",
        "sync_source": source,
        "external_id": _scoped_external_id(source.id, root_scope_value),
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
            group_name = _truncate_to_field(Group, "name", str(item.get("name", external_id)))
            group = existing_by_external_id.get(scoped_external_id)
            if group is None:
                group = Group.objects.create(
                    name=group_name,
                    parent_id=parent_group.id,
                    external_id=scoped_external_id,
                    description=f"user_sync_source_{source.id}",
                    sync_source=source,
                )
            else:
                update_fields = []
                if group.name != group_name:
                    group.name = group_name
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


def _sync_users(
    source: UserSyncSource,
    user_list: list[dict],
    group_id_mapping: dict,
    root_group_id: int,
    root_department_id: str,
    current_run: "UserSyncRun | None" = None,
):
    field_mapping = {**DEFAULT_FIELD_MAPPING, **(source.field_mapping or {})}
    normalized_users = []
    for raw_user in user_list:
        username = str(_mapped_value(raw_user, field_mapping, "username") or raw_user.get("user_id") or raw_user.get("open_id") or "").strip()
        if not username:
            continue
        # 截断后的 username 同时作为本轮匹配键,保证与写库值一致
        username = _truncate_to_field(User, "username", username)
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
                "display_name": _truncate_to_field(
                    User, "display_name", str(_mapped_value(raw_user, field_mapping, "display_name") or username)
                ),
                "email": _truncate_to_field(User, "email", str(_mapped_value(raw_user, field_mapping, "email") or "")),
                "phone": _truncate_to_field(User, "phone", str(_mapped_value(raw_user, field_mapping, "phone") or "")),
                "group_list": sorted(set(local_group_ids)),
            }
        )

    usernames = [item["username"] for item in normalized_users]
    # `domain` is a deprecated compatibility field. Synced users intentionally
    # stay in the legacy default domain until the column is removed.
    legacy_domain = "domain.com"
    existing_users = User.objects.select_related("sync_source").filter(username__in=usernames, domain=legacy_domain)
    existing_user_map = {user.username: user for user in existing_users}
    synced_usernames = []
    conflict_usernames = []
    new_users = []  # 本次同步新建的 user(需要触发密码初始化)
    update_users = []

    # 解析平台侧 password_init 配置;仅在新建用户时触发。
    password_init_cfg = (source.platform_config or {}).get("password_init") or {}
    password_init_mode = password_init_cfg.get("mode")

    for item in normalized_users:
        user = existing_user_map.get(item["username"])
        if user is None:
            try:
                new_user = User.objects.create(
                    user_id=str(uuid.uuid4()),
                    username=item["username"],
                    display_name=item["display_name"],
                    email=item["email"],
                    phone=item["phone"],
                    password=make_password(""),
                    domain=legacy_domain,
                    disabled=False,
                    group_list=item["group_list"],
                    sync_source=source,
                )
                new_users.append(new_user)
            except IntegrityError:
                # race condition:同名 user 在本轮 sync 中被另一 source 创建 → 标记为 conflict
                conflict_usernames.append(item["username"])
            continue

        try:
            _ensure_user_sync_source_match(user, source, item["username"])
        except ValueError:
            conflict_usernames.append(item["username"])

    # 触发密码初始化(仅首次创建;后续周期同步不动 password)
    if new_users and password_init_mode:
        from apps.system_mgmt.services.password_init_service import init_password_for_user

        run_for_init = current_run or UserSyncRun.objects.filter(
            source=source, status=UserSyncRunStatusChoices.RUNNING
        ).first()
        for new_user in new_users:
            try:
                init_result = init_password_for_user(new_user, password_init_mode, password_init_cfg, run_for_init)
                if init_result.get("status") != "ok":
                    from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL_MARK

                    new_user.password = PASSWORD_INIT_SENTINEL_MARK
                    new_user.temporary_pwd = False
                    new_user.save(update_fields=["password", "temporary_pwd"])
                    logger.warning(
                        f"init_password_for_user 被拒绝 username={new_user.username}: {init_result.get('reason')}"
                    )
            except Exception as e:
                from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL_MARK

                new_user.password = PASSWORD_INIT_SENTINEL_MARK
                new_user.temporary_pwd = False
                new_user.save(update_fields=["password", "temporary_pwd"])
                logger.warning(
                    f"init_password_for_user 失败 username={new_user.username}: {e}",
                )

    synced_users = User.objects.select_related("sync_source").filter(username__in=usernames, domain=legacy_domain)
    synced_user_map = {user.username: user for user in synced_users}

    for item in normalized_users:
        user = synced_user_map.get(item["username"])
        if user is None:
            continue

        try:
            _ensure_user_sync_source_match(user, source, item["username"])
        except ValueError:
            if item["username"] not in conflict_usernames:
                conflict_usernames.append(item["username"])
            continue

        if item["username"] not in synced_usernames:
            synced_usernames.append(item["username"])

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
    stale_users = User.objects.filter(sync_source=source, domain=legacy_domain).exclude(username__in=synced_usernames)
    for user in stale_users:
        if not user.disabled or user.group_list:
            user.disabled = True
            user.group_list = []
            user.save(update_fields=["disabled", "group_list"])
            disabled_user_count += 1

    affected_usernames = {user.username for user in new_users + update_users}
    affected_usernames.update(user.username for user in stale_users)
    if affected_usernames:
        clear_users_permission_cache([{"username": username, "domain": legacy_domain} for username in affected_usernames])

    return synced_usernames, disabled_user_count, sorted(set(conflict_usernames))


def _ensure_user_sync_source_match(user: User, source: UserSyncSource, username: str):
    owner_source = None
    if user.sync_source_id is None:
        raise ValueError(
            f"User '{username}' already exists as an unmanaged platform user "
            f"and cannot be claimed by '{source.name}'"
        )
    if user.sync_source_id != source.id:
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


def _truncate_to_field(model, field_name: str, value: str) -> str:
    """按模型字段 max_length 截断外部数据,防止超长值(如 AD 的 DN/名称)溢出 varchar 上限。"""
    max_length = model._meta.get_field(field_name).max_length
    if max_length is None or len(value) <= max_length:
        return value
    return value[:max_length]


def _scoped_external_id(source_id: int, external_id: str):
    scoped = f"user-sync:{source_id}:{external_id}"
    max_length = Group._meta.get_field("external_id").max_length
    if max_length is None or len(scoped) <= max_length:
        return scoped
    # 外部 ID 超长(如 AD 组织的 DN):截断并追加摘要。同一外部 ID 每轮生成相同值
    # (否则每轮同步都会删除重建组),不同外部 ID 截断后也不会互相碰撞。
    digest = hashlib.sha256(external_id.encode("utf-8")).hexdigest()[:16]
    prefix = f"user-sync:{source_id}:"
    keep = max_length - len(prefix) - len(digest) - 1
    return f"{prefix}{external_id[:max(keep, 0)]}~{digest}"


def _get_user_sync_root_group(source: UserSyncSource):
    return Group.objects.filter(parent_id=0, sync_source=source, name=source.root_group_name).order_by("id").first()


def _collect_group_subtree_ids(root_group_id: int):
    subtree_ids = {root_group_id}
    frontier = [root_group_id]
    while frontier:
        child_ids = list(Group.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
        frontier = [group_id for group_id in child_ids if group_id not in subtree_ids]
        subtree_ids.update(frontier)
    return subtree_ids


def _collect_user_ids_for_group_subtree(group_ids: set[int]):
    if not group_ids:
        return set()

    query = Q()
    for group_id in group_ids:
        query |= Q(group_list__contains=[group_id])

    try:
        return set(User.objects.filter(query).values_list("id", flat=True))
    except NotSupportedError:
        candidate_users = User.objects.exclude(group_list=[]).exclude(group_list__isnull=True).only("id", "group_list")
        return {user.id for user in candidate_users if set(user.group_list or []).intersection(group_ids)}


def delete_user_sync_source(source: UserSyncSource):
    root_group = _get_user_sync_root_group(source)
    subtree_ids = _collect_group_subtree_ids(root_group.id) if root_group else set()

    users_to_delete = set(User.objects.filter(sync_source=source).values_list("id", flat=True))
    users_to_delete.update(_collect_user_ids_for_group_subtree(subtree_ids))
    affected_usernames = list(User.objects.filter(id__in=users_to_delete).values("username", "domain"))

    with transaction.atomic():
        if users_to_delete:
            User.objects.filter(id__in=users_to_delete).delete()
        if subtree_ids:
            Group.objects.filter(id__in=subtree_ids).delete()
        source.delete()

    if affected_usernames:
        clear_users_permission_cache(affected_usernames)

    return {
        "result": True,
        "message": "User sync source deleted",
        "data": {
            "deleted_group_count": len(subtree_ids),
            "deleted_user_count": len(users_to_delete),
        },
    }


def detect_root_group_name_conflicts():
    duplicate_names = (
        UserSyncSource.objects.exclude(root_group_name="")
        .values("root_group_name")
        .annotate(source_count=Count("id"))
        .filter(source_count__gt=1)
    )
    conflicts = {}
    for item in duplicate_names:
        root_group_name = item["root_group_name"]
        conflicts[root_group_name] = list(
            UserSyncSource.objects.filter(root_group_name=root_group_name)
            .order_by("id")
            .values_list("id", flat=True)
        )
    return conflicts


def is_root_group_name_reserved(root_group_name: str, current_source_id: int | None = None):
    queryset = UserSyncSource.objects.filter(root_group_name=root_group_name, enabled=True)
    if current_source_id is not None:
        queryset = queryset.exclude(id=current_source_id)
    return queryset.exists()
