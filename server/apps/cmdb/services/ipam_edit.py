# -- coding: utf-8 --
"""IP 视图手工登记：分配状态 / IP 类型 / 使用人 / IP 状态 / MAC / 描述。空闲不落库。"""
from apps.cmdb.utils.ipam_cidr import ip_in_subnet, parse_subnet
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.core.logger import cmdb_logger as logger

ALLOC_AVAILABLE = "available"

ACTION_CREATE = "create"
ACTION_UPDATE = "update"
ACTION_DELETE = "delete"
ACTION_NOOP = "noop"

ACTION_PERMISSION = {
    ACTION_CREATE: "asset_info-Add",
    ACTION_UPDATE: "asset_info-Edit",
    ACTION_DELETE: "asset_info-Delete",
}


class IpamEditError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def first_enum(value):
    if isinstance(value, list):
        return value[0] if value else None
    if value in (None, ""):
        return None
    return value


def as_id_list(value) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)]


def enum_list(value, default=None) -> list | None:
    status = first_enum(value)
    if not status:
        return default
    return [str(status)]


def normalize_allocated_status(value) -> str:
    status = first_enum(value)
    if not status:
        raise IpamEditError("分配状态不能为空")
    return str(status)


def build_editable_ip_attrs(
    *,
    allocated_status: str,
    ip_status=None,
    ip_type=None,
    ip_user=None,
    mac=None,
    description=None,
    for_create: bool = False,
) -> dict:
    """只写入 IP 视图允许编辑的字段。"""
    attrs = {
        "ip_allocated_status": [allocated_status],
        "auto_collect": False,
        "ip_type": enum_list(ip_type, []),
        "ip_user": as_id_list(ip_user),
        "mac": "" if mac is None else str(mac),
        "description": "" if description is None else str(description),
    }
    status = enum_list(ip_status, ["unknown"] if for_create else None)
    if status is not None:
        attrs["ip_status"] = status
    return attrs


def decide_manual_ip_action(existing, allocated_status: str) -> str:
    """可分配且无实例 → noop；可分配且已落库 → 删除；其余按是否已有实例创建或更新。"""
    allocated_status = normalize_allocated_status(allocated_status)
    if allocated_status == ALLOC_AVAILABLE:
        return ACTION_DELETE if existing else ACTION_NOOP
    return ACTION_UPDATE if existing else ACTION_CREATE


def required_asset_permission(action: str):
    return ACTION_PERMISSION.get(action)


def find_ip_in_subnet(ips: list, ip_addr: str):
    target = str(ip_addr or "").strip()
    for row in ips or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("ip_addr") or "").strip() == target:
            return row
    return None


def validate_ip_belongs_to_subnet(ip_addr: str, subnet: dict) -> None:
    addr = str(ip_addr or "").strip()
    if not addr:
        raise IpamEditError("IP 地址不能为空")
    try:
        net = parse_subnet(subnet.get("subnet_address"), subnet.get("subnet_mask"))
    except BaseAppException as exc:
        raise IpamEditError(str(exc)) from exc
    if not ip_in_subnet(addr, net):
        raise IpamEditError("IP 不属于当前子网")
    import ipaddress

    try:
        parsed = ipaddress.ip_address(addr)
    except (ValueError, TypeError) as exc:
        raise IpamEditError("非法 IP 地址") from exc
    if net.num_addresses > 2 and parsed in (net.network_address, net.broadcast_address):
        raise IpamEditError("不能登记网络号或广播地址")


def user_has_asset_permission(user, permission: str) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    perms = getattr(user, "permission", {}) or {}
    if isinstance(perms, dict):
        return permission in (perms.get("cmdb") or set())
    return permission in perms


def execute_manual_ip_action(
    *,
    action: str,
    subnet: dict,
    existing: dict | None,
    ip_addr: str,
    allocated_status: str,
    operator: str,
    allowed_org_ids: list | None,
    user_groups: list,
    roles: list,
    ip_status=None,
    ip_type=None,
    ip_user=None,
    mac=None,
    description: str = "",
) -> dict:
    """执行已鉴权的手工登记。调用方必须先完成菜单权限与实例 Operate 校验。"""
    from apps.cmdb.services.instance import InstanceManage

    allocated_status = normalize_allocated_status(allocated_status)
    subnet_id = subnet.get("_id")
    organization = subnet.get("organization") or []
    editable = build_editable_ip_attrs(
        allocated_status=allocated_status,
        ip_status=ip_status,
        ip_type=ip_type,
        ip_user=ip_user,
        mac=mac,
        description=description,
        for_create=action == ACTION_CREATE,
    )

    if action == ACTION_NOOP:
        return {"action": ACTION_NOOP, "ip": None}

    if action == ACTION_CREATE:
        created = InstanceManage.instance_create(
            "ip",
            {
                "ip_addr": ip_addr,
                "inst_name": ip_addr,
                "subnet_id": str(subnet_id),
                "organization": organization,
                **editable,
            },
            operator,
            allowed_org_ids=allowed_org_ids,
        )
        try:
            _require_subnet_ip_association(subnet_id, created["_id"])
        except Exception:
            inst_uuid = created.get("inst_uuid")
            if inst_uuid:
                try:
                    InstanceManage.instance_batch_delete_by_uuids(user_groups, roles, [inst_uuid], operator)
                except Exception:
                    logger.exception(
                        "[IPAM] 手工登记关联失败后回滚 IP 失败 subnet_id=%s ip_id=%s",
                        subnet_id,
                        created.get("_id"),
                    )
            raise
        _safe_writeback(subnet_id)
        return {"action": ACTION_CREATE, "ip": created}

    if action == ACTION_UPDATE:
        if not existing:
            raise IpamEditError("IP 实例不存在")
        updated = InstanceManage.instance_update(
            user_groups,
            roles,
            existing["_id"],
            {
                **editable,
                "subnet_id": str(subnet_id),
            },
            operator,
            allowed_org_ids=allowed_org_ids,
        )
        _require_subnet_ip_association(subnet_id, existing["_id"])
        return {"action": ACTION_UPDATE, "ip": updated}

    if action == ACTION_DELETE:
        if not existing:
            return {"action": ACTION_NOOP, "ip": None}
        inst_uuid = existing.get("inst_uuid")
        if not inst_uuid:
            raise IpamEditError("IP 实例缺少 inst_uuid，无法解除")
        InstanceManage.instance_batch_delete_by_uuids(user_groups, roles, [inst_uuid], operator)
        _safe_writeback(subnet_id)
        return {"action": ACTION_DELETE, "ip": None}

    raise IpamEditError(f"未知操作: {action}")


def _require_subnet_ip_association(subnet_id, ip_id) -> None:
    from apps.cmdb.services.ipam_discovery import _ensure_subnet_ip_association

    result = _ensure_subnet_ip_association(subnet_id, ip_id) or {}
    failed = result.get("failed") or []
    if not failed:
        return
    first = failed[0]
    detail = first.get("error") if isinstance(first, dict) else first
    raise IpamEditError(str(detail) or "无法建立子网与 IP 的关联")


def _safe_writeback(subnet_id):
    from apps.cmdb.services.ipam_reconcile import _writeback_subnet_utilization

    try:
        _writeback_subnet_utilization([subnet_id])
    except Exception:
        logger.exception("[IPAM] 手工登记后回写子网利用率失败 subnet_id=%s", subnet_id)
