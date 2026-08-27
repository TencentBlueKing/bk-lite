from __future__ import annotations

import json
import os
import random
import socket
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from opentelemetry import propagate, trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

SERVICE = os.environ.get("APM_DEMO_SERVICE", "storefront")
NAMESPACE = os.environ.get("APM_DEMO_NAMESPACE", "apm-demo-shop")
ENVIRONMENT = os.environ.get("APM_DEMO_ENVIRONMENT", "local")
VERSION = os.environ.get("APM_DEMO_VERSION", "1.0.0")
INSTANCE_ID = os.environ.get("APM_INSTANCE_ID") or socket.gethostname()

provider = TracerProvider(
    resource=Resource.create(
        {
            "service.namespace": NAMESPACE,
            "service.name": f"demo-{SERVICE}",
            "service.instance.id": INSTANCE_ID,
            "service.version": VERSION,
            "deployment.environment": ENVIRONMENT,
        }
    )
)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("bk-lite.apm.demo", VERSION)


def pause(minimum_ms: int, maximum_ms: int) -> None:
    time.sleep(random.uniform(minimum_ms, maximum_ms) / 1000)


def response(status: int, payload: dict) -> tuple[int, dict]:
    return status, payload


def downstream(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    parsed = urlsplit(url)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    attributes = {
        "http.request.method": method,
        "server.address": parsed.hostname or "unknown",
        "server.port": parsed.port or 80,
        "url.full": url,
    }
    data = json.dumps(body).encode() if body is not None else None
    span_name = f"{method} {parsed.path}"
    with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT, attributes=attributes) as span:
        propagate.inject(headers)
        try:
            request = urllib.request.Request(url, data=data, headers=headers, method=method)
            with urllib.request.urlopen(request, timeout=3) as result:
                status = result.status
                payload = json.loads(result.read() or b"{}")
        except urllib.error.HTTPError as error:
            status = error.code
            payload = json.loads(error.read() or b"{}")
        except Exception as error:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, type(error).__name__))
            span.set_attribute("error.type", type(error).__name__)
            return HTTPStatus.BAD_GATEWAY, {"error": "downstream_unavailable"}
        span.set_attribute("http.response.status_code", status)
        if status >= 500:
            span.set_status(Status(StatusCode.ERROR, str(payload.get("error", "downstream_error"))))
            span.set_attribute("error.type", str(payload.get("error", "downstream_error")))
        else:
            span.set_status(Status(StatusCode.OK))
        return status, payload


