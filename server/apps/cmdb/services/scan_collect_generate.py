"""扫描命中 → 生成单凭据采集任务。"""

from __future__ import annotations

from django.db import transaction
from rest_framework.request import Request

from apps.cmdb.constants.constants import INSTANCE, CollectInputMethod, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.collect_model import CollectModels, normalize_topology_contract
from apps.cmdb.models.collect_task_credential_hit import CollectTaskCredentialHit
from apps.cmdb.models.scan_model import ScanExecution, ScanHit, resolve_scan_task_credential, scan_driver_type_for_model, scan_task_type_for_model
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.scan_shot import join_ip_ranges
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

_SCAN_SOURCE_PARAM = "generated_from_scan_task_id"
# 与专业采集表单初始值对齐（Beat 周期，不是 Telegraf scrape interval）。
_COLLECT_FORM_DEFAULTS = {
    "network": {"timeout": 5, "cycle_minutes": 30},
    "host": {"timeout": 20, "cycle_minutes": 30},
    "physcial_server": {"timeout": 20, "cycle_minutes": 30},
    "mysql": {"timeout": 20, "cycle_minutes": 30},
    "postgresql": {"timeout": 20, "cycle_minutes": 30},
    "mssql": {"timeout": 20, "cycle_minutes": 30},
    "influxdb": {"timeout": 20, "cycle_minutes": 30},
}
_DEFAULT_TIMEOUT = 60
_DEFAULT_CYCLE_MINUTES = 30
_V3_ONLY_FIELDS = ("username", "level", "integrity", "authkey", "privacy", "privkey")
_INFLUX_ALLOWED_FIELDS = ("credential_id", "scheme", "port", "verify_tls", "token", "password")
_SINGLE_ENDPOINT_FAMILIES = frozenset({"influxdb"})


def _uses_single_endpoint(family_model_id: str) -> bool:
    return family_model_id in _SINGLE_ENDPOINT_FAMILIES


def _host_cloud_from_scan(scan_task) -> dict:
    region = getattr(scan_task, "cloud_region", None)
    if not region:
        return {}
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
            return {}
        cloud, cloud_name = (int(text), "") if text.isdigit() else (None, text)
    params = {}
    if cloud not in (None, ""):
        params["cloud"] = cloud
    if cloud_name:
        params["cloud_name"] = cloud_name
    return params


def _collect_params(scan_task, family_model_id: str) -> dict:
    params = {_SCAN_SOURCE_PARAM: scan_task.id}
    if family_model_id == "network":
        # 与手建 SNMP 任务表单默认一致：默认采集网络关系。
        params.update(normalize_topology_contract({"has_network_topo": True}))
    if family_model_id == "host":
        params.update(_host_cloud_from_scan(scan_task))
    return params


def _form_defaults(family_model_id: str) -> dict:
    return _COLLECT_FORM_DEFAULTS.get(
        family_model_id,
        {"timeout": _DEFAULT_TIMEOUT, "cycle_minutes": _DEFAULT_CYCLE_MINUTES},
    )


def _ipv4(value: str):
    parts = str(value or "").strip().split(".")
    if len(parts) != 4:
        return None
    try:
        octets = [int(part) for part in parts]
    except ValueError:
        return None
    if any(part < 0 or part > 255 for part in octets):
        return None
    return (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]


def _range_contains(item: dict, host: str) -> bool:
    ip = _ipv4(host)
    begin = _ipv4(str(item.get("begin") or ""))
    end = _ipv4(str(item.get("end") or ""))
    if ip is None or begin is None or end is None:
        return False
    low, high = (begin, end) if begin <= end else (end, begin)
    return low <= ip <= high


def _ip_range_from_scan(scan_task, hosts: list[str] | None = None) -> str:
    """采集任务的 ip_range 直接用扫描任务上的起止段，形状与手建 296 一致。"""
    ranges = [item for item in (scan_task.ip_ranges or []) if isinstance(item, dict)]
    matched = []
    seen = set()
    for item in ranges:
        begin = str(item.get("begin") or "").strip()
        end = str(item.get("end") or "").strip()
        key = (begin, end)
        if not begin or not end or key in seen:
            continue
        if hosts and not any(_range_contains(item, host) for host in hosts):
            continue
        seen.add(key)
        matched.append(item)
    ip_range = join_ip_ranges(matched or ranges)
    if not ip_range:
        raise BaseAppException("扫描任务没有 IP 段，无法生成采集")
    return ip_range


