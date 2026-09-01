"""Generation-aware full rebuild for ready/enabled Wiki knowledge bases."""

from dataclasses import dataclass, field

from django.db import transaction

from apps.opspilot.models import BuildRecord, KnowledgePage, Material, MaterialVersion, WikiDirectory, WikiGenerationPage, WikiStructureRevision
from apps.opspilot.services.wiki.build_generation_service import (
    PIPELINE_VERSION,
    BuildGenerationError,
    begin_build_generation,
    fail_build_generation,
    finalize_build_generation,
    freeze_source_fingerprints,
    material_fingerprint,
    stage_ai_page,
)
from apps.opspilot.services.wiki.build_service import (
    _canonical_title,
    _invoke_llm,
    _source_chunk_trace,
    generation_publish_status,
    generation_skip_checkpoint,
)
from apps.opspilot.services.wiki.candidate_adapter_contract import (
    CandidateParticipant,
    DjangoKnowledgeCandidateAdapter,
    body_conflict_key,
    identity_conflict_key,
)
from apps.opspilot.services.wiki.decision_service import build_participants_from_page_evidence, compute_schema_fingerprint
from apps.opspilot.services.wiki.directory_assignment_service import resolve_page_directory
from apps.opspilot.services.wiki.generation_service import GENERATION_PAGE_ACTIONS_KEY, put_generation_member, remove_generation_member
from apps.opspilot.services.wiki.generation_wikilink_enrichment_service import apply_generation_wikilink_trace, enrich_generation_pages_wikilinks
from apps.opspilot.services.wiki.title_service import title_alias_terms_for_enrichment as _title_alias_terms_for_enrichment
from apps.opspilot.services.wiki.title_service import title_identity_key
from apps.opspilot.services.wiki.update_service import _validate_frozen_generation_identity
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded


@dataclass
class StagedRebuild:
    page_actions: list
    directory_trace: list
    pending_material_ids_by_page: dict
    authoritative_ai_source_ids: set
    evidence_records: list
    enrichment_page_ids: set
    source_trace: dict
    counts: dict
    affected_page_ids: list
    removal_actions: list
    skipped: list = field(default_factory=list)


def _material_snapshot_hash(material):
    current_version = getattr(material, "current_version", None)
    return (getattr(current_version, "content_hash", "") or material.content_hash or "").strip()


def _lock_prepared_snapshot(kb, prepared, build):
    locked_kb = kb.__class__.objects.select_for_update().get(pk=kb.pk)
    locked_build = BuildRecord.objects.select_for_update().get(
        pk=build.pk,
        knowledge_base=locked_kb,
    )
    if compute_schema_fingerprint(locked_kb) != prepared["schema_fingerprint"]:
        raise BuildGenerationError(
            "schema_changed",
            "重建期间 Schema 已变化，请重新发起重建",
            retryable=True,
        )

    prepared_ids = list(prepared["material_ids"])
    materials = {material.pk: material for material in Material.objects.select_for_update().filter(knowledge_base=locked_kb).order_by("id")}
    if set(materials) != set(prepared_ids):
        raise BuildGenerationError(
            "source_set_changed",
            "重建期间资料集合已变化，请重新发起重建",
            retryable=True,
        )
    version_ids = {material.current_version_id for material in materials.values() if material.current_version_id}
    versions = {
        version.pk: version
        for version in MaterialVersion.objects.select_for_update().filter(
            id__in=version_ids,
            material_id__in=prepared_ids,
        )
    }
    if set(versions) != version_ids:
        raise BuildGenerationError(
            "source_version_changed",
            "重建期间资料版本已变化，请重新发起重建",
            retryable=True,
        )
    prepared_by_id = {item["material_id"]: item for item in prepared["materials"]}
    for material_id in prepared_ids:
        material = materials[material_id]
        material.current_version = versions.get(material.current_version_id)
        item = prepared_by_id[material_id]
        if (
            material.current_version_id != item["material_version_id"]
            or _material_snapshot_hash(material) != item["material_content_hash"]
            or material.updated_at != item["material_updated_at"]
        ):
            raise BuildGenerationError(
                "source_content_changed",
                "重建期间资料内容已变化，请重新发起重建",
                retryable=True,
                details={"material_id": material_id},
            )
    return locked_kb, locked_build, [materials[item] for item in prepared_ids]


