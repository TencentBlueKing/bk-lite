import json
import logging
import re

from apps.opspilot.models import KnowledgePage, PageVersion
from apps.opspilot.services.wiki.relation_service import normalize_wikilink_key

logger = logging.getLogger("opspilot")

JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
WIKILINK_RE = re.compile(r"\[\[[^\]\n]+?\]\]")
FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def parse_wikilink_suggestions(raw):
    """Parse LLM wikilink suggestions from a JSON object."""
    text = JSON_FENCE_RE.sub("", (raw or "").strip())
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return []

    result = []
    for item in payload.get("links", []) or []:
        if not isinstance(item, dict):
            continue
        term = (item.get("term") or "").strip()
        target = (item.get("target") or "").strip()
        if term and target:
            result.append({"term": term, "target": target})
    return result


def apply_wikilink_suggestions(body, links, allowed_titles):
    """Apply safe term->target wikilink suggestions without rewriting page text."""
    enriched = body or ""
    normalized_targets = {normalize_wikilink_key(alias): title for alias, title in (allowed_titles or {}).items() if alias and title}
    linked_targets = _existing_linked_targets(enriched)
    inserted = 0

    for link in links or []:
        term = (link.get("term") or "").strip()
        target = (link.get("target") or "").strip()
        canonical_target = normalized_targets.get(normalize_wikilink_key(target))
        if not term or not canonical_target:
            continue

        target_key = normalize_wikilink_key(canonical_target)
        if target_key in linked_targets:
            continue

        idx = _find_unprotected_occurrence(enriched, term)
        if idx < 0:
            continue

        replacement = _format_wikilink(term, canonical_target)
        enriched = enriched[:idx] + replacement + enriched[idx + len(term) :]
        linked_targets.add(target_key)
        inserted += 1

    return enriched, inserted


def enrich_pages_wikilinks(
    knowledge_base,
    page_ids,
    llm_model_id,
    invoke_llm,
    build_record=None,
    operator="",
    canonicalize=None,
    alias_terms_resolver=None,
):
    """Use LLM suggestions to add wikilinks to affected AI-generated pages."""
    if not page_ids:
        return []

    active_pages = list(KnowledgePage.objects.filter(knowledge_base=knowledge_base, status="active").select_related("current_version"))
    actual_titles = {(page.title or "").strip() for page in active_pages if (page.title or "").strip()}
    source_ids = {int(page_id) for page_id in page_ids if page_id}
    sources = [page for page in active_pages if page.id in source_ids and page.current_version_id]
    enriched_ids = []

    for page in sources:
        target_pages = [target for target in active_pages if target.id != page.id]
        allowed_titles = _allowed_title_map(target_pages, actual_titles, canonicalize, alias_terms_resolver)
        if not allowed_titles:
            continue

        body = page.current_version.body or ""
        if not _body_contains_candidate_term(body, allowed_titles):
            continue

        direct_links = _direct_wikilink_suggestions(body, allowed_titles)
        enriched_body, inserted = apply_wikilink_suggestions(body, direct_links, allowed_titles)
        if inserted > 0 and enriched_body != body:
            _replace_current_version(page, enriched_body, build_record, operator)
            enriched_ids.append(page.id)
            continue

        if not llm_model_id:
            continue

        prompt = _build_enrichment_prompt(page.title, body, sorted(set(allowed_titles.values())))
        try:
            raw = invoke_llm(llm_model_id, prompt)
        except Exception:
            logger.exception("wiki wikilink enrichment failed page=%s", page.id)
            continue

        enriched_body, inserted = apply_wikilink_suggestions(body, parse_wikilink_suggestions(raw), allowed_titles)
        if inserted <= 0 or enriched_body == body:
            continue

        _replace_current_version(page, enriched_body, build_record, operator)
        enriched_ids.append(page.id)

    return enriched_ids


def _direct_wikilink_suggestions(body, allowed_titles):
    suggestions = []
    seen_targets = set()
    candidates = []
    for term, target in (allowed_titles or {}).items():
        term = (term or "").strip()
        target = (target or "").strip()
        if not term or not target:
            continue
        match = _find_unprotected_term(body, term)
        if not match:
            continue
        idx, actual_term = match
        candidates.append((idx, -len(actual_term), actual_term, target))

    for _, _, actual_term, target in sorted(candidates):
        target_key = normalize_wikilink_key(target)
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        suggestions.append({"term": actual_term, "target": target})
    return suggestions


