"""平台采集共用的地址和证书校验解析，不执行网络请求。"""

from urllib.parse import urlsplit, urlunsplit

PLATFORM_CONNECTION_MODELS = frozenset({"openstack", "smartx", "manageone", "fusioncompute", "nutanixhci", "inspurincloudrail"})


def platform_connection(params, *, default_port=None, default_scheme="https"):
    host = str(params.get("host") or "").strip()
    parsed = urlsplit(host if "://" in host else f"{params.get('scheme') or default_scheme}://{host}")
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Invalid platform endpoint")
    port = params.get("port") or parsed.port or default_port
    if port is not None:
        port = int(port)
        if not 1 <= port <= 65535:
            raise ValueError("Invalid platform port")
    hostname = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    netloc = f"{hostname}:{port}" if port else hostname
    endpoint = urlunsplit((parsed.scheme, netloc, parsed.path.rstrip("/"), "", ""))
    verify = params.get("verify_tls", True)
    if not isinstance(verify, bool):
        normalized = str(verify).strip().lower()
        if normalized not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
            raise ValueError("Invalid TLS verification option")
        verify = normalized in {"true", "1", "yes", "on"}
    return endpoint, verify
