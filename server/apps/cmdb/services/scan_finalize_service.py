import time
from types import SimpleNamespace

from apps.cmdb.collection.metrics_cannula import MetricsCannula
from apps.cmdb.collection.plugins import get_collection_plugin
from apps.cmdb.constants.constants import DataCleanupStrategy
from apps.cmdb.models.scan_model import SCAN_MIDDLEWARE_TYPES, ScanExecution, ScanFamilyRun, ScanHit, scan_task_type_for_model
from apps.cmdb.services.scan_schedule_service import SCAN_MIDDLEWARE_LISTEN_PORTS
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
_MIDDLEWARE_SNAPSHOT_KEYS = (
    "inst_name",
    "ip_addr",
    "port",
    "listen_port",
    "version",
    "bin_path",
    "nginx_path",
    "conf_path",
    "config_path",
    "install_path",
    "log_path",
)
_MIDDLEWARE_PATH_KEYS = (
    "bin_path",
    "nginx_path",
    "conf_path",
    "config_path",
    "install_path",
    "log_path",
)
_CHANNEL_PORTS = (0, 22)
_HOST_OS_TYPE_LABELS = {"1": "Linux", "2": "Windows", "3": "AIX", "4": "Unix"}
_SCAN_METRICS_RETRY_ATTEMPTS = 12
_SCAN_METRICS_RETRY_SECONDS = 5
SCAN_MIDDLEWARE_ENRICH_DEADLINE_SECONDS = 3600
SCAN_MIDDLEWARE_ENRICH_MAX_ATTEMPTS = 16
SCAN_MIDDLEWARE_ENRICH_BASE_SECONDS = 15
SCAN_MIDDLEWARE_ENRICH_MAX_SECONDS = 300


def build_scan_collect_shim(family_run: ScanFamilyRun):
    params = {"has_network_topo": False}
    if family_run.model_id == "host":
        from apps.cmdb.services.scan_host_cloud import host_cloud_from_scan

        task = getattr(getattr(family_run, "execution", None), "task", None)
        if task is not None:
            params.update(host_cloud_from_scan(task))
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


def _middleware_row_has_paths(row: dict) -> bool:
    return any(row.get(key) not in (None, "") for key in _MIDDLEWARE_PATH_KEYS)


def middleware_enrich_countdown(attempt: int) -> int:
    return min(
        SCAN_MIDDLEWARE_ENRICH_MAX_SECONDS,
        SCAN_MIDDLEWARE_ENRICH_BASE_SECONDS * (2 ** max(int(attempt), 0)),
    )


def middleware_success_hits_missing_paths(execution: ScanExecution) -> bool:
    for family_run in execution.family_runs.all():
        if family_run.model_id not in SCAN_MIDDLEWARE_TYPES:
            continue
        for hit in family_run.hits.filter(status=ScanHit.STATUS_SUCCESS):
            snapshot = hit.snapshot if isinstance(hit.snapshot, dict) else {}
            if not _middleware_row_has_paths(snapshot):
                return True
    return False


def schedule_middleware_snapshot_enrich(execution_id, attempt=0, deadline_ts=None) -> bool:
    now_ts = int(time.time())
    if deadline_ts is None:
        deadline_ts = now_ts + SCAN_MIDDLEWARE_ENRICH_DEADLINE_SECONDS
    deadline_ts = int(deadline_ts)
    attempt = int(attempt)
    remaining = deadline_ts - now_ts
    if attempt >= SCAN_MIDDLEWARE_ENRICH_MAX_ATTEMPTS or remaining <= 0:
        return False
    from apps.cmdb.tasks.celery_tasks import enrich_scan_middleware_snapshots

    enrich_scan_middleware_snapshots.apply_async(
        args=(int(execution_id), attempt, deadline_ts),
        countdown=min(middleware_enrich_countdown(attempt), remaining),
    )
    return True


