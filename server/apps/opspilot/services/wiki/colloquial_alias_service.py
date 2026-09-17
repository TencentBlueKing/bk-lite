"""Colloquial aliases for generation-time pages and post-import enrichment."""

from __future__ import annotations

import json

from django.db import transaction

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import WikiGeneration, WikiGenerationIndexEntry
from apps.opspilot.services.wiki.generation_navigation_service import _index_payload
from apps.opspilot.services.wiki.generation_service import put_generation_member
from apps.opspilot.services.wiki.wiki_budget_service import WikiBudgetExceeded

MAX_ALIASES = 32
MAX_ALIAS_CHARS = 64
ALIAS_BODY_EXCERPT_CHARS = 2000
ALIAS_ENRICH_BATCH_SIZE = 8
ALIAS_ENRICH_OUTPUT_RESERVE = 2000
_SYSTEM_TAG_PREFIXES = ("okf:",)

COLLOQUIAL_ALIAS_CONTRACT = (
    "aliases 只用于导航召回，必须能在本页标题、标签或正文中找到依据，禁止补造产品名或制度名。"
    "除正式名称外，必须列出资料中出现的员工口语、俗称、系统昵称与明显同义短词"
    "（例如正文写向日葵则 aliases 含向日葵；写提单/找谁批则列出这些说法）。"
    "另外必须给出 2–3 条员工会怎么描述这个问题的短句，以及正文里出现的报错原句。"
    "不要重复标题全文；每条尽量短。"
)


class GenerationAliasEnrichmentError(Exception):
    def __init__(self, code, message, *, details=None):
        self.code = str(code)
        self.details = dict(details or {})
        super().__init__(message)


def seed_aliases_from_tags(tags):
    seeded = []
    for tag in tags or []:
        text = str(tag or "").strip()
        if not text:
            continue
        lowered = text.casefold()
        if any(lowered.startswith(prefix) for prefix in _SYSTEM_TAG_PREFIXES):
            continue
        if text not in seeded:
            seeded.append(text)
    return seeded


def ground_aliases(candidates, *, title="", tags=None, body="", always_keep=None):
    """Keep aliases that appear in the page text, plus explicit keepers (e.g. source tags)."""

    kept = []
    blob = "\n".join([str(title or ""), "\n".join(str(item or "") for item in (tags or [])), str(body or "")]).casefold()
    preserve = []
    for item in always_keep or []:
        text = str(item or "").strip()
        if text and text not in preserve:
            preserve.append(text)
    for item in [*preserve, *(candidates or [])]:
        text = str(item or "").strip()
        if not text or text in kept:
            continue
        if len(text) > MAX_ALIAS_CHARS:
            text = text[:MAX_ALIAS_CHARS].strip()
            if not text or text in kept:
                continue
        if text in preserve or text.casefold() in blob:
            kept.append(text)
        if len(kept) >= MAX_ALIASES:
            break
    return kept