def _union_ip_range(existing: str, incoming: str) -> str:
    parts = []
    seen = set()
    for part in f"{existing},{incoming}".split(","):
        value = part.strip()
        if not value or value in seen or "-" not in value:
            continue
        begin, _sep, end = value.partition("-")
        if _ipv4(begin) is None or _ipv4(end) is None:
            continue
        seen.add(value)
        parts.append(value)
    return ",".join(parts)


def _successful_credential_hit_task_id(host: str, credential_id: str) -> int | None:
    return (
        CollectTaskCredentialHit.objects.filter(
            object_key=f"host:{host}",
            credential_id=credential_id,
            status=CollectTaskCredentialHit.STATUS_SUCCESS,
        )
        .values_list("task_id", flat=True)
        .first()
    )


def _resolve_credential_item(task, family_model_id: str, credential_id: str) -> dict | None:
    return resolve_scan_task_credential(task, family_model_id, credential_id)


def _unique_task_name(base: str) -> str:
    name = base[:120]
    if not CollectModels.objects.filter(name=name).exists():
        return name
    for idx in range(2, 100):
        candidate = f"{base[:110]}-{idx}"
        if not CollectModels.objects.filter(name=candidate).exists():
            return candidate
    return f"{base[:100]}-{ScanHit.objects.count()}"


def _normalize_credential_item(family_model_id: str, credential_item: dict) -> dict:
    item = dict(credential_item)
    if family_model_id == "influxdb":
        return _normalize_influxdb_credential(item)
    if family_model_id != "network":
        return item
    version = str(item.get("version") or "v2").strip() or "v2"
    normalized = {
        "version": version,
        "snmp_port": item.get("snmp_port") or "161",
    }
    if item.get("credential_id"):
        normalized["credential_id"] = item["credential_id"]
    if version.lower() == "v3":
        for key in _V3_ONLY_FIELDS:
            if item.get(key) not in (None, ""):
                normalized[key] = item[key]
        return normalized
    if item.get("community"):
        normalized["community"] = item["community"]
    return normalized


def _normalize_influxdb_credential(item: dict) -> dict:
    scheme = str(item.get("scheme") or ("https" if item.get("ssl") else "http")).strip().lower() or "http"
    try:
        port = int(item.get("port", 8086))
    except (TypeError, ValueError):
        port = 8086
    verify_tls = item.get("verify_tls", True)
    normalized = {
        "scheme": scheme,
        "port": port,
        "verify_tls": verify_tls if isinstance(verify_tls, bool) else True,
    }
    if item.get("credential_id"):
        normalized["credential_id"] = item["credential_id"]
    for key in ("token", "password"):
        if item.get(key) not in (None, ""):
            normalized[key] = item[key]
    return {key: value for key, value in normalized.items() if key in _INFLUX_ALLOWED_FIELDS}


def _collect_view(request, *, action: str, pk=None):
    from apps.cmdb.views.collect import CollectModelViewSet

    view = CollectModelViewSet()
    kwargs = {"pk": pk} if pk is not None else {}
    view.request = request
    view.args = ()
    view.kwargs = kwargs
    view.action = action
    view.format_kwarg = None
    return view


def _build_create_payload(
    *,
    scan_task,
    family_model_id: str,
    credential_item: dict,
    ip_range: str,
    name: str,
    instances: list | None = None,
) -> dict:
    defaults = _form_defaults(family_model_id)
    if _uses_single_endpoint(family_model_id):
        payload_ip_range = ""
        payload_instances = list(instances or [])
    else:
        # 必须做成手建 IP 段任务：instances 为空，plugin 查找才走 task.model_id=network。
        # 挂交换机实例会让线上旧 format_params 用 model_id=switch 查插件并失败。
        payload_ip_range = ip_range
        payload_instances = []
    return {
        "name": name,
        "task_type": scan_task_type_for_model(family_model_id),
        "driver_type": scan_driver_type_for_model(family_model_id),
        "model_id": family_model_id,
        "timeout": defaults["timeout"],
        "input_method": CollectInputMethod.AUTO,
        "scan_cycle": {"value_type": "cycle", "value": str(defaults["cycle_minutes"])},
        "team": list(scan_task.team or []),
        "access_point": list(scan_task.access_point or []),
        "ip_range": payload_ip_range,
        "instances": payload_instances,
        "credential": CollectCredentialPoolService.normalize_pool([_normalize_credential_item(family_model_id, credential_item)]),
        "params": _collect_params(scan_task, family_model_id),
        "data_cleanup_strategy": DataCleanupStrategy.NO_CLEANUP,
        "expire_days": 0,
    }


