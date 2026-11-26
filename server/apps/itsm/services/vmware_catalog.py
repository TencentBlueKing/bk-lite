"""仅发布管理员批准的 VMware 资源快照，真实作业还须向对应 VC 复核。"""

import ipaddress
import re

from apps.core.backends import _normalize_group_ids
from apps.itsm.models import ItsmSetting, Service
from apps.itsm.services.notify.recipients import active_users

PROFILE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$"
KINDS = ("flavor", "template", "network", "disk_policy")
DEMO_CONFIG = {
    "max_quantity": 5,
    "catalog": {
        "flavor": [
            {"value": "small", "label": "标准型 · 2 vCPU / 4 GiB", "cpu": 2, "memory_gib": 4},
            {"value": "medium", "label": "标准型 · 4 vCPU / 8 GiB", "cpu": 4, "memory_gib": 8},
        ],
        "template": [{"value": "vm-demo-ubuntu", "label": "Ubuntu Server · 演示模板"}],
        "network": [{"value": "network-demo", "label": "开发网络 · DHCP"}],
        "disk_policy": [{"value": "standard", "label": "标准数据盘", "datastore_id": "datastore-demo", "allowed_disk_gib": [0, 20, 40, 80]}],
    },
}


def _key(profile):
    if not isinstance(profile, str) or not re.fullmatch(PROFILE_PATTERN, profile):
        raise ValueError("交付环境标识无效")
    return f"vmware_profile_{profile}"


def _integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def _validate_config(config, demo):
    keys = {"catalog", "max_quantity"} if demo else {"catalog", "max_quantity", "vc_instance_uuid", "vc_host", "target_id"}
    if not isinstance(config, dict) or set(config) != keys or not _integer(config["max_quantity"], 1, 100):
        raise ValueError("请填写有效的目录、单次交付上限和目标绑定")
    catalog = config["catalog"]
    if not isinstance(catalog, dict) or set(catalog) != set(KINDS):
        raise ValueError("请配置规格、模板、网络及磁盘策略目录")
    extras = {"flavor": {"cpu", "memory_gib"}, "disk_policy": {"allowed_disk_gib", "datastore_id"}}
    for kind, rows in catalog.items():
        if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
            raise ValueError("每类目录须包含 1 至 500 项")
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"value", "label"} | extras.get(kind, set()):
                raise ValueError("目录项字段无效")
            if not all(isinstance(row[k], str) and row[k].strip() and len(row[k]) <= 200 for k in ("label", "value")) or row["value"] in seen:
                raise ValueError("目录项名称和标识必填，标识不能重复")
            seen.add(row["value"])
            if kind == "flavor" and not (_integer(row["cpu"], 1, 1024) and _integer(row["memory_gib"], 1, 65536)):
                raise ValueError("规格须包含有效的 CPU 和内存")
            if kind == "disk_policy":
                sizes = row["allowed_disk_gib"]
                if not isinstance(row["datastore_id"], str) or not row["datastore_id"].strip():
                    raise ValueError("磁盘策略须指定数据存储")
                if (
                    not isinstance(sizes, list)
                    or not 1 <= len(sizes) <= 100
                    or not all(_integer(v, 0, 65536) for v in sizes)
                    or len(set(sizes)) != len(sizes)
                ):
                    raise ValueError("数据盘容量列表无效")


def _check_target(target_id, team_id, domain):
    from apps.job_mgmt.models import Target

    if (
        not _integer(target_id, 1, 2**63 - 1)
        or not Target.objects.filter(pk=target_id, domain=domain, os_type="linux", team_memberships__team_id=team_id).exists()
    ):
        raise ValueError("请选择本组织可用的 Linux 作业执行机")