def _current_identity(kb, source_fingerprints, classification_root_id):
    revision = kb.active_structure_revision
    if revision is None or kb.active_generation_id is None:
        raise BuildGenerationError(
            "active_governance_snapshot_missing",
            "知识库缺少 active structure/generation",
        )
    return {
        "base_generation_id": kb.active_generation_id,
        "structure_revision_id": revision.pk,
        "structure_version": revision.revision_no,
        "structure_fingerprint": revision.fingerprint,
        "pipeline_version": PIPELINE_VERSION,
        "source_fingerprints": list(source_fingerprints),
        "classification_root_id": classification_root_id,
    }


def _assert_live_context(kb, context):
    revision = kb.active_structure_revision
    if (
        kb.active_generation_id != context.base_generation_id
        or getattr(revision, "pk", None) != context.structure_revision_id
        or getattr(revision, "revision_no", None) != context.structure_version
        or getattr(revision, "fingerprint", "") != context.structure_fingerprint
    ):
        raise BuildGenerationError(
            "active_generation_changed",
            "重建期间 active generation 或 structure revision 已变化",
            retryable=True,
        )


def _all_state_pages(kb):
    grouped = {}
    pages = list(KnowledgePage.objects.select_for_update().filter(knowledge_base=kb).select_related("current_version", "directory").order_by("id"))
    for page in pages:
        grouped.setdefault(title_identity_key(page.title), []).append(page)
    unique = {identity: rows[0] for identity, rows in grouped.items() if len(rows) == 1}
    duplicates = {identity: rows for identity, rows in grouped.items() if len(rows) > 1}
    return unique, duplicates


def _member_display(member, page):
    display = dict(member.page_display_snapshot or {}) if member else {}
    return {
        "title": display.get("title") or page.title,
        "page_type": display.get("page_type") or page.page_type or "concept",
        "tags": list(display.get("tags") if display.get("tags") is not None else (page.tags or [])),
        "contribution": display.get("contribution") or page.contribution or "ai",
        "update_method": display.get("update_method") or page.update_method,
        "created_by": display.get("created_by") or page.created_by,
        "updated_by": display.get("updated_by") or page.updated_by,
        "created_at": display.get("created_at"),
        "updated_at": display.get("updated_at"),
    }


def _confidence(page_data):
    value = page_data.get("directory_confidence")
    if value is None:
        value = page_data.get("confidence")
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _route_directory(
    kb,
    revision,
    directory_rows,
    page_data,
    *,
    assignment_mode,
    current_directory,
    classification_root_id,
):
    confidence = _confidence(page_data)
    try:
        threshold = float((kb.generation_rules or {}).get("directory_confidence_threshold", 0.6))
    except (TypeError, ValueError):
        threshold = 0.6
    return resolve_page_directory(
        knowledge_base=kb,
        structure_revision=revision,
        page_type=page_data.get("page_type") or "concept",
        assignment_mode=assignment_mode,
        current_directory=current_directory,
        suggested_key=page_data.get("directory_key"),
        suggestion_source="llm",
        classification_root_id=classification_root_id,
        confidence=confidence,
        schema_mismatch=bool(page_data.get("directory_schema_mismatch", False)),
        suggestion_reason=page_data.get("directory_reason") or "",
        low_confidence=confidence is not None and confidence < threshold,
        directory_rows=directory_rows,
    )


