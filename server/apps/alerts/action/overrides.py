from apps.alerts.action.exceptions import ConfigError


def validate_manual_param_overrides(bindings: list, overrides) -> dict:
    if not overrides:
        return {}
    if not isinstance(overrides, dict):
        raise ConfigError("param_overrides 必须是对象")
    allowed = {
        binding["name"]
        for binding in (bindings or [])
        if binding.get("name") and binding.get("from") == "const" and binding.get("allow_adjust") is True
    }
    extra = [key for key in overrides if key not in allowed]
    if extra:
        raise ConfigError(f"不允许覆盖参数: {', '.join(sorted(str(key) for key in extra))}")
    return {key: overrides[key] for key in overrides}