def parse_alias_payload(raw):
    """Parse `{aliases:[...]}` or `{pages:[{page_id, aliases:[...]}]}`."""

    text = str(raw or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    pages = payload.get("pages")
    if isinstance(pages, list):
        by_id = {}
        for item in pages:
            if not isinstance(item, dict):
                continue
            page_id = item.get("page_id")
            try:
                page_id = int(page_id)
            except (TypeError, ValueError):
                continue
            aliases = item.get("aliases")
            if isinstance(aliases, list):
                by_id[page_id] = [str(alias).strip() for alias in aliases if str(alias).strip()]
        return by_id
    aliases = payload.get("aliases")
    if isinstance(aliases, list):
        return {None: [str(alias).strip() for alias in aliases if str(alias).strip()]}
    return {}


def _member_title(member):
    return ((member.page_display_snapshot or {}).get("title") or member.page.title or "").strip()


def _member_tags(member):
    display = member.page_display_snapshot or {}
    tags = display.get("tags")
    if tags:
        return list(tags)
    return list(member.page.tags or [])


def _member_aliases(member):
    display = list((member.page_display_snapshot or {}).get("aliases") or [])
    meta = list((member.page_version.meta_snapshot or {}).get("aliases") or [])
    return list(dict.fromkeys([*display, *meta]))


def build_alias_enrich_prompt(rows):
    return (
        "你是企业知识库导航助手。根据各页标题、标签与正文摘录，只输出 JSON："
        '{"pages":[{"page_id":1,"aliases":["..."]}]}。\n'
        f"{COLLOQUIAL_ALIAS_CONTRACT}\n"
        "只为提供的 page_id 输出 aliases；不要解释。\n" + json.dumps({"pages": rows}, ensure_ascii=False)
    )


def _candidate_members(candidate_id, page_ids, *, allow_active=False):
    candidate = WikiGeneration.objects.filter(pk=candidate_id).first()
    if candidate is None:
        raise GenerationAliasEnrichmentError(
            "generation_not_found",
            "generation 不存在",
            details={"generation_id": candidate_id},
        )
    allowed = {"preparing", "active"} if allow_active else {"preparing"}
    if candidate.status not in allowed:
        raise GenerationAliasEnrichmentError(
            "generation_status_conflict",
            "只有 preparing generation 可以补全口语 aliases" if not allow_active else "只有 preparing/active generation 可以补全口语 aliases",
            details={"generation_id": candidate.pk, "status": candidate.status},
        )
    members = list(candidate.page_members.select_related("generation__knowledge_base", "page", "page_version", "directory").order_by("page_id"))
    requested_ids = {int(page_id) for page_id in page_ids if page_id}
    return candidate, members, requested_ids


def _write_member_aliases(candidate, member, aliases):
    version = member.page_version
    meta = dict(version.meta_snapshot or {})
    if list(meta.get("aliases") or []) == aliases and list((member.page_display_snapshot or {}).get("aliases") or []) == aliases:
        return False
    meta["aliases"] = aliases
    version.meta_snapshot = meta
    version.save(update_fields=["meta_snapshot", "updated_at"])
    display = dict(member.page_display_snapshot or {})
    display["aliases"] = aliases
    put_generation_member(
        candidate.pk,
        page_id=member.page_id,
        page_version_id=version.pk,
        directory_id=member.directory_id,
        assignment_mode=member.assignment_mode,
        page_status=member.page_status,
        display_snapshot=display,
    )
    return True


def _write_live_member_aliases(member, aliases):
    version = member.page_version
    meta = dict(version.meta_snapshot or {})
    display = dict(member.page_display_snapshot or {})
    if list(meta.get("aliases") or []) == aliases and list(display.get("aliases") or []) == aliases:
        return False
    meta["aliases"] = aliases
    version.meta_snapshot = meta
    version.save(update_fields=["meta_snapshot", "updated_at"])
    display["aliases"] = aliases
    member.page_display_snapshot = display
    member.save(update_fields=["page_display_snapshot", "updated_at"])
    payload = _index_payload(member)
    entry = WikiGenerationIndexEntry.objects.filter(generation_id=member.generation_id, page_id=member.page_id).first()
    if entry is not None:
        entry.aliases = payload["aliases"]
        entry.keywords = payload["keywords"]
        entry.search_text = payload["search_text"]
        entry.content_fingerprint = payload["content_fingerprint"]
        entry.save(update_fields=["aliases", "keywords", "search_text", "content_fingerprint", "updated_at"])
    return True


def _invoke_alias_llm(invoke_llm, llm_model_id, prompt, *, budget):
    kwargs = {}
    if budget is not None:
        kwargs = {
            "budget": budget,
            "stage": "colloquial_alias_enrich",
            "output_reserve": ALIAS_ENRICH_OUTPUT_RESERVE,
            "force_json": True,
        }
    try:
        return invoke_llm(llm_model_id, prompt, **kwargs)
    except TypeError:
        return invoke_llm(llm_model_id, prompt)


def enrich_generation_colloquial_aliases(
    candidate_id,
    page_ids,
    *,
    llm_model_id=None,
    invoke_llm=None,
    budget=None,
    llm_when="always",
    inplace=False,
):
    """Seed grounded aliases and optionally LLM-expand them. Does not rewrite body."""

    candidate, members, requested_ids = _candidate_members(candidate_id, page_ids, allow_active=inplace)
    if not requested_ids:
        return {"status": "empty", "updated": 0, "llm_pages": 0, "skipped": 0, "llm_called": False}

    prepared = []
    skipped = 0
    for member in members:
        if member.page_id not in requested_ids:
            continue
        if not inplace and member.page_version.created_in_generation_id != candidate.pk:
            skipped += 1
            continue
        title = _member_title(member)
        tags = _member_tags(member)
        body = member.page_version.body or ""
        seeded = ground_aliases(
            [*seed_aliases_from_tags(tags), *_member_aliases(member)],
            title=title,
            tags=tags,
            body=body,
            always_keep=seed_aliases_from_tags(tags),
        )
        prepared.append(
            {
                "member": member,
                "title": title,
                "tags": tags,
                "body": body,
                "aliases": seeded,
                "need_llm": bool(llm_when == "always" or (llm_when == "if_empty" and not seeded)),
            }
        )

    llm_pages = [item for item in prepared if item["need_llm"]]
    llm_called = False
    if llm_model_id and invoke_llm and llm_pages and (budget is None or budget.remaining_calls > 0):
        for offset in range(0, len(llm_pages), ALIAS_ENRICH_BATCH_SIZE):
            batch = llm_pages[offset : offset + ALIAS_ENRICH_BATCH_SIZE]
            rows = [
                {
                    "page_id": item["member"].page_id,
                    "title": item["title"],
                    "tags": item["tags"],
                    "excerpt": (item["body"] or "")[:ALIAS_BODY_EXCERPT_CHARS],
                }
                for item in batch
            ]
            prompt = build_alias_enrich_prompt(rows)
            try:
                raw = _invoke_alias_llm(invoke_llm, llm_model_id, prompt, budget=budget)
            except WikiBudgetExceeded:
                logger.warning(
                    "wiki colloquial alias enrich budget reached generation_id=%s failed_stage=%s error_type=%s",
                    candidate.pk,
                    "colloquial_alias_enrich",
                    "WikiBudgetExceeded",
                )
                break
            except Exception as exc:
                logger.warning(
                    "wiki colloquial alias enrich batch failed generation_id=%s failed_stage=%s error_type=%s",
                    candidate.pk,
                    "colloquial_alias_enrich",
                    type(exc).__name__,
                )
                continue
            llm_called = True
            parsed = parse_alias_payload(raw)
            for item in batch:
                extra = parsed.get(item["member"].page_id) or parsed.get(None) or []
                item["aliases"] = ground_aliases(
                    [*item["aliases"], *extra],
                    title=item["title"],
                    tags=item["tags"],
                    body=item["body"],
                    always_keep=seed_aliases_from_tags(item["tags"]),
                )

    updated = 0
    with transaction.atomic():
        for item in prepared:
            wrote = (
                _write_live_member_aliases(item["member"], item["aliases"])
                if inplace
                else _write_member_aliases(candidate, item["member"], item["aliases"])
            )
            if wrote:
                updated += 1

    used_tokens = getattr(budget, "used_tokens", 0) if budget is not None else 0
    logger.info(
        "wiki colloquial alias enrich completed generation_id=%s updated=%s llm_pages=%s skipped=%s llm_called=%s used_tokens=%s",
        candidate.pk,
        updated,
        len(llm_pages),
        skipped,
        llm_called,
        used_tokens,
    )
    return {
        "status": "ok",
        "updated": updated,
        "llm_pages": len(llm_pages),
        "skipped": skipped,
        "llm_called": llm_called,
        "used_tokens": used_tokens,
    }


def enrich_generation_colloquial_aliases_safely(candidate_id, page_ids, **kwargs):
    try:
        return enrich_generation_colloquial_aliases(candidate_id, page_ids, **kwargs)
    except GenerationAliasEnrichmentError:
        logger.warning(
            "wiki colloquial alias enrich skipped generation_id=%s failed_stage=%s error_type=%s",
            candidate_id,
            "colloquial_alias_enrich",
            "GenerationAliasEnrichmentError",
        )
        return {
            "status": "skipped",
            "updated": 0,
            "llm_pages": 0,
            "skipped": 0,
            "llm_called": False,
        }


__all__ = [
    "ALIAS_BODY_EXCERPT_CHARS",
    "ALIAS_ENRICH_BATCH_SIZE",
    "COLLOQUIAL_ALIAS_CONTRACT",
    "GenerationAliasEnrichmentError",
    "build_alias_enrich_prompt",
    "enrich_generation_colloquial_aliases",
    "enrich_generation_colloquial_aliases_safely",
    "ground_aliases",
    "parse_alias_payload",
    "seed_aliases_from_tags",
]
