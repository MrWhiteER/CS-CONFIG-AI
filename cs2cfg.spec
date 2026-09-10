# PyInstaller spec for a portable, single-file cs2cfg.exe.
#
# One file, no installer, no Python needed on the target machine. Everything
# read-only is bundled; everything writable goes beside the exe at runtime (see
# cs2cfg/paths.py), so the whole tool travels on a USB stick and leaves nothing
# on the machine it ran on.

import pathlib

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# The window and shortcut icon, generated at build time rather than committed
# as a binary. See cs2cfg/appicon.py.
import sys as _sys
_sys.path.insert(0, ".")
from cs2cfg import appicon as _appicon
ICON = str(_appicon.write_ico(pathlib.Path("build") / "cs2cfg.ico"))

# Bundled resources. The probe is a PowerShell script rather than Python, and
# the knowledge base and web page are data files, so none of them are picked up
# by import analysis — they have to be listed.
datas = collect_data_files("webview") + [
    ("cs2cfg/probe.ps1", "cs2cfg"),
    ("cs2cfg/knowledge/*.json", "cs2cfg/knowledge"),
    ("cs2cfg/web/*", "cs2cfg/web"),
]

# tkinter is imported lazily by the `gui` command, so the analyser never sees
# it. Named explicitly, or the native window silently fails to open.
hiddenimports = [
    "tkinter", "tkinter.ttk", "tkinter.messagebox",
    # The native desktop window. Imported lazily inside desktop.py so the CLI
    # never pays for it, which also means the analyser cannot see it.
    "webview", "webview.platforms.edgechromium", "clr_loader", "pythonnet",
] + collect_submodules("cs2cfg") + collect_submodules("webview")

a = Analysis(
    ["run_cs2cfg.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Trimmed: none of these are used, and each drags in tens of megabytes.
    excludes=[
        "numpy", "pandas", "matplotlib", "scipy", "PIL", "pytest",
        "setuptools", "pip", "wheel", "test", "unittest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Two executables from one analysis, the way Windows expects.
#
#   CS2 Launcher.exe   GUI subsystem. Double-clicking opens the window and
#                      never flashes a console.
#   cs2cfg.exe         console subsystem. The shell waits for it and its
#                      output arrives in order, which a GUI-subsystem binary
#                      cannot do -- it returns immediately and prints after
#                      the prompt.
#
# This is the python.exe / pythonw.exe split. One binary cannot be both.

common = dict(
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON,
)

app = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="CS2 Launcher",
    console=False,
    **common,
)

cli = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="cs2cfg",
    console=True,
    **common,
)
