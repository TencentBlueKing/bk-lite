"""扫描命中 → 显式带凭据推送到监控（经 CMDB→Monitor IoC，不直连监控内部）。"""

from __future__ import annotations

from apps.cmdb.models.scan_model import ScanExecution, ScanHit, resolve_scan_task_credential
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.module_push import CmdbToMonitorPushService, build_cmdb_push_actor_scope
from apps.core.logger import cmdb_logger as logger

_NETWORK_MODELS = frozenset({"switch", "router", "firewall", "loadbalance"})
_DB_MODELS = frozenset({"mysql", "postgresql", "mssql", "influxdb"})


def _resolve_credential_item(task, family_model_id: str, credential_id: str) -> dict | None:
    return resolve_scan_task_credential(task, family_model_id, credential_id)


def _attach_cloud_region(instance: dict, scan_task) -> None:
    """扫描任务上的云区域补到 CI raw，便于 Host 身份 / Remote 选节点。"""
    if instance.get("cloud_region_id") not in (None, "") or instance.get("cloud") not in (None, ""):
        return
    region = getattr(scan_task, "cloud_region", None)
    if not region:
        return
    if isinstance(region, dict):
        cloud = region.get("id")
        if cloud in (None, ""):
            cloud = region.get("cloud_region_id", region.get("cloud"))
        cloud_name = region.get("name") or region.get("cloud_region_name") or region.get("cloud_name") or ""
    elif isinstance(region, int):
        cloud, cloud_name = region, ""
    else:
        text = str(region).strip()
        if not text:
            return
        cloud, cloud_name = (int(text), "") if text.isdigit() else (None, text)
    if cloud not in (None, ""):
        instance["cloud"] = cloud
        instance["cloud_region_id"] = cloud
    if cloud_name:
        instance["cloud_name"] = cloud_name
        instance["cloud_region_name"] = cloud_name


def _enrich_instance_for_push(instance: dict, hit: ScanHit, scan_task) -> dict:
    """补齐扫描侧已知字段，供 module_push 写入 raw（监控内部自行映射）。"""
    merged = dict(instance)
    model_id = str(hit.cmdb_model_id or instance.get("model_id") or hit.family_run.model_id or "").strip()
    if model_id:
        merged["model_id"] = model_id
        merged["object_type"] = model_id
        if model_id in _NETWORK_MODELS:
            merged["device_type"] = model_id
    if not merged.get("ip") and not merged.get("ip_addr"):
        merged["ip"] = hit.host
        merged["ip_addr"] = hit.host
    if hit.port and not merged.get("port") and not merged.get("snmp_port"):
        if model_id in _NETWORK_MODELS or hit.family_run.model_id == "network":
            merged["snmp_port"] = hit.port
            merged["port"] = hit.port
        else:
            merged["port"] = hit.port
    _attach_cloud_region(merged, scan_task)
    return merged


def _lookup_instance_by_ip(model_id: str, host: str, port=None) -> dict | None:
    """扫描 hit 上的 inst_uuid 可能已被后续采集 upsert 换掉，按模型+IP（库再加端口）找回现网 CI。"""
    if not model_id or not host:
        return None
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    filters = [
        {"field": "model_id", "type": "str=", "value": model_id},
        {"field": "ip_addr", "type": "str=", "value": host},
    ]
    if port not in (None, "") and model_id in _DB_MODELS:
        try:
            filters.append({"field": "port", "type": "int=", "value": int(port)})
        except (TypeError, ValueError):
            pass
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, filters)
    for row in rows or []:
        if isinstance(row, dict) and row.get("_id") is not None:
            return row
    return None


def _resolve_graph_instance(hit: ScanHit) -> dict | None:
    if hit.inst_uuid:
        rows = InstanceManage.query_entity_by_uuids([hit.inst_uuid]) or []
        instance = next(
            (row for row in rows if isinstance(row, dict) and row.get("inst_uuid") == hit.inst_uuid),
            None,
        )
        if instance is not None:
            return instance
    model_id = str(hit.cmdb_model_id or "").strip()
    if not model_id or model_id == "network":
        return None
    return _lookup_instance_by_ip(model_id, hit.host, hit.port)


def _actor_context_from_request(request):
    if request is None:
        return None
    try:
        from apps.monitor.views.node_mgmt import _build_actor_context

        return _build_actor_context(request)
    except Exception:
        logger.info("[ScanPushMonitor] 无法从请求构造 actor_context，按内部创建路径推送")
        return None