def enrich_middleware_snapshots(execution_id, attempt=0, deadline_ts=None) -> dict:
    execution = ScanExecution.objects.filter(pk=execution_id).first()
    if execution is None:
        return {"status": "missing", "execution_id": execution_id}
    for family_run in execution.family_runs.all():
        if family_run.model_id not in SCAN_MIDDLEWARE_TYPES:
            continue
        try:
            plugin_result = collect_family_metrics(family_run)
        except Exception:
            logger.exception(
                "[ScanFinalize] 补齐中间件指标失败 execution=%s family=%s",
                execution.id,
                family_run.model_id,
            )
            continue
        explode_middleware_hits(family_run, plugin_result)
        polish_hit_snapshots(family_run)
    if not middleware_success_hits_missing_paths(execution):
        logger.info("[ScanFinalize] 中间件路径已补齐 execution=%s", execution.id)
        return {"status": "ready", "execution_id": execution.id}
    next_attempt = int(attempt) + 1
    if schedule_middleware_snapshot_enrich(execution.id, next_attempt, deadline_ts):
        logger.debug(
            "[ScanFinalize] 中间件路径仍待补齐 execution=%s attempt=%s",
            execution.id,
            next_attempt,
        )
        return {"status": "scheduled", "execution_id": execution.id, "attempt": next_attempt}
    logger.warning(
        "[ScanFinalize] 中间件路径补齐停止 execution=%s attempt=%s",
        execution.id,
        attempt,
    )
    return {"status": "stopped", "execution_id": execution.id}


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
    if model_id in SCAN_MIDDLEWARE_TYPES:
        return _MIDDLEWARE_SNAPSHOT_KEYS
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


def _default_middleware_listen_port(model_id: str) -> int:
    ports = SCAN_MIDDLEWARE_LISTEN_PORTS.get(model_id) or ()
    return int(ports[0]) if ports else 0


def _upsert_middleware_hit(family_run: ScanFamilyRun, *, host: str, port: int, credential_id: str, snapshot: dict, template=None):
    existing = family_run.hits.filter(host=host, port=port, credential_id=credential_id).first()
    if existing:
        existing.status = ScanHit.STATUS_SUCCESS
        existing.cmdb_model_id = family_run.model_id
        existing.snapshot = snapshot
        existing.save(update_fields=["status", "cmdb_model_id", "snapshot", "updated_at"])
        return existing
    return ScanHit.objects.create(
        execution=family_run.execution,
        family_run=family_run,
        protocol=(template.protocol if template is not None else family_run.model_id),
        host=host,
        port=port,
        credential_id=credential_id,
        status=ScanHit.STATUS_SUCCESS,
        cmdb_model_id=family_run.model_id,
        snapshot=snapshot,
    )


def _keep_channel_hits_without_metrics(family_run: ScanFamilyRun, host: str, host_hits: list):
    """JOB 已成功但 VM 尚未可读时，保留命中并把 SSH 通道口改成默认监听口。"""
    fallback_port = _default_middleware_listen_port(family_run.model_id)
    for hit in host_hits:
        snapshot = dict(hit.snapshot or {}) if isinstance(hit.snapshot, dict) else {}
        credential_id = hit.credential_id
        if fallback_port and hit.port in _CHANNEL_PORTS:
            if fallback_port != hit.port:
                family_run.hits.filter(pk=hit.pk).delete()
            _upsert_middleware_hit(
                family_run,
                host=host,
                port=fallback_port,
                credential_id=credential_id,
                snapshot=snapshot,
                template=hit,
            )
            continue
        hit.cmdb_model_id = family_run.model_id
        hit.save(update_fields=["cmdb_model_id", "updated_at"])


def _middleware_hit_port(row: dict) -> int:
    raw = row.get("listen_port")
    if raw in (None, ""):
        raw = row.get("port")
    if raw in (None, ""):
        return 0
    text = str(raw).strip()
    if text.lower() == "unknown":
        return 0
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            return int(part)
        except ValueError:
            continue
    return 0


def _middleware_snapshot(row: dict, base=None) -> dict:
    snapshot = dict(base or {})
    for key in _MIDDLEWARE_SNAPSHOT_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            snapshot[key] = value
    return snapshot


