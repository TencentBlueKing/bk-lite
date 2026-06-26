from apps.alerts.action.payload import resolve_field
from apps.alerts.action.exceptions import ConfigError


def resolve_params(payload: dict, bindings: list, script_params: list) -> list:
    """按绑定解析作业参数。field 缺失回退脚本 default；无 default → ConfigError。"""
    defaults = {p["name"]: p for p in (script_params or [])}
    out = []
    for b in bindings or []:
        name = b["name"]
        if b.get("from") == "const":
            value = b.get("value")
        else:
            value = resolve_field(payload, b.get("value"))
            if value is None:
                pdef = defaults.get(name, {})
                if "default" not in pdef:
                    raise ConfigError(f"参数[{name}]字段[{b.get('value')}]缺失且无默认值")
                value = pdef["default"]
        out.append({"name": name, "value": value})
    return out
