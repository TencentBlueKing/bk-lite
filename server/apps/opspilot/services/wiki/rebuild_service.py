"""Schema 变更全量重建(P6,非向量部分)。

当 Purpose/Schema 调整后,按新 Schema 重建知识页面。**和解策略(默认,可后续按需调整)**:
- 纯 AI 页面(contribution=ai):归档(status=archived)——旧 Schema 产物,由重建生成的新页面取代;
- 含人工编辑(human/mixed):保留为 active,并生成 `schema_changed` 检查事项,提示人工核对是否符合新 Schema;
- 依据各资料按新 Schema 重新生成页面(generator 可注入,默认走 build 的 LLM 生成)。

证据重链接/跨资料去重为简化实现(新页面按资料各自挂证据),完整去重与人工页迁移留待增强。
"""

import logging

from django.db import transaction

from apps.opspilot.models import BuildRecord, KnowledgePage, Material
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
)
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.check_service import ensure_check
from apps.opspilot.services.wiki.material_service import load_parsed_markdown
from apps.opspilot.services.wiki.wikilink_enrichment_service import enrich_pages_wikilinks

logger = logging.getLogger("opspilot")


def _reconcile_existing(kb):
    """归档旧 AI 页面;人工/混合页面保留并标记 schema_changed 待核对。返回 (archived_ids, flagged_ids)。"""
    archived, flagged = [], []
    for page in KnowledgePage.objects.filter(knowledge_base=kb, status="active"):
        if page.contribution == "ai":
            page.status = "archived"
            page.save(update_fields=["status", "updated_at"])
            archived.append(page.id)
        elif ensure_check(kb, "schema_changed", page, suggested_actions=["review", "rebuild_page"]):
            flagged.append(page.id)
    return archived, flagged


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


@transaction.atomic
def rebuild_knowledge_base(kb, llm_model_id=None, operator="", generator=None, build=None):
    """按当前 Schema 全量重建,返回 BuildRecord(trigger=rebuild)。"""
    build = build or create_rebuild_record(kb, operator=operator)
    _mark_rebuild_generating(build, kb, operator)
    try:
        archived, flagged = _reconcile_existing(kb)

        def _material_text(material):
            return (load_parsed_markdown(material) or material.ai_summary or material.text_content or "").strip()

        def _generate_pages(material, text):
            if generator:
                return generator(material) or []
            facts = _llm_extract_facts(text, llm_model_id)
            return _llm_generate_pages(kb, facts or text, llm_model_id)

        new_ids = []
        cascade_ids = []
        maintenance = {}
        source_trace = {"materials": []}
        existing_by_title = _existing_pages_by_title(kb)
        for material in Material.objects.filter(knowledge_base=kb):
            text = _material_text(material)
            source_chunks = _source_chunks_with_offsets(text)
            material_trace = {
                "material_id": material.id,
                "material_name": material.name,
                "chunks": _source_chunk_trace(source_chunks),
                "page_actions": [],
            }
            for pd in _generate_pages(material, text):
                if not pd.get("title"):
                    continue
                pd = _normalize_page_data_title(kb, pd)
                key = _title_key(pd.get("title"), kb)
                page = existing_by_title.get(key)
                locator = _source_locator_for_page(material, text, pd, chunks=source_chunks)
                if not page:
                    page = _create_ai_page(
                        kb,
                        material,
                        build,
                        pd,
                        update_method="rebuild",
                        change_type="rebuild",
                        operator=operator,
                        locator=locator,
                    )
                    existing_by_title[key] = page
                    new_ids.append(page.id)
                    cascade_ids.append(page.id)
                    action = "new"
                elif page.contribution == "ai":
                    action = _merge_ai_page(
                        page,
                        material,
                        build,
                        pd,
                        operator=operator,
                        update_method="rebuild",
                        change_type="rebuild",
                        locator=locator,
                    )
                    if action == "updated":
                        cascade_ids.append(page.id)
                elif ensure_check(kb, "cannot_merge", page, suggested_actions=["review", "rebuild_page"]):
                    action = "pending_review"
                    flagged.append(page.id)
                else:
                    action = "unchanged"
                material_trace["page_actions"].append(_page_action_trace(page, action, locator))
            source_trace["materials"].append(material_trace)

        if cascade_ids:
            enriched_ids = enrich_pages_wikilinks(
                kb,
                cascade_ids,
                llm_model_id,
                _invoke_llm,
                build_record=build,
                operator=operator,
                canonicalize=lambda value: _canonical_title(kb, value),
                alias_terms_resolver=lambda value: _title_alias_terms_for_enrichment(kb, value),
            )
            cascade_ids = list(dict.fromkeys([*cascade_ids, *enriched_ids]))
            maintenance = cascade(kb, cascade_ids, "build")

        build.inputs = {**(build.inputs or {}), "source_trace": source_trace}
        build.counts = {
            "new": len(new_ids),
            "archived": len(archived),
            "unchanged": 0,
            "pending_review": len(flagged),
        }
        build.affected_pages = new_ids
        build.maintenance = maintenance
        build.stage = "done"
        build.status = "success"
        build.progress = 100
        build.save(update_fields=["inputs", "counts", "affected_pages", "maintenance", "stage", "status", "progress", "updated_at"])
        return build
    except Exception as exc:
        logger.exception("wiki 全量重建失败 kb=%s", kb.id)
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        raise
