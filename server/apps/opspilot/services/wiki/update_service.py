"""资料更新的安全编排：自动维护确定性结果，仅将真实知识冲突交给用户决策。

调用前提:material 已完成"重新摄取"(text_content/ai_summary/版本已更新)。
页面正文的"提议内容"由 generator(page, material) 产出(默认走 LLM,可注入以便测试)。
"""

import logging

from django.db import transaction
from django.utils import timezone

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, LLMModel, Material, MaterialVersion, PageEvidence, WikiKnowledgeBase
from apps.opspilot.services.wiki import decision_service
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.material_service import load_parsed_markdown

logger = logging.getLogger("opspilot")


def affected_pages(material):
    """返回引用了该资料的有效页面。"""
    page_ids = list(PageEvidence.objects.filter(material=material).values_list("page_id", flat=True).distinct())
    return list(KnowledgePage.objects.filter(id__in=page_ids, status="active").order_by("id"))


def _material_evidence_page_ids(material_id):
    return list(PageEvidence.objects.filter(material_id=material_id).values_list("page_id", flat=True).distinct().order_by("page_id"))


def _material_evidence_pages(material, *, for_update=False):
    page_ids = _material_evidence_page_ids(material.id)
    pages = KnowledgePage.objects.filter(knowledge_base_id=material.knowledge_base_id, id__in=page_ids).order_by("id")
    if for_update:
        pages = pages.select_for_update()
    return list(pages)


def _page_impact_payload(page, reason):
    return {
        "id": page.id,
        "title": page.title,
        "page_type": page.page_type,
        "status": page.status,
        "reason": reason,
    }


def _version_impact_payload(version):
    if not version:
        return None
    return {
        "id": version.id,
        "content_hash": version.content_hash,
        "content_locator": version.content_locator,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def preview_material_deletion(material):
    """预览物理删除影响；归档页面可恢复，但被删资料来源不可恢复。"""
    pages = _material_evidence_pages(material)
    page_ids = [page.id for page in pages]
    protected_page_ids = set(
        PageEvidence.objects.filter(page_id__in=page_ids).exclude(material=material).values_list("page_id", flat=True).distinct()
    )
    active_pages = [page for page in pages if page.status == "active"]
    archived_pages = [page for page in pages if page.status == "archived"]
    will_lose_reason = "此页面唯一来源,删除后会变 source_invalid"
    shared_reason = "此页面共享来源,删除后来源失效但页面保留"
    archived_reason = "页面仍保持归档且可恢复，但被删除的资料来源将永久失去"
    inactive_reason = "页面保持当前状态，但被删除的资料来源将永久失去"

    def impact_reason(page):
        if page.status == "archived":
            return archived_reason
        if page.status != "active":
            return inactive_reason
        return shared_reason if page.id in protected_page_ids else will_lose_reason

    affected = [_page_impact_payload(page, impact_reason(page)) for page in pages]
    will_be_source_invalid = [_page_impact_payload(page, will_lose_reason) for page in active_pages if page.id not in protected_page_ids]
    shared_source_protected = [_page_impact_payload(page, shared_reason) for page in active_pages if page.id in protected_page_ids]
    archived_recoverable = [_page_impact_payload(page, archived_reason) for page in archived_pages]
    return {
        "material_id": material.id,
        "material_name": material.name,
        "affected_count": len(affected),
        "will_be_source_invalid_count": len(will_be_source_invalid),
        "shared_source_protected_count": len(shared_source_protected),
        "archived_recoverable_count": len(archived_recoverable),
        "affected_pages": affected,
        "will_be_source_invalid": will_be_source_invalid,
        "shared_source_protected": shared_source_protected,
        "archived_recoverable": archived_recoverable,
    }


def preview_material_update(material):
    """预览资料更新影响,不调用 LLM、不生成候选版本。"""
    pages = affected_pages(material)
    versions = list(MaterialVersion.objects.filter(material=material).order_by("-id")[:2])
    latest = versions[0] if versions else None
    previous = versions[1] if len(versions) > 1 else None
    update_reason = "资料更新后将自动重新评估；仅知识结论冲突时需要人工选择"
    affected = [_page_impact_payload(page, update_reason) for page in pages]
    content_changed = bool(
        material.status == "updated"
        or (latest and previous and latest.content_hash and previous.content_hash and latest.content_hash != previous.content_hash)
    )
    return {
        "material_id": material.id,
        "material_name": material.name,
        "material_status": material.status,
        "content_hash": material.content_hash,
        "content_changed": content_changed,
        "latest_version": _version_impact_payload(latest),
        "previous_version": _version_impact_payload(previous),
        "affected_count": len(affected),
        "pending_review_count": 0,
        "affected_pages": affected,
        "pending_review_pages": [],
    }


@transaction.atomic
def apply_material_update(page, new_body, material=None, build_record=None, operator=""):
    """对单个页面编排资料更新决策，返回 (action, check_or_trace)。

    完整签名命中旧规则时自动回放；正文未变直接 unchanged；其余才创建候选。
    """
    if material is None:
        raise ValueError("material context is required")
    from apps.opspilot.services.wiki.build_service import resolve_knowledge_conflict

    action, decision_trace = resolve_knowledge_conflict(
        page,
        material,
        build_record,
        new_body,
        operator=operator,
        check_type="material_update",
        reason="资料更新,需人工确认后生效",
        related={
            "pages": [page.id],
            "materials": [material.id] if material is not None else [],
        },
    )
    if action == "pending_review":
        return action, CheckItem.objects.get(pk=decision_trace["check_id"])
    return action, decision_trace


def _default_generator(page, material, llm_model_id):
    """默认正文生成:用更新后的资料为该页面重写正文(LLM)。无模型则返回空(跳过)。"""
    if not llm_model_id:
        return ""
    text = (load_parsed_markdown(material) or material.ai_summary or material.text_content or "").strip()
    if not text:
        return ""
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        current = page.current_version.body if page.current_version_id else ""
        prompt = "资料已更新,请据此重写指定知识页面的正文,保持标题主题不变,只输出 markdown 正文。\n\n" f"# 页面标题\n{page.title}\n\n# 现有正文\n{current}\n\n# 更新后的资料\n{text}\n"
        request = BasicLLMRequest(
            openai_api_base=llm.openai_api_base,
            openai_api_key=llm.openai_api_key,
            model=llm.model_name,
            temperature=0.2,
            user_message=prompt,
        )
        return (LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}]) or "").strip()
    except Exception:
        logger.exception("wiki 资料更新重写失败 page=%s", page.id)
        return ""


