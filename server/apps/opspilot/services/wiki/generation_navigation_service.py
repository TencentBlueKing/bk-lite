"""Generation-owned deterministic Index and Overview navigation artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from django.db import transaction

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import WikiDirectory, WikiGeneration, WikiGenerationIndexEntry, WikiGenerationOverview
from apps.opspilot.services.wiki.title_service import title_alias_terms_for_enrichment, title_identity_key
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded, estimate_tokens

_ROOT_SCOPE_KEY = "__root__"
_MAX_SUMMARY_CHARS = 800
_MAX_HEADINGS = 64
_MAX_KEYWORDS = 32
_MAX_ENTITIES = 32
_MAX_OVERVIEW_PAGES = 100
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_WORD_RE = re.compile(r"[\w\-]{2,}", re.UNICODE)
_PAGE_REF_RE = re.compile(r"\[(\d+)\]")


class GenerationNavigationError(Exception):
    def __init__(self, code, message, *, details=None):
        self.code = str(code)
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True)
class NavigationBuildResult:
    generation_id: int
    index_count: int
    overview_count: int
    fingerprint: str


def _stable_hash(value):
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _bounded_strings(value, *, limit, max_chars=255):
    if not isinstance(value, (list, tuple, set)):
        return []
    result = []
    for item in value:
        text = str(item or "").strip()
        if not text or text in result:
            continue
        result.append(text[:max_chars])
        if len(result) >= limit:
            break
    return result


def _extract_headings(body):
    result = []
    for line in (body or "").splitlines():
        match = _HEADING_RE.match(line)
        if not match:
            continue
        heading = match.group(1).strip()
        if heading and heading not in result:
            result.append(heading[:255])
        if len(result) >= _MAX_HEADINGS:
            break
    return result


def _first_meaningful_paragraph(body):
    parts = []
    for line in (body or "").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or text.startswith("```"):
            if parts:
                break
            continue
        parts.append(text)
        if sum(len(item) for item in parts) >= _MAX_SUMMARY_CHARS:
            break
    return " ".join(parts)[:_MAX_SUMMARY_CHARS]


def _normalize_summary(meta, body):
    summary = str((meta or {}).get("summary") or "").strip()
    if not summary or len(summary) > _MAX_SUMMARY_CHARS:
        return _first_meaningful_paragraph(body)
    return summary


def _keywords(title, tags, headings, meta):
    explicit = _bounded_strings((meta or {}).get("keywords"), limit=_MAX_KEYWORDS, max_chars=64)
    candidates = [*explicit, *tags]
    candidates.extend(_WORD_RE.findall(" ".join([title, *headings])))
    return _bounded_strings(candidates, limit=_MAX_KEYWORDS, max_chars=64)


def _index_payload(member):
    page = member.page
    version = member.page_version
    display = dict(member.page_display_snapshot or {})
    meta = dict(version.meta_snapshot or {})
    title = str(display.get("title") or page.title or "").strip()
    page_type = str(display.get("page_type") or page.page_type or "concept").strip() or "concept"
    tags = _bounded_strings(display.get("tags") or page.tags, limit=_MAX_KEYWORDS, max_chars=64)
    aliases = _bounded_strings(
        [
            *(display.get("aliases") or []),
            *(meta.get("aliases") or []),
            *title_alias_terms_for_enrichment(member.generation.knowledge_base, title),
        ],
        limit=_MAX_KEYWORDS,
    )
    headings = _extract_headings(version.body)
    summary = _normalize_summary(meta, version.body)
    keywords = _keywords(title, tags, headings, meta)
    entities = _bounded_strings(meta.get("entities"), limit=_MAX_ENTITIES)
    breadcrumb = list(member.directory_breadcrumb_snapshot or [])
    fingerprint_payload = {
        "page_id": page.pk,
        "page_version_id": version.pk,
        "directory_id": member.directory_id,
        "directory_key": member.directory_key_snapshot,
        "title": title,
        "aliases": aliases,
        "page_type": page_type,
        "tags": tags,
        "headings": headings,
        "keywords": keywords,
        "entities": entities,
        "summary": summary,
        "body_hash": hashlib.sha256((version.body or "").encode("utf-8")).hexdigest(),
    }
    search_text = "\n".join(part for part in [title, *aliases, page_type, *tags, *headings, *keywords, *entities, summary] if part).casefold()
    return {
        "generation": member.generation,
        "page": page,
        "page_version": version,
        "directory": member.directory,
        "title": title,
        "normalized_title": title_identity_key(title),
        "aliases": aliases,
        "page_type": page_type,
        "tags": tags,
        "directory_key": member.directory_key_snapshot,
        "directory_breadcrumb": breadcrumb,
        "headings": headings,
        "keywords": keywords,
        "entities": entities,
        "summary": summary,
        "search_text": search_text,
        "content_fingerprint": _stable_hash(fingerprint_payload),
    }


def _directory_descendants(directories):
    children = {}
    for directory in directories:
        children.setdefault(directory.parent_id, []).append(directory.pk)
    result = {}
    for directory in directories:
        collected = {directory.pk}
        pending = [directory.pk]
        while pending:
            for child_id in children.get(pending.pop(), []):
                if child_id in collected:
                    continue
                collected.add(child_id)
                pending.append(child_id)
        result[directory.pk] = collected
    return result


def _overview_text(generation, *, directory, entries):
    kb = generation.knowledge_base
    title = kb.name if directory is None else directory.name
    description = kb.introduction if directory is None else directory.description
    purpose = (kb.purpose_md or "").strip()
    lines = [f"# {title}"]
    if description:
        lines.append(description.strip())
    if purpose and directory is None:
        lines.extend(["", "## 用途", purpose[:2000]])
    lines.extend(["", "## 内容索引"])
    if not entries:
        lines.append("当前范围暂无知识页面。")
    else:
        for entry in entries[:_MAX_OVERVIEW_PAGES]:
            path = " / ".join(item.get("name", "") for item in entry.directory_breadcrumb if item.get("name"))
            location = f"（{path}）" if path else ""
            summary = f"：{entry.summary}" if entry.summary else ""
            lines.append(f"- [{entry.page_id}] {entry.title}{location}{summary}")
        if len(entries) > _MAX_OVERVIEW_PAGES:
            lines.append(f"- 另有 {len(entries) - _MAX_OVERVIEW_PAGES} 个页面，请通过 Index 检索。")
    return "\n".join(lines).strip()


def render_index_markdown(generation, *, page_paths=None):
    page_paths = dict(page_paths or {})
    entries = generation.index_entries.order_by("directory_key", "normalized_title", "page_id")
    lines = [f"# {generation.knowledge_base.name} Index", ""]
    current_directory = None
    for entry in entries:
        if entry.directory_key != current_directory:
            current_directory = entry.directory_key
            breadcrumb = " / ".join(item.get("name", "") for item in entry.directory_breadcrumb if item.get("name"))
            lines.extend([f"## {breadcrumb or current_directory}", ""])
        summary = f" — {entry.summary}" if entry.summary else ""
        path = page_paths.get(
            entry.page_id,
            f"pages/{entry.directory_key}/{entry.page_id}.md",
        )
        lines.append(f"- [{entry.title}]({path}){summary}")
    return "\n".join(lines).rstrip() + "\n"


def render_overview_markdown(generation, *, directory_id=None, prefer_semantic=True):
    scope_key = _ROOT_SCOPE_KEY if directory_id is None else str(directory_id)
    overview = generation.overviews.get(scope_key=scope_key)
    if prefer_semantic and overview.semantic_status == "ready" and overview.semantic_text:
        return overview.semantic_text.rstrip() + "\n"
    return overview.deterministic_text.rstrip() + "\n"


def _parse_semantic_overviews(raw, allowed_page_ids_by_scope):
    text = str(raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except (TypeError, ValueError):
        return {}
    result = {}
    for item in payload.get("overviews") or []:
        if not isinstance(item, dict):
            continue
        scope_key = str(item.get("scope_key") or "")
        semantic_text = str(item.get("text") or "").strip()
        if scope_key not in allowed_page_ids_by_scope or not semantic_text:
            continue
        try:
            referenced = {int(page_id) for page_id in (item.get("referenced_page_ids") or [])}
        except (TypeError, ValueError):
            continue
        if not referenced.issubset(allowed_page_ids_by_scope[scope_key]):
            continue
        result[scope_key] = {
            "text": semantic_text[:6000],
            "referenced_page_ids": referenced,
        }
    return result


def enhance_generation_overviews(
    generation_id,
    *,
    llm_model_id,
    budget,
    invoke_llm,
):
    """Optionally enrich deterministic overviews with one bounded LLM call."""

    generation = WikiGeneration.objects.get(pk=generation_id)
    overviews = list(generation.overviews.order_by("directory_id", "id"))
    if not overviews:
        return {"status": "empty", "updated": 0, "llm_called": False}
    if not llm_model_id or budget.remaining_calls <= 0:
        generation.overviews.update(semantic_status="skipped", semantic_text="")
        return {"status": "skipped", "updated": 0, "llm_called": False}

    remaining_soft_tokens = budget.remaining_soft_tokens
    if remaining_soft_tokens is not None and remaining_soft_tokens < 1000:
        generation.overviews.update(semantic_status="skipped", semantic_text="")
        return {"status": "soft_budget_reached", "updated": 0, "llm_called": False}

    available_tokens = 10000 if remaining_soft_tokens is None else remaining_soft_tokens
    output_reserve = min(2000, max(available_tokens // 4, 500))
    input_limit = min(max(available_tokens - output_reserve, 0), 8000)
    context_limit = getattr(budget, "max_context_tokens_per_call", None)
    if context_limit is not None:
        input_limit = min(
            input_limit,
            max(context_limit - output_reserve, 0),
        )
    rows = []
    used_tokens = 0
    for overview in overviews:
        deterministic_text = overview.deterministic_text[:1600]
        covered_page_ids = {int(page_id) for page_id in _PAGE_REF_RE.findall(deterministic_text)}
        row = {
            "scope_key": overview.scope_key,
            "deterministic_overview": deterministic_text,
            "allowed_page_ids": sorted(covered_page_ids),
            "coverage_complete": covered_page_ids == set(overview.referenced_page_ids or []),
        }
        row_tokens = estimate_tokens(json.dumps(row, ensure_ascii=False))
        if used_tokens + row_tokens > input_limit:
            continue
        rows.append(row)
        used_tokens += row_tokens
    if not rows:
        generation.overviews.update(semantic_status="skipped", semantic_text="")
        return {"status": "budget_unavailable", "updated": 0, "llm_called": False}

    prompt = (
        "基于确定性概览生成简洁、准确的语义概览。不得添加输入中没有的事实；"
        "每条结论必须由 allowed_page_ids 中的页面支持。只输出 JSON："
        '{"overviews":[{"scope_key":"__root__","text":"...",'
        '"referenced_page_ids":[1]}]}。不得输出未提供的 scope_key 或页面 ID。\n' + json.dumps(rows, ensure_ascii=False)
    )
    try:
        raw = invoke_llm(
            llm_model_id,
            prompt,
            budget=budget,
            stage="material_semantic_overview",
            output_reserve=output_reserve,
        )
    except WikiBudgetExceeded:
        generation.overviews.update(semantic_status="skipped", semantic_text="")
        return {"status": "budget_unavailable", "updated": 0, "llm_called": False}
    except Exception as exc:
        # 顶层导入 build_service.BuildOutputInvalid 会与 generation_service 形成 import cycle。
        from apps.opspilot.services.wiki.build_service import BuildOutputInvalid

        if not isinstance(exc, BuildOutputInvalid):
            raise
        generation.overviews.update(semantic_status="skipped", semantic_text="")
        logger.warning(
            "wiki semantic overview LLM 失败，降级为确定性概览 generation_id=%s error_type=%s",
            generation_id,
            type(exc).__name__,
        )
        return {"status": "llm_failed", "updated": 0, "llm_called": True}

    allowed_scopes = {row["scope_key"] for row in rows}
    allowed_page_ids_by_scope = {row["scope_key"]: set(row["allowed_page_ids"]) for row in rows}
    coverage_by_scope = {row["scope_key"]: bool(row["coverage_complete"]) for row in rows}
    parsed = _parse_semantic_overviews(raw, allowed_page_ids_by_scope)
    updated = 0
    with transaction.atomic():
        for overview in WikiGenerationOverview.objects.select_for_update().filter(generation=generation):
            semantic_result = parsed.get(overview.scope_key)
            if semantic_result is None:
                overview.semantic_text = ""
                overview.semantic_status = "degraded" if overview.scope_key in allowed_scopes else "skipped"
            else:
                overview.semantic_text = semantic_result["text"]
                overview.semantic_status = (
                    "ready" if coverage_by_scope.get(overview.scope_key, False) and bool(semantic_result["referenced_page_ids"]) else "degraded"
                )
                if overview.semantic_status == "ready":
                    updated += 1
            overview.save(
                update_fields=[
                    "semantic_text",
                    "semantic_status",
                    "updated_at",
                ]
            )
    return {
        "status": "ready" if updated == len(rows) else "degraded",
        "updated": updated,
        "requested": len(rows),
        "llm_called": True,
    }


@transaction.atomic
def rebuild_generation_navigation(generation_id):
    generation = WikiGeneration.objects.select_for_update().select_related("knowledge_base", "structure_revision").get(pk=generation_id)
    if generation.status not in {"preparing", "ready"}:
        raise GenerationNavigationError(
            "generation_navigation_status_conflict",
            "只有 preparing/ready generation 可以重建导航产物",
            details={"generation_id": generation.pk, "status": generation.status},
        )
    members = list(
        generation.page_members.select_related(
            "generation__knowledge_base",
            "page",
            "page_version",
            "directory",
        ).order_by("page_id")
    )
    index_rows = [WikiGenerationIndexEntry(**_index_payload(member)) for member in members]
    generation.index_entries.all().delete()
    if index_rows:
        WikiGenerationIndexEntry.objects.bulk_create(index_rows, batch_size=500)
    entries = list(generation.index_entries.select_related("page", "directory").order_by("directory_key", "normalized_title", "page_id"))

    directories = list(
        WikiDirectory.objects.filter(
            knowledge_base=generation.knowledge_base,
            status="active",
        ).order_by("sort_order", "id")
    )
    descendants = _directory_descendants(directories)
    overview_rows = []
    root_text = _overview_text(generation, directory=None, entries=entries)
    overview_rows.append(
        WikiGenerationOverview(
            generation=generation,
            directory=None,
            scope_key=_ROOT_SCOPE_KEY,
            deterministic_text=root_text,
            semantic_status="skipped",
            referenced_page_ids=[entry.page_id for entry in entries],
            content_fingerprint=_stable_hash({"scope": _ROOT_SCOPE_KEY, "text": root_text}),
        )
    )
    for directory in directories:
        scoped = [entry for entry in entries if entry.directory_id in descendants[directory.pk]]
        text = _overview_text(generation, directory=directory, entries=scoped)
        overview_rows.append(
            WikiGenerationOverview(
                generation=generation,
                directory=directory,
                scope_key=str(directory.pk),
                deterministic_text=text,
                semantic_status="skipped",
                referenced_page_ids=[entry.page_id for entry in scoped],
                content_fingerprint=_stable_hash({"scope": directory.pk, "text": text}),
            )
        )
    generation.overviews.all().delete()
    WikiGenerationOverview.objects.bulk_create(overview_rows, batch_size=500)
    fingerprint = _stable_hash(
        {
            "generation_id": generation.pk,
            "index": [entry.content_fingerprint for entry in entries],
            "overviews": [row.content_fingerprint for row in overview_rows],
        }
    )
    return NavigationBuildResult(
        generation_id=generation.pk,
        index_count=len(entries),
        overview_count=len(overview_rows),
        fingerprint=fingerprint,
    )


def navigation_validation_issues(generation):
    member_page_ids = set(generation.page_members.values_list("page_id", flat=True))
    index_page_ids = set(generation.index_entries.values_list("page_id", flat=True))
    issues = []
    if member_page_ids != index_page_ids:
        issues.append(
            {
                "code": "generation_index_membership_mismatch",
                "missing_page_ids": sorted(member_page_ids - index_page_ids),
                "extra_page_ids": sorted(index_page_ids - member_page_ids),
            }
        )
    expected_scopes = {_ROOT_SCOPE_KEY}
    expected_scopes.update(
        str(item)
        for item in WikiDirectory.objects.filter(
            knowledge_base=generation.knowledge_base,
            status="active",
        ).values_list("id", flat=True)
    )
    actual_scopes = set(generation.overviews.values_list("scope_key", flat=True))
    if expected_scopes != actual_scopes:
        issues.append(
            {
                "code": "generation_overview_scope_mismatch",
                "missing_scopes": sorted(expected_scopes - actual_scopes),
                "extra_scopes": sorted(actual_scopes - expected_scopes),
            }
        )
    return issues


__all__ = [
    "GenerationNavigationError",
    "NavigationBuildResult",
    "enhance_generation_overviews",
    "navigation_validation_issues",
    "rebuild_generation_navigation",
    "render_index_markdown",
    "render_overview_markdown",
]
