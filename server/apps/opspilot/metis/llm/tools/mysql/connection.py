import json
from typing import Any, Dict, Literal, Optional

from langchain_core.runnables import RunnableConfig
from mysql.connector import connect

from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, CredentialValidationError, NormalizedCredentials, normalize_credentials

MYSQL_INSTANCE_FIELDS = (
    "id",
    "name",
    "host",
    "port",
    "database",
    "user",
    "password",
    "charset",
    "collation",
    "ssl",
    "ssl_ca",
    "ssl_cert",
    "ssl_key",
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


def normalize_mysql_instance(instance: Dict[str, Any], fallback_name: str = "MySQL - 1", fallback_id: str = "mysql-1") -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in MYSQL_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["host"] = _normalize_text(normalized.get("host"))
    normalized["port"] = _normalize_int(normalized.get("port"), 3306)
    normalized["database"] = _normalize_text(normalized.get("database")) or "mysql"
    normalized["user"] = _normalize_text(normalized.get("user"))
    normalized["password"] = _normalize_text(normalized.get("password"))
    normalized["charset"] = _normalize_text(normalized.get("charset")) or "utf8mb4"
    normalized["collation"] = _normalize_text(normalized.get("collation")) or "utf8mb4_unicode_ci"
    normalized["ssl"] = _normalize_bool(normalized.get("ssl"))
    normalized["ssl_ca"] = _normalize_text(normalized.get("ssl_ca"))
    normalized["ssl_cert"] = _normalize_text(normalized.get("ssl_cert"))
    normalized["ssl_key"] = _normalize_text(normalized.get("ssl_key"))
    return normalized


def parse_mysql_instances(raw_instances: Any) -> list[Dict[str, Any]]:
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
        normalized_instances.append(normalize_mysql_instance(instance, fallback_name=f"MySQL - {index}", fallback_id=f"mysql-{index}"))
    return normalized_instances


def get_mysql_instances_from_configurable(configurable: Dict[str, Any]) -> tuple[list[Dict[str, Any]], str]:
    instances = parse_mysql_instances(configurable.get("mysql_instances"))
    default_instance_id = _normalize_text(configurable.get("mysql_default_instance_id"))
    return instances, default_instance_id


def resolve_mysql_instance(
    instances: list[Dict[str, Any]],
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No MySQL instances configured")

    if instance_id:
        for instance in instances:
            if instance.get("id") == instance_id:
                return instance
        raise ValueError(f"MySQL instance not found: {instance_id}")

    if instance_name:
        for instance in instances:
            if instance.get("name") == instance_name:
                return instance
        raise ValueError(f"MySQL instance not found: {instance_name}")

    if default_instance_id:
        for instance in instances:
            if instance.get("id") == default_instance_id:
                return instance

    return instances[0]


def _build_legacy_mysql_config(configurable: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "host": configurable.get("host", "127.0.0.1"),
        "port": _normalize_int(configurable.get("port"), 3306),
        "database": configurable.get("database", "mysql"),
        "user": configurable.get("user", ""),
        "password": configurable.get("password", ""),
    }


def build_mysql_config_from_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_mysql_instance(instance)
    params: Dict[str, Any] = {
        "host": normalized.get("host") or "127.0.0.1",
        "port": normalized.get("port", 3306),
        "database": normalized.get("database") or "mysql",
        "user": normalized.get("user") or "",
        "password": normalized.get("password") or "",
        "charset": normalized.get("charset") or "utf8mb4",
        "collation": normalized.get("collation") or "utf8mb4_unicode_ci",
    }
    if normalized.get("ssl"):
        ssl_config: Dict[str, Any] = {}
        if normalized.get("ssl_ca"):
            ssl_config["ca"] = normalized["ssl_ca"]
        if normalized.get("ssl_cert"):
            ssl_config["cert"] = normalized["ssl_cert"]
        if normalized.get("ssl_key"):
            ssl_config["key"] = normalized["ssl_key"]
        if ssl_config:
            params["ssl_ca"] = ssl_config.get("ca")
            params["ssl_cert"] = ssl_config.get("cert")
            params["ssl_key"] = ssl_config.get("key")
    return params


def _create_mysql_connection(params: Dict[str, Any]):
    conn_params = params.copy()
    conn_params["autocommit"] = True
    conn_params["connect_timeout"] = 10
    conn_params["sql_mode"] = "TRADITIONAL"
    return connect(**{k: v for k, v in conn_params.items() if v is not None and v != ""})


def get_mysql_connection(
    config: Optional[RunnableConfig] = None,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
):
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_mysql_instances_from_configurable(configurable)

    if instances:
        instance = resolve_mysql_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
        params = build_mysql_config_from_instance(instance)
        return _create_mysql_connection(params)

    if instance_name or instance_id:
        raise ValueError("MySQL instance selection is unavailable for legacy single-instance configuration")

    params = _build_legacy_mysql_config(configurable)
    return _create_mysql_connection(params)


MYSQL_FLAT_FIELDS = ["host", "port", "database", "user", "password"]


class MysqlCredentialAdapter:
    flat_fields = MYSQL_FLAT_FIELDS

    def build_from_flat_config(self, configurable: Dict[str, Any]) -> Dict[str, Any]:
        return _build_legacy_mysql_config(configurable)

    def build_from_credential_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return build_mysql_config_from_instance(item)

    def validate(self, config: Dict[str, Any]) -> None:
        if not config.get("host"):
            raise CredentialValidationError("MySQL host is required")

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"MySQL - {index + 1}"


_mysql_adapter = MysqlCredentialAdapter()


def build_mysql_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    """
    Build NormalizedCredentials from RunnableConfig.

    - If mysql_instances is configured with a specific instance_name/id: single-mode targeting that instance.
    - If mysql_instances is configured without instance selection: multi-mode (all instances) when count > 1, single-mode when count == 1.
    - If no mysql_instances: legacy single-mode from flat fields.
    """
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_mysql_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_mysql_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
            mysql_config = build_mysql_config_from_instance(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[CredentialItem(index=0, name=instance.get("name", "MySQL - 1"), raw=instance, config=mysql_config)],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            mysql_config = build_mysql_config_from_instance(instance)
            items.append(CredentialItem(index=i, name=instance.get("name", f"MySQL - {i + 1}"), raw=instance, config=mysql_config))
        return NormalizedCredentials(mode=mode, legacy_single=False, items=items)

    return normalize_credentials(configurable, _mysql_adapter)


def get_mysql_connection_from_item(item: CredentialItem):
    """Create a MySQL connection from a CredentialItem (for use in executors)."""
    return _create_mysql_connection(item["config"].copy())


def test_mysql_instance(instance: Dict[str, Any]) -> bool:
    normalized = normalize_mysql_instance(instance)
    if not normalized.get("host"):
        raise ValueError("MySQL host is required")
    params = build_mysql_config_from_instance(normalized)
    conn = _create_mysql_connection(params)
    try:
        conn.ping(reconnect=False)
        return True
    finally:
        conn.close()


def get_mysql_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_mysql_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_mysql_instance(instances, default_instance_id)
    available_instances = ", ".join(instance["name"] for instance in instances if instance.get("name"))
    return (
        f"已配置 {len(instances)} 个 MySQL 实例，可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )
