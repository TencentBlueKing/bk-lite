from __future__ import annotations

from typing import Any

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from celery_singleton import Singleton
from django.core.cache import cache

from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info
from apps.core.utils.celery_utils import CeleryUtils

REBUILD_PERIODIC_TASK_NAME = "cmdb_ci_context_rebuild"
REBUILD_TASK = "apps.cmdb.tasks.ci_context.rebuild_ci_context_runtime"
REBUILD_CRONTAB = "*/5 * * * *"
REBUILD_CURSOR_KEY = "cmdb:ci-context-rebuild-cursor"
REBUILD_LOCK_KEY = "cmdb:ci-context-rebuild-lock"
REBUILD_LOCK_TTL = 10 * 60
REBUILD_CURSOR_TTL = 24 * 60 * 60
REBUILD_BUDGET = 50


class _CiContextPendingSingleton(Singleton):
    """周期排空 CI 上下文待重算名单。锁会过期，避免任务卡在队列里时后续调度被永久丢掉。"""

    lock_expiry = 30 * 60
    raise_on_duplicate = False


@shared_task(base=_CiContextPendingSingleton)
def reconcile_ci_context_pending_task() -> dict:
    from apps.cmdb.services.ci_context import drain_ci_context_pending

    return drain_ci_context_pending()


def ensure_ci_context_rebuild_periodic_task():
    """首次部署创建周期任务；已经禁用的表示全量重摊完成，不再重新打开。"""
    current = CeleryUtils.get_periodic_task(REBUILD_PERIODIC_TASK_NAME)
    if current is not None:
        return current
    return CeleryUtils.create_or_update_periodic_task(
        name=REBUILD_PERIODIC_TASK_NAME,
        crontab=REBUILD_CRONTAB,
        task=REBUILD_TASK,
        enabled=True,
    )


def _disable_rebuild_periodic_task() -> None:
    current = CeleryUtils.get_periodic_task(REBUILD_PERIODIC_TASK_NAME)
    if current is None or not current.enabled:
        return
    CeleryUtils.disable_periodic_task(REBUILD_PERIODIC_TASK_NAME)


@shared_task(name=REBUILD_TASK, soft_time_limit=240, time_limit=300)
def rebuild_ci_context_runtime() -> dict[str, Any]:
    """部署后异步全量重摊 ci_context。启动只入队，Worker 按页重算。"""
    task = ensure_ci_context_rebuild_periodic_task()
    if task is not None and not task.enabled and cache.get(REBUILD_CURSOR_KEY) is None:
        return {"status": "idle"}

    if not cache.add(REBUILD_LOCK_KEY, "1", timeout=REBUILD_LOCK_TTL):
        logger.info("event=ci_context_rebuild_locked")
        return {"status": "locked"}

    try:
        return _rebuild_under_lock()
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "event=ci_context_rebuild_soft_timeout failed_stage=rebuild error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return {"status": "retry", "reason": "soft_timeout"}
    except Exception as exc:
        logger.error(
            "event=ci_context_rebuild_failed failed_stage=rebuild error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return {"status": "retry", "reason": "rebuild_failed"}
    finally:
        cache.delete(REBUILD_LOCK_KEY)


def _cursor_state() -> dict[str, int]:
    cursor = cache.get(REBUILD_CURSOR_KEY) or {}
    if not isinstance(cursor, dict):
        cursor = {}
    return {
        "skip": int(cursor.get("skip") or 0),
        "ok": int(cursor.get("ok") or 0),
        "fail": int(cursor.get("fail") or 0),
    }


def _rebuild_under_lock() -> dict[str, Any]:
    from apps.cmdb.services.ci_context import rebuild_ci_context_bounded

    cursor = _cursor_state()
    result = rebuild_ci_context_bounded(skip=cursor["skip"], limit=REBUILD_BUDGET)
    ok_count = cursor["ok"] + result["ok_count"]
    fail_count = cursor["fail"] + result["fail_count"]
    if result["done"] and cursor["skip"] == 0 and int(result.get("seen") or 0) == 0:
        # 第 0 页为空可能是图还没数据，不能当成摊完并关掉周期任务。
        logger.info("event=ci_context_rebuild_waiting reason=%s", "empty")
        return {"status": "waiting", "reason": "empty"}
    if result["done"]:
        cache.delete(REBUILD_CURSOR_KEY)
        _disable_rebuild_periodic_task()
        logger.info(
            "event=ci_context_rebuild_finished recomputed=%s failed=%s",
            ok_count,
            fail_count,
        )
        return {
            "status": "done",
            "recomputed": ok_count,
            "failed": fail_count,
        }

    cache.set(
        REBUILD_CURSOR_KEY,
        {"skip": result["next_skip"], "ok": ok_count, "fail": fail_count},
        timeout=REBUILD_CURSOR_TTL,
    )
    rebuild_ci_context_runtime.apply_async(countdown=1)
    logger.debug(
        "event=ci_context_rebuild_continue skip=%s recomputed=%s failed=%s",
        result["next_skip"],
        ok_count,
        fail_count,
    )
    return {
        "status": "continue",
        "skip": result["next_skip"],
        "recomputed": ok_count,
        "failed": fail_count,
    }