_MATERIAL_DELETE_METRIC_KEYS = (
    "relations",
    "indexed_pages",
    "indexed_chunks",
    "cleared_pages",
    "auto_resolved",
    "pruned_checks",
    "pruned_build_records",
)


def _combine_material_delete_stage(invalidated_stage, shared_stage):
    components = {
        name: dict(stage)
        for name, stage in (
            ("invalidated", invalidated_stage),
            ("shared", shared_stage),
        )
        if isinstance(stage, dict)
    }
    if len(components) == 1:
        return dict(next(iter(components.values())))
    statuses = {stage.get("status") for stage in components.values()}
    status = "failed" if "failed" in statuses else "success" if "success" in statuses else "skipped"
    result = {
        "status": status,
        "count": sum(stage.get("count", 0) for stage in components.values()),
        "components": components,
    }
    errors = [stage.get("error") for stage in components.values() if stage.get("error")]
    if errors:
        result["error"] = "; ".join(errors)
    return result


def _combine_material_delete_maintenance(
    invalidated_maintenance,
    shared_maintenance,
    invalidated_page_ids,
    shared_page_ids,
    *,
    event="material_delete",
):
    """汇总失效页清理与共享来源页重建，并保留各自可重试上下文。"""
    invalidated_maintenance = dict(invalidated_maintenance or {})
    shared_maintenance = dict(shared_maintenance or {})
    invalidated_stages = invalidated_maintenance.get("stages") if isinstance(invalidated_maintenance.get("stages"), dict) else {}
    shared_stages = shared_maintenance.get("stages") if isinstance(shared_maintenance.get("stages"), dict) else {}
    stages = {
        stage: _combine_material_delete_stage(
            invalidated_stages.get(stage),
            shared_stages.get(stage),
        )
        for stage in dict.fromkeys([*invalidated_stages, *shared_stages])
    }
    maintenance_items = [item for item in (invalidated_maintenance, shared_maintenance) if item]
    maintenance_statuses = {item.get("status") for item in maintenance_items}
    has_failure = bool({"partial", "failed"}.intersection(maintenance_statuses)) or any(stage.get("status") == "failed" for stage in stages.values())
    status = "partial" if has_failure else "pending" if {"pending", "running"}.intersection(maintenance_statuses) else "success"
    result = {
        "status": status,
        "event": event,
        "affected_page_ids": list(dict.fromkeys([*invalidated_page_ids, *shared_page_ids])),
        "stages": stages,
    }
    if invalidated_maintenance:
        result["invalidated"] = invalidated_maintenance
    if shared_maintenance:
        result["shared"] = shared_maintenance
    for key in _MATERIAL_DELETE_METRIC_KEYS:
        values = [item.get(key) for item in maintenance_items if isinstance(item.get(key), (int, float))]
        if values:
            result[key] = sum(values)
    return result