def _body_candidate(page, member, material, build, context, body, operator):
    raw = build_participants_from_page_evidence(
        page,
        incoming_snapshot=material_fingerprint(material),
    )
    participants = []
    for item in raw:
        material_id = item.get("material_id")
        content_hash = str(item.get("content_hash") or "").strip()
        if type(material_id) is not int or material_id <= 0 or not content_hash:
            raise BuildGenerationError(
                "source_identity_incomplete",
                "human/mixed 正文候选缺少完整来源身份",
                details={"page_id": page.pk, "participant": item},
            )
        participants.append(CandidateParticipant(material_id=material_id, content_hash=content_hash))
    locked_version_id = member.page_version_id if member else page.current_version_id
    if locked_version_id is None:
        raise BuildGenerationError(
            "current_page_version_missing",
            "human/mixed 页面缺少当前正文版本",
            details={"page_id": page.pk},
        )
    conflict = body_conflict_key(
        knowledge_base_id=page.knowledge_base_id,
        page_id=page.pk,
        locked_current_version_id=locked_version_id,
        content_contract_fingerprint=context.structure_fingerprint,
        participants=participants,
    )
    return DjangoKnowledgeCandidateAdapter().create_body_conflict(
        conflict_key=conflict,
        candidate_body=body,
        build_record_id=build.pk,
        generation_id=context.candidate_generation_id,
        reason="全量重建产生不同知识结论，保持当前正文并等待人工决策",
        created_by=operator or "",
    )


def _persist_identity_failure(kb, build, context, duplicates, operator):
    adapter = DjangoKnowledgeCandidateAdapter()
    actions = []
    for identity, pages in duplicates.items():
        handle = adapter.create_identity_conflict(
            conflict_key=identity_conflict_key(
                knowledge_base_id=kb.pk,
                normalized_title_key=identity,
            ),
            incoming_candidate_ref=f"rebuild:{context.candidate_generation_id}:{identity}",
            competing_page_ids=[page.pk for page in pages],
            build_record_id=build.pk,
            generation_id=context.candidate_generation_id,
            reason="知识库全部状态存在重复标题身份，已阻止 generation 激活",
            created_by=operator or "",
        )
        actions.append(
            {
                "action": "identity_conflict",
                "title_identity": identity,
                "page_ids": [page.pk for page in pages],
                "check_id": handle.check_id,
                "candidate_created": handle.created,
                "blocks_generation_activation": handle.blocks_generation_activation,
            }
        )
    error = BuildGenerationError(
        "page_identity_ambiguous",
        "知识库全部状态存在重复标题身份，已阻止 generation 激活",
        details={"conflicts": actions},
    )
    fail_build_generation(
        context,
        build_record=build,
        code=error.code,
        error=error,
    )
    build.refresh_from_db()
    build.page_actions = actions
    build.counts = {"pending_review": len(actions)}
    build.affected_pages = list(dict.fromkeys(page.pk for pages in duplicates.values() for page in pages))
    build.stage = "failed"
    build.status = "failed"
    build.progress = 100
    build.errors = [f"{error.code}: {error}"]
    build.save(
        update_fields=[
            "page_actions",
            "counts",
            "affected_pages",
            "stage",
            "status",
            "progress",
            "errors",
            "updated_at",
        ]
    )
    return error


