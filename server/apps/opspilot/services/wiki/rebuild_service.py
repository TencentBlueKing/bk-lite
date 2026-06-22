"""Schema 变更全量重建(P6,非向量部分)。

当 Purpose/Schema 调整后,按新 Schema 重建知识页面。**和解策略(默认,可后续按需调整)**:
- 纯 AI 页面(contribution=ai):归档(status=archived)——旧 Schema 产物,由重建生成的新页面取代;
- 含人工编辑(human/mixed):保留为 active,并生成 `schema_changed` 检查事项,提示人工核对是否符合新 Schema;
- 依据各资料按新 Schema 重新生成页面(generator 可注入,默认走 build 的 LLM 生成)。

证据重链接/跨资料去重为简化实现(新页面按资料各自挂证据),完整去重与人工页迁移留待增强。
"""

import logging

from django.db import transaction

from apps.opspilot.models import BuildRecord, KnowledgePage, Material, PageEvidence, PageVersion
from apps.opspilot.services.wiki.build_service import _llm_generate_pages
from apps.opspilot.services.wiki.check_service import ensure_check
from apps.opspilot.services.wiki.relation_service import rebuild_relations

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


@transaction.atomic
def rebuild_knowledge_base(kb, llm_model_id=None, operator="", generator=None):
    """按当前 Schema 全量重建,返回 BuildRecord(trigger=rebuild)。"""
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="rebuild",
        operator=operator,
        inputs={"schema_len": len(kb.schema_md or "")},
        stage="generating",
        status="running",
    )
    try:
        archived, flagged = _reconcile_existing(kb)

        def _default_gen(material):
            text = (material.ai_summary or material.text_content or "").strip()
            return _llm_generate_pages(kb, text, llm_model_id)

        gen = generator or _default_gen
        new_ids = []
        for material in Material.objects.filter(knowledge_base=kb):
            for pd in gen(material) or []:
                if not pd.get("title"):
                    continue
                page = KnowledgePage.objects.create(
                    knowledge_base=kb,
                    page_type=pd.get("page_type", "concept"),
                    title=pd["title"],
                    tags=pd.get("tags", []) or [],
                    contribution="ai",
                    update_method="rebuild",
                )
                version = PageVersion.objects.create(
                    page=page,
                    no=1,
                    body=pd.get("body", "") or "",
                    change_type="rebuild",
                    is_current=True,
                    build_record=build,
                )
                page.current_version = version
                page.save(update_fields=["current_version"])
                PageEvidence.objects.create(page=page, material=material, material_version=material.current_version)
                new_ids.append(page.id)

        if new_ids:
            rebuild_relations(kb)

        build.counts = {"new": len(new_ids), "archived": len(archived), "unchanged": 0, "pending_review": len(flagged)}
        build.affected_pages = new_ids
        build.stage = "done"
        build.status = "success"
        build.progress = 100
        build.save(update_fields=["counts", "affected_pages", "stage", "status", "progress", "updated_at"])
        return build
    except Exception as exc:
        logger.exception("wiki 全量重建失败 kb=%s", kb.id)
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        raise
