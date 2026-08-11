"""按知识库串行的资料构建队列。

同 KB 内资料顺序构建；不同 KB 可并发。入队只写 DB + 至多 kick 一个 runner Celery 任务，
避免对每条资料各投递一个长任务导致队列爆炸。
"""

from __future__ import annotations

import os
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import BuildRecord, Material, WikiKnowledgeBase

QUEUE_ITEM_TRIGGER = "material_queue_item"
RUNNER_TRIGGER = "material_queue"
QUEUED_STATUS = "queued"
_ACTIVE_BUILD_STATUSES = frozenset({"parsing", "building"})
_MAX_BATCH_SIZE = 200
_RUNNER_STALE_SECONDS = int(os.environ.get("WIKI_MATERIAL_BUILD_RUNNER_STALE_SECONDS", str(2 * 3600)))


class MaterialBuildQueueError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _dedupe_ids(material_ids) -> list[int]:
    seen = set()
    ordered = []
    for raw in material_ids or []:
        try:
            mid = int(raw)
        except (TypeError, ValueError):
            continue
        if mid <= 0 or mid in seen:
            continue
        seen.add(mid)
        ordered.append(mid)
    return ordered


def _is_stale_runner(lease: BuildRecord) -> bool:
    stamp = lease.updated_at or lease.created_at
    if stamp is None:
        return True
    return stamp < timezone.now() - timedelta(seconds=max(_RUNNER_STALE_SECONDS, 60))


def _active_runner_lease(kb_id: int):
    return (
        BuildRecord.objects.filter(
            knowledge_base_id=kb_id,
            trigger=RUNNER_TRIGGER,
            status="running",
        )
        .order_by("-id")
        .first()
    )


def has_active_runner(kb_id: int) -> bool:
    lease = _active_runner_lease(kb_id)
    if lease is None:
        return False
    return not _is_stale_runner(lease)


def enqueue_material_builds(*, knowledge_base_id: int, material_ids, operator: str = "") -> dict:
    """将资料加入 KB 构建队列并必要时 kick runner。

    返回:
      {
        queued: [id...],
        already_queued: [id...],
        in_progress: [id...],
        skipped: [{id, reason}],
        kicked: bool,
      }
    """
    ids = _dedupe_ids(material_ids)
    if not ids:
        raise MaterialBuildQueueError("material_ids_required", "material_ids 必填", status_code=400)
    if len(ids) > _MAX_BATCH_SIZE:
        raise MaterialBuildQueueError(
            "material_ids_too_many",
            f"单次最多排队 {_MAX_BATCH_SIZE} 条资料",
            status_code=400,
            details={"max": _MAX_BATCH_SIZE},
        )

    kb = WikiKnowledgeBase.objects.filter(pk=knowledge_base_id).first()
    if kb is None:
        raise MaterialBuildQueueError("knowledge_base_not_found", "知识库不存在", status_code=404)

    queued: list[int] = []
    already_queued: list[int] = []
    in_progress: list[int] = []
    skipped: list[dict] = []

    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
        materials = {m.pk: m for m in Material.objects.select_for_update().filter(knowledge_base_id=knowledge_base_id, id__in=ids).order_by("id")}
        for mid in ids:
            material = materials.get(mid)
            if material is None:
                skipped.append({"id": mid, "reason": "not_found_in_kb"})
                continue
            if material.status in _ACTIVE_BUILD_STATUSES:
                in_progress.append(mid)
                continue
            if material.status == QUEUED_STATUS:
                already_queued.append(mid)
                continue
            if material.status == "invalid":
                skipped.append({"id": mid, "reason": "invalid"})
                continue

            source_status = material.status
            material.status = QUEUED_STATUS
            material.error_message = ""
            material.save(update_fields=["status", "error_message", "updated_at"])
            BuildRecord.objects.create(
                knowledge_base_id=knowledge_base_id,
                trigger=QUEUE_ITEM_TRIGGER,
                operator=operator or "",
                stage="queued",
                status="running",
                inputs={
                    "material_id": material.pk,
                    "source_status": source_status,
                    "classification_root_id": material.classification_root_id,
                },
            )
            queued.append(mid)

    kicked = kick_kb_material_build_runner(knowledge_base_id, operator=operator)
    return {
        "knowledge_base_id": knowledge_base_id,
        "queued": queued,
        "already_queued": already_queued,
        "in_progress": in_progress,
        "skipped": skipped,
        "kicked": kicked,
    }


def try_acquire_kb_build_runner(kb_id: int, operator: str = "") -> BuildRecord | None:
    """领取已 scheduled 的 runner 租约；重复 Celery 投递或他人持有时返回 None。"""
    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        lease = (
            BuildRecord.objects.select_for_update()
            .filter(
                knowledge_base_id=kb_id,
                trigger=RUNNER_TRIGGER,
                status="running",
            )
            .order_by("-id")
            .first()
        )
        if lease is None:
            return None
        if lease.stage == "scheduled":
            lease.stage = "running"
            if operator and not lease.operator:
                lease.operator = operator
            lease.save(update_fields=["stage", "operator", "updated_at"])
            return lease
        if lease.stage == "running":
            if _is_stale_runner(lease):
                lease.stage = "running"
                lease.operator = operator or lease.operator
                lease.errors = []
                lease.save(update_fields=["stage", "operator", "errors", "updated_at"])
                return lease
            return None
        return None


