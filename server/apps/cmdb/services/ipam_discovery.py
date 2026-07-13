# -- coding: utf-8 --
"""IP 发现采集 server 端:子网参数提取、VM 指标落库、IPAM 台账回写。"""
from datetime import datetime

from apps.cmdb.constants.constants import INSTANCE
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger


def _empty_summary(**extra) -> dict:
    return {
        "created": 0,
        "updated": 0,
        "offline": 0,
        "failed": 0,
        "format_data": {"add": [], "update": [], "delete": [], "association": [], "all": 0},
        **extra,
    }


def extract_subnet_discovery_params(task) -> tuple:
    """从采集任务 model 实例或 dict 中提取 (subnet_ids, scan_method, ports)。"""
    if hasattr(task, "instances"):
        raw_instances = task.instances
        raw_params = getattr(task, "params", {}) or {}
    else:
        raw_instances = task.get("instances", {})
        raw_params = task.get("params", {}) or {}

    if not isinstance(raw_instances, dict):
        raw_instances = {}
    if not isinstance(raw_params, dict):
        raw_params = {}

    raw_instances = {**raw_instances, **raw_params}

    subnet_ids = raw_instances.get("subnet_ids", [])
    if not isinstance(subnet_ids, list):
        subnet_ids = list(subnet_ids) if subnet_ids else []

    scan_method = raw_instances.get("scan_method", "icmp") or "icmp"
    ports = raw_instances.get("ports", None)
    if ports is not None and not isinstance(ports, list):
        ports = list(ports)

    return subnet_ids, scan_method, ports


def _load_subnets_by_ids(subnet_ids: list) -> list:
    ids = []
    for item in subnet_ids or []:
        if isinstance(item, bool):
            continue
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            logger.warning("[IPDiscovery] 忽略非法 subnet_id=%r", item)
    if not ids:
        return []
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "subnet"},
            {"field": "id", "type": "id[]", "value": ids}])
    return rows or []


# ---------------------------------------------------------------------------
# 回写层:apply_discovery_result / apply_ip_discovery_vm_rows
# ---------------------------------------------------------------------------

def _dedupe_ip_rows(rows: list) -> list:
    result = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        identity = row.get("_id") or (row.get("subnet_id"), row.get("ip_addr"))
        if identity in seen:
            continue
        seen.add(identity)
        result.append(row)
    return result


def _load_subnet_ips_by_field(subnet_id) -> list:
    """兼容旧数据:按 subnet_id 字段查询某子网下所有 IP 记录。"""
    with GraphClient() as ag:
        rows, _ = ag.query_entity(INSTANCE, [
            {"field": "model_id", "type": "str=", "value": "ip"},
            {"field": "subnet_id", "type": "str=", "value": str(subnet_id)},
        ])
    return rows or []


def _load_subnet_associated_ips(subnet_id) -> list:
    """按 subnet_group_ip 关联查询子网下的 IP。"""
    from apps.cmdb.services.instance import InstanceManage

    associations = InstanceManage.instance_association_instance_list("subnet", int(subnet_id)) or []
    rows = []
    for item in associations:
        if item.get("model_asst_id") != "subnet_group_ip":
            continue
        rows.extend(item.get("inst_list") or [])
    return rows


def _load_subnet_ips(subnet_id) -> list:
    """查询某子网下所有 IP 记录(关联优先,字段兜底兼容历史数据)。"""
    return _dedupe_ip_rows(_load_subnet_associated_ips(subnet_id) + _load_subnet_ips_by_field(subnet_id))


def _ensure_subnet_ip_association(subnet_id, ip_id) -> dict:
    """确保 subnet --group--> ip 关联存在；重复关联视为成功幂等。"""
    from apps.cmdb.services.instance import InstanceManage

    data = {
        "src_inst_id": int(subnet_id),
        "dst_inst_id": int(ip_id),
        "asst_id": "group",
        "src_model_id": "subnet",
        "dst_model_id": "ip",
        "model_asst_id": "subnet_group_ip",
    }
    try:
        InstanceManage.instance_association_create(data, "system")
        return {"success": [data], "failed": []}
    except BaseAppException as exc:
        message = getattr(exc, "message", "") or str(exc)
        if "repetition" in message:
            return {"success": [data], "failed": []}
        error_data = dict(data)
        error_data["error"] = message
        return {"success": [], "failed": [error_data]}


