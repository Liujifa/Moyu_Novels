# 所有随包资源显式列出，禁止把个人书库、小说和 Cookie 打入发布包。
from pathlib import Path

root = Path(SPECPATH)
a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / "charset.json"), "."),
           (str(root / "cookie_export_guide.md"), "."),
           (str(root / "assets" / "moyu.ico"), "assets")],
    hiddenimports=["PyQt6.QtTest"],
    hookspath=[],
    runtime_hooks=[str(root / "packaging" / "runtime_logging.py")],
    excludes=["tkinter", "unittest"],
    noarchive=False,
)
# Qt 使用 Windows 自带的 ICU；构建机 PATH 中的同名第三方 DLL 会缺少所需导出。
# Win10/11 的系统 API 和 UCRT 也由操作系统提供，避免捆入新版 SDK 的转发 DLL。
system_dlls = {"icuuc.dll", "icuin.dll", "ucrtbase.dll"}
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in system_dlls
              and not Path(entry[0]).name.lower().startswith(("icudt", "api-ms-win-", "ext-ms-win-"))]
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="MoYuReader", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=str(root / "assets" / "moyu.ico"),
    version=str(root / "packaging" / "version_info.txt"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MoYuReader")
