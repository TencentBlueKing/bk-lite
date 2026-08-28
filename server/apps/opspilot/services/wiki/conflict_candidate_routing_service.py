"""Bounded generation-index routing for new-material conflict candidates."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import PageVersion, WikiGeneration, WikiGenerationIndexEntry
from apps.opspilot.services.wiki.build_service import BuildOutputInvalid
from apps.opspilot.services.wiki.title_service import title_identity_key
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, estimate_tokens

_MAX_COMPACT_CANDIDATES = 20
_MAX_EVIDENCE_PAGES = 5
_MAX_OLD_EVIDENCE_TOKENS = 8000
_CONFLICT_OUTPUT_RESERVE = 4000
_CONFLICT_INPUT_TOKEN_LIMIT = 12000
_CONFLICT_LLM_MAX_ATTEMPTS = 2
_MIN_BODY_EVIDENCE_TOKENS = 256
_TOKEN_RE = re.compile(r"[\w\-]{2,}", re.UNICODE)


@dataclass(frozen=True)
class ConflictRoutingResult:
    comparisons: dict
    compact_candidate_count: int
    evidence_page_ids: tuple
    old_evidence_tokens: int
    overflow_count: int
    llm_called: bool
    unresolved_incoming_indexes: tuple


def _terms(page_data):
    values = [
        page_data.get("title") or "",
        page_data.get("summary") or "",
        " ".join(page_data.get("tags") or []),
        " ".join(page_data.get("keywords") or []),
        " ".join(page_data.get("entities") or []),
    ]
    result = {item.casefold() for item in _TOKEN_RE.findall(" ".join(values))}
    title = str(page_data.get("title") or "").strip().casefold()
    if title:
        result.add(title)
    return result


def _candidate_score(page_data, entry):
    incoming_title = title_identity_key(page_data.get("title"))
    aliases = {title_identity_key(item) for item in (entry.aliases or [])}
    incoming_page_type = str(page_data.get("page_type") or "").strip()
    if incoming_page_type == "source" or entry.page_type == "source":
        if incoming_page_type != "source" or entry.page_type != "source":
            return 0
        if incoming_title and incoming_title == entry.normalized_title:
            return 100
        if incoming_title and incoming_title in aliases:
            return 90
        return 0
    if incoming_title and incoming_title == entry.normalized_title:
        return 100
    if incoming_title and incoming_title in aliases:
        return 90
    haystack = entry.search_text or ""
    terms = _terms(page_data)
    keywords = {str(item).casefold() for item in (entry.keywords or [])}
    return sum(5 if term in keywords else 1 for term in terms if term in haystack)


def _compact_candidates(base_generation_id, pages_data):
    entries = list(WikiGenerationIndexEntry.objects.filter(generation_id=base_generation_id).order_by("page_id"))
    candidates = []
    for incoming_index, page_data in enumerate(pages_data):
        for entry in entries:
            score = _candidate_score(page_data, entry)
            if score <= 0:
                continue
            candidates.append(
                {
                    "incoming_index": incoming_index,
                    "old_page_id": entry.page_id,
                    "old_page_version_id": entry.page_version_id,
                    "old_title": entry.title,
                    "score": score,
                }
            )
    candidates.sort(
        key=lambda item: (
            -item["score"],
            item["incoming_index"],
            item["old_page_id"],
        )
    )
    compact = candidates[:_MAX_COMPACT_CANDIDATES]
    version_bodies = {
        row["id"]: str(row["body"] or "").strip()
        for row in PageVersion.objects.filter(id__in={item["old_page_version_id"] for item in compact}).values("id", "body")
    }
    hydrated = []
    for item in compact:
        current_body = version_bodies.get(item["old_page_version_id"])
        if current_body is None:
            continue
        incoming_body = str(pages_data[item["incoming_index"]].get("body") or "").strip()
        hydrated.append(
            {
                **item,
                "old_body": current_body,
                "deterministic_relation": ("unchanged" if incoming_body and incoming_body == current_body else None),
            }
        )
    return hydrated, max(
        len(candidates) - _MAX_COMPACT_CANDIDATES,
        0,
    )


def _evidence_candidates(compact):
    selected = []
    selected_page_ids = set()
    used_tokens = 0
    for item in compact:
        if item["deterministic_relation"] == "unchanged":
            continue
        page_id = item["old_page_id"]
        body_tokens = estimate_tokens(item["old_body"])
        if page_id not in selected_page_ids and len(selected_page_ids) >= _MAX_EVIDENCE_PAGES:
            continue
        if used_tokens + body_tokens > _MAX_OLD_EVIDENCE_TOKENS:
            continue
        selected.append(item)
        selected_page_ids.add(page_id)
        used_tokens += body_tokens
    return selected, tuple(sorted(selected_page_ids)), used_tokens


def _truncate_to_token_budget(value, token_budget):
    text = str(value or "")
    token_budget = max(int(token_budget or 0), 0)
    if not text or estimate_tokens(text) <= token_budget:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if estimate_tokens(text[:middle]) <= token_budget:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def _conflict_prompt_prefix():
    return (
        "批量比较新旧知识。只有相同限定条件下事实互斥才是 conflict；新增兼容细节是 supplement；"
        "事实等价是 unchanged；主题不同是 unrelated。只输出 JSON："
        '{"comparisons":[{"incoming_index":0,"old_page_id":1,'
        '"same_subject":true,"relation":"unchanged|supplement|conflict|unrelated",'
        '"reason":"..."}]}。不得遗漏输入 pair。\n\n'
    )


def _bounded_conflict_prompt(evidence, pages_data, input_token_limit):
    """Fit the highest-ranked real evidence pairs into the remaining budget."""

    prefix = _conflict_prompt_prefix()
    if input_token_limit is None:
        selected = list(evidence)
        body_token_limit = None
    else:
        input_token_limit = max(int(input_token_limit), 0)
        prefix_tokens = estimate_tokens(prefix + "[]")
        selected = []
        body_token_limit = 0
        for candidate_count in range(len(evidence), 0, -1):
            candidates = list(evidence[:candidate_count])
            skeletons = [
                {
                    "incoming_index": item["incoming_index"],
                    "old_page_id": item["old_page_id"],
                    "new": {
                        "title": pages_data[item["incoming_index"]].get("title") or "",
                        "body": "",
                    },
                    "old": {"title": item["old_title"], "body": ""},
                }
                for item in candidates
            ]
            skeleton_tokens = estimate_tokens(json.dumps(skeletons, ensure_ascii=False))
            available_body_tokens = input_token_limit - prefix_tokens - skeleton_tokens
            per_body_tokens = available_body_tokens // (candidate_count * 2)
            if per_body_tokens >= _MIN_BODY_EVIDENCE_TOKENS:
                selected = candidates
                body_token_limit = per_body_tokens
                break
        if not selected:
            return "", [], ()

    prompt_items = []
    for item in selected:
        incoming = pages_data[item["incoming_index"]]
        new_body = str(incoming.get("body") or "")
        old_body = str(item["old_body"] or "")
        if body_token_limit is not None:
            new_body = _truncate_to_token_budget(new_body, body_token_limit)
            old_body = _truncate_to_token_budget(old_body, body_token_limit)
        prompt_items.append(
            {
                "incoming_index": item["incoming_index"],
                "old_page_id": item["old_page_id"],
                "new": {
                    "title": incoming.get("title") or "",
                    "body": new_body,
                },
                "old": {
                    "title": item["old_title"],
                    "body": old_body,
                },
            }
        )
    prompt = prefix + json.dumps(prompt_items, ensure_ascii=False)
    if input_token_limit is not None and estimate_tokens(prompt) > input_token_limit:
        return "", [], ()
    return prompt, prompt_items, tuple(sorted({item["old_page_id"] for item in selected}))


def _parse_comparisons(raw, allowed_pairs):
    text = str(raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return {}
    results = {}
    for item in payload.get("comparisons") or []:
        if not isinstance(item, dict):
            continue
        try:
            pair = (int(item.get("incoming_index")), int(item.get("old_page_id")))
        except (TypeError, ValueError):
            continue
        relation = item.get("relation")
        if pair not in allowed_pairs or relation not in {"unchanged", "supplement", "conflict", "unrelated"}:
            continue
        results[pair] = {
            "same_subject": bool(item.get("same_subject")),
            "relation": relation,
            "reason": str(item.get("reason") or "").strip()[:500],
        }
    return results


def _reduce_by_incoming(comparisons):
    by_incoming = {}
    priority = {"unresolved": 5, "conflict": 4, "supplement": 3, "unchanged": 2, "unrelated": 1}
    for (incoming_index, old_page_id), comparison in comparisons.items():
        current = by_incoming.get(incoming_index)
        if current is None or priority[comparison["relation"]] > priority[current["relation"]]:
            by_incoming[incoming_index] = {
                **comparison,
                "old_page_id": old_page_id,
            }
    return by_incoming


def _fill_unresolved_incoming(comparisons, compact, *, reason):
    """Fail closed when the bounded evidence window cannot compare a candidate."""

    covered_incoming = {incoming_index for incoming_index, _old_page_id in comparisons}
    for item in compact:
        incoming_index = item["incoming_index"]
        if incoming_index in covered_incoming:
            continue
        comparisons[(incoming_index, item["old_page_id"])] = {
            "same_subject": None,
            "relation": "unresolved",
            "reason": reason,
        }
        covered_incoming.add(incoming_index)
    return comparisons


def _invoke_conflict_comparison(invoke_llm, llm_model_id, prompt, budget, *, candidate_generation_id):
    """Retry once on empty/invalid comparison output, then fail closed as unresolved."""

    raw = ""
    last_error_type = "empty_output"
    for attempt in range(1, _CONFLICT_LLM_MAX_ATTEMPTS + 1):
        if budget.remaining_calls <= 0:
            break
        stage = "material_conflict_batch" if attempt == 1 else f"material_conflict_batch_retry_{attempt}"
        try:
            raw = invoke_llm(
                llm_model_id,
                prompt,
                budget=budget,
                stage=stage,
                output_reserve=_CONFLICT_OUTPUT_RESERVE,
            )
        except WikiBudgetExceeded:
            if attempt == 1:
                raise
            last_error_type = "WikiBudgetExceeded"
            raw = ""
            break
        except BuildOutputInvalid as exc:
            last_error_type = type(exc).__name__
            raw = ""
            if attempt < _CONFLICT_LLM_MAX_ATTEMPTS and budget.remaining_calls > 0:
                logger.warning(
                    "wiki_conflict_comparison_retry candidate_generation_id=%s stage=%s attempt=%s/%s error_type=%s",
                    candidate_generation_id,
                    stage,
                    attempt,
                    _CONFLICT_LLM_MAX_ATTEMPTS,
                    last_error_type,
                )
            continue
        if str(raw or "").strip():
            return raw
        last_error_type = "empty_output"
        raw = ""
        if attempt < _CONFLICT_LLM_MAX_ATTEMPTS and budget.remaining_calls > 0:
            logger.warning(
                "wiki_conflict_comparison_retry candidate_generation_id=%s stage=%s attempt=%s/%s error_type=%s",
                candidate_generation_id,
                stage,
                attempt,
                _CONFLICT_LLM_MAX_ATTEMPTS,
                last_error_type,
            )
    logger.warning(
        "wiki conflict comparison LLM 失败，降级为 unresolved candidate_generation_id=%s error_type=%s",
        candidate_generation_id,
        last_error_type,
    )
    return raw


def route_material_conflicts(
    candidate_generation_id,
    pages_data,
    *,
    llm_model_id,
    budget,
    invoke_llm,
    base_generation_id=None,
):
    """Return a bounded comparison map keyed by incoming page index."""

    if base_generation_id is None:
        candidate = WikiGeneration.objects.only("id", "base_generation_id").get(pk=candidate_generation_id)
        base_generation_id = candidate.base_generation_id
    if base_generation_id is None or not pages_data:
        return ConflictRoutingResult({}, 0, (), 0, 0, False, ())
    compact, overflow = _compact_candidates(base_generation_id, pages_data)
    deterministic = {
        (item["incoming_index"], item["old_page_id"]): {
            "same_subject": True,
            "relation": "unchanged",
            "reason": "exact_body_match",
        }
        for item in compact
        if item["deterministic_relation"] == "unchanged"
    }
    evidence, evidence_page_ids, old_tokens = _evidence_candidates(compact)
    if not evidence or not llm_model_id:
        unresolved_pairs = {
            (item["incoming_index"], item["old_page_id"]): {
                "same_subject": None,
                "relation": "unresolved",
                "reason": "conflict_comparison_unavailable",
            }
            for item in evidence
        }
        comparisons = _fill_unresolved_incoming(
            {**deterministic, **unresolved_pairs},
            compact,
            reason="conflict_evidence_window_exhausted",
        )
        unresolved = tuple(
            sorted(incoming_index for (incoming_index, _old_page_id), comparison in comparisons.items() if comparison["relation"] == "unresolved")
        )
        return ConflictRoutingResult(
            _reduce_by_incoming(comparisons),
            len(compact),
            evidence_page_ids,
            old_tokens,
            overflow,
            False,
            unresolved,
        )
    remaining_tokens = budget.remaining_tokens
    input_token_limit = _CONFLICT_INPUT_TOKEN_LIMIT
    if remaining_tokens is not None:
        input_token_limit = min(
            input_token_limit,
            max(remaining_tokens - _CONFLICT_OUTPUT_RESERVE, 0),
        )
    context_limit = getattr(budget, "max_context_tokens_per_call", None)
    if context_limit is not None:
        input_token_limit = min(
            input_token_limit,
            max(context_limit - _CONFLICT_OUTPUT_RESERVE, 0),
        )
    prompt, prompt_items, selected_page_ids = _bounded_conflict_prompt(
        evidence,
        pages_data,
        input_token_limit,
    )
    if not prompt or budget.remaining_calls <= 0:
        unresolved_pairs = {
            (item["incoming_index"], item["old_page_id"]): {
                "same_subject": None,
                "relation": "unresolved",
                "reason": "conflict_comparison_budget_unavailable",
            }
            for item in evidence
        }
        comparisons = _fill_unresolved_incoming(
            {**deterministic, **unresolved_pairs},
            compact,
            reason="conflict_evidence_window_exhausted",
        )
        unresolved = tuple(
            sorted(incoming_index for (incoming_index, _old_page_id), comparison in comparisons.items() if comparison["relation"] == "unresolved")
        )
        return ConflictRoutingResult(
            _reduce_by_incoming(comparisons),
            len(compact),
            (),
            0,
            overflow + len(evidence),
            False,
            unresolved,
        )
    allowed_pairs = {(item["incoming_index"], item["old_page_id"]) for item in prompt_items}
    raw = _invoke_conflict_comparison(
        invoke_llm,
        llm_model_id,
        prompt,
        budget,
        candidate_generation_id=candidate_generation_id,
    )
    comparisons = {**deterministic, **_parse_comparisons(raw, allowed_pairs)}
    resolved_pairs = set(comparisons)
    unresolved_pairs = allowed_pairs - resolved_pairs
    unresolved_incoming = {incoming_index for incoming_index, _old_page_id in unresolved_pairs}
    missing_reason = "conflict_comparison_llm_empty" if not str(raw or "").strip() else "conflict_comparison_incomplete"
    comparisons.update(
        {
            pair: {
                "same_subject": None,
                "relation": "unresolved",
                "reason": missing_reason,
            }
            for pair in unresolved_pairs
        }
    )
    comparisons = _fill_unresolved_incoming(
        comparisons,
        compact,
        reason="conflict_evidence_window_exhausted",
    )
    unresolved_incoming.update(
        incoming_index for (incoming_index, _old_page_id), comparison in comparisons.items() if comparison["relation"] == "unresolved"
    )
    by_incoming = _reduce_by_incoming(comparisons)
    return ConflictRoutingResult(
        by_incoming,
        len(compact),
        selected_page_ids,
        sum(estimate_tokens(item["old"]["body"]) for item in prompt_items),
        overflow + max(len(evidence) - len(prompt_items), 0),
        True,
        tuple(sorted(unresolved_incoming)),
    )


__all__ = ["ConflictRoutingResult", "route_material_conflicts"]
