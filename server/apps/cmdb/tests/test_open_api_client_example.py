import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apps.cmdb.examples.open_api_client import CMDBOpenAPIClient


class _OpenAPIHandler(BaseHTTPRequestHandler):
    requests = []

    def log_message(self, format, *args):
        return

    def _respond(self, status, data):
        body = json.dumps({"result": True, "data": data, "message": "", "code": "ok"}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.__class__.requests.append(("GET", self.path, self.headers, None))
        self._respond(
            200,
            {"count": 1, "page": 1, "page_size": 20, "items": [{"inst_id": 11, "inst_name": "host-01"}]},
        )

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.__class__.requests.append(("POST", self.path, self.headers, body))
        self._respond(201, {"inst_id": 12, **body})


@contextmanager
def _open_api_server():
    _OpenAPIHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OpenAPIHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_list_instances_sends_real_http_request_with_header_and_filters():
    with _open_api_server() as base_url:
        client = CMDBOpenAPIClient(base_url, "test-secret")
        data = client.list_instances(
            "host",
            filters=[{"field": "inst_name", "type": "str*", "value": "host"}],
        )

    method, path, headers, body = _OpenAPIHandler.requests[0]
    assert method == "GET"
    assert path.startswith("/api/v1/cmdb/api/open/models/host/instances?")
    assert "%22type%22%3A+%22str%2A%22" in path
    assert headers["Api-Authorization"] == "test-secret"
    assert body is None
    assert data["items"][0]["inst_id"] == 11


def test_create_instance_sends_real_json_request_and_returns_data():
    with _open_api_server() as base_url:
        client = CMDBOpenAPIClient(base_url, "test-secret")
        data = client.create_instance("host", {"inst_name": "host-02", "ip": "10.0.0.2"})

    method, path, headers, body = _OpenAPIHandler.requests[0]
    assert method == "POST"
    assert path == "/api/v1/cmdb/api/open/models/host/instances"
    assert headers["Api-Authorization"] == "test-secret"
    assert headers.get_content_type() == "application/json"
    assert body == {"inst_name": "host-02", "ip": "10.0.0.2"}
    assert data["inst_id"] == 12