def _stage_rebuild_candidate(
    kb,
    prepared,
    build,
    materials,
    context,
    operator,
    classification_root_id,
):
    existing, duplicates = _all_state_pages(kb)
    if duplicates:
        return None, _persist_identity_failure(kb, build, context, duplicates, operator)

    revision = WikiStructureRevision.objects.select_for_update().get(
        pk=context.structure_revision_id,
        knowledge_base=kb,
    )
    directory_rows = list(WikiDirectory.objects.select_for_update().filter(knowledge_base=kb).select_related("parent", "merged_into").order_by("id"))
    base_members = list(
        WikiGenerationPage.objects.select_for_update()
        .filter(generation_id=context.base_generation_id)
        .select_related("page", "page_version", "directory")
        .order_by("page_id")
    )
    base_by_page = {member.page_id: member for member in base_members}
    pages_by_id = {page.pk: page for page in existing.values()}
    generated_ai = set()
    authoritative_ai_sources = set()
    pending_material_ids = {}
    evidence_records = []
    page_actions = []
    directory_trace = []
    affected = []
    removal_actions = []
    source_trace = {"materials": []}
    materials_by_id = {material.pk: material for material in materials}
    counts = {
        "new": 0,
        "updated": 0,
        "restored": 0,
        "archived": 0,
        "unchanged": 0,
        "pending_review": 0,
    }
    skipped = []

    for prepared_material in prepared["materials"]:
        material = materials_by_id[prepared_material["material_id"]]
        for item in prepared_material.get("skipped") or []:
            skipped.append({**item, "material_id": material.pk})
        material_trace = {
            "material_id": material.pk,
            "material_name": material.name,
            "chunks": _source_chunk_trace(prepared_material["source_chunks"]),
            "page_actions": [],
            "budget_trace": prepared_material.get("budget_trace") or {},
            "conflict_routing": prepared_material.get("conflict_routing") or {},
        }
        source_trace["materials"].append(material_trace)
        for prepared_page in prepared_material["pages"]:
            page_data = prepared_page["page_data"]
            locator = prepared_page["locator"]
            identity = title_identity_key(page_data.get("title"))
            page = existing.get(identity)
            comparison = prepared_page.get("comparison") or None
            comparison_page = pages_by_id.get(comparison.get("old_page_id")) if comparison is not None else None
            if comparison is not None and comparison_page is not None:
                if comparison.get("same_subject") is True:
                    page = comparison_page
                    page_data = {**page_data, "title": comparison_page.title}
                    identity = title_identity_key(comparison_page.title)
                elif comparison.get("relation") in {"conflict", "unresolved"} and page is None:
                    page = comparison_page
            member = base_by_page.get(page.pk) if page else None
            display = _member_display(member, page) if page else None
            contribution = display["contribution"] if display else "ai"
            identity_ambiguous = bool(
                page is not None and comparison is not None and comparison.get("old_page_id") == page.pk and comparison.get("relation") == "unrelated"
            )
            routed_review = bool(
                page is not None and comparison is not None and (comparison.get("relation") in {"conflict", "unresolved"} or identity_ambiguous)
            )
            if routed_review:
                if member is None:
                    raise BuildGenerationError(
                        "conflict_page_outside_base_generation",
                        "冲突候选页面不属于固定 base generation",
                        details={"page_id": page.pk},
                    )
                put_generation_member(
                    context.candidate_generation_id,
                    page_id=page.pk,
                    page_version_id=member.page_version_id,
                    directory_id=member.directory_id,
                    assignment_mode=member.assignment_mode,
                    page_status="active",
                    display_snapshot=_member_display(member, page),
                )
                handle = _body_candidate(
                    page,
                    member,
                    material,
                    build,
                    context,
                    page_data.get("body") or "",
                    operator,
                )
                counts["pending_review"] += 1
                affected.append(page.pk)
                action_item = {
                    "page_id": page.pk,
                    "page_version_id": member.page_version_id,
                    "candidate_version_id": handle.candidate_version_id,
                    "check_id": handle.check_id,
                    "title": _member_display(member, page)["title"],
                    "action": "candidate",
                    "body_preserved": True,
                    "contribution": contribution,
                    "candidate_created": handle.created,
                    "blocks_generation_activation": handle.blocks_generation_activation,
                    "material_id": material.pk,
                    "conflict_routing": comparison,
                    "identity_ambiguous": identity_ambiguous,
                }
                page_actions.append(action_item)
                material_trace["page_actions"].append({**action_item, "locator": locator})
                continue

            if page is not None and contribution in {"human", "mixed"}:
                assignment = None
                directory_changed = False
                if member is not None:
                    assignment = _route_directory(
                        kb,
                        revision,
                        directory_rows,
                        {**page_data, "page_type": display["page_type"]},
                        assignment_mode=member.assignment_mode,
                        current_directory=member.directory,
                        classification_root_id=classification_root_id,
                    )
                    put_generation_member(
                        context.candidate_generation_id,
                        page_id=page.pk,
                        page_version_id=member.page_version_id,
                        directory_id=assignment.directory.pk,
                        assignment_mode=assignment.assignment_mode,
                        page_status="active",
                        display_snapshot=display,
                    )
                    directory_changed = assignment.directory.pk != member.directory_id or assignment.assignment_mode != member.assignment_mode
                    directory_item = assignment.as_build_trace()
                    directory_item.update({"page_id": page.pk, "title": display["title"], "material_id": material.pk})
                    directory_trace.append(directory_item)

                current_version = member.page_version if member else page.current_version
                current_body = (current_version.body or "").strip() if current_version else ""
                incoming_body = (page_data.get("body") or "").strip()
                if incoming_body == current_body:
                    action = "update" if directory_changed else "unchanged"
                    counts["updated" if directory_changed else "unchanged"] += 1
                    if member is not None:
                        pending_material_ids.setdefault(page.pk, set()).add(material.pk)
                        evidence_records.append(
                            {
                                "page_id": page.pk,
                                "material_id": material.pk,
                                "material_version_id": material.current_version_id,
                                "locator": locator,
                            }
                        )
                    action_item = {
                        "page_id": page.pk,
                        "page_version_id": getattr(current_version, "pk", None),
                        "title": display["title"],
                        "action": action,
                        "body_preserved": True,
                        "contribution": contribution,
                        "material_id": material.pk,
                    }
                else:
                    handle = _body_candidate(
                        page,
                        member,
                        material,
                        build,
                        context,
                        incoming_body,
                        operator,
                    )
                    counts["pending_review"] += 1
                    action_item = {
                        "page_id": page.pk,
                        "page_version_id": getattr(current_version, "pk", None),
                        "candidate_version_id": handle.candidate_version_id,
                        "check_id": handle.check_id,
                        "title": display["title"],
                        "action": "candidate",
                        "body_preserved": True,
                        "contribution": contribution,
                        "candidate_created": handle.created,
                        "blocks_generation_activation": handle.blocks_generation_activation,
                        "material_id": material.pk,
                    }
                affected.append(page.pk)
                page_actions.append(action_item)
                material_trace["page_actions"].append({**action_item, "locator": locator})
                continue

            assignment_mode = member.assignment_mode if member else (page.directory_assignment_mode if page else "auto")
            current_directory = member.directory if member else (page.directory if page else None)
            assignment = _route_directory(
                kb,
                revision,
                directory_rows,
                page_data,
                assignment_mode=assignment_mode,
                current_directory=current_directory,
                classification_root_id=classification_root_id,
            )
            first_occurrence = page is None or page.pk not in generated_ai
            staged = stage_ai_page(
                context,
                page_id=page.pk if page else None,
                title=page_data.get("title") or "",
                page_type=page_data.get("page_type") or "concept",
                tags=page_data.get("tags") or [],
                body=page_data.get("body") or "",
                directory_id=assignment.directory.pk,
                assignment_mode=assignment.assignment_mode,
                build_record=build,
                operator=operator,
                update_method="rebuild",
                change_type="rebuild",
                body_strategy="replace" if first_occurrence else "merge",
                navigation_metadata={
                    "summary": page_data.get("summary") or "",
                    "keywords": page_data.get("keywords") or [],
                    "entities": page_data.get("entities") or [],
                    "aliases": page_data.get("aliases") or [],
                },
            )
            page = KnowledgePage.objects.select_for_update().get(pk=staged.page_id)
            existing[identity] = page
            generated_ai.add(staged.page_id)
            authoritative_ai_sources.add(staged.page_id)
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
            material_trace["page_actions"].append(action_item)
            directory_item = assignment.as_build_trace()
            directory_item.update({"page_id": staged.page_id, "title": staged.title, "material_id": material.pk})
            directory_trace.append(directory_item)
            pending_material_ids.setdefault(staged.page_id, set()).add(material.pk)
            evidence_records.append(
                {
                    "page_id": staged.page_id,
                    "material_id": material.pk,
                    "material_version_id": material.current_version_id,
                    "locator": locator,
                }
            )

    for member in base_members:
        display = _member_display(member, member.page)
        if display["contribution"] == "ai" and member.page_id not in generated_ai:
            remove_generation_member(
                context.candidate_generation_id,
                page_id=member.page_id,
            )
            action_item = {
                "page_id": member.page_id,
                "page_version_id": member.page_version_id,
                "title": display["title"],
                "action": "archive",
                "target_status": "archived",
                "reason": "full_rebuild_not_generated",
            }
            removal_actions.append(action_item)
            page_actions.append(action_item)
            counts["archived"] += 1
            affected.append(member.page_id)

    build.maintenance = {
        **(build.maintenance or {}),
        GENERATION_PAGE_ACTIONS_KEY: removal_actions,
    }
    build.save(update_fields=["maintenance", "updated_at"])

    return (
        StagedRebuild(
            page_actions=page_actions,
            directory_trace=directory_trace,
            pending_material_ids_by_page=pending_material_ids,
            authoritative_ai_source_ids=authoritative_ai_sources,
            evidence_records=evidence_records,
            enrichment_page_ids=generated_ai,
            source_trace=source_trace,
            counts=counts,
            affected_page_ids=affected,
            removal_actions=removal_actions,
            skipped=skipped,
        ),
        None,
    )


