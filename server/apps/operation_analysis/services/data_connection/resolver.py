from urllib.parse import urljoin, urlparse
from posixpath import normpath

from apps.operation_analysis.models.datasource_models import DataConnection, DataSourceAPIModel
from apps.operation_analysis.services.data_connection.config_crypto import decrypt_connection_config
from apps.operation_analysis.services.data_connection.groups import find_groups_outside_connection, is_groups_subset


class ConnectionResolveError(Exception):
    def __init__(self, message, *, code="connection_resolve_failed", status_code=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


def _is_safe_relative_path(path):
    if path in (None, ""):
        return True
    if not isinstance(path, str):
        return False
    stripped = path.strip()
    if not stripped:
        return True
    if stripped.startswith("//"):
        return False
    parsed = urlparse(stripped)
    if parsed.scheme or parsed.netloc:
        return False
    # 禁止 ../ 路径穿越，避免 urljoin 跳出 Base URL 前缀。
    normalized = normpath(stripped.lstrip("/"))
    if normalized.startswith("..") or "/../" in f"/{stripped}/":
        return False
    return True


def _join_base_url(base_url, path):
    base = (base_url or "").rstrip("/") + "/"
    relative = (path or "").lstrip("/")
    joined = urljoin(base, relative)
    base_host = urlparse(base_url or "").netloc
    joined_host = urlparse(joined).netloc
    if base_host and joined_host and base_host != joined_host:
        raise ConnectionResolveError(
            "REST 相对路径不得改变目标主机",
            code="rest_path_invalid",
            status_code=400,
        )
    return joined


class ConnectionResolver:
    """按数据源与当前组织解析可执行连接配置。"""

    def resolve(self, datasource, *, current_team=None):
        if not isinstance(datasource, DataSourceAPIModel):
            raise ConnectionResolveError("数据源无效", code="datasource_invalid", status_code=400)

        if not datasource.connection_id:
            return dict(datasource.connection_config or {})

        connection = datasource.connection
        if connection is None:
            raise ConnectionResolveError("数据连接不存在", code="connection_missing", status_code=400)
        if not connection.is_active:
            raise ConnectionResolveError("数据连接已停用，请启用或更换连接", code="connection_inactive", status_code=400)

        if not is_groups_subset(datasource.groups, connection.groups):
            outside = find_groups_outside_connection(datasource.groups, connection.groups)
            raise ConnectionResolveError(
                f"数据源组织超出连接授权范围: {outside}",
                code="connection_groups_mismatch",
                status_code=403,
            )

        if current_team is not None:
            team_values = {current_team, str(current_team)}
            try:
                team_values.add(int(current_team))
            except (TypeError, ValueError):
                pass
            connection_groups = set(connection.groups or [])
            comparable = set()
            for item in connection_groups:
                comparable.add(item)
                comparable.add(str(item))
                try:
                    comparable.add(int(item))
                except (TypeError, ValueError):
                    pass
            if not team_values.intersection(comparable):
                raise ConnectionResolveError("无权使用当前数据连接", code="connection_org_denied", status_code=403)

        decrypted = decrypt_connection_config(connection.config or {})
        overrides = datasource.connection_overrides if isinstance(datasource.connection_overrides, dict) else {}

        if connection.connection_type in {DataConnection.TYPE_MYSQL, DataConnection.TYPE_POSTGRESQL}:
            resolved = {
                "host": decrypted.get("host"),
                "port": decrypted.get("port"),
                "database": decrypted.get("database"),
                "username": decrypted.get("username"),
                "password": decrypted.get("password"),
            }
            if "database" in overrides and overrides.get("database") not in (None, ""):
                resolved["database"] = overrides["database"]
            return resolved

        if connection.connection_type == DataConnection.TYPE_REST_API:
            path = overrides.get("path")
            if path in (None, ""):
                path = (datasource.connection_config or {}).get("path") or ""
            if not _is_safe_relative_path(path):
                raise ConnectionResolveError(
                    "REST 相对路径不允许使用绝对或跨源 URL",
                    code="rest_path_invalid",
                    status_code=400,
                )
            method = overrides.get("method") or (datasource.connection_config or {}).get("method") or "GET"
            timeout = overrides.get("timeout")
            if timeout in (None, ""):
                timeout = (datasource.connection_config or {}).get("timeout") or decrypted.get("timeout") or 10
            return {
                "url": _join_base_url(decrypted.get("base_url") or decrypted.get("url"), path),
                "method": method,
                "timeout": timeout,
                "headers": decrypted.get("headers") if isinstance(decrypted.get("headers"), dict) else {},
            }

        raise ConnectionResolveError("连接类型不支持", code="connection_type_unsupported", status_code=400)


def resolve_datasource_connection(datasource, *, current_team=None):
    return ConnectionResolver().resolve(datasource, current_team=current_team)
