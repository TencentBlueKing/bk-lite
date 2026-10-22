"""网络发现未识别 SOID：补特征库，或按已有映射写入勾选设备。"""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from apps.cmdb.collection.collect_plugin.network import CollectNetworkMetrics
from apps.cmdb.collection.common import Management
from apps.cmdb.constants.constants import INSTANCE, CollectRunStatusType
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.collect_model import OidMapping
from apps.cmdb.services.scan_identity import NETWORK_CI_TYPES
from apps.core.exceptions.base_app_exception import ForbiddenException, ValidationAppException

_WRITABLE_STATUSES = frozenset({CollectRunStatusType.SUCCESS, CollectRunStatusType.PARTIAL_SUCCESS})
_SOID_ADD = "soid_library-Add"


def user_can_add_soid(user) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    permissions = getattr(user, "permission", None)
    if isinstance(permissions, dict):
        names = permissions.get("cmdb", set())
    elif isinstance(permissions, set):
        names = permissions
    else:
        names = set()
    if isinstance(names, (list, tuple)):
        names = set(names)
    return _SOID_ADD in names


def save_unknown_soid_mappings(task, user, items):
    _ensure_task_ready(task, user)
    pending = _normalize_items(task, items)
    created = []
    skipped = []
    with transaction.atomic():
        existing = {row.oid: row for row in OidMapping.objects.filter(oid__in=[item["soid"] for item in pending])}
        for item in pending:
            row = existing.get(item["soid"])
            if row is not None:
                skipped.append(_mapping_payload(row))
                continue
            row = OidMapping.objects.create(
                oid=item["soid"],
                device_type=item["device_type"],
                brand=item["brand"],
                model=item["model"],
                built_in=False,
            )
            created.append(_mapping_payload(row))
    return {"created": created, "skipped": skipped}


def write_unknown_devices(task, user, ip_addrs, *, ingest=None):
    _ensure_task_ready(task, user)
    selected = _selected_devices(task, ip_addrs)
    library = {row.oid: row for row in OidMapping.objects.filter(oid__in=sorted({soid for soid, _device in selected}))}
    missing = sorted({soid for soid, _device in selected if soid not in library})
    if missing:
        raise ValidationAppException("存在未补全映射的 SOID，不能写入", data={"missing_soids": missing})

    rows_by_model = {}
    for soid, device in selected:
        row = library[soid]
        ip_addr = str(device.get("ip_addr") or "")
        inst_name = "{}-{}".format(ip_addr, row.device_type)
        rows_by_model.setdefault(row.device_type, []).append(
            {
                "inst_name": inst_name,
                "ip_addr": ip_addr,
                "soid": row.oid,
                "port": str(device.get("port") or ""),
                "model": row.model or "",
                "brand": row.brand or "",
                "sys_desc": device.get("sys_desc") or "",
                "model_id": row.device_type,
            }
        )
        interfaces = device.get("interfaces") if isinstance(device.get("interfaces"), list) else []
        for interface in interfaces:
            if not isinstance(interface, dict):
                continue
            name = interface.get("name") or ""
            rows_by_model.setdefault("interface", []).append(
                {
                    "inst_name": "{}-{}".format(inst_name, name),
                    "self_device": inst_name,
                    "mac": interface.get("mac") or "",
                    "name": name,
                    "description": interface.get("description") or "",
                    "status": interface.get("status") or "",
                    "model_id": "interface",
                    "assos": [
                        {
                            "model_id": row.device_type,
                            "inst_name": inst_name,
                            "asst_id": "belong",
                            "model_asst_id": "interface_belong_{}".format(row.device_type),
                        }
                    ],
                }
            )

    writer = ingest or ingest_network_rows
    ordered = {model_id: rows_by_model[model_id] for model_id in list(NETWORK_CI_TYPES) + ["interface"] if model_id in rows_by_model}
    result = writer(task, ordered)
    if _ingest_failed(result):
        raise ValidationAppException("写入模型失败", data={"result": result})

    written_ips = {str(device.get("ip_addr") or "") for _soid, device in selected}
    format_data = dict(task.format_data or {})
    format_data["unresolved"] = _drop_ips(format_data.get("unresolved") or [], written_ips)
    task.format_data = format_data
    task.save(update_fields=["format_data"])
    return {"written": sorted(written_ips)}


