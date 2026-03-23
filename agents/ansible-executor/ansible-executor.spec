# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, copy_metadata


ansible_datas, ansible_binaries, ansible_hiddenimports = collect_all("ansible")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=ansible_binaries,
    datas=ansible_datas + copy_metadata("ansible-core") + copy_metadata("jinja2") + [("config.example.yml", ".")],
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
