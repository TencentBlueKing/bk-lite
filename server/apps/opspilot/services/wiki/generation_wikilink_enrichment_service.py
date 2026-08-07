"""WikiLink enrichment for immutable candidate-generation page versions."""

from django.db import transaction
from django.db.models import Max

from apps.core.logger import opspilot_logger as logger
from apps.opspilot.models import KnowledgePage, PageVersion, WikiGeneration, WikiGenerationPage, WikiKnowledgeBase
from apps.opspilot.services.wiki.generation_service import put_generation_member
from apps.opspilot.services.wiki.wikilink_enrichment_service import (
    _body_contains_candidate_term,
    _build_enrichment_prompt,
    _direct_wikilink_suggestions,
    apply_wikilink_suggestions,
    parse_wikilink_suggestions,
)

_TRACE_ACTIONS = frozenset({"create", "restore", "update", "unchanged"})


class GenerationWikilinkEnrichmentError(Exception):
    def __init__(self, code, message, *, details=None):
        self.code = str(code)
        self.details = dict(details or {})
        super().__init__(message)


def _member_title(member):
    return ((member.page_display_snapshot or {}).get("title") or member.page.title or "").strip()


def _candidate_members(candidate_id, page_ids):
    candidate = WikiGeneration.objects.filter(pk=candidate_id).first()
    if candidate is None:
        raise GenerationWikilinkEnrichmentError(
            "generation_not_found",
            "generation 不存在",
            details={"generation_id": candidate_id},
        )
    if candidate.status != "preparing":
        raise GenerationWikilinkEnrichmentError(
            "generation_status_conflict",
            "只有 preparing generation 可以补充 WikiLink",
            details={"generation_id": candidate.pk, "status": candidate.status},
        )

    members = list(candidate.page_members.select_related("page", "page_version").order_by("page_id"))
    requested_ids = {int(page_id) for page_id in page_ids if page_id}
    member_ids = {member.page_id for member in members}
    missing_ids = sorted(requested_ids - member_ids)
    if missing_ids:
        raise GenerationWikilinkEnrichmentError(
            "generation_member_missing",
            "待补链页面不属于 candidate generation",
            details={"generation_id": candidate.pk, "page_ids": missing_ids},
        )
    return candidate, members, requested_ids


def _allowed_titles(members, source_page_id, canonicalize, alias_terms_resolver):
    actual_titles = {_member_title(member) for member in members if _member_title(member)}
    allowed = {}
    for member in members:
        if member.page_id == source_page_id:
            continue
        title = _member_title(member)
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


@transaction.atomic
def _replace_candidate_member_version(
    candidate_id,
    *,
    page_id,
    source_page_version_id,
    body,
    build_record,
    operator,
    method,
    inserted_count,
):
    identity = WikiGeneration.objects.filter(pk=candidate_id).values("knowledge_base_id").first()
    if identity is None:
        raise GenerationWikilinkEnrichmentError(
            "generation_not_found",
            "generation 不存在",
            details={"generation_id": candidate_id},
        )
    knowledge_base = WikiKnowledgeBase.objects.select_for_update().get(pk=identity["knowledge_base_id"])
    candidate = WikiGeneration.objects.select_for_update().get(
        pk=candidate_id,
        knowledge_base=knowledge_base,
    )
    if candidate.status != "preparing":
        raise GenerationWikilinkEnrichmentError(
            "generation_status_conflict",
            "只有 preparing generation 可以补充 WikiLink",
            details={"generation_id": candidate.pk, "status": candidate.status},
        )
    page = KnowledgePage.objects.select_for_update().get(
        pk=page_id,
        knowledge_base=knowledge_base,
    )
    member = WikiGenerationPage.objects.select_for_update().select_related("page_version", "directory").get(generation=candidate, page=page)
    if member.page_version_id != source_page_version_id:
        raise GenerationWikilinkEnrichmentError(
            "generation_member_version_changed",
            "candidate 页面版本已变化",
            details={
                "generation_id": candidate.pk,
                "page_id": page.pk,
                "expected_page_version_id": source_page_version_id,
                "actual_page_version_id": member.page_version_id,
            },
        )
    source_version = member.page_version
    if source_version.created_in_generation_id != candidate.pk:
        raise GenerationWikilinkEnrichmentError(
            "generation_page_version_not_owned",
            "只能补充 candidate generation 自己创建的页面版本",
            details={
                "generation_id": candidate.pk,
                "page_id": page.pk,
                "page_version_id": source_version.pk,
            },
        )

    version = PageVersion.objects.create(
        page=page,
        no=(page.page_versions.aggregate(value=Max("no"))["value"] or 0) + 1,
        body=body,
        meta_snapshot={
            **(source_version.meta_snapshot or {}),
            "candidate_generation_id": candidate.pk,
            "wikilink_enrichment": {
                "source_page_version_id": source_version.pk,
                "method": method,
                "inserted_count": inserted_count,
            },
        },
        change_type="wikilink_enrich",
        build_record=build_record,
        created_in_generation=candidate,
        is_current=False,
        created_by=operator or "",
    )
    put_generation_member(
        candidate.pk,
        page_id=page.pk,
        page_version_id=version.pk,
        directory_id=member.directory_id,
        assignment_mode=member.assignment_mode,
        page_status=member.page_status,
        display_snapshot=member.page_display_snapshot,
    )
    return version.pk


