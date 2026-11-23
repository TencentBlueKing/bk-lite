import asyncio
import ipaddress
import json
import ssl
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from rest_framework.exceptions import ValidationError

from apps.core.utils.safe_requests import SafeRequestsError
from apps.opspilot.metis.llm.agent.deep_agent import DeepAgentRequest
from apps.opspilot.metis.llm.common.llm_client_factory import LLMClientFactory
from apps.opspilot.models.model_provider_mgmt import LLMModel, ModelVendor, SkillTypeChoices
from apps.opspilot.serializers.model_vendor_serializer import ModelVendorSerializer
from apps.opspilot.services.chat_service import ChatService
from apps.opspilot.services.model_vendor_sync_service import ModelVendorSyncService
from apps.opspilot.viewsets.model_vendor_view import ModelVendorViewSet


@pytest.fixture(scope="module")
def tls_vendor_url(tmp_path_factory):
    directory = tmp_path_factory.mktemp("vendor-tls")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test vendor")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    (directory / "cert").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory / "key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": "demo"}]}).encode())

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            if self.path.endswith("/messages"):
                payload = {
                    "id": "msg",
                    "type": "message",
                    "role": "assistant",
                    "model": "demo",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            else:
                payload = {
                    "id": "msg",
                    "model": "demo",
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                }
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(directory / "cert", directory / "key")
        server.socket = ctx.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"https://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.django_db
def test_vendor_setting_round_trip_and_certificate_verification(tls_vendor_url):
    vendor = ModelVendor.objects.create(name="local", api_base=tls_vendor_url, api_key="test", team=[1])
    for skip in (False, True, False):
        serializer = ModelVendorSerializer(vendor, data={"skip_ssl_verify": skip}, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        vendor.refresh_from_db()
        assert ModelVendorSerializer(vendor).data["skip_ssl_verify"] is skip
        if skip:
            ModelVendorSyncService.sync_vendor_models(vendor)
            assert vendor.llm_models.get().model == "demo"
        else:
            with pytest.raises(SafeRequestsError, match="CERTIFICATE_VERIFY_FAILED"):
                ModelVendorSyncService.sync_vendor_models(vendor)


@pytest.mark.django_db
@pytest.mark.parametrize("vendor,protocol", [("other", "openai"), ("anthropic", "anthropic"), ("other", "anthropic")])
def test_chat_with_self_signed_vendor(tls_vendor_url, vendor, protocol, monkeypatch, mocker):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    configured = ModelVendor.objects.create(
        name="private", vendor_type=vendor, protocol_type=protocol, api_base=tls_vendor_url, api_key="test", skip_ssl_verify=True
    )
    model = LLMModel.objects.create(name="demo", vendor=configured)
    mocker.patch("apps.opspilot.services.chat_service.consume_pending_question", return_value=None)
    params = {
        "user_id": "tester",
        "user_message": "test",
        "skill_prompt": "",
        "chat_history": [],
        "skill_type": SkillTypeChoices.BASIC_TOOL,
    }
    chat_kwargs, _, _ = ChatService.format_chat_server_kwargs(params, model)
    request = DeepAgentRequest(**chat_kwargs)
    client = LLMClientFactory.create_client(request, disable_stream=True)
    for message in (client.invoke("test"), asyncio.run(client.ainvoke("test"))):
        answer = message.content
        assert answer == "ok" or (isinstance(answer, list) and answer[0]["text"] == "ok")


@pytest.mark.django_db
@pytest.mark.parametrize("protocol", ["openai", "anthropic"])
def test_connection_uses_current_form_value_before_save(tls_vendor_url, protocol):
    vendor = ModelVendor.objects.create(name="vendor", api_base=tls_vendor_url, api_key="test", team=[1], skip_ssl_verify=True)
    payload = {"api_base": tls_vendor_url, "original_id": vendor.id, "password_changed": False, "protocol_type": protocol}
    user = SimpleNamespace(locale="en", group_list=[1, 2])
    for override, expected in [({}, True), ({"skip_ssl_verify": False}, False), ({"skip_ssl_verify": True}, True)]:
        request = SimpleNamespace(data={**payload, **override}, user=user, COOKIES={"current_team": "1"})
        response = ModelVendorViewSet.test_connection.__wrapped__(ModelVendorViewSet(), request)
        assert json.loads(response.content)["result"] is expected
    vendor.refresh_from_db()
    assert vendor.skip_ssl_verify is True
    other_team = SimpleNamespace(data=payload, user=user, COOKIES={"current_team": "2"})
    with pytest.raises(ValidationError, match="original_id"):
        ModelVendorViewSet.test_connection.__wrapped__(ModelVendorViewSet(), other_team)
