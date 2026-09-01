"""知识构建管道:资料 → 知识页面(对标 llm_wiki 两步法)。

Stage1 抽取事实:从资料抽取结构化要点(去噪、聚焦可复用事实)。
Stage2 生成页面:依据 Purpose 与固定 Structure Schema 从事实生成互联知识页面。
创建页面 + 首版本(ai_create)+ 资料证据,并记录构建过程到 BuildRecord。
"""

import json
import os
import re

import json_repair
from django.db import transaction

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_log_value
from apps.opspilot.metis.llm.chain.entity import BasicLLMRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory, resolve_gateway_temperature
from apps.opspilot.models import BuildRecord, KnowledgePage, LLMModel, PageEvidence, PageVersion, WikiKnowledgeBase
from apps.opspilot.services.llm_context_budget import derive_llm_working_budget, window_tokens_for_model_id, working_budget_for_model
from apps.opspilot.services.wiki.cascade_service import cascade
from apps.opspilot.services.wiki.check_service import create_candidate
from apps.opspilot.services.wiki.maintenance_errors import humanize_maintenance_error
from apps.opspilot.services.wiki.text_utils import split_text_by_estimated_tokens, split_text_for_llm
from apps.opspilot.services.wiki.title_service import canonical_title as _canonical_title
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, estimate_tokens

_split_text_for_llm = split_text_for_llm
_WIKI_LLM_TIMEOUT_SECONDS = 300.0
_CURRENT_MATERIAL_VERSION = object()
_EVIDENCE_SNIPPET_CHARS = 500
_SOURCE_CHUNK_PREVIEW_CHARS = 240
_MATERIAL_DIRECT_OUTPUT_TOKENS = 6000
_MATERIAL_MAP_OUTPUT_TOKENS = 2500
_MATERIAL_REDUCE_OUTPUT_TOKENS = 2500
_MATERIAL_MAX_REDUCE_ROUNDS = 8
_PROMPT_SAFETY_TOKENS = 256


def _material_window_limits(llm_model_id):
    window = window_tokens_for_model_id(llm_model_id)
    primary = derive_llm_working_budget(window, scene_output_default=_MATERIAL_DIRECT_OUTPUT_TOKENS)
    map_output = derive_llm_working_budget(window, scene_output_default=_MATERIAL_MAP_OUTPUT_TOKENS).output_reserve_tokens
    reduce_output = derive_llm_working_budget(window, scene_output_default=_MATERIAL_REDUCE_OUTPUT_TOKENS).output_reserve_tokens
    return primary, map_output, reduce_output


