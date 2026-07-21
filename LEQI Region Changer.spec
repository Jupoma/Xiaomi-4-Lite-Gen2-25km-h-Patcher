from pathlib import Path


PROJECT_ROOT = Path(SPEC).resolve().parent
APP_ENTRY = PROJECT_ROOT / "LEQI Region Changer.pyw"
APP_ICON = PROJECT_ROOT / "assets" / "jupoma.ico"
VERSION_INFO = PROJECT_ROOT / "windows_version_info.txt"


def collect_tree(source_name):
    source_root = PROJECT_ROOT / source_name
    if not source_root.is_dir():
        raise FileNotFoundError(f"Required data directory is missing: {source_root}")

    return [
        (
            str(source_path),
            str(Path(source_name) / source_path.relative_to(source_root).parent),
        )
        for source_path in sorted(source_root.rglob("*"))
        if source_path.is_file()
    ]


if not APP_ENTRY.is_file():
    raise FileNotFoundError(f"Application entry point is missing: {APP_ENTRY}")
if not APP_ICON.is_file():
    raise FileNotFoundError(f"Application icon is missing: {APP_ICON}")
if not VERSION_INFO.is_file():
    raise FileNotFoundError(f"Windows version resource is missing: {VERSION_INFO}")


datas = collect_tree("profiles") + collect_tree("assets")

a = Analysis(
    [str(APP_ENTRY)],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LEQI Region Changer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(APP_ICON),
    version=str(VERSION_INFO),
)
