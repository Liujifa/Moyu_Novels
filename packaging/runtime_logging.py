"""无控制台发布包保留启动错误，方便定位缺失依赖和用户环境问题。"""

import os
import sys
from pathlib import Path


if sys.stderr is None:
    try:
        directory = Path(os.environ.get("MOYU_DATA_DIR") or
                         Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "MoYuReader")
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / "startup.log"
        if log.exists() and log.stat().st_size > 1024 * 1024:
            log.unlink()
        sys.stderr = log.open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr
    except OSError:
        pass
