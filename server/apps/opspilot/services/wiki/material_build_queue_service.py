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
from apps.core.logger import safe_exception_call_chain, safe_exception_info
from apps.opspilot.models import BuildRecord, Material, WikiKnowledgeBase

QUEUE_ITEM_TRIGGER = "material_queue_item"
RUNNER_TRIGGER = "material_queue"
QUEUED_STATUS = "queued"
QUEUE_RESUME_INPUT_KEY = "resume_interrupted"
_ACTIVE_BUILD_STATUSES = frozenset({"parsing", "building"})
USER_BUILD_TRIGGERS = frozenset({"material", "material_update", "rebuild"})
CROSS_PIPELINE_TRIGGERS = frozenset({"rebuild", "material_update"})
_MAX_BATCH_SIZE = 200
_RUNNER_STALE_SECONDS = int(os.environ.get("WIKI_MATERIAL_BUILD_RUNNER_STALE_SECONDS", str(2 * 3600)))


class MaterialBuildQueueError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _log_runner_dispatch_failure(kb_id: int, lease_id: int, exc: BaseException) -> None:
    """投递失败只在 kick 边界打一条 traceback；异常正文可能含 broker 地址，用类型名代替。"""
    logger.error(
        "wiki material build runner 投递失败 kb=%s lease_id=%s failed_stage=%s error_type=%s call_chain=%s",
        kb_id,
        lease_id,
        "task_dispatch",
        type(exc).__name__,
        safe_exception_call_chain(exc),
        exc_info=safe_exception_info(exc),
    )


class MaterialBuildCancelled(Exception):
    """In-flight 资料构建发现 BuildRecord 已取消，调用方应丢弃写入。"""


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


def kb_has_user_build_in_progress(kb_id, *, exclude_build_id=None) -> bool:
    """是否有用户可见的资料/重建任务在跑。队列租约和排队项不算。"""
    qs = BuildRecord.objects.filter(
        knowledge_base_id=kb_id,
        status="running",
        trigger__in=USER_BUILD_TRIGGERS,
    )
    if exclude_build_id is not None:
        qs = qs.exclude(pk=exclude_build_id)
    return qs.exists()


def kb_has_cross_pipeline_build_in_progress(kb_id) -> bool:
    """rebuild / material_update 与资料队列互斥；不含兄弟 material 和队列租约。"""
    return BuildRecord.objects.filter(
        knowledge_base_id=kb_id,
        status="running",
        trigger__in=CROSS_PIPELINE_TRIGGERS,
    ).exists()


def unstick_material_for_cancelled_build(record) -> bool:
    """取消构建后解开资料的 parsing/building/queued，避免资料页卡在构建中。"""
    if getattr(record, "trigger", "") not in {"material", "material_update"}:
        return False
    material_id = (record.inputs or {}).get("material_id")
    if not material_id:
        return False
    material = Material.objects.filter(pk=material_id, knowledge_base_id=record.knowledge_base_id).first()
    if material is None:
        return False
    BuildRecord.objects.filter(
        knowledge_base_id=record.knowledge_base_id,
        trigger=QUEUE_ITEM_TRIGGER,
        status="running",
        stage="queued",
        inputs__material_id=material.pk,
    ).update(
        stage="cancelled",
        status="failed",
        progress=100,
        updated_at=timezone.now(),
    )
    if material.status not in (_ACTIVE_BUILD_STATUSES | {QUEUED_STATUS}):
        return False
    material.status = "build_failed" if material.current_version_id else "parse_failed"
    material.error_message = "构建已取消"
    material.save(update_fields=["status", "error_message", "updated_at"])
    return True


def release_idle_runner_lease(kb_id: int, *, operator: str = "", kick_if_queued: bool = True) -> bool:
    """没有用户构建在跑时释放队列 runner，避免 Celery 死后租约挡住重试和入队。

    kick_if_queued=False：只拆租约，不续跑队列。重试会自己投递当前资料，
    若这里再 kick，会把排队里的其它资料一并拉起，出现两条并行「进行中」。
    """
    if kb_has_user_build_in_progress(kb_id):
        return False
    lease = _active_runner_lease(kb_id)
    if lease is None:
        return False
    queued = kb_has_queued_materials(kb_id)
    lease.stage = "cancelled"
    lease.status = "failed"
    lease.progress = 100
    lease.errors = [{"code": "runner_released", "message": "无进行中的资料构建，释放队列租约"}]
    lease.save(update_fields=["stage", "status", "progress", "errors", "updated_at"])
    if queued and kick_if_queued:
        kick_kb_material_build_runner(kb_id, operator=operator)
    return True


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
        if kb_has_cross_pipeline_build_in_progress(knowledge_base_id):
            raise MaterialBuildQueueError(
                "knowledge_base_build_in_progress",
                "知识库存在运行中的构建任务，请等待完成后再操作",
                status_code=409,
            )
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
                    "material_name": material.name,
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


