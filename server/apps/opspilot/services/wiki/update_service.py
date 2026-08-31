"""资料更新的安全编排：自动维护确定性结果，仅将真实知识冲突交给用户决策。

调用前提:material 已完成"重新摄取"(text_content/ai_summary/版本已更新)。
页面正文的"提议内容"由 generator(page, material) 产出(默认走 LLM,可注入以便测试)。
"""

from django.db import transaction
from django.utils import timezone

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import (
    BuildRecord,
    CheckItem,
    KnowledgePage,
    Material,
    MaterialVersion,
    PageEvidence,
    WikiGenerationPage,
    WikiKnowledgeBase,
    WikiStructureRevision,
)
from apps.opspilot.services.wiki import decision_service
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.maintenance_errors import humanize_maintenance_error
from apps.opspilot.services.wiki.material_service import load_parsed_markdown
from apps.opspilot.services.llm_context_budget import window_tokens_for_model_id
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, new_material_call_budget


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


def _default_generator(
    page,
    material,
    llm_model_id,
    *,
    budget,
    current_body=None,
    title=None,
):
    """Rewrite one affected page inside the material-scoped hard budget."""

    if not llm_model_id:
        return ""
    text = (load_parsed_markdown(material) or material.ai_summary or material.text_content or "").strip()
    if not text:
        return ""
    from apps.opspilot.services.wiki.build_service import _invoke_llm, _page_type_body_guidance

    current = current_body if current_body is not None else (page.current_version.body if page.current_version_id else "")
    display_title = title if title is not None else page.title
    page_type = page.page_type or "concept"
    prompt = (
        "资料已更新,请据此重写指定知识页面的正文,保持标题主题和页面类型不变,只输出 markdown 正文。\n"
        "不得把来源摘要、实体、概念、对比或综合页退化成同一种通用摘要。\n\n"
        f"# 页面标题\n{display_title}\n\n"
        f"# 页面类型\n{page_type}\n\n"
        f"# 写作契约\n{_page_type_body_guidance(page_type)}\n\n"
        f"# 现有正文\n{current}\n\n# 更新后的资料\n{text}\n"
    )
    return str(
        _invoke_llm(
            llm_model_id,
            prompt,
            budget=budget,
            stage=f"material_update_page:{page.pk}",
            output_reserve=6000,
        )
        or ""
    ).strip()


_GENERATION_IDENTITY_FIELDS = (
    "base_generation_id",
    "structure_revision_id",
    "structure_version",
    "structure_fingerprint",
    "pipeline_version",
    "source_fingerprints",
    "classification_root_id",
)


def _validate_frozen_generation_identity(
    knowledge_base,
    frozen_identity,
    *,
    source_fingerprints,
    classification_root_id=None,
    context=None,
):
    from apps.opspilot.services.wiki.build_generation_service import PIPELINE_VERSION, BuildGenerationError

    incomplete_sources = [
        fingerprint
        for fingerprint in source_fingerprints
        if not fingerprint.get("material_version_id")
        or not str(fingerprint.get("content_hash") or "").strip()
        or not str(fingerprint.get("source_identity") or "").strip()
    ]
    if incomplete_sources:
        raise BuildGenerationError(
            "source_identity_incomplete",
            "generation 更新任务缺少完整资料来源身份",
            details={"source_fingerprints": incomplete_sources},
        )
    if frozen_identity is None:
        return
    if not isinstance(frozen_identity, dict):
        raise ValueError("frozen_identity 必须为对象")
    missing = [field for field in _GENERATION_IDENTITY_FIELDS if field not in frozen_identity]
    if missing:
        raise ValueError(f"generation task identity 缺少字段: {', '.join(missing)}")
    revision = knowledge_base.active_structure_revision
    expected = {
        "base_generation_id": context.base_generation_id if context is not None else knowledge_base.active_generation_id,
        "structure_revision_id": context.structure_revision_id if context is not None else getattr(revision, "pk", None),
        "structure_version": context.structure_version if context is not None else getattr(revision, "revision_no", None),
        "structure_fingerprint": context.structure_fingerprint if context is not None else getattr(revision, "fingerprint", ""),
        "pipeline_version": context.pipeline_version if context is not None else PIPELINE_VERSION,
        "source_fingerprints": list(source_fingerprints),
        "classification_root_id": classification_root_id,
    }
    mismatches = {
        field: {"expected": expected[field], "actual": frozen_identity.get(field)}
        for field in _GENERATION_IDENTITY_FIELDS
        if frozen_identity.get(field) != expected[field]
    }
    if mismatches:
        raise BuildGenerationError(
            "frozen_generation_identity_mismatch",
            "任务固定身份与当前 generation 上下文不一致",
            retryable=True,
            details={"mismatches": mismatches},
        )