def _build_update_payload(collect: CollectModels, *, ip_range: str, instances: list | None = None, params=None) -> dict:
    if _uses_single_endpoint(collect.model_id):
        payload_ip_range = ""
        payload_instances = list(instances if instances is not None else (collect.instances or []))
    else:
        payload_ip_range = ip_range
        payload_instances = []
    if not isinstance(params, dict):
        params = collect.params if isinstance(collect.params, dict) else {}
    return {
        "name": collect.name,
        "task_type": collect.task_type,
        "driver_type": collect.driver_type,
        "model_id": collect.model_id,
        "timeout": collect.timeout,
        "input_method": CollectInputMethod.AUTO,
        "scan_cycle": {
            "value_type": collect.cycle_value_type or "cycle",
            "value": collect.cycle_value or str(_form_defaults(collect.model_id)["cycle_minutes"]),
        },
        "team": list(collect.team or []),
        "access_point": list(collect.access_point or []) if isinstance(collect.access_point, list) else collect.access_point,
        "ip_range": payload_ip_range,
        "instances": payload_instances,
        "credential": CollectCredentialPoolService.normalize_pool(collect.decrypt_credentials),
        "params": params,
        "data_cleanup_strategy": collect.data_cleanup_strategy,
        "expire_days": collect.expire_days or 0,
    }


def _require_request(request):
    if request is None:
        raise BaseAppException("生成采集需要请求上下文")
    if not isinstance(request, Request):
        return Request(request)
    return request


def _create_collect_task(
    *,
    scan_task,
    family_model_id: str,
    credential_item: dict,
    ip_range: str,
    request,
    instances: list | None = None,
    host: str = "",
    port: int = 0,
) -> CollectModels:
    request = _require_request(request)
    cred_id = str(credential_item.get("credential_id") or "cred")[:8]
    name_parts = [scan_task.name, family_model_id, cred_id]
    if _uses_single_endpoint(family_model_id):
        if host:
            name_parts.append(str(host).strip())
        if port:
            name_parts.append(str(port))
    name = _unique_task_name("-".join(part for part in name_parts if part))
    payload = _build_create_payload(
        scan_task=scan_task,
        family_model_id=family_model_id,
        credential_item=credential_item,
        ip_range=ip_range,
        name=name,
        instances=instances,
    )
    view = _collect_view(request, action="create")
    collect_id = CollectModelService.create(request, view, payload=payload)
    return CollectModels.objects.get(pk=collect_id)


def _pool_has_credential(collect: CollectModels, credential_id: str) -> bool:
    pool = collect.decrypt_credentials or []
    if isinstance(pool, dict):
        pool = [pool]
    return any(isinstance(item, dict) and str(item.get("credential_id") or "") == credential_id for item in pool)


def _first_instance_uuid(collect: CollectModels) -> str:
    items = collect.instances or []
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return str(items[0].get("inst_uuid") or "")
    return ""


def _find_scan_generated_collect(
    scan_task,
    family_model_id: str,
    credential_id: str,
    inst_uuid: str | None = None,
) -> CollectModels | None:
    """只匹配本扫描生成的任务，避免误改手建采集。

    优先 params.generated_from_scan_task_id；名称前缀仅作旧数据兜底。
    """
    qs = CollectModels.objects.filter(is_system=False, model_id=family_model_id)
    marked = list(qs.filter(params__contains={_SCAN_SOURCE_PARAM: scan_task.id}))
    if marked:
        candidates = marked
    else:
        # 旧任务可能没有 params 标记，用命名约定兜底（限 name__startswith，不扫全表）。
        cred_prefix = str(credential_id or "cred")[:8]
        name_prefix = f"{scan_task.name}-{family_model_id}-{cred_prefix}"
        candidates = list(qs.filter(name__startswith=name_prefix))
    for collect in candidates:
        if _uses_single_endpoint(family_model_id) and inst_uuid:
            if _first_instance_uuid(collect) != str(inst_uuid):
                continue
        if _pool_has_credential(collect, credential_id):
            return collect
    return None


def _collect_holding_instance(inst_uuid: str) -> CollectModels | None:
    """查 CI 是否已被某张采集任务占用。先看图上 collect_task，再按 instances 精确匹配。"""
    if not inst_uuid:
        return None
    rows = InstanceManage.query_entity_by_uuids([inst_uuid]) or []
    row = next((item for item in rows if isinstance(item, dict)), None)
    if row is not None:
        raw_id = row.get("collect_task")
        if raw_id not in (None, ""):
            try:
                found = CollectModels.objects.filter(pk=int(raw_id), is_system=False).first()
            except (TypeError, ValueError):
                found = None
            if found is not None:
                return found
    # Influx 等把端点挂在 instances；网络/主机 IP 段任务 instances 为空，不会误扫全表。
    return (
        CollectModels.objects.filter(
            is_system=False,
            instances__contains=[{"inst_uuid": inst_uuid}],
        )
        .only("id", "instances")
        .first()
    )