def try_acquire_kb_build_runner(kb_id: int, operator: str = "", *, reclaim_running: bool = False) -> BuildRecord | None:
    """领取已 scheduled 的 runner 租约；他人仍持有新鲜租约时返回 None。

    reclaim_running 已废弃，调用方传入也不再抢新鲜 running 租约。
    仅 stale 租约可接管；进程死后的续跑走 resume_wiki_material_builds。
    """
    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        if kb_has_cross_pipeline_build_in_progress(kb_id):
            return None
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
            if not _is_stale_runner(lease):
                return None
            lease.stage = "running"
            lease.operator = operator or lease.operator
            lease.errors = []
            lease.save(update_fields=["stage", "operator", "errors", "updated_at"])
            return lease
        return None


def _ensure_scheduled_runner_lease(kb_id: int, operator: str = "") -> BuildRecord | None:
    """若无活跃租约则创建 stage=scheduled 的租约，供随后唯一一次 Celery kick。"""
    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        if kb_has_cross_pipeline_build_in_progress(kb_id):
            return None
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
    # 队列 runner 的 status 必须反映失败数，否则「筛选失败」看不到、界面却显示 failed N。
    if failed > 0 and processed > 0:
        lease.status = "partial"
    elif failed > 0:
        lease.status = "failed"
    else:
        lease.status = "success"
    lease.progress = 100
    lease.counts = {
        **(lease.counts or {}),
        "processed": processed,
        "failed": failed,
    }
    lease.save(update_fields=["stage", "status", "progress", "counts", "updated_at"])


def repair_queue_runner_status_from_counts(kb_id: int) -> int:
    """修正历史脏数据：material_queue 成功但 counts.failed>0 的记录。"""

    fixed = 0
    runners = BuildRecord.objects.filter(
        knowledge_base_id=kb_id,
        trigger=RUNNER_TRIGGER,
        status="success",
    ).order_by("id")
    for lease in runners.iterator():
        counts = lease.counts or {}
        try:
            failed = int(counts.get("failed") or 0)
            processed = int(counts.get("processed") or 0)
        except (TypeError, ValueError):
            continue
        if failed <= 0:
            continue
        lease.status = "partial" if processed > 0 else "failed"
        lease.save(update_fields=["status", "updated_at"])
        fixed += 1
    return fixed


def _touch_runner(lease: BuildRecord) -> None:
    BuildRecord.objects.filter(pk=lease.pk, status="running").update(updated_at=timezone.now())


def _runner_still_owns(lease: BuildRecord) -> bool:
    current = (
        BuildRecord.objects.filter(
            pk=lease.pk,
            trigger=RUNNER_TRIGGER,
            status="running",
        )
        .only("stage")
        .first()
    )
    return current is not None and current.stage in {"scheduled", "running"}


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
                inputs__resume_interrupted=True,
            )
            .order_by("id")
            .first()
        )
        if item is None:
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
    except Exception as exc:
        _log_runner_dispatch_failure(kb_id, lease.pk, exc)
        BuildRecord.objects.filter(pk=lease.pk, status="running").update(
            stage="dispatch_failed",
            status="failed",
            progress=100,
            updated_at=timezone.now(),
        )
        raise


def _force_release_runner_lease(kb_id: int) -> bool:
    """结束当前 runner 租约，供进程中断后的继续构建使用。

    旧循环必须在下次 claim 前看到 status!=running 后退出；不凭 redelivered 抢活租约。
    """
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
            return False
        lease.stage = "cancelled"
        lease.status = "failed"
        lease.progress = 100
        lease.errors = [{"code": "runner_released", "message": "进程中断后释放队列租约"}]
        lease.save(update_fields=["stage", "status", "progress", "errors", "updated_at"])
        return True


def release_stale_runner_lease(kb_id: int) -> bool:
    """仅拆 stale 的 runner 租约，供 rebuild 启动；新鲜租约不动。"""
    lease = _active_runner_lease(kb_id)
    if lease is None or not _is_stale_runner(lease):
        return False
    return _force_release_runner_lease(kb_id)


