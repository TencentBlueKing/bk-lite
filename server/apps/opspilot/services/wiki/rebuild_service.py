"""Schema 变更后的知识库全量重建。

当 Purpose/Schema 调整后，按新 Schema 重建知识页面：
- 纯 AI 页面(contribution=ai):归档(status=archived)——旧 Schema 产物,由重建生成的新页面取代;
- 含人工编辑(human/mixed):保留为 active，不因确定性重建创建审批;
- 依据各资料按新 Schema 重新生成页面(generator 可注入,默认走 build 的 LLM 生成)。

只有真实知识结论冲突进入决策；归档页的关系与向量由级联维护自动清理。
"""

import logging

from django.db import transaction

from apps.opspilot.models import BuildRecord, KnowledgePage, Material, MaterialVersion
from apps.opspilot.services.wiki.build_service import (
    _canonical_title,
    _create_ai_page,
    _existing_pages_by_title,
    _invoke_llm,
    _llm_extract_facts,
    _llm_generate_pages,
    _merge_ai_page,
    _normalize_page_data_title,
    _page_action_trace,
    _source_chunk_trace,
    _source_chunks_with_offsets,
    _source_locator_for_page,
    _title_alias_terms_for_enrichment,
    _title_key,
    resolve_knowledge_conflict,
)
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.decision_service import compute_schema_fingerprint
from apps.opspilot.services.wiki.material_service import load_parsed_markdown
from apps.opspilot.services.wiki.wikilink_enrichment_service import enrich_pages_wikilinks

logger = logging.getLogger("opspilot")

_MAINTENANCE_METRIC_KEYS = (
    "relations",
    "indexed_pages",
    "indexed_chunks",
    "cleared_pages",
    "auto_resolved",
    "pruned_checks",
    "pruned_build_records",
)


def _combine_maintenance_stage(archive_stage, generated_stage):
    components = {
        name: dict(stage)
        for name, stage in (
            ("archive", archive_stage),
            ("generated", generated_stage),
        )
        if isinstance(stage, dict)
    }
    if len(components) == 1:
        return dict(next(iter(components.values())))
    statuses = {stage.get("status") for stage in components.values()}
    if "failed" in statuses:
        status = "failed"
    elif "pending" in statuses or "running" in statuses:
        status = "pending"
    elif "success" in statuses:
        status = "success"
    else:
        status = "skipped"
    result = {
        "status": status,
        "count": sum(stage.get("count", 0) for stage in components.values()),
        "components": components,
    }
    errors = list(dict.fromkeys(stage.get("error") for stage in components.values() if stage.get("error")))
    if errors:
        result["error"] = "; ".join(errors)
    return result


def _combine_rebuild_maintenance(
    archive_maintenance,
    generated_maintenance,
    archived_page_ids,
    generated_page_ids,
    *,
    event="rebuild",
):
    """Combine delete-style archive cleanup and build-style generated-page maintenance."""
    if not archive_maintenance:
        return generated_maintenance or {}

    archive_maintenance = dict(archive_maintenance)
    generated_maintenance = dict(generated_maintenance or {})
    archive_stages = archive_maintenance.get("stages") if isinstance(archive_maintenance.get("stages"), dict) else {}
    generated_stages = generated_maintenance.get("stages") if isinstance(generated_maintenance.get("stages"), dict) else {}
    stages = {
        stage: _combine_maintenance_stage(archive_stages.get(stage), generated_stages.get(stage))
        for stage in dict.fromkeys([*archive_stages, *generated_stages])
    }
    maintenance_statuses = {
        archive_maintenance.get("status"),
        generated_maintenance.get("status"),
    }
    has_failure = "partial" in maintenance_statuses or any(stage.get("status") == "failed" for stage in stages.values())
    has_pending = bool({"pending", "running"}.intersection(maintenance_statuses))
    result = {
        "status": "partial" if has_failure else "pending" if has_pending else "success",
        "event": event,
        "affected_page_ids": list(dict.fromkeys([*archived_page_ids, *generated_page_ids])),
        "stages": stages,
        "archive": archive_maintenance,
    }
    if generated_maintenance:
        result["generated"] = generated_maintenance
    for key in _MAINTENANCE_METRIC_KEYS:
        values = [
            maintenance.get(key) for maintenance in (archive_maintenance, generated_maintenance) if isinstance(maintenance.get(key), (int, float))
        ]
        if values:
            result[key] = sum(values)
    return result


