# -*- coding: utf-8 -*-
"""NetApp ONTAP REST 最小 mock。

TEST-ONLY / 本地联调，不进默认生产采集路径，不改任务树默认值。
语义对齐 `netapp_ontap_https`：443 Basic，base_path=/api。
空 MAC / 空 WWPN 原样返回，调用方跳过，mock 不编造身份。
LUN 夹具只含官方 serial_number，不含臆造 wwn/naa。
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
DEFAULT_PASSWORD = "Netapp@storage"
DEFAULT_CLUSTER_UUID = "1cd8a442-86d1-11e0-ae1c-123478563412"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18443
LIST_RESOURCES = {
    "/api/cluster/nodes": "nodes",
    "/api/network/ethernet/ports": "ethernet_ports",
    "/api/network/fc/ports": "fc_ports",
    "/api/storage/aggregates": "aggregates",
    "/api/storage/disks": "disks",
    "/api/storage/luns": "luns",
    "/api/storage/volumes": "volumes",
    "/api/network/ip/interfaces": "ip_interfaces",
}


def load_json(name: str, fixture_dir: Path | None = None):
    path = (fixture_dir or FIXTURE_DIR) / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_fixtures(fixture_dir: Path | None = None) -> dict:
    root = fixture_dir or FIXTURE_DIR
    return {
        "cluster": load_json("cluster.json", root),
        "nodes": load_json("nodes.json", root),
        "aggregates": load_json("aggregates.json", root),
        "disks": load_json("disks.json", root),
        "volumes": load_json("volumes.json", root),
        "luns": load_json("luns.json", root),
        "ethernet_ports": load_json("ethernet_ports.json", root),
        "fc_ports": load_json("fc_ports.json", root),
        "ip_interfaces": load_json("ip_interfaces.json", root),
    }


def _bytes_to_gb(value):
    try:
        return int(int(float(value)) / (1024**3))
    except (TypeError, ValueError):
        return 0


def collect_result_from_fixtures(host: str = DEFAULT_HOST, fixture_dir: Path | None = None) -> dict:
    """按 NetAppOntapManager.list_all_resources()['result'] 形状组装夹具。"""
    from plugins.inputs.netapp_ontap.netapp_ontap_info import NetAppOntapManager

    fixtures = load_fixtures(fixture_dir)
    manager = NetAppOntapManager({"host": host})
    ip_by_port = manager._ip_by_eth_port(fixtures["ip_interfaces"])
    pools = [manager._flatten_pool(item) for item in fixtures["aggregates"]]
    disks = [manager._flatten_disk(item) for item in fixtures["disks"]]
    volumes = [manager._flatten_volume(item) for item in fixtures["volumes"]]
    luns = [manager._flatten_lun(item) for item in fixtures["luns"]]
    eth_ports = [manager._flatten_eth(item, ip_by_port) for item in fixtures["ethernet_ports"]]
    fc_ports = [manager._flatten_fc(item) for item in fixtures["fc_ports"]]
    total = used = avail = 0
    for pool in pools:
        total += _bytes_to_gb(pool.get("total_bytes"))
        used += _bytes_to_gb(pool.get("used_bytes"))
        avail += _bytes_to_gb(pool.get("available_bytes"))
    cluster = fixtures["cluster"]
    nodes = fixtures["nodes"]
    storage = {
        "device_sn": cluster.get("uuid") or "",
        "ip_addr": host,
        "model": (nodes[0].get("model") if nodes else "") or "",
        "brand": "netapp",
        "storage_type": "unified",
        "firmware_version": ((cluster.get("version") or {}).get("full") if isinstance(cluster.get("version"), dict) else "") or "",
        "sys_desc": cluster.get("name") or "NetApp ONTAP",
        "total_capacity": str(total),
        "used_capacity": str(used),
        "available_capacity": str(avail),
        "pool_count": str(len(pools)),
        "disk_count": str(len(disks)),
        "volume_count": str(len(volumes) + len(luns)),
        "state": "online",
    }
    return {
        "storage": [storage],
        "storage_pool": pools,
        "storage_disk": disks,
        "storage_volume": volumes + luns,
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
        max_records = int((query.get("max_records") or ["100"])[0])
    except (TypeError, ValueError):
        max_records = 100
    try:
        offset = int((query.get("offset") or ["0"])[0])
    except (TypeError, ValueError):
        offset = 0
    if max_records <= 0 or offset < 0:
        return [], {}
    batch = items[offset : offset + max_records]
    links = {}
    if offset + max_records < len(items):
        links["next"] = {"href": f"?offset={offset + max_records}&max_records={max_records}"}
    return batch, links


class NetAppOntapMockState:
    def __init__(self, username, password, fixtures):
        self.username = username
        self.password = password
        self.fixtures = fixtures


def _basic_ok(handler: BaseHTTPRequestHandler, state: NetAppOntapMockState) -> bool:
    header = handler.headers.get("Authorization") or ""
    if not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    username, _, password = decoded.partition(":")
    return username == state.username and password == state.password


def make_handler(state: NetAppOntapMockState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if os.environ.get("NETAPP_ONTAP_MOCK_VERBOSE"):
                super().log_message(fmt, *args)

        def _write_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path.rstrip("/") or "/"
            query = parse_qs(parsed.query)
            if not _basic_ok(self, state):
                self._write_json({"error": {"message": "Unauthorized"}}, status=401)
                return
            if path == "/api/cluster":
                self._write_json(state.fixtures["cluster"])
                return
            resource = LIST_RESOURCES.get(path)
            if resource is None:
                self._write_json({"error": {"message": "not found"}}, status=404)
                return
            batch, links = apply_page(list(state.fixtures[resource]), query)
            payload = {"records": batch, "num_records": len(batch)}
            if links:
                next_href = links["next"]["href"]
                payload["_links"] = {"next": {"href": f"{path}{next_href}"}}
            self._write_json(payload)

    return Handler


class NetAppOntapMockServer:
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
        self.state = NetAppOntapMockState(username, password, load_fixtures(self.fixture_dir))

    @property
    def scheme(self) -> str:
        return "https" if self.tls else "http"

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def start(self) -> NetAppOntapMockServer:
        handler = make_handler(self.state)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        if self.tls:
            certfile, keyfile = self._tls_files()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="netapp-ontap-mock", daemon=True)
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

    def __enter__(self) -> NetAppOntapMockServer:
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    def _tls_files(self) -> tuple[str, str]:
        if self.certfile and self.keyfile:
            return self.certfile, self.keyfile
        self._tls_tmpdir = tempfile.TemporaryDirectory(prefix="netapp-ontap-mock-")
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
    parser = argparse.ArgumentParser(description="NetApp ONTAP REST mock（仅测试）")
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
    server = NetAppOntapMockServer(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        tls=args.tls,
        certfile=args.certfile,
        keyfile=args.keyfile,
    )
    server.start()
    print(f"NetApp ONTAP mock listening on {server.base_url}")
    print(f"cluster: GET {server.base_url}/api/cluster")
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
