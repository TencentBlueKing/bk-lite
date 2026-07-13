"""知识构建管道:资料 → 知识页面(对标 llm_wiki 两步法)。

Stage1 抽取事实:从资料抽取结构化要点(去噪、聚焦可复用事实)。
Stage2 生成页面:依据 Purpose/Schema 从事实生成互联知识页面。
创建页面 + 首版本(ai_create)+ 资料证据,并记录构建过程到 BuildRecord。
"""

import json
import logging
import os

from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models import BuildRecord, KnowledgePage, LLMModel, PageEvidence, PageVersion
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.check_service import create_candidate
from apps.opspilot.services.wiki.material_service import load_parsed_markdown
from apps.opspilot.services.wiki.text_utils import split_text_for_llm
from apps.opspilot.services.wiki.title_service import canonical_title as _canonical_title
from apps.opspilot.services.wiki.title_service import compact_title_key
from apps.opspilot.services.wiki.title_service import title_alias_terms_for_enrichment as _title_alias_terms_for_enrichment
from apps.opspilot.services.wiki.wikilink_enrichment_service import enrich_pages_wikilinks

logger = logging.getLogger("opspilot")

_split_text_for_llm = split_text_for_llm
_WIKI_LLM_TIMEOUT_SECONDS = 300.0
_EVIDENCE_SNIPPET_CHARS = 500
_SOURCE_CHUNK_PREVIEW_CHARS = 240


def _wiki_llm_timeout():
    raw_timeout = os.getenv("WIKI_LLM_INVOKE_TIMEOUT") or os.getenv("LLM_INVOKE_TIMEOUT")
    if not raw_timeout:
        return _WIKI_LLM_TIMEOUT_SECONDS
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return _WIKI_LLM_TIMEOUT_SECONDS
    return max(timeout, 1.0)


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
            extra_config={"timeout": _wiki_llm_timeout()},
        )
        return LLMClientFactory.invoke_isolated(request, [{"role": "user", "content": prompt}]) or ""
    except Exception:
        logger.exception("wiki LLM 调用失败")
        return ""


def _llm_extract_facts(text, llm_model_id):
    """Stage1:从资料全文分块抽取结构化要点(每行一条事实)。"""
    if not llm_model_id or not (text or "").strip():
        return ""
    chunks = _split_text_for_llm(text)
    facts = []
    for idx, chunk in enumerate(chunks, start=1):
        prompt = (
            "你是知识抽取助手。请从下面的资料片段中抽取稳定、可复用、对运维有价值的关键事实/要点,"
            "去除噪音与临时细节,每行一条,只输出要点列表本身,不要解释。\n"
            "注意:这是同一份资料的分块处理,不得因为只看到当前片段就判断全文结束。\n\n"
            f"# 资料片段 {idx}/{len(chunks)}\n{chunk}\n"
        )
        result = _invoke_llm(llm_model_id, prompt).strip()
        if result:
            facts.append(result)
    return "\n".join(facts)