def _base_generation_members_for_material(context, material):
    page_ids = _material_evidence_page_ids(material.pk)
    if not page_ids:
        return []
    return list(
        WikiGenerationPage.objects.filter(
            generation_id=context.base_generation_id,
            page_id__in=page_ids,
            page_status="active",
        )
        .select_related("page", "page_version", "directory")
        .order_by("page_id")
    )


def _generation_body_candidate(page, member, material, build, context, candidate_body, operator):
    from apps.opspilot.services.wiki.build_generation_service import BuildGenerationError, material_fingerprint
    from apps.opspilot.services.wiki.candidate_adapter_contract import CandidateParticipant, DjangoKnowledgeCandidateAdapter, body_conflict_key
    from apps.opspilot.services.wiki.decision_service import build_participants_from_page_evidence

    participants = []
    for item in build_participants_from_page_evidence(
        page,
        incoming_snapshot=material_fingerprint(material),
    ):
        material_id = item.get("material_id")
        content_hash = str(item.get("content_hash") or "").strip()
        if type(material_id) is not int or material_id <= 0 or not content_hash:
            raise BuildGenerationError(
                "source_identity_incomplete",
                "human/mixed 正文候选缺少完整来源身份",
                details={"page_id": page.pk, "participant": item},
            )
        participants.append(
            CandidateParticipant(
                material_id=material_id,
                content_hash=content_hash,
            )
        )
    conflict = body_conflict_key(
        knowledge_base_id=page.knowledge_base_id,
        page_id=page.pk,
        locked_current_version_id=member.page_version_id,
        content_contract_fingerprint=context.structure_fingerprint,
        participants=participants,
    )
    return DjangoKnowledgeCandidateAdapter().create_body_conflict(
        conflict_key=conflict,
        candidate_body=candidate_body,
        build_record_id=build.pk,
        generation_id=context.candidate_generation_id,
        reason="资料更新产生了不同知识结论，保持当前正文并等待人工决策",
        created_by=operator or "",
    )