def _reconcile_existing(kb):
    """归档旧 AI 页面；人工/混合页面保留，确定性重建不创建审批。"""
    archived = []
    pages = KnowledgePage.objects.select_for_update().filter(knowledge_base=kb, status="active").order_by("id")
    for page in pages:
        if page.contribution == "ai":
            page.status = "archived"
            page.save(update_fields=["status", "updated_at"])
            archived.append(page.id)
    return archived, []


def running_build_record(kb):
    return BuildRecord.objects.filter(knowledge_base=kb, status="running").order_by("-id").first()


def create_rebuild_record(kb, operator=""):
    return BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="rebuild",
        operator=operator,
        inputs={"schema_len": len(kb.schema_md or "")},
        stage="queued",
        status="running",
    )


def _mark_rebuild_generating(build, kb, operator):
    build.operator = operator or build.operator
    build.inputs = {"schema_len": len(kb.schema_md or ""), "source_trace": {"materials": []}}
    build.stage = "generating"
    build.status = "running"
    build.progress = 0
    build.errors = []
    build.save(update_fields=["operator", "inputs", "stage", "status", "progress", "errors", "updated_at"])


def _material_snapshot_hash(material):
    current_version = getattr(material, "current_version", None)
    return (getattr(current_version, "content_hash", "") or material.content_hash or "").strip()


def _material_text(material):
    return (load_parsed_markdown(material) or material.ai_summary or material.text_content or "").strip()


def _generate_pages(kb, material, text, llm_model_id, generator):
    if generator is not None:
        return generator(material) or []
    facts = _llm_extract_facts(text, llm_model_id)
    return _llm_generate_pages(kb, facts or text, llm_model_id) or []


def _prepare_rebuild(kb, llm_model_id, generator):
    """在任何核心写事务前完成全部资料读取、切块与 LLM 生成。"""
    prepared = []
    schema_fingerprint = compute_schema_fingerprint(kb)
    materials = list(Material.objects.filter(knowledge_base=kb).select_related("current_version").order_by("id"))
    for material in materials:
        text = _material_text(material)
        source_chunks = _source_chunks_with_offsets(text)
        pages = []
        for page_data in _generate_pages(
            kb,
            material,
            text,
            llm_model_id,
            generator,
        ):
            if not page_data.get("title"):
                continue
            normalized = _normalize_page_data_title(kb, page_data)
            locator = _source_locator_for_page(
                material,
                text,
                normalized,
                chunks=source_chunks,
            )
            pages.append({"page_data": normalized, "locator": locator})
        prepared.append(
            {
                "material": material,
                "material_id": material.id,
                "material_version_id": material.current_version_id,
                "material_content_hash": _material_snapshot_hash(material),
                "material_updated_at": material.updated_at,
                "source_chunks": source_chunks,
                "pages": pages,
            }
        )
    return {
        "schema_fingerprint": schema_fingerprint,
        "material_ids": [material.id for material in materials],
        "materials": prepared,
    }


def _pending_rebuild_maintenance(page_ids, event, **metadata):
    page_ids = list(page_ids)
    if not page_ids:
        return {}
    return {
        "status": "pending",
        "event": event,
        "affected_page_ids": page_ids,
        "stages": {},
        **metadata,
    }


def _failed_rebuild_maintenance(page_ids, event, exc, **metadata):
    error = str(exc)
    return {
        "status": "partial",
        "event": event,
        "affected_page_ids": list(page_ids),
        "stages": {"cascade": {"status": "failed", "error": error}},
        "error": error,
        **metadata,
    }


