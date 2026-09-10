# -*- coding: utf-8 -*-
"""Dell Unity Unisphere REST 最小 mock。

TEST-ONLY / 本地联调，不进默认生产采集路径，不改任务树默认值。
语义对齐 `dell_unity_https`：443 Basic，base_path=/api，
请求头 X-EMC-REST-CLIENT: true。
空 MAC / 空 WWPN 原样返回，调用方跳过，mock 不编造身份。
禁止 storops。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Unity@storage"
DEFAULT_SERIAL = "FNM00123456789"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18444
LIST_RESOURCES = {
    "/api/types/pool/instances": "pools",
    "/api/types/lun/instances": "luns",
    "/api/types/disk/instances": "disks",
    "/api/types/ethernetPort/instances": "ethernet_ports",
    "/api/types/fcPort/instances": "fc_ports",
}


def load_json(name: str, fixture_dir: Path | None = None):
    path = (fixture_dir or FIXTURE_DIR) / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_fixtures(fixture_dir: Path | None = None) -> dict:
    root = fixture_dir or FIXTURE_DIR
    return {
        "system": load_json("system.json", root),
        "pools": load_json("pools.json", root),
        "luns": load_json("luns.json", root),
        "disks": load_json("disks.json", root),
        "ethernet_ports": load_json("ethernet_ports.json", root),
        "fc_ports": load_json("fc_ports.json", root),
        "login_session": load_json("login_session.json", root),
    }


def _bytes_to_gb(value):
    try:
        return int(int(float(value)) / (1024**3))
    except (TypeError, ValueError):
        return 0


def collect_result_from_fixtures(host: str = DEFAULT_HOST, fixture_dir: Path | None = None) -> dict:
    """按 DellUnityManager.list_all_resources()['result'] 形状组装夹具。"""
    from plugins.inputs.dell_unity.dell_unity_info import DellUnityManager

    fixtures = load_fixtures(fixture_dir)
    manager = DellUnityManager({"host": host})
    pools = [manager._flatten_pool(item) for item in fixtures["pools"]]
    disks = [manager._flatten_disk(item) for item in fixtures["disks"]]
    luns = [manager._flatten_lun(item) for item in fixtures["luns"]]
    eth_ports = [manager._flatten_eth(item) for item in fixtures["ethernet_ports"]]
    fc_ports = [manager._flatten_fc(item) for item in fixtures["fc_ports"]]
    total = used = avail = 0
    for pool in pools:
        total += _bytes_to_gb(pool.get("sizeTotal"))
        used += _bytes_to_gb(pool.get("sizeUsed"))
        avail += _bytes_to_gb(pool.get("sizeFree"))
    system = fixtures["system"]
    storage = {
        "device_sn": system.get("serialNumber") or "",
        "ip_addr": host,
        "model": system.get("model") or "",
        "brand": "dell",
        "storage_type": "SAN",
        "firmware_version": system.get("softwareVersion") or "",
        "sys_desc": system.get("name") or "Dell Unity",
        "total_capacity": str(total),
        "used_capacity": str(used),
        "available_capacity": str(avail),
        "pool_count": str(len(pools)),
        "disk_count": str(len(disks)),
        "volume_count": str(len(luns)),
        "state": "online",
    }
    return {
        "storage": [storage],
        "storage_pool": pools,
        "storage_disk": disks,
        "storage_volume": luns,
        "storage_eth_port": eth_ports,
        "storage_fc_port": fc_ports,
    }


def to_vm_vector(collect_result: dict, timestamp: int | None = None) -> dict:
    ts = int(time.time()) - 60 if timestamp is None else timestamp
    rows = []
    for model_id, items in collect_result.items():
        metric_name = f"{model_id}_info_gauge"
        for item in items or []:
            metric = {"__name__": metric_name, "collect_status": "success"}
            metric.update(item)
            rows.append({"metric": metric, "value": [ts, "1"]})
    return {"result": rows}


def apply_page(items: list, query: dict) -> tuple[list, dict]:
    try:
        per_page = int((query.get("per_page") or ["100"])[0])
    except (TypeError, ValueError):
        per_page = 100
    try:
        page = int((query.get("page") or ["1"])[0])
    except (TypeError, ValueError):
        page = 1
    if per_page <= 0 or page <= 0:
        return [], {}
    offset = (page - 1) * per_page
    batch = items[offset : offset + per_page]
    links = [{"rel": "self", "href": f"?page={page}&per_page={per_page}"}]
    if offset + per_page < len(items):
        links.append({"rel": "next", "href": f"?page={page + 1}&per_page={per_page}"})
    return batch, links


def _as_entries(items: list) -> list:
    return [{"content": item} for item in items]


class DellUnityMockState:
    def __init__(self, username, password, fixtures):
        self.username = username
        self.password = password
        self.fixtures = fixtures


def _basic_ok(handler: BaseHTTPRequestHandler, state: DellUnityMockState) -> bool:
    header = handler.headers.get("Authorization") or ""
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return username == state.username and password == state.password


def _rest_client_ok(handler: BaseHTTPRequestHandler) -> bool:
    return (handler.headers.get("X-EMC-REST-CLIENT") or "").strip().lower() == "true"


def make_handler(state: DellUnityMockState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if os.environ.get("DELL_UNITY_MOCK_VERBOSE"):
                super().log_message(fmt, *args)

        def _write_json(self, payload, status=200, extra_headers=None):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("EMC-CSRF-TOKEN", "mock-csrf-token")
            for key, value in (extra_headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            if not _basic_ok(self, state):
                self._write_json({"error": {"message": "Unauthorized"}}, status=401)
                return
            if not _rest_client_ok(self):
                self._write_json({"error": {"message": "X-EMC-REST-CLIENT required"}}, status=401)
                return
            if path in {"/api/types/loginSessionInfo/instances", "/api/types/loginSessionInfo/instances"}:
                self._write_json({"entries": _as_entries([state.fixtures["login_session"]])})
                return
            if path in {"/api/types/system/instances", "/api/instances/system/0"}:
                if path.endswith("/0"):
                    self._write_json({"content": state.fixtures["system"]})
                    return
                self._write_json({"entries": _as_entries([state.fixtures["system"]])})
                return
            resource = LIST_RESOURCES.get(path)
            if resource is None:
                self._write_json({"error": {"message": "not found"}}, status=404)
                return
            batch, links = apply_page(list(state.fixtures[resource]), query)
            payload = {"entries": _as_entries(batch)}
            if links:
                payload["links"] = links
            self._write_json(payload)

    return Handler


class DellUnityMockServer:
    """线程化 HTTP(S) mock，port=0 时绑定临时端口。"""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = 0,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
        fixture_dir: Path | None = None,
        tls: bool = False,
        certfile: str | None = None,
        keyfile: str | None = None,
    ):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.fixture_dir = Path(fixture_dir) if fixture_dir else FIXTURE_DIR
        self.tls = tls
        self.certfile = certfile
        self.keyfile = keyfile
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._tls_tmpdir = None
        self.state = DellUnityMockState(username, password, load_fixtures(self.fixture_dir))

    @property
    def scheme(self) -> str:
        return "https" if self.tls else "http"

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def start(self) -> DellUnityMockServer:
        handler = make_handler(self.state)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        if self.tls:
            certfile, keyfile = self._tls_files()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="dell-unity-mock", daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        if self._tls_tmpdir is not None:
            self._tls_tmpdir.cleanup()
            self._tls_tmpdir = None

    def __enter__(self) -> DellUnityMockServer:
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    def _tls_files(self) -> tuple[str, str]:
        if self.certfile and self.keyfile:
            return self.certfile, self.keyfile
        self._tls_tmpdir = tempfile.TemporaryDirectory(prefix="dell-unity-mock-")
        certfile = os.path.join(self._tls_tmpdir.name, "cert.pem")
        keyfile = os.path.join(self._tls_tmpdir.name, "key.pem")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                keyfile,
                "-out",
                certfile,
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=localhost",
            ],
            check=True,
            capture_output=True,
        )
        return certfile, keyfile


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Dell Unity Unisphere REST mock（仅测试）")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--tls", action="store_true", help="自签证书 HTTPS")
    parser.add_argument("--certfile")
    parser.add_argument("--keyfile")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    server = DellUnityMockServer(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        tls=args.tls,
        certfile=args.certfile,
        keyfile=args.keyfile,
    )
    server.start()
    print(f"Dell Unity mock listening on {server.base_url}")
    print(f"system: GET {server.base_url}/api/types/system/instances")
    print(f"username={server.username} password={server.password}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
