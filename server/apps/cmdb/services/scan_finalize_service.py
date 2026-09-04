import time
from types import SimpleNamespace

from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import DataCleanupStrategy
from apps.cmdb.models.scan_model import ScanExecution, ScanFamilyRun, ScanHit, scan_task_type_for_model
from apps.cmdb.services.scan_identity import refine_scan_metrics
from apps.core.logger import cmdb_logger as logger

_PHYSICAL_SNAPSHOT_KEYS = ("serial_number", "uuid", "board_serial")
_HOST_SNAPSHOT_KEYS = (
    "hostname",
    "os_type",
    "os_name",
    "os_version",
    "os_bit",
    "cpu_arch",
    "cpu_model",
    "cpu_core",
    "memory",
    "disk",
    "inner_mac",
)
_NETWORK_SNAPSHOT_KEYS = (
    "inst_name",
    "ip_addr",
    "soid",
    "sysobjectid",
    "sysname",
    "sysdescr",
    "device_type",
    "brand",
    "model",
)
_DB_SNAPSHOT_KEYS = ("inst_name", "ip_addr", "port", "version", "db_version")
_HOST_OS_TYPE_LABELS = {"1": "Linux", "2": "Windows", "3": "AIX", "4": "Unix"}
_SCAN_METRICS_RETRY_ATTEMPTS = 12
_SCAN_METRICS_RETRY_SECONDS = 5


def build_scan_collect_shim(family_run: ScanFamilyRun):
    params = {"has_network_topo": False}
    if family_run.model_id == "host":
        from apps.cmdb.services.scan_collect_generate import _host_cloud_from_scan

        task = getattr(getattr(family_run, "execution", None), "task", None)
        if task is not None:
            params.update(_host_cloud_from_scan(task))
    return SimpleNamespace(
        id=family_run.id,
        model_id=family_run.model_id,
        instances=[],
        is_network_topo=False,
        params=params,
        driver_type=family_run.driver_type,
        topology_snapshot={},
        topology_contract={},
    )


def collect_family_metrics(family_run: ScanFamilyRun):
    plugin_cls = get_collection_plugin(
        scan_task_type_for_model(family_run.model_id),
        family_run.model_id,
    )
    plugin = plugin_cls(
        "scan",
        None,
        family_run.id,
        collect_inst=build_scan_collect_shim(family_run),
    )
    return plugin.run() or {}


def _missing_success_hosts(family_run: ScanFamilyRun, plugin_result: dict) -> int:
    success_hosts = {host for host in family_run.hits.filter(status=ScanHit.STATUS_SUCCESS).values_list("host", flat=True) if str(host or "").strip()}
    if not success_hosts:
        return 0
    covered = {host for host, row in _rows_by_host(plugin_result).items() if _row_has_snapshot_facts(family_run.model_id, row)}
    return len(success_hosts - covered)


def collect_family_metrics_until_hits(family_run: ScanFamilyRun) -> dict:
    metrics = {}
    last_missing = 0
    for attempt in range(1, _SCAN_METRICS_RETRY_ATTEMPTS + 1):
        metrics = collect_family_metrics(family_run)
        last_missing = _missing_success_hosts(family_run, metrics)
        if last_missing == 0:
            return metrics
        logger.debug(
            "[ScanFinalize] 指标尚未覆盖成功命中 execution=%s family=%s missing=%s attempt=%s",
            family_run.execution_id,
            family_run.model_id,
            last_missing,
            attempt,
        )
        if attempt < _SCAN_METRICS_RETRY_ATTEMPTS:
            time.sleep(_SCAN_METRICS_RETRY_SECONDS)
    logger.info(
        "[ScanFinalize] 收口时指标仍未覆盖成功命中 execution=%s family=%s missing=%s",
        family_run.execution_id,
        family_run.model_id,
        last_missing,
    )
    return metrics


def write_refined_metrics(family_run: ScanFamilyRun, organization, refined: dict):
    plugin_cls = get_collection_plugin(
        scan_task_type_for_model(family_run.model_id),
        family_run.model_id,
    )
    cannula = MetricsCannula(
        inst_id=None,
        organization=organization,
        inst_name=None,
        task_id=family_run.id,
        collect_plugin=plugin_cls,
        manual=False,
        default_metrics=refined,
        filter_collect_task=False,
        data_cleanup_strategy=DataCleanupStrategy.NO_CLEANUP,
    )
    return cannula.collect_controller()


def _row_host(row: dict) -> str:
    return str(row.get("ip_addr") or row.get("host") or row.get("ip") or "").strip()


def _controller_instances(controller_result: dict):
    for model_id, result in (controller_result or {}).items():
        if model_id in ("__raw_data__", "all") or not isinstance(result, dict):
            continue
        for op in ("add", "update"):
            bucket = result.get(op) or {}
            for item in bucket.get("success") or []:
                info = item.get("inst_info") if isinstance(item, dict) else None
                if not isinstance(info, dict):
                    info = item if isinstance(item, dict) else {}
                yield model_id, info