def _claim_instances(collect: CollectModels, inst_uuids: list[str]) -> None:
    """把扫描已写入的 CI 认领到这张采集任务上。

    采集执行（线上旧代码）按 collect_task 对账。扫描落库时 collect_task 是 family_run.id，
    不认领则自动模式会把已有 CI 当成新增，撞 inst_name 唯一约束。
    网络 / 主机 / 库的 IP 段任务不往 instances 里挂 CI；InfluxDB 必须挂恰好一个端点。
    """
    uuids = []
    seen = set()
    for raw in inst_uuids or []:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        uuids.append(value)
    if not uuids:
        return
    rows = InstanceManage.query_entity_by_uuids(uuids) or []
    entity_ids = [row["_id"] for row in rows if isinstance(row, dict) and row.get("_id") is not None]
    if not entity_ids:
        logger.warning(
            "[ScanCollectGenerate] 认领采集任务未找到图实例 collect=%s uuids=%s",
            collect.id,
            uuids,
        )
        return
    with GraphClient() as ag:
        ag.set_entity_properties(
            INSTANCE,
            entity_ids,
            {"collect_task": str(collect.id)},
            {},
            [],
            check=False,
        )


def _sync_existing_collect(
    collect: CollectModels,
    *,
    scan_task,
    ip_range: str,
    instances: list | None,
    request,
) -> CollectModels:
    params = collect.params if isinstance(collect.params, dict) else {}
    if collect.model_id == "host":
        params = {**params, **_collect_params(scan_task, "host")}
    needs_auto = collect.input_method != CollectInputMethod.AUTO
    needs_params = params != (collect.params if isinstance(collect.params, dict) else {})
    if _uses_single_endpoint(collect.model_id):
        needs_range = False
    else:
        needs_range = (collect.ip_range or "") != ip_range
    if not needs_auto and not needs_range and not needs_params:
        return collect
    request = _require_request(request)
    payload = _build_update_payload(collect, ip_range=ip_range, instances=instances, params=params)
    view = _collect_view(request, action="update", pk=collect.id)
    collect_id = CollectModelService.update(request, view, payload=payload)
    return CollectModels.objects.get(pk=collect_id)


