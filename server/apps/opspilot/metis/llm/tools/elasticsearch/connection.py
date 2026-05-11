"""Elasticsearch 多实例凭据管理 - 对齐 mysql/connection.py 模式"""

import json
from typing import Any, Dict, Literal, Optional

from elasticsearch import Elasticsearch
from langchain_core.runnables import RunnableConfig

from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, CredentialValidationError, NormalizedCredentials, normalize_credentials

ES_INSTANCE_FIELDS = ("id", "name", "url", "username", "password", "api_key", "verify_certs", "ca_certs", "client_cert", "client_key")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in ("false", "0", "no", "off")
    return default


def normalize_es_instance(
    instance: Dict[str, Any],
    fallback_name: str = "Elasticsearch - 1",
    fallback_id: str = "es-1",
) -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in ES_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["url"] = _normalize_text(normalized.get("url")) or "http://127.0.0.1:9200"
    normalized["username"] = _normalize_text(normalized.get("username"))
    normalized["password"] = _normalize_text(normalized.get("password"))
    normalized["api_key"] = _normalize_text(normalized.get("api_key"))
    normalized["verify_certs"] = _normalize_bool(normalized.get("verify_certs"), True)
    normalized["ca_certs"] = _normalize_text(normalized.get("ca_certs"))
    normalized["client_cert"] = _normalize_text(normalized.get("client_cert"))
    normalized["client_key"] = _normalize_text(normalized.get("client_key"))
    return normalized


def parse_es_instances(raw_instances: Any) -> list:
    if not raw_instances:
        return []
    parsed = raw_instances
    if isinstance(raw_instances, str):
        try:
            parsed = json.loads(raw_instances)
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, list):
        return []
    result = []
    for i, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            continue
        result.append(normalize_es_instance(item, fallback_name=f"Elasticsearch - {i}", fallback_id=f"es-{i}"))
    return result


def get_es_instances_from_configurable(configurable: Dict[str, Any]) -> tuple:
    instances = parse_es_instances(configurable.get("es_instances"))
    default_instance_id = _normalize_text(configurable.get("es_default_instance_id"))
    return instances, default_instance_id


def resolve_es_instance(
    instances: list,
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No Elasticsearch instances configured")
    if instance_id:
        for inst in instances:
            if inst.get("id") == instance_id:
                return inst
        raise ValueError(f"Elasticsearch instance not found: {instance_id}")
    if instance_name:
        for inst in instances:
            if inst.get("name") == instance_name:
                return inst
        raise ValueError(f"Elasticsearch instance not found: {instance_name}")
    if default_instance_id:
        for inst in instances:
            if inst.get("id") == default_instance_id:
                return inst
    return instances[0]


def _build_legacy_es_config(configurable: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": configurable.get("url") or "http://127.0.0.1:9200",
        "username": configurable.get("username", ""),
        "password": configurable.get("password", ""),
        "api_key": configurable.get("api_key", ""),
        "verify_certs": _normalize_bool(configurable.get("verify_certs"), True),
        "ca_certs": configurable.get("ca_certs", ""),
        "client_cert": configurable.get("client_cert", ""),
        "client_key": configurable.get("client_key", ""),
    }


def _build_es_client_kwargs(cfg: Dict[str, Any]) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {
        "hosts": [cfg["url"]],
        "verify_certs": cfg.get("verify_certs", True),
    }
    if cfg.get("api_key"):
        kwargs["api_key"] = cfg["api_key"]
    elif cfg.get("username") or cfg.get("password"):
        kwargs["http_auth"] = (cfg.get("username", ""), cfg.get("password", ""))
    if cfg.get("ca_certs"):
        kwargs["ca_certs"] = cfg["ca_certs"]
    if cfg.get("client_cert"):
        kwargs["client_cert"] = cfg["client_cert"]
    if cfg.get("client_key"):
        kwargs["client_key"] = cfg["client_key"]
    return kwargs


ES_FLAT_FIELDS = ["url", "username", "password", "api_key", "verify_certs", "ca_certs", "client_cert", "client_key"]


class ESCredentialAdapter:
    flat_fields = ES_FLAT_FIELDS

    def build_from_flat_config(self, configurable: Dict[str, Any]) -> Dict[str, Any]:
        return _build_legacy_es_config(configurable)

    def build_from_credential_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_es_instance(item)
        return {
            "url": normalized.get("url") or "http://127.0.0.1:9200",
            "username": normalized.get("username", ""),
            "password": normalized.get("password", ""),
            "api_key": normalized.get("api_key", ""),
            "verify_certs": normalized.get("verify_certs", True),
            "ca_certs": normalized.get("ca_certs", ""),
            "client_cert": normalized.get("client_cert", ""),
            "client_key": normalized.get("client_key", ""),
        }

    def validate(self, config: Dict[str, Any]) -> None:
        if not config.get("url"):
            raise CredentialValidationError("Elasticsearch URL is required")

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"Elasticsearch - {index + 1}"


_es_adapter = ESCredentialAdapter()


def build_es_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_es_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_es_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
            es_config = _es_adapter.build_from_credential_item(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[CredentialItem(index=0, name=instance.get("name", "Elasticsearch - 1"), raw=instance, config=es_config)],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            es_config = _es_adapter.build_from_credential_item(instance)
            items.append(CredentialItem(index=i, name=instance.get("name", f"Elasticsearch - {i + 1}"), raw=instance, config=es_config))
        return NormalizedCredentials(mode=mode, legacy_single=False, items=items)

    return normalize_credentials(configurable, _es_adapter)


def get_es_client_from_item(item: CredentialItem) -> Elasticsearch:
    """Create an Elasticsearch client from a CredentialItem."""
    return Elasticsearch(**_build_es_client_kwargs(item["config"]))


def get_es_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_es_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_es_instance(instances, default_instance_id)
    available_instances = ", ".join(inst["name"] for inst in instances if inst.get("name"))
    return (
        f"已配置 {len(instances)} 个 Elasticsearch 实例，可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )


def test_es_instance(instance: Dict[str, Any]) -> bool:
    """测试 Elasticsearch 实例连接是否可达，失败时抛出异常。"""
    normalized = normalize_es_instance(instance)
    if not normalized.get("url"):
        raise ValueError("Elasticsearch URL is required")
    client = Elasticsearch(**_build_es_client_kwargs(normalized))
    try:
        if not client.ping():
            raise ConnectionError("Elasticsearch ping returned False")
        return True
    finally:
        client.close()


# ── Legacy compatibility ──────────────────────────────────────────────────────


def build_es_config_from_runnable(config: Optional[RunnableConfig]) -> Dict[str, Any]:
    """Legacy helper kept for backward compatibility. Uses the first instance or flat fields."""
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_es_instances_from_configurable(configurable)
    if instances:
        instance = resolve_es_instance(instances, default_instance_id)
        cfg = _es_adapter.build_from_credential_item(instance)
    else:
        cfg = _build_legacy_es_config(configurable)
    return _build_es_client_kwargs(cfg)


def get_es_client(config: Optional[RunnableConfig] = None) -> Elasticsearch:
    """Legacy helper: returns an Elasticsearch client for the default/only instance."""
    return Elasticsearch(**build_es_config_from_runnable(config))
