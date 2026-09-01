import base64
import io
import json
import os
import re
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml
from cryptography import x509
from cryptography.x509.oid import ExtensionOID

PROXY_SCRIPT = Path(__file__).resolve().parents[1] / "proxy.sh"


@pytest.fixture(scope="module")
def certificate_authority(tmp_path_factory):
    cert_dir = tmp_path_factory.mktemp("proxy-ca")
    key_path = cert_dir / "ca.key"
    cert_path = cert_dir / "ca.crt"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key_path),
            "-out",
            str(cert_path),
            "-days",
            "1",
            "-subj",
            "/CN=proxy-test-ca",
        ],
        check=True,
        capture_output=True,
    )
    return key_path, cert_path


def _generate_proxy_archive(proxy_address, certificate_authority):
    key_path, cert_path = certificate_authority
    payload = {
        "node_id": "proxy-test",
        "zone_id": "2",
        "zone_name": "proxy-test",
        "server_url": "https://server.example.com",
        "nats_url": f"nats://{proxy_address}:4222",
        "nats_username": "user",
        "nats_password": "password",
        "api_token": "token",
        "redis_password": "redis-password",
        "proxy_ip": proxy_address,
        "nats_monitor_username": "monitor",
        "nats_monitor_password": "monitor-password",
        "apm_nats_username": "apm_region_2",
        "apm_nats_password": "apm-password",
        "traefik_web_port": "443",
    }
    env = os.environ | {
        "PROXY_CA_KEY_PATH": str(key_path),
        "PROXY_CA_CERT_PATH": str(cert_path),
    }
    result = subprocess.run(
        [str(PROXY_SCRIPT), json.dumps(payload)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    install_script = json.loads(result.stdout)["install_script"]
    archive_match = re.search(r'^ARCHIVE="([^"]+)"$', install_script, re.MULTILINE)
    assert archive_match
    archive_bytes = base64.b64decode(archive_match.group(1))
    return tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz")


@pytest.mark.parametrize(
    ("proxy_address", "expected_dns", "expected_ip"),
    [
        ("proxy.example.com", "proxy.example.com", None),
        ("10.0.0.8", None, "10.0.0.8"),
        ("[2001:db8::8]", None, "2001:db8::8"),
    ],
)
def test_proxy_certificate_contains_typed_san_and_valid_nats_route(
    proxy_address,
    expected_dns,
    expected_ip,
    certificate_authority,
):
    with _generate_proxy_archive(proxy_address, certificate_authority) as archive:
        certificate = x509.load_pem_x509_certificate(archive.extractfile("./conf/certs/proxy.crt").read())
        san = certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        nats_config = archive.extractfile("./conf/nats/nats.conf").read().decode()
        compose_config = archive.extractfile("./docker-compose.yaml").read().decode()
        generated_env = archive.extractfile("./.env").read().decode()
        regional_config = archive.extractfile("./conf/apm/regional.yaml").read().decode()

    if expected_dns:
        assert expected_dns in san.get_values_for_type(x509.DNSName)
    if expected_ip:
        assert expected_ip in {str(address) for address in san.get_values_for_type(x509.IPAddress)}
    assert f'url: "tls://{proxy_address}:4222"' in nats_config
    assert 'publish = ["apm.traces.2"]' in nats_config
    assert 'subscribe = ["_INBOX.>"]' in nats_config
    assert "apm-regional-collector:" in compose_config
    assert "APM_NATS_USERNAME=apm_region_2" in generated_env
    assert "APM_NATS_PASSWORD=apm-password" in generated_env
    assert "trace_guard:" in regional_config


def test_proxy_compose_injects_zone_instance_id_for_region_services(
    certificate_authority,
):
    with _generate_proxy_archive("10.0.0.8", certificate_authority) as archive:
        compose_config = yaml.safe_load(archive.extractfile("./docker-compose.yaml").read().decode())
        generated_env = archive.extractfile("./.env").read().decode()

    assert "ZONE_NAME=proxy-test" in generated_env

    services = compose_config["services"]
    stargazer = services["stargazer"]
    nats_executor = services["nats-executor"]

    # server 端按 {zone_name}_stargazer / {zone_name} 探活，两个服务都必须拿到 ZONE_NAME
    assert stargazer["environment"]["NATS_INSTANCE_ID"] == "${ZONE_NAME}"
    assert "NATS_INSTANCE_ID=${ZONE_NAME}" in nats_executor["environment"]

    assert stargazer["restart"] == "always"


def test_bootstrap_uses_rendered_nats_admin_user(certificate_authority):
    """bootstrap.sh 必须用 .env 渲染出的管理员账号连 NATS，不能写死 admin。"""
    with _generate_proxy_archive("10.0.0.8", certificate_authority) as archive:
        bootstrap = archive.extractfile("./bootstrap.sh").read().decode()
        generated_env = archive.extractfile("./.env").read().decode()

    # payload nats_username 渲染为 .env 的 NATS_ADMIN_USERNAME
    assert "NATS_ADMIN_USERNAME=user" in generated_env
    assert '--user "${NATS_ADMIN_USERNAME}"' in bootstrap
    assert "--user admin" not in bootstrap