_DERIVED_SYSTEM_PAGE_TYPES = frozenset({"index", "overview", "log"})
_PARSE_LOG_PREVIEW_CHARS = 400
_WIKI_LLM_TEMPERATURE = 0.0
_GENERATE_OUTPUT_MAX_ATTEMPTS = 2
_RETRYABLE_BUILD_OUTPUT_MARKERS = (
    "build_output_invalid_json",
    "build_output_empty_topic_pages",
    "build_output_empty_pages",
    "build_output_invalid_page",
    "build_output_empty_llm",
)
_THINK_BLOCK_RE = re.compile(
    r"<(?:think|thinking|reason|reasoning)\b[^>]*>[\s\S]*?</(?:think|thinking|reason|reasoning)>",
    re.IGNORECASE,
)
_CODE_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*([\s\S]*?)```")
_JSON_ONLY_OUTPUT_RULES = (
    "输出格式硬性要求（必须全部遵守，适用于任意模型）：\n"
    "1. 最终回复只输出一个 JSON 值，不要解释、前言、标题、列表或 Markdown。\n"
    "2. 不要用 ``` 代码块包裹；不要输出 <think>/<thinking> 或任何推理过程。\n"
    '3. 只能使用半角字符书写 JSON 结构：{} [] " : ,\n'
    '4. 根对象必须是 {"pages":[...]}；如果只需事实批次也必须是合法 JSON 对象。'
    '无可生成内容时输出 {"pages":[]}。\n'
    "5. 最终回复的第一个非空白字符必须是 {，最后一个非空白字符必须是 }。\n"
    '6. 字符串值内的双引号、换行必须按 JSON 转义（\\" 与 \\n），'
    "body 字段尤其容易因未转义导致整段 JSON 非法。\n"
)
_FACT_PRESERVATION_RULES = (
    "可核验事实保留硬性要求（必须全部遵守）：\n"
    "1. 必须保留资料中已给出的联系人姓名、电话、内线/分机、邮箱、URL、工号、资产编号、明确日期与数值；"
    "不得当作噪音或临时细节删除。\n"
    "2. 禁止把资料中已写明的具体事实改写成“信息缺口/未确认/是否仍有效”而不写出原值；"
    "若需提示时效性，应先完整写出原事实，再另起一句说明时效未在资料中确认。\n"
    "3. “信息缺口”仅用于资料确实未给出的信息；不得用缺口描述替代已存在的原值。\n"
)
_CONTACT_LABEL_RE = re.compile(
    r"(?P<label>联系人|联系电话|电话|手机|内线|分机|邮箱|E-?mail|Email)\s*[:：]?\s*"
    r"(?P<value>.+?)"
    r"(?=(?:\s{1,6}(?:联系人|联系电话|电话|手机|内线|分机|邮箱|E-?mail|Email)\s*[:：])|$)",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)|(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")
_CONTACT_SECTION_TITLE = "## 联系方式"
_CONTACT_TARGET_HINTS = ("联系", "指引", "管理", "安全", "通讯", "值班", "热线")


class BuildOutputInvalid(ValueError):
    code = "build_output_invalid_json"


class MaterialPageGeneration:
    """Budgeted material generation result; skipped map chunks stay visible to callers."""

    def __init__(self, pages, skipped=None):
        self.pages = list(pages or [])
        self.skipped = list(skipped or [])


def as_material_page_generation(result):
    if isinstance(result, MaterialPageGeneration):
        return result
    return MaterialPageGeneration(pages=list(result or []), skipped=[])


def generation_publish_status(skipped):
    return "partial" if skipped else "success"


def generation_skip_checkpoint(skipped):
    if not skipped:
        return {}
    return {
        "skipped_count": len(skipped),
        "skipped_map_stages": [item.get("stage") for item in skipped],
    }


def _map_skip_record(stage, error):
    return {
        "code": "wiki_build_llm_skip",
        "message": "map chunk skipped after empty LLM retry",
        "stage": str(stage),
        "error_type": type(error).__name__,
    }


def _wiki_llm_timeout():
    raw_timeout = os.getenv("WIKI_LLM_INVOKE_TIMEOUT") or os.getenv("LLM_INVOKE_TIMEOUT")
    if not raw_timeout:
        return _WIKI_LLM_TIMEOUT_SECONDS
    try:
        timeout = float(raw_timeout)
    except (TypeError, ValueError):
        return _WIKI_LLM_TIMEOUT_SECONDS
    return max(timeout, 1.0)


def _normalize_wiki_llm_model_id(model_name):
    name = str(model_name or "").strip().lower()
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    return name


def _wiki_llm_log_flag(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "-"


def _log_wiki_llm_invoke(stage, request, result, output_reserve):
    extra = (getattr(request, "extra_config", None) if request is not None else None) or {}
    usage = extra.get("_isolated_usage") or {}
    reasoning_tokens = usage.get("reasoning_tokens")
    content_chars = extra.get("_isolated_content_chars")
    if content_chars is None:
        content_chars = len(result or "")
    logger.info(
        "wiki_llm_invoke stage=%s model=%s max_output=%s finish_reason=%s truncated=%s "
        "content_chars=%s prompt_tokens=%s completion_tokens=%s reasoning_tokens=%s "
        "has_reasoning=%s thinking_enable=%s thinking_template_enable=%s",
        stage,
        safe_log_value(getattr(request, "model", None) or "-"),
        output_reserve,
        extra.get("_isolated_finish_reason") or "-",
        _wiki_llm_log_flag(extra.get("_isolated_output_truncated") is True),
        content_chars,
        usage.get("prompt_tokens") or usage.get("input_tokens") or 0,
        usage.get("completion_tokens") or usage.get("output_tokens") or 0,
        reasoning_tokens if reasoning_tokens is not None else "-",
        _wiki_llm_log_flag(extra.get("_isolated_has_reasoning_content") is True),
        _wiki_llm_log_flag(extra.get("_isolated_thinking_enable")),
        _wiki_llm_log_flag(extra.get("_isolated_thinking_template_enable")),
    )


def _wiki_llm_temperature(model_name):
    """Wiki 默认 temperature=0；部分模型网关只接受 1。"""
    return resolve_gateway_temperature(model_name, _WIKI_LLM_TEMPERATURE)


def _invoke_llm(
    llm_model_id,
    prompt,
    *,
    budget=None,
    stage="wiki_llm",
    output_reserve=1500,
    force_json=False,
):
    """Invoke one isolated LLM call and account for it when a budget is supplied.

    Generation paths pass ``budget`` and must fail loudly on empty/errored LLM
    output. Legacy callers without budget keep the soft ``""`` fallback.
    """
    if not llm_model_id:
        return ""
    reservation = None
    request = None
    try:
        llm = LLMModel.objects.select_related("vendor").get(id=llm_model_id)
        derived = working_budget_for_model(llm, scene_output_default=output_reserve)
        output_reserve = derived.output_reserve_tokens
        if budget is not None:
            reservation = budget.ensure_call(
                stage,
                prompt,
                output_reserve=output_reserve,
            )
        elif estimate_tokens(prompt) > derived.input_working_tokens:
            raise WikiBudgetExceeded(
                "wiki_llm_context_window_exceeded",
                "单次 Wiki LLM 输入输出超过系统安全上下文上限",
                details={
                    "stage": stage,
                    "input_working_tokens": derived.input_working_tokens,
                    "context_window_tokens": derived.window_tokens,
                },
            )
        vendor_type = ""
        if getattr(llm, "vendor_id", None):
            vendor_type = str(getattr(llm.vendor, "vendor_type", "") or "")
        protocol_type = getattr(llm, "protocol_type", None) or "openai"
        extra_config = {
            "timeout": _wiki_llm_timeout(),
            "input_working_tokens": derived.input_working_tokens,
            "context_window_tokens": derived.window_tokens,
        }
        # OpenAI 兼容协议可请求 json_object；网关不支持时由 factory 自动降级。
        if force_json and protocol_type == "openai":
            extra_config["response_format"] = {"type": "json_object"}
        request = BasicLLMRequest(
            openai_api_base=llm.openai_api_base,
            openai_api_key=llm.openai_api_key,
            model=llm.model_name,
            temperature=_wiki_llm_temperature(llm.model_name),
            user_message=prompt,
            max_output_tokens=output_reserve,
            protocol_type=protocol_type,
            vendor_type=vendor_type,
            extra_config=extra_config,
        )
        result = LLMClientFactory.invoke_isolated(
            request,
            [{"role": "user", "content": prompt}],
        )
        if not isinstance(result, str):
            result = "" if result is None else str(result)
        result = result.strip()
        _log_wiki_llm_invoke(stage, request, result, output_reserve)
        if budget is not None:
            budget.record_call(
                reservation,
                result,
                provider_usage=(request.extra_config or {}).get("_isolated_usage"),
            )
            if not result:
                finish_reason = (request.extra_config or {}).get("_isolated_finish_reason")
                usage = (request.extra_config or {}).get("_isolated_usage") or {}
                raise BuildOutputInvalid(
                    "build_output_empty_llm: "
                    f"stage={stage} finish_reason={finish_reason or '-'} "
                    f"prompt_tokens={usage.get('prompt_tokens') or usage.get('input_tokens') or 0} "
                    f"completion_tokens={usage.get('completion_tokens') or usage.get('output_tokens') or 0}"
                )
        return result
    except (WikiBudgetExceeded, BuildOutputInvalid):
        raise
    except Exception as exc:
        if budget is not None and reservation is not None:
            budget.record_call(reservation, "")
        logger.exception("wiki LLM 调用失败 stage=%s", stage)
        if budget is not None:
            raise BuildOutputInvalid(f"build_output_llm_error: stage={stage} {type(exc).__name__}: {exc}") from exc
        return ""


def _llm_extract_facts(text, llm_model_id):
    """Stage1:从资料全文分块抽取结构化要点(每行一条事实)。"""
    if not llm_model_id or not (text or "").strip():
        return ""
    primary, _, _ = _material_window_limits(llm_model_id)
    chunks = split_text_by_estimated_tokens(text, max_tokens=primary.build_chunk_tokens)
    facts = []
    for idx, chunk in enumerate(chunks, start=1):
        prompt = (
            "你是知识抽取助手。请从下面的资料片段中抽取稳定、可复用、对运维有价值的关键事实/要点,"
            "去除广告、排版噪音与无信息填充语,每行一条,只输出要点列表本身,不要解释。\n"
            f"{_FACT_PRESERVATION_RULES}"
            "注意:这是同一份资料的分块处理,不得因为只看到当前片段就判断全文结束。\n\n"
            f"# 资料片段 {idx}/{len(chunks)}\n{chunk}\n"
        )
        result = _invoke_llm(llm_model_id, prompt).strip()
        if result:
            facts.append(result)
    return "\n".join(facts)


def _directory_prompt_context(structure_revision, classification_root_id=None):
    if structure_revision is None:
        return ""
    snapshot = structure_revision.structure_snapshot or {}
    page_types = snapshot.get("page_types") or []
    nodes = snapshot.get("directories") or []
    by_id = {node.get("id"): node for node in nodes if type(node.get("id")) is int}

    def in_scope(node):
        if classification_root_id is None:
            return True
        current = node
        visited = set()
        while current is not None and current.get("id") not in visited:
            if current.get("id") == classification_root_id:
                return True
            visited.add(current.get("id"))
            current = by_id.get((current.get("parent") or {}).get("id"))
        return False

    prompt_nodes = []
    for node in nodes:
        if node.get("status") != "active" or not in_scope(node):
            continue
        path = []
        current = node
        visited = set()
        while current is not None and current.get("id") not in visited:
            path.append(current.get("name") or current.get("key"))
            visited.add(current.get("id"))
            current = by_id.get((current.get("parent") or {}).get("id"))
        prompt_nodes.append(
            {
                "key": node.get("key"),
                "path": "/".join(reversed([item for item in path if item])),
                "description": node.get("description") or "",
                "rules": node.get("rules") or {},
            }
        )
    return json.dumps(
        {
            "structure_revision_id": structure_revision.pk,
            "structure_version": structure_revision.revision_no,
            "structure_fingerprint": structure_revision.fingerprint,
            "classification_root_id": classification_root_id,
            "page_types": page_types,
            "directories": prompt_nodes,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def material_source_metadata(material):
    """Return stable, user-facing context for one independently built material."""

    display_name = str(getattr(material, "name", "") or "").strip()
    material_type = str(getattr(material, "material_type", "") or "").strip()
    source_url = str(getattr(material, "url", "") or "").strip()
    if not display_name:
        display_name = source_url or f"资料 {material.pk}"
    display_title = display_name
    if material_type == "file":
        display_title = os.path.splitext(os.path.basename(display_name))[0].strip() or display_name

    knowledge_base = material.knowledge_base
    existing_source = (
        PageEvidence.objects.filter(
            material=material,
            page__knowledge_base=knowledge_base,
            page__page_type="source",
        )
        .select_related("page")
        .order_by("page_id")
        .first()
    )
    if existing_source is not None:
        source_title = existing_source.page.title
    else:
        source_title = _canonical_title(knowledge_base, display_title) or display_title
        occupied_title_keys = {
            _title_key(title, knowledge_base)
            for title in KnowledgePage.objects.filter(
                knowledge_base=knowledge_base,
            ).values_list("title", flat=True)
        }
        if _title_key(source_title, knowledge_base) in occupied_title_keys:
            source_title = f"资料：{display_title}"
        if _title_key(source_title, knowledge_base) in occupied_title_keys:
            source_title = f"资料：{display_title} · {material.pk}"

    return {
        "material_id": material.pk,
        "display_name": display_name,
        "source_title": source_title,
        "material_type": material_type,
        "source_identity": str(getattr(material, "source_identity", "") or "").strip(),
        "url": source_url,
    }


def _page_type_body_guidance(page_type):
    guidance = {
        "entity": ("首段定义对象；正文覆盖核心职责或能力、关键属性、依赖关系和体系角色，" "并保留联系方式、编号等可核验字段；不得把多个独立对象混成一页。"),
        "concept": ("首段给出定义；正文覆盖机制或架构、组成与关系、适用边界，" "以及资料明确给出的联系人/电话/内线/编号等可核验事实；" "仅当资料确实未给出时才写信息缺口。"),
        "source": ("正文覆盖资料背景、内容结构、覆盖主题与信息质量；" "资料中的联系方式等可核验事实必须保留或指向含该事实的主题页；" "仅当资料确实未给出时才写已知缺口。"),
        "query": "只记录资料明确留下的未解决问题，说明问题、重要性、现有证据和还需补充的证据；不得凭空发问。",
        "comparison": "只有资料给出共同维度和明确事实时才生成；列出对象、维度、事实对比、结论与限制。",
        "synthesis": "只有资料确实支持跨主题或多来源结论时才生成；说明证据链、综合结论、适用范围和限制。",
    }
    return guidance.get(str(page_type or "").strip(), "围绕单一稳定主题组织正文，保留事实边界、限定条件和明确关系。")


def _prompt_source_metadata(source_metadata):
    if not isinstance(source_metadata, dict):
        return {}
    return {key: source_metadata.get(key) for key in ("display_name", "source_title", "material_type", "url") if source_metadata.get(key)}


def _generation_page_contract(structure_revision, source_metadata=None):
    snapshot = getattr(structure_revision, "structure_snapshot", None) or {}
    page_types = [str(item).strip() for item in snapshot.get("page_types") or [] if str(item).strip()]
    lines = [
        "解析分块只是证据，不是页面边界；最终页面必须按稳定主题组织，而不是一块生成一页。",
        "不要为了填满目录而生成空洞页面；没有充分证据的类型允许为空。",
        "不得生成 index、overview、log 或目录统计页面，这些内容由系统按 Generation 派生。",
        "正文使用清晰 Markdown 标题，并在关系明确时用 [[目标页面标题]] 建立链接。",
        "不同主体的事实、版本、适用范围和限定条件必须分开，不得把相似名称合并成同一事实。",
        _FACT_PRESERVATION_RULES.strip(),
    ]
    for page_type in page_types:
        lines.append(f"- {page_type}: {_page_type_body_guidance(page_type)}")
    prompt_metadata = _prompt_source_metadata(source_metadata)
    if "source" in page_types and prompt_metadata.get("source_title"):
        lines.append("必须且只能生成一个 source 页面，标题严格使用 " f"{prompt_metadata['source_title']!r}；该页面代表当前资料，不代表普通主题综述。")
        lines.append("除 source 外，还必须至少生成一个主题页面" "（concept/entity/query/comparison/synthesis 等非 source 类型）；" "禁止只输出 source 页面。")
    return "\n".join(lines)


def _normalize_text_list(value, limit):
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))[:limit]


def _normalize_contact_token(value):
    return re.sub(r"\s+", "", str(value or "").strip().casefold())


def _extract_contact_facts(source_text):
    """从原文抽取联系方式类可核验事实（姓名/电话/内线等）。"""
    text = str(source_text or "")
    if not text.strip():
        return []
    facts = []
    seen = set()

    def add_fact(kind, value, *, line=""):
        cleaned = str(value or "").strip().strip("。.;；,，")
        if not cleaned:
            return
        key = (kind, _normalize_contact_token(cleaned))
        if not key[1] or key in seen:
            return
        seen.add(key)
        facts.append({"kind": kind, "value": cleaned, "line": (line or "").strip()})

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for match in _CONTACT_LABEL_RE.finditer(line):
            label = (match.group("label") or "").casefold()
            value = (match.group("value") or "").strip()
            if "联系人" in label:
                # 同行可能还有电话/内线，先取姓名片段
                name = re.split(r"[；;|,，\s]{2,}|\s{2,}|联系电话|电话|内线|分机", value, maxsplit=1)[0].strip()
                add_fact("name", name or value, line=line)
            elif "内线" in label or "分机" in label:
                add_fact("extension", value, line=line)
            elif "邮箱" in label or "mail" in label:
                add_fact("email", value, line=line)
            else:
                add_fact("phone", value, line=line)
        for phone in _PHONE_RE.findall(line):
            add_fact("phone", phone, line=line)
        # 形如：联系人：张三  联系电话：0757-xxx   内线：3013
        if "联系人" in line and ("电话" in line or "内线" in line or "分机" in line):
            add_fact("line", line, line=line)
    return facts


def _contact_facts_missing(pages, facts):
    bodies = "\n".join(str((page or {}).get("body") or "") for page in pages or [])
    normalized_body = _normalize_contact_token(bodies)
    missing = []
    for fact in facts or []:
        token = _normalize_contact_token(fact.get("value"))
        if token and token not in normalized_body:
            missing.append(fact)
    return missing


def _pick_contact_target_page(pages):
    pages = [page for page in (pages or []) if isinstance(page, dict)]
    if not pages:
        return None
    scored = []
    for index, page in enumerate(pages):
        title = str(page.get("title") or "")
        body = str(page.get("body") or "")
        page_type = str(page.get("page_type") or "")
        score = 0
        blob = f"{title}\n{body}"
        for hint in _CONTACT_TARGET_HINTS:
            if hint in blob:
                score += 3
        if page_type == "source":
            score += 1
        if page_type in {"concept", "entity"}:
            score += 2
        scored.append((score, index, page))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][2]


def _format_contact_section(facts):
    lines_by_key = []
    seen_lines = set()
    for fact in facts or []:
        line = str(fact.get("line") or "").strip()
        value = str(fact.get("value") or "").strip()
        content = line or value
        key = _normalize_contact_token(content)
        if not content or key in seen_lines:
            continue
        seen_lines.add(key)
        lines_by_key.append(f"- {content}")
    if not lines_by_key:
        return ""
    return "\n".join([_CONTACT_SECTION_TITLE, "", *lines_by_key, ""])


def _insert_contact_section(body, section):
    """把联系方式小节插到正文靠前位置，避免仅出现在页末被检索摘录截断。"""
    section = (section or "").strip()
    if not section:
        return body
    text = str(body or "").rstrip()
    if not text:
        return section + "\n"
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("#"):
        rest = "\n".join(lines[1:]).lstrip("\n")
        if rest:
            return f"{lines[0]}\n\n{section}\n\n{rest}\n"
        return f"{lines[0]}\n\n{section}\n"
    return f"{section}\n\n{text}\n"


def _append_contact_facts_to_page(page, missing_facts):
    """把缺失联系方式幂等追加到单页正文。"""
    section = _format_contact_section(missing_facts)
    if not section:
        return False
    body = str(page.get("body") or "").rstrip()
    if _CONTACT_SECTION_TITLE in body and all(
        _normalize_contact_token(fact.get("value")) in _normalize_contact_token(body) for fact in missing_facts if fact.get("value")
    ):
        return False
    if _CONTACT_SECTION_TITLE in body:
        existing = _normalize_contact_token(body)
        extra_lines = []
        for fact in missing_facts:
            content = str(fact.get("line") or fact.get("value") or "").strip()
            token = _normalize_contact_token(content)
            if content and token and token not in existing:
                extra_lines.append(f"- {content}")
        if not extra_lines:
            return False
        page["body"] = f"{body}\n" + "\n".join(extra_lines) + "\n"
        return True
    page["body"] = _insert_contact_section(body, section)
    return True


def ensure_contact_facts_preserved(source_text, pages):
    """若生成页缺失原文联系方式，幂等追加到主题页与 source 页。

    主题页可能因冲突进入待审批而不生效；source 页通常会直接入库，
    因此两边都补，避免检索只能看到无联系方式的生效页。
    """
    page_list = [dict(page) for page in (pages or []) if isinstance(page, dict)]
    facts = _extract_contact_facts(source_text)
    if not facts or not page_list:
        return page_list

    targets = []
    best = _pick_contact_target_page(page_list)
    if best is not None:
        targets.append(best)
    for page in page_list:
        if page.get("page_type") == "source" and page not in targets:
            targets.append(page)
    if not targets:
        return page_list

    for target in targets:
        missing = _contact_facts_missing([target], facts)
        if missing:
            _append_contact_facts_to_page(target, missing)
    return page_list


def prepare_page_data_with_contact_facts(source_text, page_data):
    """入库/候选写入前，确保单页正文保留原文联系方式。

    生成定稿阶段已做一次全量补漏；这里再按「即将写入的单页」补一次，
    防止主题页进待审批后，唯一生效的 source 页仍然缺少联系方式。
    """
    page = dict(page_data or {})
    return ensure_contact_facts_preserved(source_text, [page])[0]


def published_pages_missing_contact_facts(source_text, pages):
    """返回已准备写入的页面集合中，仍缺失的联系方式事实。"""
    page_list = [dict(page) for page in (pages or []) if isinstance(page, dict)]
    return _contact_facts_missing(page_list, _extract_contact_facts(source_text))


def _source_default_directory_key(structure_revision):
    snapshot = getattr(structure_revision, "structure_snapshot", None) or {}
    for node in snapshot.get("directories") or []:
        rules = node.get("rules") or {}
        if "source" in (rules.get("default_for_page_types") or []):
            return node.get("key")
    return None


def _fallback_source_page(pages, source_metadata, structure_revision):
    title = source_metadata["source_title"]
    topic_pages = [page for page in pages if page.get("page_type") != "source"]
    links = [f"- [[{page['title']}]]：{page.get('summary') or page.get('page_type') or '知识主题'}" for page in topic_pages]
    overview = "本资料形成了以下可复用知识主题。" if links else "本资料未形成可单独发布的主题页面。"
    body = "\n".join(
        [
            f"# {title}",
            "",
            "## 资料概述",
            "",
            overview,
            "",
            "## 内容结构",
            "",
            *(links or ["- 暂无可列出的独立主题。"]),
            "",
            "## 信息边界",
            "",
            "本页是当前资料的来源导航；事实判断仍以对应知识页面和原始证据为准。",
        ]
    )
    return {
        "page_type": "source",
        "title": title,
        "tags": ["来源摘要"],
        "body": body,
        "directory_key": _source_default_directory_key(structure_revision),
        "directory_confidence": 1.0,
        "directory_reason": "material_source_contract",
        "summary": overview,
        "keywords": _normalize_text_list([item for page in topic_pages for item in page.get("keywords") or []], 32),
        "entities": [page["title"] for page in topic_pages if page.get("page_type") == "entity"][:32],
        "aliases": _normalize_text_list([source_metadata.get("display_name")], 32),
    }


def _pages_preview_for_log(pages, *, limit=8):
    preview = []
    for page in list(pages or [])[:limit]:
        preview.append(
            {
                "title": str((page or {}).get("title") or "")[:80],
                "page_type": (page or {}).get("page_type"),
                "body_chars": len(str((page or {}).get("body") or "")),
            }
        )
    return preview


def _resolve_page_type(page, *, source_metadata=None, allowed_page_types=None, kb=None):
    """Fill missing page_type instead of failing the whole material build."""
    page_type = str((page or {}).get("page_type") or "").strip().casefold()
    if page_type:
        return page_type, False

    title = str((page or {}).get("title") or "").strip()
    source_title = str((source_metadata or {}).get("source_title") or "").strip()
    if source_title and title and _title_key(title, kb) == _title_key(source_title, kb):
        return "source", True

    allowed = set(allowed_page_types or [])
    if not allowed or "concept" in allowed:
        return "concept", True
    for candidate in ("entity", "query", "comparison", "synthesis"):
        if candidate in allowed:
            return candidate, True
    non_source = sorted(item for item in allowed if item != "source")
    if non_source:
        return non_source[0], True
    return "concept", True


def _finalize_material_pages(pages, *, kb, structure_revision, source_metadata=None, source_text=None):
    snapshot = getattr(structure_revision, "structure_snapshot", None) or {}
    allowed_page_types = {str(item).strip().casefold() for item in snapshot.get("page_types") or [] if str(item).strip()}
    normalized = []
    for raw in pages:
        page = dict(raw or {})
        page_type, coerced = _resolve_page_type(
            page,
            source_metadata=source_metadata,
            allowed_page_types=allowed_page_types,
            kb=kb,
        )
        if coerced:
            logger.warning(
                "wiki_build_coerced_page_type title=%s inferred=%s raw=%r",
                page.get("title"),
                page_type,
                page.get("page_type"),
            )
        if page_type in _DERIVED_SYSTEM_PAGE_TYPES:
            logger.warning("wiki_build_dropped_derived_page type=%s title=%s", page_type, page.get("title"))
            continue
        if allowed_page_types and page_type not in allowed_page_types:
            page["directory_key"] = None
            page["directory_schema_mismatch"] = True
        body = str(page.get("body") or "").strip()
        if source_metadata is not None and not body:
            logger.warning(
                "wiki_build_dropped_empty_body_page title=%s page_type=%s",
                page.get("title"),
                page_type,
            )
            continue
        page["page_type"] = page_type
        page["body"] = body
        for field, limit in (("tags", 32), ("keywords", 32), ("entities", 32), ("aliases", 32)):
            page[field] = _normalize_text_list(page.get(field), limit)
        normalized.append(page)

    if source_metadata is not None and not normalized:
        logger.warning(
            "wiki_build_finalize_empty_pages preview=%s",
            _pages_preview_for_log(pages),
        )
        raise BuildOutputInvalid("build_output_empty_pages: 资料未生成任何有效知识页面")
    if "source" not in allowed_page_types or not source_metadata:
        finalized = _merge_pages(normalized, kb=kb)
        return ensure_contact_facts_preserved(source_text, finalized)

    source_title = str(source_metadata.get("source_title") or "").strip()
    if not source_title:
        raise BuildOutputInvalid("build_output_invalid_source: 来源页面标题为空")

    other_pages = _merge_pages(
        [page for page in normalized if page.get("page_type") != "source"],
        kb=kb,
    )
    if not other_pages:
        # LLM sometimes only emits source. Reuse that body as one concept topic
        # rather than failing the whole material build.
        promoted = []
        for page in normalized:
            if page.get("page_type") != "source":
                continue
            body = str(page.get("body") or "").strip()
            if len(body) < 20:
                continue
            topic_title = str(page.get("title") or source_title).strip() or source_title
            if _title_key(topic_title, kb) == _title_key(source_title, kb):
                topic_title = f"{source_title}·主题摘录"
            promoted.append(
                {
                    **page,
                    "page_type": "concept",
                    "title": topic_title,
                    "body": body,
                    "directory_reason": page.get("directory_reason") or "promoted_from_source",
                }
            )
        if promoted:
            logger.warning(
                "wiki_build_promoted_source_to_topic count=%s titles=%s",
                len(promoted),
                [item.get("title") for item in promoted],
            )
            other_pages = _merge_pages(promoted, kb=kb)
    if not other_pages:
        logger.warning(
            "wiki_build_finalize_empty_topic_pages preview=%s",
            _pages_preview_for_log(normalized or pages),
        )
        raise BuildOutputInvalid("build_output_empty_topic_pages: 资料未生成任何有效主题页面")

    occupied_title_keys = {_title_key(page.get("title"), kb) for page in other_pages}
    if _title_key(source_title, kb) in occupied_title_keys:
        source_title = f"资料：{source_title}"
    if _title_key(source_title, kb) in occupied_title_keys:
        source_title = f"资料：{source_title} · {source_metadata.get('material_id')}"
    effective_source_metadata = {**source_metadata, "source_title": source_title}

    source_pages = [page for page in normalized if page.get("page_type") == "source"]
    source_pages = [
        {
            **page,
            "title": source_title,
            "directory_key": _source_default_directory_key(structure_revision),
            "directory_confidence": 1.0,
            "directory_reason": "material_source_contract",
            "aliases": _normalize_text_list(
                [*(page.get("aliases") or []), source_metadata.get("display_name")],
                32,
            ),
        }
        for page in source_pages
    ]
    if not source_pages:
        source_pages = [_fallback_source_page(other_pages, effective_source_metadata, structure_revision)]
    finalized = [*other_pages, *_merge_pages(source_pages, kb=kb)]
    return ensure_contact_facts_preserved(source_text, finalized)


def _llm_generate_pages(
    kb,
    source_text,
    llm_model_id,
    *,
    structure_revision=None,
    classification_root_id=None,
    source_metadata=None,
    contact_source_text=None,
):
    """Stage2:依据 Purpose 与固定 Structure Schema 从要点生成页面列表。

    返回 page 列表(向后兼容签名);解析失败通过 errors_collector 参数旁路收集。
    无模型或 source_text 为空时返回 []。
    contact_source_text 用于定稿后联系方式补漏；缺省回退到 source_text。
    """
    if not llm_model_id or not (source_text or "").strip():
        if source_metadata is not None:
            raise BuildOutputInvalid("build_output_empty_pages: 资料缺少可构建正文或可用模型")
        return []
    pages = []
    errors = []
    directory_context = _directory_prompt_context(structure_revision, classification_root_id)
    page_contract = _generation_page_contract(structure_revision, source_metadata)
    source_context = json.dumps(_prompt_source_metadata(source_metadata), ensure_ascii=False, sort_keys=True)
    primary, _, _ = _material_window_limits(llm_model_id)
    chunks = split_text_by_estimated_tokens(source_text, max_tokens=primary.build_chunk_tokens)
    existing_catalog = json.dumps(
        [
            {"id": page.id, "title": page.title, "page_type": page.page_type}
            for page in KnowledgePage.objects.filter(
                knowledge_base=kb,
                status__in=["active", "source_invalid"],
            ).order_by("id")
        ],
        ensure_ascii=False,
    )
    for idx, chunk in enumerate(chunks, start=1):
        prompt = (
            "你是企业知识库构建助手。请依据 Purpose 与下面固定的 Structure Schema,"
            "从已抽取的要点生成知识页面。\n"
            f"{_JSON_ONLY_OUTPUT_RULES}"
            'JSON 字段约定：{"pages": [{"page_type":"...","title":"...","tags":["..."],'
            '"body":"markdown","existing_page_id":123或null,"directory_key":"稳定目录 key",'
            '"directory_confidence":0.0,"directory_reason":"简短原因"}]}。\n'
            "page_type 必须来自固定 Structure Schema 的 page_types；"
            '无可提取内容时输出 {"pages":[]}。\n'
            "directory_key 只能来自同一固定 Structure Schema 的 directories，"
            "不得创建、改写或猜测 key；"
            "不确定时可省略 key，由服务端确定性回退。\n"
            "生成原则:不要只输出总览页面;对资料中反复出现的产品、平台、组件、模块、能力中心、"
            "依赖项、服务、表格行中的核心对象,应优先拆成独立实体页或概念页。\n"
            "先对照现有页面清单判断是否为同一知识主题。语义相同但标题不同也应复用现有页面标题,"
            "并填写对应 existing_page_id;确实是新主题时 existing_page_id 填 null。\n"
            "同一对象的缩写、英文名、中文全称必须使用同一个页面标题;优先使用中文全称,"
            "例如 CMDB 与 配置平台 使用 配置平台,JOB 与 作业平台 使用 作业平台,不要分别建页。\n"
            "页面正文应使用 [[目标页面标题]] 引用相关页面,便于后续关系图谱建边。\n"
            f"{_FACT_PRESERVATION_RULES}"
            "注意:这是同一份资料的分块处理,如果当前片段补充了已有主题,可以输出同名页面,"
            "系统会合并同名页面内容。\n\n"
            f"# Purpose\n{kb.purpose_md}"
            f"\n\n# 现有页面清单\n{existing_catalog}"
            f"\n\n# Fixed Structure Schema\n{directory_context or 'unclassified-only'}"
            f"\n\n# Current Material\n{source_context or '{}'}"
            f"\n\n# Page Generation Contract\n{page_contract}"
            f"\n\n# 要点片段 {idx}/{len(chunks)}\n{chunk}\n"
        )
        raw_result = _invoke_llm(llm_model_id, prompt)
        parsed_pages = _parse_pages(
            raw_result,
            chunk_index=idx,
            total_chunks=len(chunks),
            errors_collector=errors,
        )
        logger.info(
            "wiki_build_stage2_chunk kb_id=%s model_id=%s chunk=%s/%s output_chars=%s response_empty=%s page_count=%s",
            kb.id,
            llm_model_id,
            idx,
            len(chunks),
            len(raw_result or ""),
            not bool((raw_result or "").strip()),
            len(parsed_pages),
        )
        pages.extend(parsed_pages)
    merged = _finalize_material_pages(
        pages,
        kb=kb,
        structure_revision=structure_revision,
        source_metadata=source_metadata,
        source_text=contact_source_text if contact_source_text is not None else source_text,
    )
    # 把 errors 暂存到函数属性,build_from_material 读取后清空
    _llm_generate_pages.last_errors = list(errors)
    return merged


def _bounded_generation_prompt(
    kb,
    source_text,
    *,
    structure_revision,
    classification_root_id,
    source_metadata=None,
):
    directory_context = _directory_prompt_context(
        structure_revision,
        classification_root_id,
    )
    page_contract = _generation_page_contract(structure_revision, source_metadata)
    source_context = json.dumps(
        _prompt_source_metadata(source_metadata),
        ensure_ascii=False,
        sort_keys=True,
    )
    return (
        "你是企业知识库构建助手。依据 Purpose 与固定 Structure Schema 生成最终知识页面。\n"
        f"{_JSON_ONLY_OUTPUT_RULES}"
        'JSON 字段约定：{"pages":[{"page_type":"concept","title":"...",'
        '"tags":[],"body":"markdown","directory_key":"...",'
        '"directory_confidence":0.0,"directory_reason":"...",'
        '"summary":"不超过800字符","keywords":[],"entities":[],"aliases":[]}]}。\n'
        "page_type 必须来自固定 Structure Schema 的 page_types；"
        "directory_key 只能来自同一 Schema 的 directories，不得猜测不存在的 key。"
        "页面正文必须非空；summary、keywords、entities、aliases 只用于导航召回，"
        "必须来自本资料，不得补造事实。\n"
        f"{_FACT_PRESERVATION_RULES}\n"
        f"# Purpose\n{kb.purpose_md}\n\n"
        f"# Fixed Structure Schema\n{directory_context}\n\n"
        f"# Current Material\n{source_context or '{}'}\n\n"
        f"# Page Generation Contract\n{page_contract}\n\n"
        f"# Source\n{source_text}"
    )


def _attach_map_checkpoint(error, mapped, chunk_count):
    error.details = {
        **error.details,
        "partial_map_outputs": list(mapped),
        "map_chunk_count": int(chunk_count),
        "completed_map_calls": len(mapped),
    }


def _source_token_limit(input_limit, prompt_without_source):
    return max(
        int(input_limit) - estimate_tokens(prompt_without_source) - _PROMPT_SAFETY_TOKENS,
        256,
    )


def _material_map_prompt(chunk, index, total):
    return (
        "从资料片段中提取可验证的事实、具名实体候选、可复用概念候选、依赖关系、明确问题、对比维度、限定条件、时间、数值、步骤、"
        "联系人/电话/内线/邮箱/URL 等可核验线索和页码/幻灯片/标题来源线索。\n"
        f"{_JSON_ONLY_OUTPUT_RULES}"
        f"{_FACT_PRESERVATION_RULES}"
        "本阶段不要生成 Wiki 页面，不推测缺失信息；"
        "这是同一份资料的一个片段，必须保留可用于后续归并的上下文。\n"
        '推荐格式：{"facts":["..."],"entities":["..."],"concepts":["..."],'
        '"relations":["..."],"open_questions":["..."],"source_hints":["..."]}。\n\n'
        f"# Chunk {index}/{total}\n{chunk}"
    )


def _format_reduce_items(items):
    return "\n\n".join(f"## Fact batch {index}\n{value}" for index, value in enumerate(items, start=1))


def _material_compact_prompt(source, round_index, group_index, group_count):
    return (
        "合并并去重下面的资料事实批次，保留具名实体、概念、关系、明确问题、对比维度、限定条件、时间、数值、步骤、"
        "联系人/电话/内线/邮箱/URL 等可核验线索和来源线索。\n"
        f"{_JSON_ONLY_OUTPUT_RULES}"
        f"{_FACT_PRESERVATION_RULES}"
        "本阶段不生成 Wiki 页面，不补造事实。\n\n"
        f"# Reduce round {round_index}, group {group_index}/{group_count}\n{source}"
    )


def _group_reduce_items(items, max_tokens):
    groups = []
    current = []
    for item in items:
        candidate = [*current, item]
        if current and estimate_tokens(_format_reduce_items(candidate)) > max_tokens:
            groups.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        groups.append(current)
    return groups


def _compact_mapped_outputs(
    mapped,
    *,
    llm_model_id,
    budget,
    final_source_limit,
    chunk_count,
):
    current = list(mapped)
    round_index = 0
    while estimate_tokens(_format_reduce_items(current)) > final_source_limit:
        round_index += 1
        if round_index > _MATERIAL_MAX_REDUCE_ROUNDS:
            raise WikiBudgetExceeded(
                "wiki_reduce_safety_limit_exceeded",
                "资料事实归并超过系统安全轮次",
                details=budget.trace(
                    reduce_round=round_index,
                    map_chunk_count=chunk_count,
                ),
            )

        empty_prompt = _material_compact_prompt("", round_index, 99999, 99999)
        primary, _map_output, reduce_output = _material_window_limits(llm_model_id)
        compact_source_limit = _source_token_limit(
            primary.input_working_tokens,
            empty_prompt,
        )
        groups = _group_reduce_items(current, compact_source_limit)
        previous_tokens = estimate_tokens(_format_reduce_items(current))
        compacted = []
        for group_index, group in enumerate(groups, start=1):
            prompt = _material_compact_prompt(
                _format_reduce_items(group),
                round_index,
                group_index,
                len(groups),
            )
            output = _invoke_llm_retryable(
                llm_model_id,
                prompt,
                budget=budget,
                stage=f"material_reduce_compact_{round_index}_{group_index}",
                output_reserve=reduce_output,
                force_json=True,
                on_budget_exceeded=lambda error: _attach_map_checkpoint(error, current, chunk_count),
                skip_after_retry=False,
            )
            if output:
                compacted.append(output)

        if not compacted:
            return []
        compacted_tokens = estimate_tokens(_format_reduce_items(compacted))
        if len(compacted) >= len(current) and compacted_tokens >= previous_tokens:
            raise WikiBudgetExceeded(
                "wiki_reduce_no_progress",
                "资料事实归并未能继续压缩，已触发系统安全保护",
                details=budget.trace(
                    reduce_round=round_index,
                    map_chunk_count=chunk_count,
                    previous_tokens=previous_tokens,
                    compacted_tokens=compacted_tokens,
                ),
            )
        current = compacted
    return current


def _is_retryable_build_output_error(error):
    message = str(error or "")
    return any(marker in message for marker in _RETRYABLE_BUILD_OUTPUT_MARKERS)


def _invoke_llm_retryable(
    llm_model_id,
    prompt,
    *,
    budget,
    stage,
    output_reserve,
    force_json=False,
    on_budget_exceeded=None,
    skip_after_retry=False,
    skipped=None,
):
    """Retry once on retryable empty/invalid LLM output.

    Map may skip the chunk after the last attempt; compact must raise instead.
    """

    for attempt in range(1, _GENERATE_OUTPUT_MAX_ATTEMPTS + 1):
        attempt_stage = stage if attempt == 1 else f"{stage}_retry_{attempt}"
        try:
            return _invoke_llm(
                llm_model_id,
                prompt,
                budget=budget,
                stage=attempt_stage,
                output_reserve=output_reserve,
                force_json=force_json,
            ).strip()
        except WikiBudgetExceeded as error:
            if on_budget_exceeded is not None:
                on_budget_exceeded(error)
            raise
        except BuildOutputInvalid as exc:
            if not _is_retryable_build_output_error(exc):
                raise
            if attempt >= _GENERATE_OUTPUT_MAX_ATTEMPTS:
                if not skip_after_retry:
                    raise
                logger.warning(
                    "wiki_build_llm_skip stage=%s attempt=%s/%s error_type=%s",
                    stage,
                    attempt,
                    _GENERATE_OUTPUT_MAX_ATTEMPTS,
                    type(exc).__name__,
                )
                if skipped is not None:
                    skipped.append(_map_skip_record(stage, exc))
                return ""
            logger.warning(
                "wiki_build_llm_retry stage=%s attempt=%s/%s error_type=%s",
                stage,
                attempt,
                _GENERATE_OUTPUT_MAX_ATTEMPTS,
                type(exc).__name__,
            )
    return ""


def _retry_correction_prompt(base_prompt, error):
    return (
        f"{base_prompt}\n\n"
        "# Previous output rejected — regenerate once\n"
        f"Rejection reason: {error}\n"
        "Requirements for this retry:\n"
        '1. Output exactly one JSON object: {"pages":[...]}.\n'
        "2. Every page MUST include non-empty page_type, title, and body.\n"
        "3. Include exactly one source page AND at least one concept/entity topic page.\n"
        '4. Escape quotes inside body as \\". Do not wrap JSON in markdown fences.\n'
        'Minimal valid shape: {"pages":[{"page_type":"source","title":"...","body":"..."},'
        '{"page_type":"concept","title":"...","body":"..."}]}.'
    )


def _generate_and_finalize_pages(
    *,
    llm_model_id,
    prompt,
    budget,
    stage,
    output_reserve,
    kb,
    structure_revision,
    source_metadata,
    source_text=None,
    chunk_index=None,
    total_chunks=None,
):
    """Invoke LLM, parse pages, finalize; retry once on retryable JSON/structure failures."""
    current_prompt = prompt
    last_error = None
    for attempt in range(1, _GENERATE_OUTPUT_MAX_ATTEMPTS + 1):
        attempt_stage = stage if attempt == 1 else f"{stage}_retry_{attempt}"
        try:
            pages = _parse_pages(
                _invoke_llm(
                    llm_model_id,
                    current_prompt,
                    budget=budget,
                    stage=attempt_stage,
                    output_reserve=output_reserve,
                    force_json=True,
                ),
                chunk_index=chunk_index,
                total_chunks=total_chunks,
                strict=True,
            )
            return _finalize_material_pages(
                pages,
                kb=kb,
                structure_revision=structure_revision,
                source_metadata=source_metadata,
                source_text=source_text,
            )
        except BuildOutputInvalid as exc:
            last_error = exc
            if attempt >= _GENERATE_OUTPUT_MAX_ATTEMPTS or not _is_retryable_build_output_error(exc):
                raise
            logger.warning(
                "wiki_build_generate_retry stage=%s attempt=%s/%s error=%s",
                stage,
                attempt,
                _GENERATE_OUTPUT_MAX_ATTEMPTS,
                exc,
            )
            current_prompt = _retry_correction_prompt(prompt, exc)
    raise last_error


def generate_material_pages_with_budget(
    kb,
    text,
    llm_model_id,
    *,
    budget,
    structure_revision,
    classification_root_id=None,
    source_metadata=None,
):
    """Generate pages with adaptive Map and hierarchical Reduce.

    The configured per-material token amount is a soft audit threshold. Complete
    parsed content is processed in context-safe calls; only call/context and
    abnormal-loop safety guards can stop the task.
    """

    source = (text or "").strip()
    skipped = []

    def _finish(pages):
        if skipped:
            logger.info(
                "wiki_build_llm_skipped kb=%s skipped=%s stages=%s",
                getattr(kb, "pk", None) or getattr(kb, "id", None),
                len(skipped),
                ",".join(item.get("stage") or "-" for item in skipped),
            )
        return MaterialPageGeneration(pages=pages, skipped=skipped)

    if not source or not llm_model_id:
        if source_metadata is not None:
            raise BuildOutputInvalid("build_output_empty_pages: 资料缺少可构建正文或可用模型")
        return _finish([])

    primary, map_output, _reduce_output = _material_window_limits(llm_model_id)
    empty_generation_prompt = _bounded_generation_prompt(
        kb,
        "",
        structure_revision=structure_revision,
        classification_root_id=classification_root_id,
        source_metadata=source_metadata,
    )
    final_source_limit = _source_token_limit(
        primary.input_working_tokens,
        empty_generation_prompt,
    )
    if estimate_tokens(source) <= final_source_limit:
        prompt = _bounded_generation_prompt(
            kb,
            source,
            structure_revision=structure_revision,
            classification_root_id=classification_root_id,
            source_metadata=source_metadata,
        )
        return _finish(
            _generate_and_finalize_pages(
                llm_model_id=llm_model_id,
                prompt=prompt,
                budget=budget,
                stage="material_generate",
                output_reserve=primary.output_reserve_tokens,
                kb=kb,
                structure_revision=structure_revision,
                source_metadata=source_metadata,
                source_text=source,
            )
        )

    empty_map_prompt = _material_map_prompt("", 99999, 99999)
    map_source_limit = _source_token_limit(
        primary.input_working_tokens,
        empty_map_prompt,
    )
    # Keep semantic source windows stable when prompt wording changes. Context
    # safety is still enforced above; this cap is based on source size alone.
    map_source_limit = min(map_source_limit, primary.build_chunk_tokens)
    chunks = split_text_by_estimated_tokens(
        source,
        max_tokens=map_source_limit,
    )
    mapped = []
    for index, chunk in enumerate(chunks, start=1):
        prompt = _material_map_prompt(chunk, index, len(chunks))
        output = _invoke_llm_retryable(
            llm_model_id,
            prompt,
            budget=budget,
            stage=f"material_map_{index}",
            output_reserve=map_output,
            force_json=True,
            on_budget_exceeded=lambda error, mapped=mapped, chunk_count=len(chunks): _attach_map_checkpoint(error, mapped, chunk_count),
            skip_after_retry=True,
            skipped=skipped,
        )
        if output:
            mapped.append(output)
    if not mapped:
        return _finish(
            _finalize_material_pages(
                [],
                kb=kb,
                structure_revision=structure_revision,
                source_metadata=source_metadata,
                source_text=source,
            )
        )

    mapped = _compact_mapped_outputs(
        mapped,
        llm_model_id=llm_model_id,
        budget=budget,
        final_source_limit=final_source_limit,
        chunk_count=len(chunks),
    )
    if not mapped:
        return _finish(
            _finalize_material_pages(
                [],
                kb=kb,
                structure_revision=structure_revision,
                source_metadata=source_metadata,
                source_text=source,
            )
        )

    prompt = _bounded_generation_prompt(
        kb,
        _format_reduce_items(mapped),
        structure_revision=structure_revision,
        classification_root_id=classification_root_id,
        source_metadata=source_metadata,
    )
    try:
        return _finish(
            _generate_and_finalize_pages(
                llm_model_id=llm_model_id,
                prompt=prompt,
                budget=budget,
                stage="material_reduce_generate",
                output_reserve=primary.output_reserve_tokens,
                kb=kb,
                structure_revision=structure_revision,
                source_metadata=source_metadata,
                source_text=source,
            )
        )
    except WikiBudgetExceeded as error:
        _attach_map_checkpoint(error, mapped, len(chunks))
        raise


def _log_text_preview(text, *, head=_PARSE_LOG_PREVIEW_CHARS, tail=_PARSE_LOG_PREVIEW_CHARS):
    value = str(text or "").replace("\r\n", "\n")
    if len(value) <= head + tail + 32:
        return value
    return f"{value[:head]}\n...({len(value)} chars total)...\n{value[-tail:]}"


def _normalize_jsonish_text(raw):
    """Strip reasoning wrappers and normalize common fullwidth JSON punctuation."""
    text = str(raw or "").strip()
    if not text:
        return ""
    text = _THINK_BLOCK_RE.sub("", text)
    text = text.translate(
        str.maketrans(
            {
                "｛": "{",
                "｝": "}",
                "［": "[",
                "］": "]",
                "“": '"',
                "”": '"',
                "‘": "'",
                "’": "'",
            }
        )
    )
    return text.strip()


def _extract_json_candidate(raw):
    """Pick the most likely JSON object/array from mixed LLM prose."""
    text = _normalize_jsonish_text(raw)
    if not text:
        return ""

    fence_blocks = [block.strip() for block in _CODE_FENCE_RE.findall(text) if block.strip()]
    preferred = [block for block in fence_blocks if '"pages"' in block or "'pages'" in block or block.lstrip()[:1] in {"{", "["}]
    if preferred:
        text = max(preferred, key=len)
    elif fence_blocks:
        text = max(fence_blocks, key=len)

    stripped = text.lstrip()
    if stripped.startswith("["):
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end > start:
            return text[start : end + 1]

    pages_idx = text.find('"pages"')
    if pages_idx == -1:
        pages_idx = text.find("'pages'")
    if pages_idx != -1:
        start = text.rfind("{", 0, pages_idx + 1)
        end = text.rfind("}")
        if start != -1 and end > start:
            return text[start : end + 1]

    if stripped.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            return text[start : end + 1]

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        return text[start : end + 1]
    return ""


def _parse_pages(
    content,
    chunk_index=None,
    total_chunks=None,
    errors_collector=None,
    *,
    strict=False,
):
    """从 LLM 输出中解析 pages 列表,容忍代码块/推理标签/全角括号。

    legacy 调用保持返回空列表；generation 构建使用 strict=True，
    结构化输出无效时必须终止候选发布。
    """
    original = (content or "").strip()
    loc = f"chunk={chunk_index}/{total_chunks}" if chunk_index is not None else "chunk=?"
    candidate = _extract_json_candidate(original)
    if not candidate:
        err = f"_parse_pages 失败 [{loc}]: 未找到匹配的 {{...}} 区间, " f"output_chars={len(original)}, preview={_log_text_preview(original)!r}"
        logger.warning(err)
        if errors_collector is not None:
            errors_collector.append(err)
        if strict:
            raise BuildOutputInvalid(f"build_output_invalid_json: {err}")
        return []

    try:
        data = json.loads(candidate)
    except (TypeError, ValueError) as exc:
        try:
            data = json_repair.loads(candidate)
        except Exception as repair_exc:  # noqa: BLE001 - 保留原始 JSON 异常作为业务错误
            err = (
                f"_parse_pages 失败 [{loc}]: JSON 解析异常 {type(exc).__name__}: {exc}; "
                f"本地修复失败 {type(repair_exc).__name__}: {repair_exc}, "
                f"output_chars={len(original)}, candidate_chars={len(candidate)}, "
                f"preview={_log_text_preview(original)!r}"
            )
            logger.warning(err)
            if errors_collector is not None:
                errors_collector.append(err)
            if strict:
                raise BuildOutputInvalid(f"build_output_invalid_json: {err}") from exc
            return []
        logger.warning(
            "wiki_build_output_json_repaired %s original_error=%s output_chars=%s candidate_chars=%s",
            loc,
            exc,
            len(original),
            len(candidate),
        )

    if isinstance(data, list):
        data = {"pages": data}
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        err = f"_parse_pages 失败 [{loc}]: JSON 缺少 pages 数组, " f"output_chars={len(original)}, preview={_log_text_preview(original)!r}"
        logger.warning(err)
        if errors_collector is not None:
            errors_collector.append(err)
        if strict:
            raise BuildOutputInvalid(f"build_output_invalid_json: {err}")
        return []
    pages = data["pages"]
    valid_pages = [p for p in pages if isinstance(p, dict) and p.get("title")]
    if strict and pages and not valid_pages:
        raise BuildOutputInvalid("build_output_invalid_json: pages 中没有包含有效 title 的知识页面")
    return valid_pages


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
            merged_page = {
                "page_type": page.get("page_type", "concept"),
                "title": title,
                "tags": list(dict.fromkeys(tags)),
                "body": body,
                "directory_key": page.get("directory_key"),
                "directory_confidence": page.get("directory_confidence"),
                "directory_reason": page.get("directory_reason") or "",
                "directory_schema_mismatch": bool(page.get("directory_schema_mismatch", False)),
                "summary": str(page.get("summary") or "").strip()[:800],
                "keywords": list(dict.fromkeys(page.get("keywords") or []))[:32],
                "entities": list(dict.fromkeys(page.get("entities") or []))[:32],
                "aliases": list(dict.fromkeys(page.get("aliases") or []))[:32],
            }
            if page.get("existing_page_id") is not None:
                merged_page["existing_page_id"] = page["existing_page_id"]
            merged[key] = merged_page
            order.append(key)
            continue
        current = merged[key]
        current["tags"] = list(dict.fromkeys([*current.get("tags", []), *tags]))
        if current.get("existing_page_id") is None and page.get("existing_page_id") is not None:
            current["existing_page_id"] = page["existing_page_id"]
        if body and body not in current.get("body", ""):
            current["body"] = "\n\n".join(part for part in [current.get("body", ""), body] if part)
        try:
            current_confidence = float(current.get("directory_confidence"))
        except (TypeError, ValueError):
            current_confidence = -1.0
        try:
            incoming_confidence = float(page.get("directory_confidence"))
        except (TypeError, ValueError):
            incoming_confidence = -1.0
        if incoming_confidence > current_confidence and page.get("directory_key"):
            current["directory_key"] = page.get("directory_key")
            current["directory_confidence"] = page.get("directory_confidence")
            current["directory_reason"] = page.get("directory_reason") or ""
        current["directory_schema_mismatch"] = bool(current.get("directory_schema_mismatch") or page.get("directory_schema_mismatch"))
        if not current.get("summary") and page.get("summary"):
            current["summary"] = str(page.get("summary") or "").strip()[:800]
        current["keywords"] = list(dict.fromkeys([*(current.get("keywords") or []), *(page.get("keywords") or [])]))[:32]
        current["entities"] = list(dict.fromkeys([*(current.get("entities") or []), *(page.get("entities") or [])]))[:32]
        current["aliases"] = list(dict.fromkeys([*(current.get("aliases") or []), *(page.get("aliases") or [])]))[:32]
    return [merged[key] for key in order]


def _title_key(title, kb=None):
    title = _canonical_title(kb, title) if kb else title
    return (title or "").strip().lower()


def _next_version_no(page):
    last = page.page_versions.order_by("-no").first()
    return (last.no + 1) if last else 1


def _existing_pages_by_title(kb):
    pages = KnowledgePage.objects.filter(knowledge_base=kb).select_related("current_version").order_by("id")
    result = {}
    for page in pages:
        key = _title_key(page.title, kb)
        if key and key not in result:
            result[key] = page
    return result


def _existing_page_by_id(kb, page_id):
    try:
        page_id = int(page_id)
    except (TypeError, ValueError):
        return None
    if page_id <= 0:
        return None
    return (
        KnowledgePage.objects.filter(
            id=page_id,
            knowledge_base=kb,
            status__in=["active", "source_invalid"],
        )
        .select_related("current_version")
        .first()
    )


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


def _ensure_evidence(page, material, locator="", material_version=_CURRENT_MATERIAL_VERSION):
    if material_version is _CURRENT_MATERIAL_VERSION:
        material_version = getattr(material, "current_version", None)
    material_version_id = getattr(material_version, "id", None)
    evidence = (
        PageEvidence.objects.filter(
            page=page,
            material=material,
            material_version_id=material_version_id,
        )
        .order_by("id")
        .first()
    )
    if evidence is None:
        PageEvidence.objects.create(
            page=page,
            material=material,
            material_version=material_version,
            locator=locator or "",
        )
        return True
    update_fields = []
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


def _classify_page_change(page, page_data, llm_model_id):
    """判断新旧正文是否为同一主题，以及属于无变化、补充还是事实冲突。"""
    current_body = page.current_version.body if page.current_version_id else ""
    incoming_body = (page_data.get("body") or "").strip()
    if not current_body.strip() or not incoming_body:
        logger.info(
            "wiki_conflict_compare kb_id=%s page_id=%s model_id=%s status=skipped_empty_body",
            page.knowledge_base_id,
            page.id,
            llm_model_id,
        )
        return None
    if current_body.strip() == incoming_body:
        logger.info(
            "wiki_conflict_compare kb_id=%s page_id=%s model_id=%s status=deterministic_equal same_subject=true relation=unchanged",
            page.knowledge_base_id,
            page.id,
            llm_model_id,
        )
        return {"same_subject": True, "relation": "unchanged", "reason": ""}

    prompt = (
        "你是企业知识冲突检测助手。请比较当前知识与新知识，只判断事实结论是否互相矛盾。\n"
        "同一主题下新增不矛盾的细节属于 supplement；事实结论相同属于 unchanged；"
        "同一条件下数值、责任人、状态、步骤或规则互斥才属于 conflict。\n"
        '只输出 JSON：{"same_subject":true或false,"relation":"unchanged|supplement|conflict","reason":"简短原因"}。\n\n'
        f"# 当前知识\n标题：{page.title}\n正文：\n{current_body}\n\n"
        f"# 新知识\n标题：{page_data.get('title') or ''}\n正文：\n{incoming_body}\n"
    )
    raw = (_invoke_llm(llm_model_id, prompt) or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1:
        logger.warning(
            "wiki_conflict_compare kb_id=%s page_id=%s model_id=%s status=invalid_json output_chars=%s",
            page.knowledge_base_id,
            page.id,
            llm_model_id,
            len(raw),
        )
        return None
    try:
        result = json.loads(raw[start : end + 1])
    except (TypeError, ValueError):
        logger.warning(
            "wiki_conflict_compare kb_id=%s page_id=%s model_id=%s status=json_parse_failed output_chars=%s",
            page.knowledge_base_id,
            page.id,
            llm_model_id,
            len(raw),
        )
        return None
    if not isinstance(result, dict) or not isinstance(result.get("same_subject"), bool):
        logger.warning(
            "wiki_conflict_compare kb_id=%s page_id=%s model_id=%s status=invalid_schema output_chars=%s",
            page.knowledge_base_id,
            page.id,
            llm_model_id,
            len(raw),
        )
        return None
    if result.get("relation") not in {"unchanged", "supplement", "conflict"}:
        logger.warning(
            "wiki_conflict_compare kb_id=%s page_id=%s model_id=%s status=invalid_relation output_chars=%s",
            page.knowledge_base_id,
            page.id,
            llm_model_id,
            len(raw),
        )
        return None
    return {
        "same_subject": result["same_subject"],
        "relation": result["relation"],
        "reason": str(result.get("reason") or "").strip(),
    }


def _has_other_material_source(page, material):
    return PageEvidence.objects.filter(page=page).exclude(material=material).exists()


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


def _incoming_material_snapshot(material, material_version=_CURRENT_MATERIAL_VERSION):
    if material_version is _CURRENT_MATERIAL_VERSION:
        material_version = getattr(material, "current_version", None)
    return {
        "material_id": getattr(material, "id", None),
        "material_version_id": getattr(material_version, "id", None),
        "content_hash": (getattr(material_version, "content_hash", "") or getattr(material, "content_hash", "") or ""),
    }


def resolve_knowledge_conflict(
    page,
    material,
    build,
    candidate_body,
    *,
    operator="",
    check_type="cannot_merge",
    reason="知识结论发生变化，需人工选择当前知识或新知识",
    related=None,
    locator="",
):
    """在短事务内以最新页面状态执行 unchanged / replayed / pending 三态编排。"""
    from apps.opspilot.services.wiki.decision_service import (
        build_participants_from_page_evidence,
        compute_schema_fingerprint,
        replay_decision,
        subject_key_for_page,
    )

    incoming_material_version = getattr(material, "current_version", None)
    incoming_snapshot = _incoming_material_snapshot(
        material,
        material_version=incoming_material_version,
    )
    with transaction.atomic():
        locked_kb = WikiKnowledgeBase.objects.select_for_update().get(pk=page.knowledge_base_id)
        locked_page = KnowledgePage.objects.select_for_update().get(
            pk=page.pk,
            knowledge_base=locked_kb,
        )
        locked_page.knowledge_base = locked_kb
        if locked_page.current_version_id:
            locked_page.current_version = PageVersion.objects.select_for_update().get(pk=locked_page.current_version_id)
        participants = build_participants_from_page_evidence(
            locked_page,
            incoming_snapshot=incoming_snapshot,
        )
        schema_fingerprint = compute_schema_fingerprint(locked_page.knowledge_base)
        subject_key = subject_key_for_page(
            page_type=locked_page.page_type or "concept",
            canonical_title=_canonical_title(locked_page.knowledge_base, locked_page.title),
        )
        result, rule = replay_decision(
            knowledge_base=locked_page.knowledge_base,
            decision_type="knowledge_conflict",
            subject_key=subject_key,
            schema_fingerprint=schema_fingerprint,
            participants=participants,
            page=locked_page,
            candidate_body=candidate_body,
        )
        if result == "replayed":
            return (
                "unchanged",
                {
                    "decision_reused": True,
                    "rule_id": rule.id,
                    "action": rule.action,
                },
            )
        if result == "unchanged":
            _ensure_evidence(
                locked_page,
                material,
                locator=locator,
                material_version=incoming_material_version,
            )
            return "unchanged", {}

        check = create_candidate(
            locked_page,
            body=candidate_body,
            reason=reason,
            check_type=check_type,
            build_record=build,
            created_by=operator,
            related=related or {"pages": [locked_page.id], "materials": [material.id]},
            incoming_material=material,
            incoming_material_version=incoming_material_version,
        )
        return "pending_review", {"check_id": check.id}


def _create_review_candidate(page, material, build, page_data, operator="", locator=""):
    return resolve_knowledge_conflict(
        page,
        material,
        build,
        page_data.get("body", "") or "",
        operator=operator,
        check_type="cannot_merge",
        reason="构建资料产生了不同知识结论，需人工选择",
        related={"pages": [page.id], "materials": [material.id]},
        locator=locator,
    )


def _maintenance_errors(maintenance):
    errors = []
    if maintenance.get("error"):
        errors.append(maintenance["error"])
    for stage in (maintenance.get("stages") or {}).values():
        if isinstance(stage, dict) and stage.get("error"):
            errors.append(stage["error"])
    return list(dict.fromkeys(errors))


def _run_build_cascade(knowledge_base, affected_page_ids):
    try:
        return cascade(knowledge_base, affected_page_ids, "build")
    except Exception as exc:
        logger.exception("wiki 构建级联维护异常 kb=%s", knowledge_base.id)
        error = humanize_maintenance_error(exc)
        return {
            "status": "partial",
            "event": "build",
            "affected_page_ids": list(affected_page_ids),
            "stages": {"cascade": {"status": "failed", "error": error}},
            "error": error,
        }


def build_from_material(
    material,
    llm_model_id=None,
    operator="",
    trigger="material",
    classification_root_id=None,
):
    """Build one material and publish it through a staging generation."""
    from apps.opspilot.services.wiki.build_generation_service import freeze_generation_identity

    with transaction.atomic():
        kb = material.knowledge_base.__class__.objects.select_for_update().get(pk=material.knowledge_base_id)
        material = material.__class__.objects.select_for_update().select_related("knowledge_base").get(pk=material.pk, knowledge_base=kb)
        identity = freeze_generation_identity(
            kb,
            [material],
            classification_root_id=classification_root_id,
        )
        material.status = "building"
        material.save(update_fields=["status", "updated_at"])
        build = BuildRecord.objects.create(
            knowledge_base=kb,
            trigger=trigger,
            operator=operator,
            inputs={
                "material_id": material.id,
                "task_identity": identity,
                "classification_root_id": classification_root_id,
            },
            stage="generating",
            status="running",
            base_generation_id=identity["base_generation_id"],
            structure_revision_id=identity["structure_revision_id"],
            structure_fingerprint=identity["structure_fingerprint"],
            pipeline_version=identity["pipeline_version"],
            source_fingerprints=identity["source_fingerprints"],
        )

    from apps.opspilot.services.wiki.generation_material_build_service import build_material_with_generation

    return build_material_with_generation(
        material,
        build,
        llm_model_id=llm_model_id,
        operator=operator,
        classification_root_id=classification_root_id,
        frozen_identity=identity,
    )
