"""知识构建管道:资料 → 知识页面(对标 llm_wiki 两步法)。

Stage1 抽取事实:从资料抽取结构化要点(去噪、聚焦可复用事实)。
Stage2 生成页面:依据 Purpose/Schema 从事实生成互联知识页面。
创建页面 + 首版本(ai_create)+ 资料证据,并记录构建过程到 BuildRecord。
"""

import json
import logging

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import BuildRecord, KnowledgePage, LLMModel, PageEvidence, PageVersion

logger = logging.getLogger("opspilot")


def _invoke_llm(llm_model_id, prompt):
    """单次隔离式 LLM 调用,返回文本;无模型/失败返回 ""。测试可 monkeypatch。"""
    if not llm_model_id:
        return ""
    try:
        llm = LLMModel.objects.get(id=llm_model_id)
        request = BasicLLMRequest(
            openai_api_base=llm.openai_api_base,
            openai_api_key=llm.openai_api_key,
            model=llm.model_name,
            temperature=0.2,
            user_message=prompt,
        )
        return LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}]) or ""
    except Exception:
        logger.exception("wiki LLM 调用失败")
        return ""


def _llm_extract_facts(text, llm_model_id):
    """Stage1:从资料抽取结构化要点(每行一条事实)。无模型/空文本返回 ""。"""
    if not llm_model_id or not (text or "").strip():
        return ""
    prompt = (
        "你是知识抽取助手。请从下面的资料中抽取稳定、可复用、对运维有价值的关键事实/要点,"
        "去除噪音与临时细节,每行一条,只输出要点列表本身,不要解释。\n\n"
        f"# 资料\n{text[:8000]}\n"
    )
    return _invoke_llm(llm_model_id, prompt).strip()


def _llm_generate_pages(kb, source_text, llm_model_id):
    """Stage2:依据 Purpose/Schema 从(已抽取的)要点生成页面列表。

    返回 [{"page_type","title","tags","body"}, ...];无模型或解析失败时返回 []。
    """
    if not llm_model_id or not (source_text or "").strip():
        return []
    prompt = (
        "你是企业知识库构建助手。请依据下面的 Purpose 与 Schema,从已抽取的要点生成知识页面。\n"
        '只输出 JSON,格式为 {"pages":[{"page_type":"...","title":"...","tags":["..."],"body":"markdown"}]}。\n'
        'page_type 必须来自 Schema 定义的类型;无可提取内容时输出 {"pages":[]}。\n\n'
        f"# Purpose\n{kb.purpose_md}\n\n# Schema\n{kb.schema_md}\n\n# 要点\n{source_text[:8000]}\n"
    )
    return _parse_pages(_invoke_llm(llm_model_id, prompt))


def _parse_pages(content):
    """从 LLM 输出中解析 pages 列表,容忍代码块包裹。"""
    raw = (content or "").strip()
    if "```" in raw:
        # 去掉 ```json ... ``` 包裹
        raw = raw.split("```", 2)[1] if raw.count("```") >= 2 else raw
        if raw.lstrip().lower().startswith("json"):
            raw = raw.lstrip()[4:]
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        return []
    data = json.loads(raw[start : end + 1])
    pages = data.get("pages", [])
    return [p for p in pages if isinstance(p, dict) and p.get("title")]


def build_from_material(material, llm_model_id=None, operator="", trigger="material"):
    """从一份资料构建知识页面。返回 BuildRecord。"""
    kb = material.knowledge_base
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=trigger,
        operator=operator,
        inputs={"material_id": material.id},
        stage="generating",
        status="running",
    )
    try:
        text = (material.ai_summary or material.text_content or "").strip()
        # 两步法:Stage1 抽取要点 → Stage2 依据 Schema 生成页面(抽取失败则回退原文)
        facts = _llm_extract_facts(text, llm_model_id)
        pages_data = _llm_generate_pages(kb, facts or text, llm_model_id)
        affected = []
        for pd in pages_data:
            page = KnowledgePage.objects.create(
                knowledge_base=kb,
                page_type=pd.get("page_type", "concept"),
                title=pd["title"],
                tags=pd.get("tags", []) or [],
                contribution="ai",
                update_method="ai_create",
            )
            version = PageVersion.objects.create(
                page=page,
                no=1,
                body=pd.get("body", "") or "",
                change_type="ai_create",
                is_current=True,
                build_record=build,
            )
            page.current_version = version
            page.save(update_fields=["current_version"])
            PageEvidence.objects.create(page=page, material=material, material_version=material.current_version)
            affected.append(page.id)
        if affected:
            # 新页面与同库其他页面建立关系(共享资料/正文引用)
            from apps.opspilot.services.wiki.relation_service import rebuild_relations

            rebuild_relations(kb)
        build.counts = {"new": len(affected), "updated": 0, "unchanged": 0, "pending_review": 0}
        build.affected_pages = affected
        build.stage = "done"
        build.status = "success"
        build.progress = 100
        build.save(update_fields=["counts", "affected_pages", "stage", "status", "progress", "updated_at"])
        return build
    except Exception as exc:
        logger.exception("wiki 构建失败 material=%s", material.id)
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        raise