def backfill_hit_identities(family_run: ScanFamilyRun, refined: dict, controller_result: dict):
    model_by_host = {}
    for model_id, rows in (refined or {}).items():
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            host = _row_host(row)
            if host:
                model_by_host[host] = model_id

    uuid_by_host = {}
    for model_id, info in _controller_instances(controller_result):
        host = _row_host(info)
        inst_uuid = str(info.get("inst_uuid") or "").strip()
        if host and inst_uuid:
            uuid_by_host[host] = (inst_uuid, str(info.get("model_id") or model_id))

    for hit in family_run.hits.all():
        if hit.status != ScanHit.STATUS_SUCCESS:
            continue
        mapped = uuid_by_host.get(hit.host)
        update_fields = []
        if mapped:
            hit.inst_uuid, hit.cmdb_model_id = mapped
            update_fields.extend(["inst_uuid", "cmdb_model_id"])
        elif hit.host in model_by_host and not hit.cmdb_model_id:
            hit.cmdb_model_id = model_by_host[hit.host]
            update_fields.append("cmdb_model_id")
        if update_fields:
            update_fields.append("updated_at")
            hit.save(update_fields=update_fields)


def _snapshot_keys_for_family(model_id: str):
    if model_id == "host":
        return _HOST_SNAPSHOT_KEYS
    if model_id == "network":
        return _NETWORK_SNAPSHOT_KEYS
    if model_id == "physcial_server":
        return _PHYSICAL_SNAPSHOT_KEYS
    return _DB_SNAPSHOT_KEYS


def _row_has_snapshot_facts(model_id: str, row: dict) -> bool:
    return any(row.get(key) not in (None, "") for key in _snapshot_keys_for_family(model_id))


def _rows_by_host(plugin_result: dict):
    by_host = {}
    for model_id, rows in (plugin_result or {}).items():
        if model_id in ("interface", "__raw_data__", "all") or not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            host = _row_host(row)
            if not host:
                continue
            merged = dict(by_host.get(host) or {})
            merged.update({k: v for k, v in row.items() if v not in (None, "")})
            merged.setdefault("_plugin_model", model_id)
            by_host[host] = merged
    return by_host


def annotate_hit_snapshots(family_run: ScanFamilyRun, plugin_result: dict, oid_map=None):
    """把 mapping 后的基础事实回填到命中清单 snapshot（含未知 SOID 仍保留的行）。"""
    by_host = _rows_by_host(plugin_result)
    if not by_host:
        return
    oid_map = oid_map or {}
    keys = _snapshot_keys_for_family(family_run.model_id)
    for hit in family_run.hits.filter(status=ScanHit.STATUS_SUCCESS):
        row = by_host.get(hit.host)
        if not row:
            continue
        snapshot = dict(hit.snapshot or {})
        changed = False
        update_fields = []
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            if family_run.model_id == "host" and key == "os_type":
                value = _HOST_OS_TYPE_LABELS.get(str(value), value)
            if snapshot.get(key) != value:
                snapshot[key] = value
                changed = True
        if family_run.model_id == "network" and not snapshot.get("sysname"):
            for key in ("sys_desc", "sysdescr"):
                value = row.get(key)
                if value not in (None, ""):
                    snapshot["sysname"] = value
                    changed = True
                    break
        soid = str(row.get("soid") or row.get("sysobjectid") or snapshot.get("soid") or snapshot.get("sysobjectid") or "")
        if soid and family_run.model_id == "network":
            mapped = oid_map.get(soid) if isinstance(oid_map, dict) else None
            if isinstance(mapped, dict):
                for key in ("brand", "model", "device_type"):
                    value = mapped.get(key)
                    if value and snapshot.get(key) != value:
                        snapshot[key] = value
                        changed = True
            if hit.soid != soid:
                hit.soid = soid
                update_fields.append("soid")
        if changed:
            hit.snapshot = snapshot
            update_fields.extend(["snapshot", "updated_at"])
        elif update_fields:
            update_fields.append("updated_at")
        if update_fields:
            hit.save(update_fields=list(dict.fromkeys(update_fields)))


def annotate_physical_snapshot(family_run: ScanFamilyRun, plugin_result: dict):
    annotate_hit_snapshots(family_run, plugin_result)


def attach_snmp_hits_to_physical(execution: ScanExecution):
    physical_by_host = {
        hit.host: hit.inst_uuid
        for hit in execution.hits.filter(
            family_run__model_id="physcial_server",
            status=ScanHit.STATUS_SUCCESS,
        ).exclude(inst_uuid="")
    }
    if not physical_by_host:
        return
    snmp_hits = execution.hits.filter(
        family_run__model_id="network",
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id="",
        inst_uuid="",
    )
    for hit in snmp_hits:
        attached = physical_by_host.get(hit.host)
        if not attached:
            continue
        hit.attached_inst_uuid = attached
        hit.save(update_fields=["attached_inst_uuid", "updated_at"])


def write_scan_execution(execution: ScanExecution):
    task = execution.task
    organization = task.team or []
    if organization is not None and not isinstance(organization, list):
        organization = [organization]

    for family_run in execution.family_runs.all():
        try:
            metrics = collect_family_metrics_until_hits(family_run)
        except Exception:
            logger.exception(
                "[ScanFinalize] 族 mapping 失败 execution=%s family=%s",
                execution.id,
                family_run.model_id,
            )
            continue

        oid_map = None
        if family_run.model_id == "network":
            from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics

            oid_map = CollectNetworkMetrics.get_oid_map()
        refined = refine_scan_metrics(family_run.model_id, metrics, oid_map=oid_map)
        annotate_hit_snapshots(family_run, metrics, oid_map=oid_map)
        if not refined:
            continue
        try:
            controller_result = write_refined_metrics(family_run, organization, refined)
        except Exception:
            logger.exception(
                "[ScanFinalize] 写 CI 失败 execution=%s family=%s",
                execution.id,
                family_run.model_id,
            )
            continue
        backfill_hit_identities(family_run, refined, controller_result)

    attach_snmp_hits_to_physical(execution)
    return {"status": "written", "execution_id": execution.id}
