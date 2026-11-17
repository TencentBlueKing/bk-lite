"""启动后一次性修复实例组织、列表标量和变更过的唯一规则。"""

from __future__ import annotations

import uuid

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.core.cache import cache

from apps.cmdb.services.instance_shape_repair import InstanceShapeRepair
from apps.core.logger import cmdb_logger as logger
from apps.core.logger import safe_exception_info

INSTANCE_SHAPE_REPAIR_TASK = "apps.cmdb.tasks.instance_shape_repair.repair_cmdb_instance_shape"
INSTANCE_SHAPE_REPAIR_LOCK = "cmdb:instance-shape-repair-lock"
INSTANCE_SHAPE_REPAIR_LOCK_TTL = 1860


def _release_shape_lock(token: str) -> None:
    if cache.get(INSTANCE_SHAPE_REPAIR_LOCK) == token:
        cache.delete(INSTANCE_SHAPE_REPAIR_LOCK)


@shared_task(name=INSTANCE_SHAPE_REPAIR_TASK, soft_time_limit=1800, time_limit=1860)
def repair_cmdb_instance_shape() -> dict:
    token = uuid.uuid4().hex
    if not cache.add(INSTANCE_SHAPE_REPAIR_LOCK, token, timeout=INSTANCE_SHAPE_REPAIR_LOCK_TTL):
        logger.warning("event=instance_shape_repair_locked")
        return {"status": "locked"}
    try:
        status = InstanceShapeRepair().run()
        if status == "continue":
            repair_cmdb_instance_shape.apply_async(countdown=1)
            logger.debug("event=instance_shape_repair_finished status=%s", status)
        else:
            logger.info("event=instance_shape_repair_finished status=%s", status)
        return {"status": status}
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "event=instance_shape_repair_soft_timeout failed_stage=repair error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        repair_cmdb_instance_shape.apply_async(countdown=60)
        return {"status": "retry", "reason": "soft_timeout"}
    except Exception as exc:
        logger.error(
            "event=instance_shape_repair_failed failed_stage=repair error_type=%s",
            type(exc).__name__,
            exc_info=safe_exception_info(exc),
        )
        return {"status": "retry", "reason": "repair_failed"}
    finally:
        _release_shape_lock(token)
