from collections import Counter

from django.db import transaction
from django.utils import timezone

from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, Material, PageEvidence, PageRelation
from apps.opspilot.services.wiki.decision_service import (
    build_page_identity_snapshot,
    build_participants_from_page_evidence,
    compute_schema_fingerprint,
    page_identity_context_stale_reason,
)


def _recount_source_build(check):
    # Lazy import avoids check_service -> cascade_service -> sweep_service cycle.
    from apps.opspilot.services.wiki.check_service import _recount_pending_review

    _recount_pending_review(check)


def _set_automatic_resolution(check, related, *, reason):
    related["resolution"] = {
        "action": "automatic_maintenance",
        "reason": reason,
        "operator": "system",
        "processed_at": timezone.now().isoformat(),
    }
    check.related = related
    check.status = "auto_resolved"
    check.suggested_actions = []
    check.updated_by = "system"


@transaction.atomic
def drop_page_references(knowledge_base, page_ids):
    """Remove deleted page ids from JSON references kept by checks/build records."""
    ids = {int(page_id) for page_id in (page_ids or []) if page_id}
    if not ids:
        return {"checks": 0, "build_records": 0}

    checks = 0
    check_qs = CheckItem.objects.select_for_update().filter(knowledge_base=knowledge_base).order_by("id")
    for check in check_qs:
        related = dict(check.related) if isinstance(check.related, dict) else {}
        pages = related.get("pages", []) or []
        kept_pages = [page_id for page_id in pages if page_id not in ids]
        if kept_pages == pages:
            continue
        related["pages"] = kept_pages
        update_fields = ["related", "updated_at"]
        if check.status == "open" and not kept_pages:
            _set_automatic_resolution(check, related, reason="premise_invalid")
            update_fields.extend(["status", "suggested_actions", "updated_by"])
        check.related = related
        check.save(update_fields=update_fields)
        if "status" in update_fields:
            _recount_source_build(check)
        checks += 1

    build_records = 0
    record_qs = BuildRecord.objects.select_for_update().filter(knowledge_base=knowledge_base).order_by("id")
    for record in record_qs:
        affected_pages = record.affected_pages or []
        kept_pages = [page_id for page_id in affected_pages if page_id not in ids]
        if kept_pages == affected_pages:
            continue
        record.affected_pages = kept_pages
        record.save(update_fields=["affected_pages", "updated_at"])
        build_records += 1

    return {"checks": checks, "build_records": build_records}


@transaction.atomic
def sweep_open_checks(knowledge_base):
    """Auto-resolve open checks whose premise is no longer true."""
    resolved = 0
    checks = CheckItem.objects.select_for_update().filter(knowledge_base=knowledge_base, status="open").order_by("id")
    for check in checks:
        if _should_auto_resolve(check):
            # The premise evaluation can call services that finish the same check.
            # Never overwrite a decision that stopped being open in the meantime.
            check.refresh_from_db(fields=["status"])
            if check.status != "open":
                continue
            related = dict(check.related) if isinstance(check.related, dict) else {}
            _set_automatic_resolution(check, related, reason="premise_invalid")
            check.save(update_fields=["related", "status", "suggested_actions", "updated_by", "updated_at"])
            _recount_source_build(check)
            resolved += 1
    return resolved


def _participant_counter(participants):
    return Counter(
        (
            item.get("material_id"),
            (item.get("content_hash") or "").strip(),
        )
        for item in participants or []
        if isinstance(item, dict)
    )


def _schema_changed(check):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    frozen = (context.get("schema_fingerprint") or "").strip()
    return bool(frozen and compute_schema_fingerprint(check.knowledge_base) != frozen)


def _knowledge_conflict_context_invalid(check, page):
    context = check.decision_context if isinstance(check.decision_context, dict) else {}
    if _schema_changed(check):
        return True
    frozen_participants = context.get("participants")
    incoming = context.get("incoming") if isinstance(context.get("incoming"), dict) else {}
    if not isinstance(frozen_participants, list) or not incoming.get("material_id"):
        return False

    material_ids = {item.get("material_id") for item in frozen_participants if isinstance(item, dict) and item.get("material_id")}
    materials = {
        material.id: material
        for material in Material.objects.filter(
            knowledge_base_id=check.knowledge_base_id,
            id__in=material_ids,
        ).select_related("current_version")
    }
    if set(materials) != material_ids:
        return True
    incoming_material = materials.get(incoming.get("material_id"))
    if incoming_material is None:
        return True
    live_version = incoming_material.current_version
    live_incoming = {
        "material_id": incoming_material.id,
        "material_version_id": getattr(live_version, "id", None),
        "content_hash": (getattr(live_version, "content_hash", "") or incoming_material.content_hash or ""),
    }
    live_participants = build_participants_from_page_evidence(
        page,
        incoming_snapshot=live_incoming,
    )
    return _participant_counter(live_participants) != _participant_counter(
        frozen_participants,
    )


def _page_identity_context_invalid(check):
    related = check.related if isinstance(check.related, dict) else {}
    raw_page_ids = related.get("pages", [])
    if not isinstance(raw_page_ids, list):
        return True
    page_ids = []
    for page_id in raw_page_ids:
        if isinstance(page_id, bool):
            return True
        try:
            page_ids.append(int(page_id))
        except (TypeError, ValueError):
            return True

    pages = list(
        KnowledgePage.objects.filter(
            knowledge_base_id=check.knowledge_base_id,
            id__in=page_ids,
            status="active",
        )
        .select_related("current_version")
        .order_by("id")
    )
    live_identities = [build_page_identity_snapshot(check.knowledge_base, page) for page in pages]
    return bool(
        page_identity_context_stale_reason(
            knowledge_base_id=check.knowledge_base_id,
            decision_key=check.decision_key,
            context=check.decision_context,
            schema_fingerprint=compute_schema_fingerprint(check.knowledge_base),
            related_page_ids=raw_page_ids,
            live_identities=live_identities,
        )
    )


def _should_auto_resolve(check):
    related = check.related if isinstance(check.related, dict) else {}
    page_ids = related.get("pages", []) or []
    active_pages = KnowledgePage.objects.filter(knowledge_base=check.knowledge_base, id__in=page_ids, status="active")
    active_count = active_pages.count()

    if check.check_type in ("duplicate", "conflict"):
        return _page_identity_context_invalid(check)
    if check.check_type == "ambiguous_link":
        return active_count < 2
    if check.check_type == "broken_relation":
        target = related.get("target")
        if not target:
            return not PageRelation.objects.filter(
                from_page__knowledge_base=check.knowledge_base,
                from_page_id__in=page_ids,
                relation_type="reference",
            ).exists()
        return KnowledgePage.objects.filter(knowledge_base=check.knowledge_base, title=target, status="active").exists()
    if check.check_type in ("no_source", "all_sources_invalid", "orphan", "source_invalid"):
        return PageEvidence.objects.filter(page__knowledge_base=check.knowledge_base, page_id__in=page_ids, material__status="done").exists()
    if check.check_type in ("material_update", "cannot_merge"):
        candidate = check.candidate_version
        if candidate is None:
            return True
        page = KnowledgePage.objects.filter(
            knowledge_base=check.knowledge_base,
            id=candidate.page_id,
            status="active",
        ).first()
        return page is None or _knowledge_conflict_context_invalid(check, page)
    return False