def storefront(method: str, path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
    scenario = query.get("scenario", ["normal"])[0]
    if method == "GET" and path == "/api/products":
        status, catalog = downstream("GET", f"{os.environ['APM_DEMO_CATALOG_URL']}/products?scenario={scenario}")
        with tracer.start_as_current_span("render.product-list"):
            pause(4, 14)
        return response(status, {"page": "products", "catalog": catalog})
    if method == "POST" and path == "/api/checkout":
        status, order = downstream(
            "POST",
            f"{os.environ['APM_DEMO_ORDERS_URL']}/orders?scenario={scenario}",
            {"cart_id": "demo-cart", "amount": 129.90},
        )
        return response(status, {"checkout": "accepted" if status < 500 else "failed", "order": order})
    if method == "GET" and path == "/api/profile":
        with tracer.start_as_current_span("cache GET profile", kind=SpanKind.CLIENT) as span:
            span.set_attribute("db.system", "redis")
            span.set_attribute("db.operation.name", "GET")
            pause(8, 25)
            span.set_status(Status(StatusCode.OK))
        return response(HTTPStatus.OK, {"customer": "demo-user", "tier": "gold"})
    return response(HTTPStatus.NOT_FOUND, {"error": "route_not_found"})


def catalog(method: str, path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
    if method != "GET" or path != "/products":
        return response(HTTPStatus.NOT_FOUND, {"error": "route_not_found"})
    scenario = query.get("scenario", ["normal"])[0]
    with tracer.start_as_current_span("SELECT featured products", kind=SpanKind.CLIENT) as span:
        span.set_attribute("db.system", "mysql")
        span.set_attribute("db.name", "shop")
        span.set_attribute("server.address", "mysql.demo.svc")
        span.set_attribute("server.port", 3306)
        span.set_attribute("db.operation.name", "SELECT")
        pause(12, 35)
        span.set_status(Status(StatusCode.OK))
    status, stock = downstream("GET", f"{os.environ['APM_DEMO_INVENTORY_URL']}/stock?scenario={scenario}")
    return response(status, {"items": 12, "stock": stock})


def orders(method: str, path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
    if method != "POST" or path != "/orders":
        return response(HTTPStatus.NOT_FOUND, {"error": "route_not_found"})
    scenario = query.get("scenario", ["normal"])[0]
    reserve_status, reserve = downstream("POST", f"{os.environ['APM_DEMO_INVENTORY_URL']}/reserve?scenario={scenario}", {"sku": "demo-1"})
    if reserve_status >= 500:
        return response(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "inventory_reservation_failed", "detail": reserve})
    payment_status, payment = downstream("POST", f"{os.environ['APM_DEMO_PAYMENT_URL']}/charge?scenario={scenario}", {"amount": 129.90})
    if payment_status >= 500:
        return response(HTTPStatus.BAD_GATEWAY, {"error": "payment_declined", "detail": payment})
    with tracer.start_as_current_span("INSERT order", kind=SpanKind.CLIENT) as span:
        span.set_attribute("db.system", "postgresql")
        span.set_attribute("db.operation.name", "INSERT")
        pause(15, 45)
        span.set_status(Status(StatusCode.OK))
    return response(HTTPStatus.CREATED, {"order_id": f"demo-{random.randint(1000, 9999)}"})


def inventory(method: str, path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
    scenario = query.get("scenario", ["normal"])[0]
    if method == "GET" and path == "/stock":
        if scenario == "inventory-failure":
            pause(30, 60)
            return response(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "inventory_backend_timeout"})
        pause(10, 40)
        return response(HTTPStatus.OK, {"available": 42})
    if method == "POST" and path == "/reserve":
        if scenario == "slow":
            with tracer.start_as_current_span("inventory.lock.wait"):
                pause(420, 620)
        else:
            pause(20, 55)
        return response(HTTPStatus.OK, {"reserved": True})
    return response(HTTPStatus.NOT_FOUND, {"error": "route_not_found"})


def payment(method: str, path: str, query: dict[str, list[str]]) -> tuple[int, dict]:
    if method != "POST" or path != "/charge":
        return response(HTTPStatus.NOT_FOUND, {"error": "route_not_found"})
    scenario = query.get("scenario", ["normal"])[0]
    with tracer.start_as_current_span("payment.provider.authorize", kind=SpanKind.CLIENT) as span:
        span.set_attribute("rpc.system", "demo-payment-gateway")
        if scenario == "payment-failure":
            pause(90, 180)
            span.set_status(Status(StatusCode.ERROR, "card_declined"))
            span.set_attribute("error.type", "card_declined")
            return response(HTTPStatus.BAD_GATEWAY, {"error": "card_declined"})
        pause(35, 90)
        span.set_status(Status(StatusCode.OK))
    return response(HTTPStatus.OK, {"transaction": f"txn-{random.randint(10000, 99999)}"})


ROUTES = {
    "storefront": storefront,
    "catalog": catalog,
    "orders": orders,
    "inventory": inventory,
    "payment": payment,
}


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "BkLiteApmDemo/1.0"

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length:
            self.rfile.read(min(content_length, 64 * 1024))
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health":
            self._write(HTTPStatus.OK, {"status": "ok", "service": SERVICE})
            return
        route = ROUTES[SERVICE]
        context = propagate.extract({key.lower(): value for key, value in self.headers.items()})
        span_name = f"{method} {parsed.path}"
        attributes = {
            "http.request.method": method,
            "http.route": parsed.path,
            "url.path": parsed.path,
            "server.address": SERVICE,
        }
        with tracer.start_as_current_span(span_name, context=context, kind=SpanKind.SERVER, attributes=attributes) as span:
            try:
                status, payload = route(method, parsed.path, parse_qs(parsed.query))
            except Exception as error:
                span.record_exception(error)
                span.set_attribute("error.type", type(error).__name__)
                status, payload = HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "unhandled_demo_error"}
            span.set_attribute("http.response.status_code", int(status))
            if status >= 500:
                error_type = str(payload.get("error", "server_error"))
                span.set_attribute("error.type", error_type)
                span.set_status(Status(StatusCode.ERROR, error_type))
            else:
                span.set_status(Status(StatusCode.OK))
            self._write(status, payload)

    def _write(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{SERVICE}: {format % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8080), DemoHandler)
    print(f"APM demo service ready: {SERVICE} ({INSTANCE_ID})", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        provider.shutdown()
