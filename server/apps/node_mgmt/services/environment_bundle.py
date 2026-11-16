"""Build one shell/ELF/ZIP file; credentials only exist in the returned sensitive artifact."""
import hashlib
import io
import json
import zipfile

MAX_EXECUTABLE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 256 * 1024


def assemble_run(launcher, installer, manifest, signing_key):
    for content in (launcher, installer):
        if not content.startswith(b"\x7fELF") or len(content) > MAX_EXECUTABLE_BYTES:
            raise ValueError("invalid or oversized Linux executable")
    document = dict(manifest, installer_sha256=hashlib.sha256(installer).hexdigest())
    raw = json.dumps(document, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("environment manifest too large")
    signature = signing_key.sign(raw)
    executable = io.BytesIO(launcher)
    with zipfile.ZipFile(executable, "a", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", raw)
        archive.writestr("manifest.sig", signature)
        archive.writestr("installer", installer)
    header = """#!/bin/sh
set -eu
umask 077
if [ "$(uname -s)" != Linux ] || [ "$(uname -m)" != x86_64 ]; then echo 'Linux x86_64 required' >&2; exit 10; fi
if [ "$(id -u)" != 0 ]; then echo 'Run this installer as root' >&2; exit 10; fi
if ! work=$(mktemp -d /opt/.bklite-environment.XXXXXXXX); then echo 'Cannot create installer workspace in /opt' >&2; exit 10; fi
trap 'rm -rf -- "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
tail -n +PAYLOAD_LINE "$0" > "$work/entry"
chmod 700 "$work/entry"
"$work/entry" "$@"
exit $?
# __ENV_INSTALL_PAYLOAD__
"""
    header = header.replace("PAYLOAD_LINE", str(header.count("\n") + 1)).encode()
    return header + executable.getvalue()


def export_environment_bundle(
    *,
    owner,
    domain,
    organization,
    cloud_region_id,
    package_id,
    valid_days,
    max_nodes,
    platform_ca,
    management_cidr,
    required_free_bytes,
    timeout_seconds,
    required_collectors=None,
):
    """Validate release inputs first; a failed assembly rolls back the new capability."""
    import base64
    import os
    from datetime import timedelta
    from pathlib import Path
    from urllib.parse import urlsplit

    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from django.db import transaction
    from django.utils import timezone

    from apps.node_mgmt.models import PackageVersion
    from apps.node_mgmt.services.environment_install import EnvironmentInstallService
    from apps.node_mgmt.services.installer_session import InstallerSessionService
    from apps.node_mgmt.services.package import PackageService

    artifacts = []
    for setting in ("ENVIRONMENT_INSTALLER_LAUNCHER_FILE", "ENVIRONMENT_INSTALLER_WORKER_FILE", "ENVIRONMENT_INSTALLER_SIGNING_KEY_FILE"):
        path = os.environ.get(setting)
        if not path:
            raise ValueError("Environment installer release artifacts are not configured")
        with Path(path).open("rb") as source:
            content = source.read(MAX_EXECUTABLE_BYTES + 1)
        if len(content) > MAX_EXECUTABLE_BYTES:
            raise ValueError("Environment installer artifact too large")
        artifacts.append(content)
    launcher, installer, private_pem = artifacts
    key = serialization.load_pem_private_key(private_pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 release signing key required")
    public_key = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    if base64.b64encode(public_key) not in launcher:
        raise ValueError("Launcher does not trust the configured release signing key")
    env = InstallerSessionService._get_cloud_region_env(cloud_region_id)
    # Operators maintain internal trust once per cloud region; exports carry it in
    # the signed manifest so blank UI input does not produce an unusable bundle.
    if not platform_ca.strip():
        platform_ca = env.get("NODE_SERVER_CA", "")
    if len(platform_ca.encode()) > 65536:
        raise ValueError("Platform CA exceeds the supported size")
    if platform_ca:
        x509.load_pem_x509_certificate(platform_ca.encode())
    platform_url = env.get("NODE_SERVER_URL", "").rstrip("/")
    parsed = urlsplit(platform_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("Cloud region requires an HTTPS platform origin")
    if not env.get("NATS_INSTALLER_USERNAME") or not env.get("NATS_INSTALLER_PASSWORD") or env.get("NATS_PROTOCOL", "").lower() != "tls":
        raise ValueError("Dedicated NATS installer credentials and TLS are required")
    servers = [value.strip() for value in env.get("NATS_SERVERS", "").split(",") if value.strip()]
    if not servers or any("://" in server and not server.lower().startswith("tls://") for server in servers):
        raise ValueError("TLS NATS download servers are required")
    package = PackageVersion.objects.get(pk=package_id)
    # Object storage stat is deliberately outside the grant transaction.
    PackageService.resolve_existing_file_path(package)
    from apps.node_mgmt.services.environment_dependencies import validate_executor_dependency

    executor_id = validate_executor_dependency(package, env)
    required_collectors = list(dict.fromkeys([executor_id, *(required_collectors or [])]))
    with transaction.atomic():
        grant, secret = EnvironmentInstallService.create(
            owner=owner,
            domain=domain,
            team=organization,
            cloud_region_id=cloud_region_id,
            package_id=package_id,
            expires_at=timezone.now() + timedelta(days=valid_days),
            max_nodes=max_nodes,
            required_collectors=required_collectors,
        )
        manifest = {
            "schema": 1,
            "grant_id": str(grant.id),
            "platform_url": platform_url,
            "required_components": grant.required_components,
            "installation_key": secret,
            "acting_user": f"{owner}@{domain}",
            "team": organization,
            "cloud_region": cloud_region_id,
            "package_version": grant.package_version,
            "package_sha256": grant.package_sha256,
            "expires_at": grant.token.expires_at.isoformat(),
            "platform_ca": platform_ca,
            "management_cidr": management_cidr,
            "required_free_bytes": required_free_bytes,
            "timeout_seconds": timeout_seconds,
        }
        artifact = assemble_run(launcher, installer, manifest, key)
    return grant, artifact