# ---------------------------------------------------------------------------
# 系统写公共 helper,周期任务写台账用,跳过权限校验 + 不记变更日志
# ---------------------------------------------------------------------------

def _system_create_or_update(model_id: str, instance_info: dict, existing_id=None, organization=None) -> dict:
    """已有 _id 走 update,否则 create。统一走 system 操作员 + 跳过权限校验。"""
    from apps.cmdb.services.instance import InstanceManage

    if existing_id:
        InstanceManage.instance_update(
            [], [], existing_id, instance_info, "system",
            skip_permission_check=True,
            allowed_org_ids=organization or [],
            record_change=False,
        )
        return {"_id": existing_id, **instance_info}
    created = InstanceManage.instance_create(
        model_id,
        instance_info,
        "system",
        allowed_org_ids=organization or [],
        record_change=False,
    )
    return {"_id": created["_id"], **instance_info}


def _system_update(instance_id, instance_info: dict) -> None:
    """更新单条实例。"""
    from apps.cmdb.services.instance import InstanceManage

    InstanceManage.instance_update(
        [], [], instance_id, instance_info, "system",
        skip_permission_check=True, record_change=False,
    )


def _upsert_alive_ip(existing_id=None, subnet_id=None, ip_addr=None, mac="", organization=None):
    """创建或更新在线 IP 记录。subnet_id 以字符串写入,保证查询一致性。"""
    payload = {
        "ip_addr": ip_addr,
        "inst_name": ip_addr,
        "subnet_id": str(subnet_id),
        "ip_status": ["online"],
        "auto_collect": True,
        "mac": mac,
        "organization": organization or [],
        "collect_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    saved = _system_create_or_update("ip", payload, existing_id=existing_id, organization=organization)
    ip_id = saved["_id"]
    payload_with_id = {**payload, "_id": ip_id, "model_id": "ip"}
    assos_result = _ensure_subnet_ip_association(subnet_id, ip_id)
    return {"_id": ip_id, "inst_info": payload_with_id, "assos_result": assos_result}


def _mark_offline(ip_id):
    """将单条自动发现 IP 置为离线,不影响手工记录。"""
    _system_update(ip_id, {"ip_status": ["offline"]})


def _writeback_subnet_utilization(subnet_ids):
    """重算子网利用率统计(复用 P1 同款 helper,保持口径一致)。"""
    from apps.cmdb.services.ipam_reconcile import _writeback_subnet_utilization as wb

    wb(set(subnet_ids))


def apply_discovery_result(subnet_id, alive: list) -> dict:
    """活跃 IP 回写台账。规格 §13.4。"""
    subnet_rows = _load_subnets_by_ids([subnet_id])
    if not subnet_rows:
        logger.warning("[IPDiscovery] 子网不存在,跳过 subnet_id=%s alive_count=%s", subnet_id, len(alive))
        return _empty_summary(skipped=True)
    organization = subnet_rows[0].get("organization") or []
    if not organization:
        logger.warning("[IPDiscovery] 子网 %s 缺少 organization,ip 模型要求必填,跳过", subnet_id)
        return _empty_summary(skipped=True)

    existing = _load_subnet_ips(subnet_id)
    existing_by_addr = {i.get("ip_addr"): i for i in existing}
    alive_addrs = {a["ip"] for a in alive}

    created = updated = offline = failed = 0
    format_data = {"add": [], "update": [], "delete": [], "association": [], "all": 0}
    for item in alive:
        prev = existing_by_addr.get(item["ip"])
        if prev and prev.get("auto_collect") is not True:
            # 手工录入不被自动发现覆盖(仅 auto_collect is True 的记录归发现采集所有、可写)
            continue
        try:
            upsert_result = _upsert_alive_ip(
                existing_id=(prev or {}).get("_id"),
                subnet_id=subnet_id,
                ip_addr=item["ip"],
                mac=item.get("mac", ""),
                organization=organization,
            ) or {}
        except Exception as err:
            failed += 1
            logger.warning(
                "[IPDiscovery] upsert IP 失败 subnet_id=%s ip=%s err=%s,继续处理其他 IP",
                subnet_id, item["ip"], err,
            )
            continue

        upsert_inst_info = upsert_result.get("inst_info") or {
            "_id": (prev or {}).get("_id"),
            "model_id": "ip",
            "inst_name": item["ip"],
            "ip_addr": item["ip"],
            "subnet_id": str(subnet_id),
            "ip_status": ["online"],
            "auto_collect": True,
            "mac": item.get("mac", ""),
            "organization": organization,
        }
        if upsert_result.get("assos_result"):
            for status, rows in upsert_result["assos_result"].items():
                for row in rows:
                    format_data["association"].append({**row, "_status": status})
        if prev:
            updated += 1
            format_data["update"].append({"_status": "success", **upsert_inst_info})
        else:
            created += 1
            format_data["add"].append({"_status": "success", **upsert_inst_info})

    for ip in existing:
        if ip.get("auto_collect") is True and ip.get("ip_addr") not in alive_addrs:
            try:
                _mark_offline(ip["_id"])
            except Exception as err:
                failed += 1
                logger.warning(
                    "[IPDiscovery] mark_offline 失败 subnet_id=%s ip_id=%s err=%s,继续处理其他 IP",
                    subnet_id, ip["_id"], err,
                )
                continue
            offline += 1
            format_data["update"].append({
                "_status": "success",
                "_id": ip["_id"],
                "model_id": "ip",
                "inst_name": ip.get("inst_name") or ip.get("ip_addr"),
                "ip_addr": ip.get("ip_addr"),
                "subnet_id": str(subnet_id),
                "ip_status": ["offline"],
                "auto_collect": True,
            })

    _writeback_subnet_utilization([subnet_id])
    format_data["all"] = len(format_data["add"]) + len(format_data["update"]) + len(format_data["delete"])
    return {
        "created": created,
        "updated": updated,
        "offline": offline,
        "failed": failed,
        "format_data": format_data,
    }


def apply_ip_discovery_vm_rows(task, rows: list[dict]) -> dict:
    """把 VM 中的 ip_info 指标行回写到 IPAM 台账。"""
    selected_subnet_ids, _, _ = extract_subnet_discovery_params(task)
    selected_subnet_ids = [str(item) for item in selected_subnet_ids]
    if not selected_subnet_ids:
        logger.warning("[IPDiscovery] 任务未勾选子网,跳过 VM 指标处理,行数=%s", len(rows or []))
        return _empty_summary()

    alive_by_subnet: dict[str, list[dict]] = {}
    for row in rows or []:
        if row.get("collect_status", "success") == "failed":
            continue
        subnet_id = str(row.get("subnet_id") or "").strip()
        ip_addr = str(row.get("ip_addr") or row.get("ip") or "").strip()
        if not subnet_id or not ip_addr:
            continue
        if subnet_id not in selected_subnet_ids:
            continue
        alive_by_subnet.setdefault(subnet_id, []).append(
            {"ip": ip_addr, "mac": row.get("mac", "")}
        )

    summary = _empty_summary()
    for subnet_id in selected_subnet_ids:
        result = apply_discovery_result(subnet_id, alive_by_subnet.get(subnet_id, []))
        for key in ("created", "updated", "offline", "failed"):
            summary[key] += int(result.get(key, 0))
        result_format_data = result.get("format_data") or {}
        for key in ("add", "update", "delete", "association"):
            summary["format_data"][key].extend(result_format_data.get(key) or [])
        summary["format_data"]["all"] += int(result_format_data.get("all", 0) or 0)
    return summary
