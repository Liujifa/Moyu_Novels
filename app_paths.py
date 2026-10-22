"""区分只读随包资源和用户可写数据，避免发布版把书库写进解压目录。"""

import os
import sys
from pathlib import Path


APP_VERSION = "1.0.0"


def resource_path(name):
    return Path(__file__).resolve().parent / name


def data_directory():
    override = os.environ.get("MOYU_DATA_DIR")
    if override:
        directory = Path(override).expanduser().resolve()
    elif getattr(sys, "frozen", False):
        directory = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "MoYuReader"
    else:
        directory = Path(__file__).resolve().parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory
