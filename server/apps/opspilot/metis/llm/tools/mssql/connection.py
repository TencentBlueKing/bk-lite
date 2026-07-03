import json
from typing import Any, Dict, Literal, Optional

import pyodbc
from langchain_core.runnables import RunnableConfig
from loguru import logger

from apps.opspilot.metis.llm.tools.common.credentials import (
    CredentialItem,
    CredentialValidationError,
    NormalizedCredentials,
    normalize_credentials,
)
from apps.opspilot.metis.llm.tools.mssql.utils import get_available_driver

if not hasattr(pyodbc, "connect"):
    def _missing_pyodbc_connect(*args, **kwargs):
        raise RuntimeError("pyodbc.connect is unavailable")

    pyodbc.connect = _missing_pyodbc_connect

MSSQL_INSTANCE_FIELDS = (
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


def normalize_mssql_instance(instance: Dict[str, Any], fallback_name: str = "MSSQL - 1", fallback_id: str = "mssql-1") -> Dict[str, Any]:
    normalized = {key: instance.get(key) for key in MSSQL_INSTANCE_FIELDS}
    normalized["id"] = _normalize_text(normalized.get("id")) or fallback_id
    normalized["name"] = _normalize_text(normalized.get("name")) or fallback_name
    normalized["host"] = _normalize_text(normalized.get("host"))
    normalized["port"] = _normalize_int(normalized.get("port"), 1433)
    normalized["database"] = _normalize_text(normalized.get("database")) or "master"
    normalized["user"] = _normalize_text(normalized.get("user"))
    normalized["password"] = _normalize_text(normalized.get("password"))
    return normalized


def parse_mssql_instances(raw_instances: Any) -> list[Dict[str, Any]]:
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
        normalized_instances.append(normalize_mssql_instance(instance, fallback_name=f"MSSQL - {index}", fallback_id=f"mssql-{index}"))
    return normalized_instances


def get_mssql_instances_from_configurable(configurable: Dict[str, Any]) -> tuple[list[Dict[str, Any]], str]:
    instances = parse_mssql_instances(configurable.get("mssql_instances"))
    default_instance_id = _normalize_text(configurable.get("mssql_default_instance_id"))
    return instances, default_instance_id


def resolve_mssql_instance(
    instances: list[Dict[str, Any]],
    default_instance_id: str = "",
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> Dict[str, Any]:
    if not instances:
        raise ValueError("No MSSQL instances configured")

    if instance_id:
        for instance in instances:
            if instance.get("id") == instance_id:
                return instance
        raise ValueError(f"MSSQL instance not found: {instance_id}")

    if instance_name:
        for instance in instances:
            if instance.get("name") == instance_name:
                return instance
        raise ValueError(f"MSSQL instance not found: {instance_name}")

    if default_instance_id:
        for instance in instances:
            if instance.get("id") == default_instance_id:
                return instance

    return instances[0]


def _build_legacy_mssql_config(configurable: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "host": configurable.get("host", "localhost"),
        "port": _normalize_int(configurable.get("port"), 1433),
        "database": configurable.get("database", "master"),
        "user": configurable.get("user", "sa"),
        "password": configurable.get("password", ""),
    }


def build_mssql_config_from_instance(instance: Dict[str, Any]) -> Dict[str, Any]:
    normalized = normalize_mssql_instance(instance)
    return {
        "host": normalized.get("host") or "localhost",
        "port": normalized.get("port", 1433),
        "database": normalized.get("database") or "master",
        "user": normalized.get("user") or "sa",
        "password": normalized.get("password") or "",
    }


def _create_mssql_connection(params: Dict[str, Any]):
    driver = get_available_driver()
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={params['host']},{params['port']};"
        f"DATABASE={params['database']};"
        f"UID={params['user']};"
        f"PWD={params['password']}"
    )
    if "18" in driver:
        conn_str += ";TrustServerCertificate=yes"
    return pyodbc.connect(conn_str, timeout=10)


def get_mssql_connection(
    config: Optional[RunnableConfig] = None,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
):
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_mssql_instances_from_configurable(configurable)

    if instances:
        instance = resolve_mssql_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
        params = build_mssql_config_from_instance(instance)
        return _create_mssql_connection(params)

    if instance_name or instance_id:
        raise ValueError("MSSQL instance selection is unavailable for legacy single-instance configuration")

    params = _build_legacy_mssql_config(configurable)
    return _create_mssql_connection(params)


MSSQL_FLAT_FIELDS = ["host", "port", "database", "user", "password"]


class MssqlCredentialAdapter:
    flat_fields = MSSQL_FLAT_FIELDS

    def build_from_flat_config(self, configurable: Dict[str, Any]) -> Dict[str, Any]:
        return _build_legacy_mssql_config(configurable)

    def build_from_credential_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return build_mssql_config_from_instance(item)

    def validate(self, config: Dict[str, Any]) -> None:
        if not config.get("host"):
            raise CredentialValidationError("MSSQL host is required")

    def get_display_name(self, source: Dict[str, Any], index: int) -> str:
        return source.get("name") or f"MSSQL - {index + 1}"


_mssql_adapter = MssqlCredentialAdapter()


def build_mssql_normalized_from_runnable(
    config: Optional[RunnableConfig],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
) -> NormalizedCredentials:
    configurable = config.get("configurable", {}) if config else {}
    instances, default_instance_id = get_mssql_instances_from_configurable(configurable)

    if instances:
        if instance_name or instance_id:
            instance = resolve_mssql_instance(instances, default_instance_id, instance_name=instance_name, instance_id=instance_id)
            mssql_config = build_mssql_config_from_instance(instance)
            return NormalizedCredentials(
                mode="single",
                legacy_single=False,
                items=[CredentialItem(index=0, name=instance.get("name", "MSSQL - 1"), raw=instance, config=mssql_config)],
            )

        mode: Literal["single", "multi"] = "single" if len(instances) == 1 else "multi"
        items = []
        for i, instance in enumerate(instances):
            mssql_config = build_mssql_config_from_instance(instance)
            items.append(CredentialItem(index=i, name=instance.get("name", f"MSSQL - {i + 1}"), raw=instance, config=mssql_config))
        return NormalizedCredentials(mode=mode, legacy_single=False, items=items)

    return normalize_credentials(configurable, _mssql_adapter)


def get_mssql_connection_from_item(item: CredentialItem):
    return _create_mssql_connection(item["config"].copy())


def test_mssql_instance(instance: Dict[str, Any]) -> bool:
    normalized = normalize_mssql_instance(instance)
    if not normalized.get("host"):
        raise ValueError("MSSQL host is required")
    params = build_mssql_config_from_instance(normalized)
    conn = _create_mssql_connection(params)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        return True
    finally:
        conn.close()


def get_mssql_instances_prompt(configurable: Dict[str, Any]) -> str:
    instances, default_instance_id = get_mssql_instances_from_configurable(configurable)
    if not instances:
        return ""

    default_instance = resolve_mssql_instance(instances, default_instance_id)
    available_instances = ", ".join(instance["name"] for instance in instances if instance.get("name"))
    return (
        f"已配置 {len(instances)} 个 MSSQL 实例，可用实例: {available_instances}。"
        f"默认实例为「{default_instance['name']}」。"
        "当用户未指定实例时，直接使用默认实例执行工具调用，无需向用户询问。"
        "仅当用户明确要求切换实例时，才在工具调用中传入 instance_name 或 instance_id 参数。"
    )