def _run_rebuild_cascade(kb, page_ids, event, **kwargs):
    page_ids = list(page_ids)
    if not page_ids:
        return {}
    metadata = {}
    if "deleted_titles" in kwargs:
        metadata["deleted_titles"] = list(kwargs["deleted_titles"] or [])
    try:
        result = cascade(kb, page_ids, event, **kwargs) or {}
    except Exception as exc:  # noqa: BLE001 - 核心提交后维护必须降级为可重试 partial
        logger.exception(
            "wiki 全量重建级联维护异常 kb=%s event=%s",
            kb.id,
            event,
        )
        return _failed_rebuild_maintenance(
            page_ids,
            event,
            exc,
            **metadata,
        )
    if metadata:
        return {**result, **metadata}
    return result


def _add_maintenance_failure(maintenance, stage, exc, page_ids, event):
    result = dict(maintenance or {})
    result.setdefault("event", event)
    result.setdefault("affected_page_ids", list(page_ids))
    stages = dict(result.get("stages") or {})
    stages[stage] = {"status": "failed", "error": str(exc)}
    result["stages"] = stages
    result["status"] = "partial"
    result.setdefault("error", str(exc))
    return result


def _maintenance_errors(maintenance):
    errors = []

    def collect(value):
        if isinstance(value, dict):
            error = value.get("error")
            if error and str(error) not in errors:
                errors.append(str(error))
            for key, item in value.items():
                if key != "error":
                    collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(maintenance)
    return [error for error in errors if not (";" in error and all(part.strip() in errors for part in error.split(";") if part.strip()))]


def _mark_rebuild_failed(build, exc):
    failed_build = BuildRecord.objects.get(pk=build.pk)
    failed_build.stage = "failed"
    failed_build.status = "failed"
    failed_build.errors = [str(exc)]
    failed_build.save(update_fields=["stage", "status", "errors", "updated_at"])


