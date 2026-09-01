import base64

from celery import shared_task
from django.db import transaction

from apps.core.logger import opspilot_logger as logger

_WIKI_TASK_IDENTITY_FIELDS = (
    "base_generation_id",
    "structure_revision_id",
    "structure_version",
    "structure_fingerprint",
    "pipeline_version",
    "source_fingerprints",
    "classification_root_id",
)


def _material_build_is_cancelled(build) -> bool:
    return bool(build is not None and getattr(build, "status", None) == "cancelled")


def _discard_cancelled_material_build(build, material_id) -> bool:
    if not _material_build_is_cancelled(build):
        return False
    logger.info("wiki material build discarded cancelled record=%s material=%s", build.pk, material_id)
    return True


def _lock_wiki_generation_task(knowledge_base_id):
    """Lock the knowledge base used by a generation-aware task."""

    from apps.opspilot.models import WikiKnowledgeBase

    return WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)


def _freeze_wiki_task_identity(
    knowledge_base,
    materials,
    *,
    classification_root_id=None,
):
    """Freeze all identities that a generation task is allowed to observe."""

    from apps.opspilot.models import WikiKnowledgeBase
    from apps.opspilot.services.wiki.build_generation_service import PIPELINE_VERSION, BuildGenerationError, freeze_source_fingerprints

    knowledge_base = WikiKnowledgeBase.objects.select_related("active_structure_revision").get(pk=knowledge_base.pk)
    revision = knowledge_base.active_structure_revision
    if revision is None or knowledge_base.active_generation_id is None:
        raise BuildGenerationError(
            "active_governance_snapshot_missing",
            "知识库缺少 active structure/generation",
        )
    source_fingerprints = freeze_source_fingerprints(materials)
    incomplete = [
        fingerprint
        for fingerprint in source_fingerprints
        if not fingerprint.get("material_version_id")
        or not str(fingerprint.get("content_hash") or "").strip()
        or not str(fingerprint.get("source_identity") or "").strip()
    ]
    if incomplete:
        raise BuildGenerationError(
            "source_identity_incomplete",
            "generation 任务缺少完整资料来源身份",
            details={"source_fingerprints": incomplete},
        )
    return {
        "base_generation_id": knowledge_base.active_generation_id,
        "structure_revision_id": revision.pk,
        "structure_version": revision.revision_no,
        "structure_fingerprint": revision.fingerprint,
        "pipeline_version": PIPELINE_VERSION,
        "source_fingerprints": source_fingerprints,
        "classification_root_id": classification_root_id,
    }


def _resolve_wiki_task_identity(
    knowledge_base,
    materials,
    *,
    classification_root_id=None,
    task_identity=None,
):
    from apps.opspilot.services.wiki.build_generation_service import BuildGenerationError

    current = _freeze_wiki_task_identity(
        knowledge_base,
        materials,
        classification_root_id=classification_root_id,
    )
    if current is None:
        return None
    if task_identity is None:
        raise BuildGenerationError(
            "task_identity_incomplete",
            "generation truth 状态的任务缺少固定身份，已拒绝继续",
            details={"missing_fields": list(_WIKI_TASK_IDENTITY_FIELDS)},
        )
    if not isinstance(task_identity, dict):
        raise BuildGenerationError(
            "task_identity_invalid",
            "generation task identity 必须为对象",
        )
    missing = [field for field in _WIKI_TASK_IDENTITY_FIELDS if field not in task_identity]
    if missing:
        raise BuildGenerationError(
            "task_identity_incomplete",
            "旧 generation 任务缺少固定身份，已拒绝继续",
            details={"missing_fields": missing},
        )
    mismatches = {
        field: {
            "expected": current[field],
            "actual": task_identity.get(field),
        }
        for field in _WIKI_TASK_IDENTITY_FIELDS
        if task_identity.get(field) != current[field]
    }
    if mismatches:
        raise BuildGenerationError(
            "task_identity_stale",
            "generation task identity 已过期，已拒绝继续",
            retryable=True,
            details={"mismatches": mismatches},
        )
    return dict(task_identity)