def ingest_network_rows(task, rows_by_model):
    """按实例名对账后写入。只把本次行当作旧数据范围，避免清掉同任务的其他设备。"""
    results = {}
    collect_time = datetime.now(timezone.utc).isoformat()
    with GraphClient() as client:
        for model_id, rows in rows_by_model.items():
            names = [row["inst_name"] for row in rows if row.get("inst_name")]
            already = []
            for start in range(0, len(names), 200):
                found, _total = client.query_entity(
                    INSTANCE,
                    [
                        {"field": "model_id", "type": "str=", "value": model_id},
                        {"field": "inst_name", "type": "str[]", "value": names[start : start + 200]},
                    ],
                )
                already.extend(found)
            management = Management(
                task.team or [],
                "",
                model_id,
                already,
                rows,
                ["inst_name"],
                collect_time,
                task.id,
                reconcile_task_assets=True,
                expire_days=getattr(task, "expire_days", 0) or 0,
            )
            results[model_id] = management.controller()
    return results


def _ensure_task_ready(task, user):
    if not user_can_add_soid(user):
        raise ForbiddenException("没有特征库新增权限")
    if getattr(task, "model_id", None) != "network":
        raise ValidationAppException("只有网络发现任务可以处理未识别设备")
    if getattr(task, "exec_status", None) not in _WRITABLE_STATUSES:
        raise ValidationAppException("任务尚未成功，不能处理未识别设备")


def _normalize_items(task, items):
    if not isinstance(items, list) or not items:
        raise ValidationAppException("请提交要补全的 SOID")
    known = _unresolved_soids(task)
    pending = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValidationAppException("映射行格式不正确")
        soid = CollectNetworkMetrics.normalize_sysobjectid(item.get("soid"))
        device_type = str(item.get("device_type") or "").strip()
        brand = str(item.get("brand") or "").strip()
        model = str(item.get("model") or "").strip()
        if soid not in known:
            raise ValidationAppException("SOID 不在当前未识别结果里", data={"soid": soid})
        if device_type not in NETWORK_CI_TYPES:
            raise ValidationAppException("设备类型必须是交换机、路由器、防火墙或负载均衡")
        if not brand or not model:
            raise ValidationAppException("品牌和型号不能为空")
        if soid in seen:
            continue
        seen.add(soid)
        pending.append({"soid": soid, "device_type": device_type, "brand": brand, "model": model})
    return pending


def _selected_devices(task, ip_addrs):
    if not isinstance(ip_addrs, list) or not ip_addrs:
        raise ValidationAppException("请选择要写入的设备")
    by_ip = {}
    for soid, device in _iter_devices(task):
        ip_addr = str(device.get("ip_addr") or "")
        if ip_addr and ip_addr not in by_ip:
            by_ip[ip_addr] = (soid, device)
    missing_ips = [str(ip) for ip in ip_addrs if str(ip) not in by_ip]
    if missing_ips:
        raise ValidationAppException("所选设备不在当前未识别结果里", data={"ip_addrs": missing_ips})
    selected = []
    seen = set()
    for ip_addr in ip_addrs:
        ip_addr = str(ip_addr)
        if ip_addr in seen:
            continue
        seen.add(ip_addr)
        selected.append(by_ip[ip_addr])
    return selected


def _unresolved_soids(task):
    return {soid for soid, _device in _iter_devices(task)}


def _iter_devices(task):
    groups = (task.format_data or {}).get("unresolved") or []
    if not isinstance(groups, list):
        return
    for group in groups:
        if not isinstance(group, dict):
            continue
        soid = CollectNetworkMetrics.normalize_sysobjectid(group.get("soid"))
        devices = group.get("devices") if isinstance(group.get("devices"), list) else []
        for device in devices:
            if isinstance(device, dict):
                yield soid, device


def _drop_ips(groups, ip_addrs):
    kept = []
    if not isinstance(groups, list):
        return kept
    for group in groups:
        if not isinstance(group, dict):
            continue
        devices = []
        for device in group.get("devices") or []:
            if not isinstance(device, dict):
                continue
            if str(device.get("ip_addr") or "") in ip_addrs:
                continue
            devices.append(device)
        if devices:
            kept.append({"soid": group.get("soid") or "", "devices": devices})
    return kept


def _mapping_payload(row):
    return {
        "soid": row.oid,
        "device_type": row.device_type,
        "brand": row.brand or "",
        "model": row.model or "",
    }


def _ingest_failed(result):
    if not isinstance(result, dict):
        return False
    for model_result in result.values():
        if not isinstance(model_result, dict):
            continue
        for operator in ("add", "update"):
            failed = (model_result.get(operator) or {}).get("failed") or []
            if failed:
                return True
    return False