def _related_keys(value):
    if isinstance(value, (list, tuple, set)):
        values = value
    elif value in (None, ""):
        values = []
    else:
        values = [value]
    return {str(item) for item in values if item not in (None, "")}


def _check_material_keys(check):
    """Return every frozen material id that can invalidate this decision."""
    related = check.related if isinstance(check.related, dict) else {}
    keys = set(_related_keys(related.get("materials")))
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    for participant in context.get("participants") or []:
        if isinstance(participant, dict):
            keys.update(_related_keys(participant.get("material_id")))
    incoming = context.get("incoming")
    if isinstance(incoming, dict):
        keys.update(_related_keys(incoming.get("material_id")))
    return keys


def _auto_resolve_material_deletion_checks(
    knowledge_base,
    *,
    material_id,
    invalidated_page_ids,
    checks=None,
):
    """关闭删除资料或页面失效后已无决策意义的检查，并回算来源构建待审数。"""
    from apps.opspilot.services.wiki.check_service import _recount_pending_review

    material_key = str(material_id)
    invalidated_page_keys = {str(page_id) for page_id in invalidated_page_ids}
    resolved = 0
    if checks is None:
        checks = CheckItem.objects.select_for_update().filter(knowledge_base=knowledge_base, status="open").order_by("id")
    for check in checks:
        if check.status != "open":
            continue
        related = check.related if isinstance(check.related, dict) else {}
        material_obsolete = material_key in _check_material_keys(check)
        invalidated_page_obsolete = bool(invalidated_page_keys.intersection(_related_keys(related.get("pages"))))
        if not material_obsolete and not invalidated_page_obsolete:
            continue
        related = dict(related)
        related["resolution"] = {
            "action": "automatic_maintenance",
            "reason": "material_deleted",
            "operator": "system",
            "processed_at": timezone.now().isoformat(),
        }
        check.related = related
        check.status = "auto_resolved"
        check.suggested_actions = []
        check.updated_by = "system"
        check.save(update_fields=["related", "status", "suggested_actions", "updated_by", "updated_at"])
        _recount_pending_review(check)
        resolved += 1
    return resolved


def _pending_material_delete_maintenance(page_ids, event):
    return {
        "status": "partial",
        "event": event,
        "affected_page_ids": list(page_ids),
        "stages": {},
    }


def _run_material_delete_cascade(knowledge_base, page_ids, event):
    page_ids = list(page_ids)
    if not page_ids:
        return {}
    try:
        return cascade(knowledge_base, page_ids, event)
    except Exception as exc:
        logger.exception(
            "wiki 资料删除级联维护异常 kb=%s event=%s",
            knowledge_base.id,
            event,
        )
        error = str(exc)
        return {
            "status": "partial",
            "event": event,
            "affected_page_ids": page_ids,
            "stages": {"cascade": {"status": "failed", "error": error}},
            "error": error,
        }


