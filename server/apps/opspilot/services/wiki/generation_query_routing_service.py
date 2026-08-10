"""One bounded Overview call for low-confidence generation-index queries."""

from __future__ import annotations

import json
from dataclasses import dataclass

from apps.opspilot.models import WikiGenerationOverview
from apps.opspilot.services.wiki.wiki_budget_service import estimate_tokens


@dataclass(frozen=True)
class OverviewRouteResult:
    scopes: tuple
    knowledge_tokens: int
    llm_called: bool
    status: str


def _parse_scopes(raw, allowed):
    text = str(raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return ()
    try:
        payload = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return ()
    result = []
    for item in payload.get("scopes") or []:
        if not isinstance(item, dict):
            continue
        try:
            pair = (int(item.get("kb_id")), int(item.get("directory_id")))
        except (TypeError, ValueError):
            continue
        if pair in allowed and pair not in result:
            result.append(pair)
        if len(result) >= 3:
            break
    return tuple(result)


def route_overview_scopes(
    scopes,
    query,
    *,
    llm_model_id,
    call_budget,
    knowledge_token_limit,
    invoke_llm,
):
    """Select at most three directory scopes with one shared Overview call."""

    if not llm_model_id or call_budget.remaining_calls <= 1:
        return OverviewRouteResult((), 0, False, "skipped")
    catalog_limit = max(0, min(int(knowledge_token_limit) // 3, 2000))
    if catalog_limit <= 0:
        return OverviewRouteResult((), 0, False, "budget_unavailable")

    allowed = set()
    catalog = []
    used_tokens = 0
    for knowledge_base, read_scope in scopes:
        if read_scope.generation_id is None:
            continue
        overviews = (
            WikiGenerationOverview.objects.filter(
                generation_id=read_scope.generation_id,
                directory_id__isnull=False,
            )
            .select_related("directory")
            .order_by("directory__sort_order", "directory_id")
        )
        for overview in overviews:
            text = overview.semantic_text if overview.semantic_status == "ready" and overview.semantic_text else overview.deterministic_text
            row = {
                "kb_id": knowledge_base.pk,
                "directory_id": overview.directory_id,
                "directory": overview.directory.name,
                "overview": str(text or "")[:800],
            }
            row_tokens = estimate_tokens(json.dumps(row, ensure_ascii=False))
            if used_tokens + row_tokens > catalog_limit:
                continue
            catalog.append(row)
            allowed.add((knowledge_base.pk, overview.directory_id))
            used_tokens += row_tokens
    if not catalog:
        return OverviewRouteResult((), 0, False, "catalog_empty")

    prompt = (
        "根据用户问题，从目录概览中选择最可能包含答案的目录，最多 3 个。"
        '只输出 JSON：{"scopes":[{"kb_id":1,"directory_id":2}]}。'
        "没有可靠目录时返回空 scopes，不得编造 ID。\n"
        f"用户问题：{query}\n目录概览：" + json.dumps(catalog, ensure_ascii=False)
    )
    raw = invoke_llm(
        llm_model_id,
        prompt,
        budget=call_budget,
        stage="query_overview_route",
        output_reserve=500,
    )
    selected = _parse_scopes(raw, allowed)
    return OverviewRouteResult(
        selected,
        used_tokens,
        True,
        "routed" if selected else "no_scope",
    )


__all__ = ["OverviewRouteResult", "route_overview_scopes"]
