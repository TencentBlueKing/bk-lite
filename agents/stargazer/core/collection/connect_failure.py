"""连接失败的稳定原因。不返回异常正文，也不返回凭据值。"""

from __future__ import annotations


def credential_detail(username, password) -> str:
    if not str(username or "").strip():
        return "credential_user"
    if not password:
        return "credential_password"
    return "credential_user_or_password"


def transport_detail(error: BaseException) -> str:
    text = " ".join(str(part) for part in (error, error.__cause__, error.__context__) if part).lower()
    if "connection refused" in text or "errno 61" in text or "errno 111" in text:
        return "tcp_connection_refused"
    if "timed out" in text or "timeout" in text:
        return "tcp_connect_timeout"
    if "name or service not known" in text or "nodename nor servname" in text:
        return "dns_resolution_failed"
    if "no route" in text or "network is unreachable" in text:
        return "tcp_no_route"
    return "tcp_connect_failed"