def _ensure_scheduled_runner_lease(kb_id: int, operator: str = "") -> BuildRecord | None:
    """若无活跃租约则创建 stage=scheduled 的租约，供随后唯一一次 Celery kick。"""
    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        lease = (
            BuildRecord.objects.select_for_update()
            .filter(
                knowledge_base_id=kb_id,
                trigger=RUNNER_TRIGGER,
                status="running",
            )
            .order_by("-id")
            .first()
        )
        if lease is not None:
            if _is_stale_runner(lease):
                lease.stage = "stale"
                lease.status = "failed"
                lease.errors = [{"code": "runner_stale", "message": "material build runner lease expired"}]
                lease.progress = 100
                lease.save(update_fields=["stage", "status", "errors", "progress", "updated_at"])
            else:
                return None
        return BuildRecord.objects.create(
            knowledge_base_id=kb_id,
            trigger=RUNNER_TRIGGER,
            operator=operator or "",
            stage="scheduled",
            status="running",
            inputs={"kind": "material_build_queue"},
            counts={"processed": 0, "failed": 0},
        )


def release_kb_build_runner(lease: BuildRecord, *, processed: int = 0, failed: int = 0) -> None:
    lease.refresh_from_db()
    if lease.status != "running":
        return
    lease.stage = "done"
    lease.status = "success"
    lease.progress = 100
    lease.counts = {
        **(lease.counts or {}),
        "processed": processed,
        "failed": failed,
    }
    lease.save(update_fields=["stage", "status", "progress", "counts", "updated_at"])


def _touch_runner(lease: BuildRecord) -> None:
    BuildRecord.objects.filter(pk=lease.pk, status="running").update(updated_at=timezone.now())


def ensure_running_material_build_record(
    *,
    knowledge_base_id: int,
    material_id: int,
    operator: str = "",
    source_status: str | None = None,
    stage: str = "preparing",
) -> BuildRecord:
    """确保存在可用于列表展示起止时间的真实 material 构建记录。"""
    existing = (
        BuildRecord.objects.filter(
            knowledge_base_id=knowledge_base_id,
            trigger="material",
            status="running",
            inputs__material_id=material_id,
        )
        .order_by("-id")
        .first()
    )
    if existing is not None:
        inputs = dict(existing.inputs or {})
        changed = []
        if source_status and not inputs.get("source_status"):
            inputs["source_status"] = source_status
            existing.inputs = inputs
            changed.append("inputs")
        if stage and existing.stage != stage and existing.stage in {"preparing", "queued", "parsing"}:
            existing.stage = stage
            changed.append("stage")
        if operator and not existing.operator:
            existing.operator = operator
            changed.append("operator")
        if changed:
            existing.save(update_fields=[*changed, "updated_at"])
        return existing
    inputs = {"material_id": material_id}
    if source_status:
        inputs["source_status"] = source_status
    return BuildRecord.objects.create(
        knowledge_base_id=knowledge_base_id,
        trigger="material",
        operator=operator or "",
        stage=stage,
        status="running",
        inputs=inputs,
    )


def claim_next_queued_material(kb_id: int, *, operator: str = "") -> dict | None:
    """领取下一条排队资料。返回 {material_id, source_status, classification_root_id} 或 None。"""
    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        item = (
            BuildRecord.objects.select_for_update()
            .filter(
                knowledge_base_id=kb_id,
                trigger=QUEUE_ITEM_TRIGGER,
                stage="queued",
                status="running",
            )
            .order_by("id")
            .first()
        )
        if item is not None:
            inputs = item.inputs or {}
            material_id = int(inputs.get("material_id") or 0)
            source_status = inputs.get("source_status") or "pending"
            classification_root_id = inputs.get("classification_root_id")
            item.stage = "dispatched"
            item.status = "success"
            item.progress = 100
            item.save(update_fields=["stage", "status", "progress", "updated_at"])
            if material_id:
                # 领取即标为 building,并创建真实 BuildRecord,列表立刻有构建开始时间
                updated = Material.objects.filter(
                    pk=material_id,
                    knowledge_base_id=kb_id,
                    status=QUEUED_STATUS,
                ).update(status="building", error_message="", updated_at=timezone.now())
                if not updated:
                    Material.objects.filter(pk=material_id, knowledge_base_id=kb_id).update(
                        status="building",
                        error_message="",
                        updated_at=timezone.now(),
                    )
                build = ensure_running_material_build_record(
                    knowledge_base_id=kb_id,
                    material_id=material_id,
                    operator=operator,
                    source_status=source_status,
                    stage="preparing",
                )
                return {
                    "material_id": material_id,
                    "source_status": source_status,
                    "classification_root_id": classification_root_id,
                    "build_record_id": build.pk,
                }

        # 兜底：状态为 queued 但缺少队列记录的资料
        material = Material.objects.select_for_update().filter(knowledge_base_id=kb_id, status=QUEUED_STATUS).order_by("id").first()
        if material is None:
            return None
        material.status = "building"
        material.error_message = ""
        material.save(update_fields=["status", "error_message", "updated_at"])
        build = ensure_running_material_build_record(
            knowledge_base_id=kb_id,
            material_id=material.pk,
            operator=operator,
            source_status="pending",
            stage="preparing",
        )
        return {
            "material_id": material.pk,
            "source_status": "pending",
            "classification_root_id": material.classification_root_id,
            "build_record_id": build.pk,
        }


