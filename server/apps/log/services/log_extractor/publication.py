import hashlib
import re
import time
import traceback
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.core.logger import log_logger as logger
from apps.log.models import LogExtractor, SystemVectorConfigState
from apps.log.services.log_extractor.compiler import compile_system_vector_config

GLOBAL_SCOPE = "global"
_SENSITIVE_TEXT = re.compile(r"(?i)(bearer\s+|token[=: ]+|secret[=: ]+|password[=: ]+)([^\s,;]+)")


@dataclass(frozen=True)
class PublishedSnapshot:
    content: str
    checksum: str
    generation: int


def _sanitize(value: str) -> str:
    return _SENSITIVE_TEXT.sub(r"\1***", value)[:4000]


def _error_summary(prefix: str, exc: Exception) -> str:
    return f"{prefix}（{type(exc).__name__}）"


def _log_exception(message: str, exc: Exception, **context) -> None:
    stack = _sanitize("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    logger.error(message, extra={**context, "exception_type": type(exc).__name__, "exception_stack": stack})


def _publication_task():
    from apps.log.tasks.extractor import publish_system_vector_config

    return publish_system_vector_config


def _get_locked_state() -> SystemVectorConfigState:
    state, _ = SystemVectorConfigState.objects.get_or_create(scope=GLOBAL_SCOPE)
    return SystemVectorConfigState.objects.select_for_update().get(scope=state.scope)


def _record_failure(generation: int, summary: str) -> None:
    with transaction.atomic():
        state = _get_locked_state()
        if state.desired_generation != generation or state.published_generation >= generation:
            return
        state.status = SystemVectorConfigState.Status.FAILED
        state.last_error = summary[:500]
        state.save(update_fields=("status", "last_error", "updated_at"))


def _enqueue(generation: int) -> None:
    try:
        _publication_task().delay(generation)
    except Exception as exc:
        _record_failure(generation, _error_summary("任务投递失败", exc))
        _log_exception("中心 Vector 配置发布任务投递失败", exc, generation=generation)


def mark_dirty() -> int:
    with transaction.atomic():
        state = _get_locked_state()
        state.desired_generation += 1
        state.status = SystemVectorConfigState.Status.PENDING
        state.last_error = ""
        generation = state.desired_generation
        state.save(update_fields=("desired_generation", "status", "last_error", "updated_at"))
        transaction.on_commit(lambda: _enqueue(generation))
        return generation


def publish_generation(generation: int) -> str:
    started_at = time.monotonic()
    with transaction.atomic():
        state = _get_locked_state()
        if state.published_generation >= generation:
            return "already_published"
        if state.desired_generation != generation:
            return "stale"
        state.status = SystemVectorConfigState.Status.GENERATING
        state.last_error = ""
        state.save(update_fields=("status", "last_error", "updated_at"))

    rule_count = 0
    try:
        records = list(LogExtractor.objects.filter(collect_instance__isnull=False).order_by("collect_instance_id", "sort_order", "id"))
        rule_count = len(records)
        content = compile_system_vector_config(records)
        checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
    except Exception as exc:
        _record_failure(generation, _error_summary("配置生成失败", exc))
        _log_exception(
            "中心 Vector 配置生成失败",
            exc,
            generation=generation,
            rule_count=rule_count,
            duration_seconds=round(time.monotonic() - started_at, 3),
        )
        return "failed"

    try:
        with transaction.atomic():
            state = _get_locked_state()
            if state.published_generation >= generation:
                return "already_published"
            if state.desired_generation != generation:
                return "stale"
            state.published_content = content
            state.published_checksum = checksum
            state.published_generation = generation
            state.status = SystemVectorConfigState.Status.PUBLISHED
            state.last_error = ""
            state.last_published_at = timezone.now()
            state.save(
                update_fields=(
                    "published_content",
                    "published_checksum",
                    "published_generation",
                    "status",
                    "last_error",
                    "last_published_at",
                    "updated_at",
                )
            )
    except Exception as exc:
        _record_failure(generation, _error_summary("快照保存失败", exc))
        _log_exception(
            "中心 Vector 配置快照保存失败",
            exc,
            generation=generation,
            rule_count=rule_count,
            duration_seconds=round(time.monotonic() - started_at, 3),
        )
        return "failed"
    logger.info(
        "中心 Vector 配置已发布",
        extra={
            "generation": generation,
            "published_generation": generation,
            "checksum": checksum,
            "rule_count": rule_count,
            "duration_seconds": round(time.monotonic() - started_at, 3),
            "status": SystemVectorConfigState.Status.PUBLISHED,
        },
    )
    return "published"


def get_published_snapshot() -> PublishedSnapshot | None:
    state = SystemVectorConfigState.objects.filter(scope=GLOBAL_SCOPE).only("published_content", "published_checksum", "published_generation").first()
    if not state or not state.published_content:
        return None
    return PublishedSnapshot(state.published_content, state.published_checksum, state.published_generation)


def get_publication_status() -> dict:
    state = SystemVectorConfigState.objects.filter(scope=GLOBAL_SCOPE).first()
    if not state:
        return {
            "desired_generation": 0,
            "published_generation": 0,
            "status": SystemVectorConfigState.Status.PENDING,
            "last_error": "",
            "last_published_at": None,
        }
    return {
        "desired_generation": state.desired_generation,
        "published_generation": state.published_generation,
        "status": state.status,
        "last_error": state.last_error,
        "last_published_at": state.last_published_at,
    }


def retry_publication() -> int | None:
    with transaction.atomic():
        state = _get_locked_state()
        if state.status == SystemVectorConfigState.Status.PUBLISHED and state.published_generation == state.desired_generation:
            return None
        generation = state.desired_generation
        state.status = SystemVectorConfigState.Status.PENDING
        state.last_error = ""
        state.save(update_fields=("status", "last_error", "updated_at"))
        transaction.on_commit(lambda: _enqueue(generation))
        return generation


def ensure_initial_snapshot() -> PublishedSnapshot:
    state = SystemVectorConfigState.objects.filter(scope=GLOBAL_SCOPE).first()
    if state and state.published_content:
        return PublishedSnapshot(state.published_content, state.published_checksum, state.published_generation)
    with transaction.atomic():
        state = _get_locked_state()
        if not state.published_content and state.desired_generation == 0:
            state.desired_generation = 1
            state.status = SystemVectorConfigState.Status.PENDING
            state.save(update_fields=("desired_generation", "status", "updated_at"))
        generation = state.desired_generation
    result = publish_generation(generation)
    snapshot = get_published_snapshot()
    if not snapshot:
        raise RuntimeError(f"无法生成中心 Vector 初始快照：{result}")
    return snapshot
