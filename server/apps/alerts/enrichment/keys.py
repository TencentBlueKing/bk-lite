from typing import Dict, Optional, Tuple

BindingKey = Tuple[Tuple[str, str], ...]


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
