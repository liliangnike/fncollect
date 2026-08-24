# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec to build a standalone `fncollect` binary.

a = Analysis(
    ["src/fncollect/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[("config", "config"), ("src/fncollect/vendors", "fncollect/vendors")],
    hiddenimports=[
        "fncollect.vendors.mock",
        "fncollect.vendors.nokia_fx",
        "fncollect.vendors.registry",
        "pydantic",
        "yaml",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="fncollect",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="fncollect")
