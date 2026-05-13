"""PostgreSQL 多实例凭据管理 - 对齐 mysql/connection.py 模式"""

import json
from typing import Any, Dict, Literal, Optional

import psycopg2
from langchain_core.runnables import RunnableConfig
from psycopg2.extras import RealDictCursor

from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, CredentialValidationError, NormalizedCredentials, normalize_credentials

POSTGRES_INSTANCE_FIELDS = (
    "id",
    "name",
    "host",
    "port",
    "database",
    "user",
    "password",
)


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


def normalize_postgres_instance(
    instance: Dict[str, Any],
    fallback_name: str = "PostgreSQL - 1",
    fallback_id: str = "postgres-1",
) -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in POSTGRES_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["host"] = _normalize_text(normalized.get("host"))
    normalized["port"] = _normalize_int(normalized.get("port"), 5432)
    normalized["database"] = _normalize_text(normalized.get("database")) or "postgres"
    normalized["user"] = _normalize_text(normalized.get("user"))
    normalized["password"] = _normalize_text(normalized.get("password"))
    return normalized


def parse_postgres_instances(raw_instances: Any) -> list[Dict[str, Any]]:
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
        normalized_instances.append(
            normalize_postgres_instance(
                instance,
                fallback_name=f"PostgreSQL - {index}",
                fallback_id=f"postgres-{index}",
            )
        )
    return normalized_instances


def get_postgres_instances_from_configurable(
    configurable: Dict[str, Any],
) -> tuple[list[Dict[str, Any]], str]:
    instances = parse_postgres_instances(configurable.get("postgres_instances"))
    default_instance_id = _normalize_text(configurable.get("postgres_default_instance_id"))
    return instances, default_instance_id


def resolve_postgres_instance(
    instances: list[Dict[str, Any]],
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No PostgreSQL instances configured")

    if instance_id:
        for instance in instances:
            if instance.get("id") == instance_id:
                return instance
        raise ValueError(f"PostgreSQL instance not found: {instance_id}")

    if instance_name:
        for instance in instances:
            if instance.get("name") == instance_name:
                return instance
        raise ValueError(f"PostgreSQL instance not found: {instance_name}")

    if default_instance_id:
        for instance in instances:
            if instance.get("id") == default_instance_id:
                return instance

    return instances[0]


def _build_legacy_postgres_config(configurable: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "host": configurable.get("host", "localhost"),
        "port": _normalize_int(configurable.get("port"), 5432),
        "database": configurable.get("database", "postgres"),
        "user": configurable.get("user", "postgres"),
        "password": configurable.get("password", ""),
    }


def build_postgres_config_from_item(item: CredentialItem) -> Dict[str, Any]:
    """从 CredentialItem 构建 psycopg2 连接参数字典。"""
    cfg = item["config"]
    return {
        "host": cfg.get("host") or "localhost",
        "port": cfg.get("port", 5432),
        "database": cfg.get("database") or "postgres",
        "user": cfg.get("user") or "postgres",
        "password": cfg.get("password") or "",
    }


POSTGRES_FLAT_FIELDS = ["host", "port", "database", "user", "password"]


class PostgresCredentialAdapter:
    flat_fields = POSTGRES_FLAT_FIELDS

    def build_from_flat_config(self, configurable: Dict[str, Any]) -> Dict[str, Any]:
        return _build_legacy_postgres_config(configurable)

    def build_from_credential_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = normalize_postgres_instance(item)
        return {
            "host": normalized.get("host") or "localhost",
            "port": normalized.get("port", 5432),
            "database": normalized.get("database") or "postgres",
            "user": normalized.get("user") or "postgres",
            "password": normalized.get("password") or "",
        }

    def validate(self, config: Dict[str, Any]) -> None:
        if not config.get("host"):
            raise CredentialValidationError("PostgreSQL host is required")

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"PostgreSQL - {index + 1}"


_postgres_adapter = PostgresCredentialAdapter()


def build_postgres_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    """
    Build NormalizedCredentials from RunnableConfig.

    - If postgres_instances is configured with a specific instance_name/id: single-mode targeting that instance.
    - If postgres_instances is configured without instance selection: multi-mode when count > 1, single-mode when count == 1.
    - If no postgres_instances: legacy single-mode from flat fields (host/port/database/user/password).
    """
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_postgres_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_postgres_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
            pg_config = _postgres_adapter.build_from_credential_item(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[
                    CredentialItem(
                        index=0,
                        name=instance.get("name", "PostgreSQL - 1"),
                        raw=instance,
                        config=pg_config,
                    )
                ],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            pg_config = _postgres_adapter.build_from_credential_item(instance)
            items.append(
                CredentialItem(
                    index=i,
                    name=instance.get("name", f"PostgreSQL - {i + 1}"),
                    raw=instance,
                    config=pg_config,
                )
            )
        return NormalizedCredentials(mode=mode, legacy_single=False, items=items)

    return normalize_credentials(configurable, _postgres_adapter)


def get_postgres_connection_from_item(item: CredentialItem):
    """Create a psycopg2 connection from a CredentialItem (uses RealDictCursor)."""
    cfg = build_postgres_config_from_item(item)
    return psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        database=cfg["database"],
        user=cfg["user"],
        password=cfg["password"],
        cursor_factory=RealDictCursor,
        connect_timeout=10,
    )


def get_postgres_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_postgres_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_postgres_instance(instances, default_instance_id)
    available_instances = ", ".join(instance["name"] for instance in instances if instance.get("name"))
    return (
        f"已配置 {len(instances)} 个 PostgreSQL 实例，可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )


def test_postgres_instance(instance: Dict[str, Any]) -> bool:
    """测试 PostgreSQL 实例连接是否可达，连接失败时抛出异常。"""
    normalized = normalize_postgres_instance(instance)
    if not normalized.get("host"):
        raise ValueError("PostgreSQL host is required")
    conn = psycopg2.connect(
        host=normalized["host"],
        port=normalized["port"],
        database=normalized["database"],
        user=normalized["user"],
        password=normalized["password"],
        connect_timeout=10,
    )
    try:
        conn.cursor().execute("SELECT 1")
        return True
    finally:
        conn.close()
