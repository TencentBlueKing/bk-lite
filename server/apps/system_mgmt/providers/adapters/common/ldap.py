from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass(slots=True)
class LDAPConnectionConfig:
    connection_url: str
    use_ssl: bool
    timeout: int
    bind_dn: str
    bind_password: str
    base_dn: str


def build_connection_config(config: dict[str, Any] | None) -> LDAPConnectionConfig:
    raw = config or {}
    return LDAPConnectionConfig(
        connection_url=str(raw.get("connection_url") or ""),
        use_ssl=str(raw.get("ssl_encryption") or "").lower() in {"ssl", "ldaps", "true", "1"},
        timeout=int(raw.get("timeout") or 10),
        bind_dn=str(raw.get("bind_dn") or ""),
        bind_password=str(raw.get("bind_password") or ""),
        base_dn=str(raw.get("base_dn") or ""),
    )


def _load_ldap3():
    from ldap3 import ALL, BASE, SIMPLE, SUBTREE, Connection, Server

    return ALL, BASE, SIMPLE, SUBTREE, Connection, Server


def resolve_ldap_server_target(connection_url: str, *, use_ssl: bool) -> tuple[str, int]:
    raw = str(connection_url or "").strip()
    if not raw:
        return "", 636 if use_ssl else 389

    if "://" in raw:
        parsed = urlparse(raw)
        host = (parsed.hostname or "").strip()
        port = parsed.port or (636 if parsed.scheme == "ldaps" or use_ssl else 389)
        return host, port

    if ":" in raw and raw.count(":") == 1:
        host, port_text = raw.split(":", 1)
        if port_text.isdigit():
            return host.strip(), int(port_text)

    return raw, 636 if use_ssl else 389


def create_service_connection(connection_config: LDAPConnectionConfig):
    all_info, _, simple_auth, _, connection_cls, server_cls = _load_ldap3()
    server_host, server_port = resolve_ldap_server_target(
        connection_config.connection_url,
        use_ssl=connection_config.use_ssl,
    )
    server = server_cls(server_host, port=server_port, get_info=all_info, use_ssl=connection_config.use_ssl)
    return connection_cls(
        server,
        user=connection_config.bind_dn,
        password=connection_config.bind_password,
        authentication=simple_auth,
        auto_bind=True,
        receive_timeout=connection_config.timeout,
    )


def normalize_ldap_entry(entry: dict[str, Any]) -> dict[str, Any]:
    if hasattr(entry, "entry_attributes_as_dict"):
        normalized = dict(entry.entry_attributes_as_dict)
        if getattr(entry, "entry_dn", "") and "distinguishedName" not in normalized:
            normalized["distinguishedName"] = entry.entry_dn
        return normalized

    attributes = dict(entry.get("attributes") or {})
    normalized = {key: value for key, value in attributes.items()}
    if entry.get("dn") and "distinguishedName" not in normalized:
        normalized["distinguishedName"] = entry["dn"]
    return normalized


def get_ldap_scalar(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        return get_ldap_scalar(value[0], default=default)
    return str(value).strip()


def normalize_dn(value: str) -> str:
    parts = [segment.strip().lower() for segment in str(value or "").split(",") if segment.strip()]
    return ",".join(parts)


def is_sub_dn(child_dn: str, base_dn: str) -> bool:
    normalized_child = normalize_dn(child_dn)
    normalized_base = normalize_dn(base_dn)
    if not normalized_child or not normalized_base:
        return False
    return normalized_child == normalized_base or normalized_child.endswith(f",{normalized_base}")


def search_entries(
    connection_config: LDAPConnectionConfig,
    search_base: str,
    search_filter: str,
    attributes: list[str] | None = None,
    *,
    search_scope=None,
    paged_size: int | None = None,
) -> list[dict[str, Any]]:
    _, base_scope, _, subtree_scope, _, _ = _load_ldap3()
    connection = create_service_connection(connection_config)
    if paged_size:
        results: list[dict[str, Any]] = []
        page_cookie = None
        while True:
            connection.search(
                search_base=search_base,
                search_filter=search_filter,
                search_scope=search_scope or subtree_scope,
                attributes=attributes or [],
                paged_size=paged_size,
                paged_cookie=page_cookie,
            )
            results.extend(normalize_ldap_entry(entry) for entry in connection.entries)
            controls = connection.result.get("controls", {})
            page_control = controls.get("1.2.840.113556.1.4.319", {}).get("value", {})
            page_cookie = page_control.get("cookie")
            if not page_cookie:
                break
        return results

    connection.search(
        search_base=search_base,
        search_filter=search_filter,
        search_scope=search_scope or subtree_scope,
        attributes=attributes or [],
    )
    return [normalize_ldap_entry(entry) for entry in connection.entries]


def search_single_user(
    connection_config: LDAPConnectionConfig,
    identity_field: str,
    identity_value: str,
    attributes: list[str] | None = None,
) -> dict[str, Any] | None:
    search_filter = f"(&(|(objectClass=user)(objectClass=person))({identity_field}={identity_value}))"
    results = search_entries(connection_config, connection_config.base_dn, search_filter, attributes)
    if len(results) == 1:
        return results[0]
    if len(results) == 0:
        return None
    raise ValueError(f"Expected a single LDAP user for '{identity_field}', got {len(results)}")


def bind_user_dn(connection_config: LDAPConnectionConfig, user_dn: str, password: str) -> None:
    all_info, _, simple_auth, _, connection_cls, server_cls = _load_ldap3()
    server_host, server_port = resolve_ldap_server_target(
        connection_config.connection_url,
        use_ssl=connection_config.use_ssl,
    )
    server = server_cls(server_host, port=server_port, get_info=all_info, use_ssl=connection_config.use_ssl)
    connection_cls(
        server,
        user=user_dn,
        password=password,
        authentication=simple_auth,
        auto_bind=True,
        receive_timeout=connection_config.timeout,
    )


def probe_root_dse(connection_config: LDAPConnectionConfig) -> dict[str, Any]:
    _, base_scope, _, _, _, _ = _load_ldap3()
    results = search_entries(
        connection_config,
        "",
        "(objectClass=*)",
        ["*", "+"],
        search_scope=base_scope,
    )
    return results[0] if results else {}
