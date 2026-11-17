"""环境安装包交付格式：单文件内含签名清单及固定摘要安装器。"""
import hashlib
import io
import json
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from apps.node_mgmt.services.environment_bundle import assemble_run


def test_single_file_contains_signed_manifest_and_installer():
    key = Ed25519PrivateKey.generate()
    launcher = b"\x7fELFtest-launcher"
    installer = b"\x7fELFtest-official-installer"
    result = assemble_run(launcher, installer, {"schema": 1, "grant_id": "example"}, key)
    assert result.startswith(b"#!/bin/sh\n")
    _, executable = result.split(b"# __ENV_INSTALL_PAYLOAD__\n", 1)
    assert executable.startswith(launcher)
    with zipfile.ZipFile(io.BytesIO(executable)) as archive:
        manifest = archive.read("manifest.json")
        key.public_key().verify(archive.read("manifest.sig"), manifest)
        assert json.loads(manifest)["installer_sha256"] == hashlib.sha256(installer).hexdigest()
        assert archive.read("installer") == installer