class ScanPushMonitorService:
    """扫描清单勾选 → CmdbToMonitorPushService.push_with_credential → Monitor.ingest_from_source。

    不直连 MonitorModuleIngestService；重复推送的幂等由监控侧 skipped 回传。
    """

    @classmethod
    def push(cls, execution: ScanExecution, hit_ids: list[int], *, request=None, operator: str = "") -> dict:
        actor_scope = (
            build_cmdb_push_actor_scope(request)
            if request is not None
            else {
                "allowed_org_ids": list(execution.task.team or []),
                "operator": operator or "",
            }
        )
        if not actor_scope.get("allowed_org_ids") and execution.task.team:
            actor_scope["allowed_org_ids"] = [int(x) for x in execution.task.team if str(x).isdigit() or isinstance(x, int)]
        operator = actor_scope.get("operator") or operator or ""
        actor_context = _actor_context_from_request(request)

        hits = list(
            ScanHit.objects.filter(
                execution=execution,
                id__in=hit_ids,
                status=ScanHit.STATUS_SUCCESS,
            ).select_related("family_run", "execution__task")
        )
        scan_task = execution.task
        results = []

        for hit in hits:
            family_model_id = hit.family_run.model_id
            credential_id = str(hit.credential_id or "").strip()
            item = {
                "hit_id": hit.id,
                "host": hit.host,
                "credential_id": credential_id,
                "family": family_model_id,
                "cmdb_model_id": hit.cmdb_model_id,
            }

            # network 未识别 soid：先拦，避免空 uuid 被误报成 no_ci。
            if family_model_id == "network" and not hit.cmdb_model_id:
                item.update({"status": "skipped", "reason": "unknown_soid"})
                results.append(item)
                continue
            if not credential_id:
                item.update({"status": "skipped", "reason": "no_credential"})
                results.append(item)
                continue

            credential = _resolve_credential_item(scan_task, family_model_id, credential_id)
            if not credential:
                item.update({"status": "failed", "reason": "credential_not_found"})
                results.append(item)
                continue

            # hit.inst_uuid 可能为空或过期：按 uuid → 模型+IP 找回 CI（主机常见未回写 uuid）。
            instance = _resolve_graph_instance(hit)
            if instance is None:
                item.update(
                    {
                        "status": "skipped" if not hit.inst_uuid else "failed",
                        "reason": "no_ci" if not hit.inst_uuid else "ci_not_found",
                    }
                )
                results.append(item)
                continue
            live_uuid = str(instance.get("inst_uuid") or hit.inst_uuid or "").strip()
            if live_uuid and live_uuid != hit.inst_uuid:
                hit.inst_uuid = live_uuid
                hit.save(update_fields=["inst_uuid", "updated_at"])

            org_ids = actor_scope.get("allowed_org_ids") or []
            if not org_ids:
                item.update({"status": "failed", "reason": "no_org_scope"})
                results.append(item)
                continue

            push_instance = _enrich_instance_for_push(instance, hit, scan_task)
            try:
                push_result = CmdbToMonitorPushService.push_with_credential(
                    push_instance,
                    # _client_id 由 module_push 统一剥离，此处不再二次拷贝。
                    credential=credential,
                    actor_scope=actor_scope,
                    actor_context=actor_context,
                )
                result = push_result.get("monitor_result") or {}
                if result.get("collect_error"):
                    item.update({"status": "failed", "reason": result["collect_error"], "monitor_result": result})
                elif result.get("skipped"):
                    item.update(
                        {
                            "status": "skipped",
                            "reason": "already_in_monitor",
                            "monitor_result": result,
                        }
                    )
                elif result.get("ignored"):
                    # 带凭据推送期望建采；ignored 不是「可跳过」，而是链路未落库（常见：远端 NATS 抢答）。
                    item.update({"status": "failed", "reason": "ingest_ignored", "monitor_result": result})
                elif result.get("created") or result.get("updated") or result.get("id"):
                    item.update({"status": "pushed", "monitor_result": result})
                else:
                    item.update({"status": "failed", "reason": "ingest_empty", "monitor_result": result})
            except Exception as exc:
                logger.exception("[ScanPushMonitor] 推送失败 hit=%s host=%s", hit.id, hit.host)
                item.update({"status": "failed", "reason": str(exc)})
            results.append(item)

        pushed = sum(1 for row in results if row.get("status") == "pushed")
        skipped = sum(1 for row in results if row.get("status") == "skipped")
        failed = sum(1 for row in results if row.get("status") == "failed")
        return {
            "execution_id": execution.id,
            "pushed": pushed,
            "skipped": skipped,
            "failed": failed,
            "items": results,
        }
