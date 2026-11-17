"""读取使用 chapterPageAjxa 协议的动态目录，复用下载器的会话和请求调度。"""

import base64
import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse


class CatalogProtocolError(ValueError):
    pass


@dataclass
class EncryptedCatalogSpec:
    book_id: str
    pages: list[tuple[int, int, int]]

    @classmethod
    def from_page(cls, soup, max_pages):
        control = soup.select_one(".chapter_page select")
        if control is None:
            return None
        owner = control.find_parent(attrs={"data-aid": True})
        if owner is None or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", owner["data-aid"]):
            return None
        pages = []
        for option in control.select("option[value]"):
            match = re.fullmatch(r"\s*(\d+)\s*[-—~～]\s*(\d+)\s*章\s*", option.get_text())
            if not match or not option["value"].isdigit():
                return None
            number = int(option["value"])
            start, end = map(int, match.groups())
            if number != len(pages) + 1 or start != (pages[-1][2] + 1 if pages else 1) or end < start:
                raise CatalogProtocolError("动态目录的页码或章节范围不连续，未生成不完整 TXT。")
            pages.append((number, start, end))
        if len(pages) < 2:
            return None
        if len(pages) > max_pages:
            raise CatalogProtocolError(f"动态目录超过 {max_pages} 页，已停止加载。")
        return cls(owner["data-aid"], pages)


def parse_cipher_config(script):
    # 只读取公开脚本中的固定字符串配置，不执行远程 JavaScript 或混淆代码。
    required = ("function chapterPageAjxa", "CryptoJS.AES.encrypt", "CryptoJS.mode.CBC", "CryptoJS.pad.Pkcs7")
    if not all(marker in script for marker in required):
        return None
    key = re.search(r"new\s+AESCrypt\(\s*(['\"])([^'\"\\\r\n]+)\1\s*\)", script)
    iv = re.search(r"this\.iv\s*=\s*CryptoJS\.enc\.Utf8\.parse\(\s*(['\"])([^'\"\\\r\n]+)\1\s*\)", script)
    if not key or not iv:
        return None
    key_bytes, iv_bytes = key.group(2).encode("utf-8"), iv.group(2).encode("utf-8")
    if len(key_bytes) not in (16, 24, 32) or len(iv_bytes) != 16:
        raise CatalogProtocolError("动态目录请求的 AES 配置无效，未生成不完整 TXT。")
    return key_bytes, iv_bytes


def encode_catalog_request(book_id, page, key, iv):
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
    except ImportError as exc:
        raise CatalogProtocolError("动态目录需要 pycryptodome；请安装 requirements.txt 中的依赖或更新免安装版。") from exc
    plain = json.dumps({"id": book_id, "page": page}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plain, AES.block_size))).decode("ascii")


def load_encrypted_catalog(downloader, base_url, soup, initial_entries):
    if downloader.parser.rules.get("catalog_next_selector"):
        return None
    spec = EncryptedCatalogSpec.from_page(soup, downloader.MAX_CATALOG_PAGES)
    if spec is None:
        return None
    cipher = None
    inspected = set()
    for tag in soup.select("script[src]"):
        script_url = downloader.parser.link(base_url, tag["src"])
        if not script_url or script_url in inspected or re.search(r"jquery|crypto-js|/layer/", script_url, re.I):
            continue
        if len(inspected) >= 8:
            break
        inspected.add(script_url)
        if downloader.is_cancelled:
            raise CatalogProtocolError("已取消目录加载。")
        cipher = parse_cipher_config(downloader.fetch_html(script_url, referer=base_url))
        if cipher:
            break
    if cipher is None:
        return None

    # 该地址是已验证的前端协议入口，始终在原站请求，不依赖域名白名单。
    endpoint = downloader.parser.link(base_url, "/index.php?action=loadChapterPage")
    entries, seen_urls = [], set()
    article_id = None
    for page, start, end in spec.pages:
        if downloader.is_cancelled:
            raise CatalogProtocolError("已取消目录加载。")
        downloader.log(f"正在加载动态目录第 {page}/{len(spec.pages)} 页。")
        encrypted = encode_catalog_request(spec.book_id, page, *cipher)
        raw = downloader.post_html(endpoint, {"data": encrypted}, base_url,
                                   extra_headers={"X-Requested-With": "XMLHttpRequest"})
        try:
            response = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise CatalogProtocolError(f"动态目录第 {page} 页未返回有效 JSON，未生成不完整 TXT。") from exc
        if not isinstance(response, dict) or response.get("code") not in (0, "0"):
            raise CatalogProtocolError(f"动态目录第 {page} 页请求失败，未生成不完整 TXT。")
        rows = response.get("data")
        capacity = end - start + 1
        if (not isinstance(rows, list) or not rows or len(rows) > capacity
                or (page < len(spec.pages) and len(rows) != capacity)):
            raise CatalogProtocolError(f"动态目录第 {page} 页章节数量不完整，未生成不完整 TXT。")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise CatalogProtocolError(f"动态目录第 {page} 页章节格式错误。")
            title, href = row.get("chaptername"), row.get("chapterurl")
            target = downloader.parser.link(base_url, href)
            if not isinstance(title, str) or not title.strip() or not target:
                raise CatalogProtocolError(f"动态目录第 {page} 页缺少有效章节标题或同站链接。")
            if target in seen_urls:
                raise CatalogProtocolError(f"动态目录第 {page} 页重复返回章节，已停止以避免漏章。")
            order = row.get("chapterorder")
            if order is not None and str(order) != str(start + index):
                raise CatalogProtocolError(f"动态目录第 {page} 页章节顺序或范围不一致。")
            row_article = row.get("articleid")
            if row_article is not None:
                if article_id is not None and str(row_article) != article_id:
                    raise CatalogProtocolError("动态目录混入其他书籍，已停止下载。")
                article_id = str(row_article)
            seen_urls.add(target)
            entries.append((title.strip(), target))
    if not {url for _title, url in initial_entries}.issubset(seen_urls):
        raise CatalogProtocolError("动态目录与当前页面的书籍不一致，未生成不完整 TXT。")
    latest = soup.select_one('meta[property="og:novel:latest_chapter_url"]')
    if latest:
        target = downloader.parser.link(base_url, latest.get("content"))
        if target:
            latest_path = (urlparse(target).path, urlparse(target).query)
            if latest_path not in {(urlparse(url).path, urlparse(url).query) for url in seen_urls}:
                raise CatalogProtocolError("动态目录尚未包含页面声明的最新章节，未生成不完整 TXT。")
    downloader.log(f"动态目录已完整加载，共 {len(entries)} 章。")
    return entries