def _finalize_material_delete_maintenance(
    build,
    knowledge_base,
    maintenance_prune_page_ids,
    shared_page_ids,
):
    """Run derived maintenance only after the deleting transaction commits."""
    invalidated_maintenance = _run_material_delete_cascade(
        knowledge_base,
        maintenance_prune_page_ids,
        "material_delete",
    )
    shared_maintenance = _run_material_delete_cascade(
        knowledge_base,
        shared_page_ids,
        "build",
    )
    maintenance = _combine_material_delete_maintenance(
        invalidated_maintenance,
        shared_maintenance,
        maintenance_prune_page_ids,
        shared_page_ids,
    )
    build.maintenance = maintenance
    build.errors = _maintenance_errors(maintenance)
    build.stage = "done"
    build.status = maintenance.get("status", "success")
    build.progress = 100
    build.save(
        update_fields=[
            "maintenance",
            "errors",
            "stage",
            "status",
            "progress",
            "updated_at",
        ]
    )


def handle_material_deletion(material, operator=""):
    """短事务提交物理删除，再在事务外 best-effort 维护派生结构。"""
    kb = material.knowledge_base
    knowledge_base_id = material.knowledge_base_id
    material_id = material.id
    frozen_page_ids = _material_evidence_page_ids(material_id)

    with transaction.atomic():
        kb = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
        locked_checks = list(CheckItem.objects.select_for_update().filter(knowledge_base_id=knowledge_base_id).order_by("id"))
        pages = list(KnowledgePage.objects.select_for_update().filter(knowledge_base_id=knowledge_base_id, id__in=frozen_page_ids).order_by("id"))
        material = Material.objects.select_for_update().get(
            pk=material_id,
            knowledge_base_id=knowledge_base_id,
        )
        current_page_ids = _material_evidence_page_ids(material_id)
        if current_page_ids != frozen_page_ids:
            raise RuntimeError("资料关联页面已并发变化，请重试删除")
        material_name = material.name
        rules_revoked = decision_service.revoke_rules_for_materials(
            [material],
            reason="资料已物理删除",
            operator=operator,
        )
        all_evidence_page_ids = [page.id for page in pages]
        active_pages = [page for page in pages if page.status == "active"]
        archived_pages = [page for page in pages if page.status == "archived"]
        inactive_pages = [page for page in pages if page.status not in {"active", "archived"}]
        build = BuildRecord.objects.create(
            knowledge_base=kb,
            trigger="material_delete",
            operator=operator,
            inputs={
                "material_id": material_id,
                "material_name": material_name,
                "all_evidence_page_ids": all_evidence_page_ids,
            },
            stage="done",
            status="partial",
            progress=100,
        )

        material.delete()

        remaining_page_ids = set(PageEvidence.objects.filter(page_id__in=all_evidence_page_ids).values_list("page_id", flat=True).distinct())
        invalidated_pages = [page for page in active_pages if page.id not in remaining_page_ids]
        shared_pages = [page for page in active_pages if page.id in remaining_page_ids]
        invalidated_page_ids = [page.id for page in invalidated_pages]
        shared_page_ids = [page.id for page in shared_pages]
        archived_recoverable_page_ids = [page.id for page in archived_pages]
        inactive_source_loss_page_ids = [page.id for page in inactive_pages]
        shared_page_id_set = set(shared_page_ids)
        # 归档/既有失效页保持状态，但同样进入 material_delete 维护以清理残留关系与索引。
        maintenance_prune_page_ids = [page.id for page in pages if page.id not in shared_page_id_set]
        for page in invalidated_pages:
            page.status = "source_invalid"
            page.save(update_fields=["status", "updated_at"])

        checks_auto_resolved = _auto_resolve_material_deletion_checks(
            kb,
            material_id=material_id,
            invalidated_page_ids=invalidated_page_ids,
            checks=locked_checks,
        )
        pending_maintenance = _combine_material_delete_maintenance(
            (
                _pending_material_delete_maintenance(
                    maintenance_prune_page_ids,
                    "material_delete",
                )
                if maintenance_prune_page_ids
                else {}
            ),
            (_pending_material_delete_maintenance(shared_page_ids, "build") if shared_page_ids else {}),
            maintenance_prune_page_ids,
            shared_page_ids,
        )
        build.inputs = {
            **(build.inputs or {}),
            "invalidated_page_ids": invalidated_page_ids,
            "shared_page_ids": shared_page_ids,
            "archived_recoverable_page_ids": archived_recoverable_page_ids,
            "inactive_source_loss_page_ids": inactive_source_loss_page_ids,
            "maintenance_prune_page_ids": maintenance_prune_page_ids,
            **({"archived_source_loss": "页面可恢复，但被删除的资料来源不可恢复"} if archived_recoverable_page_ids else {}),
            "rules_revoked": rules_revoked,
            "checks_auto_resolved": checks_auto_resolved,
        }
        counts = {
            "new": 0,
            "updated": len(invalidated_page_ids),
            "unchanged": len(shared_page_ids),
            "pending_review": 0,
        }
        if archived_recoverable_page_ids:
            counts["archived_recoverable"] = len(archived_recoverable_page_ids)
        if inactive_source_loss_page_ids:
            counts["inactive_source_loss"] = len(inactive_source_loss_page_ids)
        build.counts = counts
        build.affected_pages = all_evidence_page_ids
        build.maintenance = pending_maintenance
        has_maintenance = bool(maintenance_prune_page_ids or shared_page_ids)
        build.stage = "done"
        build.status = "partial" if has_maintenance else "success"
        build.progress = 100
        build.save(
            update_fields=[
                "inputs",
                "counts",
                "affected_pages",
                "maintenance",
                "stage",
                "status",
                "progress",
                "updated_at",
            ]
        )

        if has_maintenance:
            transaction.on_commit(
                lambda: _finalize_material_delete_maintenance(
                    build,
                    kb,
                    maintenance_prune_page_ids,
                    shared_page_ids,
                )
            )
    return build


