# library_manager.py
import json
import os
import math
import tempfile
from pathlib import Path

class LibraryManager:
    def __init__(self, data_file='library.json'):
        self.data_file = data_file
        self.data = self._load()
        self._saved_settings = self.data["settings"].copy()

    def _load(self):
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            return {"library": [], "settings": self.default_settings()}
        except (OSError, ValueError) as exc:
            # 损坏的书库不能当成空书库继续保存，否则会覆盖可恢复的原始数据。
            raise ValueError(f"无法读取书库 {self.data_file}，原文件未修改：{exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("library", []), list):
            raise ValueError(f"书库格式错误，原文件未修改：{self.data_file}")
        for item in data.setdefault("library", []):
            if (not isinstance(item, dict) or not isinstance(item.get("title"), str)
                    or not isinstance(item.get("path"), str) or not item["path"]
                    or type(item.get("last_pos", 0)) is not int or item.get("last_pos", 0) < 0):
                raise ValueError(f"书库条目格式错误，原文件未修改：{self.data_file}")
            ratio = item.get("last_scroll_ratio", 0.0)
            if type(ratio) not in (int, float) or not math.isfinite(ratio) or not 0 <= ratio <= 1:
                raise ValueError(f"阅读进度格式错误，原文件未修改：{self.data_file}")
        if not isinstance(data.get("settings", {}), dict):
            raise ValueError(f"阅读设置格式错误，原文件未修改：{self.data_file}")
        data["settings"] = self._normalize_settings(data.get("settings", {}))
        return data

    def _normalize_settings(self, settings):
        normalized = self.default_settings()
        normalized.update(settings)
        defaults = self.default_settings()
        for key in ("font_size", "text_opacity"):
            value = normalized[key]
            if type(value) not in (int, float) or not math.isfinite(value):
                normalized[key] = defaults[key]
        normalized["font_size"] = max(10, min(50, int(normalized["font_size"])))
        normalized["text_opacity"] = max(0.1, min(1.0, normalized["text_opacity"]))
        if normalized["language"] not in ("CN", "EN"):
            normalized["language"] = defaults["language"]
        for key in ("reading_mode", "first_run"):
            if type(normalized[key]) is not bool:
                normalized[key] = defaults[key]
        if not isinstance(normalized["font_color"], str) or not normalized["font_color"]:
            normalized["font_color"] = defaults["font_color"]
        normalized.pop("window_opacity", None)
        return normalized

    def default_settings(self):
        return {
            "font_size": 18,
            "font_color": "#e0e0e0",
            "text_opacity": 1.0,
            "reading_mode": False,
            "language": "CN",
            "first_run": True
        }

    def save(self):
        destination = Path(self.data_file).absolute()
        temporary = None
        try:
            # 同目录写入并替换，写入或替换失败时原书库始终保持完整。
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                             prefix=".library-", suffix=".tmp", delete=False) as f:
                temporary = Path(f.name)
                json.dump(self.data, f, ensure_ascii=False, indent=4, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, destination)
            self._saved_settings = self.data["settings"].copy()
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def add_novel(self, title, path):
        path = os.fspath(path)
        identity = os.path.normcase(os.path.abspath(path))
        for item in self.data["library"]:
            if os.path.normcase(os.path.abspath(item["path"])) == identity:
                return item
        new_item = {"title": title, "path": path, "last_pos": 0, "chapters": []}
        self.data["library"].append(new_item)
        try:
            self.save()
        except Exception:
            self.data["library"].pop()
            raise
        return new_item

    def remove_novel(self, path):
        for index, item in enumerate(self.data["library"]):
            if item["path"] == path:
                del self.data["library"][index]
                try:
                    self.save()
                except Exception:
                    self.data["library"].insert(index, item)
                    raise
                return True
        return False

    def update_pos(self, path, pos):
        self.update_progress(path, pos)

    def update_progress(self, path, pos, scroll_value=0, scroll_max=0):
        scroll_ratio = (scroll_value / scroll_max) if scroll_max else 0.0
        for item in self.data["library"]:
            if item["path"] == path:
                previous = item.copy()
                current_pos = item.get("last_pos", 0)
                current_ratio = item.get("last_scroll_ratio", 0.0)
                if current_pos == pos and abs(current_ratio - scroll_ratio) < 0.0005:
                    return False
                item["last_pos"] = pos
                item["last_scroll_ratio"] = scroll_ratio
                break
        else:
            return False

        try:
            self.save()
        except Exception:
            item.clear()
            item.update(previous)
            raise
        return True

    def get_settings(self):
        return self.data.get("settings", self.default_settings())

    def update_settings(self, settings):
        normalized = self._normalize_settings(settings)
        current = self.data["settings"]
        current.clear()
        current.update(normalized)
        try:
            self.save()
        except Exception:
            current.clear()
            current.update(self._saved_settings)
            raise
