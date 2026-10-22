import os
import re
import hashlib
import io
import json

import chardet


class ReaderLogic:
    def __init__(self):
        self._encoding_cache = {}
        self._chapter_cache = {}
        self.last_error = ""
        self.chapter_patterns = [
            re.compile("^\\s*\u7b2c[\\d\u96f6\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\u4e24\u3007\u25cb\u58f9\u8d30\u53c1\u8086\u4f0d\u9646\u67d2\u634c\u7396\u62fe\u4f70\u4edf]+[\u7ae0\u8282\u5377\u96c6\u90e8\u7bc7\u56de\u8bdd\u5e55].*$"),
            re.compile("^\\s*(\u5e8f\u7ae0|\u5e8f\u5e55|\u6954\u5b50|\u524d\u8a00|\u5f15\u5b50|\u6b63\u6587|\u540e\u8bb0|\u5c3e\u58f0|\u756a\u5916).*$"),
            re.compile(r"^\s*(chapter\s+[0-9ivxlcdm]+.*|prologue.*|epilogue.*)$", re.IGNORECASE),
            re.compile("^\\s*\\d+\\s*[\\u3001\\.\\uff0e]\\s*.+$"),
        ]

    def detect_encoding(self, path):
        try:
            stat = os.stat(path)
            signature = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            signature = None

        cached = self._encoding_cache.get(path)
        if cached and cached["signature"] == signature:
            return cached["encoding"]

        with open(path, "rb") as f:
            raw_data = f.read(10000)
            result = chardet.detect(raw_data)
            encoding = result["encoding"] or "utf-8"

        self._encoding_cache[path] = {
            "signature": signature,
            "encoding": encoding,
        }
        return encoding

    def load_txt(self, path):
        self.last_error = ""
        try:
            encoding = self.detect_encoding(path)
            with open(path, "r", encoding=encoding, errors="ignore") as f:
                content = f.read()
            signature = self.file_signature(path)
            cached = self._chapter_cache.get(path)
            if cached and cached["signature"] == signature:
                chapters = cached["chapters"]
            else:
                chapters = self._parse_chapters_from_lines(
                    io.StringIO(content), self._load_chapter_index(path),
                    allow_legacy=not os.path.exists(str(path) + ".chapters.json"),
                )
            self._update_chapter_cache(path, chapters)
            return content, chapters
        except Exception as e:
            self.last_error = str(e)
            print(f"读取小说失败：{path}，原因：{e}")
            return "", []

    def get_chapters(self, path):
        try:
            signature = self.file_signature(path)
        except OSError:
            return []

        cached = self._chapter_cache.get(path)
        if cached and cached["signature"] == signature:
            return cached["chapters"]

        try:
            encoding = self.detect_encoding(path)
            with open(path, "r", encoding=encoding, errors="ignore") as f:
                chapters = self._parse_chapters_from_lines(
                    f, self._load_chapter_index(path),
                    allow_legacy=not os.path.exists(str(path) + ".chapters.json"),
                )
            self._chapter_cache[path] = {
                "signature": signature,
                "chapters": chapters,
            }
            return chapters
        except Exception as e:
            print(f"解析小说目录失败：{path}，原因：{e}")
            return []

    def _update_chapter_cache(self, path, chapters):
        try:
            signature = self.file_signature(path)
        except OSError:
            return

        self._chapter_cache[path] = {
            "signature": signature,
            "chapters": chapters,
        }

    def is_chapter_title(self, line):
        stripped = line.strip()
        if not stripped or len(stripped) > 80:
            return False

        return any(pattern.match(stripped) for pattern in self.chapter_patterns)

    def file_signature(self, path):
        stat = os.stat(path)
        try:
            index_stat = os.stat(str(path) + ".chapters.json")
            index_signature = (index_stat.st_mtime_ns, index_stat.st_size)
        except OSError:
            index_signature = None
        return stat.st_mtime_ns, stat.st_size, index_signature

    def _load_chapter_index(self, path):
        try:
            with open(str(path) + ".chapters.json", encoding="utf-8") as file:
                metadata = json.load(file)
            if metadata.get("version") != 1:
                return None
            entries = metadata["chapters"]
            if not isinstance(entries, list) or not entries:
                return None
            index = {}
            previous = -1
            for entry in entries:
                line = entry["index"]
                title = entry["title"]
                if type(line) is not int or line <= previous or not isinstance(title, str) or not title.strip():
                    return None
                index[line] = title
                previous = line
            digest = hashlib.sha256()
            with open(path, "rb") as file:
                for block in iter(lambda: file.read(1024 * 1024), b""):
                    digest.update(block)
            # TXT 被外部编辑后必须丢弃旧索引，避免跳到错误位置。
            return index if digest.hexdigest() == metadata.get("sha256") else None
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    def _parse_chapters_from_lines(self, lines, chapter_index=None, allow_legacy=True):
        chapters = []
        indexed_chapters = []
        boundary_chapters = []
        header = []
        previous_blank = False
        boundary_candidate = None
        current_pos = 0

        for i, raw_line in enumerate(lines):
            line = raw_line.rstrip("\r\n")
            stripped = line.strip()
            if i < 4:
                header.append(stripped)
            chapter = {"title": stripped, "pos": current_pos, "index": i}
            if chapter_index is not None and chapter_index.get(i) == stripped:
                indexed_chapters.append(chapter)
            if boundary_candidate is not None and not stripped:
                boundary_chapters.append(boundary_candidate)
            is_title = self.is_chapter_title(line)
            boundary_candidate = (
                chapter if i >= 4 and previous_blank and is_title and stripped != "正文" else None
            )
            previous_blank = not stripped
            if is_title:
                chapters.append(chapter)
            # QTextCursor 使用 UTF-16 偏移，生僻字和表情在 Python 中只占一个字符。
            current_pos += len(raw_line.encode("utf-16-le")) // 2

        if chapter_index is not None and len(indexed_chapters) == len(chapter_index):
            return indexed_chapters
        if allow_legacy and len(header) == 4 and header[1].startswith(("Source: http://", "Source: https://")) and not header[3]:
            count = re.fullmatch(r"Chapters: (\d+)", header[2])
            # 兼容旧版下载 TXT：仅在段落边界数与文件声明完全一致时采用结构化目录。
            if count and int(count.group(1)) > 0 and len(boundary_chapters) == int(count.group(1)):
                return boundary_chapters
        return chapters

    def parse_chapters(self, content):
        return self._parse_chapters_from_lines(io.StringIO(content))
