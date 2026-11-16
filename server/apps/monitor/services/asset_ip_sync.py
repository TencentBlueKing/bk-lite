import ipaddress

from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.instance_facts import InstanceFactResolver

ASSET_IP_FACT = InstanceFactResolver.ASSET_IP_FACT


def align_summary_asset_ip(instance, model_ip) -> bool:
    """绑定字段就是 ip 时，把摘要 asset.ip 写成这次保存的模型 IP。

    host / jmx_url 等其它绑定不改，避免 CMDB 地址盖掉用户填写的目标。
    """
    normalized = _valid_ip(model_ip)
    monitor_object_id = getattr(instance, "monitor_object_id", None)
    if normalized is None or not _object_binds_asset_ip_to_ip_field(monitor_object_id):
        return False
    facts = instance.summary_facts if isinstance(instance.summary_facts, dict) else {}
    if facts.get(ASSET_IP_FACT) == normalized:
        return False
    updated = dict(facts)
    updated[ASSET_IP_FACT] = normalized
    sources = dict(updated.get("_sources") or {})
    sources[ASSET_IP_FACT] = {"model_ip": normalized}
    updated["_sources"] = sources
    instance.summary_facts = updated
    return True


def _object_binds_asset_ip_to_ip_field(monitor_object_id) -> bool:
    if monitor_object_id in (None, ""):
        return False
    saw_ip_field = False
    bindings_rows = MonitorPlugin.objects.filter(monitor_object__id=monitor_object_id).values_list("instance_fact_bindings", flat=True)
    for bindings in bindings_rows:
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            if not isinstance(binding, dict) or binding.get("fact") != ASSET_IP_FACT:
                continue
            options = binding.get("options") if isinstance(binding.get("options"), dict) else {}
            if binding.get("resolver") != "input" or options.get("field") != "ip":
                return False
            saw_ip_field = True
    return saw_ip_field


def _valid_ip(value):
    try:
        return str(ipaddress.ip_address(str(value or "").strip()))
    except ValueError:
        return None
