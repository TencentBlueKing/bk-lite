"""通过 elasticsearch-py 访问单个节点。不嗅探、不 mTLS、不跟随多节点。"""

from __future__ import annotations

import ssl
from typing import Any

from apps.core.logger import operation_analysis_logger as logger
from apps.operation_analysis.services.datasource_preview.base import ConnectorError
from apps.operation_analysis.services.datasource_preview.elasticsearch_egress import pinned_connect_target, validate_elasticsearch_url
from apps.operation_analysis.services.datasource_preview.elasticsearch_query import MAX_RESPONSE_BYTES
from apps.operation_analysis.services.user_messages import oa_message

DEFAULT_TIMEOUT_SECONDS = 30
MAX_TIMEOUT_SECONDS = 60
_ALLOWED_CONFIG_KEYS = frozenset(
    {
        "url",
        "auth_type",
        "username",
        "password",
        "api_key",
        "ca_cert",
        "timeout_seconds",
        "index",
    }
)
_REJECTED_CONFIG_KEYS = frozenset(
    {
        "client_cert",
        "client_key",
        "hosts",
        "nodes",
        "sniff",
        "urls",
        "verify_certs",
    }
)


def _fail(message_key: str, default: str, *, code: str, **params) -> ConnectorError:
    return ConnectorError(oa_message(message_key, default, **params), code=code, status_code=400)


def _timeout_seconds(value: Any) -> int:
    if value in (None, ""):
        return DEFAULT_TIMEOUT_SECONDS
    try:
        seconds = int(value)
    except (TypeError, ValueError) as exc:
        raise _fail("messages.es_timeout_invalid", "Elasticsearch 超时无效", code="elasticsearch_timeout_invalid") from exc
    if isinstance(value, bool) or seconds < 1 or seconds > MAX_TIMEOUT_SECONDS:
        raise _fail("messages.es_timeout_invalid", "Elasticsearch 超时无效", code="elasticsearch_timeout_invalid")
    return seconds


def _api_key_value(value: Any) -> str | tuple[str, str]:
    text = str(value or "").strip()
    if text.lower().startswith("apikey "):
        text = text.split(" ", 1)[1].strip()
    if not text:
        raise _fail("messages.es_api_key_required", "Elasticsearch API Key 不能为空", code="elasticsearch_auth_invalid")
    if ":" in text:
        key_id, secret = text.split(":", 1)
        if not key_id or not secret:
            raise _fail("messages.es_api_key_required", "Elasticsearch API Key 不能为空", code="elasticsearch_auth_invalid")
        return key_id, secret
    return text


def normalize_elasticsearch_config(config: dict[str, Any], *, resolve_dns: bool = True) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise _fail("messages.es_config_object", "Elasticsearch 连接配置必须是对象", code="elasticsearch_config_invalid")
    rejected = sorted(set(config.keys()).intersection(_REJECTED_CONFIG_KEYS))
    unknown = sorted(set(config.keys()) - _ALLOWED_CONFIG_KEYS - _REJECTED_CONFIG_KEYS)
    if rejected or unknown:
        names = ", ".join(rejected + unknown)
        raise _fail(
            "messages.es_config_keys",
            "Elasticsearch 连接配置包含不允许的字段: {names}",
            code="elasticsearch_config_invalid",
            names=names,
        )
    if config.get("verify_certs") is False:
        raise _fail("messages.es_verify_required", "Elasticsearch HTTPS 必须校验证书", code="elasticsearch_tls_invalid")

    url = validate_elasticsearch_url(str(config.get("url") or ""), resolve_dns=resolve_dns)
    auth_type = str(config.get("auth_type") or "none").lower()
    if auth_type not in {"none", "basic", "api_key"}:
        raise _fail(
            "messages.es_auth_type",
            "不支持的 Elasticsearch 鉴权类型: {auth_type}",
            code="elasticsearch_auth_invalid",
            auth_type=auth_type,
        )

    normalized: dict[str, Any] = {
        "url": url,
        "auth_type": auth_type,
        "timeout_seconds": _timeout_seconds(config.get("timeout_seconds")),
        "index": str(config.get("index") or "").strip(),
        "ca_cert": "",
    }
    ca_cert = config.get("ca_cert")
    if ca_cert not in (None, ""):
        ca_text = str(ca_cert).strip()
        if "BEGIN CERTIFICATE" not in ca_text or len(ca_text) > 20000:
            raise _fail("messages.es_ca_invalid", "Elasticsearch CA 证书无效", code="elasticsearch_tls_invalid")
        normalized["ca_cert"] = ca_text

    if auth_type == "basic":
        username = config.get("username")
        password = config.get("password")
        if username in (None, "") or password in (None, ""):
            raise _fail("messages.es_basic_auth", "Elasticsearch Basic 鉴权需要用户名和密码", code="elasticsearch_auth_invalid")
        normalized["username"] = str(username)
        normalized["password"] = str(password)
    elif auth_type == "api_key":
        normalized["api_key"] = _api_key_value(config.get("api_key"))
    return normalized


