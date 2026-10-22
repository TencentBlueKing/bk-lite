from typing import Dict, Optional, Tuple

from apps.cmdb.services.instance_identity import optional_inst_uuid

BindingKey = Tuple[Tuple[str, str], ...]
BUILTIN_CMDB_PRESET = "builtin_cmdb_resource"


def resolve_rule_binding(event: Dict, rule) -> Optional[Dict[str, str]]:
    """内置 CMDB 规则优先用监控带来的 cmdb_id / monitor_id，否则沿用规则绑定。"""
    if getattr(rule, "preset_key", "") == BUILTIN_CMDB_PRESET:
        identity = _builtin_identity_binding(event)
        if identity:
            return identity
    return resolve_binding(event, getattr(rule, "input_binding", {}) or {})


def _builtin_identity_binding(event: Dict) -> Optional[Dict[str, str]]:
    params = {}
    cmdb_uuid = optional_inst_uuid(event.get("cmdb_id"))
    if cmdb_uuid:
        params["inst_uuid"] = cmdb_uuid
    monitor_id = event.get("monitor_id")
    if monitor_id not in (None, ""):
        text = str(monitor_id).strip()
        if text:
            params["monitor_id"] = text
    return params or None


def resolve_binding(event: Dict, binding: Dict[str, str]) -> Optional[Dict[str, str]]:
    """按 input_binding 把 event 字段映射为 provider 查询参数。任一字段缺失/为空则返回 None（跳过）。"""
    params = {}
    for provider_param, event_field in binding.items():
        value = event.get(event_field)
        if value in (None, ""):
            return None
        params[provider_param] = str(value)
    return params or None


def build_binding_key(params: Dict[str, str]) -> BindingKey:
    """把查询参数归一化为稳定排序的可哈希 key。"""
    return tuple(sorted((str(k), str(v)) for k, v in params.items()))
