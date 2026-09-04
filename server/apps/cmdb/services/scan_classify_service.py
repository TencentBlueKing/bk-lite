from apps.cmdb.models.collect_model import OidMapping
from apps.cmdb.models.scan_model import ScanExecution, ScanHit
from apps.cmdb.services.scan_finalize_service import backfill_hit_identities, write_refined_metrics
from apps.cmdb.services.scan_identity import NETWORK_CI_TYPES
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

_TERMINAL_STATUSES = frozenset(
    {
        ScanExecution.STATUS_COMPLETED,
        ScanExecution.STATUS_FAILED,
        ScanExecution.STATUS_TIMED_OUT,
    }
)


def _ensure_terminal(execution: ScanExecution):
    if execution.status not in _TERMINAL_STATUSES:
        raise BaseAppException("扫描尚未收口，不能分类未匹配命中")


def _organization(execution: ScanExecution):
    organization = execution.task.team or []
    if organization is not None and not isinstance(organization, list):
        return [organization]
    return organization


def _eligible_unmatched_network_hits(execution: ScanExecution, hit_ids=None, soid=None):
    queryset = (
        ScanHit.objects.filter(
            execution=execution,
            status=ScanHit.STATUS_SUCCESS,
            family_run__model_id="network",
            cmdb_model_id="",
        )
        .select_related("family_run")
        .order_by("host", "id")
    )
    if hit_ids is not None:
        queryset = queryset.filter(id__in=hit_ids)
    if soid is not None:
        queryset = queryset.filter(soid=soid)
    return list(queryset)


def _row_from_hit(hit: ScanHit, device_type: str, brand: str, model: str) -> dict:
    snapshot = hit.snapshot if isinstance(hit.snapshot, dict) else {}
    sysname = str(snapshot.get("sysname") or snapshot.get("inst_name") or hit.host)
    return {
        "ip_addr": hit.host,
        "host": hit.host,
        "inst_name": f"{hit.host}-{device_type}",
        "soid": hit.soid,
        "sysobjectid": hit.soid or snapshot.get("sysobjectid") or "",
        "sysname": sysname,
        "device_type": device_type,
        "brand": brand,
        "model": model,
    }


def _annotate_snapshot(hit: ScanHit, device_type: str, brand: str, model: str):
    snapshot = dict(hit.snapshot or {}) if isinstance(hit.snapshot, dict) else {}
    snapshot["device_type"] = device_type
    snapshot["brand"] = brand
    snapshot["model"] = model
    hit.snapshot = snapshot
    hit.save(update_fields=["snapshot", "updated_at"])


def _brand_model(hit: ScanHit, brand=None, model=None):
    snapshot = hit.snapshot if isinstance(hit.snapshot, dict) else {}
    resolved_brand = str(brand or snapshot.get("brand") or "未知")
    resolved_model = str(model or snapshot.get("model") or "未知")
    return resolved_brand, resolved_model


def _write_hits(execution: ScanExecution, hits: list[ScanHit], device_type: str, brand=None, model=None):
    if not hits:
        return {"classified": 0, "skipped": 0, "failed": 0, "items": []}
    family_run = hits[0].family_run
    rows = []
    brands = {}
    for hit in hits:
        hit_brand, hit_model = _brand_model(hit, brand, model)
        brands[hit.id] = (hit_brand, hit_model)
        rows.append(_row_from_hit(hit, device_type, hit_brand, hit_model))
    refined = {device_type: rows}
    try:
        controller_result = write_refined_metrics(family_run, _organization(execution), refined)
    except Exception as exc:
        logger.exception(
            "event=scan_classify_write_failed execution=%s family_run=%s failed_stage=%s error_type=%s",
            execution.id,
            family_run.id,
            "write_ci",
            type(exc).__name__,
        )
        return {
            "classified": 0,
            "skipped": 0,
            "failed": len(hits),
            "items": [{"hit_id": hit.id, "host": hit.host, "status": "failed", "reason": "write_ci"} for hit in hits],
        }
    backfill_hit_identities(family_run, refined, controller_result)
    classified = 0
    failed = 0
    items = []
    for hit in hits:
        hit.refresh_from_db()
        if hit.cmdb_model_id == device_type:
            hit_brand, hit_model = brands[hit.id]
            _annotate_snapshot(hit, device_type, hit_brand, hit_model)
            classified += 1
            items.append({"hit_id": hit.id, "host": hit.host, "status": "classified", "cmdb_model_id": device_type})
            continue
        failed += 1
        items.append({"hit_id": hit.id, "host": hit.host, "status": "failed", "reason": "no_ci"})
    return {"classified": classified, "skipped": 0, "failed": failed, "items": items}


def classify_hits(execution: ScanExecution, hit_ids, cmdb_model_id: str) -> dict:
    _ensure_terminal(execution)
    device_type = str(cmdb_model_id or "").strip()
    if device_type not in NETWORK_CI_TYPES:
        raise BaseAppException("设备类型必须是 switch / router / firewall / loadbalance")
    requested = list(hit_ids or [])
    unmatched = _eligible_unmatched_network_hits(execution, hit_ids=requested)
    unmatched_ids = {hit.id for hit in unmatched}
    skipped = len([hit_id for hit_id in requested if hit_id not in unmatched_ids])
    written = _write_hits(execution, unmatched, device_type)
    result = {
        "classified": written["classified"],
        "skipped": skipped + written["skipped"],
        "failed": written["failed"],
        "items": written["items"],
    }
    logger.info(
        "event=scan_classify_done execution=%s classified=%s skipped=%s failed=%s",
        execution.id,
        result["classified"],
        result["skipped"],
        result["failed"],
    )
    return result


def _stamp_soid(hit: ScanHit, oid: str):
    snapshot = dict(hit.snapshot or {}) if isinstance(hit.snapshot, dict) else {}
    snapshot["soid"] = oid
    snapshot["sysobjectid"] = oid
    hit.soid = oid
    hit.snapshot = snapshot
    hit.save(update_fields=["soid", "snapshot", "updated_at"])


def rematch_soid(execution: ScanExecution, soid: str, hit_ids=None) -> dict:
    _ensure_terminal(execution)
    oid = str(soid or "").strip()
    if not oid:
        raise BaseAppException("SOID 不能为空")
    mapping = OidMapping.objects.filter(oid=oid).first()
    device_type = str(getattr(mapping, "device_type", "") or "").strip() if mapping else ""
    if mapping is None or device_type not in NETWORK_CI_TYPES:
        raise BaseAppException("特征库中没有该 SOID 的网络映射")
    if hit_ids is not None:
        candidates = _eligible_unmatched_network_hits(execution, hit_ids=hit_ids)
        unmatched = []
        for hit in candidates:
            current = str(hit.soid or "").strip()
            if current and current != oid:
                continue
            if current != oid:
                _stamp_soid(hit, oid)
            unmatched.append(hit)
    else:
        unmatched = _eligible_unmatched_network_hits(execution, soid=oid)
    brand = str(mapping.brand or "未知")
    model = str(mapping.model or "未知")
    written = _write_hits(execution, unmatched, device_type, brand, model)
    logger.info(
        "event=scan_rematch_soid_done execution=%s classified=%s skipped=%s failed=%s",
        execution.id,
        written["classified"],
        written["skipped"],
        written["failed"],
    )
    return written
