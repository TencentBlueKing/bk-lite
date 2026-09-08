"""通过真实 HTTP/HTTPS 请求验证模拟目标；不代表生产插件或真机通过验收。"""

import base64
import json
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from mock_server import MAX_BODY, SESSIONS, MockServer


@contextmanager
def target(profile="x86", scenario="healthy", tls_context=None):
    # 明确的测试哨兵，仅存在于测试内存；CLI 服务不使用默认凭据。
    server = MockServer(0, "fixture-user", "fixture-password-sentinel", profile, scenario, tls_context)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def request(server, path, method="GET", auth=True, token=None, body=None, context=None, extra_headers=None):
    scheme = "https" if server.tls_context else "http"
    headers = dict(extra_headers or {})
    if auth:
        headers["Authorization"] = "Basic " + base64.b64encode(b"fixture-user:fixture-password-sentinel").decode()
    if token:
        headers["X-Auth-Token"] = token
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
    req = Request(f"{scheme}://127.0.0.1:{server.server_port}{path}", data=body, headers=headers, method=method)
    try:
        response = opener.open(req, timeout=2)
    except HTTPError as error:
        response = error
    with response:
        data = response.read()
        return response.status, dict(response.headers), json.loads(data) if data else None


def collection_members(server, path):
    members = []
    for _ in range(4):
        status, _, payload = request(server, path)
        if status != 200:
            raise AssertionError(f"collection returned {status}")
        members.extend(payload["Members"])
        path = payload.get("Members@odata.nextLink")
        if not path:
            return members
    raise AssertionError("unexpected pagination loop")