def _llm_generate_pages(kb, source_text, llm_model_id):
    """Stage2:依据 Purpose/Schema 从(已抽取的)要点生成页面列表。

    返回 [{"page_type","title","tags","body"}, ...];无模型或解析失败时返回 []。
    """
    if not llm_model_id or not (source_text or "").strip():
        return []
    pages = []
    chunks = _split_text_for_llm(source_text)
    for idx, chunk in enumerate(chunks, start=1):
        prompt = (
            "你是企业知识库构建助手。请依据下面的 Purpose 与 Schema,从已抽取的要点生成知识页面。\n"
            '只输出 JSON,格式为 {"pages":[{"page_type":"...","title":"...","tags":["..."],"body":"markdown"}]}。\n'
            'page_type 必须来自 Schema 定义的类型;无可提取内容时输出 {"pages":[]}。\n'
            "生成原则:不要只输出总览页面;对资料中反复出现的产品、平台、组件、模块、能力中心、"
            "依赖项、服务、表格行中的核心对象,应优先拆成独立实体页或概念页。\n"
            "同一对象的缩写、英文名、中文全称必须使用同一个页面标题;优先使用中文全称,"
            "例如 CMDB 与 配置平台 使用 配置平台,JOB 与 作业平台 使用 作业平台,不要分别建页。\n"
            "页面正文应使用 [[目标页面标题]] 引用相关页面,便于后续关系图谱建边。\n"
            "注意:这是同一份资料的分块处理,如果当前片段补充了已有主题,可以输出同名页面,"
            "系统会合并同名页面内容。\n\n"
            f"# Purpose\n{kb.purpose_md}\n\n# Schema\n{kb.schema_md}\n\n# 要点片段 {idx}/{len(chunks)}\n{chunk}\n"
        )
        pages.extend(_parse_pages(_invoke_llm(llm_model_id, prompt)))
    return _merge_pages(pages, kb=kb)


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
    try:
        data = json.loads(raw[start : end + 1])
    except (TypeError, ValueError):
        logger.warning("wiki 页面生成 JSON 解析失败")
        return []
    pages = data.get("pages", [])
    return [p for p in pages if isinstance(p, dict) and p.get("title")]


def _normalize_page_data_title(kb, page_data):
    data = dict(page_data or {})
    title = _canonical_title(kb, data.get("title"))
    if title:
        data["title"] = title
    return data


def _merge_pages(pages, kb=None):
    """Merge duplicate titles produced by different chunks of the same material."""
    merged = {}
    order = []
    for page in pages:
        title = _canonical_title(kb, page.get("title")) if kb else (page.get("title") or "").strip()
        if not title:
            continue
        key = _title_key(title, kb)
        tags = [tag for tag in page.get("tags", []) or [] if tag]
        body = (page.get("body") or "").strip()
        if key not in merged:
            merged[key] = {
                "page_type": page.get("page_type", "concept"),
                "title": title,
                "tags": list(dict.fromkeys(tags)),
                "body": body,
            }
            order.append(key)
            continue
        current = merged[key]
        current["tags"] = list(dict.fromkeys([*current.get("tags", []), *tags]))
        if body and body not in current.get("body", ""):
            current["body"] = "\n\n".join(part for part in [current.get("body", ""), body] if part)
    return [merged[key] for key in order]


def _title_key(title, kb=None):
    title = _canonical_title(kb, title) if kb else title
    return (title or "").strip().lower()


def _next_version_no(page):
    last = page.page_versions.order_by("-no").first()
    return (last.no + 1) if last else 1


def _existing_pages_by_title(kb):
    pages = (
        KnowledgePage.objects.filter(
            knowledge_base=kb,
            status__in=["active", "source_invalid"],
        )
        .select_related("current_version")
        .order_by("id")
    )
    result = {}
    for page in pages:
        key = _title_key(page.title, kb)
        if key and key not in result:
            result[key] = page
    return result


def _source_chunks_with_offsets(text):
    normalized = (text or "").strip()
    if not normalized:
        return []
    chunks = _split_text_for_llm(normalized)
    result = []
    search_start = 0
    for idx, chunk in enumerate(chunks):
        start = normalized.find(chunk, search_start)
        if start == -1:
            start = normalized.find(chunk)
        if start == -1:
            start = search_start
        end = start + len(chunk)
        result.append({"index": idx, "start": start, "end": end, "text": chunk})
        search_start = max(start + 1, end - 1)
    return result


def _locator_score(chunk_text, page_data):
    chunk = (chunk_text or "").lower()
    if not chunk:
        return 0
    score = 0
    title = (page_data.get("title") or "").strip().lower()
    if title and title in chunk:
        score += 50
    for tag in page_data.get("tags", []) or []:
        tag = (tag or "").strip().lower()
        if tag and tag in chunk:
            score += 10
    body = page_data.get("body", "") or ""
    for line in body.splitlines():
        line = line.strip().lower()
        if len(line) < 8:
            continue
        if line in chunk:
            score += max(5, min(len(line), 80))
            continue
        for part in _locator_text_parts(line):
            part = part.strip()
            if len(part) >= 8 and part in chunk:
                score += max(5, min(len(part), 40))
    return score


