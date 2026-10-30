import json
from unittest.mock import patch

import pytest

import build_release
import release_policy as policy

GOOD = {"python": "3.12.15", "openssl": "3.5.9", "cryptography": "46.0.5", "cryptography_openssl": "3.5.9"}


@pytest.mark.parametrize("key,value", [("python", "3.12.13"), ("openssl", "1.1.1k"), ("cryptography_openssl", "3.5.5"), ("cryptography", "46.0.4")])
def test_rejects_wrong_runtime(key, value):
    with pytest.raises(RuntimeError, match=key):
        policy.check_versions(dict(GOOD, **{key: value}))


def test_accepts_release_runtime():
    policy.check_versions(GOOD)


@pytest.mark.parametrize("system,machine", [("darwin", "x86_64"), ("linux", "aarch64")])
def test_rejects_unvalidated_build_architecture(system, machine):
    with patch.object(policy.sys, "platform", system), patch.object(policy.platform, "machine", return_value=machine):
        with pytest.raises(RuntimeError, match="Linux x86_64"):
            policy.check_build_runtime()


def package(root):
    (root / "ansible-executor").write_bytes(b"\x7fELFfixture")
    (root / "_internal").mkdir()
    (root / "_internal/libpython.so").write_bytes(b"\x7fELFfixture")
    return root


def fake_output(args, **kwargs):
    if "--build-info" in args:
        return json.dumps(GOOD)
    if "--version-info" in args:
        return "GLIBC_2.2.5 GLIBC_2.28"
    return "NEEDED libc.so.6"


def test_manifest_hashes_final_package(tmp_path):
    root = package(tmp_path)
    with patch.object(policy.subprocess, "check_output", side_effect=fake_output):
        manifest = policy.verify_package(root)
    assert manifest["runtime"] == GOOD
    assert manifest["sha256"]["ansible-executor"] == policy.sha256(root / "ansible-executor")
    assert len(manifest["sha256"]) == 2


@pytest.mark.parametrize("name", ["libssl.so.1.1", ".libcrypto.so.1.1.hmac"])
def test_rejects_stale_files_even_when_runtime_is_new(tmp_path, name):
    root = package(tmp_path)
    (root / "_internal" / name).write_text("old")
    with patch.object(policy.subprocess, "check_output", side_effect=fake_output):
        with pytest.raises(RuntimeError, match="Obsolete OpenSSL file"):
            policy.verify_package(root)


@pytest.mark.parametrize(
    "option,output,error", [("--version-info", "GLIBC_2.34", "GLIBC newer"), ("--dynamic", "NEEDED libcrypto.so.1.1", "Obsolete OpenSSL dependency")]
)
def test_rejects_incompatible_elf(tmp_path, option, output, error):
    root = package(tmp_path)

    def execute(args, **kwargs):
        return output if option in args else fake_output(args)

    with patch.object(policy.subprocess, "check_output", side_effect=execute):
        with pytest.raises(RuntimeError, match=error):
            policy.verify_package(root)


def test_rejects_frozen_runtime_different_from_builder(tmp_path):
    root = package(tmp_path)
    with patch.object(policy.subprocess, "check_output", return_value=json.dumps(dict(GOOD, cryptography_openssl="3.5.5"))):
        with pytest.raises(RuntimeError, match="cryptography_openssl"):
            policy.verify_package(root)


def test_cached_source_hash_is_checked_before_use(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (cache / "source.tar.gz").write_bytes(b"source")
    item = {"filename": "source.tar.gz", "sha256": policy.sha256(cache / "source.tar.gz")}
    assert build_release.source_archive(item, downloads, cache).read_bytes() == b"source"
    (cache / "source.tar.gz").write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        build_release.source_archive(item, downloads, cache)


@pytest.mark.parametrize("mutation", ["missing", "changed", "old", "traversal", "wrong-runtime", "none"])
def test_final_manifest_check(tmp_path, mutation):
    root = package(tmp_path)
    manifest = {"runtime": GOOD, "sha256": {"ansible-executor": policy.sha256(root / "ansible-executor")}}
    if mutation == "traversal":
        manifest["sha256"] = {"../outside": "fake"}
    if mutation == "wrong-runtime":
        manifest["runtime"] = dict(GOOD, cryptography_openssl="3.5.5")
    (root / "_internal/release-manifest.json").write_text(json.dumps(manifest))
    if mutation == "missing":
        (root / "ansible-executor").unlink()
    if mutation == "changed":
        (root / "ansible-executor").write_bytes(b"bad")
    if mutation == "old":
        (root / "_internal/libssl.so.1.1").write_bytes(b"old")
    with patch.object(policy, "runtime_info", return_value=GOOD):
        if mutation == "none":
            assert policy.verify_manifest(root) == GOOD
        else:
            with pytest.raises(RuntimeError):
                policy.verify_manifest(root)


def test_ntlm_algorithms_work():
    policy.check_ntlm_compatibility()


def test_missing_rc4_provider_fails_release_check():
    with patch("spnego._ntlm_raw.crypto.rc4k", side_effect=RuntimeError("provider unavailable")):
        with pytest.raises(RuntimeError, match="provider unavailable"):
            policy.check_ntlm_compatibility()


def test_frozen_check_hides_build_machine_provider_directory(tmp_path):
    import os

    with (
        patch.dict(os.environ, {"OPENSSL_MODULES": "/build/openssl/modules", "CRYPTOGRAPHY_OPENSSL_NO_LEGACY": "1"}),
        patch.object(policy.subprocess, "run") as execute,
    ):
        policy.verify_frozen_release(tmp_path)
    env = execute.call_args.kwargs["env"]
    assert env["OPENSSL_MODULES"] == os.devnull
    assert env["OPENSSL_CONF"] == os.devnull
    assert "CRYPTOGRAPHY_OPENSSL_NO_LEGACY" not in env
    assert execute.call_args.kwargs["check"] is True