def explode_middleware_hits(family_run: ScanFamilyRun, plugin_result: dict):
    model_id = family_run.model_id
    if model_id not in SCAN_MIDDLEWARE_TYPES:
        return
    rows_by_host = {}
    for row in (plugin_result or {}).get(model_id) or []:
        if not isinstance(row, dict):
            continue
        host = _row_host(row)
        if not host:
            continue
        rows_by_host.setdefault(host, []).append(row)

    hits_by_host = {}
    for hit in family_run.hits.filter(status=ScanHit.STATUS_SUCCESS):
        hits_by_host.setdefault(hit.host, []).append(hit)

    for host, host_hits in hits_by_host.items():
        plugin_rows = rows_by_host.get(host) or []
        if not plugin_rows:
            _keep_channel_hits_without_metrics(family_run, host, host_hits)
            continue
        templates = []
        seen_credentials = set()
        for hit in host_hits:
            if hit.credential_id in seen_credentials:
                continue
            seen_credentials.add(hit.credential_id)
            templates.append(hit)
        new_ports = set()
        for row in plugin_rows:
            port = _middleware_hit_port(row)
            new_ports.add(port)
            for template in templates:
                existing = family_run.hits.filter(
                    host=host,
                    port=port,
                    credential_id=template.credential_id,
                ).first()
                snapshot = _middleware_snapshot(row, existing.snapshot if existing else template.snapshot)
                _upsert_middleware_hit(
                    family_run,
                    host=host,
                    port=port,
                    credential_id=template.credential_id,
                    snapshot=snapshot,
                    template=template,
                )
        family_run.hits.filter(
            host=host,
            status=ScanHit.STATUS_SUCCESS,
            port__in=_CHANNEL_PORTS,
        ).exclude(port__in=new_ports).delete()

    for host, plugin_rows in rows_by_host.items():
        if host in hits_by_host:
            continue
        for row in plugin_rows:
            port = _middleware_hit_port(row)
            _upsert_middleware_hit(
                family_run,
                host=host,
                port=port,
                credential_id="",
                snapshot=_middleware_snapshot(row),
            )


def polish_hit_snapshots(family_run: ScanFamilyRun):
    """收口只整理 snapshot，不写图、不拉 VM。网络用特征库给建议类型。"""
    if family_run.model_id == "network":
        from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics

        oid_map = CollectNetworkMetrics.get_oid_map()
        for hit in family_run.hits.filter(status=ScanHit.STATUS_SUCCESS):
            snapshot = dict(hit.snapshot or {}) if isinstance(hit.snapshot, dict) else {}
            soid = str(hit.soid or snapshot.get("soid") or snapshot.get("sysobjectid") or "").strip()
            changed = False
            update_fields = []
            if soid:
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
        return
    if family_run.model_id != "host":
        return
    for hit in family_run.hits.filter(status=ScanHit.STATUS_SUCCESS):
        snapshot = dict(hit.snapshot or {}) if isinstance(hit.snapshot, dict) else {}
        os_type = snapshot.get("os_type")
        mapped = _HOST_OS_TYPE_LABELS.get(str(os_type)) if os_type not in (None, "") else None
        if mapped and snapshot.get("os_type") != mapped:
            snapshot["os_type"] = mapped
            hit.snapshot = snapshot
            hit.save(update_fields=["snapshot", "updated_at"])


def write_scan_execution(execution: ScanExecution):
    for family_run in execution.family_runs.all():
        try:
            if family_run.model_id in SCAN_MIDDLEWARE_TYPES:
                try:
                    plugin_result = collect_family_metrics(family_run)
                except Exception:
                    logger.exception(
                        "[ScanFinalize] 拉取中间件指标失败 execution=%s family=%s",
                        execution.id,
                        family_run.model_id,
                    )
                else:
                    explode_middleware_hits(family_run, plugin_result)
            polish_hit_snapshots(family_run)
        except Exception:
            logger.exception(
                "[ScanFinalize] 整理 snapshot 失败 execution=%s family=%s",
                execution.id,
                family_run.model_id,
            )
            continue
    if middleware_success_hits_missing_paths(execution) and schedule_middleware_snapshot_enrich(execution.id):
        logger.info("[ScanFinalize] 中间件路径待补齐 execution=%s", execution.id)
    return {"status": "written", "execution_id": execution.id}