def _persist_wiki_task_identity(build, task_identity):
    if build is None or task_identity is None:
        return build
    build.base_generation_id = task_identity["base_generation_id"]
    build.structure_revision_id = task_identity["structure_revision_id"]
    build.structure_fingerprint = task_identity["structure_fingerprint"]
    build.pipeline_version = task_identity["pipeline_version"]
    build.source_fingerprints = list(task_identity["source_fingerprints"])
    build.inputs = {
        **(build.inputs or {}),
        "task_identity": dict(task_identity),
        "classification_root_id": task_identity["classification_root_id"],
    }
    build.save(
        update_fields=[
            "base_generation",
            "structure_revision",
            "structure_fingerprint",
            "pipeline_version",
            "source_fingerprints",
            "inputs",
            "updated_at",
        ]
    )
    return build


def _wiki_running_build_has_identity(build):
    if build is None:
        return False
    task_identity = (build.inputs or {}).get("task_identity")
    return bool(
        build.base_generation_id
        and build.structure_revision_id
        and build.structure_fingerprint
        and build.pipeline_version
        and isinstance(build.source_fingerprints, list)
        and isinstance(task_identity, dict)
        and all(field in task_identity for field in _WIKI_TASK_IDENTITY_FIELDS)
    )


def _fail_wiki_task_build(
    build,
    code,
    message,
    *,
    retryable=False,
    outcome="failed",
):
    if build is None:
        return None
    if build.status in {"success", "partial"}:
        return build
    code = getattr(code, "value", code)
    outcome = getattr(outcome, "value", outcome)
    build.stage = "failed"
    build.status = "failed"
    build.progress = 100
    build.errors = [f"{code}: {message}"]
    build.activation = {
        **(build.activation or {}),
        "outcome": outcome,
        "code": code,
        "retryable": bool(retryable),
    }
    build.save(
        update_fields=[
            "stage",
            "status",
            "progress",
            "errors",
            "activation",
            "updated_at",
        ]
    )
    return build


@shared_task(name="apps.opspilot.tasks.wiki_ingest_material_task", queue="opspilot_wiki")
def wiki_ingest_material_task(material_id, llm_model_id=None):
    """资料解析(异步):抽取文本 + 生成 AI 摘要。文件/网页解析较重(loader/OCR/LLM),不阻塞前台请求。"""
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.material_service import ingest_material

    material = Material.objects.filter(id=material_id).first()
    if not material:
        logger.error("wiki 解析任务: 资料不存在 id=%s", material_id)
        return None
    return ingest_material(material, llm_model_id=llm_model_id).id