class ScanCollectGenerateService:
    @classmethod
    def generate(cls, execution: ScanExecution, hit_ids: list[int], *, operator: str = "", request=None) -> dict:
        hits = list(
            ScanHit.objects.filter(
                execution=execution,
                id__in=hit_ids,
                status=ScanHit.STATUS_SUCCESS,
            ).select_related("family_run", "execution__task")
        )
        scan_task = execution.task
        results = []
        groups: dict[tuple[str, str, str], dict] = {}
        # 批量校验 hit 上回写的 collect_task_id，避免循环内逐条 exists。
        recorded_task_ids = {int(hit.collect_task_id) for hit in hits if hit.collect_task_id not in (None, "")}
        live_task_ids = (
            set(CollectModels.objects.filter(pk__in=recorded_task_ids, is_system=False).values_list("pk", flat=True)) if recorded_task_ids else set()
        )

        for hit in hits:
            family_model_id = hit.family_run.model_id
            credential_id = str(hit.credential_id or "").strip()
            host = str(hit.host or "").strip()
            item = {
                "hit_id": hit.id,
                "host": host,
                "credential_id": credential_id,
                "family": family_model_id,
            }

            if not hit.inst_uuid:
                item.update({"status": "skipped", "reason": "no_ci"})
                results.append(item)
                continue
            if not credential_id:
                item.update({"status": "skipped", "reason": "no_credential"})
                results.append(item)
                continue
            # 幂等：已生成过且任务仍在 → 跳过（重复点击）。
            if hit.collect_task_id:
                if hit.collect_task_id in live_task_ids:
                    item.update(
                        {
                            "status": "skipped",
                            "reason": "already_generated",
                            "collect_task_id": hit.collect_task_id,
                        }
                    )
                    results.append(item)
                    continue
                # 任务已被删：清掉脏引用，允许重新生成。
                hit.collect_task_id = None
                hit.save(update_fields=["collect_task_id", "updated_at"])
            holding = _collect_holding_instance(hit.inst_uuid)
            if holding is not None:
                existing_holder = _find_scan_generated_collect(
                    scan_task,
                    family_model_id,
                    credential_id,
                    inst_uuid=hit.inst_uuid,
                )
                if existing_holder is not None and existing_holder.id == holding.id:
                    # 旧数据未回写 collect_task_id：补写后同样跳过。
                    if hit.collect_task_id != holding.id:
                        hit.collect_task_id = holding.id
                        hit.save(update_fields=["collect_task_id", "updated_at"])
                        live_task_ids.add(holding.id)
                    item.update(
                        {
                            "status": "skipped",
                            "reason": "already_generated",
                            "collect_task_id": holding.id,
                        }
                    )
                    results.append(item)
                    continue
                # 已被其它采集任务占用，不抢。
                item.update({"status": "skipped", "reason": "already_on_collect"})
                results.append(item)
                continue
            hit_task_id = _successful_credential_hit_task_id(host, credential_id)
            if hit_task_id is not None:
                existing_for_hit = _find_scan_generated_collect(
                    scan_task,
                    family_model_id,
                    credential_id,
                    inst_uuid=hit.inst_uuid,
                )
                # 别的采集任务已经采过：不要再建。本扫描生成的任务已采过：仍要认领 CI。
                if existing_for_hit is None or existing_for_hit.id != hit_task_id:
                    item.update({"status": "skipped", "reason": "credential_already_hit"})
                    results.append(item)
                    continue

            credential_item = _resolve_credential_item(scan_task, family_model_id, credential_id)
            if not credential_item:
                item.update({"status": "failed", "reason": "credential_not_found"})
                results.append(item)
                continue

            group_inst = hit.inst_uuid if _uses_single_endpoint(family_model_id) else ""
            group = groups.setdefault(
                (family_model_id, credential_id, group_inst),
                {
                    "family_model_id": family_model_id,
                    "credential_id": credential_id,
                    "credential_item": credential_item,
                    "hosts": [],
                    "inst_uuids": [],
                    "instances": [],
                    "host": host,
                    "port": hit.port or 0,
                    "items": [],
                },
            )
            group["hosts"].append(host)
            group["inst_uuids"].append(hit.inst_uuid)
            if _uses_single_endpoint(family_model_id) and not group["instances"]:
                group["instances"] = [
                    {
                        "inst_uuid": hit.inst_uuid,
                        "model_id": hit.cmdb_model_id or family_model_id,
                    }
                ]
            group["items"].append(item)

        for group in groups.values():
            existing = _find_scan_generated_collect(
                scan_task,
                group["family_model_id"],
                group["credential_id"],
                inst_uuid=group["inst_uuids"][0] if _uses_single_endpoint(group["family_model_id"]) else None,
            )
            try:
                with transaction.atomic():
                    if _uses_single_endpoint(group["family_model_id"]):
                        ip_range = ""
                    else:
                        ip_range = _ip_range_from_scan(scan_task, group["hosts"])
                    if existing is not None:
                        if ip_range:
                            ip_range = _union_ip_range(existing.ip_range or "", ip_range)
                        collect = _sync_existing_collect(
                            existing,
                            scan_task=scan_task,
                            ip_range=ip_range,
                            instances=group["instances"] or None,
                            request=request,
                        )
                        status = "appended"
                    else:
                        collect = _create_collect_task(
                            scan_task=scan_task,
                            family_model_id=group["family_model_id"],
                            credential_item=group["credential_item"],
                            ip_range=ip_range,
                            request=request,
                            instances=group["instances"] or None,
                            host=group["host"],
                            port=group["port"],
                        )
                        status = "created"
                    _claim_instances(collect, group["inst_uuids"])
                for index, item in enumerate(group["items"]):
                    item_status = status
                    if status == "created" and index > 0:
                        item_status = "appended"
                    item.update(
                        {
                            "status": item_status,
                            "collect_task_id": collect.id,
                            "collect_task_name": collect.name,
                        }
                    )
                    results.append(item)
                hit_ids_in_group = [row["hit_id"] for row in group["items"] if row.get("hit_id")]
                if hit_ids_in_group:
                    ScanHit.objects.filter(id__in=hit_ids_in_group).update(collect_task_id=collect.id)
            except Exception as exc:
                logger.exception(
                    "[ScanCollectGenerate] 生成失败 family=%s credential=%s",
                    group["family_model_id"],
                    group["credential_id"],
                )
                for item in group["items"]:
                    item.update({"status": "failed", "reason": str(exc)})
                    results.append(item)

        created = sum(1 for row in results if row.get("status") == "created")
        appended = sum(1 for row in results if row.get("status") == "appended")
        skipped = sum(1 for row in results if row.get("status") == "skipped")
        failed = sum(1 for row in results if row.get("status") == "failed")
        return {
            "execution_id": execution.id,
            "created": created,
            "appended": appended,
            "skipped": skipped,
            "failed": failed,
            "items": results,
        }
