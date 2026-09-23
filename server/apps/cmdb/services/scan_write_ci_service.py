"""扫描命中 → 按 snapshot 显式写入 CMDB。"""

from __future__ import annotations

from collections import defaultdict

from apps.cmdb.models.scan_model import SCAN_DATABASE_TYPES, SCAN_MIDDLEWARE_TYPES, ScanExecution, ScanHit
from apps.cmdb.services.scan_finalize_service import attach_snmp_hits_to_physical, backfill_hit_identities, write_refined_metrics
from apps.cmdb.services.scan_host_cloud import host_cloud_from_scan
from apps.cmdb.services.scan_identity import UNMATCH_CREDENTIAL_FAILED, ensure_scan_execution_terminal, suggested_network_type, unmatch_reason_for_hit
from apps.core.logger import cmdb_logger as logger

_DB_INST_NAME_SUFFIX = {
    "mysql": "mysql",
    "postgresql": "pg",
    "mssql": "mssql",
    "influxdb": "influxdb",
}


def _organization(execution: ScanExecution):
    organization = execution.task.team or []
    if organization is not None and not isinstance(organization, list):
        return [organization]
    return organization


def _snapshot(hit: ScanHit) -> dict:
    snapshot = hit.snapshot if isinstance(hit.snapshot, dict) else {}
    return dict(snapshot)


def _scan_task_of(hit: ScanHit):
    task = getattr(getattr(hit, "execution", None), "task", None)
    if task is not None:
        return task
    family_run = getattr(hit, "family_run", None)
    return getattr(getattr(family_run, "execution", None), "task", None)


def _host_cloud_fields(hit: ScanHit, snapshot: dict) -> dict:
    """主机「云区域」必填：snapshot → 扫描任务 → 缺省区域 1。"""
    if snapshot.get("cloud") not in (None, ""):
        fields = {"cloud": snapshot.get("cloud")}
        if snapshot.get("cloud_name") not in (None, ""):
            fields["cloud_name"] = snapshot.get("cloud_name")
        return fields
    fields = dict(host_cloud_from_scan(_scan_task_of(hit)))
    if fields.get("cloud") in (None, ""):
        fields["cloud"] = 1
    return fields


def _map_network_row(hit: ScanHit, snapshot: dict, host: str) -> tuple[str, dict] | None:
    device_type = suggested_network_type(hit)
    if not device_type:
        return None
    inst_name = str(snapshot.get("inst_name") or "").strip() or f"{host}-{device_type}"
    return device_type, {
        "ip_addr": host,
        "host": host,
        "inst_name": inst_name,
        "soid": hit.soid or snapshot.get("soid") or snapshot.get("sysobjectid") or "",
        "sysobjectid": snapshot.get("sysobjectid") or hit.soid or "",
        "sysname": snapshot.get("sysname") or snapshot.get("sys_desc") or inst_name,
        "sys_desc": snapshot.get("sys_desc") or snapshot.get("sysdescr") or snapshot.get("sysname") or "",
        "brand": snapshot.get("brand") or "",
        "model": snapshot.get("model") or "",
        "device_type": device_type,
        "model_id": device_type,
    }


def _map_host_row(hit: ScanHit, snapshot: dict, host: str) -> tuple[str, dict]:
    inst_name = str(snapshot.get("inst_name") or snapshot.get("hostname") or host).strip() or host
    row = {
        "ip_addr": host,
        "host": host,
        "inst_name": inst_name,
        "hostname": snapshot.get("hostname") or "",
        "os_type": snapshot.get("os_type") or "",
        "os_name": snapshot.get("os_name") or "",
        "os_version": snapshot.get("os_version") or "",
        "os_bit": snapshot.get("os_bit") or snapshot.get("os_bits") or "",
        "cpu_arch": snapshot.get("cpu_arch") or "",
        "cpu_model": snapshot.get("cpu_model") or "",
        "cpu_core": snapshot.get("cpu_core") or snapshot.get("cpu_cores") or "",
        "memory": snapshot.get("memory") or snapshot.get("memory_gb") or "",
        "disk": snapshot.get("disk") or snapshot.get("disk_gb") or "",
        "inner_mac": snapshot.get("inner_mac") or snapshot.get("mac_address") or "",
    }
    row.update(_host_cloud_fields(hit, snapshot))
    return "host", row


