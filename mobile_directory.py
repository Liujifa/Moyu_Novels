"""读取带章节范围下拉框的移动目录，并校验重复的章节地址。"""

import re
from urllib.parse import urlparse

from ajax_catalog import CatalogProtocolError


DIRECTORY_SELECTOR = ".directoryArea:not(#chapterlist) a[href]"
BOOK_PATH = re.compile(r"(/\d+/)(?:\d+/)?")
RANGE_LABEL = re.compile(r"(\d+)\s*[-—~～]\s*(\d+)\s*章")


def is_mobile_directory(url, soup):
    return bool(BOOK_PATH.fullmatch(urlparse(url).path)
                and soup.select_one("select#indexselect option[value]")
                and soup.select_one(DIRECTORY_SELECTOR))


def load_mobile_directory(downloader, url, soup):
    book_path = BOOK_PATH.fullmatch(urlparse(url).path)[1]
    host = urlparse(url).netloc
    chapter_path = re.compile(re.escape(book_path) + r"\d+\.html")

    def chapter_url(base, href):
        target = downloader.parser.link(base, href)
        parsed = urlparse(target)
        if parsed.netloc != host or parsed.query or not chapter_path.fullmatch(parsed.path):
            return ""
        return target

    pages = []
    end = 0
    for index, option in enumerate(soup.select("select#indexselect option[value]"), 1):
        target = downloader.parser.link(url, option["value"])
        parsed = urlparse(target)
        label = RANGE_LABEL.fullmatch(option.get_text(strip=True))
        expected_path = book_path if index == 1 else f"{book_path}{index}/"
        if parsed.netloc != host or parsed.path != expected_path or parsed.query or not label:
            raise CatalogProtocolError("目录分页地址或章节范围无效，已停止下载。")
        start, page_end = map(int, label.groups())
        if start != end + 1 or page_end < start:
            raise CatalogProtocolError("目录分页范围不连续，已停止下载。")
        pages.append((target, page_end - end))
        end = page_end
    if len(pages) > downloader.MAX_CATALOG_PAGES:
        raise CatalogProtocolError("目录分页超过下载上限，已停止下载。")

    rows = []
    for index, (target, count) in enumerate(pages, 1):
        if downloader.is_cancelled:
            raise CatalogProtocolError("下载已取消。")
        downloader.log(f"正在读取目录第 {index}/{len(pages)} 页。")
        resolved, page = (url, soup) if target == url else downloader.fetch_soup_with_site_fallback(target, referer=url)
        if resolved != target:
            raise CatalogProtocolError(f"目录第 {index} 页重定向到其他地址，已停止下载。")
        entries = [(anchor.get_text(" ", strip=True), chapter_url(target, anchor["href"]))
                   for anchor in page.select(DIRECTORY_SELECTOR)]
        if len(entries) != count or any(not title or not link for title, link in entries):
            raise CatalogProtocolError(f"目录第 {index} 页缺少有效章节，已停止下载。")
        rows.extend(entries)

    all_links = {link for _, link in rows}
    result, seen = [], set()
    skipped = 0
    for title, link in rows:
        if link in seen:
            skipped += 1
            continue
        if skipped:
            # 目录会把不同章节指向同一地址。沿后一个阅读页的“上一章”回溯，只接受能接回目录的链路。
            recovered = []
            previous = link
            for _ in range(skipped):
                previous = _previous_chapter(downloader, previous, chapter_url)
                if previous in all_links or previous in seen or previous == link:
                    raise CatalogProtocolError(f"{title}之前的重复目录链接无法核对，已停止下载。")
                recovered.append(previous)
                seen.add(previous)
            if _previous_chapter(downloader, previous, chapter_url) != result[-1][1]:
                raise CatalogProtocolError(f"{title}之前的章节链与目录不一致，已停止下载。")
            result.extend(("", recovered_url) for recovered_url in reversed(recovered))
            skipped = 0
        result.append((title, link))
        seen.add(link)
    if skipped:
        raise CatalogProtocolError("目录末尾存在无法核对的重复链接，已停止下载。")
    downloader.log(f"已核对 {len(pages)} 页目录，共 {len(result)} 章，修正 {len(result) - len(all_links)} 个重复链接。")
    return result


def _previous_chapter(downloader, url, chapter_url):
    resolved, page = downloader.fetch_soup_with_site_fallback(url)
    if resolved != url:
        raise CatalogProtocolError("用于核对目录的阅读页重定向到其他地址，已停止下载。")
    targets = {chapter_url(url, anchor["href"]) for anchor in page.select("a[href]")
               if downloader.normalize_navigation_label(anchor.get_text(" ", strip=True)) in {"上一章", "上一章节"}}
    if len(targets) != 1 or "" in targets:
        raise CatalogProtocolError("阅读页缺少明确的上一章链接，无法核对重复目录。")
    return targets.pop()