def kb_has_queued_materials(kb_id: int) -> bool:
    if BuildRecord.objects.filter(
        knowledge_base_id=kb_id,
        trigger=QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
    ).exists():
        return True
    return Material.objects.filter(knowledge_base_id=kb_id, status=QUEUED_STATUS).exists()


def kick_kb_material_build_runner(kb_id: int, operator: str = "") -> bool:
    """确保至多一个 scheduled/running 租约，并仅在新建租约时投递 Celery 任务。"""
    if not kb_has_queued_materials(kb_id):
        return False
    lease = _ensure_scheduled_runner_lease(kb_id, operator=operator)
    if lease is None:
        return False
    from apps.opspilot import tasks as opspilot_tasks

    try:
        opspilot_tasks.wiki_process_kb_material_builds_task.delay(kb_id, operator or "")
        return True
    except Exception:
        logger.exception("wiki material build runner 投递失败 kb=%s", kb_id)
        BuildRecord.objects.filter(pk=lease.pk, status="running").update(
            stage="dispatch_failed",
            status="failed",
            progress=100,
            updated_at=timezone.now(),
        )
        raise


def process_kb_material_builds(kb_id: int, operator: str = "") -> dict:
    """串行消费某 KB 的构建队列（供 Celery runner 调用）。"""
    from apps.opspilot.tasks import wiki_build_material_task

    lease = try_acquire_kb_build_runner(kb_id, operator=operator)
    if lease is None:
        return {"skipped": "runner_active", "processed": 0, "failed": 0}

    processed = 0
    failed = 0
    try:
        while True:
            claimed = claim_next_queued_material(kb_id, operator=operator)
            if claimed is None:
                break
            _touch_runner(lease)
            material_id = claimed["material_id"]
            material = Material.objects.select_related("knowledge_base").filter(pk=material_id, knowledge_base_id=kb_id).first()
            if material is None:
                failed += 1
                continue
            try:
                wiki_build_material_task.run(
                    material.pk,
                    material.knowledge_base.llm_model_id,
                    operator or "",
                    classification_root_id=claimed.get("classification_root_id"),
                    ensure_parsed=True,
                    source_status=claimed.get("source_status"),
                    build_record_id=claimed.get("build_record_id"),
                )
                processed += 1
            except Exception:  # noqa: BLE001 - 单条失败不阻断队列
                failed += 1
                logger.exception(
                    "wiki KB 串行构建单条失败 kb=%s material=%s",
                    kb_id,
                    material_id,
                )
                Material.objects.filter(pk=material_id, status__in=("parsing", "building", QUEUED_STATUS)).update(
                    status="build_failed",
                    error_message="构建任务异常退出",
                    updated_at=timezone.now(),
                )
    finally:
        release_kb_build_runner(lease, processed=processed, failed=failed)
        # 释放租约后若仍有排队（入队竞态），再 kick 一次；仍保证至多一个活跃 runner
        if kb_has_queued_materials(kb_id):
            try:
                kick_kb_material_build_runner(kb_id, operator=operator)
            except Exception:  # noqa: BLE001
                logger.exception("wiki material build runner 续跑投递失败 kb=%s", kb_id)

    return {"processed": processed, "failed": failed, "skipped": None}


def cancel_stale_queue_items_for_missing_materials(kb_id: int) -> int:
    """清理指向已删除资料的队列项（运维/测试辅助）。"""
    items = BuildRecord.objects.filter(
        knowledge_base_id=kb_id,
        trigger=QUEUE_ITEM_TRIGGER,
        stage="queued",
        status="running",
    )
    closed = 0
    for item in items.iterator():
        mid = (item.inputs or {}).get("material_id")
        if mid and Material.objects.filter(pk=mid).exists():
            continue
        item.stage = "cancelled"
        item.status = "failed"
        item.progress = 100
        item.save(update_fields=["stage", "status", "progress", "updated_at"])
        closed += 1
    return closed


# 供列表排序等引用
ATTENTION_QUEUE_STATUSES = (QUEUED_STATUS,)