def requeue_interrupted_materials(kb_id: int, *, operator: str = "") -> list[int]:
    """把 parsing/building 的资料收回排队，并优先于原有排队项领取。"""
    requeued: list[int] = []
    with transaction.atomic():
        WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        materials = list(Material.objects.select_for_update().filter(knowledge_base_id=kb_id, status__in=_ACTIVE_BUILD_STATUSES).order_by("id"))
        for material in materials:
            source_status = material.status
            running = BuildRecord.objects.filter(
                knowledge_base_id=kb_id,
                trigger="material",
                status="running",
                inputs__material_id=material.pk,
            )
            for build in running:
                fail_material_build_record(
                    build.pk,
                    knowledge_base_id=kb_id,
                    code="material_build_interrupted",
                    message="构建因进程中断已重新排队",
                )
            existing_items = list(
                BuildRecord.objects.select_for_update()
                .filter(
                    knowledge_base_id=kb_id,
                    trigger=QUEUE_ITEM_TRIGGER,
                    stage="queued",
                    status="running",
                    inputs__material_id=material.pk,
                )
                .order_by("id")
            )
            material.status = QUEUED_STATUS
            material.error_message = ""
            material.save(update_fields=["status", "error_message", "updated_at"])
            if existing_items:
                for item in existing_items:
                    inputs = dict(item.inputs or {})
                    inputs[QUEUE_RESUME_INPUT_KEY] = True
                    inputs["source_status"] = source_status
                    item.inputs = inputs
                    update_fields = ["inputs", "updated_at"]
                    if operator and not item.operator:
                        item.operator = operator
                        update_fields.append("operator")
                    item.save(update_fields=update_fields)
            else:
                BuildRecord.objects.create(
                    knowledge_base_id=kb_id,
                    trigger=QUEUE_ITEM_TRIGGER,
                    operator=operator or "",
                    stage="queued",
                    status="running",
                    inputs={
                        "material_id": material.pk,
                        "material_name": material.name,
                        "source_status": source_status,
                        "classification_root_id": material.classification_root_id,
                        QUEUE_RESUME_INPUT_KEY: True,
                    },
                )
            requeued.append(material.pk)
    return requeued


def resume_kb_material_builds(kb_id: int, *, operator: str = "") -> dict:
    """升级/Celery 中断后继续串行构建：中断项排到队首，其余排队项保持原顺序。"""
    kb = WikiKnowledgeBase.objects.filter(pk=kb_id).first()
    if kb is None:
        raise MaterialBuildQueueError("knowledge_base_not_found", "知识库不存在", status_code=404)
    if kb_has_cross_pipeline_build_in_progress(kb_id):
        raise MaterialBuildQueueError(
            "knowledge_base_build_in_progress",
            "知识库存在运行中的构建任务，请等待完成后再操作",
            status_code=409,
        )
    requeued = requeue_interrupted_materials(kb_id, operator=operator)
    released = _force_release_runner_lease(kb_id)
    kicked = kick_kb_material_build_runner(kb_id, operator=operator)
    logger.info(
        "wiki material builds resumed kb=%s requeued=%s released=%s kicked=%s",
        kb_id,
        len(requeued),
        released,
        kicked,
    )
    return {
        "knowledge_base_id": kb_id,
        "requeued": requeued,
        "released": released,
        "kicked": kicked,
    }


def fail_material_build_record(
    build_record_id: int | None,
    *,
    knowledge_base_id: int | None = None,
    code: str = "material_build_aborted",
    message: str = "构建任务异常退出",
) -> bool:
    """将仍 running 的 material BuildRecord 收尾为 failed。返回是否写入。"""

    if not build_record_id:
        return False
    qs = BuildRecord.objects.filter(
        pk=build_record_id,
        trigger="material",
        status="running",
    )
    if knowledge_base_id is not None:
        qs = qs.filter(knowledge_base_id=knowledge_base_id)
    build = qs.first()
    if build is None:
        return False
    build.stage = "failed"
    build.status = "failed"
    build.progress = 100
    build.errors = [{"code": code, "message": message}]
    build.save(update_fields=["stage", "status", "progress", "errors", "updated_at"])
    return True


def reconcile_orphaned_material_builds(kb_id: int) -> int:
    """关闭「资料已不在构建态、但 BuildRecord 仍 running」的孤儿记录。

    claim 后若任务在解析/加锁阶段抛错、或进程被杀，会出现资料已回落、
    记录仍停在 preparing 的不一致；列表会显示大量「进行中」。
    """

    closed = 0
    running = BuildRecord.objects.filter(
        knowledge_base_id=kb_id,
        trigger="material",
        status="running",
    ).order_by("id")
    for build in running.iterator():
        material_id = (build.inputs or {}).get("material_id")
        if not material_id:
            if fail_material_build_record(
                build.pk,
                knowledge_base_id=kb_id,
                code="material_build_orphan",
                message="构建记录缺少 material_id",
            ):
                closed += 1
            continue
        material = Material.objects.filter(pk=material_id, knowledge_base_id=kb_id).only("status").first()
        if material is None:
            if fail_material_build_record(
                build.pk,
                knowledge_base_id=kb_id,
                code="material_missing",
                message="资料已删除，关闭残留构建记录",
            ):
                closed += 1
            continue
        if material.status in _ACTIVE_BUILD_STATUSES or material.status == QUEUED_STATUS:
            continue
        if fail_material_build_record(
            build.pk,
            knowledge_base_id=kb_id,
            code="material_build_orphan",
            message=f"资料已离开构建态（status={material.status}），关闭残留构建记录",
        ):
            closed += 1
    return closed