class _LimitedSerializer:
    """在解析响应前限制字节数。mimetype 与官方 JSONSerializer 一致。"""

    mimetype = "application/json"

    def dumps(self, data):
        from elasticsearch.serializer import JSONSerializer

        return JSONSerializer().dumps(data)

    def loads(self, data):
        size = len(data) if isinstance(data, (bytes, bytearray)) else len(str(data).encode("utf-8"))
        if size > MAX_RESPONSE_BYTES:
            raise ConnectorError(
                oa_message("messages.es_response_too_large", "Elasticsearch 响应体过大"),
                code="elasticsearch_response_too_large",
                status_code=400,
            )
        from elasticsearch.serializer import JSONSerializer

        return JSONSerializer().loads(data)


def _ssl_context(ca_cert: str) -> ssl.SSLContext:
    context = ssl.create_default_context()
    if ca_cert:
        context.load_verify_locations(cadata=ca_cert)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class _SafeLogError(Exception):
    """日志代理。正文只有异常类型，traceback 仍指向原始异常。"""


def log_elasticsearch_failure(stage: str, exc: BaseException, *, status_code: Any = None) -> None:
    proxy = _SafeLogError(type(exc).__name__)
    logger.error(
        "[ElasticsearchConnector] request failed failed_stage=%s error_type=%s status=%s",
        stage,
        type(exc).__name__,
        "" if status_code is None else status_code,
        exc_info=(type(proxy), proxy, exc.__traceback__),
    )


def _pinned_connection_class(tls_hostname: str):
    from elasticsearch.connection import Urllib3HttpConnection

    class PinnedHostConnection(Urllib3HttpConnection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            pool = getattr(self, "pool", None)
            if pool is None:
                return
            pool.assert_hostname = tls_hostname
            context = getattr(pool, "ssl_context", None)
            if context is not None:
                context.check_hostname = False

    return PinnedHostConnection


def build_elasticsearch_client(config: dict[str, Any]):
    from elasticsearch import Elasticsearch

    normalized = normalize_elasticsearch_config(config)
    host, port, use_ssl, tls_hostname = pinned_connect_target(normalized["url"])
    kwargs: dict[str, Any] = {
        "hosts": [{"host": host, "port": port, "use_ssl": use_ssl}],
        "timeout": normalized["timeout_seconds"],
        "retry_on_timeout": False,
        "max_retries": 0,
        "sniff_on_start": False,
        "sniff_on_connection_fail": False,
        "serializer": _LimitedSerializer(),
    }
    if tls_hostname:
        kwargs["headers"] = {"Host": tls_hostname}
        kwargs["connection_class"] = _pinned_connection_class(tls_hostname)
    if use_ssl:
        kwargs["verify_certs"] = True
        kwargs["ssl_context"] = _ssl_context(normalized["ca_cert"])
        kwargs["ssl_show_warn"] = False
    if normalized["auth_type"] == "basic":
        kwargs["http_auth"] = (normalized["username"], normalized["password"])
    elif normalized["auth_type"] == "api_key":
        kwargs["api_key"] = normalized["api_key"]
    return Elasticsearch(**kwargs)


class ElasticsearchSearchClient:
    def __init__(self, client_factory=None):
        self.client_factory = client_factory or build_elasticsearch_client

    def info(self, connection_config: dict[str, Any]) -> dict:
        return self._call(connection_config, "info")

    def search(self, connection_config: dict[str, Any], index: str, body: dict) -> dict:
        return self._call(connection_config, "search", index=index, body=body)

    def _call(self, connection_config: dict[str, Any], operation: str, **kwargs):
        try:
            client = self.client_factory(connection_config)
        except ConnectorError:
            raise
        except Exception as exc:
            log_elasticsearch_failure("connect", exc)
            raise ConnectorError(
                oa_message("messages.es_connection_failed", "Elasticsearch 连接失败"),
                code="elasticsearch_connection_failed",
                status_code=502,
            ) from exc

        try:
            if operation == "info":
                payload = client.info()
            else:
                payload = client.search(index=kwargs["index"], body=kwargs["body"])
        except ConnectorError:
            raise
        except Exception as exc:
            self._raise_transport(operation, exc)
        else:
            if not isinstance(payload, dict):
                raise ConnectorError(
                    oa_message("messages.es_response_invalid", "Elasticsearch 响应格式无效"),
                    code="elasticsearch_response_invalid",
                    status_code=502,
                )
            return payload
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception as exc:
                    logger.warning(
                        "[ElasticsearchConnector] client close failed failed_stage=close error_type=%s",
                        type(exc).__name__,
                    )

    def _raise_transport(self, operation: str, exc: Exception) -> None:
        current: BaseException | None = exc
        seen: set[int] = set()
        while current is not None and id(current) not in seen:
            if isinstance(current, ConnectorError):
                raise current
            seen.add(id(current))
            current = current.__cause__ or current.__context__

        status_code = getattr(exc, "status_code", None)
        log_elasticsearch_failure(operation, exc, status_code=status_code if status_code is not None else "")
        if status_code in {401, 403}:
            raise ConnectorError(
                oa_message("messages.es_auth_failed", "Elasticsearch 鉴权失败"),
                code="elasticsearch_auth_failed",
                status_code=400,
            ) from exc
        message_key = "messages.es_connection_failed" if operation == "info" else "messages.es_query_failed"
        default = "Elasticsearch 连接失败" if operation == "info" else "Elasticsearch 查询失败"
        code = "elasticsearch_connection_failed" if operation == "info" else "elasticsearch_query_failed"
        raise ConnectorError(oa_message(message_key, default), code=code, status_code=502) from exc
