"""资料更新的安全合并(P1):资料变更后,受影响页面按贡献类型安全更新。

- 纯 AI 页面(contribution=ai):直接生成新当前版本(change_type=material_update)。
- 含人工编辑(human/mixed):不覆盖当前有效版本,生成候选版本 + 检查事项(交人工审核)。

调用前提:material 已完成"重新摄取"(text_content/ai_summary/版本已更新)。
页面正文的"提议内容"由 generator(page, material) 产出(默认走 LLM,可注入以便测试)。
"""

import logging

from django.db import transaction

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import BuildRecord, KnowledgePage, LLMModel, PageEvidence, PageVersion
from apps.opspilot.services.wiki.check_service import create_candidate, ensure_check

logger = logging.getLogger("opspilot")


def affected_pages(material):
    """返回引用了该资料的有效页面。"""
    page_ids = list(PageEvidence.objects.filter(material=material).values_list("page_id", flat=True).distinct())
    return list(KnowledgePage.objects.filter(id__in=page_ids, status="active"))


@transaction.atomic
def apply_material_update(page, new_body, build_record=None, operator=""):
    """对单个页面应用资料更新结果,返回 (action, obj)。

    纯 AI 页面直接成为新当前版本;含人工编辑的页面生成候选版本待审。
    """
    if page.contribution == "ai":
        last = page.page_versions.order_by("-no").first()
        next_no = (last.no + 1) if last else 1
        page.page_versions.filter(is_current=True).update(is_current=False)
        version = PageVersion.objects.create(
            page=page,
            no=next_no,
            body=new_body,
            change_type="material_update",
            is_current=True,
            build_record=build_record,
            created_by=operator or "",
        )
        page.current_version = version
        page.update_method = "material_update"
        page.save(update_fields=["current_version", "update_method", "updated_at"])
        return "updated", version
    # human / mixed:不污染当前版本,走候选 + 检查
    check = create_candidate(
        page,
        body=new_body,
        reason="资料更新,页面含人工编辑,需人工确认",
        check_type="material_update",
        build_record=build_record,
        created_by=operator,
    )
    return "pending_review", check


def _default_generator(page, material, llm_model_id):
    """默认正文生成:用更新后的资料为该页面重写正文(LLM)。无模型则返回空(跳过)。"""
    if not llm_model_id:
        return ""
    text = (material.ai_summary or material.text_content or "").strip()
    if not text:
        return ""
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        current = page.current_version.body if page.current_version_id else ""
        prompt = (
            "资料已更新,请据此重写指定知识页面的正文,保持标题主题不变,只输出 markdown 正文。\n\n"
            f"# 页面标题\n{page.title}\n\n# 现有正文\n{current[:4000]}\n\n# 更新后的资料\n{text[:6000]}\n"
        )
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


@transaction.atomic
def handle_material_deletion(material, operator=""):
    """删除资料并记录影响:级联移除证据后,把因此失去全部来源的页面标记为待审。

    返回 BuildRecord(trigger=material_delete)。失去来源的页面生成 source_invalid 检查,
    交人工决定补充来源或归档,不自动隐藏页面。
    """
    kb = material.knowledge_base
    page_ids = [p.id for p in affected_pages(material)]  # 删除前捕获
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_delete",
        operator=operator,
        inputs={"material_id": material.id, "material_name": material.name},
        stage="done",
        status="success",
        progress=100,
    )
    material.delete()  # 级联删除该资料的 PageEvidence
    flagged = []
    for page in KnowledgePage.objects.filter(id__in=page_ids, status="active"):
        if not PageEvidence.objects.filter(page=page).exists():
            if ensure_check(kb, "source_invalid", page, suggested_actions=["supplement_source", "archive"]):
                flagged.append(page.id)
    build.counts = {"new": 0, "updated": 0, "unchanged": 0, "pending_review": len(flagged)}
    build.affected_pages = flagged
    build.save(update_fields=["counts", "affected_pages", "updated_at"])
    return build


def propose_update(material, llm_model_id=None, operator="", generator=None):
    """资料更新后,对受影响页面执行安全合并,返回 BuildRecord。"""
    kb = material.knowledge_base
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger="material_update",
        operator=operator,
        inputs={"material_id": material.id},
        stage="generating",
        status="running",
    )
    try:
        gen = generator or (lambda p, m: _default_generator(p, m, llm_model_id))
        updated, pending = [], []
        for page in affected_pages(material):
            new_body = gen(page, material)
            if not (new_body or "").strip():
                continue
            action, _ = apply_material_update(page, new_body, build_record=build, operator=operator)
            (updated if action == "updated" else pending).append(page.id)
        build.counts = {"new": 0, "updated": len(updated), "unchanged": 0, "pending_review": len(pending)}
        build.affected_pages = updated + pending
        build.stage = "done"
        build.status = "success"
        build.progress = 100
        build.save(update_fields=["counts", "affected_pages", "stage", "status", "progress", "updated_at"])
        return build
    except Exception as exc:
        logger.exception("wiki 资料更新失败 material=%s", material.id)
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        raise
