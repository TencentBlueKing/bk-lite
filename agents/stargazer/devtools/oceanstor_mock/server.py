# -*- coding: utf-8 -*-
"""华为 OceanStor DeviceManager REST 最小 mock。

TEST-ONLY / 本地联调，不进默认生产采集路径，不改任务树默认值。
语义对齐 `oceanstor_https`：POST /xxxxx/sessions → iBaseToken + deviceid，
之后 GET /{deviceid}/{storagepool|disk|lun|eth_port|fc_port}。
空 MAC / 空 WWPN 原样返回，调用方跳过，mock 不编造身份。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
LIST_RESOURCES = ("storagepool", "disk", "lun", "eth_port", "fc_port")
OBJECT_RESOURCES = ("system",)
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "Admin@storage"
DEFAULT_DEVICE_ID = "2102355TJUN0S1100017"
DEFAULT_TOKEN = "mock-ibase-token"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18088
_RANGE_RE = re.compile(r"\[(\d+)-(\d+)\]")
_REST_RE = re.compile(r"^/deviceManager/rest/([^/]+)(?:/([^/?#]+))?/?$")


def load_json(name: str, fixture_dir: Path | None = None):
    path = (fixture_dir or FIXTURE_DIR) / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_fixtures(fixture_dir: Path | None = None) -> dict:
    root = fixture_dir or FIXTURE_DIR
    return {
        "system": load_json("system.json", root),
        "storagepool": load_json("storagepool.json", root),
        "disk": load_json("disk.json", root),
        "lun": load_json("lun.json", root),
        "eth_port": load_json("eth_port.json", root),
        "fc_port": load_json("fc_port.json", root),
    }


def _gb(sectors, sector_size):
    try:
        return int(int(float(sectors)) * int(float(sector_size)) / (1024**3))
    except (TypeError, ValueError):
        return 0


def collect_result_from_fixtures(host: str = DEFAULT_HOST, device_id: str = DEFAULT_DEVICE_ID, fixture_dir: Path | None = None) -> dict:
    """按 OceanStorManager.list_all_resources()['result'] 形状组装夹具。"""
    fixtures = load_fixtures(fixture_dir)
    pools = fixtures["storagepool"]
    disks = fixtures["disk"]
    luns = fixtures["lun"]
    system = fixtures["system"]
    total = used = avail = 0
    for pool in pools:
        sector_size = pool.get("SECTORSIZE", "512")
        total += _gb(pool.get("USERTOTALCAPACITY", 0), sector_size)
        used += _gb(pool.get("USERCONSUMEDCAPACITY", 0), sector_size)
        avail += _gb(pool.get("USERFREECAPACITY", 0), sector_size)
    storage = {
        "device_sn": device_id,
        "ip_addr": host,
        "model": str(system.get("PRODUCTMODESTRING") or "").strip(),
        "brand": "huawei",
        "storage_type": "SAN",
        "firmware_version": str(system.get("PRODUCTVERSION") or "").strip(),
        "sys_desc": "Huawei OceanStor",
        "total_capacity": str(total),
        "used_capacity": str(used),
        "available_capacity": str(avail),
        "pool_count": str(len(pools)),
        "disk_count": str(len(disks)),
        "volume_count": str(len(luns)),
        "RUNNINGSTATUS": "27",
    }
    return {
        "storage": [storage],
        "storage_pool": pools,
        "storage_disk": disks,
        "storage_volume": luns,
        "storage_eth_port": fixtures["eth_port"],
        "storage_fc_port": fixtures["fc_port"],
    }


def to_vm_vector(collect_result: dict, timestamp: int | None = None) -> dict:
    """把采集 result 转成 CMDB format_data 所需的 VM 向量。"""
    ts = int(time.time()) - 60 if timestamp is None else timestamp
    rows = []
    for model_id, items in collect_result.items():
        metric_name = f"{model_id}_info_gauge"
        for item in items or []:
            metric = {"__name__": metric_name, "collect_status": "success"}
            metric.update(item)
            rows.append({"metric": metric, "value": [ts, "1"]})
    return {"result": rows}


def apply_range(items: list, range_value: str | None) -> list:
    if not range_value:
        return items
    match = _RANGE_RE.fullmatch(str(range_value).strip())
    if not match:
        return items
    start, end = int(match.group(1)), int(match.group(2))
    if start < 0 or end < start:
        return []
    return items[start : end + 1]


def ok_payload(data):
    return {"error": {"code": 0, "description": "0"}, "data": data}


def err_payload(code: int, description: str, data=None):
    return {"error": {"code": code, "description": description}, "data": [] if data is None else data}


class OceanStorMockState:
    def __init__(self, username, password, device_id, token, fixtures):
        self.username = username
        self.password = password
        self.device_id = device_id
        self.token = token
        self.fixtures = fixtures
        self.sessions: set[str] = set()
        self.lock = threading.Lock()


def _read_json(handler: BaseHTTPRequestHandler):
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _header_token(handler: BaseHTTPRequestHandler) -> str:
    for key, value in handler.headers.items():
        if key.lower() == "ibasetoken":
            return str(value or "")
    return ""


def make_handler(state: OceanStorMockState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if os.environ.get("OCEANSTOR_MOCK_VERBOSE"):
                super().log_message(fmt, *args)

        def _write_json(self, payload, status=200):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _parse_rest(self):
            parsed = urlparse(self.path)
            match = _REST_RE.match(parsed.path)
            if not match:
                return None, None, parse_qs(parsed.query)
            return match.group(1), match.group(2) or "", parse_qs(parsed.query)

        def _authed(self) -> bool:
            token = _header_token(self)
            with state.lock:
                return bool(token) and token in state.sessions

        def do_POST(self):
            device_id, resource, _query = self._parse_rest()
            if device_id is None or resource != "sessions":
                self._write_json(err_payload(1077949072, "URL does not exist"))
                return
            payload = _read_json(self)
            username = str(payload.get("username") or "")
            password = str(payload.get("password") or "")
            if username != state.username or password != state.password:
                self._write_json(err_payload(1077949061, "username or password is incorrect", {}))
                return
            with state.lock:
                state.sessions.add(state.token)
            self._write_json(ok_payload({"iBaseToken": state.token, "deviceid": state.device_id}))

        def do_DELETE(self):
            device_id, resource, _query = self._parse_rest()
            if device_id is None or resource != "sessions":
                self._write_json(err_payload(1077949072, "URL does not exist"))
                return
            if device_id not in {"xxxxx", state.device_id}:
                self._write_json(err_payload(1077949072, "URL does not exist"))
                return
            token = _header_token(self)
            with state.lock:
                state.sessions.discard(token)
            self._write_json(ok_payload({}))

        def do_GET(self):
            device_id, resource, query = self._parse_rest()
            if device_id is None or not resource:
                self._write_json(err_payload(1077949072, "URL does not exist"))
                return
            if device_id != state.device_id:
                self._write_json(err_payload(1077949072, "URL does not exist"))
                return
            if not self._authed():
                self._write_json(err_payload(1077949061, "session is invalid"))
                return
            if resource in OBJECT_RESOURCES:
                self._write_json(ok_payload(state.fixtures["system"]))
                return
            if resource not in LIST_RESOURCES:
                self._write_json(err_payload(1077949072, "URL does not exist"))
                return
            range_values = query.get("range") or []
            range_value = range_values[0] if range_values else None
            items = apply_range(list(state.fixtures[resource]), range_value)
            self._write_json(ok_payload(items))

    return Handler


class OceanStorMockServer:
    """线程化 HTTP(S) mock，port=0 时绑定临时端口。"""

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = 0,
        username: str = DEFAULT_USERNAME,
        password: str = DEFAULT_PASSWORD,
        device_id: str = DEFAULT_DEVICE_ID,
        token: str = DEFAULT_TOKEN,
        fixture_dir: Path | None = None,
        tls: bool = False,
        certfile: str | None = None,
        keyfile: str | None = None,
    ):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.device_id = device_id
        self.token = token
        self.fixture_dir = Path(fixture_dir) if fixture_dir else FIXTURE_DIR
        self.tls = tls
        self.certfile = certfile
        self.keyfile = keyfile
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._tls_tmpdir = None
        self.state = OceanStorMockState(username, password, device_id, token, load_fixtures(self.fixture_dir))

    @property
    def scheme(self) -> str:
        return "https" if self.tls else "http"

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def start(self) -> OceanStorMockServer:
        handler = make_handler(self.state)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        if self.tls:
            certfile, keyfile = self._tls_files()
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            self._httpd.socket = context.wrap_socket(self._httpd.socket, server_side=True)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="oceanstor-mock", daemon=True)
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

    def __enter__(self) -> OceanStorMockServer:
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.stop()
        return False

    def _tls_files(self) -> tuple[str, str]:
        if self.certfile and self.keyfile:
            return self.certfile, self.keyfile
        self._tls_tmpdir = tempfile.TemporaryDirectory(prefix="oceanstor-mock-")
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
    parser = argparse.ArgumentParser(description="OceanStor DeviceManager REST mock（仅测试）")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--device-id", default=DEFAULT_DEVICE_ID)
    parser.add_argument("--tls", action="store_true", help="自签证书 HTTPS")
    parser.add_argument("--certfile")
    parser.add_argument("--keyfile")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    server = OceanStorMockServer(
        host=args.host,
        port=args.port,
        username=args.username,
        password=args.password,
        device_id=args.device_id,
        tls=args.tls,
        certfile=args.certfile,
        keyfile=args.keyfile,
    )
    server.start()
    print(f"OceanStor mock listening on {server.base_url}")
    print(f"login: POST {server.base_url}/deviceManager/rest/xxxxx/sessions")
    print(f"username={server.username} password={server.password} deviceid={server.device_id}")
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
