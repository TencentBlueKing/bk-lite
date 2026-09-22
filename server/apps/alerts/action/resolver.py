from apps.alerts.action.exceptions import ConfigError
from apps.alerts.action.payload import resolve_field

MASKED_DEFAULTS = {"******", "***"}


def plain_script_default(param_def: dict) -> str:
    if "default" not in (param_def or {}):
        return ""
    value = param_def.get("default")
    if value in MASKED_DEFAULTS:
        return ""
    if value is None:
        return ""
    return value


def resolve_params(payload: dict, bindings: list, script_params: list, overrides: dict | None = None) -> list:
    """按脚本参数顺序解析。const 空值原样下发；field 缺失回退明文 default。"""
    overrides = overrides or {}
    by_name = {b["name"]: b for b in (bindings or []) if b.get("name")}
    defs = [p for p in (script_params or []) if p.get("name")]
    if not defs:
        defs = [{"name": b["name"]} for b in (bindings or []) if b.get("name")]
    out = []
    for param_def in defs:
        name = param_def["name"]
        if name in overrides:
            out.append({"name": name, "value": overrides[name]})
            continue
        binding = by_name.get(name)
        if binding is None:
            out.append({"name": name, "value": plain_script_default(param_def)})
            continue
        if binding.get("from") == "const":
            value = binding.get("value")
            out.append({"name": name, "value": "" if value is None else value})
            continue
        value = resolve_field(payload, binding.get("value"))
        if value is None:
            if "default" not in param_def:
                raise ConfigError(f"参数[{name}]字段[{binding.get('value')}]缺失且无默认值")
            value = plain_script_default(param_def)
            if value == "" and param_def.get("default") in MASKED_DEFAULTS:
                raise ConfigError(f"参数[{name}]字段[{binding.get('value')}]缺失且无默认值")
        out.append({"name": name, "value": value})
    return out
