# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: one-file, windowed (no console). Build with:  pyinstaller inboxctl.spec

import sys

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=[],
    datas=[("inboxctl/static", "inboxctl/static")],
    hiddenimports=[
        "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto", "uvicorn.protocols",
        "uvicorn.protocols.http", "uvicorn.protocols.http.auto", "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto", "uvicorn.lifespan", "uvicorn.lifespan.on",
        "msal", "pydantic", "anyio._backends._asyncio",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="inboxctl",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # no terminal window for end users; logs go to the data dir
    icon=None,
    target_arch=None,
)

if sys.platform == "darwin":
    app = BUNDLE(exe, name="inboxctl.app", icon=None, bundle_identifier="co.triaxis.inboxctl")
