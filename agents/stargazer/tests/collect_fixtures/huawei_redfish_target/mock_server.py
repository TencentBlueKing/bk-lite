"""只在本机运行的 Redfish 合成目标，硬件只读，支持短期模拟会话。"""

import argparse
import base64
import hmac
import json
import os
import secrets
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from inventory import PROFILES, SCENARIOS, build_inventory

SESSIONS = "/redfish/v1/SessionService/Sessions"
MAX_BODY = 4096


class MockServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, username, password, profile="x86", scenario="healthy", tls_context=None):
        if not username or not password:
            raise ValueError("mock credentials must be provided through environment variables")
        self.resources = build_inventory(profile, scenario)
        self.scenario = scenario
        self.username, self.password = username, password
        self.sessions = {}
        self.session_lock = threading.Lock()
        self.workers = threading.BoundedSemaphore(8)
        self.tls_context = tls_context
        super().__init__(("127.0.0.1", port), Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(3)
        if self.tls_context:
            try:
                connection = self.tls_context.wrap_socket(connection, server_side=True)
            except Exception:
                connection.close()
                raise
        return connection, address

    def process_request(self, request, client_address):
        if not self.workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.workers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.workers.release()

    def handle_error(self, request, client_address):
        # 测试目标不记录请求、凭据和可能含敏感内容的 traceback。
        return

    def valid_credentials(self, username, password):
        if not isinstance(username, str) or not isinstance(password, str):
            return False
        return hmac.compare_digest(username.encode(), self.username.encode()) and hmac.compare_digest(password.encode(), self.password.encode())

    def expire_sessions(self):
        now = time.monotonic()
        self.sessions = {token: value for token, value in self.sessions.items() if value[1] > now}


class Handler(BaseHTTPRequestHandler):
    server_version = "SyntheticRedfish/1.0"
    sys_version = ""

    def log_message(self, format, *args):
        """模拟服务不输出逐请求日志。"""
        return

    def reply(self, status, payload=None, headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("OData-Version", "4.0")
        self.send_header("X-Mock-Data", "synthetic-not-hardware-verified")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def error(self, status, code):
        self.reply(status, {"error": {"code": f"Base.1.0.{code}", "message": "Synthetic test response"}})

    def authenticated(self):
        if self.server.scenario == "unauthorized":
            return False
        with self.server.session_lock:
            self.server.expire_sessions()
            if self.headers.get("X-Auth-Token", "") in self.server.sessions:
                return True
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Basic "):
            return False
        try:
            user, password = base64.b64decode(authorization[6:], validate=True).decode().split(":", 1)
        except (ValueError, UnicodeError):
            return False
        return self.server.valid_credentials(user, password)

    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path.rstrip("/")
        if path != "/redfish/v1" and not self.authenticated():
            self.error(401, "NoValidSession")
            return
        if self.server.scenario == "unavailable" and path == "/redfish/v1/Systems":
            self.reply(503, {"error": {"code": "Base.1.0.ServiceTemporarilyUnavailable"}}, {"Retry-After": "1"})
            return
        if self.server.scenario == "partial" and path == "/redfish/v1/Systems/1/Storage":
            self.error(404, "ResourceMissingAtURI")
            return
        key = path + (f"?{url.query}" if url.query else "")
        payload = self.server.resources.get(key)
        if payload is None:
            self.error(404, "ResourceMissingAtURI")
        else:
            self.reply(200, payload)

    def do_POST(self):
        if self.path.rstrip("/") != SESSIONS:
            self.error(405, "ActionNotSupported")
            return
        if self.headers.get("Transfer-Encoding"):
            self.error(400, "MalformedJSON")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                self.error(413, "RequestEntityTooLarge")
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("object required")
        except (ValueError, UnicodeError):
            self.error(400, "MalformedJSON")
            return
        if self.server.scenario == "unauthorized" or not self.server.valid_credentials(payload.get("UserName"), payload.get("Password")):
            self.error(401, "NoValidSession")
            return
        with self.server.session_lock:
            self.server.expire_sessions()
            if len(self.server.sessions) >= 16:
                self.error(503, "SessionLimitExceeded")
                return
            token, session_id = secrets.token_urlsafe(24), secrets.token_hex(8)
            self.server.sessions[token] = (session_id, time.monotonic() + 60)
        location = f"{SESSIONS}/{session_id}"
        self.reply(
            201,
            {
                "@odata.id": location,
                "@odata.type": "#Session.v1_0_0.Session",
                "Id": session_id,
                "Name": "Synthetic session",
                "UserName": self.server.username,
            },
            {"X-Auth-Token": token, "Location": location},
        )

    def do_DELETE(self):
        if not self.path.startswith(SESSIONS + "/"):
            self.error(405, "ActionNotSupported")
            return
        if not self.authenticated():
            self.error(401, "NoValidSession")
            return
        token = self.headers.get("X-Auth-Token", "")
        with self.server.session_lock:
            session = self.server.sessions.get(token)
            if not session or self.path != f"{SESSIONS}/{session[0]}":
                self.error(403, "InsufficientPrivilege")
                return
            del self.server.sessions[token]
        self.reply(204)

    def do_PATCH(self):
        self.error(405, "ActionNotSupported")

    do_PUT = do_PATCH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18443)
    parser.add_argument("--profile", choices=PROFILES, default="x86")
    parser.add_argument("--scenario", choices=SCENARIOS, default="healthy")
    parser.add_argument("--cert")
    parser.add_argument("--key")
    parser.add_argument("--http", action="store_true", help="仅用于环回地址的明文协议测试")
    args = parser.parse_args()
    if args.http and (args.cert or args.key):
        parser.error("--http cannot be combined with --cert/--key")
    context = None
    if not args.http:
        if not args.cert or not args.key:
            parser.error("HTTPS requires --cert and --key; use --http explicitly for loopback tests")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(args.cert, args.key)
    user, password = os.getenv("REDFISH_MOCK_USERNAME", ""), os.getenv("REDFISH_MOCK_PASSWORD", "")
    if not user or not password:
        parser.error("set REDFISH_MOCK_USERNAME and REDFISH_MOCK_PASSWORD")
    with MockServer(args.port, user, password, args.profile, args.scenario, context) as server:
        print(
            f"Synthetic Redfish: {'http' if args.http else 'https'}://127.0.0.1:{server.server_port}/redfish/v1/ "
            f"profile={args.profile} scenario={args.scenario}",
            flush=True,
        )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Synthetic Redfish stopped.")


if __name__ == "__main__":
    main()
