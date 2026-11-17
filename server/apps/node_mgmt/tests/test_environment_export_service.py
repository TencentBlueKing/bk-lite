"""Export transaction and sensitive artifact contract; only object storage is stubbed."""

import base64
import hashlib
import io
import json
import zipfile

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.node_mgmt.models import CloudRegion, EnvironmentInstallGrant, PackageVersion, SidecarEnv
from apps.node_mgmt.services.environment_bundle import export_environment_bundle
from apps.node_mgmt.services.package import PackageService
from apps.system_mgmt.models import SystemAPIToken

pytestmark = pytest.mark.django_db


@pytest.fixture
def export_inputs(tmp_path, monkeypatch):
    key = Ed25519PrivateKey.generate()
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    artifacts = {
        "ENVIRONMENT_INSTALLER_LAUNCHER_FILE": b"\x7fELF" + base64.b64encode(public),
        "ENVIRONMENT_INSTALLER_WORKER_FILE": b"\x7fELFworker",
        "ENVIRONMENT_INSTALLER_SIGNING_KEY_FILE": key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ),
    }
    for name, content in artifacts.items():
        path = tmp_path / name
        path.write_bytes(content)
        monkeypatch.setenv(name, str(path))
    region = CloudRegion.objects.create(name="export-test")
    for name, value in {
        "NODE_SERVER_URL": "https://platform.example",
        "NATS_SERVERS": "tls://nats.example:4222",
        "NATS_ADMIN_USERNAME": "test-executor",
        "NATS_ADMIN_PASSWORD": "executor-secret",
        "NATS_PROTOCOL": "tls",
        "NATS_INSTALLER_USERNAME": "test-download",
        "NATS_INSTALLER_PASSWORD": "test-only",
    }.items():
        SidecarEnv.objects.create(cloud_region=region, key=name, value=value)
    package = PackageVersion.objects.create(
        type="controller", object="Controller", os="linux", cpu_architecture="x86_64", name="controller.zip", version="test-v1", sha256="c" * 64
    )
    from apps.node_mgmt.models import Collector

    Collector.objects.create(
        id="natsexecutor_linux",
        name="NATS-Executor",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        service_type="exec",
        executable_path="/opt/fusion-collectors/bin/nats-executor",
        execute_parameters="--config %s",
        controller_default_run=True,
        default_config={"nats": 'nats_urls: "${NATS_PROTOCOL}://${NATS_ADMIN_USERNAME}:${NATS_ADMIN_PASSWORD}@${NATS_SERVERS}"'},
    )
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr("fusion-collectors/install.sh", b"#!/bin/sh\n# BK_LITE_CONFIG_PREPARED\n")
        archive.writestr("fusion-collectors/bin/nats-executor", b"\x7fELF\x02\x01" + b"\x00" * 12 + b"\x3e\x00" + b"executor")
    package.sha256 = hashlib.sha256(body.getvalue()).hexdigest()
    package.save(update_fields=["sha256"])
    monkeypatch.setattr(PackageService, "download_file_streaming", lambda package: (iter([body.getvalue()]), "controller.zip"))
    monkeypatch.setattr(PackageService, "resolve_existing_file_path", lambda package: "test/controller.zip")
    return dict(
        owner="installer",
        domain="test",
        organization=1,
        cloud_region_id=region.pk,
        package_id=package.pk,
        valid_days=1,
        max_nodes=2,
        platform_ca="",
        management_cidr="192.0.2.0/24",
        required_free_bytes=1024 * 1024 * 1024,
        timeout_seconds=900,
    )


def test_export_contains_scoped_secret_without_storing_plaintext(export_inputs):
    grant, artifact = export_environment_bundle(**export_inputs)
    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["grant_id"] == str(grant.pk)
    assert manifest["team"] == 1
    assert manifest["package_sha256"] == PackageVersion.objects.get(pk=export_inputs["package_id"]).sha256
    assert grant.token.secret_hash == SystemAPIToken.hash_secret(manifest["installation_key"])
    assert grant.token.scope["endpoints"] == ["POST node-mgmt/environment-install", "POST node-mgmt/environment-install-status"]
    assert manifest["installation_key"] not in str(grant.__dict__)


