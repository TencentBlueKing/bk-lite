from apps.opspilot.models import BuildRecord, CheckItem, KnowledgePage, PageEvidence, PageRelation


def drop_page_references(knowledge_base, page_ids):
    """Remove deleted page ids from JSON references kept by checks/build records."""
    ids = {int(page_id) for page_id in (page_ids or []) if page_id}
    if not ids:
        return {"checks": 0, "build_records": 0}

    checks = 0
    for check in CheckItem.objects.filter(knowledge_base=knowledge_base):
        related = dict(check.related) if isinstance(check.related, dict) else {}
        pages = related.get("pages", []) or []
        kept_pages = [page_id for page_id in pages if page_id not in ids]
        if kept_pages == pages:
            continue
        related["pages"] = kept_pages
        update_fields = ["related", "updated_at"]
        if check.status == "open" and not kept_pages:
            check.status = "auto_resolved"
            update_fields.append("status")
        check.related = related
        check.save(update_fields=update_fields)
        checks += 1

    build_records = 0
    for record in BuildRecord.objects.filter(knowledge_base=knowledge_base):
        affected_pages = record.affected_pages or []
        kept_pages = [page_id for page_id in affected_pages if page_id not in ids]
        if kept_pages == affected_pages:
            continue
        record.affected_pages = kept_pages
        record.save(update_fields=["affected_pages", "updated_at"])
        build_records += 1

    return {"checks": checks, "build_records": build_records}


def sweep_open_checks(knowledge_base):
    """Auto-resolve open checks whose premise is no longer true."""
    resolved = 0
    checks = CheckItem.objects.filter(knowledge_base=knowledge_base, status="open")
    for check in checks:
        if _should_auto_resolve(check):
            check.status = "auto_resolved"
            check.save(update_fields=["status", "updated_at"])
            resolved += 1
    return resolved


def _should_auto_resolve(check):
    related = check.related if isinstance(check.related, dict) else {}
    page_ids = related.get("pages", []) or []
    active_pages = KnowledgePage.objects.filter(id__in=page_ids, status="active")
    active_count = active_pages.count()

    if check.check_type in ("duplicate", "conflict", "ambiguous_link"):
        return active_count < 2
    if check.check_type == "broken_relation":
        target = related.get("target")
        if not target:
            return not PageRelation.objects.filter(from_page_id__in=page_ids, relation_type="reference").exists()
        return KnowledgePage.objects.filter(knowledge_base=check.knowledge_base, title=target, status="active").exists()
    if check.check_type in ("no_source", "all_sources_invalid", "orphan", "source_invalid"):
        return PageEvidence.objects.filter(page_id__in=page_ids, material__status="done").exists()
    if check.check_type == "material_update":
        candidate = check.candidate_version
        return candidate is None or not KnowledgePage.objects.filter(id=candidate.page_id, status="active").exists()
    return False
