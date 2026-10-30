"""Build a fresh Linux amd64 release without changing the source virtualenv."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from release_policy import OPENSSL_VERSION, PYTHON_VERSION, sha256

SOURCE = Path(__file__).resolve().parent


def source_archive(item, downloads, cache=None):
    target = downloads / item["filename"]
    if cache is not None:
        shutil.copyfile(cache / item["filename"], target)
    else:
        with urllib.request.urlopen(item["url"], timeout=90) as response, target.open("wb") as output:
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > 128 * 1024 * 1024:
                    raise RuntimeError("Source archive exceeds 128 MiB")
                output.write(block)
    if sha256(target) != item["sha256"]:
        raise RuntimeError(f"Source SHA-256 mismatch: {item['filename']}")
    return target


def run(args, cwd, env):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True, timeout=1800)


def build(args):
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Use a Linux x86_64 builder with GLIBC 2.28 or older")
    work = args.work_dir.resolve()
    if work == SOURCE or SOURCE in work.parents:
        raise RuntimeError("Work directory must be outside the source directory")
    destination = args.dist_dir.resolve() / "ansible-executor"
    if destination.exists():
        raise RuntimeError("Destination exists; use a fresh dist directory")
    python = Path(args.python).resolve()
    info = json.loads(
        subprocess.check_output(
            [str(python), "-c", "import json,ssl,platform;print(json.dumps([platform.python_version(),ssl.OPENSSL_VERSION.split()[1]]))"], text=True
        )
    )
    if info != [PYTHON_VERSION, OPENSSL_VERSION]:
        raise RuntimeError(f"Python runtime must be {PYTHON_VERSION} with OpenSSL {OPENSSL_VERSION}; got {info}")
    work.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update(
        UV_PROJECT_ENVIRONMENT=str(work / "venv"),
        UV_CACHE_DIR=str(work / "cache"),
        UV_DEFAULT_INDEX="https://pypi.org/simple",
        UV_PYTHON_DOWNLOADS="never",
        ANSIBLE_HOME=str(work / "ansible-home"),
        CARGO_BUILD_JOBS="2",
        LANG="C.UTF-8",
        LC_ALL="C.UTF-8",
    )
    # A project sync may install a stock cryptography wheel; replace it only after sync.
    source = work / "source"
    shutil.copytree(
        SOURCE,
        source,
        ignore=shutil.ignore_patterns(".venv", "build", "dist", "__pycache__", ".env*", "config.yml", ".pytest_cache", ".coverage", "*.log"),
    )
    downloads = work / "downloads"
    downloads.mkdir()
    lock = json.loads((SOURCE / "release-sources.json").read_text())
    archives = {name: source_archive(item, downloads, args.sources_dir) for name, item in lock.items()}
    # Only hash-verified upstream source is extracted; data filter also blocks unsafe paths/links.
    with tarfile.open(archives["openssl"]) as archive:
        archive.extractall(work / "openssl-source", filter="data")
    openssl_source = work / "openssl-source" / "openssl-3.5.9"
    prefix = work / "openssl"
    run(
        [
            "./Configure",
            "linux-x86_64",
            "no-shared",
            "no-module",
            "-fPIC",
            "--prefix=" + str(prefix),
            "--openssldir=" + str(prefix / "ssl"),
            "--libdir=lib",
            "-Wl,-Bsymbolic-functions",
        ],
        openssl_source,
        env,
    )
    run(["make", "-j2"], openssl_source, env)
    run(["make", "test", "TESTS=test_evp test_aesgcm test_rsa"], openssl_source, env)
    run(["make", "install_sw"], openssl_source, env)
    env.update(OPENSSL_DIR=str(prefix), OPENSSL_STATIC="1", OPENSSL_NO_VENDOR="1")
    wheelhouse = work / "wheelhouse"
    run([args.uv, "build", archives["cryptography"], "--wheel", "--out-dir", wheelhouse, "--python", python], source, env)
    wheels = list(wheelhouse.glob("cryptography-46.0.5-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one rebuilt cryptography wheel")
    run([args.uv, "sync", "--frozen", "--python", python], source, env)
    vpython = work / "venv/bin/python"
    run(
        [
            args.uv,
            "pip",
            "install",
            "--python",
            vpython,
            "pyinstaller==6.16.0",
            "pyinstaller-hooks-contrib==2026.8",
            "pytest==8.3.5",
            "pytest-asyncio==0.26.0",
        ],
        source,
        env,
    )
    run([args.uv, "pip", "install", "--python", vpython, "--reinstall-package", "cryptography", wheels[0]], source, env)
    env["PATH"] = str(work / "venv/bin") + os.pathsep + env["PATH"]
    run([vpython, "-c", "from release_policy import check_build_runtime;check_build_runtime()"], source, env)
    run([vpython, "-m", "pytest", "tests", "-q", "--junitxml=" + str(work / "tests.xml")], source, env)
    run(
        [work / "venv/bin/ansible-galaxy", "collection", "install", "-r", "collections/requirements.yml", "-p", "build/pyinstaller-collections"],
        source,
        env,
    )
    run(
        [
            vpython,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            "--distpath",
            work / "candidate",
            "--workpath",
            work / "pyinstaller-work",
            "ansible-executor.spec",
        ],
        source,
        env,
    )
    candidate = work / "candidate/ansible-executor"
    run([candidate / "ansible-executor", "--build-info"], source, env)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ansible-release-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "ansible-executor"
        shutil.copytree(candidate, staged, symlinks=True)
        os.rename(staged, destination)
    print(f"Release package ready: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Python 3.12.15 executable with OpenSSL 3.5.9")
    parser.add_argument("--uv", default="uv")
    parser.add_argument("--work-dir", required=True, type=Path, help="New directory outside the source tree")
    parser.add_argument("--dist-dir", required=True, type=Path)
    parser.add_argument("--sources-dir", type=Path, help="Optional offline directory containing both pinned source archives")
    build(parser.parse_args())