def _trace_result(
    member,
    *,
    status,
    method="none",
    inserted_count=0,
    result_page_version_id=None,
    reason=None,
    error_type=None,
):
    result = {
        "page_id": member.page_id,
        "status": status,
        "method": method,
        "inserted_count": int(inserted_count),
        "source_page_version_id": member.page_version_id,
        "result_page_version_id": result_page_version_id or member.page_version_id,
    }
    if reason:
        result["reason"] = str(reason)[:64]
    if error_type:
        result["error_type"] = str(error_type)[:64]
    return result


def enrich_generation_pages_wikilinks(
    candidate_id,
    page_ids,
    llm_model_id,
    invoke_llm,
    *,
    build_record,
    operator="",
    canonicalize=None,
    alias_terms_resolver=None,
):
    """Enrich candidate-owned versions without touching the active snapshot."""

    candidate, members, requested_ids = _candidate_members(candidate_id, page_ids)
    if not requested_ids:
        return []

    results = []
    for member in members:
        if member.page_id not in requested_ids:
            continue
        if member.page_version.created_in_generation_id != candidate.pk:
            results.append(
                _trace_result(
                    member,
                    status="skipped",
                    reason="reused_page_version",
                )
            )
            continue

        allowed_titles = _allowed_titles(
            members,
            member.page_id,
            canonicalize,
            alias_terms_resolver,
        )
        if not allowed_titles:
            results.append(_trace_result(member, status="skipped", reason="no_target_page"))
            continue

        body = member.page_version.body or ""
        if not _body_contains_candidate_term(body, allowed_titles):
            results.append(_trace_result(member, status="skipped", reason="no_candidate_term"))
            continue

        method = "direct"
        suggestions = _direct_wikilink_suggestions(body, allowed_titles)
        enriched_body, inserted = apply_wikilink_suggestions(
            body,
            suggestions,
            allowed_titles,
        )
        if inserted <= 0 or enriched_body == body:
            if not llm_model_id:
                results.append(
                    _trace_result(
                        member,
                        status="unchanged",
                        method=method,
                        reason="llm_model_missing",
                    )
                )
                continue
            method = "llm"
            prompt = _build_enrichment_prompt(
                _member_title(member),
                body,
                sorted(set(allowed_titles.values())),
            )
            try:
                raw = invoke_llm(llm_model_id, prompt)
            except Exception as exc:  # noqa: BLE001 - 单页失败不得污染候选正文
                logger.exception(
                    "wiki generation wikilink enrichment failed generation=%s page=%s",
                    candidate.pk,
                    member.page_id,
                )
                results.append(
                    _trace_result(
                        member,
                        status="llm_failed",
                        method=method,
                        error_type=type(exc).__name__,
                    )
                )
                continue
            if not isinstance(raw, str) or not raw.strip():
                results.append(
                    _trace_result(
                        member,
                        status="llm_failed",
                        method=method,
                        error_type="empty_response",
                    )
                )
                continue
            enriched_body, inserted = apply_wikilink_suggestions(
                body,
                parse_wikilink_suggestions(raw),
                allowed_titles,
            )

        if inserted <= 0 or enriched_body == body:
            results.append(_trace_result(member, status="unchanged", method=method))
            continue

        result_version_id = _replace_candidate_member_version(
            candidate.pk,
            page_id=member.page_id,
            source_page_version_id=member.page_version_id,
            body=enriched_body,
            build_record=build_record,
            operator=operator,
            method=method,
            inserted_count=inserted,
        )
        results.append(
            _trace_result(
                member,
                status="changed",
                method=method,
                inserted_count=inserted,
                result_page_version_id=result_version_id,
            )
        )
    return results


def apply_generation_wikilink_trace(page_actions, enrichment_results):
    """Attach bounded enrichment facts and the final published version id."""

    by_page_id = {item["page_id"]: item for item in enrichment_results or []}
    for action in page_actions or []:
        result = by_page_id.get(action.get("page_id"))
        if result is None or action.get("action") not in _TRACE_ACTIONS:
            continue
        action["page_version_id"] = result["result_page_version_id"]
        action["wikilink_enrichment"] = {key: value for key, value in result.items() if key not in {"page_id", "result_page_version_id"}}
    return page_actions


__all__ = [
    "GenerationWikilinkEnrichmentError",
    "apply_generation_wikilink_trace",
    "enrich_generation_pages_wikilinks",
]
