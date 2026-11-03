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
    runtime_hooks=[],
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
