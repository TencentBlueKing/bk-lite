"""JOB 主机发现的目标选择规则；插件身份始终由任务决定。"""

import ipaddress

from rest_framework.exceptions import ValidationError

from apps.cmdb.constants.constants import CollectDriverTypes, CollectPluginTypes

MAX_HOST_DISCOVERY_TARGETS = 2048


def organization_ids(value):
    if not isinstance(value, list):
        value = [value] if value is not None else []
    return {str(item) for item in value if type(item) in (int, str) and str(item).isdigit()}


def region_id(value):
    if type(value) not in (str, int) or not str(value).isdigit() or int(value) <= 0:
        return None
    return int(value)


def validate_host_snapshots(instances, team, cloud_region_id):
    """校验可信资产快照并规范化执行 IP，不从主机名称推导地址。"""
    seen = set()
    teams = organization_ids(team)
    for instance in instances:
        if not teams.intersection(organization_ids(instance.get("organization"))):
            raise ValidationError({"instances": "所选主机不在任务组织范围内"})
        cloud = next((instance[key] for key in ("cloud", "cloud_id", "cloud_region_id") if instance.get(key) is not None), None)
        if region_id(cloud) != cloud_region_id:
            raise ValidationError({"instances": "所选主机必须与接入点属于同一云区域"})
        try:
            ip = str(ipaddress.ip_address(str(instance.get("ip_addr") or "").strip()))
        except ValueError as error:
            raise ValidationError({"instances": "所选主机缺少合法管理 IP"}) from error
        if ip in seen:
            raise ValidationError({"instances": "同一任务中主机管理 IP 不能重复"})
        seen.add(ip)
        instance["ip_addr"] = ip


def supports_host_discovery(meta):
    return meta.get("type") == CollectDriverTypes.JOB and (
        meta.get("task_type") in {CollectPluginTypes.DB, CollectPluginTypes.MIDDLEWARE} or meta.get("model_id") == "physcial_server"
    )
