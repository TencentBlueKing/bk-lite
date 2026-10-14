"""出站 HTTP 网关：默认直连钉死已审 IP，trusted-proxy 仅预留。"""

from typing import Any

import requests
from requests.adapters import HTTPAdapter

from apps.core.logger import logger
from apps.core.utils.ssrf_validator import ValidatedTarget

MODE_DIRECT = "direct"
MODE_TRUSTED_PROXY = "trusted-proxy"


class PinnedSNIAdapter(HTTPAdapter):
    """按原始主机名做 TLS SNI / 证书校验，连接地址仍是已审 IP。"""

    def __init__(self, server_hostname: str, **kwargs):
        self.server_hostname = server_hostname
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["server_hostname"] = self.server_hostname
        pool_kwargs["assert_hostname"] = self.server_hostname
        return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


class EgressGateway:
    def __init__(self, mode: str = MODE_DIRECT, trusted_proxies: tuple[str, ...] = ()):
        self.mode = mode
        self.trusted_proxies = tuple(trusted_proxies)

    def send(self, method: str, target: ValidatedTarget, **kwargs: Any):
        if self.mode == MODE_TRUSTED_PROXY:
            return self._send_via_trusted_proxy(method, target, **kwargs)
        return self._send_direct(method, target, **kwargs)

    def _send_via_trusted_proxy(self, method: str, target: ValidatedTarget, **kwargs: Any):
        # 当前环境没有可登记的生产代理；预留入口，不 fail-open 到未知转发。
        if self.trusted_proxies:
            logger.info("[EgressGateway] trusted-proxy 预留，当前仍走 direct")
        else:
            logger.info("[EgressGateway] trusted-proxy 无可用代理，使用 direct")
        return self._send_direct(method, target, **kwargs)

    def _send_direct(self, method: str, target: ValidatedTarget, **kwargs: Any):
        request_kwargs = dict(kwargs)
        request_kwargs.pop("proxies", None)
        session = requests.Session()
        session.trust_env = False
        if target.scheme == "https":
            session.mount("https://", PinnedSNIAdapter(target.hostname))
        headers = dict(request_kwargs.get("headers") or {})
        headers["Host"] = target.host_header()
        request_kwargs["headers"] = headers
        return session.request(method, target.connect_url(), **request_kwargs)


_default_gateway: EgressGateway | None = None


def get_egress_gateway() -> EgressGateway:
    global _default_gateway
    if _default_gateway is None:
        _default_gateway = EgressGateway()
    return _default_gateway
