from django.db.models import Q

from apps.cmdb.constants.constants import INSTANCE, INSTANCE_ASSOCIATION
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.ci_context import CmdbCiContext, CmdbCiContextPending
from apps.cmdb.services.ci_context_policy import APPLICATION_MODEL, CONTEXT_APPLICATION, LINK_FOLLOW, classify_application_edge
from apps.core.logger import cmdb_logger as logger


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
    _enqueue_ci_context_drain()


def _enqueue_ci_context_drain() -> None:
    try:
        from apps.cmdb.tasks.ci_context import reconcile_ci_context_pending_task

        reconcile_ci_context_pending_task.delay()
    except Exception:
        logger.exception("failed to enqueue ci_context pending drain")


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


def _normalize_uuid(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _edge_parts(item):
    if isinstance(item, dict) and "edge" in item:
        props = item.get("edge") or {}
        src = item.get("src") or {}
        dst = item.get("dst") or {}
    else:
        props, src, dst = item or {}, {}, {}
    src_uuid = str(src.get("inst_uuid") or props.get("src_inst_uuid") or "")
    dst_uuid = str(dst.get("inst_uuid") or props.get("dst_inst_uuid") or "")
    src_model = str(src.get("model_id") or props.get("src_model_id") or "")
    dst_model = str(dst.get("model_id") or props.get("dst_model_id") or "")
    src_view = {"model_id": src_model, "inst_uuid": src_uuid}
    dst_view = {"model_id": dst_model, "inst_uuid": dst_uuid}
    return props, src_view, dst_view, dst if isinstance(dst, dict) else {}


def _classifier_edge(props, src, dst) -> dict:
    return {
        "asst_id": props.get("asst_id") or "",
        "model_asst_id": props.get("model_asst_id") or "",
        "context_link": props.get("context_link") or LINK_FOLLOW,
        "src": src,
        "dst": dst,
    }


def _query_instances(ag, conditions) -> list[dict]:
    rows, _count = ag.query_entity(INSTANCE, conditions)
    return list(rows or [])


def _outbound_edges(ag, src_uuid):
    return ag.query_edge(
        INSTANCE_ASSOCIATION,
        [{"field": "src_inst_uuid", "type": "str=", "value": src_uuid}],
        return_entity=True,
    ) or []


def _member_record(decision, dst_view, raw_dst, *, via_uuid) -> dict | None:
    ci_uuid = _normalize_uuid(decision.ci_uuid)
    if not ci_uuid:
        return None
    return {
        "ci_uuid": ci_uuid,
        "ci_model": str(dst_view.get("model_id") or ""),
        "layer": decision.layer,
        "via_uuid": _normalize_uuid(via_uuid) or None,
        "model_asst_id": decision.model_asst_id or "",
        "raw_dst": raw_dst if isinstance(raw_dst, dict) else {},
    }


def _pick(name, *sources):
    for source in sources:
        if not isinstance(source, dict) or name not in source:
            continue
        value = source.get(name)
        if value is None:
            continue
        return value
    return None


def _load_member_instances(ag, uuids) -> dict[str, dict]:
    wanted = list(dict.fromkeys(uuid for uuid in uuids if uuid))
    if not wanted:
        return {}
    rows = _query_instances(ag, [{"field": "inst_uuid", "type": "str[]", "value": wanted}])
    return {str(row.get("inst_uuid")): row for row in rows if row.get("inst_uuid")}


def _delete_application_rows(root_uuid: str, *, keep=()) -> None:
    stale = CmdbCiContext.objects.filter(root_uuid=root_uuid, context=CONTEXT_APPLICATION)
    if keep:
        stale = stale.exclude(ci_uuid__in=list(keep))
    stale.delete()


def recompute_application(application_uuid) -> None:
    """从单个应用正向最多走两跳，重写该应用的 application 上下文成员。"""
    application_uuid = _normalize_uuid(application_uuid)
    if not application_uuid:
        return

    with GraphClient() as ag:
        apps = _query_instances(ag, [{"field": "inst_uuid", "type": "str=", "value": application_uuid}])
        app = apps[0] if apps else None
        if not app or str(app.get("model_id") or "") != APPLICATION_MODEL:
            _delete_application_rows(application_uuid)
            return

        layer1: dict[str, dict] = {}
        for item in _outbound_edges(ag, application_uuid):
            props, src, dst, raw_dst = _edge_parts(item)
            decision = classify_application_edge(_classifier_edge(props, src, dst), src_is_member=False)
            if not (decision.include and decision.layer == 1):
                continue
            record = _member_record(decision, dst, raw_dst, via_uuid=None)
            if record is None or record["ci_uuid"] == application_uuid or record["ci_uuid"] in layer1:
                continue
            layer1[record["ci_uuid"]] = record

        layer2: dict[str, dict] = {}
        for via_uuid in layer1:
            for item in _outbound_edges(ag, via_uuid):
                props, src, dst, raw_dst = _edge_parts(item)
                decision = classify_application_edge(_classifier_edge(props, src, dst), src_is_member=True)
                if not (decision.include and decision.layer == 2):
                    continue
                record = _member_record(decision, dst, raw_dst, via_uuid=decision.via_uuid or via_uuid)
                if record is None or record["ci_uuid"] in layer1 or record["ci_uuid"] in layer2:
                    continue
                if record["ci_uuid"] == application_uuid:
                    continue
                layer2[record["ci_uuid"]] = record

        members = {**layer2, **layer1}
        instances = _load_member_instances(ag, members)
        system_uuids = []
        inbound = ag.query_edge(
            INSTANCE_ASSOCIATION,
            [{"field": "dst_inst_uuid", "type": "str=", "value": application_uuid}],
            return_entity=True,
        ) or []
        for item in inbound:
            props, src, dst, _raw_dst = _edge_parts(item)
            decision = classify_application_edge(_classifier_edge(props, src, dst), src_is_member=False)
            system_id = _normalize_uuid(decision.attach_system_uuid)
            if system_id:
                system_uuids.append(system_id)
        system_uuid = min(system_uuids) if system_uuids else None
        root_model = str(app.get("model_id") or APPLICATION_MODEL)

        for record in members.values():
            inst = instances.get(record["ci_uuid"]) or {}
            raw_dst = record["raw_dst"]
            organization = _pick("organization", inst, raw_dst)
            ci_model = _pick("model_id", inst, raw_dst) or record["ci_model"]
            CmdbCiContext.objects.update_or_create(
                ci_uuid=record["ci_uuid"],
                context=CONTEXT_APPLICATION,
                root_uuid=application_uuid,
                defaults={
                    "root_model": root_model,
                    "ci_model": str(ci_model or ""),
                    "ip_addr": str(_pick("ip_addr", inst, raw_dst) or ""),
                    "organization": list(organization) if isinstance(organization, list) else [],
                    "system_uuid": system_uuid,
                    "layer": record["layer"],
                    "via_uuid": record["via_uuid"],
                    "model_asst_id": record["model_asst_id"] or "",
                    "payload": {},
                },
            )
        _delete_application_rows(application_uuid, keep=members)


def _claim_pending(field: str, limit: int) -> list:
    query = CmdbCiContextPending.objects.filter(**{f"{field}__isnull": False}).order_by("id").values_list("id", field)
    rows = list(query[:limit])
    if not rows:
        return []
    CmdbCiContextPending.objects.filter(id__in=[row[0] for row in rows]).delete()
    return [row[1] for row in rows]


def _restore_pending(**fields) -> None:
    CmdbCiContextPending.objects.bulk_create([CmdbCiContextPending(**fields)], ignore_conflicts=True)


def _application_endpoints(item) -> tuple[list, list[str]]:
    _props, src, dst, _raw_dst = _edge_parts(item)
    endpoints = [src.get("inst_uuid"), dst.get("inst_uuid")]
    roots = []
    if src.get("model_id") == APPLICATION_MODEL:
        roots.append(src.get("inst_uuid"))
    if dst.get("model_id") == APPLICATION_MODEL:
        roots.append(dst.get("inst_uuid"))
    return endpoints, roots


def _roots_for_model_asst(model_asst_id: str) -> list[str]:
    roots: list[str] = []
    endpoint_uuids: list = []
    with GraphClient() as ag:
        edges = (
            ag.query_edge(
                INSTANCE_ASSOCIATION,
                [{"field": "model_asst_id", "type": "str=", "value": model_asst_id}],
                return_entity=True,
            )
            or []
        )
    for item in edges:
        endpoints, application_uuids = _application_endpoints(item)
        endpoint_uuids.extend(endpoints)
        roots.extend(application_uuids)
    endpoints = _distinct_texts(endpoint_uuids)
    if endpoints:
        roots.extend(CmdbCiContext.objects.filter(ci_uuid__in=endpoints, context=CONTEXT_APPLICATION).values_list("root_uuid", flat=True))
    return _distinct_texts(roots)


def _load_ci(ci_uuid: str) -> tuple[dict | None, list[str]]:
    roots = list(
        CmdbCiContext.objects.filter(Q(ci_uuid=ci_uuid) | Q(root_uuid=ci_uuid), context=CONTEXT_APPLICATION).values_list("root_uuid", flat=True)
    )
    endpoint_uuids: list = []
    with GraphClient() as ag:
        instances = _query_instances(ag, [{"field": "inst_uuid", "type": "str=", "value": ci_uuid}])
        for field in ("src_inst_uuid", "dst_inst_uuid"):
            edges = (
                ag.query_edge(
                    INSTANCE_ASSOCIATION,
                    [{"field": field, "type": "str=", "value": ci_uuid}],
                    return_entity=True,
                )
                or []
            )
            for item in edges:
                endpoints, application_uuids = _application_endpoints(item)
                endpoint_uuids.extend(endpoints)
                roots.extend(application_uuids)
    endpoints = _distinct_texts(endpoint_uuids)
    if endpoints:
        roots.extend(CmdbCiContext.objects.filter(ci_uuid__in=endpoints, context=CONTEXT_APPLICATION).values_list("root_uuid", flat=True))
    instance = instances[0] if instances else None
    return instance, _distinct_texts(roots)


def _recompute_roots(root_uuids) -> None:
    for root_uuid in _distinct_texts(root_uuids):
        recompute_application(root_uuid)


def _apply_ci(ci_uuid: str) -> None:
    instance, roots = _load_ci(ci_uuid)
    if instance is None:
        _recompute_roots(roots)
        CmdbCiContext.objects.filter(ci_uuid=ci_uuid).delete()
        return
    organization = _pick("organization", instance)
    CmdbCiContext.objects.filter(ci_uuid=ci_uuid).update(
        ip_addr=str(_pick("ip_addr", instance) or ""),
        organization=list(organization) if isinstance(organization, list) else [],
    )
    if str(instance.get("model_id") or "") == APPLICATION_MODEL:
        recompute_application(ci_uuid)
        self_uuid = _normalize_uuid(ci_uuid)
        roots = [root_uuid for root_uuid in roots if _normalize_uuid(root_uuid) != self_uuid]
    _recompute_roots(roots)


def _drain_roots(root_uuids: list[str]) -> int:
    done = 0
    for root_uuid in root_uuids:
        try:
            recompute_application(root_uuid)
        except Exception:
            logger.exception("ci_context pending drain failed, root_uuid=%s", root_uuid)
            _restore_pending(root_uuid=root_uuid)
            continue
        done += 1
    return done


def _drain_model_assts(model_asst_ids: list[str]) -> int:
    done = 0
    for model_asst_id in model_asst_ids:
        try:
            _recompute_roots(_roots_for_model_asst(model_asst_id))
        except Exception:
            logger.exception("ci_context pending drain failed, model_asst_id=%s", model_asst_id)
            _restore_pending(model_asst_id=model_asst_id)
            continue
        done += 1
    return done


def _drain_cis(ci_uuids: list[str]) -> int:
    done = 0
    for ci_uuid in ci_uuids:
        try:
            _apply_ci(ci_uuid)
        except Exception:
            logger.exception("ci_context pending drain failed, ci_uuid=%s", ci_uuid)
            _restore_pending(ci_uuid=ci_uuid)
            continue
        done += 1
    return done


def drain_ci_context_pending(limit: int = 200) -> dict:
    """排空待重算名单。单轮最多处理 limit 行，顺序是应用、关联规则、实例。"""
    remaining = limit
    root_uuids = _claim_pending("root_uuid", remaining)
    remaining -= len(root_uuids)
    root_done = _drain_roots(root_uuids)

    model_asst_ids = _claim_pending("model_asst_id", remaining)
    remaining -= len(model_asst_ids)
    model_done = _drain_model_assts(model_asst_ids)

    ci_uuids = _claim_pending("ci_uuid", remaining)
    ci_done = _drain_cis(ci_uuids)
    if root_done or model_done or ci_done:
        logger.info(
            "ci_context pending drain finished, root_uuids=%s, model_asst_ids=%s, ci_uuids=%s",
            root_done,
            model_done,
            ci_done,
        )
    return {"root_uuids": root_done, "model_asst_ids": model_done, "ci_uuids": ci_done}