def _locator_terms(page_data):
    terms = []
    title = (page_data.get("title") or "").strip()
    if title:
        terms.append(title)
    terms.extend((tag or "").strip() for tag in page_data.get("tags", []) or [] if (tag or "").strip())
    body = page_data.get("body", "") or ""
    for line in body.splitlines():
        line = line.strip()
        if len(line) >= 8:
            terms.append(line)
        for part in _locator_text_parts(line):
            part = part.strip()
            if len(part) >= 8:
                terms.append(part)
    return list(dict.fromkeys(term for term in terms if term))


def _locator_text_parts(text):
    normalized = text
    for separator in ("。", ".", "，", ",", "；", ";", "：", ":", " ", "\t"):
        normalized = normalized.replace(separator, "\n")
    return normalized.splitlines()


def _locator_snippet(chunk_text, page_data):
    chunk = chunk_text or ""
    lowered = chunk.lower()
    match_at = 0
    for term in sorted(_locator_terms(page_data), key=len, reverse=True):
        pos = lowered.find(term.lower())
        if pos != -1:
            match_at = pos
            break
    start = max(match_at - _EVIDENCE_SNIPPET_CHARS // 4, 0)
    end = min(start + _EVIDENCE_SNIPPET_CHARS, len(chunk))
    return chunk[start:end]


def _source_chunk_trace(chunks):
    return [
        {
            "index": chunk["index"],
            "start": chunk["start"],
            "end": chunk["end"],
            "preview": _chunk_preview(chunk["text"]),
        }
        for chunk in chunks
    ]


def _chunk_preview(text):
    content = text or ""
    if len(content) <= _SOURCE_CHUNK_PREVIEW_CHARS:
        return content
    edge_chars = _SOURCE_CHUNK_PREVIEW_CHARS // 2
    return f"{content[:edge_chars].rstrip()}\n...\n{content[-edge_chars:].lstrip()}"


def _decode_locator(locator):
    if not locator:
        return {}
    try:
        return json.loads(locator)
    except (TypeError, ValueError):
        return {}


def _page_action_trace(page, action, locator):
    return {
        "page_id": page.id,
        "title": page.title,
        "page_type": page.page_type,
        "status": page.status,
        "action": action,
        "source_locator": _decode_locator(locator),
    }


def _source_locator_for_page(material, source_text, page_data, chunks=None):
    chunks = chunks if chunks is not None else _source_chunks_with_offsets(source_text)
    if not chunks:
        return ""
    best = max(chunks, key=lambda item: (_locator_score(item["text"], page_data), item["index"] == 0))
    locator = {
        "kind": "material_chunk",
        "material_version_id": material.current_version_id,
        "content_locator": getattr(material.current_version, "content_locator", "") if material.current_version_id else "",
        "chunk_index": best["index"],
        "chunk_count": len(chunks),
        "start": best["start"],
        "end": best["end"],
        "snippet": _locator_snippet(best["text"], page_data),
    }
    return json.dumps(locator, ensure_ascii=False)


def _ensure_evidence(page, material, locator=""):
    evidence, created = PageEvidence.objects.get_or_create(
        page=page,
        material=material,
        defaults={"material_version": material.current_version, "locator": locator or ""},
    )
    if created:
        return True
    update_fields = []
    if material.current_version_id and evidence.material_version_id != material.current_version_id:
        evidence.material_version = material.current_version
        update_fields.append("material_version")
    if locator and evidence.locator != locator:
        evidence.locator = locator
        update_fields.append("locator")
    if update_fields:
        update_fields.append("updated_at")
        evidence.save(update_fields=update_fields)
        return True
    return False


def _create_ai_page(kb, material, build, page_data, update_method="ai_create", change_type="ai_create", operator="", locator=""):
    page = KnowledgePage.objects.create(
        knowledge_base=kb,
        page_type=page_data.get("page_type", "concept"),
        title=page_data["title"],
        tags=page_data.get("tags", []) or [],
        contribution="ai",
        update_method=update_method,
    )
    version = PageVersion.objects.create(
        page=page,
        no=1,
        body=page_data.get("body", "") or "",
        change_type=change_type,
        is_current=True,
        build_record=build,
        created_by=operator or "",
    )
    page.current_version = version
    page.save(update_fields=["current_version"])
    PageEvidence.objects.create(page=page, material=material, material_version=material.current_version, locator=locator or "")
    return page


def _merged_body_for_material(page, material, incoming_body):
    current_body = page.current_version.body if page.current_version_id else ""
    body = (incoming_body or "").strip()
    if not body or body == current_body or body in current_body:
        return current_body

    evidence_qs = PageEvidence.objects.filter(page=page)
    same_material_exists = evidence_qs.filter(material=material).exists()
    if same_material_exists and evidence_qs.count() <= 1:
        return body
    if not current_body:
        return body
    return "\n\n".join([current_body, body])


def _merge_ai_page(page, material, build, page_data, operator="", update_method="ai_merge", change_type="ai_merge", locator=""):
    title = (page_data.get("title") or "").strip()
    body = page_data.get("body", "") or ""
    page_type = page_data.get("page_type", "concept")
    tags = page_data.get("tags", []) or []
    current_body = page.current_version.body if page.current_version_id else ""
    merged_body = _merged_body_for_material(page, material, body)
    merged_tags = list(dict.fromkeys([*(page.tags or []), *tags]))
    changed = False
    update_fields = []

    if current_body != merged_body:
        page.page_versions.filter(is_current=True).update(is_current=False)
        version = PageVersion.objects.create(
            page=page,
            no=_next_version_no(page),
            body=merged_body,
            change_type=change_type,
            is_current=True,
            build_record=build,
            created_by=operator or "",
        )
        page.current_version = version
        update_fields.append("current_version")
        changed = True

    if page.page_type != page_type:
        page.page_type = page_type
        update_fields.append("page_type")
        changed = True
    if page.tags != merged_tags:
        page.tags = merged_tags
        update_fields.append("tags")
        changed = True
    if title and page.title != title:
        page.title = title
        update_fields.append("title")
        changed = True
    if page.status != "active":
        page.status = "active"
        update_fields.append("status")
        changed = True

    evidence_changed = _ensure_evidence(page, material, locator=locator)
    if changed or evidence_changed:
        page.update_method = update_method
        update_fields.extend(["update_method", "updated_at"])
        page.save(update_fields=list(dict.fromkeys(update_fields)))
        return "updated"
    return "unchanged"


def _create_review_candidate(page, material, build, page_data, operator=""):
    # phase 4.2: 调决策服务查规则,命中回放不创建 CheckItem,BuildRecord 记 decision_reused
    from apps.opspilot.services.wiki.decision_service import (
        build_participants_from_materials,
        compute_schema_fingerprint,
        replay_decision,
        subject_key_for_page,
    )

    schema_fingerprint = compute_schema_fingerprint(page.knowledge_base)
    subject_key = subject_key_for_page(
        page_type=page.page_type or "concept",
        canonical_title=compact_title_key(page.title or ""),
    )
    result, rule = replay_decision(
        knowledge_base=page.knowledge_base,
        decision_type="page_identity",
        subject_key=subject_key,
        schema_fingerprint=schema_fingerprint,
        participants=build_participants_from_materials([material]),
        page=page,
    )
    if result == "replayed":
        # 命中规则,记录到 BuildRecord 供审计,直接返回 unchanged
        _record_decision_reused(build, rule, action=rule.action, page=page)
        return "unchanged"
    if result == "unchanged":
        return "unchanged"

    # result == "pending" 或规则不适配:创建候选 + 决策
    create_candidate(
        page,
        body=page_data.get("body", "") or "",
        reason="构建资料命中同名人工知识,需人工确认后合并",
        check_type="cannot_merge",
        build_record=build,
        created_by=operator,
        related={"pages": [page.id], "materials": [material.id]},
    )
    return "pending_review"


def _record_decision_reused(build, rule, *, action, page):
    """phase 4: 把决策回放写入 BuildRecord.inputs.source_trace,审计用。"""
    trace = dict(build.inputs.get("source_trace") or {})
    page_actions = list(trace.get("page_actions") or [])
    page_actions.append(
        {
            "page_id": page.id,
            "decision_reused": True,
            "rule_id": rule.id,
            "action": action,
        }
    )
    trace["page_actions"] = page_actions
    inputs = dict(build.inputs or {})
    inputs["source_trace"] = trace
    build.inputs = inputs
    build.save(update_fields=["inputs", "updated_at"])


def build_from_material(material, llm_model_id=None, operator="", trigger="material"):
    """从一份资料构建知识页面。返回 BuildRecord。"""
    kb = material.knowledge_base
    # 资料进入「构建中」,前端轮询即可看到状态
    material.status = "building"
    material.save(update_fields=["status", "updated_at"])
    build = BuildRecord.objects.create(
        knowledge_base=kb,
        trigger=trigger,
        operator=operator,
        inputs={"material_id": material.id},
        stage="generating",
        status="running",
    )
    try:
        text = (load_parsed_markdown(material) or material.ai_summary or material.text_content or "").strip()
        source_chunks = _source_chunks_with_offsets(text)
        source_trace = {"chunks": _source_chunk_trace(source_chunks), "page_actions": []}
        build.inputs = {
            **(build.inputs or {}),
            "material_name": material.name,
            "source_trace": source_trace,
        }
        build.save(update_fields=["inputs", "updated_at"])
        # 两步法:Stage1 抽取要点 → Stage2 依据 Schema 生成页面(抽取失败则回退原文)
        facts = _llm_extract_facts(text, llm_model_id)
        pages_data = _llm_generate_pages(kb, facts or text, llm_model_id)
        affected = []
        cascade_ids = []
        maintenance = {}
        counts = {"new": 0, "updated": 0, "unchanged": 0, "pending_review": 0}
        existing_by_title = _existing_pages_by_title(kb)
        for pd in pages_data:
            pd = _normalize_page_data_title(kb, pd)
            key = _title_key(pd.get("title"), kb)
            page = existing_by_title.get(key)
            locator = _source_locator_for_page(material, text, pd, chunks=source_chunks)
            if not page:
                page = _create_ai_page(kb, material, build, pd, locator=locator)
                existing_by_title[key] = page
                action = "new"
            elif page.contribution == "ai":
                action = _merge_ai_page(page, material, build, pd, operator=operator, locator=locator)
            else:
                action = _create_review_candidate(page, material, build, pd, operator=operator)

            counts[action] += 1
            source_trace["page_actions"].append(_page_action_trace(page, action, locator))
            if action in ("new", "updated"):
                affected.append(page.id)
                cascade_ids.append(page.id)
            elif action == "pending_review":
                affected.append(page.id)

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
            # 新页面与同库其他页面建立关系并增量维护索引。
            maintenance = cascade(kb, cascade_ids, "build")
        build.counts = counts
        build.affected_pages = affected
        build.inputs = {
            **(build.inputs or {}),
            "source_trace": source_trace,
        }
        build.maintenance = maintenance
        build.stage = "done"
        build.status = "success"
        build.progress = 100
        build.save(update_fields=["counts", "affected_pages", "inputs", "maintenance", "stage", "status", "progress", "updated_at"])
        material.status = "built"
        material.save(update_fields=["status", "updated_at"])
        return build
    except Exception as exc:
        logger.exception("wiki 构建失败 material=%s", material.id)
        build.stage = "failed"
        build.status = "failed"
        build.errors = [str(exc)]
        build.save(update_fields=["stage", "status", "errors", "updated_at"])
        # 构建失败:解析结果仍有效,资料回退到「已解析」,失败详情见构建记录
        material.status = "done"
        material.save(update_fields=["status", "updated_at"])
        raise