class MockTargetTests(unittest.TestCase):
    def test_both_profiles_can_be_read_twice_with_stable_identity_and_counts(self):
        for profile, expected_arch in [("x86", "x86-64"), ("arm", "ARM-A64")]:
            with self.subTest(profile=profile), target(profile) as server:
                snapshots = []
                for _ in range(2):
                    status, headers, root = request(server, "/redfish/v1/", auth=False)
                    self.assertEqual(status, 200)
                    self.assertIn("synthetic", headers["X-Mock-Data"])
                    systems = collection_members(server, root["Systems"]["@odata.id"])
                    self.assertEqual(len(systems), 1)
                    _, _, system = request(server, systems[0]["@odata.id"])
                    snapshots.append(system)
                    self.assertTrue(system["SerialNumber"].startswith("MOCK-"))
                    for key, count in [("Processors", 2), ("Memory", 8), ("EthernetInterfaces", 2)]:
                        members = collection_members(server, system[key]["@odata.id"])
                        self.assertEqual(len(members), count)
                        for member in members:
                            code, _, detail = request(server, member["@odata.id"])
                            self.assertEqual(code, 200)
                            if key == "Processors":
                                self.assertEqual(detail["InstructionSet"], expected_arch)
                    _, _, manager = request(server, system["Links"]["ManagedBy"][0]["@odata.id"])
                    _, _, management_nic = request(server, manager["EthernetInterfaces"]["@odata.id"] + "/1")
                    _, _, host_nic = request(server, system["EthernetInterfaces"]["@odata.id"] + "/1")
                    self.assertNotEqual(host_nic["MACAddress"], management_nic["MACAddress"])
                self.assertEqual(snapshots[0], snapshots[1])

    def test_storage_links_resolve_outside_system_and_volume_links_to_its_drives(self):
        with target(scenario="multi-system") as server:
            sizes, serials = [], []
            for member in collection_members(server, "/redfish/v1/Systems"):
                _, _, system = request(server, member["@odata.id"])
                serials.append(system["SerialNumber"])
                controllers = collection_members(server, system["Storage"]["@odata.id"])
                _, _, controller = request(server, controllers[0]["@odata.id"])
                total = 0
                for drive in controller["Drives"]:
                    self.assertTrue(drive["@odata.id"].startswith("/redfish/v1/Chassis/"))
                    status, _, disk = request(server, drive["@odata.id"])
                    self.assertEqual(status, 200)
                    total += disk["CapacityBytes"]
                volumes = collection_members(server, controller["Volumes"]["@odata.id"])
                _, _, volume = request(server, volumes[0]["@odata.id"])
                self.assertEqual(volume["Links"]["Drives"], controller["Drives"])
                self.assertEqual(volume["RAIDType"], "RAID1")
                sizes.append(total)
            self.assertEqual(len(set(serials)), 2)
            self.assertEqual(sizes, [1_920_000_000_000, 3_840_000_000_000])

    def test_pagination_keeps_all_eight_dimms(self):
        with target(scenario="paginated") as server:
            members = collection_members(server, "/redfish/v1/Systems/1/Memory")
            self.assertEqual(len({m["@odata.id"] for m in members}), 8)

    def test_failure_scenarios_are_http_failures_not_empty_success(self):
        cases = [
            ("partial", "/redfish/v1/Systems/1/Storage", 404),
            ("unauthorized", "/redfish/v1/Systems", 401),
            ("unavailable", "/redfish/v1/Systems", 503),
        ]
        for scenario, path, expected in cases:
            with self.subTest(scenario=scenario), target(scenario=scenario) as server:
                status, _, body = request(server, path)
                self.assertEqual(status, expected)
                self.assertIn("error", body)

    def test_missing_or_malformed_credentials_are_rejected(self):
        with target() as server:
            for header in [None, "Basic !!!", "Basic " + base64.b64encode(b"wrong:password").decode()]:
                status, _, _ = request(server, "/redfish/v1/Systems", auth=False, extra_headers={"Authorization": header} if header else {})
                self.assertEqual(status, 401)
            self.assertEqual(request(server, "/redfish/v1/missing")[0], 404)

    def test_session_creation_token_auth_logout_and_expiry(self):
        with target() as server:
            credentials = {"UserName": "fixture-user", "Password": "fixture-password-sentinel"}
            status, headers, body = request(server, SESSIONS, "POST", auth=False, body=credentials)
            self.assertEqual(status, 201)
            self.assertEqual(body["@odata.id"], headers["Location"])
            token = headers["X-Auth-Token"]
            self.assertEqual(request(server, "/redfish/v1/Systems", auth=False, token=token)[0], 200)
            self.assertEqual(request(server, headers["Location"] + "other", "DELETE", auth=False, token=token)[0], 403)
            self.assertEqual(request(server, headers["Location"], "DELETE", auth=False, token=token)[0], 204)
            self.assertEqual(request(server, "/redfish/v1/Systems", auth=False, token=token)[0], 401)
            _, headers, _ = request(server, SESSIONS, "POST", auth=False, body=credentials)
            token = headers["X-Auth-Token"]
            with server.session_lock:
                server.sessions[token] = ("expired", 0)
            self.assertEqual(request(server, "/redfish/v1/Systems", auth=False, token=token)[0], 401)

    def test_session_inputs_and_capacity_are_bounded(self):
        with target() as server:
            for body, expected in [
                (b"{", 400),
                ([], 400),
                ({"UserName": "wrong"}, 401),
                ({"UserName": [], "Password": {}}, 401),
                (b"x" * (MAX_BODY + 1), 413),
            ]:
                self.assertEqual(request(server, SESSIONS, "POST", auth=False, body=body)[0], expected)
            credentials = {"UserName": "fixture-user", "Password": "fixture-password-sentinel"}
            for _ in range(16):
                self.assertEqual(request(server, SESSIONS, "POST", auth=False, body=credentials)[0], 201)
            self.assertEqual(request(server, SESSIONS, "POST", auth=False, body=credentials)[0], 503)

    def test_hardware_writes_are_rejected_and_inventory_is_unchanged(self):
        with target() as server:
            path = "/redfish/v1/Systems/1"
            before = request(server, path)[2]
            for method, target_path in [("POST", path + "/Actions/ComputerSystem.Reset"), ("PATCH", path), ("PUT", path), ("DELETE", path)]:
                self.assertEqual(request(server, target_path, method, body={"PowerState": "Off"})[0], 405)
            self.assertEqual(request(server, path)[2], before)

    def test_no_implicit_credentials(self):
        with self.assertRaises(ValueError):
            MockServer(0, "", "")

    @unittest.skipUnless(shutil.which("openssl"), "openssl is needed to generate a temporary test certificate")
    def test_https_requires_trusted_certificate_and_checks_hostname(self):
        with tempfile.TemporaryDirectory(prefix="redfish-mock-tls-") as tmp:
            cert, key = str(Path(tmp) / "cert.pem"), str(Path(tmp) / "key.pem")
            subprocess.run(
                [
                    "openssl",
                    "req",
                    "-x509",
                    "-newkey",
                    "rsa:2048",
                    "-nodes",
                    "-days",
                    "1",
                    "-keyout",
                    key,
                    "-out",
                    cert,
                    "-config",
                    str(Path(__file__).with_name("tls.cnf")),
                ],
                check=True,
                capture_output=True,
                timeout=20,
            )
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(cert, key)
            with target(tls_context=context) as server:
                with self.assertRaises(URLError):
                    request(server, "/redfish/v1/", auth=False)
                trusted = ssl.create_default_context(cafile=cert)
                self.assertTrue(trusted.check_hostname)
                self.assertEqual(request(server, "/redfish/v1/", context=trusted)[0], 200)


if __name__ == "__main__":
    unittest.main()