def _enrich_staged_rebuild(
    kb,
    build,
    context,
    staged,
    operator,
    llm_model_id,
):
    enrichment_results = enrich_generation_pages_wikilinks(
        context.candidate_generation_id,
        staged.enrichment_page_ids,
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
    apply_generation_wikilink_trace(
        staged.page_actions,
        enrichment_results,
    )
    for material_trace in staged.source_trace["materials"]:
        apply_generation_wikilink_trace(
            material_trace["page_actions"],
            enrichment_results,
        )


def _materialize_evidence_records(staged, materials):
    materials_by_id = {material.pk: material for material in materials}
    records = []
    for frozen in staged.evidence_records:
        material = materials_by_id.get(frozen["material_id"])
        if material is None or material.current_version_id != frozen["material_version_id"]:
            raise BuildGenerationError(
                "source_content_changed",
                "重建期间证据来源版本已变化，请重新发起重建",
                retryable=True,
                details={"material_id": frozen["material_id"]},
            )
        records.append(
            {
                "page_id": frozen["page_id"],
                "material": material,
                "material_version": material.current_version,
                "locator": frozen["locator"],
            }
        )
    return records


def _finalize_staged_rebuild(
    kb,
    build,
    materials,
    context,
    staged,
    classification_root_id,
):
    evidence_records = _materialize_evidence_records(staged, materials)

    def activation_hook(_candidate, locked_kb, relation_result):
        locked_build = BuildRecord.objects.select_for_update().get(
            pk=build.pk,
            knowledge_base=locked_kb,
        )
        locked_build.inputs = {
            **(locked_build.inputs or {}),
            "classification_root_id": classification_root_id,
            "source_trace": staged.source_trace,
        }
        locked_build.counts = staged.counts
        locked_build.affected_pages = list(dict.fromkeys(staged.affected_page_ids))
        locked_build.maintenance = {
            **(locked_build.maintenance or {}),
            GENERATION_PAGE_ACTIONS_KEY: staged.removal_actions,
            "generation_relations": relation_result,
        }
        locked_build.errors = list(staged.skipped)
        locked_build.budget_trace = {
            "scope": "wiki_rebuild",
            "materials": [
                {
                    "material_id": item.get("material_id"),
                    "budget": item.get("budget_trace") or {},
                }
                for item in staged.source_trace.get("materials", [])
            ],
        }
        locked_build.checkpoint = generation_skip_checkpoint(staged.skipped)
        locked_build.stage = "done"
        locked_build.status = generation_publish_status(staged.skipped)
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

    finalize_build_generation(
        context,
        build_record=build,
        page_actions=staged.page_actions,
        directory_trace=staged.directory_trace,
        pending_material_ids_by_page=staged.pending_material_ids_by_page,
        replace_material_ids_for_pages=staged.authoritative_ai_source_ids,
        evidence_records=evidence_records,
        activation_hook=activation_hook,
    )
    build.refresh_from_db()
    return build


def rebuild_with_generation(
    kb,
    *,
    llm_model_id=None,
    operator="",
    generator=None,
    build=None,
    classification_root_id=None,
    frozen_identity=None,
):
    from apps.opspilot.services.wiki.rebuild_service import _mark_rebuild_generating, _prepare_rebuild, create_rebuild_record

    kb = kb.__class__.objects.select_related("active_structure_revision").get(pk=kb.pk)
    if not (kb.active_generation_id and kb.active_structure_revision_id):
        raise BuildGenerationError(
            "generation_pipeline_not_enabled",
            "知识库尚未进入 generation truth 状态",
        )
    build = build or create_rebuild_record(kb, operator=operator)
    _mark_rebuild_generating(build, kb, operator)
    context = None
    try:
        materials = list(Material.objects.filter(knowledge_base=kb).select_related("current_version").order_by("id"))
        source_fingerprints = freeze_source_fingerprints(materials)
        if frozen_identity is not None:
            classification_root_id = frozen_identity.get("classification_root_id")
        else:
            frozen_identity = _current_identity(
                kb,
                source_fingerprints,
                classification_root_id,
            )
        _validate_frozen_generation_identity(
            kb,
            frozen_identity,
            source_fingerprints=source_fingerprints,
            classification_root_id=classification_root_id,
        )
        build.inputs = {
            **(build.inputs or {}),
            "task_identity": dict(frozen_identity),
            "classification_root_id": classification_root_id,
        }
        build.save(update_fields=["inputs", "updated_at"])
        prepared = _prepare_rebuild(
            kb,
            llm_model_id,
            generator,
            structure_revision=kb.active_structure_revision,
            classification_root_id=classification_root_id,
        )

        with transaction.atomic():
            locked_kb, locked_build, materials = _lock_prepared_snapshot(kb, prepared, build)
            source_fingerprints = freeze_source_fingerprints(materials)
            _validate_frozen_generation_identity(
                locked_kb,
                frozen_identity,
                source_fingerprints=source_fingerprints,
                classification_root_id=classification_root_id,
            )
            context = begin_build_generation(
                locked_kb,
                locked_build,
                source_fingerprints=source_fingerprints,
                pipeline_version=PIPELINE_VERSION,
                kind="build",
                operator=operator,
            )
            _validate_frozen_generation_identity(
                locked_kb,
                frozen_identity,
                source_fingerprints=source_fingerprints,
                classification_root_id=classification_root_id,
                context=context,
            )

        with transaction.atomic():
            locked_kb, locked_build, materials = _lock_prepared_snapshot(kb, prepared, build)
            source_fingerprints = freeze_source_fingerprints(materials)
            _assert_live_context(locked_kb, context)
            _validate_frozen_generation_identity(
                locked_kb,
                frozen_identity,
                source_fingerprints=source_fingerprints,
                classification_root_id=classification_root_id,
                context=context,
            )
            staged, identity_error = _stage_rebuild_candidate(
                locked_kb,
                prepared,
                locked_build,
                materials,
                context,
                operator,
                classification_root_id,
            )
        if identity_error is not None:
            raise identity_error

        _enrich_staged_rebuild(
            kb,
            build,
            context,
            staged,
            operator,
            llm_model_id,
        )

        with transaction.atomic():
            locked_kb, locked_build, materials = _lock_prepared_snapshot(kb, prepared, build)
            source_fingerprints = freeze_source_fingerprints(materials)
            _assert_live_context(locked_kb, context)
            _validate_frozen_generation_identity(
                locked_kb,
                frozen_identity,
                source_fingerprints=source_fingerprints,
                classification_root_id=classification_root_id,
                context=context,
            )
            result = _finalize_staged_rebuild(
                locked_kb,
                locked_build,
                materials,
                context,
                staged,
                classification_root_id,
            )
        return result
    except Exception as exc:
        if context is not None:
            fail_build_generation(
                context,
                build_record=build,
                code=getattr(exc, "code", "generation_rebuild_failed"),
                error=exc,
            )
        build.refresh_from_db()
        is_budget_error = isinstance(exc, WikiBudgetExceeded)
        build.stage = "budget_exhausted" if is_budget_error else "failed"
        build.status = "budget_exhausted" if is_budget_error else "failed"
        build.progress = 100
        build.errors = (
            [
                {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            ]
            if is_budget_error
            else [f"{getattr(exc, 'code', 'generation_rebuild_failed')}: {exc}"]
        )
        if is_budget_error:
            build.budget_trace = {
                "scope": "wiki_rebuild",
                "failure": exc.details,
            }
            build.checkpoint = {
                "stopped_stage": exc.details.get("next_stage") or "budget_exhausted",
                "material_scope": exc.details.get("scope"),
                "partial_map_outputs": list(exc.details.get("partial_map_outputs") or []),
                "map_chunk_count": exc.details.get("map_chunk_count"),
                "completed_map_calls": exc.details.get(
                    "completed_map_calls",
                    0,
                ),
            }
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
        raise


__all__ = ["rebuild_with_generation"]
