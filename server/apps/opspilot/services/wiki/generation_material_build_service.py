"""Material build implementation for ready/enabled Wiki knowledge bases."""

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import BuildRecord, KnowledgePage, Material, WikiGeneration, WikiStructureRevision
from apps.opspilot.services.llm_context_budget import window_tokens_for_model_id
from apps.opspilot.services.wiki.build_generation_service import (
    BuildGenerationError,
    begin_build_generation,
    fail_build_generation,
    finalize_build_generation,
    material_fingerprint,
    stage_ai_page,
)
from apps.opspilot.services.wiki.build_service import (
    _canonical_title,
    _create_review_candidate,
    _invoke_llm,
    _normalize_page_data_title,
    _page_action_trace,
    _source_chunk_trace,
    _source_chunks_with_offsets,
    _source_locator_for_page,
    as_material_page_generation,
    generate_material_pages_with_budget,
    generation_publish_status,
    generation_skip_checkpoint,
    material_source_metadata,
    prepare_page_data_with_contact_facts,
    published_pages_missing_contact_facts,
)
from apps.opspilot.services.wiki.conflict_candidate_routing_service import route_material_conflicts
from apps.opspilot.services.wiki.directory_assignment_service import resolve_page_directory
from apps.opspilot.services.wiki.generation_wikilink_enrichment_service import apply_generation_wikilink_trace, enrich_generation_pages_wikilinks
from apps.opspilot.services.wiki.material_build_queue_service import MaterialBuildCancelled
from apps.opspilot.services.wiki.material_service import load_parsed_markdown
from apps.opspilot.services.wiki.title_service import title_alias_terms_for_enrichment as _title_alias_terms_for_enrichment
from apps.opspilot.services.wiki.title_service import title_identity_key
from apps.opspilot.services.wiki.update_service import _validate_frozen_generation_identity
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, new_material_call_budget


def _confidence(page_data):
    value = page_data.get("directory_confidence")
    if value is None:
        value = page_data.get("confidence")
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _prompt_source_trace(source_metadata):
    return {
        key: source_metadata.get(key)
        for key in ("material_id", "display_name", "source_title", "material_type")
        if source_metadata.get(key) is not None
    }


def _log_material_build_token_usage(*, material, build, budget, status, llm_model_id=None):
    """Emit one searchable line summarizing LLM token spend for a material build."""
    summary = budget.usage_summary() if budget is not None else {}
    logger.info(
        "wiki_build_token_usage material=%s build=%s kb=%s status=%s model_id=%s "
        "used_calls=%s used_tokens=%s input_tokens=%s output_tokens=%s "
        "provider_calls=%s estimate_calls=%s soft_total_tokens=%s soft_budget_exceeded=%s stages=%s",
        getattr(material, "pk", None),
        getattr(build, "pk", None),
        getattr(getattr(material, "knowledge_base", None), "pk", None) or getattr(build, "knowledge_base_id", None),
        status,
        llm_model_id,
        summary.get("used_calls", 0),
        summary.get("used_tokens", 0),
        summary.get("input_tokens", 0),
        summary.get("output_tokens", 0),
        summary.get("provider_calls", 0),
        summary.get("estimate_calls", 0),
        summary.get("soft_total_tokens"),
        summary.get("soft_budget_exceeded", False),
        summary.get("stages") or "-",
    )


def _existing_pages(knowledge_base):
    result = {}
    for page in KnowledgePage.objects.filter(knowledge_base=knowledge_base).select_related("current_version").order_by("id"):
        result.setdefault(title_identity_key(page.title), page)
    return result


def _base_directory(context, page):
    if page is None or context.base_generation_id is None:
        return None
    membership = WikiGeneration.objects.get(pk=context.base_generation_id).page_members.select_related("directory").filter(page=page).first()
    return membership.directory if membership is not None else page.directory