def _map_physical_row(snapshot: dict, host: str) -> tuple[str, dict]:
    serial = str(snapshot.get("serial_number") or "").strip()
    inst_name = str(snapshot.get("inst_name") or serial or host).strip() or host
    return "physcial_server", {
        "ip_addr": host,
        "host": host,
        "inst_name": inst_name,
        "serial_number": serial,
        "uuid": snapshot.get("uuid") or "",
        "board_serial": snapshot.get("board_serial") or "",
        "brand": snapshot.get("brand") or "",
        "model": snapshot.get("model") or "",
    }


def _map_database_row(hit: ScanHit, snapshot: dict, host: str, family: str) -> tuple[str, dict]:
    port = hit.port or snapshot.get("port") or ""
    suffix = _DB_INST_NAME_SUFFIX.get(family, family)
    inst_name = str(snapshot.get("inst_name") or "").strip() or (f"{host}-{suffix}-{port}" if port not in (None, "") else f"{host}-{suffix}")
    return family, {
        "ip_addr": host,
        "host": host,
        "inst_name": inst_name,
        "port": port,
        "version": snapshot.get("version") or snapshot.get("db_version") or "",
    }


def _map_middleware_row(hit: ScanHit, snapshot: dict, host: str, family: str) -> tuple[str, dict]:
    port = hit.port or snapshot.get("port") or snapshot.get("listen_port") or ""
    if isinstance(port, str) and "," in port:
        port = port.split(",")[0].strip() or port
    inst_name = str(snapshot.get("inst_name") or "").strip() or (
        f"{host}-{family}-{port}" if port not in (None, "", "unknown") else f"{host}-{family}"
    )
    row = {
        "ip_addr": host,
        "host": host,
        "inst_name": inst_name,
        "port": port if port not in ("unknown",) else "",
        "version": snapshot.get("version") or "",
        "bin_path": snapshot.get("bin_path") or snapshot.get("nginx_path") or "",
        "conf_path": snapshot.get("conf_path") or snapshot.get("config_path") or "",
        "install_path": snapshot.get("install_path") or "",
        "log_path": snapshot.get("log_path") or "",
        "model_id": family,
        "assos": [
            {
                "model_id": "host",
                "inst_name": host,
                "asst_id": "run",
                "model_asst_id": f"{family}_run_host",
            }
        ],
    }
    for key, value in snapshot.items():
        if key in row or value in (None, ""):
            continue
        row[key] = value
    return family, row


def mapping_row_from_hit(hit: ScanHit) -> tuple[str, dict] | None:
    """snapshot → 写入 CI 的一行。只信 snapshot，不回查采集结果。"""
    family = str(getattr(hit.family_run, "model_id", "") or "").strip()
    snapshot = _snapshot(hit)
    host = str(hit.host or snapshot.get("ip_addr") or snapshot.get("host") or "").strip()
    if not host:
        return None
    if family == "network":
        return _map_network_row(hit, snapshot, host)
    if family == "host":
        return _map_host_row(hit, snapshot, host)
    if family == "physcial_server":
        return _map_physical_row(snapshot, host)
    if family in SCAN_DATABASE_TYPES:
        return _map_database_row(hit, snapshot, host, family)
    if family in SCAN_MIDDLEWARE_TYPES:
        return _map_middleware_row(hit, snapshot, host, family)
    return None