def process_kb_material_builds(kb_id: int, operator: str = "", *, reclaim_running: bool = False) -> dict:
    """串行消费某 KB 的构建队列（供 Celery runner 调用）。

    reclaim_running 已废弃，保留参数以免旧调用方报错；新鲜租约不会被接管。
    """
    from apps.opspilot.tasks import wiki_build_material_task

    reconcile_orphaned_material_builds(kb_id)

    if kb_has_cross_pipeline_build_in_progress(kb_id):
        logger.info("wiki material build runner skipped kb=%s reason=%s", kb_id, "cross_pipeline")
        return {"skipped": "cross_pipeline", "processed": 0, "failed": 0}

    lease = try_acquire_kb_build_runner(kb_id, operator=operator)
    if lease is None:
        reason = "cross_pipeline" if kb_has_cross_pipeline_build_in_progress(kb_id) else "runner_active"
        logger.info("wiki material build runner skipped kb=%s reason=%s", kb_id, reason)
        return {"skipped": reason, "processed": 0, "failed": 0}

    requeue_interrupted_materials(kb_id, operator=operator)

    processed = 0
    failed = 0
    stop_reason = None
    try:
        while True:
            if not _runner_still_owns(lease):
                stop_reason = "lease_lost"
                logger.info("wiki material build runner lost lease kb=%s lease_id=%s", kb_id, lease.pk)
                break
            if kb_has_cross_pipeline_build_in_progress(kb_id):
                stop_reason = "cross_pipeline"
                logger.info(
                    "wiki material build runner stopped kb=%s reason=%s lease_id=%s",
                    kb_id,
                    "cross_pipeline",
                    lease.pk,
                )
                break
            claimed = claim_next_queued_material(kb_id, operator=operator)
            if claimed is None:
                break
            _touch_runner(lease)
            material_id = claimed["material_id"]
            build_record_id = claimed.get("build_record_id")
            material = Material.objects.select_related("knowledge_base").filter(pk=material_id, knowledge_base_id=kb_id).first()
            if material is None:
                failed += 1
                fail_material_build_record(
                    build_record_id,
                    knowledge_base_id=kb_id,
                    code="material_missing",
                    message="队列领取后资料不存在",
                )
                continue
            try:
                wiki_build_material_task.run(
                    material.pk,
                    material.knowledge_base.llm_model_id,
                    operator or "",
                    classification_root_id=claimed.get("classification_root_id"),
                    ensure_parsed=True,
                    source_status=claimed.get("source_status"),
                    build_record_id=build_record_id,
                )
                processed += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不阻断队列
                failed += 1
                logger.error(
                    "wiki KB 串行构建单条失败 kb=%s lease_id=%s material=%s build_record_id=%s " "failed_stage=%s error_type=%s call_chain=%s",
                    kb_id,
                    lease.pk,
                    material_id,
                    build_record_id,
                    "material_build",
                    type(exc).__name__,
                    safe_exception_call_chain(exc),
                    exc_info=safe_exception_info(exc),
                )
                Material.objects.filter(pk=material_id, status__in=("parsing", "building", QUEUED_STATUS)).update(
                    status="build_failed",
                    error_message="构建任务异常退出",
                    updated_at=timezone.now(),
                )
                fail_material_build_record(
                    build_record_id,
                    knowledge_base_id=kb_id,
                    code="material_build_aborted",
                    message="构建任务异常退出",
                )
    finally:
        release_kb_build_runner(lease, processed=processed, failed=failed)
        # 释放租约后若仍有排队（入队竞态），再 kick 一次；仍保证至多一个活跃 runner
        if kb_has_queued_materials(kb_id) and not kb_has_cross_pipeline_build_in_progress(kb_id):
            try:
                kick_kb_material_build_runner(kb_id, operator=operator)
            except Exception as exc:  # noqa: BLE001 - traceback 已由 kick 持有
                logger.warning(
                    "wiki material build runner 续跑投递失败 kb=%s lease_id=%s failed_stage=%s error_type=%s",
                    kb_id,
                    lease.pk,
                    "task_dispatch_resume",
                    type(exc).__name__,
                )

    return {"processed": processed, "failed": failed, "skipped": stop_reason}


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