def _hostname(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("vCenter 地址不能为空")
    value = value.strip().rstrip(".")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        host = value.encode("idna").decode("ascii").lower()
        if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", s) for s in host.split(".")):
            raise ValueError("vCenter 地址无效") from None
        return host


def _check_vcenter(instance_uuid, team_id, expected_host):
    from apps.cmdb.constants.constants import INSTANCE
    from apps.cmdb.graph.drivers.graph_client import GraphClient

    if not isinstance(instance_uuid, str) or not 1 <= len(instance_uuid) <= 128:
        raise ValueError("请选择本组织的 CMDB vCenter")
    with GraphClient() as graph:
        roots, _ = graph.query_entity(
            INSTANCE,
            [
                {"field": "model_id", "type": "str=", "value": "vmware_vc"},
                {"field": "inst_uuid", "type": "str=", "value": instance_uuid},
                {"field": "organization", "type": "list[]", "value": [team_id]},
            ],
            page={"skip": 0, "limit": 2},
            fields=["inst_uuid", "ip_addr"],
            include_count=False,
        )
    if len(roots) != 1:
        raise ValueError("请选择本组织的 CMDB vCenter")
    host = _hostname(roots[0].get("ip_addr"))
    if host != _hostname(expected_host):
        raise ValueError("目录的 vCenter 地址与 CMDB 根资产不一致")
    return host


def _bind(profile, service, team_id, config, *, demo):
    if type(team_id) is not int or _normalize_group_ids(service.team) != {team_id}:
        raise ValueError("交付服务须绑定对应组织")
    _validate_config(config, demo)
    if not demo:
        _check_target(config["target_id"], team_id, service.domain)
        _check_vcenter(config["vc_instance_uuid"], team_id, config["vc_host"])
    value = {**config, "service_id": service.pk}
    setting, created = ItsmSetting.objects.get_or_create(
        domain=service.domain,
        key=_key(profile),
        defaults={"value": value, "team": [team_id], "created_by": service.created_by, "updated_by": service.updated_by},
    )
    if not created and (setting.value != value or setting.team != [team_id]):
        raise ValueError("此交付环境已绑定其他目录、服务或组织")
    return setting


def install_demo_catalog(service, team_id):
    return _bind("demo", service, team_id, DEMO_CONFIG, demo=True)


def bind_catalog(profile, service, team_id, config):
    if profile == "demo":
        raise ValueError("demo 标识专用于本地演示")
    return _bind(profile, service, team_id, config, demo=False)


def _scoped_profile(profile, domain, teams, *, allow_unbound=False):
    setting = ItsmSetting.objects.filter(key=_key(profile), domain=domain).first()
    if not setting and allow_unbound:
        for team_id in _normalize_group_ids(teams):
            if Service.objects.filter(
                domain=domain, workflow__domain=domain, workflow__key=f"vmware_{profile}_{team_id}", team=[team_id], is_enabled=False
            ).exists():
                return None, team_id
    owners = _normalize_group_ids(setting.team) if setting else set()
    if len(owners) != 1 or not owners.intersection(_normalize_group_ids(teams)):
        raise PermissionError("无权访问该交付环境")
    return setting, owners.pop()


def catalog_options(profile, kind, domain, teams, disk_policy_id=None, keyword="", page=1, *, preview=False):
    setting, _ = _scoped_profile(profile, domain, teams, allow_unbound=True)
    if not setting and not preview:
        return {"items": [], "has_more": False}
    config = setting.value if setting else DEMO_CONFIG
    catalog = config["catalog"]
    if kind == "disk_size":
        allowed = next((r["allowed_disk_gib"] for r in catalog["disk_policy"] if r["value"] == disk_policy_id), [])
        rows = [{"label": f"{v} GiB" if v else "无需数据盘", "value": v} for v in allowed]
    elif kind == "quantity":
        rows = [{"label": f"{v} 台", "value": v} for v in range(1, config["max_quantity"] + 1)]
    elif kind in KINDS:
        keys = ("value", "label", "cpu", "memory_gib") if kind == "flavor" else ("value", "label")
        rows = [{k: r[k] for k in keys} for r in catalog[kind]]
    else:
        raise ValueError("目录类型无效")
    if setting is None:
        rows = [{**row, "label": f"示例（尚未绑定目录）· {row['label']}"} for row in rows]
    if keyword:
        rows = [r for r in rows if keyword.casefold() in f"{r['label']} {r['value']}".casefold()]
    start = (page - 1) * 20
    return {"items": rows[start : start + 20], "has_more": len(rows) > start + 20}


def provision_profile(version):
    if version is None:
        return None
    profiles = [
        (node.get("auto") or {}).get("profile")
        for node in (version.design or {}).get("nodes", [])
        if (node.get("auto") or {}).get("kind") == "vmware_provision"
    ]
    if not profiles:
        return None
    if any(not isinstance(item, str) or item != profiles[0] for item in profiles) or not profiles[0]:
        raise ValueError("流程的 VMware 交付环境不明确")
    return profiles[0]


def request_table(version):
    fields = {f["key"]: f for f in (version.design.get("form_schema") or {}).get("fields", [])}
    if not version.is_published:
        raise ValueError("VMware 交付需要已发布的流程版本")
    if "vm_requests" in fields:
        if fields["vm_requests"].get("type") != "table":
            raise ValueError("虚拟机配置必须使用明细表")
        return "vm_requests"
    if {f"{k}_id" for k in KINDS} | {"quantity", "data_disk_gib"} <= fields.keys():
        return None
    raise ValueError("流程版本缺少 VMware 申请表单快照")


def _request_config(profile, version, service, creator, team):
    if service is None or service.domain != version.domain or service.workflow_id != version.workflow_id or not service.is_enabled:
        raise PermissionError("工单缺少有效的交付服务")
    setting, team_id = _scoped_profile(profile, version.domain, service.team)
    user = active_users(version.domain).filter(username=creator).first()
    if setting.value["service_id"] != service.pk or not user or team_id not in _normalize_group_ids(user.group_list):
        raise PermissionError("工单或申请人无权使用该交付环境")
    if team and team_id not in _normalize_group_ids(team):
        raise PermissionError("工单组织与交付环境不匹配")
    if service.visibility != "all":
        from types import SimpleNamespace

        from apps.itsm.services.service_access import visible_services

        if not visible_services(SimpleNamespace(user=user), service_id=service.pk).exists():
            raise PermissionError("申请人无权访问该交付服务")
    if profile != "demo":
        group = service.handler_group
        if group is None or group.domain != version.domain or (group.team and team_id not in _normalize_group_ids(group.team)):
            raise PermissionError("运维审批组与交付服务不匹配")
    return setting.value, team_id


def _machines(config, data, table):
    if table:
        rows = data.get(table)
        if not isinstance(rows, list) or not 1 <= len(rows) <= config["max_quantity"]:
            raise ValueError(f"虚拟机明细须包含 1 至 {config['max_quantity']} 台")
    else:
        count = data.get("quantity")
        if not _integer(count, 1, config["max_quantity"]):
            raise ValueError("申请数量超出允许范围")
        rows = [data] * count
    catalog = {kind: {item["value"]: item for item in config["catalog"][kind]} for kind in KINDS}
    machines = []
    labels = {}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise TypeError(f"虚拟机第 {index} 行格式错误")
        machine = {}
        for kind in KINDS:
            key = f"{kind}_id"
            value = row.get(key)
            option = catalog[kind].get(value) if isinstance(value, str) else None
            if not option:
                raise ValueError(f"虚拟机第 {index} 行选用了无效的 VMware 资源")
            labels.setdefault(key, {})[value] = option["label"]
            if kind == "flavor":
                machine.update(cpu=option["cpu"], memory_gib=option["memory_gib"])
            else:
                machine[key] = value
        size = row.get("data_disk_gib")
        policy = catalog["disk_policy"][machine["disk_policy_id"]]
        if type(size) is not int or size not in policy["allowed_disk_gib"]:
            raise ValueError(f"虚拟机第 {index} 行的数据盘容量不符合所选策略")
        machine["data_disk_gib"] = size
        labels.setdefault("data_disk_gib", {})[size] = f"{size} GiB" if size else "无需数据盘"
        machines.append(machine)
    public_labels = (
        {f"{table}.{key}": [{"value": value, "label": label} for value, label in options.items()] for key, options in labels.items()} if table else {}
    )
    return machines, public_labels


def validate_requests(profile, version, service, creator, form_data, team=None):
    config, _ = _request_config(profile, version, service, creator, team)
    table = request_table(version)
    try:
        _, labels = _machines(config, form_data, table)
    except (TypeError, ValueError) as exc:
        raise ValueError({table or "quantity": str(exc)}) from exc
    if labels:
        form_data["_field_labels"] = {**(form_data.get("_field_labels") or {}), **labels}


def load_delivery(profile, ticket):
    version = ticket.workflow_version
    if not version or version.domain != ticket.domain or version.workflow_id != ticket.workflow_id or provision_profile(version) != profile:
        raise PermissionError("工单与交付流程版本不匹配")
    config, team_id = _request_config(profile, version, ticket.service, ticket.creator, ticket.team)
    machines, _ = _machines(config, ticket.form_data, request_table(version))
    host = None
    if profile != "demo":
        _check_target(config["target_id"], team_id, ticket.domain)
        host = _check_vcenter(config["vc_instance_uuid"], team_id, config["vc_host"])
    return {
        "machines": machines,
        "team_id": team_id,
        "target_id": config.get("target_id"),
        "vc_host": host,
        "vc_instance_uuid": config.get("vc_instance_uuid"),
    }
