import json
from typing import Any, Dict, Literal, Optional

import oracledb
from langchain_core.runnables import RunnableConfig

from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, CredentialValidationError, NormalizedCredentials, normalize_credentials

if not hasattr(oracledb, "makedsn"):
    def _compat_oracle_makedsn(host, port, service_name=None, sid=None, **_kwargs):
        if service_name:
            return f"{host}:{port}/{service_name}"
        if sid:
            return f"{host}:{port}:{sid}"
        return f"{host}:{port}"

    oracledb.makedsn = _compat_oracle_makedsn

if not hasattr(oracledb, "connect"):
    def _missing_oracle_connect(*_args, **_kwargs):
        raise RuntimeError("oracledb.connect is unavailable in the installed Oracle driver")

    oracledb.connect = _missing_oracle_connect

ORACLE_INSTANCE_FIELDS = (
    "id",
    "name",
    "host",
    "port",
    "service_name",
    "user",
    "password",
    "nls_lang",
)


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def normalize_oracle_instance(instance: Dict[str, Any], fallback_name: str = "Oracle - 1", fallback_id: str = "oracle-1") -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in ORACLE_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["host"] = _normalize_text(normalized.get("host"))
    normalized["port"] = _normalize_int(normalized.get("port"), 1521)
    normalized["service_name"] = _normalize_text(normalized.get("service_name")) or "ORCL"
    normalized["user"] = _normalize_text(normalized.get("user"))
    normalized["password"] = _normalize_text(normalized.get("password"))
    normalized["nls_lang"] = _normalize_text(normalized.get("nls_lang"))
    return normalized


def parse_oracle_instances(raw_instances: Any) -> list[Dict[str, Any]]:
    if not raw_instances:
        return []

    parsed_instances = raw_instances
    if isinstance(raw_instances, str):
        try:
            parsed_instances = json.loads(raw_instances)
        except json.JSONDecodeError:
            return []

    if not isinstance(parsed_instances, list):
        return []

    normalized_instances = []
    for index, instance in enumerate(parsed_instances, start=1):
        if not isinstance(instance, dict):
            continue
        normalized_instances.append(normalize_oracle_instance(instance, fallback_name=f"Oracle - {index}", fallback_id=f"oracle-{index}"))
    return normalized_instances


def get_oracle_instances_from_configurable(configurable: Dict[str, Any]) -> tuple[list[Dict[str, Any]], str]:
    instances = parse_oracle_instances(configurable.get("oracle_instances"))
    default_instance_id = _normalize_text(configurable.get("oracle_default_instance_id"))
    return instances, default_instance_id


def resolve_oracle_instance(
    instances: list[Dict[str, Any]],
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No Oracle instances configured")

    if instance_id:
        for instance in instances:
            if instance.get("id") == instance_id:
                return instance
        raise ValueError(f"Oracle instance not found: {instance_id}")

    if instance_name:
        for instance in instances:
            if instance.get("name") == instance_name:
                return instance
        raise ValueError(f"Oracle instance not found: {instance_name}")

    if default_instance_id:
        for instance in instances:
            if instance.get("id") == default_instance_id:
                return instance

    return instances[0]


def _build_legacy_oracle_config(configurable: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "host": configurable.get("host", "127.0.0.1"),
        "port": _normalize_int(configurable.get("port"), 1521),
        "service_name": configurable.get("service_name", "ORCL"),
        "user": configurable.get("user", ""),
        "password": configurable.get("password", ""),
    }


def build_oracle_config_from_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_oracle_instance(instance)
    params: Dict[str, Any] = {
        "host": normalized.get("host") or "127.0.0.1",
        "port": normalized.get("port", 1521),
        "service_name": normalized.get("service_name") or "ORCL",
        "user": normalized.get("user") or "",
        "password": normalized.get("password") or "",
        "nls_lang": normalized.get("nls_lang") or "",
    }
    return params


def _create_oracle_connection(params: Dict[str, Any]):
    host = params.get("host", "127.0.0.1")
    port = params.get("port", 1521)
    service_name = params.get("service_name", "ORCL")
    user = params.get("user", "")
    password = params.get("password", "")

    dsn = oracledb.makedsn(host, port, service_name=service_name)
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    return conn


def get_oracle_connection(
    config: Optional[RunnableConfig] = None,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
):
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_oracle_instances_from_configurable(configurable)

    if instances:
        instance = resolve_oracle_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
        params = build_oracle_config_from_instance(instance)
        return _create_oracle_connection(params)

    if instance_name or instance_id:
        raise ValueError("Oracle instance selection is unavailable for legacy single-instance configuration")

    params = _build_legacy_oracle_config(configurable)
    return _create_oracle_connection(params)


ORACLE_FLAT_FIELDS = ["host", "port", "service_name", "user", "password"]


class OracleCredentialAdapter:
    flat_fields = ORACLE_FLAT_FIELDS

    def build_from_flat_config(self, configurable: Dict[str, Any]) -> Dict[str, Any]:
        return _build_legacy_oracle_config(configurable)

    def build_from_credential_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return build_oracle_config_from_instance(item)

    def validate(self, config: Dict[str, Any]) -> None:
        if not config.get("host"):
            raise CredentialValidationError("Oracle host is required")

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"Oracle - {index + 1}"


_oracle_adapter = OracleCredentialAdapter()


def build_oracle_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    """
    Build NormalizedCredentials from RunnableConfig.

    - If oracle_instances is configured with a specific instance_name/id: single-mode targeting that instance.
    - If oracle_instances is configured without instance selection: multi-mode (all instances) when count > 1, single-mode when count == 1.
    - If no oracle_instances: legacy single-mode from flat fields.
    """
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_oracle_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_oracle_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
            oracle_config = build_oracle_config_from_instance(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[CredentialItem(index=0, name=instance.get("name", "Oracle - 1"), raw=instance, config=oracle_config)],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            oracle_config = build_oracle_config_from_instance(instance)
            items.append(CredentialItem(index=i, name=instance.get("name", f"Oracle - {i + 1}"), raw=instance, config=oracle_config))
        return NormalizedCredentials(mode=mode, legacy_single=False, items=items)

    return normalize_credentials(configurable, _oracle_adapter)


def get_oracle_connection_from_item(item: CredentialItem):
    """Create an Oracle connection from a CredentialItem (for use in executors)."""
    return _create_oracle_connection(item["config"].copy())


def test_oracle_instance(instance: Dict[str, Any]) -> bool:
    normalized = normalize_oracle_instance(instance)
    if not normalized.get("host"):
        raise ValueError("Oracle host is required")
    params = build_oracle_config_from_instance(normalized)
    conn = _create_oracle_connection(params)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM DUAL")
        cursor.close()
        return True
    finally:
        conn.close()


def get_oracle_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_oracle_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_oracle_instance(instances, default_instance_id)
    available_instances = ", ".join(instance["name"] for instance in instances if instance.get("name"))
    return (
        f"已配置 {len(instances)} 个 Oracle 实例，可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )
