"""Active Directory LDAP 连接与多实例配置。"""

from __future__ import annotations

import json
import ssl
from typing import Any

from langchain_core.runnables import RunnableConfig
from ldap3 import ALL, SIMPLE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException

from apps.core.logger import opspilot_logger as logger
from apps.core.logger import safe_log_value
from apps.opspilot.metis.llm.tools.common.credentials import CredentialItem, CredentialValidationError, NormalizedCredentials, normalize_credentials

AD_INSTANCE_FIELDS = (
    "id",
    "name",
    "host",
    "port",
    "use_ssl",
    "verify_cert",
    "ca_cert",
    "bind_dn",
    "bind_password",
    "base_dn",
)

_AD_LDAPS_VERIFY_DISABLED = "event=ad_ldaps_certificate_verification_disabled instance_id=%s host=%s"


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_ad_instance(instance: dict[str, Any], fallback_name: str = "AD - 1", fallback_id: str = "ad-1") -> dict[str, Any]:
    use_ssl = _normalize_bool(instance.get("use_ssl"), default=True)
    default_port = 636 if use_ssl else 389
    return {
        "id": _normalize_text(instance.get("id")) or fallback_id,
        "name": _normalize_text(instance.get("name")) or fallback_name,
        "host": _normalize_text(instance.get("host")),
        "port": _normalize_int(instance.get("port"), default_port),
        "use_ssl": use_ssl,
        "verify_cert": _normalize_bool(instance.get("verify_cert"), default=True),
        "ca_cert": _normalize_text(instance.get("ca_cert")),
        "bind_dn": _normalize_text(instance.get("bind_dn")),
        "bind_password": _normalize_text(instance.get("bind_password")),
        "base_dn": _normalize_text(instance.get("base_dn")),
    }


def parse_ad_instances(raw_instances: Any) -> list[dict[str, Any]]:
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
    out = []
    for index, item in enumerate(parsed, start=1):
        if isinstance(item, dict):
            out.append(normalize_ad_instance(item, fallback_name=f"AD - {index}", fallback_id=f"ad-{index}"))
    return out


class ActiveDirectoryCredentialAdapter:
    flat_fields = ["host", "bind_dn", "bind_password", "base_dn", "ad_host", "ad_bind_dn", "ad_bind_password", "ad_base_dn"]

    def build_from_flat_config(self, configurable: dict[str, Any]) -> dict[str, Any]:
        verify_cert = configurable.get("verify_cert")
        if verify_cert is None:
            verify_cert = configurable.get("ad_verify_cert", True)
        ca_cert = configurable.get("ca_cert")
        if ca_cert is None:
            ca_cert = configurable.get("ad_ca_cert")
        return normalize_ad_instance(
            {
                "id": configurable.get("id") or "ad-1",
                "name": configurable.get("name") or "Active Directory",
                "host": configurable.get("host") or configurable.get("ad_host"),
                "port": configurable.get("port") or configurable.get("ad_port"),
                "use_ssl": configurable.get("use_ssl") if configurable.get("use_ssl") is not None else configurable.get("ad_use_ssl", True),
                "verify_cert": verify_cert,
                "ca_cert": ca_cert,
                "bind_dn": configurable.get("bind_dn") or configurable.get("ad_bind_dn"),
                "bind_password": configurable.get("bind_password") or configurable.get("ad_bind_password"),
                "base_dn": configurable.get("base_dn") or configurable.get("ad_base_dn"),
            }
        )

    def build_from_credential_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return normalize_ad_instance(item)

    def validate(self, config: dict[str, Any]) -> None:
        missing = [k for k in ("host", "bind_dn", "bind_password", "base_dn") if not config.get(k)]
        if missing:
            raise CredentialValidationError(f"Active Directory 缺少连接参数: {', '.join(missing)}")

    def get_display_name(self, source: dict[str, Any], index: int) -> str:
        return _normalize_text(source.get("name")) or f"AD - {index + 1}"


def get_ad_instances_from_configurable(configurable: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    instances = parse_ad_instances(configurable.get("ad_instances"))
    default_id = _normalize_text(configurable.get("ad_default_instance_id"))
    if instances:
        return instances, default_id
    # 兼容 flat / credentials
    try:
        normalized = normalize_credentials(configurable, ActiveDirectoryCredentialAdapter())
        return [item["config"] for item in normalized["items"]], default_id
    except Exception:
        return [], default_id


def build_ad_normalized_from_runnable(
    config: RunnableConfig | None,
    instance_name: str | None = None,
    instance_id: str | None = None,
) -> NormalizedCredentials:
    configurable = (config or {}).get("configurable") or {}
    instances, default_id = get_ad_instances_from_configurable(configurable)

    if instances:
        selected = instances
        if instance_id:
            selected = [i for i in instances if i.get("id") == instance_id] or instances
        elif instance_name:
            selected = [i for i in instances if i.get("name") == instance_name] or instances
        elif default_id:
            matched = [i for i in instances if i.get("id") == default_id]
            if matched:
                selected = matched
        adapter = ActiveDirectoryCredentialAdapter()
        items = []
        for idx, inst in enumerate(selected):
            adapter.validate(inst)
            items.append(
                CredentialItem(
                    index=idx,
                    name=inst.get("name") or f"AD - {idx + 1}",
                    raw=inst,
                    config=inst,
                )
            )
        mode = "single" if len(items) == 1 else "multi"
        return NormalizedCredentials(mode=mode, legacy_single=False, items=items)

    return normalize_credentials(configurable, ActiveDirectoryCredentialAdapter())


def _build_ad_tls(cfg: dict[str, Any]):
    """LDAPS 默认校验证书；仅 verify_cert=False 时关闭校验。"""
    if not cfg.get("use_ssl"):
        return None
    verify_cert = _normalize_bool(cfg.get("verify_cert"), default=True)
    if not verify_cert:
        logger.warning(
            _AD_LDAPS_VERIFY_DISABLED,
            safe_log_value(cfg.get("id")),
            safe_log_value(cfg.get("host")),
        )
        return Tls(validate=ssl.CERT_NONE, version=ssl.PROTOCOL_TLS_CLIENT)
    ca_cert = _normalize_text(cfg.get("ca_cert"))
    if ca_cert:
        return Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT, ca_certs_data=ca_cert)
    return Tls(validate=ssl.CERT_REQUIRED, version=ssl.PROTOCOL_TLS_CLIENT)


def get_ad_connection_from_item(item: CredentialItem) -> Connection:
    cfg = item["config"]
    tls = _build_ad_tls(cfg)
    server = Server(cfg["host"], port=int(cfg["port"]), use_ssl=bool(cfg.get("use_ssl")), get_info=ALL, tls=tls)
    conn = Connection(
        server,
        user=cfg["bind_dn"],
        password=cfg["bind_password"],
        authentication=SIMPLE,
        auto_bind=True,
        raise_exceptions=True,
    )
    return conn


def test_ad_instance(instance: dict[str, Any]) -> bool:
    """探测 AD/LDAP 连通性：绑定成功即视为通过。"""
    normalized = normalize_ad_instance(instance)
    missing = [k for k in ("host", "bind_dn", "bind_password", "base_dn") if not normalized.get(k)]
    if missing:
        raise ValueError(f"Active Directory 缺少连接参数: {', '.join(missing)}")
    conn = None
    try:
        item: CredentialItem = {
            "index": 0,
            "name": normalized.get("name") or "AD",
            "raw": normalized,
            "config": normalized,
        }
        conn = get_ad_connection_from_item(item)
        return True
    finally:
        safe_unbind(conn)


def get_ad_instances_prompt(tool_kwargs: dict[str, Any] | None) -> str:
    instances = parse_ad_instances((tool_kwargs or {}).get("ad_instances"))
    if not instances:
        return ""
    lines = ["Available Active Directory instances:"]
    for inst in instances:
        lines.append(f"- id={inst['id']} name={inst['name']} host={inst['host']} base_dn={inst['base_dn']}")
    lines.append("Pass instance_id or instance_name when multiple instances are configured.")
    return "\n".join(lines)


def safe_unbind(conn: Connection | None) -> None:
    if conn is None:
        return
    try:
        conn.unbind()
    except LDAPException:
        pass
