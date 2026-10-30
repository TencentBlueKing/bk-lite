# -*- mode: python ; coding: utf-8 -*-

import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, copy_metadata


SPEC_PATH = Path(globals().get("SPEC", "ansible-executor.spec")).resolve()
SPEC_DIR = SPEC_PATH.parent
DIST_PATH = Path(globals().get("DISTPATH", SPEC_DIR / "dist")).resolve()

BUILD_SUPPORT_SPEC = importlib.util.spec_from_file_location(
    "build_support",
    SPEC_DIR / "build_support.py",
)
if BUILD_SUPPORT_SPEC is None or BUILD_SUPPORT_SPEC.loader is None:
    raise SystemExit(f"Unable to load build helper from {SPEC_DIR / 'build_support.py'}")
BUILD_SUPPORT_MODULE = importlib.util.module_from_spec(BUILD_SUPPORT_SPEC)
BUILD_SUPPORT_SPEC.loader.exec_module(BUILD_SUPPORT_MODULE)

# Keep this gate in the spec: Jenkins also invokes PyInstaller directly.
RELEASE_POLICY_SPEC = importlib.util.spec_from_file_location("release_policy", SPEC_DIR / "release_policy.py")
RELEASE_POLICY = importlib.util.module_from_spec(RELEASE_POLICY_SPEC)
RELEASE_POLICY_SPEC.loader.exec_module(RELEASE_POLICY)
RELEASE_POLICY.check_build_runtime()

COLLECTIONS_ROOT = SPEC_DIR / "build" / "pyinstaller-collections"
ANSIBLE_WINDOWS_ROOT = BUILD_SUPPORT_MODULE.ensure_ansible_windows_collection(
    COLLECTIONS_ROOT,
    cwd=SPEC_DIR,
)

ansible_datas, ansible_binaries, ansible_hiddenimports = collect_all("ansible")
ansible_windows_datas = BUILD_SUPPORT_MODULE.ansible_collections_root_to_datas(
    COLLECTIONS_ROOT
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=ansible_binaries,
    datas=ansible_datas
    + copy_metadata("ansible-core")
    + copy_metadata("jinja2")
    + [("config.example.yml", ".")]
    + ansible_windows_datas,
    hiddenimports=ansible_hiddenimports + ["nats.aio.client"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPEC_DIR / "release_runtime_hook.py")],
    excludes=[],
    noarchive=False,
    module_collection_mode={"ansible": "py+pyz"},
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ansible-executor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ansible-executor",
)

BUILD_SUPPORT_MODULE.verify_packaged_ansible_windows_collection(
    DIST_PATH / "ansible-executor"
)

# Validate the final frozen runtime, not just the interpreter used by the builder.
import json
release_manifest = RELEASE_POLICY.verify_package(DIST_PATH / "ansible-executor")
(DIST_PATH / "ansible-executor" / "_internal" / "release-manifest.json").write_text(
    json.dumps(release_manifest, indent=2) + "\n", encoding="utf-8"
)

RELEASE_POLICY.verify_frozen_release(DIST_PATH / "ansible-executor")