def _lookup_host_by_ip(host: str) -> dict | None:
    """按 host.ip_addr 查已有主机；查不到则返回 None，禁止新建。"""
    if not host:
        return None
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    filters = [
        {"field": "model_id", "type": "str=", "value": "host"},
        {"field": "ip_addr", "type": "str=", "value": host},
    ]
    try:
        with GraphClient() as ag:
            rows, _ = ag.query_entity(INSTANCE, filters)
    except Exception:
        logger.info("event=scan_middleware_host_lookup_skipped host=%s", host)
        return None
    for row in rows or []:
        if isinstance(row, dict) and row.get("_id") is not None:
            return row
    return None


def attach_middleware_hits_to_host(execution: ScanExecution):
    from apps.cmdb.services.instance import InstanceManage

    hits = (
        execution.hits.filter(
            family_run__model_id__in=SCAN_MIDDLEWARE_TYPES,
            status=ScanHit.STATUS_SUCCESS,
        )
        .exclude(inst_uuid="")
        .select_related("family_run")
    )
    for hit in hits:
        host_row = _lookup_host_by_ip(hit.host)
        if not host_row:
            continue
        host_uuid = str(host_row.get("inst_uuid") or "")
        if host_uuid and hit.attached_inst_uuid != host_uuid:
            hit.attached_inst_uuid = host_uuid
            hit.save(update_fields=["attached_inst_uuid", "updated_at"])
        if hit.inst_uuid and host_uuid:
            try:
                InstanceManage.instance_association_create_by_uuid(
                    src_inst_uuid=hit.inst_uuid,
                    dst_inst_uuid=host_uuid,
                    model_asst_id=f"{hit.family_run.model_id}_run_host",
                    operator="scan",
                )
            except Exception:
                logger.info("event=scan_middleware_run_host_skipped hit=%s host=%s", hit.id, hit.host)


def _skip_item(hit: ScanHit, reason: str) -> dict:
    return {
        "hit_id": hit.id,
        "host": hit.host,
        "status": "skipped",
        "reason": reason,
        "family": getattr(hit.family_run, "model_id", ""),
    }


def _recorded_uuid(hit: ScanHit) -> str:
    return str(getattr(hit, "inst_uuid", "") or "").strip()


def _live_inst_uuids(hits: list[ScanHit]) -> set[str]:
    """清单 inst_uuid 必须在图里才算已写入；用户删过 CI 后应重写，不能只看 Postgres。"""
    wanted = [_recorded_uuid(hit) for hit in hits if _recorded_uuid(hit)]
    if not wanted:
        return set()
    from apps.cmdb.services.instance import InstanceManage

    rows = []
    try:
        rows = InstanceManage.query_entity_by_uuids(wanted) or []
    except Exception:
        for uuid in wanted:
            try:
                row = InstanceManage.query_entity_by_uuid(uuid) or {}
            except Exception:
                row = {}
            if isinstance(row, dict) and row.get("inst_uuid"):
                rows.append(row)
    found = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        uid = str(row.get("inst_uuid") or "").strip()
        if uid:
            found.add(uid)
    return found