def _material_pipeline_fingerprints(knowledge_base, material):
    """Return deterministic parse/build identities without reading large files."""

    import hashlib
    import json

    from apps.opspilot.services.wiki.build_generation_service import PIPELINE_VERSION, material_fingerprint

    source_marker = {
        "text": hashlib.sha256((material.text_content or "").encode("utf-8")).hexdigest(),
        "web": material.url or "",
        # 文件资料没有替换入口；文件字段名 + OCR 配置足以识别当前上传对象。
        "file": getattr(material.file, "name", "") or material.name,
    }.get(material.material_type, "")
    parse_payload = {
        "pipeline_version": "wiki-material-parse-v1",
        "material_type": material.material_type,
        "source_marker": source_marker,
        "ocr_enhance": bool(material.ocr_enhance),
        "vision_model_id": knowledge_base.vision_model_id,
    }
    parse_fingerprint = hashlib.sha256(
        json.dumps(
            parse_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    revision = knowledge_base.active_structure_revision
    build_payload = {
        "parse_fingerprint": parse_fingerprint,
        "source": material_fingerprint(material),
        "purpose_md": knowledge_base.purpose_md or "",
        "generation_rules": knowledge_base.generation_rules or {},
        "generation_language": knowledge_base.generation_language,
        "llm_model_id": knowledge_base.llm_model_id,
        "structure_revision_id": getattr(revision, "pk", None),
        "structure_fingerprint": getattr(revision, "fingerprint", ""),
        "classification_root_id": material.classification_root_id,
        "pipeline_version": PIPELINE_VERSION,
    }
    build_fingerprint = hashlib.sha256(
        json.dumps(
            build_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return parse_fingerprint, build_fingerprint


def _latest_successful_material_build(knowledge_base_id, material_id):
    from apps.opspilot.models import BuildRecord

    records = BuildRecord.objects.filter(
        knowledge_base_id=knowledge_base_id,
        trigger="material",
        status="success",
    ).order_by(
        "-id"
    )[:50]
    for record in records:
        if (record.inputs or {}).get("material_id") == material_id:
            return record
    return None


def _material_build_artifacts_are_active(knowledge_base, build_record):
    """A matching fingerprint may be reused only while its pages remain active."""

    from apps.opspilot.models import WikiGenerationPage

    page_ids = {int(page_id) for page_id in (build_record.affected_pages or []) if type(page_id) is int}
    if not page_ids:
        return True
    if not knowledge_base.active_generation_id:
        return False
    active_ids = set(
        WikiGenerationPage.objects.filter(
            generation_id=knowledge_base.active_generation_id,
            page_id__in=page_ids,
            page_status="active",
        ).values_list("page_id", flat=True)
    )
    return active_ids == page_ids


@shared_task(name="apps.opspilot.tasks.wiki_build_material_task", queue="opspilot_wiki")
def wiki_build_material_task(
    material_id,
    llm_model_id=None,
    operator="",
    classification_root_id=None,
    task_identity=None,
    ensure_parsed=False,
    source_status=None,
    build_record_id=None,
):
    """统一执行资料解析与 generation 构建，并持久化阶段性失败 key。"""

    from apps.opspilot.models import BuildRecord, Material
    from apps.opspilot.services.wiki.material_build_queue_service import MaterialBuildCancelled, ensure_running_material_build_record
    from apps.opspilot.services.wiki.material_service import ingest_material

    material = (
        Material.objects.select_related(
            "knowledge_base__active_structure_revision",
            "current_version",
            "classification_root",
        )
        .filter(id=material_id)
        .first()
    )
    if not material:
        logger.error("wiki 构建任务: 资料不存在 id=%s", material_id)
        return None

    initial_status = source_status or material.status
    # 尽早落/复用 running BuildRecord,避免状态已是构建中但列表无开始时间
    build = None
    if build_record_id:
        existing = BuildRecord.objects.filter(
            pk=build_record_id,
            knowledge_base_id=material.knowledge_base_id,
            trigger="material",
        ).first()
        if _discard_cancelled_material_build(existing, material.pk):
            return None
        if existing is not None and existing.status == "running":
            build = existing
    if build is None:
        build = ensure_running_material_build_record(
            knowledge_base_id=material.knowledge_base_id,
            material_id=material.pk,
            operator=operator,
            source_status=initial_status if isinstance(initial_status, str) else None,
            stage="preparing",
        )

    if ensure_parsed:
        parse_fingerprint, build_fingerprint = _material_pipeline_fingerprints(
            material.knowledge_base,
            material,
        )
        previous = _latest_successful_material_build(
            material.knowledge_base_id,
            material.pk,
        )
        previous_inputs = (previous.inputs or {}) if previous else {}
        if (
            initial_status == "built"
            and material.current_version_id
            and material.content_hash
            and previous_inputs.get("parse_fingerprint") == parse_fingerprint
            and previous_inputs.get("build_fingerprint") == build_fingerprint
            and _material_build_artifacts_are_active(
                material.knowledge_base,
                previous,
            )
        ):
            build.refresh_from_db()
            if _discard_cancelled_material_build(build, material.pk):
                return None
            build.inputs = {
                **(build.inputs or {}),
                "material_id": material.pk,
                "outcome": "skipped_unchanged",
                "parse_fingerprint": parse_fingerprint,
                "build_fingerprint": build_fingerprint,
            }
            build.stage = "done"
            build.status = "success"
            build.progress = 100
            build.counts = {"skipped_unchanged": 1}
            build.errors = []
            build.save(
                update_fields=[
                    "inputs",
                    "stage",
                    "status",
                    "progress",
                    "counts",
                    "errors",
                    "updated_at",
                ]
            )
            Material.objects.filter(pk=material.pk).update(
                status="built",
                error_message="",
            )
            return build.pk

        must_parse = (
            material.current_version_id is None
            or initial_status in {"pending", "updated", "parse_failed", "failed"}
            or (previous_inputs.get("parse_fingerprint") and previous_inputs.get("parse_fingerprint") != parse_fingerprint)
        )
        if must_parse:
            build.refresh_from_db()
            if _discard_cancelled_material_build(build, material.pk):
                return None
            Material.objects.filter(pk=material.pk).update(
                status="parsing",
                error_message="",
            )
            build.stage = "parsing"
            build.save(update_fields=["stage", "updated_at"])
            material.refresh_from_db()
            material = ingest_material(material, llm_model_id=llm_model_id)
            if material.status != "done":
                build.refresh_from_db()
                if _discard_cancelled_material_build(build, material.pk):
                    return None
                material.status = "parse_failed"
                material.save(update_fields=["status", "updated_at"])
                build.inputs = {
                    **(build.inputs or {}),
                    "material_id": material.pk,
                    "parse_fingerprint": parse_fingerprint,
                }
                build.stage = "parse_failed"
                build.status = "failed"
                build.progress = 100
                build.errors = [
                    {
                        "code": "material_parse_failed",
                        "message": material.error_message or "资料解析失败",
                    }
                ]
                build.save(
                    update_fields=[
                        "inputs",
                        "stage",
                        "status",
                        "progress",
                        "errors",
                        "updated_at",
                    ]
                )
                return build.pk
            material = Material.objects.select_related(
                "knowledge_base__active_structure_revision",
                "current_version",
                "classification_root",
            ).get(pk=material.pk)

    with transaction.atomic():
        locked_kb = _lock_wiki_generation_task(material.knowledge_base_id)
        build = BuildRecord.objects.select_for_update().get(pk=build.pk)
        if _discard_cancelled_material_build(build, material.pk):
            return None
        material = Material.objects.select_for_update().get(pk=material.pk)
        material.knowledge_base = locked_kb
        root_id = classification_root_id if classification_root_id is not None else material.classification_root_id
        if ensure_parsed and task_identity is None:
            identity = _freeze_wiki_task_identity(
                locked_kb,
                [material],
                classification_root_id=root_id,
            )
        else:
            identity = _resolve_wiki_task_identity(
                locked_kb,
                [material],
                classification_root_id=root_id,
                task_identity=task_identity,
            )
        parse_fingerprint, build_fingerprint = _material_pipeline_fingerprints(
            locked_kb,
            material,
        )
        material.status = "building"
        material.error_message = ""
        material.save(update_fields=["status", "error_message", "updated_at"])
        build.operator = operator or build.operator
        build.inputs = {
            **(build.inputs or {}),
            "material_id": material.pk,
            "parse_fingerprint": parse_fingerprint,
            "build_fingerprint": build_fingerprint,
        }
        build.stage = "generating"
        build.status = "running"
        build.save(update_fields=["operator", "inputs", "stage", "status", "updated_at"])
        _persist_wiki_task_identity(build, identity)

    from apps.opspilot.services.wiki.generation_material_build_service import build_material_with_generation
    from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded

    try:
        return build_material_with_generation(
            material,
            build,
            llm_model_id=llm_model_id,
            operator=operator,
            classification_root_id=root_id,
            frozen_identity=identity,
        ).id
    except MaterialBuildCancelled:
        logger.info("wiki material build discarded cancelled record=%s material=%s", build.pk, material.pk)
        return None
    except WikiBudgetExceeded as exc:
        logger.warning(
            "wiki 构建任务受预算限制停止 material=%s build=%s code=%s",
            material.pk,
            build.pk,
            exc.code,
        )
        build.refresh_from_db()
        if _discard_cancelled_material_build(build, material.pk):
            return None
        Material.objects.filter(pk=material.pk).update(
            status="build_failed",
            error_message=str(exc)[:2000],
        )
        return build.pk
    except Exception as exc:  # noqa: BLE001 - 业务失败由状态与 BuildRecord 表达
        logger.exception(
            "wiki 构建任务失败 material=%s build=%s",
            material.pk,
            build.pk,
        )
        build.refresh_from_db()
        if _discard_cancelled_material_build(build, material.pk):
            return None
        if build.status == "running":
            build.stage = "failed"
            build.status = "failed"
            build.progress = 100
            build.errors = [
                {
                    "code": getattr(exc, "code", "generation_failed"),
                    "message": str(exc),
                }
            ]
            build.save(
                update_fields=[
                    "stage",
                    "status",
                    "progress",
                    "errors",
                    "updated_at",
                ]
            )
        Material.objects.filter(pk=material.pk).update(
            status="build_failed",
            error_message=str(exc)[:2000],
        )
        return build.pk


@shared_task(name="apps.opspilot.tasks.wiki_propose_update_task", queue="opspilot_wiki")
def wiki_propose_update_task(
    material_id,
    llm_model_id=None,
    operator="",
    classification_root_id=None,
    task_identity=None,
):
    """使用固定治理快照执行资料更新。"""

    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.update_service import propose_update

    material = (
        Material.objects.select_related(
            "knowledge_base__active_structure_revision",
            "current_version",
            "classification_root",
        )
        .filter(id=material_id)
        .first()
    )
    if not material:
        logger.error("wiki 资料更新任务: 资料不存在 id=%s", material_id)
        return None
    with transaction.atomic():
        locked_kb = _lock_wiki_generation_task(material.knowledge_base_id)
        material = Material.objects.select_for_update().get(pk=material.pk)
        material.knowledge_base = locked_kb
        root_id = classification_root_id if classification_root_id is not None else material.classification_root_id
        identity = _resolve_wiki_task_identity(
            locked_kb,
            [material],
            classification_root_id=root_id,
            task_identity=task_identity,
        )

    return propose_update(
        material,
        llm_model_id=llm_model_id,
        operator=operator,
        classification_root_id=root_id,
        frozen_identity=identity,
    ).id


@shared_task(name="apps.opspilot.tasks.wiki_rebuild_kb_task", queue="opspilot_wiki")
def wiki_rebuild_kb_task(
    kb_id,
    llm_model_id=None,
    operator="",
    build_record_id=None,
    classification_root_id=None,
    task_identity=None,
):
    """Schema 变更全量重建；generation truth 状态只允许固定身份实现。"""

    from apps.opspilot.models import BuildRecord, Material, WikiKnowledgeBase
    from apps.opspilot.services.wiki import rebuild_service

    build = (
        BuildRecord.objects.filter(
            id=build_record_id,
            knowledge_base_id=kb_id,
        ).first()
        if build_record_id
        else None
    )
    kb = WikiKnowledgeBase.objects.select_related("active_structure_revision").filter(id=kb_id).first()
    if not kb:
        logger.error("wiki 重建任务: 知识库不存在 id=%s", kb_id)
        if build:
            _fail_wiki_task_build(
                build,
                "knowledge_base_not_found",
                "知识库不存在",
            )
        return None

    with transaction.atomic():
        kb = _lock_wiki_generation_task(kb.pk)
        if build is not None:
            build = BuildRecord.objects.select_for_update().get(pk=build.pk)
            if build.status in {"success", "partial"}:
                return build.pk
        build = build or rebuild_service.create_rebuild_record(kb, operator=operator)
        if build.status == "running" and build.stage != "queued" and not _wiki_running_build_has_identity(build):
            _fail_wiki_task_build(
                build,
                "running_task_identity_missing",
                "旧版运行中任务缺少固定 generation/structure/source identity",
            )
            return build.pk

        materials = list(Material.objects.filter(knowledge_base=kb).select_related("current_version").order_by("id"))
        persisted_identity = (build.inputs or {}).get("task_identity") if _wiki_running_build_has_identity(build) else None
        try:
            identity = _resolve_wiki_task_identity(
                kb,
                materials,
                classification_root_id=classification_root_id,
                task_identity=task_identity or persisted_identity,
            )
        except Exception as exc:
            retryable = bool(getattr(exc, "retryable", False))
            _fail_wiki_task_build(
                build,
                getattr(exc, "code", "task_identity_invalid"),
                str(exc),
                retryable=retryable,
                outcome="superseded" if retryable else "failed",
            )
            return build.pk
        _persist_wiki_task_identity(build, identity)

    runner = getattr(
        rebuild_service,
        "rebuild_knowledge_base_with_generation",
        None,
    )
    if runner is None:
        _fail_wiki_task_build(
            build,
            "generation_rebuild_pipeline_unavailable",
            "generation 全量重建实现尚未可用，拒绝原地重建",
        )
        return build.pk
    try:
        return runner(
            kb,
            llm_model_id=llm_model_id,
            operator=operator,
            build=build,
            classification_root_id=classification_root_id,
            frozen_identity=identity,
        ).id
    except Exception as exc:
        build.refresh_from_db()
        if build.status == "running":
            retryable = bool(getattr(exc, "retryable", False))
            _fail_wiki_task_build(
                build,
                getattr(exc, "code", "generation_rebuild_failed"),
                str(exc),
                retryable=retryable,
                outcome="superseded" if retryable else "failed",
            )
        raise


@shared_task(
    name="apps.opspilot.tasks.wiki_process_kb_material_builds_task",
    queue="opspilot_wiki",
    acks_late=True,
    reject_on_worker_lost=True,
)
def wiki_process_kb_material_builds_task(kb_id, operator=""):
    """按知识库串行消费资料构建队列。

    同 KB 至多一个活跃 runner；入队侧只 kick 本任务，避免每条资料各投一个长任务。
    acks_late 只保证 worker 死后消息可重投；不得凭 redelivered 抢仍新鲜的租约。
    进程中断后用 resume_wiki_material_builds；仅 stale 租约可被新任务接管。
    """
    from apps.opspilot.services.wiki.material_build_queue_service import process_kb_material_builds

    return process_kb_material_builds(int(kb_id), operator=operator or "")


@shared_task(name="apps.opspilot.tasks.wiki_batch_ingest_materials_task", queue="opspilot_wiki")
def wiki_batch_ingest_materials_task(material_ids, llm_model_id=None):
    """批量资料解析(异步):逐条摄取,汇总成功/失败统计。供 batch_create 端点或定时调度调用。

    单条失败不影响其他资料继续摄取。返回 {succeeded: [id], failed: [{material_id, error}]}。
    """
    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.material_service import ingest_material

    succeeded = []
    failed = []
    for mid in material_ids or []:
        material = Material.objects.filter(id=mid).first()
        if not material:
            failed.append({"material_id": mid, "error": "资料不存在"})
            continue
        try:
            ingest_material(material, llm_model_id=llm_model_id)
            succeeded.append(mid)
        except Exception as exc:  # noqa: BLE001 - 批量任务逐条隔离失败
            logger.exception("wiki 批量解析失败 material_id=%s", mid)
            failed.append({"material_id": mid, "error": str(exc)})
    return {"succeeded": succeeded, "failed": failed}


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    name="apps.opspilot.tasks.wiki_retry_markdown_import_task",
    queue="opspilot_wiki",
)
def wiki_retry_markdown_import_task(
    kb_id,
    build_record_id,
    content_b64,
    filename,
    operator="",
    preflight_token=None,
):
    """Retry a Markdown import through the generation-aware preflight contract."""
    from apps.opspilot.models import BuildRecord, WikiKnowledgeBase
    from apps.opspilot.services.wiki.markdown_import_governance_service import execute_markdown_import

    knowledge_base = WikiKnowledgeBase.objects.filter(pk=kb_id).first()
    if knowledge_base is None:
        return {
            "status": "failed",
            "code": "knowledge_base_not_found",
            "retryable": False,
            "error": f"知识库不存在 id={kb_id}",
        }

    with transaction.atomic():
        knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base.pk)
        build = BuildRecord.objects.select_for_update().filter(pk=build_record_id, knowledge_base=knowledge_base).first()
        try:
            content = base64.b64decode(content_b64)
        except Exception as error:
            logger.exception(
                "wiki markdown 重试:base64 解码失败 build_record=%s",
                build_record_id,
            )
            _fail_wiki_task_build(
                build,
                "markdown_import_payload_invalid",
                f"base64 decode failed: {error}",
            )
            return {
                "status": "failed",
                "code": "markdown_import_payload_invalid",
                "retryable": False,
                "error": f"base64 decode failed: {error}",
            }
        if not str(preflight_token or "").strip():
            _fail_wiki_task_build(
                build,
                "markdown_import_preflight_identity_incomplete",
                "Markdown 重试缺少完整单次预检身份",
            )
            return {
                "status": "failed",
                "code": "markdown_import_preflight_identity_incomplete",
                "retryable": False,
            }

    try:
        result = execute_markdown_import(
            knowledge_base,
            preflight_token,
            content,
            filename=filename,
            actor=operator,
            completion_build_record_id=build_record_id,
        )
    except Exception as error:
        logger.exception(
            "wiki markdown generation 重试失败 build_record=%s",
            build_record_id,
        )
        retryable = bool(getattr(error, "retryable", False))
        code = getattr(error, "code", "markdown_import_generation_failed")
        with transaction.atomic():
            WikiKnowledgeBase.objects.select_for_update().get(pk=kb_id)
            failed = BuildRecord.objects.select_for_update().filter(pk=build_record_id, knowledge_base_id=kb_id).first()
            _fail_wiki_task_build(
                failed,
                code,
                str(error),
                retryable=retryable,
                outcome="superseded" if retryable else "failed",
            )
        return {
            "status": "failed",
            "code": code,
            "retryable": retryable,
            "error": str(error),
        }

    return {"status": "success", **result}


@shared_task(name="apps.opspilot.tasks.wiki_refresh_web_materials_task", queue="opspilot_maintenance")
def wiki_refresh_web_materials_task():
    """网页资料定时刷新:按各站点自己的同步策略(Material.sync_policy)重新抓取并摄取,内容变化触发安全更新。

    同步策略已从知识库级别迁到「资料」级别(按站点单独配置)。本任务只处理 sync_policy.enabled 为真、
    且距上次刷新已超过 interval_hours 的 web 资料(未配置 interval_hours 则每次调度都刷新)。
    供 Celery beat 周期调度。返回 {checked, updated, skipped} 统计。
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.opspilot.models import Material
    from apps.opspilot.services.wiki.material_service import ingest_material
    from apps.opspilot.services.wiki.update_service import propose_update

    now = timezone.now()
    web_materials = Material.objects.filter(material_type="web")
    checked = updated = skipped = 0
    for material in web_materials:
        policy = material.sync_policy or {}
        if not policy.get("enabled"):
            skipped += 1
            continue
        interval = policy.get("interval_hours")
        if interval and material.updated_at and material.updated_at > now - timedelta(hours=int(interval)):
            skipped += 1
            continue
        checked += 1
        prev_hash = material.content_hash
        material = ingest_material(material, llm_model_id=material.knowledge_base.llm_model_id)
        if material.status == "done" and material.content_hash and material.content_hash != prev_hash:
            updated += 1
            try:
                propose_update(material, llm_model_id=material.knowledge_base.llm_model_id, operator="web_refresh")
            except Exception:
                logger.exception("wiki 网页刷新触发更新失败 material=%s", material.id)
    logger.info("wiki 网页资料刷新完成: checked=%s updated=%s skipped=%s", checked, updated, skipped)
    return {"checked": checked, "updated": updated, "skipped": skipped}
