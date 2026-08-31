import hashlib
import os
import uuid
from copy import deepcopy
from datetime import timedelta
from threading import Event, Thread

from django.contrib.auth.hashers import make_password
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.db.models import Count
from django.db.utils import OperationalError
from django.utils import timezone

from apps.core.logger import system_mgmt_logger as logger
from apps.core.utils.permission_cache import clear_users_permission_cache
from apps.system_mgmt.models import Group, User, UserSyncRun, UserSyncRunStatusChoices, UserSyncSource, UserSyncTriggerModeChoices
from apps.system_mgmt.providers import RuntimeApplicationService
from apps.system_mgmt.services.capability_contract_service import get_integration_capability_availability
from apps.system_mgmt.services.group_archive_service import GroupArchiveService

DEFAULT_FIELD_MAPPING = {
    "username": "user_id",
    "display_name": "name",
    "email": "email",
    "phone": "mobile",
}
DEFAULT_USER_SYNC_STALE_TIMEOUT_SECONDS = 6 * 60 * 60
MAX_USER_SYNC_HEARTBEAT_INTERVAL_SECONDS = 60


def _get_user_sync_stale_timeout_seconds() -> int:
    raw_value = os.getenv(
        "USER_SYNC_STALE_TIMEOUT_SECONDS",
        str(DEFAULT_USER_SYNC_STALE_TIMEOUT_SECONDS),
    )
    try:
        timeout_seconds = int(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid USER_SYNC_STALE_TIMEOUT_SECONDS=%r; using default %s",
            raw_value,
            DEFAULT_USER_SYNC_STALE_TIMEOUT_SECONDS,
        )
        return DEFAULT_USER_SYNC_STALE_TIMEOUT_SECONDS
    return max(timeout_seconds, 60)


def _supports_user_sync_row_locks() -> bool:
    return connection.features.has_select_for_update


def _supports_user_sync_skip_locked() -> bool:
    return connection.features.has_select_for_update_skip_locked


def _release_stale_user_sync_runs(source: UserSyncSource) -> int:
    if not _supports_user_sync_row_locks():
        now = timezone.now()
        stale_before = now - timedelta(seconds=_get_user_sync_stale_timeout_seconds())
        try:
            # SQLite 等无行锁数据库依靠条件 UPDATE 竞争写锁：活跃阶段先写
            # heartbeat 并持有事务写锁；回收若遇到锁竞争则 fail closed。
            return UserSyncRun.objects.filter(
                source=source,
                status=UserSyncRunStatusChoices.RUNNING,
                updated_at__lt=stale_before,
            ).update(
                status=UserSyncRunStatusChoices.FAILED,
                summary="User sync timed out and was released automatically",
                finished_at=now,
                updated_at=now,
            )
        except OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                logger.info(
                    "Skipped stale user sync release because the database is busy: source_id=%s",
                    source.id,
                )
                return 0
            raise

    with transaction.atomic():
        select_for_update_kwargs = {}
        if _supports_user_sync_skip_locked():
            select_for_update_kwargs["skip_locked"] = True
        locked_source = (
            UserSyncSource.objects.select_for_update(**select_for_update_kwargs)
            .filter(pk=source.pk)
            .first()
        )
        # 活跃落库阶段持有 source 行锁。支持 SKIP LOCKED 的数据库立即跳过，
        # 其余数据库等待阶段提交后再用最新 heartbeat 判断，均不会误回收。
        if locked_source is None:
            return 0
        now = timezone.now()
        stale_before = now - timedelta(seconds=_get_user_sync_stale_timeout_seconds())
        stale_run_ids = list(
            UserSyncRun.objects.select_for_update()
            .filter(
                source=source,
                status=UserSyncRunStatusChoices.RUNNING,
                updated_at__lt=stale_before,
            )
            .values_list("id", flat=True)
        )
        if not stale_run_ids:
            return 0
        return UserSyncRun.objects.filter(
            id__in=stale_run_ids,
            status=UserSyncRunStatusChoices.RUNNING,
            updated_at__lt=stale_before,
        ).update(
            status=UserSyncRunStatusChoices.FAILED,
            summary="User sync timed out and was released automatically",
            finished_at=now,
            updated_at=now,
        )


class UserSyncRunExpired(RuntimeError):
    pass


def _lock_user_sync_source(source_id: int) -> UserSyncSource:
    if not _supports_user_sync_row_locks():
        return UserSyncSource.objects.get(pk=source_id)
    return UserSyncSource.objects.select_for_update().get(pk=source_id)


def _lock_running_user_sync_run(run_id: int) -> UserSyncRun:
    if not _supports_user_sync_row_locks():
        # 单条条件 UPDATE 同时完成状态 fencing 与写锁获取。若回收先提交，
        # status 条件使旧 worker 无法继续；若本事务先写，则回收只能等待/失败。
        updated_count = UserSyncRun.objects.filter(
            pk=run_id,
            status=UserSyncRunStatusChoices.RUNNING,
        ).update(updated_at=timezone.now())
        if not updated_count:
            raise UserSyncRunExpired("User sync run expired before applying provider result")
        return UserSyncRun.objects.get(pk=run_id)

    run = UserSyncRun.objects.select_for_update().get(pk=run_id)
    if run.status != UserSyncRunStatusChoices.RUNNING:
        raise UserSyncRunExpired("User sync run expired before applying provider result")
    return run


def _touch_running_user_sync_run(run_id: int) -> UserSyncRun:
    run = _lock_running_user_sync_run(run_id)
    run.updated_at = timezone.now()
    run.save(update_fields=["updated_at"])
    return run


