from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from core.collection.enums import AccessProbeStatus
from plugins.inputs.ssl_cer.ssl_cer_info import SslCerInfo, parse_der_certificate


def _self_signed_der(*, not_before: datetime, not_after: datetime, issuer_cn: str) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def test_parse_der_certificate_maps_issuer_and_validity():
    der = _self_signed_der(
        not_before=datetime(2023, 1, 30, 8, 0, tzinfo=timezone.utc),
        not_after=datetime(2024, 2, 28, 7, 59, 59, tzinfo=timezone.utc),
        issuer_cn="DigiCert Secure Site Pro CN CA G3",
    )
    parsed = parse_der_certificate(der)
    assert parsed["issuer"] == "CN=DigiCert Secure Site Pro CN CA G3"
    assert parsed["create_time"] == "2023-01-30 08:00:00"
    assert parsed["expired_time"] == "2024-02-28 07:59:59"


@pytest.mark.asyncio
async def test_list_all_resources_keeps_inst_name_and_skips_verify():
    der = _self_signed_der(
        not_before=datetime(2023, 1, 1, tzinfo=timezone.utc),
        not_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        issuer_cn="Test CA",
    )
    collector = SslCerInfo(
        {
            "host": "www.example.com",
            "port": 443,
            "ssl_cer_targets": '[{"inst_name":"rex-test","domain":"www.example.com"}]',
        }
    )
    with patch.object(SslCerInfo, "_fetch_peer_der", return_value=der):
        payload = await collector.list_all_resources()
    row = payload["result"]["ssl_cer"][0]
    assert payload["success"] is True
    assert row["inst_name"] == "rex-test"
    assert row["domain"] == "www.example.com"
    assert row["issuer"] == "CN=Test CA"
    assert "collect_status" not in row


@pytest.mark.asyncio
async def test_empty_domain_returns_domain_missing_without_handshake():
    collector = SslCerInfo(
        {
            "host": "missing.example",
            "ssl_cer_targets": '[{"inst_name":"empty-domain","domain":""}]',
        }
    )
    with patch.object(SslCerInfo, "_fetch_peer_der", side_effect=AssertionError("must not handshake")):
        payload = await collector.list_all_resources()
    row = payload["result"]["ssl_cer"][0]
    assert row["collect_status"] == "failed"
    assert row["collect_error"] == "domain_missing"


@pytest.mark.asyncio
async def test_handshake_error_maps_to_tls_handshake_failed():
    collector = SslCerInfo({"host": "bad.example", "ssl_cer_targets": "[]"})
    with patch.object(SslCerInfo, "_fetch_peer_der", side_effect=OSError("timed out")):
        payload = await collector.list_all_resources()
    row = payload["result"]["ssl_cer"][0]
    assert row["collect_status"] == "failed"
    assert row["collect_error"] == "tls_handshake_failed"
    assert row["inst_name"] == "bad.example"


@pytest.mark.asyncio
async def test_probe_empty_host_returns_target_unreachable():
    result = await SslCerInfo({"host": ""}).probe()
    assert result.status == AccessProbeStatus.TARGET_UNREACHABLE
    assert result.error_code == "domain_missing"


@pytest.mark.asyncio
async def test_probe_with_host_returns_ready():
    result = await SslCerInfo({"host": "www.example.com"}).probe()
    assert result.status == AccessProbeStatus.READY


@pytest.mark.asyncio
async def test_matched_host_does_not_attach_empty_domain_rows():
    der = _self_signed_der(
        not_before=datetime(2023, 1, 1, tzinfo=timezone.utc),
        not_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        issuer_cn="Test CA",
    )
    collector = SslCerInfo(
        {
            "host": "www.example.com",
            "ssl_cer_targets": [
                {"inst_name": "ok", "domain": "www.example.com"},
                {"inst_name": "empty-domain", "domain": ""},
            ],
        }
    )
    with patch.object(SslCerInfo, "_fetch_peer_der", return_value=der):
        payload = await collector.list_all_resources()
    rows = payload["result"]["ssl_cer"]
    assert len(rows) == 1
    assert rows[0]["inst_name"] == "ok"
    assert rows[0]["issuer"] == "CN=Test CA"
    assert "collect_status" not in rows[0]


@pytest.mark.asyncio
async def test_handshake_failure_does_not_rewrite_prior_success_rows():
    der = _self_signed_der(
        not_before=datetime(2023, 1, 1, tzinfo=timezone.utc),
        not_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
        issuer_cn="Test CA",
    )
    collector = SslCerInfo(
        {
            "host": "www.example.com",
            "ssl_cer_targets": [
                {"inst_name": "a", "domain": "www.example.com"},
                {"inst_name": "b", "domain": "www.example.com"},
            ],
        }
    )
    with patch.object(SslCerInfo, "_fetch_peer_der", side_effect=[der, OSError("timed out")]):
        payload = await collector.list_all_resources()
    rows = payload["result"]["ssl_cer"]
    assert payload["success"] is True
    assert rows[0]["inst_name"] == "a"
    assert "collect_status" not in rows[0]
    assert rows[0]["issuer"] == "CN=Test CA"
    assert rows[1]["inst_name"] == "b"
    assert rows[1]["collect_status"] == "failed"
    assert rows[1]["collect_error"] == "tls_handshake_failed"