def _allowed_title_map(pages, actual_titles, canonicalize=None, alias_terms_resolver=None):
    allowed = {}
    for page in pages:
        title = (page.title or "").strip()
        if not title:
            continue
        target_title = title
        if canonicalize:
            canonical = (canonicalize(title) or "").strip()
            if canonical in actual_titles:
                target_title = canonical

        allowed[title] = target_title
        allowed[target_title] = target_title
        if alias_terms_resolver:
            for alias in alias_terms_resolver(target_title) or []:
                if alias:
                    allowed[alias] = target_title
    return allowed


def _body_contains_candidate_term(body, allowed_titles):
    body_lower = (body or "").lower()
    for term in allowed_titles:
        term = (term or "").strip()
        if term and (term in body or term.lower() in body_lower):
            return True
    return False


def _build_enrichment_prompt(title, body, candidate_titles):
    index = "\n".join(f"- {item}" for item in candidate_titles if item)
    return (
        "你负责为企业知识库页面补充 [[WikiLink]]。只返回 JSON,不要返回完整页面,不要改写正文。\n"
        '输出格式严格为 {"links":[{"term":"正文中的原文片段","target":"候选页面标题"}]}。\n'
        "规则:\n"
        "- term 必须是页面正文中逐字存在的片段。\n"
        "- target 必须来自候选页面标题。\n"
        "- 不要建议已经被 [[...]] 包裹的内容。\n"
        '- 不确定时返回 {"links":[]}。\n\n'
        f"# 当前页面\n{title}\n\n# 候选页面标题\n{index}\n\n# 页面正文\n{body}\n"
    )


def _replace_current_version(page, body, build_record, operator):
    page.page_versions.filter(is_current=True).update(is_current=False)
    version = PageVersion.objects.create(
        page=page,
        no=_next_version_no(page),
        body=body,
        change_type="wikilink_enrich",
        build_record=build_record,
        is_current=True,
        created_by=operator or "",
    )
    page.current_version = version
    page.update_method = "wikilink_enrich"
    page.save(update_fields=["current_version", "update_method", "updated_at"])


def _next_version_no(page):
    last = page.page_versions.order_by("-no").first()
    return (last.no + 1) if last else 1


def _existing_linked_targets(body):
    targets = set()
    for match in WIKILINK_RE.finditer(body or ""):
        raw = match.group(0)[2:-2].strip()
        target = raw.split("|", 1)[0].strip()
        if target:
            targets.add(normalize_wikilink_key(target))
    return targets


def _find_unprotected_occurrence(text, term):
    protected = _protected_ranges(text)
    start = 0
    while True:
        idx = text.find(term, start)
        if idx < 0:
            return -1
        if not _range_overlaps(idx, idx + len(term), protected):
            return idx
        start = idx + len(term)


def _find_unprotected_term(text, term):
    idx = _find_unprotected_occurrence(text, term)
    if idx >= 0:
        return idx, text[idx : idx + len(term)]

    if not term.isascii():
        return None

    lowered_text = (text or "").lower()
    lowered_term = term.lower()
    protected = _protected_ranges(text)
    start = 0
    while True:
        idx = lowered_text.find(lowered_term, start)
        if idx < 0:
            return None
        if not _range_overlaps(idx, idx + len(term), protected):
            return idx, text[idx : idx + len(term)]
        start = idx + len(term)


def _protected_ranges(text):
    ranges = []
    for regex in (FENCED_CODE_RE, INLINE_CODE_RE, WIKILINK_RE):
        ranges.extend((match.start(), match.end()) for match in regex.finditer(text or ""))
    return ranges


def _range_overlaps(start, end, ranges):
    return any(start < protected_end and end > protected_start for protected_start, protected_end in ranges)


def _format_wikilink(term, target):
    if term.lower() == target.lower():
        return f"[[{term}]]"
    return f"[[{target}|{term}]]"
