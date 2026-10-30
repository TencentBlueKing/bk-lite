"""Version checks shared by the release builder and PyInstaller entry point."""

import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

OPENSSL_VERSION = "3.5.9"
PYTHON_VERSION = "3.12.15"
CRYPTOGRAPHY_VERSION = "46.0.5"


def check_versions(info):
    expected = {"python": PYTHON_VERSION, "openssl": OPENSSL_VERSION, "cryptography": CRYPTOGRAPHY_VERSION, "cryptography_openssl": OPENSSL_VERSION}
    for key, value in expected.items():
        if info.get(key) != value:
            raise RuntimeError(f"Release requires {key}={value}; got {info.get(key)!r}")


def runtime_info():
    import ssl

    import cryptography
    from cryptography.hazmat.backends.openssl.backend import backend

    return {
        "python": platform.python_version(),
        "openssl": ssl.OPENSSL_VERSION.split()[1],
        "cryptography": cryptography.__version__,
        "cryptography_openssl": backend.openssl_version_text().split()[1],
    }


def check_build_runtime():
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise RuntimeError("This release builder is validated only on Linux x86_64")
    check_versions(runtime_info())


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_package(root):
    root = Path(root).resolve()
    info = json.loads(subprocess.check_output([str(root / "ansible-executor"), "--build-info"], text=True, timeout=30))
    check_versions(info)
    hashes = {}
    for path in sorted(root.rglob("*")):
        if "libssl.so.1.1" in path.name or "libcrypto.so.1.1" in path.name:
            raise RuntimeError(f"Obsolete OpenSSL file: {path.name}")
        if not path.is_file() or path.name == "release-manifest.json":
            continue
        with path.open("rb") as stream:
            elf = stream.read(4) == b"\x7fELF"
        if elf:
            output = subprocess.check_output(["readelf", "--version-info", "--wide", str(path)], text=True)
            versions = [tuple(map(int, v.split("."))) for v in re.findall(r"GLIBC_(\d+\.\d+(?:\.\d+)?)", output)]
            if versions and max(versions) > (2, 28):
                raise RuntimeError(f"GLIBC newer than 2.28 required: {path.name}")
            dynamic = subprocess.check_output(["readelf", "--dynamic", str(path)], text=True)
            if re.search(r"NEEDED.*lib(?:ssl|crypto)\.so\.1\.1", dynamic):
                raise RuntimeError(f"Obsolete OpenSSL dependency: {path.name}")
        hashes[str(path.relative_to(root))] = sha256(path)
    return {"runtime": info, "architecture": "linux-x86_64", "glibc_max": "2.28", "sha256": hashes}


def verify_manifest(root):
    """Check an installed/staged component without a system Python or readelf."""
    root = Path(root).resolve()
    manifest = json.loads((root / "_internal/release-manifest.json").read_text())
    check_versions(runtime_info())
    check_ntlm_compatibility()
    check_versions(manifest["runtime"])
    for relative, expected in manifest["sha256"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"Release file missing, unsafe or modified: {relative}")
    for path in root.rglob("*"):
        if "libssl.so.1.1" in path.name or "libcrypto.so.1.1" in path.name:
            raise RuntimeError(f"Obsolete OpenSSL file: {path.name}")
    return manifest["runtime"]


def check_ntlm_compatibility():
    """WinRM/NTLM must work without a provider module on the build machine."""
    from spnego._ntlm_raw.crypto import ntowfv1, ntowfv2, rc4k

    nt_hash = ntowfv1("Password")
    if nt_hash.hex() != "a4f49c406510bdcab6824ee7c30fd852":
        raise RuntimeError("NTLM hash self-test failed")
    if ntowfv2("User", nt_hash, "Domain").hex() != "0c868a403bfd7a93a3001ef22ef02e3f":
        raise RuntimeError("NTLMv2 hash self-test failed")
    if rc4k(bytes([1, 2, 3, 4, 5]), bytes(16)).hex() != "b2396305f03dc027ccc3524a0a1118a8":
        raise RuntimeError("RC4 self-test failed")


def verify_frozen_release(root):
    # Hide all external modules/configs, including this build's own OpenSSL prefix.
    env = dict(os.environ, OPENSSL_MODULES=os.devnull, OPENSSL_CONF=os.devnull)
    env.pop("CRYPTOGRAPHY_OPENSSL_NO_LEGACY", None)
    subprocess.run([str(Path(root) / "ansible-executor"), "--verify-release"], env=env, check=True, timeout=30)


if __name__ == "__main__":
    print(json.dumps(verify_package(sys.argv[1]), indent=2))
