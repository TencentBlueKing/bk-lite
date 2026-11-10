from django.db.models import Q

from apps.cmdb.models.ci_context import CmdbCiContext, CmdbCiContextPending


def _distinct_texts(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def schedule_ci_context_pending(*, root_uuids=None, model_asst_ids=None, ci_uuids=None) -> None:
    """Trim blanks, drop empties, and insert one pending row per distinct value."""
    rows = [CmdbCiContextPending(root_uuid=root_uuid) for root_uuid in _distinct_texts(root_uuids)]
    rows.extend(CmdbCiContextPending(model_asst_id=model_asst_id) for model_asst_id in _distinct_texts(model_asst_ids))
    rows.extend(CmdbCiContextPending(ci_uuid=ci_uuid) for ci_uuid in _distinct_texts(ci_uuids))
    if not rows:
        return
    CmdbCiContextPending.objects.bulk_create(rows, ignore_conflicts=True)


def _public_row(row: CmdbCiContext) -> dict:
    organization = row.organization if isinstance(row.organization, list) else []
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        "ci_uuid": row.ci_uuid,
        "context": row.context,
        "root_uuid": row.root_uuid,
        "root_model": row.root_model,
        "ci_model": row.ci_model,
        "ip_addr": row.ip_addr or "",
        "organization": list(organization),
        "system_uuid": row.system_uuid,
        "layer": row.layer,
        "via_uuid": row.via_uuid,
        "model_asst_id": row.model_asst_id or "",
        "payload": dict(payload),
    }


def lookup_ci_context(organization_ids, *, inst_uuids=None, ip_addrs=None, model_id=None, contexts=("application",)) -> dict:
    """Point lookup against cmdb_ci_context. No graph IO.

    Results are keyed only by ci_uuid. ip_addrs filters rows; it is not a dict key.
    """
    if not organization_ids:
        return {}

    inst_keys = _distinct_texts(inst_uuids)
    ip_keys = _distinct_texts(ip_addrs)
    model = "" if model_id is None else str(model_id).strip()
    clauses = []
    if inst_keys:
        clauses.append(Q(ci_uuid__in=inst_keys))
    if ip_keys and model:
        clauses.append(Q(ip_addr__in=ip_keys, ci_model=model))
    if not clauses:
        return {}

    match = clauses[0]
    for clause in clauses[1:]:
        match |= clause

    org_match = Q()
    for org_id in organization_ids:
        org_match |= Q(organization__contains=[org_id])

    rows = CmdbCiContext.objects.filter(org_match, context__in=list(contexts or [])).filter(match).order_by("ci_uuid", "root_uuid")
    found: dict[str, list[dict]] = {}
    for row in rows:
        found.setdefault(row.ci_uuid, []).append(_public_row(row))
    return found
