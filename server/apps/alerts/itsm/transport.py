"""给 urllib3 的每次 socket 读取施加同一个截止时间，包括响应头慢流。"""
import io
import ipaddress
import socket
import time

from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPSConnection
from urllib3.connectionpool import HTTPSConnectionPool


class DeadlineReader(io.RawIOBase):
    def __init__(self, sock, deadline, raw=None):
        self.sock, self.deadline, self.raw = sock, deadline, raw

    def readable(self):
        return True

    def readinto(self, buffer):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("ITSM response deadline exceeded")
        self.sock.settimeout(min(20, remaining))
        return self.raw.readinto(buffer) if self.raw is not None else self.sock.recv_into(buffer)

    def close(self):
        if self.raw is not None:
            self.raw.close()
        super().close()


class DeadlineSocket:
    def __init__(self, sock, deadline):
        self.sock, self.deadline = sock, deadline

    def __getattr__(self, key):
        return getattr(self.sock, key)

    def makefile(self, mode, buffering=None):
        if mode != "rb":
            raise ValueError("unsupported ITSM response stream mode")
        return io.BufferedReader(DeadlineReader(self.sock, self.deadline, self.sock.makefile(mode, buffering=0)))


def deadline_adapter(deadline, guard_url=None):
    class Connection(HTTPSConnection):
        def _new_conn(self):
            if guard_url is None:
                return super()._new_conn()
            from urllib3.exceptions import NewConnectionError

            from apps.core.utils.ssrf_validator import SSRFValidator

            # 解析一次、逐地址执行统一策略、直连已验证 sockaddr；TLS 仍使用原主机名。
            addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
            networks, domains = SSRFValidator._get_allowed_networks(), SSRFValidator._get_allowed_domains()
            for _, _, _, _, address in addresses:
                ip = ipaddress.ip_address(address[0])
                if SSRFValidator._parse_ip_literal(self.host) is not None:
                    SSRFValidator._assert_literal_ip_allowed(ip, networks, guard_url)
                else:
                    SSRFValidator._assert_resolved_ip_allowed(ip, self.host, networks, domains, guard_url)
            for family, kind, proto, _, address in addresses:
                sock = socket.socket(family, kind, proto)
                try:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("ITSM connection deadline exceeded")
                    sock.settimeout(min(5, remaining))
                    sock.connect(address)
                    return sock
                except OSError:
                    sock.close()
            raise NewConnectionError(self, "ITSM connection failed")

        def connect(self):
            super().connect()
            self.sock = DeadlineSocket(self.sock, deadline)

    class Pool(HTTPSConnectionPool):
        ConnectionCls = Connection

    adapter = HTTPAdapter(max_retries=0)
    # 每次请求独立连接池；不修改 urllib3 全局注册表或其他模块的 HTTP 行为。
    adapter.poolmanager.pool_classes_by_scheme = {**adapter.poolmanager.pool_classes_by_scheme, "https": Pool}
    return adapter