def test_failed_bundle_assembly_does_not_leave_live_grant(export_inputs, monkeypatch):
    from apps.node_mgmt.services import environment_bundle

    def fail(*args):
        raise ValueError("assembly failed")

    monkeypatch.setattr(environment_bundle, "assemble_run", fail)
    with pytest.raises(ValueError, match="assembly failed"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()
    assert not SystemAPIToken.objects.filter(system_id="node-environment-install").exists()


def test_export_refuses_legacy_admin_download_credentials(export_inputs):
    SidecarEnv.objects.filter(cloud_region_id=export_inputs["cloud_region_id"], key="NATS_INSTALLER_USERNAME").delete()
    with pytest.raises(ValueError, match="Dedicated"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()


def test_export_precheck_failure_returns_a_stable_error_code(monkeypatch):
    from types import SimpleNamespace

    from apps.node_mgmt.views import environment_install

    def reject(**_kwargs):
        raise ValueError("package digest required")

    monkeypatch.setattr(environment_install, "export_environment_bundle", reject)
    monkeypatch.setattr(environment_install, "_validate_install_target_organizations", lambda *_args, **_kwargs: None)
    request = SimpleNamespace(
        user=SimpleNamespace(username="installer", domain="test", locale="en", permission={"node": {"cloud_region_node-Edit"}}, is_superuser=False),
        data={
            "organization": 1,
            "cloud_region_id": 1,
            "package_id": 1,
            "valid_days": 7,
            "max_nodes": 1,
            "required_free_bytes": 128 * 1024 * 1024,
            "timeout_seconds": 60,
        },
    )
    payload = json.loads(environment_install.EnvironmentInstallViewSet().export(request).content)
    assert payload["result"] is False
    assert payload["data"]["error_code"] == "package_digest_missing"
    assert "package digest" not in payload["message"]


def test_admin_without_edit_permission_cannot_export():
    from types import SimpleNamespace

    from apps.node_mgmt.views.environment_install import EnvironmentInstallViewSet

    request = SimpleNamespace(user=SimpleNamespace(username="viewer", domain="test", locale="en", permission={}, is_superuser=False), data={})
    assert EnvironmentInstallViewSet().export(request).status_code == 403
    assert not EnvironmentInstallGrant.objects.exists()


def test_grant_management_never_crosses_current_organization(export_inputs, monkeypatch):
    from types import SimpleNamespace

    from apps.node_mgmt.views import environment_install

    grant, _ = export_environment_bundle(**export_inputs)
    request = SimpleNamespace(
        user=SimpleNamespace(username="installer", domain="test", locale="en", permission={"node": {"cloud_region_node-Edit"}}, is_superuser=False),
        data={"grant_id": str(grant.id)},
    )
    monkeypatch.setattr(environment_install, "resolve_current_team_data_scope", lambda _: SimpleNamespace(current_team=2))
    view = environment_install.EnvironmentInstallViewSet()
    assert json.loads(view.grants(request).content)["data"] == {"count": 0, "items": []}
    assert view.results(request).status_code == 403
    assert view.revoke(request).status_code == 403
    grant.token.refresh_from_db()
    assert grant.token.enabled
    monkeypatch.setattr(environment_install, "resolve_current_team_data_scope", lambda _: SimpleNamespace(current_team=1))
    assert view.revoke(request).status_code == 200
    grant.token.refresh_from_db()
    assert not grant.token.enabled


def test_export_signs_required_component_selection(export_inputs):
    from apps.node_mgmt.models import Collector

    collector = Collector.objects.create(
        id="test-telegraf",
        name="Telegraf",
        service_type="exec",
        node_operating_system="linux",
        cpu_architecture="x86_64",
        executable_path="/opt/fusion-collectors/bin/telegraf",
        execute_parameters="--config",
        controller_default_run=True,
        default_config={"nats": "test"},
    )
    grant, artifact = export_environment_bundle(**export_inputs, required_collectors=[collector.id])
    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["required_components"] == [{"id": "natsexecutor_linux", "name": "NATS-Executor"}, {"id": collector.id, "name": "Telegraf"}]
    assert grant.required_components == manifest["required_components"]


def test_export_automatically_includes_cloud_region_platform_ca(export_inputs):
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.x509.oid import NameOID

    key = Ed25519PrivateKey.generate()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Environment export test CA")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, algorithm=None)
    )
    ca = certificate.public_bytes(serialization.Encoding.PEM).decode()
    SidecarEnv.objects.create(cloud_region_id=export_inputs["cloud_region_id"], key="NODE_SERVER_CA", value=ca)
    _, artifact = export_environment_bundle(**export_inputs)
    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["platform_ca"] == ca


def test_invalid_cloud_region_ca_prevents_export_without_creating_grant(export_inputs):
    SidecarEnv.objects.create(cloud_region_id=export_inputs["cloud_region_id"], key="NODE_SERVER_CA", value="not-a-certificate")
    with pytest.raises(ValueError):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()
    assert not SystemAPIToken.objects.filter(system_id="node-environment-install").exists()


def test_export_always_enables_executor_without_optional_components(export_inputs):
    grant, artifact = export_environment_bundle(**export_inputs)
    with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["required_components"] == [{"id": "natsexecutor_linux", "name": "NATS-Executor"}]
    assert grant.required_components == manifest["required_components"]


@pytest.mark.parametrize("key", ["NATS_ADMIN_USERNAME", "NATS_ADMIN_PASSWORD"])
def test_export_missing_executor_credentials_creates_no_grant(export_inputs, key):
    SidecarEnv.objects.filter(cloud_region_id=export_inputs["cloud_region_id"], key=key).delete()
    with pytest.raises(ValueError, match="Executor"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()


def test_export_missing_executor_binary_creates_no_grant(export_inputs, monkeypatch):
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr("fusion-collectors/install.sh", b"# BK_LITE_CONFIG_PREPARED")
        archive.writestr("fusion-collectors/bin/telegraf", b"not-an-executor")
    package = PackageVersion.objects.get(pk=export_inputs["package_id"])
    package.sha256 = hashlib.sha256(body.getvalue()).hexdigest()
    package.save(update_fields=["sha256"])
    monkeypatch.setattr(PackageService, "download_file_streaming", lambda package: (iter([body.getvalue()]), "controller.zip"))
    with pytest.raises(ValueError, match="Executor"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()


def test_export_missing_executor_definition_creates_no_grant(export_inputs):
    from apps.node_mgmt.models import Collector

    Collector.objects.filter(id="natsexecutor_linux").delete()
    with pytest.raises(ValueError, match="Executor definition"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()


def test_export_rejects_changed_controller_material(export_inputs):
    package = PackageVersion.objects.get(pk=export_inputs["package_id"])
    package.sha256 = "d" * 64
    package.save(update_fields=["sha256"])
    with pytest.raises(ValueError, match="digest"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()


def test_explicit_executor_selection_does_not_duplicate_dependency(export_inputs):
    grant, _ = export_environment_bundle(**export_inputs, required_collectors=["natsexecutor_linux"])
    assert grant.required_components == [{"id": "natsexecutor_linux", "name": "NATS-Executor"}]


def test_grants_filter_region_before_paginating(export_inputs, monkeypatch):
    from types import SimpleNamespace

    from apps.node_mgmt.views import environment_install

    original, _ = export_environment_bundle(**export_inputs)
    other_region = CloudRegion.objects.create(name="other-list-region")
    for index in range(113):
        token = SystemAPIToken.objects.create(system_id="node-environment-install", name=f"list-{index}", secret_hash="test-only")
        EnvironmentInstallGrant.objects.create(
            owner=original.owner,
            domain=original.domain,
            team=original.team,
            cloud_region_id=original.cloud_region_id if index < 12 else other_region.pk,
            package=original.package,
            package_sha256=original.package_sha256,
            package_version=original.package_version,
            max_nodes=2,
            token=token,
        )
    monkeypatch.setattr(environment_install, "resolve_current_team_data_scope", lambda _: SimpleNamespace(current_team=1))
    request = SimpleNamespace(
        user=SimpleNamespace(username="installer", domain="test", locale="en", permission={"node": {"cloud_region_node-Edit"}}, is_superuser=False),
        query_params={"cloud_region_id": original.cloud_region_id, "page": 2, "page_size": 10},
    )
    result = json.loads(environment_install.EnvironmentInstallViewSet().grants(request).content)["data"]
    assert result["count"] == 13
    assert len(result["items"]) == 3
    assert all(item["cloud_region_id"] == original.cloud_region_id for item in result["items"])
    assert str(original.pk) in {item["id"] for item in result["items"]}


def test_grants_reject_unbounded_page_size(monkeypatch):
    from types import SimpleNamespace

    from rest_framework.exceptions import ValidationError

    from apps.node_mgmt.views.environment_install import EnvironmentInstallViewSet

    request = SimpleNamespace(
        user=SimpleNamespace(username="installer", domain="test", locale="en", permission={"node": {"cloud_region_node-Edit"}}, is_superuser=False),
        query_params={"page_size": 10001},
    )
    with pytest.raises(ValidationError):
        EnvironmentInstallViewSet().grants(request)


@pytest.mark.parametrize("script", [None, b"#!/bin/sh\necho legacy\n"])
def test_export_rejects_incompatible_install_script(export_inputs, monkeypatch, script):
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive:
        archive.writestr("fusion-collectors/bin/nats-executor", b"\x7fELF\x02\x01" + b"\x00" * 12 + b"\x3e\x00")
        if script is not None:
            archive.writestr("fusion-collectors/install.sh", script)
    package = PackageVersion.objects.get(pk=export_inputs["package_id"])
    package.sha256 = hashlib.sha256(body.getvalue()).hexdigest()
    package.save(update_fields=["sha256"])
    monkeypatch.setattr(PackageService, "download_file_streaming", lambda _: (iter([body.getvalue()]), "controller.zip"))
    with pytest.raises(ValueError, match="environment installation"):
        export_environment_bundle(**export_inputs)
    assert not EnvironmentInstallGrant.objects.exists()
    assert not SystemAPIToken.objects.filter(system_id="node-environment-install").exists()


def test_results_reach_records_beyond_first_thousand(export_inputs, monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4

    from apps.node_mgmt.models import EnvironmentInstallAttempt
    from apps.node_mgmt.views import environment_install

    grant, _ = export_environment_bundle(**export_inputs)
    EnvironmentInstallAttempt.objects.bulk_create(
        [EnvironmentInstallAttempt(grant=grant, request_id=uuid4(), node_id=str(uuid4()), ip="192.0.2.1", node_name=f"host-{i}") for i in range(1001)]
    )
    monkeypatch.setattr(environment_install, "resolve_current_team_data_scope", lambda _: SimpleNamespace(current_team=1))
    request = SimpleNamespace(
        user=SimpleNamespace(username="installer", domain="test", locale="en", permission={"node": {"cloud_region_node-Edit"}}, is_superuser=False),
        data={"grant_id": str(grant.id), "page": 101, "page_size": 10},
    )
    result = json.loads(environment_install.EnvironmentInstallViewSet().results(request).content)["data"]
    assert result["count"] == 1001
    assert len(result["items"]) == 1
    assert result["items"][0]["node_name"] == "host-0"
    request.data["page"] = 102
    assert json.loads(environment_install.EnvironmentInstallViewSet().results(request).content)["data"]["items"] == []
    request.data["page_size"] = 101
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        environment_install.EnvironmentInstallViewSet().results(request)