class ScanWriteCiService:
    @classmethod
    def write(cls, execution: ScanExecution, hit_ids: list[int]) -> dict:
        ensure_scan_execution_terminal(execution)
        hits = list(ScanHit.objects.filter(execution=execution, id__in=hit_ids).select_related("family_run", "execution__task"))
        results = []
        pending = defaultdict(list)
        live_uuids = _live_inst_uuids(hits)
        for hit in hits:
            recorded = _recorded_uuid(hit)
            if recorded and recorded in live_uuids:
                results.append(
                    {
                        "hit_id": hit.id,
                        "host": hit.host,
                        "status": "already_written",
                        "inst_uuid": hit.inst_uuid,
                        "cmdb_model_id": hit.cmdb_model_id,
                        "family": getattr(hit.family_run, "model_id", ""),
                    }
                )
                continue
            if recorded:
                logger.debug(
                    "event=scan_write_ci_stale_uuid hit=%s host=%s",
                    hit.id,
                    hit.host,
                )
            if unmatch_reason_for_hit(hit) == UNMATCH_CREDENTIAL_FAILED:
                results.append(_skip_item(hit, "credential_failed"))
                continue
            family = str(getattr(hit.family_run, "model_id", "") or "").strip()
            if family == "network" and not suggested_network_type(hit):
                results.append(_skip_item(hit, "need_classify"))
                continue
            if hit.status != ScanHit.STATUS_SUCCESS:
                results.append(_skip_item(hit, "not_success"))
                continue
            mapped = mapping_row_from_hit(hit)
            if mapped is None:
                results.append(_skip_item(hit, "need_classify" if family == "network" else "no_snapshot"))
                continue
            model_id, row = mapped
            pending[hit.family_run_id].append((hit, model_id, row))

        for family_run_id, batch in pending.items():
            family_run = batch[0][0].family_run
            refined = defaultdict(list)
            for _hit, model_id, row in batch:
                refined[model_id].append(row)
            try:
                controller_result = write_refined_metrics(family_run, _organization(execution), dict(refined))
            except Exception as exc:
                logger.exception(
                    "event=scan_write_ci_failed execution=%s family_run=%s failed_stage=%s error_type=%s",
                    execution.id,
                    family_run.id,
                    "write_ci",
                    type(exc).__name__,
                )
                for hit, _model_id, _row in batch:
                    results.append(
                        {
                            "hit_id": hit.id,
                            "host": hit.host,
                            "status": "failed",
                            "reason": "write_ci",
                            "family": family_run.model_id,
                        }
                    )
                continue
            backfill_hit_identities(family_run, dict(refined), controller_result)
            for hit, model_id, _row in batch:
                hit.refresh_from_db()
                if hit.inst_uuid:
                    results.append(
                        {
                            "hit_id": hit.id,
                            "host": hit.host,
                            "status": "written",
                            "inst_uuid": hit.inst_uuid,
                            "cmdb_model_id": hit.cmdb_model_id or model_id,
                            "family": family_run.model_id,
                        }
                    )
                    continue
                results.append(
                    {
                        "hit_id": hit.id,
                        "host": hit.host,
                        "status": "failed",
                        "reason": "no_ci",
                        "family": family_run.model_id,
                    }
                )

        attach_snmp_hits_to_physical(execution)
        attach_middleware_hits_to_host(execution)
        written = sum(1 for row in results if row.get("status") == "written")
        skipped = sum(1 for row in results if row.get("status") in {"skipped", "already_written"})
        failed = sum(1 for row in results if row.get("status") == "failed")
        logger.info(
            "event=scan_write_ci_done execution=%s written=%s skipped=%s failed=%s",
            execution.id,
            written,
            skipped,
            failed,
        )
        return {
            "execution_id": execution.id,
            "written": written,
            "skipped": skipped,
            "failed": failed,
            "items": results,
        }

    @classmethod
    def write_and_generate(cls, execution: ScanExecution, hit_ids: list[int], *, request=None, operator: str = "") -> dict:
        write_result = cls.write(execution, hit_ids)
        # 写失败 / 未分类 / 凭据失败的行不进生成。
        eligible_ids = [item["hit_id"] for item in write_result.get("items") or [] if item.get("status") in {"written", "already_written"}]
        collect_result = {
            "execution_id": execution.id,
            "created": 0,
            "appended": 0,
            "skipped": 0,
            "failed": 0,
            "items": [],
        }
        if eligible_ids:
            from apps.cmdb.services.scan_collect_generate import ScanCollectGenerateService

            collect_result = ScanCollectGenerateService.generate(
                execution,
                eligible_ids,
                operator=operator,
                request=request,
            )
        return {
            **write_result,
            "collect": collect_result,
            "created": collect_result.get("created", 0),
            "appended": collect_result.get("appended", 0),
        }