def _apply_prepared_rebuild(kb, prepared, build, operator):
    """一次短事务原子提交归档、页面结果、冲突候选与待维护记录。"""
    with transaction.atomic():
        locked_kb = kb.__class__.objects.select_for_update().get(pk=kb.pk)
        locked_build = BuildRecord.objects.select_for_update().get(
            pk=build.pk,
            knowledge_base=locked_kb,
        )
        if compute_schema_fingerprint(locked_kb) != prepared["schema_fingerprint"]:
            raise RuntimeError("重建期间 Schema 已变化，请重新发起重建")

        prepared_material_ids = prepared["material_ids"]
        prepared = prepared["materials"]
        locked_materials = {
            material.id: material
            for material in Material.objects.select_for_update()
            .filter(
                knowledge_base=locked_kb,
            )
            .order_by("id")
        }
        live_material_ids = set(locked_materials)
        frozen_material_ids = set(prepared_material_ids)
        if frozen_material_ids - live_material_ids:
            raise RuntimeError("重建期间资料已被删除，请重新发起重建")
        if live_material_ids - frozen_material_ids:
            raise RuntimeError("重建期间资料集合已变化，请重新发起重建")
        current_version_ids = {material.current_version_id for material in locked_materials.values() if material.current_version_id}
        locked_versions = {
            version.id: version
            for version in MaterialVersion.objects.select_for_update().filter(
                id__in=current_version_ids,
                material_id__in=prepared_material_ids,
            )
        }
        if set(locked_versions) != current_version_ids:
            raise RuntimeError("重建期间资料版本已变化，请重新发起重建")
        for material in locked_materials.values():
            material.current_version = locked_versions.get(
                material.current_version_id,
            )

        for prepared_material in prepared:
            material = locked_materials[prepared_material["material_id"]]
            if material.current_version_id != prepared_material["material_version_id"]:
                raise RuntimeError("重建期间资料版本已变化，请重新发起重建")
            if (
                _material_snapshot_hash(material) != prepared_material["material_content_hash"]
                or material.updated_at != prepared_material["material_updated_at"]
            ):
                raise RuntimeError("重建期间资料内容已变化，请重新发起重建")
            prepared_material["material"] = material

        archived, _flagged = _reconcile_existing(locked_kb)
        archived_pages = list(KnowledgePage.objects.filter(id__in=archived).order_by("id"))
        archived_titles = [page.title for page in archived_pages]

        new_ids = []
        cascade_ids = []
        source_trace = {"materials": []}
        existing_by_title = _existing_pages_by_title(locked_kb)
        unchanged_count = 0
        pending_count = 0

        for prepared_material in prepared:
            material = prepared_material["material"]
            material_trace = {
                "material_id": material.id,
                "material_name": material.name,
                "chunks": _source_chunk_trace(prepared_material["source_chunks"]),
                "page_actions": [],
            }
            for prepared_page in prepared_material["pages"]:
                page_data = prepared_page["page_data"]
                locator = prepared_page["locator"]
                key = _title_key(page_data.get("title"), locked_kb)
                page = existing_by_title.get(key)
                if not page:
                    page = _create_ai_page(
                        locked_kb,
                        material,
                        locked_build,
                        page_data,
                        update_method="rebuild",
                        change_type="rebuild",
                        operator=operator,
                        locator=locator,
                    )
                    existing_by_title[key] = page
                    new_ids.append(page.id)
                    cascade_ids.append(page.id)
                    action = "new"
                    decision_trace = {}
                elif page.contribution == "ai":
                    action = _merge_ai_page(
                        page,
                        material,
                        locked_build,
                        page_data,
                        operator=operator,
                        update_method="rebuild",
                        change_type="rebuild",
                        locator=locator,
                    )
                    if action == "updated":
                        cascade_ids.append(page.id)
                    decision_trace = {}
                else:
                    action, decision_trace = resolve_knowledge_conflict(
                        page,
                        material,
                        locked_build,
                        page_data.get("body", "") or "",
                        operator=operator,
                        check_type="cannot_merge",
                        reason="全量重建产生了不同知识结论，需人工选择",
                        related={
                            "pages": [page.id],
                            "materials": [material.id],
                        },
                        locator=locator,
                    )
                if action == "pending_review":
                    pending_count += 1
                elif action == "unchanged":
                    unchanged_count += 1
                page_trace = _page_action_trace(page, action, locator)
                page_trace.update(decision_trace)
                material_trace["page_actions"].append(page_trace)
            source_trace["materials"].append(material_trace)

        archived = list(dict.fromkeys(archived))
        cascade_ids = list(dict.fromkeys(cascade_ids))
        pending_maintenance = _combine_rebuild_maintenance(
            _pending_rebuild_maintenance(
                archived,
                "page_delete",
                deleted_titles=archived_titles,
            ),
            _pending_rebuild_maintenance(cascade_ids, "build"),
            archived,
            cascade_ids,
        )
        locked_build.inputs = {
            **(locked_build.inputs or {}),
            "source_trace": source_trace,
        }
        locked_build.counts = {
            "new": len(new_ids),
            "archived": len(archived),
            "unchanged": unchanged_count,
            "pending_review": pending_count,
        }
        locked_build.affected_pages = list(dict.fromkeys([*archived, *cascade_ids]))
        locked_build.maintenance = pending_maintenance
        locked_build.stage = "done"
        locked_build.status = "partial"
        locked_build.progress = 100
        locked_build.errors = []
        locked_build.save(
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
        return {
            "archived_page_ids": archived,
            "archived_titles": archived_titles,
            "generated_page_ids": cascade_ids,
        }


def _run_rebuild_maintenance(
    kb,
    build,
    core_result,
    llm_model_id,
    operator,
):
    archived_page_ids = list(core_result["archived_page_ids"])
    archived_titles = list(core_result["archived_titles"])
    generated_page_ids = list(core_result["generated_page_ids"])
    enrichment_error = None

    if generated_page_ids:
        try:
            enriched_ids = enrich_pages_wikilinks(
                kb,
                generated_page_ids,
                llm_model_id,
                _invoke_llm,
                build_record=build,
                operator=operator,
                canonicalize=lambda value: _canonical_title(kb, value),
                alias_terms_resolver=lambda value: _title_alias_terms_for_enrichment(kb, value),
            )
            generated_page_ids = list(dict.fromkeys([*generated_page_ids, *(enriched_ids or [])]))
        except Exception as exc:  # noqa: BLE001 - 派生维护失败不回滚核心页面
            enrichment_error = exc
            logger.exception(
                "wiki 全量重建 wikilink 维护异常 kb=%s",
                kb.id,
            )

    archive_maintenance = _run_rebuild_cascade(
        kb,
        archived_page_ids,
        "page_delete",
        deleted_titles=archived_titles,
    )
    generated_maintenance = _run_rebuild_cascade(
        kb,
        generated_page_ids,
        "build",
    )
    if enrichment_error is not None:
        generated_maintenance = _add_maintenance_failure(
            generated_maintenance,
            "wikilink_enrichment",
            enrichment_error,
            generated_page_ids,
            "build",
        )

    maintenance = _combine_rebuild_maintenance(
        archive_maintenance,
        generated_maintenance,
        archived_page_ids,
        generated_page_ids,
    )
    finished_build = BuildRecord.objects.get(pk=build.pk)
    finished_build.affected_pages = list(dict.fromkeys([*archived_page_ids, *generated_page_ids]))
    finished_build.maintenance = maintenance
    finished_build.errors = _maintenance_errors(maintenance)
    finished_build.stage = "done"
    finished_build.status = maintenance.get("status", "success")
    finished_build.progress = 100
    finished_build.save(
        update_fields=[
            "affected_pages",
            "maintenance",
            "errors",
            "stage",
            "status",
            "progress",
            "updated_at",
        ]
    )
    return finished_build


def _mark_unexpected_maintenance_failure(build, core_result, exc):
    """兜住维护编排自身异常，保持已提交核心结果并提供整批重试入口。"""
    archived_page_ids = list(core_result["archived_page_ids"])
    generated_page_ids = list(core_result["generated_page_ids"])
    maintenance = _combine_rebuild_maintenance(
        _failed_rebuild_maintenance(
            archived_page_ids,
            "page_delete",
            exc,
            deleted_titles=list(core_result["archived_titles"]),
        ),
        _failed_rebuild_maintenance(
            generated_page_ids,
            "build",
            exc,
        ),
        archived_page_ids,
        generated_page_ids,
    )
    partial_build = BuildRecord.objects.get(pk=build.pk)
    partial_build.maintenance = maintenance
    partial_build.errors = [str(exc)]
    partial_build.stage = "done"
    partial_build.status = "partial"
    partial_build.progress = 100
    partial_build.save(
        update_fields=[
            "maintenance",
            "errors",
            "stage",
            "status",
            "progress",
            "updated_at",
        ]
    )
    return partial_build


def rebuild_knowledge_base(
    kb,
    llm_model_id=None,
    operator="",
    generator=None,
    build=None,
):
    """预生成、原子应用，再在提交后 best-effort 维护派生结构。"""
    build = build or create_rebuild_record(kb, operator=operator)
    _mark_rebuild_generating(build, kb, operator)
    try:
        prepared = _prepare_rebuild(kb, llm_model_id, generator)
        core_result = _apply_prepared_rebuild(
            kb,
            prepared,
            build,
            operator,
        )
    except Exception as exc:
        logger.exception("wiki 全量重建失败 kb=%s", kb.id)
        _mark_rebuild_failed(build, exc)
        raise

    try:
        return _run_rebuild_maintenance(
            kb,
            build,
            core_result,
            llm_model_id,
            operator,
        )
    except Exception as exc:  # noqa: BLE001 - 核心已提交，只能标记 partial
        logger.exception("wiki 全量重建维护收口失败 kb=%s", kb.id)
        return _mark_unexpected_maintenance_failure(
            build,
            core_result,
            exc,
        )
