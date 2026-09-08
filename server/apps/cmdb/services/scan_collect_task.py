"""扫描生成的采集任务：建表、同族复用、凭据合并、认领 CI。

ScanCollectGenerateService 只负责勾选行分组；落库细节都在这里。
"""

from __future__ import annotations

from rest_framework.request import Request

from apps.cmdb.constants.constants import INSTANCE, CollectInputMethod, DataCleanupStrategy
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.collect_model import CollectModels, normalize_topology_contract
from apps.cmdb.models.scan_model import ScanHit, scan_driver_type_for_model, scan_task_type_for_model
from apps.cmdb.services.collect_credential_pool_service import CollectCredentialPoolService
from apps.cmdb.services.collect_service import CollectModelService
from apps.cmdb.services.instance import InstanceManage
from apps.cmdb.services.scan_host_cloud import host_cloud_from_scan
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

SCAN_SOURCE_PARAM = "generated_from_scan_task_id"
# Influx 一个端点一张任务；网络/主机/常规库按族合并。
SINGLE_ENDPOINT_FAMILIES = frozenset({"influxdb"})
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


def uses_single_endpoint(family_model_id: str) -> bool:
    return family_model_id in SINGLE_ENDPOINT_FAMILIES


def collect_params(scan_task, family_model_id: str) -> dict:
    params = {SCAN_SOURCE_PARAM: scan_task.id}
    if family_model_id == "network":
        # 与手建 SNMP 表单默认一致：默认采集网络关系。
        params.update(normalize_topology_contract({"has_network_topo": True}))
    if family_model_id == "host":
        params.update(host_cloud_from_scan(scan_task))
    return params


def _form_defaults(family_model_id: str) -> dict:
    return _COLLECT_FORM_DEFAULTS.get(
        family_model_id,
        {"timeout": _DEFAULT_TIMEOUT, "cycle_minutes": _DEFAULT_CYCLE_MINUTES},
    )


def normalize_scan_credential_item(family_model_id: str, credential_item: dict) -> dict:
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


def merge_instance_payloads(existing, incoming) -> list:
    by_uuid = {}
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        inst_uuid = str(item.get("inst_uuid") or "").strip()
        if not inst_uuid:
            continue
        by_uuid[inst_uuid] = {
            "inst_uuid": inst_uuid,
            "model_id": item.get("model_id") or by_uuid.get(inst_uuid, {}).get("model_id") or "",
        }
    return list(by_uuid.values())


def merge_credential_items(family_model_id: str, existing, incoming) -> list:
    pool = []
    seen = set()
    for item in list(existing or []) + list(incoming or []):
        if not isinstance(item, dict):
            continue
        normalized = normalize_scan_credential_item(family_model_id, item)
        cred_id = str(normalized.get("credential_id") or "")
        if not cred_id or cred_id in seen:
            continue
        seen.add(cred_id)
        pool.append(normalized)
    return CollectCredentialPoolService.normalize_pool(pool)


def _unique_task_name(base: str) -> str:
    name = base[:120]
    if not CollectModels.objects.filter(name=name).exists():
        return name
    for idx in range(2, 100):
        candidate = f"{base[:110]}-{idx}"
        if not CollectModels.objects.filter(name=candidate).exists():
            return candidate
    return f"{base[:100]}-{ScanHit.objects.count()}"


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


def require_request(request):
    if request is None:
        raise BaseAppException("生成采集需要请求上下文")
    if not isinstance(request, Request):
        return Request(request)
    return request


def _build_create_payload(*, scan_task, family_model_id: str, credential_items: list, name: str, instances: list | None = None) -> dict:
    defaults = _form_defaults(family_model_id)
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
        # 扫描生成必须走 instances，禁止 ip_range，否则采集会按段重扫。
        "ip_range": "",
        "instances": list(instances or []),
        "credential": CollectCredentialPoolService.normalize_pool(
            [normalize_scan_credential_item(family_model_id, item) for item in credential_items]
        ),
        "params": collect_params(scan_task, family_model_id),
        "data_cleanup_strategy": DataCleanupStrategy.NO_CLEANUP,
        "expire_days": 0,
    }


def _build_update_payload(collect: CollectModels, *, instances: list | None = None, params=None, credentials=None) -> dict:
    if not isinstance(params, dict):
        params = collect.params if isinstance(collect.params, dict) else {}
    pool = credentials if credentials is not None else collect.decrypt_credentials
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
        "ip_range": "",
        "instances": list(instances if instances is not None else (collect.instances or [])),
        "credential": CollectCredentialPoolService.normalize_pool(pool),
        "params": params,
        "data_cleanup_strategy": collect.data_cleanup_strategy,
        "expire_days": collect.expire_days or 0,
    }