def _maintenance_errors(maintenance):
    errors = []

    def collect(value):
        if isinstance(value, dict):
            error = value.get("error")
            if error and str(error) not in errors:
                errors.append(str(error))
            for key, nested in value.items():
                if key == "error":
                    continue
                if isinstance(nested, (dict, list, tuple)):
                    collect(nested)
        elif isinstance(value, (list, tuple)):
            for item in value:
                collect(item)

    collect(maintenance)
    return [error for error in errors if not (";" in error and all(part.strip() in errors for part in error.split(";") if part.strip()))]


def _run_update_cascade(knowledge_base, affected_page_ids):
    try:
        return cascade(knowledge_base, affected_page_ids, "material_update")
    except Exception as exc:
        logger.exception("wiki 资料更新级联维护异常 kb=%s", knowledge_base.id)
        error = str(exc)
        return {
            "status": "partial",
            "event": "material_update",
            "affected_page_ids": list(affected_page_ids),
            "stages": {"cascade": {"status": "failed", "error": error}},
            "error": error,
        }


def propose_update(material, llm_model_id=None, operator="", generator=None):
    """资料更新后,对受影响页面执行安全合并,返回 BuildRecord。"""
    kb = material.knowledge_base
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        operator=operator,
        inputs={
            "material_id": material.id,
            "material_name": material.name,
            "source_trace": {"page_actions": []},
        },
        stage="generating",
        status="running",
    )
    try:
        gen = generator or (lambda p, m: _default_generator(p, m, llm_model_id))
        counts = {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 0}
        affected = []
        cascade_ids = []
        maintenance = {}
        source_trace = {"page_actions": []}
        for page in affected_pages(material):
            new_body = gen(page, material)
            if not (new_body or "").strip():
                continue
            action, result = apply_material_update(
                page,
                new_body,
                material=material,
                build_record=build,
                operator=operator,
            )
            counts[action] += 1
            page_trace = {
                "page_id": page.id,
                "title": page.title,
                "page_type": page.page_type,
                "action": action,
            }
            if isinstance(result, dict):
                page_trace.update(result)
            source_trace["page_actions"].append(page_trace)
            affected.append(page.id)
            if action != "pending_review":
                cascade_ids.append(page.id)
        if cascade_ids:
            maintenance = _run_update_cascade(kb, cascade_ids)
        build.counts = counts
        build.affected_pages = affected
        build.inputs = {**(build.inputs or {}), "source_trace": source_trace}
        build.maintenance = maintenance
        build.errors = _maintenance_errors(maintenance)
        build.stage = "done"
        build.status = "partial" if maintenance.get("status") in {"partial", "failed"} else "success"
        build.progress = 100
        build.save(
            update_fields=[
                "counts",
                "affected_pages",
                "inputs",
                "maintenance",
                "errors",
                "stage",
                "status",
                "progress",
                "updated_at",
            ]
        )
        return build
    except Exception as exc:
        logger.exception("wiki 资料更新失败 material=%s", material.id)
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        raise