def _propose_update_generation(
    material,
    *,
    llm_model_id=None,
    operator="",
    generator=None,
    classification_root_id=None,
    frozen_identity=None,
):
    from apps.opspilot.services.wiki.build_generation_service import (
        BuildGenerationError,
        begin_build_generation,
        fail_build_generation,
        finalize_build_generation,
        material_fingerprint,
        stage_ai_page,
    )
    from apps.opspilot.services.wiki.build_service import _canonical_title, _invoke_llm
    from apps.opspilot.services.wiki.directory_assignment_service import resolve_page_directory
    from apps.opspilot.services.wiki.generation_wikilink_enrichment_service import apply_generation_wikilink_trace, enrich_generation_pages_wikilinks
    from apps.opspilot.services.wiki.title_service import title_alias_terms_for_enrichment as _title_alias_terms_for_enrichment

    kb = WikiKnowledgeBase.objects.select_related("active_structure_revision").get(pk=material.knowledge_base_id)
    material = Material.objects.select_related("current_version", "knowledge_base").get(pk=material.pk, knowledge_base=kb)
    frozen_material_fingerprint = material_fingerprint(material)
    source_fingerprints = [frozen_material_fingerprint]
    if frozen_identity is not None:
        classification_root_id = frozen_identity.get("classification_root_id")
    _validate_frozen_generation_identity(
        kb,
        frozen_identity,
        source_fingerprints=source_fingerprints,
        classification_root_id=classification_root_id,
    )
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        operator=operator,
        inputs={
            "material_id": material.pk,
            "material_name": material.name,
            "classification_root_id": classification_root_id,
            "source_trace": {"page_actions": []},
            **({"task_identity": dict(frozen_identity)} if frozen_identity is not None else {}),
        },
        stage="generating",
        status="running",
    )
    budget = new_material_call_budget(material.pk, window_tokens=window_tokens_for_model_id(llm_model_id))
    context = None
    try:
        context = begin_build_generation(
            kb,
            build,
            source_fingerprints=source_fingerprints,
            operator=operator,
        )
        _validate_frozen_generation_identity(
            kb,
            frozen_identity,
            source_fingerprints=source_fingerprints,
            classification_root_id=classification_root_id,
            context=context,
        )
        revision = WikiStructureRevision.objects.get(pk=context.structure_revision_id, knowledge_base=kb)
        counts = {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 0}
        affected = []
        page_actions = []
        directory_trace = []
        evidence_records = []
        pending_material_ids_by_page = {}
        enrichment_page_ids = set()
        source_trace = {"page_actions": []}
        for member in _base_generation_members_for_material(context, material):
            page = member.page
            display = dict(member.page_display_snapshot or {})
            title = display.get("title") or page.title
            page_type = display.get("page_type") or page.page_type or "concept"
            tags = list(display.get("tags") or [])
            contribution = display.get("contribution") or page.contribution
            current_body = member.page_version.body or ""
            new_body = (
                generator(page, material)
                if generator is not None
                else _default_generator(
                    page,
                    material,
                    llm_model_id,
                    budget=budget,
                    current_body=current_body,
                    title=title,
                )
            )
            new_body = (new_body or "").strip()
            if not new_body:
                continue

            if contribution == "ai":
                assignment = resolve_page_directory(
                    knowledge_base=kb,
                    structure_revision=revision,
                    page_type=page_type,
                    assignment_mode=member.assignment_mode,
                    current_directory=member.directory,
                    suggested_key=member.directory_key_snapshot,
                    suggestion_source="historical_link",
                    classification_root_id=classification_root_id,
                    suggestion_reason="资料更新沿用固定 generation 的目录上下文",
                )
                staged = stage_ai_page(
                    context,
                    title=title,
                    page_type=page_type,
                    tags=tags,
                    body=new_body,
                    directory_id=assignment.directory.pk,
                    assignment_mode=assignment.assignment_mode,
                    build_record=build,
                    operator=operator,
                    update_method="material_update",
                    change_type="material_update",
                    body_strategy="replace",
                )
                enrichment_page_ids.add(staged.page_id)
                action = "updated" if staged.action == "update" else "unchanged"
                counts[action] += 1
                action_item = {
                    "page_id": staged.page_id,
                    "page_version_id": staged.page_version_id,
                    "title": staged.title,
                    "action": staged.action,
                    "material_id": material.pk,
                    "directory_id": staged.directory_id,
                    "assignment_mode": staged.assignment_mode,
                }
                directory_item = assignment.as_build_trace()
                directory_item.update(
                    {
                        "page_id": staged.page_id,
                        "title": staged.title,
                        "material_id": material.pk,
                    }
                )
                directory_trace.append(directory_item)
                pending_material_ids_by_page.setdefault(staged.page_id, set()).add(material.pk)
                evidence_records.append(
                    {
                        "page_id": staged.page_id,
                        "material": material,
                        "material_version": material.current_version,
                        "locator": "",
                    }
                )
            elif new_body == current_body.strip():
                action = "unchanged"
                counts[action] += 1
                action_item = {
                    "page_id": page.pk,
                    "page_version_id": member.page_version_id,
                    "title": title,
                    "action": action,
                    "material_id": material.pk,
                    "contribution": contribution,
                }
                pending_material_ids_by_page.setdefault(page.pk, set()).add(material.pk)
                evidence_records.append(
                    {
                        "page_id": page.pk,
                        "material": material,
                        "material_version": material.current_version,
                        "locator": "",
                    }
                )
            else:
                handle = _generation_body_candidate(
                    page,
                    member,
                    material,
                    build,
                    context,
                    new_body,
                    operator,
                )
                action = "pending_review"
                counts[action] += 1
                action_item = {
                    "page_id": page.pk,
                    "page_version_id": member.page_version_id,
                    "candidate_version_id": handle.candidate_version_id,
                    "check_id": handle.check_id,
                    "title": title,
                    "action": "candidate",
                    "material_id": material.pk,
                    "contribution": contribution,
                    "candidate_created": handle.created,
                    "blocks_generation_activation": handle.blocks_generation_activation,
                }

            affected.append(page.pk)
            page_actions.append(action_item)
            source_trace["page_actions"].append(action_item)

        enrichment_results = enrich_generation_pages_wikilinks(
            context.candidate_generation_id,
            enrichment_page_ids,
            None,
            _invoke_llm,
            build_record=build,
            operator=operator,
            canonicalize=lambda value: _canonical_title(kb, value),
            alias_terms_resolver=lambda value: _title_alias_terms_for_enrichment(
                kb,
                value,
            ),
        )
        apply_generation_wikilink_trace(page_actions, enrichment_results)
        apply_generation_wikilink_trace(
            source_trace["page_actions"],
            enrichment_results,
        )

        published_build = None

        def activation_hook(_candidate, locked_kb, relation_result):
            nonlocal published_build
            locked_build = BuildRecord.objects.select_for_update().get(
                pk=build.pk,
                knowledge_base=locked_kb,
            )
            locked_material = Material.objects.select_for_update().get(pk=material.pk, knowledge_base=locked_kb)
            if material_fingerprint(locked_material) != frozen_material_fingerprint:
                raise BuildGenerationError(
                    "source_content_changed",
                    "资料内容在更新期间已变化，请重试",
                    retryable=True,
                    details={"material_id": material.pk},
                )
            locked_build.counts = counts
            locked_build.affected_pages = list(dict.fromkeys(affected))
            locked_build.inputs = {
                **(locked_build.inputs or {}),
                "source_trace": source_trace,
                "budget_trace": budget.trace(),
            }
            locked_build.maintenance = {
                **(locked_build.maintenance or {}),
                "generation_relations": relation_result,
            }
            locked_build.budget_trace = budget.trace()
            locked_build.errors = []
            locked_build.stage = "done"
            locked_build.status = "success"
            locked_build.progress = 100
            locked_build.save(
                update_fields=[
                    "counts",
                    "affected_pages",
                    "inputs",
                    "maintenance",
                    "budget_trace",
                    "errors",
                    "stage",
                    "status",
                    "progress",
                    "updated_at",
                ]
            )
            locked_material.status = "built"
            locked_material.save(update_fields=["status", "updated_at"])
            published_build = locked_build

        def pre_activation_hook(candidate):
            from apps.opspilot.services.wiki.generation_navigation_service import enhance_generation_overviews

            result = enhance_generation_overviews(
                candidate.pk,
                llm_model_id=llm_model_id,
                budget=budget,
                invoke_llm=_invoke_llm,
            )
            source_trace["semantic_overview"] = result

        finalize_build_generation(
            context,
            build_record=build,
            page_actions=page_actions,
            directory_trace=directory_trace,
            pending_material_ids_by_page=pending_material_ids_by_page,
            evidence_records=evidence_records,
            pre_activation_hook=pre_activation_hook,
            activation_hook=activation_hook,
        )
        return published_build or build
    except Exception as exc:
        logger.exception("wiki generation 资料更新失败 material=%s", material.pk)
        if context is not None:
            fail_build_generation(context, build_record=build, error=exc)
        build.refresh_from_db()
        is_budget_error = isinstance(exc, WikiBudgetExceeded)
        build.stage = "budget_exhausted" if is_budget_error else "failed"
        build.status = "budget_exhausted" if is_budget_error else "failed"
        build.budget_trace = budget.trace()
        build.errors = (
            [
                {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            ]
            if is_budget_error
            else [str(exc)]
        )
        build.checkpoint = (
            {
                "stopped_stage": exc.details.get("next_stage") or "budget_exhausted",
                "partial_map_outputs": list(exc.details.get("partial_map_outputs") or []),
                "map_chunk_count": exc.details.get("map_chunk_count"),
                "completed_map_calls": exc.details.get(
                    "completed_map_calls",
                    0,
                ),
            }
            if is_budget_error
            else build.checkpoint
        )
        build.save(
            update_fields=[
                "stage",
                "status",
                "budget_trace",
                "errors",
                "checkpoint",
                "updated_at",
            ]
        )
        raise


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
        error = humanize_maintenance_error(exc)
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


def _handle_material_deletion_generation(
    material,
    operator="",
    *,
    classification_root_id=None,
    frozen_identity=None,
):
    """Delete one material through a complete staging generation and CAS activation."""

    from apps.opspilot.services.wiki.build_generation_service import (
        BuildGenerationError,
        begin_build_generation,
        fail_build_generation,
        finalize_build_generation,
        material_fingerprint,
    )
    from apps.opspilot.services.wiki.generation_service import GENERATION_PAGE_ACTIONS_KEY, remove_generation_member

    knowledge_base_id = material.knowledge_base_id
    material_id = material.pk
    kb = WikiKnowledgeBase.objects.select_related("active_structure_revision").get(pk=knowledge_base_id)
    material = Material.objects.select_related("current_version", "knowledge_base").get(
        pk=material_id,
        knowledge_base=kb,
    )
    source_fingerprints = [material_fingerprint(material)]
    frozen_evidence_page_ids = _material_evidence_page_ids(material_id)
    if frozen_identity is not None:
        classification_root_id = frozen_identity.get("classification_root_id")
    _validate_frozen_generation_identity(
        kb,
        frozen_identity,
        source_fingerprints=source_fingerprints,
        classification_root_id=classification_root_id,
    )
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_delete",
        operator=operator,
        inputs={
            "material_id": material_id,
            "material_name": material.name,
            "classification_root_id": classification_root_id,
            **({"task_identity": dict(frozen_identity)} if frozen_identity is not None else {}),
        },
        stage="generating",
        status="running",
    )
    context = None
    try:
        context = begin_build_generation(
            kb,
            build,
            source_fingerprints=source_fingerprints,
            operator=operator,
        )
        _validate_frozen_generation_identity(
            kb,
            frozen_identity,
            source_fingerprints=source_fingerprints,
            classification_root_id=classification_root_id,
            context=context,
        )
        members = _base_generation_members_for_material(context, material)
        member_page_ids = [member.page_id for member in members]
        remaining_source_page_ids = set(
            PageEvidence.objects.filter(page_id__in=member_page_ids).exclude(material_id=material_id).values_list("page_id", flat=True).distinct()
        )
        invalidated_page_ids = [member.page_id for member in members if member.page_id not in remaining_source_page_ids]
        shared_page_ids = [member.page_id for member in members if member.page_id in remaining_source_page_ids]
        page_actions = [
            {
                "page_id": page_id,
                "action": "source_invalid",
                "target_status": "source_invalid",
                "material_id": material_id,
            }
            for page_id in invalidated_page_ids
        ]

        with transaction.atomic():
            locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=knowledge_base_id)
            # 可空 FK（current_version）不可与 FOR UPDATE 联表，否则 PG/部分信创库会报错。
            # 先锁资料行，版本再单独读取（通用写法，避免 of=("self",) 等方言参数）。
            locked_material = Material.objects.select_for_update().get(pk=material_id, knowledge_base=locked_kb)
            if locked_material.current_version_id:
                locked_material.current_version = MaterialVersion.objects.get(pk=locked_material.current_version_id)
            else:
                locked_material.current_version = None
            # FOR UPDATE 不可与 DISTINCT 同用；锁证据行后在应用侧去重 page_id
            locked_evidence_page_ids = list(
                dict.fromkeys(
                    PageEvidence.objects.select_for_update()
                    .filter(material_id=material_id)
                    .order_by("page_id", "id")
                    .values_list("page_id", flat=True)
                )
            )
            if locked_evidence_page_ids != frozen_evidence_page_ids:
                raise BuildGenerationError(
                    "material_evidence_changed",
                    "资料关联页面已并发变化，请重试删除",
                    retryable=True,
                )
            if material_fingerprint(locked_material) != source_fingerprints[0]:
                raise BuildGenerationError(
                    "source_identity_changed",
                    "资料来源身份已变化，请重试删除",
                    retryable=True,
                )
            locked_checks = list(CheckItem.objects.select_for_update().filter(knowledge_base=locked_kb).order_by("id"))
            rules_revoked = decision_service.revoke_rules_for_materials(
                [locked_material],
                reason="资料已物理删除",
                operator=operator,
            )
            for page_id in invalidated_page_ids:
                remove_generation_member(
                    context.candidate_generation_id,
                    page_id=page_id,
                )

            build.maintenance = {
                **(build.maintenance or {}),
                GENERATION_PAGE_ACTIONS_KEY: page_actions,
            }
            build.inputs = {
                **(build.inputs or {}),
                "all_evidence_page_ids": locked_evidence_page_ids,
                "invalidated_page_ids": invalidated_page_ids,
                "shared_page_ids": shared_page_ids,
                "rules_revoked": rules_revoked,
                "source_loss": "被删除的资料来源不可恢复",
            }
            build.save(update_fields=["maintenance", "inputs", "updated_at"])

            locked_material.delete()
            checks_auto_resolved = _auto_resolve_material_deletion_checks(
                locked_kb,
                material_id=material_id,
                invalidated_page_ids=invalidated_page_ids,
                checks=locked_checks,
            )
            activation, relation_result = finalize_build_generation(
                context,
                build_record=build,
                page_actions=page_actions,
                directory_trace=[],
            )
            build.refresh_from_db()
            build.inputs = {
                **(build.inputs or {}),
                "checks_auto_resolved": checks_auto_resolved,
            }
            build.counts = {
                "new": 0,
                "updated": len(invalidated_page_ids),
                "unchanged": len(shared_page_ids),
                "pending_review": 0,
            }
            build.affected_pages = frozen_evidence_page_ids
            build.maintenance = {
                **(build.maintenance or {}),
                GENERATION_PAGE_ACTIONS_KEY: page_actions,
                "generation_relations": relation_result,
            }
            build.stage = "done"
            build.status = "success"
            build.progress = 100
            build.errors = []
            build.save(
                update_fields=[
                    "inputs",
                    "counts",
                    "affected_pages",
                    "maintenance",
                    "stage",
                    "status",
                    "progress",
                    "errors",
                    "updated_at",
                ]
            )
        return build
    except Exception as exc:
        logger.exception("wiki generation 资料删除失败 material=%s", material_id)
        if context is not None:
            fail_build_generation(context, build_record=build, error=exc)
        build.refresh_from_db()
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        raise


def handle_material_deletion(
    material,
    operator="",
    *,
    classification_root_id=None,
    frozen_identity=None,
):
    """Publish material deletion through a new generation only."""

    return _handle_material_deletion_generation(
        material,
        operator=operator,
        classification_root_id=classification_root_id,
        frozen_identity=frozen_identity,
    )


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


def propose_update(
    material,
    llm_model_id=None,
    operator="",
    generator=None,
    *,
    classification_root_id=None,
    frozen_identity=None,
):
    """Publish material updates through a new generation only."""

    return _propose_update_generation(
        material,
        llm_model_id=llm_model_id,
        operator=operator,
        generator=generator,
        classification_root_id=classification_root_id,
        frozen_identity=frozen_identity,
    )