def _first_instance_uuid(collect: CollectModels) -> str:
    items = collect.instances or []
    if isinstance(items, list) and items and isinstance(items[0], dict):
        return str(items[0].get("inst_uuid") or "")
    return ""


def find_scan_generated_collect(scan_task, family_model_id: str, inst_uuid: str | None = None) -> CollectModels | None:
    """只匹配本扫描生成的同族任务，避免改到手建采集。"""
    qs = CollectModels.objects.filter(is_system=False, model_id=family_model_id)
    marked = list(qs.filter(params__contains={SCAN_SOURCE_PARAM: scan_task.id}))
    if not marked:
        name_prefix = f"{scan_task.name}-{family_model_id}"
        marked = list(qs.filter(name__startswith=name_prefix))
    for collect in marked:
        if uses_single_endpoint(family_model_id) and inst_uuid:
            if _first_instance_uuid(collect) != str(inst_uuid):
                continue
        return collect
    return None


def collect_holding_instance(inst_uuid: str) -> CollectModels | None:
    """CI 是否已被采集占用：先看图属性 collect_task，再按 instances 精确匹配。

    网络/主机 IP 段任务 instances 为空，contains 不会误扫全表。
    """
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
    return (
        CollectModels.objects.filter(
            is_system=False,
            instances__contains=[{"inst_uuid": inst_uuid}],
        )
        .only("id", "instances")
        .first()
    )


def claim_collect_instances(collect: CollectModels, inst_uuids: list[str]) -> None:
    """把已写入的 CI 认领到这张采集任务。

    采集执行按 collect_task 对账。扫描落库时该属性是 family_run.id，
    不认领则自动模式会把已有 CI 当新增，撞 inst_name 唯一约束。
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


def create_scan_collect_task(
    *,
    scan_task,
    family_model_id: str,
    credential_items: list,
    request,
    instances: list | None = None,
    host: str = "",
    port: int = 0,
) -> CollectModels:
    request = require_request(request)
    name_parts = [scan_task.name, family_model_id]
    if uses_single_endpoint(family_model_id):
        if host:
            name_parts.append(str(host).strip())
        if port:
            name_parts.append(str(port))
    name = _unique_task_name("-".join(part for part in name_parts if part))
    payload = _build_create_payload(
        scan_task=scan_task,
        family_model_id=family_model_id,
        credential_items=credential_items,
        name=name,
        instances=instances,
    )
    view = _collect_view(request, action="create")
    collect_id = CollectModelService.create(request, view, payload=payload, credential_pool_max_size=None)
    return CollectModels.objects.get(pk=collect_id)


def sync_scan_collect_task(
    collect: CollectModels,
    *,
    scan_task,
    instances: list | None,
    credentials: list | None,
    request,
) -> CollectModels:
    params = collect.params if isinstance(collect.params, dict) else {}
    if collect.model_id == "host":
        params = {**params, **collect_params(scan_task, "host")}
    merged_instances = merge_instance_payloads(collect.instances, instances)
    merged_credentials = merge_credential_items(collect.model_id, collect.decrypt_credentials, credentials)
    existing_uuids = {str(item.get("inst_uuid") or "") for item in (collect.instances or []) if isinstance(item, dict)}
    incoming_uuids = {str(item.get("inst_uuid") or "") for item in (instances or []) if isinstance(item, dict)}
    existing_creds = {str(item.get("credential_id") or "") for item in (collect.decrypt_credentials or []) if isinstance(item, dict)}
    incoming_creds = {str(item.get("credential_id") or "") for item in (credentials or []) if isinstance(item, dict)}
    needs_auto = collect.input_method != CollectInputMethod.AUTO
    needs_params = params != (collect.params if isinstance(collect.params, dict) else {})
    needs_instances = not incoming_uuids.issubset(existing_uuids)
    needs_creds = not incoming_creds.issubset(existing_creds)
    if not needs_auto and not needs_params and not needs_instances and not needs_creds:
        return collect
    request = require_request(request)
    payload = _build_update_payload(
        collect,
        instances=merged_instances,
        params=params,
        credentials=merged_credentials,
    )
    view = _collect_view(request, action="update", pk=collect.id)
    collect_id = CollectModelService.update(request, view, payload=payload, credential_pool_max_size=None)
    return CollectModels.objects.get(pk=collect_id)
