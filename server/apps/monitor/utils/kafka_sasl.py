"""Kafka SASL 下发兜底：启用认证时机制不得为空。"""

from __future__ import annotations

from typing import Any, MutableMapping

DEFAULT_SASL_MECHANISM = "plain"
_SASL_ENABLED_TRUTHY = {"true", "1", "yes", "--sasl.enabled"}


def is_sasl_enabled(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    text = str(value).strip().lower()
    return text in _SASL_ENABLED_TRUTHY


def ensure_kafka_sasl_mechanism_defaults(config_info: MutableMapping[str, Any]) -> None:
    """表单 payload（ENV_*）侧：启用认证且机制为空时写入 plain。"""
    if not is_sasl_enabled(config_info.get("ENV_SASL_ENABLED")):
        return
    mechanism = config_info.get("ENV_SASL_MECHANISM")
    if mechanism is None or str(mechanism).strip() == "":
        config_info["ENV_SASL_MECHANISM"] = DEFAULT_SASL_MECHANISM


def ensure_kafka_sasl_mechanism_in_env(env_config: MutableMapping[str, Any] | None) -> None:
    """env_config 侧：兼容无后缀与 ``SASL_*__<config_id>`` 后缀。"""
    if not env_config:
        return

    enabled_suffixes: list[str] = []
    for key, value in list(env_config.items()):
        key_text = str(key)
        if key_text == "SASL_ENABLED" or key_text.startswith("SASL_ENABLED__"):
            if is_sasl_enabled(value):
                enabled_suffixes.append(key_text[len("SASL_ENABLED") :])

    for suffix in enabled_suffixes:
        mechanism_key = f"SASL_MECHANISM{suffix}"
        mechanism = env_config.get(mechanism_key)
        if mechanism is None or str(mechanism).strip() == "":
            env_config[mechanism_key] = DEFAULT_SASL_MECHANISM
