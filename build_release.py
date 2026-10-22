"""在独立 Windows 环境中构建 ZIP，收集许可证并生成 SHA-256 校验文件。"""

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from app_paths import APP_VERSION


ROOT = Path(__file__).resolve().parent


def main():
    if sys.platform != "win32" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise SystemExit("请在 Windows x64 环境构建此发布包。")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build" / "pyinstaller"),
                    str(ROOT / "MoYuReader.spec")], check=True, cwd=ROOT)
    bundle = ROOT / "dist" / "MoYuReader"
    shutil.copy2(ROOT / "LICENSE", bundle / "LICENSE.txt")
    shutil.copy2(ROOT / "README.md", bundle / "README.md")
    shutil.copytree(ROOT / "docs", bundle / "docs", dirs_exist_ok=True)
    (bundle / "packaging").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "packaging" / "README.md", bundle / "packaging" / "README.md")
    (bundle / "使用说明.txt").write_text(
        f"MoYu Reader {APP_VERSION} · Windows x64\n\n"
        "1. 完整解压 ZIP，请勿在压缩软件内部运行。\n"
        "2. 双击 MoYuReader.exe，无需安装 Python。请保留 _internal 文件夹。\n"
        "3. 点击添加小说导入 TXT，或从网页下载小说。选好章节后点击开始阅读。\n"
        "4. 关闭书库后仍在托盘运行，右键托盘选择退出可完全关闭。\n\n"
        "书库、设置和下载保存到 %LOCALAPPDATA%\\MoYuReader。\n"
        "书库底部可打开数据目录。更新时替换程序目录即可，个人数据独立保留。\n"
        "项目与源代码：https://github.com/Liujifa/Mess-Around\n"
        "第三方组件保留各自许可证，详见 THIRD_PARTY_LICENSES 文件夹。\n",
        encoding="utf-8-sig")
    licenses = bundle / "THIRD_PARTY_LICENSES"
    licenses.mkdir(exist_ok=True)
    versions = {}
    runtime = ["PyQt6", "PyQt6-Qt6", "PyQt6-sip", "requests", "urllib3", "certifi",
               "charset-normalizer", "chardet", "idna", "beautifulsoup4", "soupsieve", "typing_extensions", "PyInstaller"]
    for name in runtime:
        distribution = importlib.metadata.distribution(name)
        versions[name] = distribution.version
        for file in distribution.files or []:
            if any(marker in file.name.lower() for marker in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = licenses / name / str(file).replace("..", "_")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.exists():
        python_license = Path(sys.base_prefix) / "LICENSE"
    shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    (licenses / "COMPONENTS.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")
    (licenses / "SOURCES.txt").write_text(
        "Application source: https://github.com/Liujifa/Mess-Around/tree/v" + APP_VERSION + "\n"
        "PyQt6 (GPL v3): https://pypi.org/project/PyQt6/6.10.2/#files\n"
        "Qt 6.10.2 sources and licenses: https://download.qt.io/archive/qt/6.10/6.10.2/\n"
        "Qt DLLs are dynamically linked and can be replaced with compatible versions.\n"
        "Other dependency source archives: https://pypi.org/ (versions in COMPONENTS.json).\n",
        encoding="utf-8")
    artifacts = ROOT / "release-artifacts"
    artifacts.mkdir(exist_ok=True)
    report_directory = ROOT / "build" / "release-smoke"
    report_directory.mkdir(parents=True, exist_ok=True)
    report = report_directory / "smoke-result.json"
    report.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment["MOYU_DATA_DIR"] = str(report_directory / "data")
    environment["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32") + os.pathsep + os.environ["SystemRoot"]
    for key in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "QT_QPA_PLATFORM"):
        environment.pop(key, None)
    subprocess.run([str(bundle / "MoYuReader.exe"), "--smoke-test", str(report_directory)],
                   env=environment, cwd=report_directory, check=True, timeout=60)
    if not report.exists() or not json.loads(report.read_text(encoding="utf-8")).get("success"):
        raise RuntimeError("发布包自检失败，停止生成 ZIP。")
    for file in bundle.rglob("*"):
        if file.is_file() and (file.name == "library.json" or "novel_downloads" in file.parts
                               or file.name.lower().startswith("cookies") or file.name.endswith(".chapters.json")):
            raise RuntimeError(f"发布包出现个人数据文件，停止打包：{file}")
    archive = Path(shutil.make_archive(str(artifacts / f"MoYuReader-v{APP_VERSION}-Windows-x64"),
                                     "zip", root_dir=ROOT / "dist", base_dir="MoYuReader"))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (artifacts / "SHA256SUMS.txt").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    shutil.copy2(report, artifacts / "smoke-result.json")
    print(f"发布包：{archive}\nSHA-256：{digest}")


if __name__ == "__main__":
    main()