def _get_user_sync_heartbeat_interval_seconds() -> float:
    timeout_seconds = _get_user_sync_stale_timeout_seconds()
    return max(min(timeout_seconds / 3, MAX_USER_SYNC_HEARTBEAT_INTERVAL_SECONDS), 1)


def _heartbeat_user_sync_run(run_id: int, stop_event: Event, interval_seconds: float) -> None:
    """Provider 阻塞调用期间用独立数据库连接续租；进程退出时心跳自然停止。"""
    close_old_connections()
    try:
        while not stop_event.wait(interval_seconds):
            try:
                with transaction.atomic():
                    _touch_running_user_sync_run(run_id)
            except UserSyncRunExpired:
                return
            except Exception as error:
                logger.warning(
                    "Failed to refresh user sync heartbeat: run_id=%s, error=%r",
                    run_id,
                    error,
                )
    finally:
        close_old_connections()


def _start_user_sync_run_heartbeat(run_id: int) -> tuple[Event, Thread]:
    stop_event = Event()
    thread = Thread(
        target=_heartbeat_user_sync_run,
        args=(run_id, stop_event, _get_user_sync_heartbeat_interval_seconds()),
        name=f"user-sync-heartbeat-{run_id}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _stop_user_sync_run_heartbeat(stop_event: Event, thread: Thread) -> None:
    stop_event.set()
    thread.join(timeout=5)
    if thread.is_alive():
        logger.warning("User sync heartbeat thread did not stop promptly: thread=%s", thread.name)


# 同步进度阶段 key(在 payload.phase_progress 下作为子键使用)
PHASE_FETCH_DIRECTORY = "fetch_directory"
PHASE_SYNC_GROUPS = "sync_groups"
PHASE_SYNC_USERS = "sync_users"
PHASE_RECONCILE = "reconcile"
PHASE_FINALIZE = "finalize"
ALL_BASE_PHASES = (PHASE_FETCH_DIRECTORY, PHASE_SYNC_GROUPS, PHASE_SYNC_USERS, PHASE_RECONCILE)

GROUP_NAME_CONFLICT_CODE = "group_name_conflict"


class UserSyncGroupNameConflict(ValueError):
    """组织名称与现有记录冲突；名称可安全展示给管理员。"""

    error_code = GROUP_NAME_CONFLICT_CODE

    def __init__(self, name: str):
        self.conflict_name = name
        super().__init__(f"Group name '{name}' conflicts with an existing group")


def _ensure_group_name_available(*, parent_id: int, name: str, exclude_id: int | None = None) -> None:
    query = Group.objects.filter(parent_id=parent_id, name=name)
    if exclude_id is not None:
        query = query.exclude(id=exclude_id)
    if query.exists():
        raise UserSyncGroupNameConflict(name)


# 终态保留字段:失败/成功保存时,这些字段从最新 run.payload 继承,不被新构造的 payload 覆盖
INHERITED_PAYLOAD_FIELDS = (
    "password_vault",
    "email_status",
    "email_dispatch",
    "email_enqueue_status",
    "email_enqueue_error_code",
    "phase_progress",
    "phase_error",
    "counters",
    "password_init_mode",
)


def _get_batch_size(total: int) -> int:
    """用户批次大小:小规模细化(10 用户→batch=1),大规模收敛(2000 用户→batch=50)。

    公式: min(50, max(1, total // 20))
    """
    if total <= 0:
        return 1
    return min(50, max(1, total // 20))


def _to_safe_error_code(error: Exception) -> str:
    """将异常归类为语言无关错误码，原始信息只写服务端日志。"""
    declared_code = getattr(error, "error_code", None)
    if isinstance(declared_code, str) and declared_code:
        return declared_code
    type_name = type(error).__name__
    if "IntegrityError" in type_name:
        return "data_conflict"
    if "OperationalError" in type_name or "DatabaseError" in type_name:
        return "database_unavailable"
    if "Timeout" in type_name:
        return "request_timeout"
    if "ConnectionError" in type_name:
        return "external_service_unavailable"
    if "ValueError" in type_name:
        return "invalid_sync_data"
    return "sync_failed"


def _mutate_run_payload(run_id: int, mutate) -> None:
    """所有 run.payload 写入的唯一入口。

    在独立短 transaction.atomic() 内用 ORM select_for_update() 锁定 run,
    在 Python 端读取最新 payload,执行 mutate 回调后保存,释放锁。
    任何 phase_progress / phase_error / password_vault / email_status / 终态写入
    都必须通过该入口或同事务已锁定的 run 实例进行,不得直接使用外层旧实例覆盖。
    """
    with transaction.atomic():
        run = _lock_running_user_sync_run(run_id)
        next_payload = dict(run.payload or {})
        mutate(next_payload)
        run.payload = next_payload
        run.save(update_fields=["payload", "updated_at"])


def _write_phase_progress(
    run_id: int,
    phase: str,
    current: int,
    total: int,
    status: str,
    counters: dict | None = None,
    skip_reason: str | None = None,
) -> None:
    """更新单个阶段进度。counters 入参为 None 时跳过 counters 写入。

    counters 写入到 phase_progress[phase]["counters"](per-phase 归属),
    不写到 payload.counters 顶层(避免对账/同步字段在不同阶段展示串台)。
    """
    def mutate(next_payload: dict) -> None:
        phase_progress = dict(next_payload.get("phase_progress") or {})
        phase_entry = {"current": current, "total": total, "status": status}
        if status in ("finish", "skipped"):
            phase_entry["completed_at"] = timezone.now().isoformat()
        if counters is not None:
            phase_entry["counters"] = dict(counters)
        if skip_reason:
            phase_entry["skip_reason"] = skip_reason
        phase_progress[phase] = phase_entry
        next_payload["phase_progress"] = phase_progress
    _mutate_run_payload(run_id, mutate)


def _write_phase_error(
    run_id: int,
    phase: str,
    current: int,
    total: int,
    error: Exception,
    error_code: str | None = None,
) -> None:
    """写入阶段失败标记与语言无关错误码；原始异常只写服务端日志。"""
    resolved_code = error_code or _to_safe_error_code(error)
    error_params = _safe_error_params(error)

    def mutate(next_payload: dict) -> None:
        phase_progress = dict(next_payload.get("phase_progress") or {})
        failed_at = timezone.now().isoformat()
        phase_progress[phase] = {
            "current": current,
            "total": total,
            "status": "error",
            "completed_at": failed_at,
        }
        next_payload["phase_progress"] = phase_progress
        phase_error = {
            "phase": phase,
            "current": current,
            "total": total,
            "error_code": resolved_code,
            "failed_at": failed_at,
        }
        if error_params:
            phase_error["error_params"] = error_params
        next_payload["phase_error"] = phase_error
    _mutate_run_payload(run_id, mutate)


def _safe_error_params(error: Exception) -> dict:
    """只持久化可展示的结构化字段，不写入异常原文。"""
    name = getattr(error, "conflict_name", None)
    if not isinstance(name, str):
        return {}
    cleaned = name.strip()[:100]
    if not cleaned:
        return {}
    return {"name": cleaned}


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

    adapter_cls = None
    if provider_key:
        try:
            adapter_cls = RuntimeApplicationService().get_adapter_class(provider_key, "user_sync")
        except ValueError:
            adapter_cls = None
    if adapter_cls is not None:
        return adapter_cls.resolve_root_scope_value(
            business_config, field=root_scope_field, default=default
        )

    if root_scope_field in business_config:
        return business_config.get(root_scope_field, default)
    return business_config.get("root_department_id", default)


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
    if not get_integration_capability_availability(instance, "user_sync")["available"]:
        return {"result": False, "message": "User sync source is not ready"}

    released_count = _release_stale_user_sync_runs(source)
    if released_count:
        logger.warning(
            "Released %s stale user sync run(s) for source '%s'",
            released_count,
            source.name,
        )

    # Snapshot source 的 password_init.mode 到 run.payload,供前端决定阶段列表;
    # 即使 source 后续修改 mode,run 阶段显示不跳变。
    password_init_mode = ((source.platform_config or {}).get("password_init") or {}).get("mode") or None

    # 与 delete_user_sync_source 共用 UserSyncSource 行锁：创建 RUNNING 前锁定 source，
    # 避免「删源已过 RUNNING 检查」与「同步刚创建 RUNNING」交叉；source 已删则拒绝启动。
    try:
        with transaction.atomic():
            locked_source = _lock_user_sync_source(source_id)
            if UserSyncRun.objects.filter(
                source=locked_source, status=UserSyncRunStatusChoices.RUNNING
            ).exists():
                return {"result": False, "message": "User sync is already running"}
            run = UserSyncRun.objects.create(
                source=locked_source,
                trigger_mode=trigger_mode,
                status=UserSyncRunStatusChoices.RUNNING,
                summary="User sync started",
                payload={"password_init_mode": password_init_mode},
            )
    except UserSyncSource.DoesNotExist:
        return {"result": False, "message": "User sync source not found"}
    except IntegrityError:
        return {"result": False, "message": "User sync is already running"}

    runtime_service = RuntimeApplicationService()
    heartbeat_stop, heartbeat_thread = _start_user_sync_run_heartbeat(run.id)
    try:
        result = runtime_service.execute(
            provider_key=instance.provider_key,
            capability_key="user_sync",
            operation="sync_users",
            config=instance.get_runtime_config(),
            source=source,
        )
    finally:
        _stop_user_sync_run_heartbeat(heartbeat_stop, heartbeat_thread)
    input_summary = _extract_input_summary(result.payload)

    try:
        with transaction.atomic():
            run = _lock_running_user_sync_run(run.id)
            run.request_id = result.request_id or ""
            run.updated_at = timezone.now()
            run.save(update_fields=["request_id", "updated_at"])
    except UserSyncRunExpired as error:
        return {"result": False, "message": str(error)}

    # 阶段 1: 拉取目录
    if not result.success:
        # provider 调用失败,写 fetch_directory 阶段脱敏错误
        safe_error_code = "provider_fetch_failed"
        try:
            _write_phase_error(
                run.id,
                PHASE_FETCH_DIRECTORY,
                0,
                0,
                Exception(result.summary or "provider call failed"),
                error_code=safe_error_code,
            )
            _save_terminal_state(
                run.id,
                status=UserSyncRunStatusChoices.FAILED,
                summary=safe_error_code,
                payload_overrides={"request_id": result.request_id or ""},
            )
        except UserSyncRunExpired as error:
            return {"result": False, "message": str(error)}
        return {"result": False, "message": safe_error_code}

    # 拉取目录成功后立即写入统计，供运行中的进度详情展示；不能等到终态再写。
    _mutate_run_payload(run.id, lambda payload: payload.update({"input_summary": input_summary}))

    user_list = result.payload.get("user_list") or []
    group_list = result.payload.get("group_list") or []
    fetch_total = len(user_list) + len(group_list)

    # 阶段 2-4: 同步组织 / 同步用户(按 batch)/ 全量对账
    try:
        _write_phase_progress(run.id, PHASE_FETCH_DIRECTORY, current=fetch_total, total=fetch_total, status="finish")
        sync_summary = _apply_user_sync_payload(source, result.payload, current_run=run)
    except UserSyncRunExpired as error:
        return {"result": False, "message": str(error)}
    except Exception as error:
        logger.exception(f"User sync failed for source '{source.name}': request_id={result.request_id}, error={error!r}")
        safe_error_code = _to_safe_error_code(error)
        try:
            _save_terminal_state(
                run.id,
                status=UserSyncRunStatusChoices.FAILED,
                summary=safe_error_code,
                payload_overrides={
                    "request_id": result.request_id or "",
                    "external_request_id": str((result.payload or {}).get("external_request_id") or ""),
                },
            )
        except UserSyncRunExpired as expired_error:
            return {"result": False, "message": str(expired_error)}
        return {"result": False, "message": safe_error_code}

    # 终态保存
    payload_overrides = _build_run_payload(result, input_summary, sync_summary, current_run=run)
    if sync_summary["conflict_usernames"]:
        final_status = (
            UserSyncRunStatusChoices.FAILED
            if sync_summary["synced_user_count"] == 0
            else UserSyncRunStatusChoices.PARTIAL
        )
    else:
        final_status = UserSyncRunStatusChoices.SUCCESS
    try:
        _save_terminal_state(
            run.id,
            status=final_status,
            summary=sync_summary["summary"],
            payload_overrides=payload_overrides,
            instance_overrides={
                "synced_user_count": sync_summary["synced_user_count"],
                "synced_group_count": sync_summary["synced_group_count"],
                "disabled_user_count": sync_summary["disabled_user_count"],
            },
        )
    except UserSyncRunExpired as error:
        return {"result": False, "message": str(error)}
    return {"result": True, "message": sync_summary["summary"], "data": {"run_id": run.id}}


def _save_terminal_state(
    run_id: int,
    *,
    status: str,
    summary: str,
    payload_overrides: dict | None = None,
    instance_overrides: dict | None = None,
) -> None:
    """保存 run 终态(成功/失败)。在独立短事务中 select_for_update 锁 run,
    合并 payload 覆盖(不破坏 phase_progress / phase_error / password_vault 等),
    再保存终态字段。任何终态保存都必须经此入口,禁止直接操作外层旧 run 实例。
    """
    with transaction.atomic():
        run = _lock_running_user_sync_run(run_id)
        run.status = status
        run.summary = summary
        if payload_overrides:
            next_payload = dict(run.payload or {})
            for key, value in payload_overrides.items():
                next_payload[key] = value
            run.payload = next_payload
        if instance_overrides:
            for field, value in instance_overrides.items():
                setattr(run, field, value)
        run.finished_at = timezone.now()
        update_fields = ["status", "summary", "payload", "finished_at", "updated_at"]
        if instance_overrides:
            for field in instance_overrides.keys():
                if field not in update_fields:
                    update_fields.append(field)
        run.save(update_fields=update_fields)


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
    if not get_integration_capability_availability(instance, "user_sync")["available"]:
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

    2026-07-22 改:扩展继承集合,同步继承 phase_progress / phase_error /
    counters / password_init_mode,确保终态保存不抹掉进度和错误信息。
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
    # 继承 service 之前写入的字段(避免被同步结果覆盖)
    if current_run is not None:
        existing = current_run.payload or {}
        for key in INHERITED_PAYLOAD_FIELDS:
            if key in existing and key not in payload:
                payload[key] = existing[key]
    return payload


def _apply_user_sync_payload(source: UserSyncSource, payload: dict, current_run: "UserSyncRun | None" = None):
    """三段式应用同步载荷:同步组织 → 按 batch 同步用户 → 全量对账。

    每段独立小事务,事务 commit 后通过 _write_phase_progress 写进度,确保其他
    DB 连接能立即看到当前阶段。前端通过 GET /user_sync_source/runs/{id}/ 拉取。

    current_run=None 时(单测场景),内部不再写阶段进度,只返回 sync_summary。
    正常生产路径(execute_user_sync)必定传 current_run。
    """
    group_list = deepcopy(payload.get("group_list") or [])
    user_list = deepcopy(payload.get("user_list") or [])
    root_scope_value = str(get_user_sync_root_scope_value(source, "") or "")
    if not root_scope_value:
        raise ValueError("User sync root scope is required")

    has_run = current_run is not None
    password_init_mode_snapshot = (
        (current_run.payload or {}).get("password_init_mode") if has_run else None
    )

    def _record_progress(phase, current, total, status, counters=None):
        """写入阶段进度;仅在 current_run 存在时执行。"""
        if not has_run:
            return
        _write_phase_progress(current_run.id, phase, current=current, total=total, status=status, counters=counters)

    def _record_error(phase, current, total, error, error_code=None):
        if not has_run:
            return
        _write_phase_error(
            current_run.id,
            phase,
            current=current,
            total=total,
            error=error,
            error_code=error_code,
        )

    # 阶段 A: 同步组织 (单事务;不在此阶段删 stale 组织)
    group_counters = {
        "created_groups": 0,
        "updated_groups": 0,
        "unchanged_groups": 0,
        "skipped_invalid_groups": 0,
    }
    try:
        with transaction.atomic():
            if has_run:
                _lock_user_sync_source(source.id)
                _touch_running_user_sync_run(current_run.id)
            root_group = _get_or_create_root_group(source)
            group_id_mapping, active_group_ids = _sync_groups(
                source, group_list, root_group, root_scope_value, group_counters
            )
            if has_run:
                _touch_running_user_sync_run(current_run.id)
    except Exception as error:
        logger.exception("User sync group stage failed: source=%s, error=%r", source.name, error)
        _record_error(PHASE_SYNC_GROUPS, current=0, total=len(group_list), error=error)
        raise
    # 写 sync_groups 进度(扣 root)。抬头 total 含跳过无效,与分项加总对账
    synced_groups = max(len(group_id_mapping) - 1, 0)
    skipped_groups = group_counters["skipped_invalid_groups"]
    group_counters["unchanged_groups"] = max(
        synced_groups - group_counters["created_groups"] - group_counters["updated_groups"], 0
    )
    group_total = synced_groups + skipped_groups
    _record_progress(
        PHASE_SYNC_GROUPS,
        current=group_total, total=group_total, status="finish",
        counters=group_counters,
    )

    # 阶段 B: 同步用户 (按 batch,每个 batch 一个独立小事务)
    # per-phase counters 只写本阶段关心的字段,避免对账字段提前出现
    total = len(user_list)
    batch_size = _get_batch_size(total)
    sync_counters = {
        "new_users": 0,
        "updated_users": 0,
        "unchanged_users": 0,
        "skipped_invalid_users": 0,
        "conflict_users": 0,
    }
    all_synced_usernames: list[str] = []
    all_conflict_usernames: list[str] = []

    if total == 0:
        # 空成员目录也必须有可解释的完成状态
        _record_progress(
            PHASE_SYNC_USERS, current=0, total=0, status="finish",
            counters=dict(sync_counters),
        )
    else:
        for batch_start in range(0, total, batch_size):
            batch = user_list[batch_start : batch_start + batch_size]
            try:
                with transaction.atomic():
                    # 锁定 run,供 batch 内的 password_init_service 复用同一实例
                    if has_run:
                        _lock_user_sync_source(source.id)
                        locked_run = _touch_running_user_sync_run(current_run.id)
                    else:
                        locked_run = None
                    batch_result = _process_user_batch(
                        source=source,
                        batch=batch,
                        group_id_mapping=group_id_mapping,
                        root_group_id=root_group.id,
                        root_department_id=root_scope_value,
                        locked_run=locked_run,
                    )
                    if has_run:
                        _touch_running_user_sync_run(current_run.id)
            except Exception as error:
                logger.exception(
                    f"User sync batch failed: source={source.name}, "
                    f"batch_start={batch_start}, error={error!r}"
                )
                _record_error(PHASE_SYNC_USERS, current=batch_start, total=total, error=error)
                raise

            all_synced_usernames.extend(batch_result["synced_usernames"])
            all_conflict_usernames.extend(batch_result["conflict_usernames"])
            sync_counters["new_users"] += batch_result["new_users"]
            sync_counters["updated_users"] += batch_result["updated_users"]
            sync_counters["unchanged_users"] += batch_result["unchanged_users"]
            sync_counters["skipped_invalid_users"] += batch_result["skipped_invalid_users"]
            sync_counters["conflict_users"] = len(all_conflict_usernames)

            is_last = (batch_start + batch_size) >= total
            _record_progress(
                PHASE_SYNC_USERS,
                current=min(batch_start + batch_size, total),
                total=total,
                status="finish" if is_last else "process",
                counters=dict(sync_counters),
            )

    # 阶段 C: 全量对账 (单事务) - 依据完整同步名单删除 stale 用户和组织
    try:
        with transaction.atomic():
            if has_run:
                _lock_user_sync_source(source.id)
                _touch_running_user_sync_run(current_run.id)
            reconcile_result = _reconcile_synced_directory(
                source=source,
                synced_usernames=all_synced_usernames,
                active_group_ids=active_group_ids,
                root_group_id=root_group.id,
            )
            if has_run:
                _touch_running_user_sync_run(current_run.id)
    except Exception as error:
        logger.exception("User sync reconcile stage failed: source=%s, error=%r", source.name, error)
        _record_error(PHASE_RECONCILE, current=0, total=1, error=error)
        raise
    # 对账阶段专属 counters,只含本阶段关心的字段
    _record_progress(
        PHASE_RECONCILE, current=1, total=1, status="finish",
        counters={
            "deleted_users": reconcile_result["deleted_user_count"],
            "deleted_group_count": reconcile_result["deleted_group_count"],
        },
    )

    # 阶段 D: finalize (仅 password_init_mode ∈ {uniform, random})
    # 邮件任务投递由 _process_user_batch 内部 password_init_service._enqueue_email 触发。
    # 只有代理实际接受任务后才标记完成；邮件送达仍由异步任务的 email_status 表示。
    if password_init_mode_snapshot in ("uniform", "random"):
        latest_payload = UserSyncRun.objects.filter(pk=current_run.id).values_list("payload", flat=True).first() if has_run else {}
        enqueue_status = (latest_payload or {}).get("email_enqueue_status")
        if enqueue_status == "enqueued":
            _record_progress(PHASE_FINALIZE, current=1, total=1, status="finish")
        elif enqueue_status == "failed":
            error_code = (latest_payload or {}).get("email_enqueue_error_code") or "email_enqueue_failed"
            error = RuntimeError(error_code)
            _record_error(PHASE_FINALIZE, current=0, total=1, error=error, error_code=error_code)
            raise error
        else:
            if has_run:
                _write_phase_progress(
                    current_run.id,
                    PHASE_FINALIZE,
                    current=0,
                    total=0,
                    status="skipped",
                    skip_reason="no_new_users",
                )

    synced_group_count = max(len(active_group_ids) - 1, 0)
    if all_conflict_usernames:
        if not all_synced_usernames:
            summary = (
                f"User sync failed: all {len(all_conflict_usernames)} users conflicted, "
                f"{synced_group_count} groups"
            )
        else:
            summary = (
                f"User sync partially completed: {len(all_synced_usernames)} users, "
                f"{synced_group_count} groups, {len(all_conflict_usernames)} conflicts"
            )
    else:
        summary = f"User sync completed: {len(all_synced_usernames)} users, {synced_group_count} groups"
    return {
        "summary": summary,
        "synced_user_count": len(all_synced_usernames),
        "synced_group_count": synced_group_count,
        # 保留现有数据库字段名，兼容既有运行记录 API；值语义为本轮删除的用户数。
        "disabled_user_count": reconcile_result["deleted_user_count"],
        "conflict_usernames": sorted(set(all_conflict_usernames)),
    }


def _process_user_batch(
    *,
    source: UserSyncSource,
    batch: list[dict],
    group_id_mapping: dict,
    root_group_id: int,
    root_department_id: str,
    locked_run: "UserSyncRun",
) -> dict:
    """处理单批用户:标准化、新建/更新、密码初始化(写入 locked_run.payload)。

    不执行 stale 用户禁用 - 那是全量对账阶段的工作。
    返回 {synced_usernames, new_users, updated_users, unchanged_users,
    skipped_invalid_users, conflict_usernames}。
    """
    field_mapping = {**DEFAULT_FIELD_MAPPING, **(source.field_mapping or {})}
    normalized_users = _normalize_user_batch(
        batch, field_mapping, group_id_mapping, root_group_id, root_department_id
    )
    # normalize 只会因缺 username 丢弃条目;显式计数,避免数据质量问题不可见
    skipped_invalid_users = len(batch) - len(normalized_users)

    usernames = [item["username"] for item in normalized_users]
    legacy_domain = "domain.com"

    password_init_cfg = (source.platform_config or {}).get("password_init") or {}
    password_init_mode = password_init_cfg.get("mode")

    # 第一遍:创建新用户 + 校验既有用户归属
    existing_user_map = {
        user.username: user
        for user in User.objects.select_related("sync_source").filter(
            username__in=usernames, domain=legacy_domain
        )
    }
    new_users = []
    conflict_usernames = []

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
                # race condition:同名 user 在本轮 sync 中被另一 source 创建
                conflict_usernames.append(item["username"])
            continue

        try:
            _ensure_user_sync_source_match(user, source, item["username"])
        except ValueError:
            conflict_usernames.append(item["username"])

    # 密码初始化 - 在本批事务内调用,使用 locked_run 复用行锁
    if new_users and password_init_mode:
        from apps.system_mgmt.services.password_init_service import PASSWORD_INIT_SENTINEL_MARK, init_password_for_user

        for new_user in new_users:
            try:
                init_result = init_password_for_user(
                    new_user, password_init_mode, password_init_cfg, locked_run
                )
                if init_result.get("status") != "ok":
                    new_user.password = PASSWORD_INIT_SENTINEL_MARK
                    new_user.temporary_pwd = False
                    new_user.save(update_fields=["password", "temporary_pwd"])
                    logger.warning(
                        f"init_password_for_user 被拒绝 username={new_user.username}: "
                        f"{init_result.get('reason')}"
                    )
            except Exception as init_error:
                new_user.password = PASSWORD_INIT_SENTINEL_MARK
                new_user.temporary_pwd = False
                new_user.save(update_fields=["password", "temporary_pwd"])
                logger.warning(
                    f"init_password_for_user 失败 username={new_user.username}: {init_error!r}"
                )

    # 第二遍:更新已有用户
    synced_users = User.objects.select_related("sync_source").filter(
        username__in=usernames, domain=legacy_domain
    )
    synced_user_map = {user.username: user for user in synced_users}
    synced_usernames: list[str] = []
    update_users = []

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
        User.objects.bulk_update(
            update_users,
            ["display_name", "email", "phone", "group_list", "disabled", "sync_source"],
            batch_size=100,
        )

    # 权限缓存清理(只针对本批涉及的 username)
    affected_usernames = {u.username for u in new_users + update_users}
    if affected_usernames:
        clear_users_permission_cache(
            [{"username": username, "domain": legacy_domain} for username in affected_usernames]
        )

    # 同步成功但既非新建也非更新的用户 = 无变化(核验过、无需改动)
    unchanged_users = max(len(synced_usernames) - len(new_users) - len(update_users), 0)

    return {
        "synced_usernames": synced_usernames,
        "new_users": len(new_users),
        "updated_users": len(update_users),
        "unchanged_users": unchanged_users,
        "skipped_invalid_users": skipped_invalid_users,
        "conflict_usernames": sorted(set(conflict_usernames)),
    }


def _normalize_user_batch(
    user_list: list[dict],
    field_mapping: dict,
    group_id_mapping: dict,
    root_group_id: int,
    root_department_id: str,
) -> list[dict]:
    """把 provider 原始 user_list 标准化为本地字段。"""
    normalized = []
    for raw_user in user_list:
        username = str(
            _mapped_value(raw_user, field_mapping, "username")
            or raw_user.get("user_id")
            or raw_user.get("open_id")
            or ""
        ).strip()
        if not username:
            continue
        username = _truncate_to_field(User, "username", username)
        departments = [
            str(item)
            for item in (raw_user.get("department_ids") or raw_user.get("departments") or [])
        ]
        local_group_ids = []
        for department_id in departments:
            local_group_id = group_id_mapping.get(department_id)
            if local_group_id:
                local_group_ids.append(local_group_id)
            elif department_id == root_department_id:
                local_group_ids.append(root_group_id)
        if not local_group_ids:
            local_group_ids = [root_group_id]
        normalized.append(
            {
                "username": username,
                "display_name": _truncate_to_field(
                    User, "display_name",
                    str(_mapped_value(raw_user, field_mapping, "display_name") or username),
                ),
                "email": _truncate_to_field(
                    User, "email",
                    str(_mapped_value(raw_user, field_mapping, "email") or ""),
                ),
                "phone": _truncate_to_field(
                    User, "phone",
                    str(_mapped_value(raw_user, field_mapping, "phone") or ""),
                ),
                "group_list": sorted(set(local_group_ids)),
            }
        )
    return normalized


def _reconcile_synced_directory(
    *,
    source: UserSyncSource,
    synced_usernames: list[str],
    active_group_ids: list[int],
    root_group_id: int,
) -> dict:
    """全量对账:依据完整同步名单删除 stale 用户，并将 stale 组织归档。

    只在所有用户 batch 成功后调用,避免单批失败时错误删除其他批次的用户。
    返回 {deleted_user_count, deleted_group_count}；deleted_group_count 表示归档数。
    归档保留用户 group_list，不再清除对 stale 组织的引用。
    锁顺序：UserSyncSource → Group → User。
    """
    legacy_domain = "domain.com"
    affected_cache_users: list[dict] = []
    deleted_user_count = 0
    deleted_group_count = 0

    with transaction.atomic():
        source_id = getattr(source, "id", None)
        if _supports_user_sync_row_locks() and source_id is not None:
            UserSyncSource.objects.select_for_update().filter(id=source_id).first()

        # 先归档 stale 组织（Source → Group），保留 group_list。
        stale_group_ids = list(
            Group.objects.filter(sync_source=source, is_delete=False)
            .exclude(id__in=active_group_ids)
            .exclude(id=root_group_id)
            .values_list("id", flat=True)
        )
        to_archive: set[int] = set()
        active_id_set = set(active_group_ids)
        for stale_id in stale_group_ids:
            for descendant_id in GroupArchiveService.collect_subtree_ids(stale_id):
                if descendant_id != root_group_id and descendant_id not in active_id_set:
                    to_archive.add(descendant_id)

        stale_users = User.objects.filter(
            sync_source=source, domain=legacy_domain
        ).exclude(username__in=synced_usernames)
        stale_user_ids = list(stale_users.values_list("id", flat=True))

        overlapping_users = []
        if to_archive or stale_user_ids:
            _locked_by_id, overlapping_users = GroupArchiveService.lock_groups_and_overlapping_users(
                to_archive, extra_user_ids=set(stale_user_ids)
            )

        if to_archive:
            archived_ids = GroupArchiveService.archive_group_ids_keeping_membership(list(to_archive))
            deleted_group_count = len(archived_ids)
            affected_cache_users.extend(
                {"id": user.id, "username": user.username, "domain": user.domain}
                for user in overlapping_users
            )

        if stale_user_ids:
            stale_usernames = list(
                User.objects.filter(id__in=stale_user_ids).values("id", "username", "domain")
            )
            User.objects.filter(id__in=stale_user_ids).delete()
            deleted_user_count = len(stale_usernames)
            seen = {(row["username"], row["domain"]) for row in affected_cache_users}
            for row in stale_usernames:
                key = (row["username"], row["domain"])
                if key not in seen:
                    affected_cache_users.append(row)
                    seen.add(key)

        cache_users = list(affected_cache_users)

        def _clear_cache():
            if cache_users:
                clear_users_permission_cache(cache_users)

        transaction.on_commit(_clear_cache)

    return {
        "deleted_user_count": deleted_user_count,
        "deleted_group_count": deleted_group_count,
    }


def _get_or_create_root_group(source: UserSyncSource):
    root_scope_value = str(get_user_sync_root_scope_value(source, "") or "")
    if not root_scope_value:
        raise ValueError("User sync root scope is required")
    scoped_external_id = _scoped_external_id(source.id, root_scope_value)

    existing = (
        Group.objects.filter(sync_source=source, external_id=scoped_external_id, parent_id=0)
        .order_by("id")
        .first()
    )
    if existing is None:
        # 同 source 已有根（历史 external_id / 范围变更）：复用并回写 scoped id，禁止另建假根
        existing = (
            Group.objects.filter(sync_source=source, parent_id=0).order_by("id").first()
        )

    if existing is not None:
        update_fields = []
        if existing.is_delete:
            existing.is_delete = False
            update_fields.append("is_delete")
        if existing.external_id != scoped_external_id:
            existing.external_id = scoped_external_id
            update_fields.append("external_id")
        if existing.name != source.root_group_name:
            _ensure_group_name_available(
                parent_id=0,
                name=source.root_group_name,
                exclude_id=existing.id,
            )
            existing.name = source.root_group_name
            update_fields.append("name")
        if update_fields:
            existing.save(update_fields=update_fields)
        return existing

    _ensure_group_name_available(parent_id=0, name=source.root_group_name)

    return Group.objects.create(
        parent_id=0,
        name=source.root_group_name,
        description=f"user_sync_source_{source.id}",
        sync_source=source,
        external_id=scoped_external_id,
    )


def _sync_groups(
    source: UserSyncSource,
    group_list: list[dict],
    root_group: Group,
    root_department_id: str,
    counters: dict | None = None,
):
    if counters is not None:
        counters.setdefault("created_groups", 0)
        counters.setdefault("updated_groups", 0)
    child_map: dict[str, list[dict]] = {}
    for item in group_list:
        item_id = str(item.get("id", ""))
        if not item_id:
            if counters is not None:
                counters["skipped_invalid_groups"] = counters.get("skipped_invalid_groups", 0) + 1
            continue
        parent_id = str(item.get("parent_id") or "")
        child_map.setdefault(parent_id, []).append(item)

    group_id_mapping = {root_department_id: root_group.id}
    active_group_ids = {root_group.id}

    existing_by_external_id: dict[str, Group] = {}
    for group in Group.objects.filter(sync_source=source).order_by("id"):
        if group.external_id and group.external_id not in existing_by_external_id:
            existing_by_external_id[group.external_id] = group
    occupied_names: dict[int, dict[str, int]] = {}

    def names_under(parent_id: int) -> dict[str, int]:
        cached = occupied_names.get(parent_id)
        if cached is None:
            cached = dict(Group.objects.filter(parent_id=parent_id).values_list("name", "id"))
            occupied_names[parent_id] = cached
        return cached

    def ensure_available(parent_id: int, name: str, exclude_id: int | None) -> None:
        occupant = names_under(parent_id).get(name)
        if occupant is not None and occupant != exclude_id:
            raise UserSyncGroupNameConflict(name)

    def remember(group: Group, previous_parent_id: int | None = None, previous_name: str | None = None) -> None:
        if group.external_id:
            existing_by_external_id[group.external_id] = group
        if previous_parent_id is not None and previous_name is not None:
            previous_map = occupied_names.get(previous_parent_id)
            if previous_map and previous_map.get(previous_name) == group.id:
                del previous_map[previous_name]
        names_under(group.parent_id)[group.name] = group.id

    def walk(parent_external_id: str, parent_group: Group):
        current_items = child_map.get(parent_external_id, [])

        for item in current_items:
            external_id = str(item["id"])
            scoped_external_id = _scoped_external_id(source.id, external_id)
            group_name = _truncate_to_field(Group, "name", str(item.get("name", external_id)))
            group = existing_by_external_id.get(scoped_external_id)
            if group is None or group.parent_id != parent_group.id or group.name != group_name:
                ensure_available(
                    parent_group.id,
                    group_name,
                    None if group is None else group.id,
                )
            if group is None:
                group = Group.objects.create(
                    name=group_name,
                    parent_id=parent_group.id,
                    external_id=scoped_external_id,
                    description=f"user_sync_source_{source.id}",
                    sync_source=source,
                )
                remember(group)
                if counters is not None:
                    counters["created_groups"] += 1
            else:
                previous_parent_id = group.parent_id
                previous_name = group.name
                update_fields = []
                if group.is_delete:
                    group.is_delete = False
                    update_fields.append("is_delete")
                if group.parent_id != parent_group.id:
                    group.parent_id = parent_group.id
                    update_fields.append("parent_id")
                if group.name != group_name:
                    group.name = group_name
                    update_fields.append("name")
                if group.sync_source_id != source.id:
                    group.sync_source = source
                    update_fields.append("sync_source")
                if update_fields:
                    group.save(update_fields=update_fields)
                    if counters is not None:
                        counters["updated_groups"] += 1
                remember(group, previous_parent_id, previous_name)
            group_id_mapping[external_id] = group.id
            active_group_ids.add(group.id)
            walk(external_id, group)

    walk(root_department_id, root_group)
    return group_id_mapping, list(active_group_ids)


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
    return (
        Group.objects.filter(parent_id=0, sync_source=source)
        .order_by("id")
        .first()
    )


def _collect_group_subtree_ids(root_group_id: int):
    return set(GroupArchiveService.collect_subtree_ids(root_group_id))


def delete_user_sync_source(source: UserSyncSource):
    """删除同步源：先查 RUNNING，可删后再停周期任务 → 归档根树 → 删同步用户 → 删 source。"""
    with transaction.atomic():
        locked_source = (
            UserSyncSource.objects.select_for_update().filter(id=source.id).first()
            if _supports_user_sync_row_locks()
            else UserSyncSource.objects.filter(id=source.id).first()
        )
        if locked_source is None:
            return {"result": False, "message": "User sync source not found"}

        if UserSyncRun.objects.filter(
            source=locked_source, status=UserSyncRunStatusChoices.RUNNING
        ).exists():
            return {"result": False, "message": "User sync is already running"}

        task_name = locked_source.periodic_task_name()
        UserSyncSource.delete_periodic_task(task_name)

        root_group = _get_user_sync_root_group(locked_source)
        subtree_ids = _collect_group_subtree_ids(root_group.id) if root_group else set()

        users_to_delete = set(
            User.objects.filter(sync_source=locked_source).values_list("id", flat=True)
        )
        overlapping_users = []
        if subtree_ids or users_to_delete:
            _locked_by_id, overlapping_users = GroupArchiveService.lock_groups_and_overlapping_users(
                subtree_ids, extra_user_ids=users_to_delete
            )

        cache_users = [
            {"id": user.id, "username": user.username, "domain": user.domain}
            for user in overlapping_users
        ]
        seen = {(row["username"], row["domain"]) for row in cache_users}
        if users_to_delete:
            for row in User.objects.filter(id__in=users_to_delete).values("id", "username", "domain"):
                key = (row["username"], row["domain"])
                if key not in seen:
                    cache_users.append(row)
                    seen.add(key)

        if subtree_ids:
            GroupArchiveService.archive_group_ids_keeping_membership(list(subtree_ids))

        if users_to_delete:
            User.objects.filter(id__in=users_to_delete).delete()

        archived_group_count = len(subtree_ids)
        deleted_user_count = len(users_to_delete)
        locked_source.delete()

        def _clear_cache():
            if cache_users:
                clear_users_permission_cache(cache_users)

        transaction.on_commit(_clear_cache)

    return {
        "result": True,
        "message": "User sync source deleted",
        "data": {
            "deleted_group_count": archived_group_count,
            "deleted_user_count": deleted_user_count,
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