def build_material_with_generation(
    material,
    build,
    *,
    llm_model_id=None,
    operator="",
    classification_root_id=None,
    frozen_identity=None,
):
    """Prepare and activate one complete generation for a material build."""

    if frozen_identity is None:
        raise BuildGenerationError(
            "frozen_generation_identity_missing",
            "generation 资料构建缺少任务固定身份",
        )
    if not isinstance(frozen_identity, dict):
        raise BuildGenerationError(
            "frozen_generation_identity_invalid",
            "generation 资料构建固定身份必须为对象",
        )
    classification_root_id = frozen_identity.get("classification_root_id")
    frozen_source_fingerprints = list(frozen_identity.get("source_fingerprints") or [])
    context = None
    budget = new_material_call_budget(material.pk, window_tokens=window_tokens_for_model_id(llm_model_id))
    try:
        material = Material.objects.select_related("knowledge_base", "current_version").get(pk=material.pk)
        knowledge_base = material.knowledge_base
        current_source_fingerprints = [material_fingerprint(material)]
        _validate_frozen_generation_identity(
            knowledge_base,
            frozen_identity,
            source_fingerprints=current_source_fingerprints,
            classification_root_id=classification_root_id,
        )
        frozen_material_fingerprint = dict(frozen_source_fingerprints[0])
        context = begin_build_generation(
            knowledge_base,
            build,
            source_fingerprints=frozen_source_fingerprints,
            operator=operator,
        )
        _validate_frozen_generation_identity(
            knowledge_base,
            frozen_identity,
            source_fingerprints=current_source_fingerprints,
            classification_root_id=classification_root_id,
            context=context,
        )
        revision = WikiStructureRevision.objects.get(pk=context.structure_revision_id, knowledge_base=knowledge_base)
        text = (load_parsed_markdown(material) or material.ai_summary or material.text_content or "").strip()
        source_chunks = _source_chunks_with_offsets(text)
        source_metadata = material_source_metadata(material)
        generation = as_material_page_generation(
            generate_material_pages_with_budget(
                knowledge_base,
                text,
                llm_model_id,
                budget=budget,
                structure_revision=revision,
                classification_root_id=classification_root_id,
                source_metadata=source_metadata,
            )
        )
        pages_data = generation.pages
        skipped = list(generation.skipped)
        conflict_routing = route_material_conflicts(
            context.candidate_generation_id,
            pages_data,
            llm_model_id=llm_model_id,
            budget=budget,
            invoke_llm=_invoke_llm,
        )
        conflict_trace = {
            "compact_candidate_count": conflict_routing.compact_candidate_count,
            "evidence_page_ids": list(conflict_routing.evidence_page_ids),
            "old_evidence_tokens": conflict_routing.old_evidence_tokens,
            "overflow_count": conflict_routing.overflow_count,
            "llm_called": conflict_routing.llm_called,
            "unresolved_incoming_indexes": list(conflict_routing.unresolved_incoming_indexes),
        }
        source_trace = {
            "material": _prompt_source_trace(source_metadata),
            "chunks": _source_chunk_trace(source_chunks),
            "page_actions": [],
            "conflict_routing": conflict_trace,
        }
        page_actions = []
        directory_trace = []
        evidence_records = []
        pending_material_ids_by_page = {}
        enrichment_page_ids = set()
        affected = []
        counts = {
            "new": 0,
            "updated": 0,
            "restored": 0,
            "unchanged": 0,
            "pending_review": 0,
        }
        existing = _existing_pages(knowledge_base)
        threshold = float((knowledge_base.generation_rules or {}).get("directory_confidence_threshold", 0.6))
        publishable_page_payloads = []

        for incoming_index, raw_page_data in enumerate(pages_data):
            page_data = _normalize_page_data_title(knowledge_base, raw_page_data)
            # 写入前按单页再补一次：主题页若进待审批，source 仍必须带上联系方式。
            page_data = prepare_page_data_with_contact_facts(text, page_data)
            title = page_data.get("title") or ""
            page = existing.get(title_identity_key(title))
            comparison = conflict_routing.comparisons.get(incoming_index)
            comparison_page = None
            if comparison is not None:
                comparison_page = KnowledgePage.objects.filter(
                    pk=comparison.get("old_page_id"),
                    knowledge_base=knowledge_base,
                ).first()
                if comparison.get("same_subject") is True and comparison_page is not None:
                    page = comparison_page
                    title = comparison_page.title
                    page_data = {**page_data, "title": title}
                    page_data = prepare_page_data_with_contact_facts(text, page_data)
                elif comparison.get("relation") in {"conflict", "unresolved"} and comparison_page is not None and page is None:
                    page = comparison_page

            identity_ambiguous = bool(
                page is not None and comparison is not None and comparison.get("old_page_id") == page.pk and comparison.get("relation") == "unrelated"
            )
            confidence = _confidence(page_data)
            assignment = resolve_page_directory(
                knowledge_base=knowledge_base,
                structure_revision=revision,
                page_type=page_data.get("page_type") or "concept",
                assignment_mode=(page.directory_assignment_mode if page is not None else "auto"),
                current_directory=_base_directory(context, page),
                suggested_key=page_data.get("directory_key"),
                suggestion_source="llm",
                classification_root_id=classification_root_id,
                confidence=confidence,
                schema_mismatch=bool(page_data.get("directory_schema_mismatch", False)),
                suggestion_reason=page_data.get("directory_reason") or "",
                low_confidence=confidence is not None and confidence < threshold,
            )
            directory_item = assignment.as_build_trace()
            directory_item.update({"title": title, "material_id": material.pk})
            directory_trace.append(directory_item)
            locator = _source_locator_for_page(material, text, page_data, chunks=source_chunks)

            requires_review = bool(
                page is not None
                and (
                    page.contribution != "ai"
                    or identity_ambiguous
                    or (comparison is not None and comparison.get("relation") in {"conflict", "unresolved"})
                )
            )
            if requires_review:
                action, decision_trace = _create_review_candidate(
                    page,
                    material,
                    build,
                    page_data,
                    operator=operator,
                    locator=locator,
                )
                decision_trace = {
                    **decision_trace,
                    "conflict_routing": comparison or {},
                    "identity_ambiguous": identity_ambiguous,
                }
                counts[action] += 1
                affected.append(page.pk)
                action_item = {
                    "page_id": page.pk,
                    "title": page.title,
                    "action": "candidate" if action == "pending_review" else action,
                    "material_id": material.pk,
                    "locator": locator,
                    **decision_trace,
                }
                page_actions.append(action_item)
                source_trace["page_actions"].append(action_item)
                continue

            publishable_page_payloads.append(page_data)
            staged = stage_ai_page(
                context,
                page_id=page.pk if page is not None else None,
                title=title,
                page_type=page_data.get("page_type") or "concept",
                tags=page_data.get("tags") or [],
                body=page_data.get("body") or "",
                directory_id=assignment.directory.pk,
                assignment_mode=assignment.assignment_mode,
                build_record=build,
                operator=operator,
                update_method="ai_create" if page is None else "ai_merge",
                change_type="ai_create" if page is None else "ai_merge",
                body_strategy="merge",
                navigation_metadata={
                    "summary": page_data.get("summary") or "",
                    "keywords": page_data.get("keywords") or [],
                    "entities": page_data.get("entities") or [],
                    "aliases": page_data.get("aliases") or [],
                },
            )
            existing[title_identity_key(staged.title)] = KnowledgePage.objects.get(pk=staged.page_id)
            count_key = {
                "create": "new",
                "restore": "restored",
                "update": "updated",
                "unchanged": "unchanged",
            }[staged.action]
            counts[count_key] += 1
            affected.append(staged.page_id)
            action_item = {
                "page_id": staged.page_id,
                "page_version_id": staged.page_version_id,
                "title": staged.title,
                "action": staged.action,
                "material_id": material.pk,
                "locator": locator,
                "directory_id": staged.directory_id,
                "assignment_mode": staged.assignment_mode,
            }
            page_actions.append(action_item)
            trace_item = _page_action_trace(
                KnowledgePage.objects.get(pk=staged.page_id),
                count_key if count_key != "restored" else "updated",
                locator,
            )
            trace_item.update(action_item)
            source_trace["page_actions"].append(trace_item)
            pending_material_ids_by_page.setdefault(staged.page_id, set()).add(material.pk)
            enrichment_page_ids.add(staged.page_id)
            evidence_records.append(
                {
                    "page_id": staged.page_id,
                    "material": material,
                    "material_version": material.current_version,
                    "locator": locator,
                }
            )

        missing_on_publishable = published_pages_missing_contact_facts(text, publishable_page_payloads)
        if missing_on_publishable:
            logger.error(
                "wiki_build_contact_facts_missing_after_prepare material_id=%s missing=%s publishable_titles=%s",
                material.pk,
                [item.get("value") for item in missing_on_publishable],
                [item.get("title") for item in publishable_page_payloads],
            )
            source_trace["contact_facts_missing"] = [{"kind": item.get("kind"), "value": item.get("value")} for item in missing_on_publishable]

        enrichment_results = enrich_generation_pages_wikilinks(
            context.candidate_generation_id,
            enrichment_page_ids,
            None,
            _invoke_llm,
            build_record=build,
            operator=operator,
            canonicalize=lambda value: _canonical_title(knowledge_base, value),
            alias_terms_resolver=lambda value: _title_alias_terms_for_enrichment(
                knowledge_base,
                value,
            ),
        )
        apply_generation_wikilink_trace(page_actions, enrichment_results)
        apply_generation_wikilink_trace(
            source_trace["page_actions"],
            enrichment_results,
        )

        published_build = None

        def pre_activation_hook(candidate):
            from apps.opspilot.services.wiki.generation_navigation_service import enhance_generation_overviews

            result = enhance_generation_overviews(
                candidate.pk,
                llm_model_id=llm_model_id,
                budget=budget,
                invoke_llm=_invoke_llm,
            )
            source_trace["semantic_overview"] = result

        def activation_hook(_candidate, locked_kb, relation_result):
            nonlocal published_build
            locked_build = BuildRecord.objects.select_for_update().get(
                pk=build.pk,
                knowledge_base=locked_kb,
            )
            if locked_build.status == "cancelled":
                raise MaterialBuildCancelled()
            locked_material = Material.objects.select_for_update().get(pk=material.pk, knowledge_base=locked_kb)
            locked_source_fingerprints = [material_fingerprint(locked_material)]
            _validate_frozen_generation_identity(
                locked_kb,
                frozen_identity,
                source_fingerprints=locked_source_fingerprints,
                classification_root_id=classification_root_id,
            )
            if locked_source_fingerprints[0] != frozen_material_fingerprint:
                raise BuildGenerationError(
                    "source_content_changed",
                    "资料内容在构建期间已变化，请重试",
                    retryable=True,
                    details={"material_id": material.pk},
                )
            locked_build.inputs = {
                **(locked_build.inputs or {}),
                "material_name": locked_material.name,
                "classification_root_id": classification_root_id,
                "source_trace": source_trace,
            }
            locked_build.counts = counts
            locked_build.affected_pages = list(dict.fromkeys(affected))
            locked_build.maintenance = {
                **(locked_build.maintenance or {}),
                "generation_relations": relation_result,
            }
            locked_build.errors = list(skipped)
            locked_build.budget_trace = budget.trace()
            locked_build.checkpoint = generation_skip_checkpoint(skipped)
            locked_build.stage = "done"
            locked_build.status = generation_publish_status(skipped)
            locked_build.progress = 100
            locked_build.save(
                update_fields=[
                    "inputs",
                    "counts",
                    "affected_pages",
                    "maintenance",
                    "errors",
                    "budget_trace",
                    "checkpoint",
                    "stage",
                    "status",
                    "progress",
                    "updated_at",
                ]
            )
            locked_material.status = "built"
            locked_material.save(update_fields=["status", "updated_at"])
            published_build = locked_build

        build.refresh_from_db()
        if build.status == "cancelled":
            raise MaterialBuildCancelled()
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
        _log_material_build_token_usage(
            material=material,
            build=published_build or build,
            budget=budget,
            status=generation_publish_status(skipped),
            llm_model_id=llm_model_id,
        )
        return published_build or build
    except MaterialBuildCancelled:
        if context is not None:
            fail_build_generation(
                context,
                build_record=None,
                code="material_build_cancelled",
                error="构建已取消",
            )
        logger.info(
            "wiki material build discarded cancelled record=%s material=%s",
            getattr(build, "pk", None),
            getattr(material, "pk", None),
        )
        _log_material_build_token_usage(
            material=material,
            build=build,
            budget=budget,
            status="cancelled",
            llm_model_id=llm_model_id,
        )
        raise
    except Exception as exc:
        is_budget_error = isinstance(exc, WikiBudgetExceeded)
        if context is not None:
            fail_build_generation(
                context,
                build_record=build,
                code=getattr(exc, "code", "generation_failed"),
                error=exc,
            )
        build.refresh_from_db()
        if build.status == "cancelled":
            logger.info(
                "wiki material build discarded cancelled record=%s material=%s",
                build.pk,
                getattr(material, "pk", None),
            )
            raise MaterialBuildCancelled() from exc
        if is_budget_error:
            build.stage = "budget_exhausted"
            build.status = "budget_exhausted"
            build.progress = 100
            build.errors = [
                {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            ]
            build.budget_trace = budget.trace()
            build.checkpoint = {
                "source_fingerprints": frozen_source_fingerprints,
                "structure_revision_id": frozen_identity.get("structure_revision_id"),
                "structure_fingerprint": frozen_identity.get("structure_fingerprint"),
                "pipeline_version": frozen_identity.get("pipeline_version"),
                "stopped_stage": exc.details.get("next_stage") or build.stage,
                "partial_map_outputs": list(exc.details.get("partial_map_outputs") or []),
                "map_chunk_count": exc.details.get("map_chunk_count"),
                "completed_map_calls": exc.details.get("completed_map_calls", 0),
            }
        else:
            build.stage = "failed"
            build.status = "failed"
            build.errors = [str(exc)]
            build.budget_trace = budget.trace()
        build.save(
            update_fields=[
                "stage",
                "status",
                "progress",
                "errors",
                "budget_trace",
                "checkpoint",
                "updated_at",
            ]
        )
        material.status = "build_failed"
        material.error_message = str(exc)[:2000]
        material.save(update_fields=["status", "error_message", "updated_at"])
        _log_material_build_token_usage(
            material=material,
            build=build,
            budget=budget,
            status=build.status,
            llm_model_id=llm_model_id,
        )
        raise


__all__ = ["build_material_with_generation"]
