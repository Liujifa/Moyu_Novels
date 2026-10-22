"""与域名无关的目录发现、分页和结构化数据解析。"""

import json
import re
from collections import Counter
from urllib.parse import parse_qsl, urlparse

from bs4 import BeautifulSoup


EXTRACTION_RULE_FIELDS = (
    ("catalog_link_selector", "目录入口", "Catalog link", 'a[href*="catalog"]'),
    ("chapter_link_selector", "章节链接", "Chapter links", ".chapter-list a"),
    ("catalog_next_selector", "目录下一页", "Next catalog page", '.pagination a[rel="next"]'),
    ("content_selector", "正文", "Chapter content", "#content"),
    ("chapter_next_selector", "正文下一页", "Next chapter page", 'a.next-page'),
    ("book_title_selector", "书名", "Book title", "h1"),
)


class NovelPageParser:
    PAGE_KEYS = {"page", "p", "pg", "pageno", "pageindex", "page_no", "offset", "start"}
    CHAPTER_KEYS = {"cid", "chid", "id", "chapter", "chapterid", "chapter_id"}
    HEADING = re.compile(r"^(?:第[\d零〇一二三四五六七八九十百千万两]+[章节回卷篇]|chapter\s+[\divxlcdm]+\b|序章|楔子|序幕|尾声|番外|prologue\b|epilogue\b)", re.I)
    NOISE = re.compile(r"(?:^|[\s_-])(?:nav|menu|footer|header|aside|recommend\w*|related|comment\w*|ads?|advert\w*|toolbar|share|breadcrumb|pagination)(?:$|[\s_-])", re.I)
    SKIP_LABELS = {"首页", "上一章", "下一章", "上一页", "下一页", "目录", "返回目录", "书页", "返回书页", "加入书架", "收藏", "登录", "注册", "阅读记录", "倒序", "正序", "home", "about", "login", "register", "next", "previous", "next chapter", "previous chapter", "next page", "previous page", "contents", "table of contents"}

    def __init__(self, normalize_link, same_site, rules=None):
        if rules is not None and not isinstance(rules, dict):
            raise ValueError("解析规则必须是包含 CSS 选择器的字典。")
        self.normalize_link = normalize_link
        self.same_site = same_site
        self.rules = {}
        allowed = {field[0] for field in EXTRACTION_RULE_FIELDS}
        for key, value in (rules or {}).items():
            if key not in allowed or not isinstance(value, str):
                raise ValueError(f"不支持的解析规则：{key}")
            if value.strip():
                try:
                    BeautifulSoup("", "html.parser").select(value)
                except Exception as exc:
                    raise ValueError(f"CSS 选择器无效（{key}）：{exc}") from exc
                self.rules[key] = value.strip()

    @staticmethod
    def text(value):
        return re.sub(r"\s+", " ", value or "").strip()

    def select_rule(self, key, soup):
        return soup.select(self.rules[key]) if key in self.rules else []

    def link(self, base_url, href):
        if not isinstance(href, str) or href.strip().lower().startswith(("#", "javascript:", "mailto:", "data:", "tel:")):
            return ""
        url = self.normalize_link(base_url, href)
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not self.same_site(urlparse(base_url).hostname or "", parsed.hostname or ""):
            return ""
        return url

    def in_noise(self, node):
        for parent in [node, *node.parents]:
            if parent.get("role") == "doc-toc":
                return False
            if parent.name in {"nav", "aside", "footer", "header"}:
                return True
            attributes = " ".join([parent.get("id", ""), *parent.get("class", [])])
            if self.NOISE.search(attributes):
                return True
        return False

    @staticmethod
    def family(url):
        parsed = urlparse(url)
        parent, _, filename = parsed.path.rstrip("/").rpartition("/")
        extension = re.search(r"\.[a-zA-Z]+$", filename)
        stable_query = tuple(sorted((k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in NovelPageParser.CHAPTER_KEYS | NovelPageParser.PAGE_KEYS))
        return parent, extension.group().lower() if extension else "", stable_query

    def anchors(self, base_url, nodes, explicit=False):
        entries = []
        seen = set()
        for node in nodes:
            links = [node] if node.name == "a" else node.select("a[href]")
            for anchor in links:
                title = self.text(anchor.get_text(" ", strip=True))
                if not title or len(title) > 120 or (not explicit and self.in_noise(anchor)):
                    continue
                label = title.strip("【】[]()（） ").lower()
                if not explicit and (label in self.SKIP_LABELS or re.fullmatch(r"\d+", label)):
                    continue
                url = self.link(base_url, anchor.get("href"))
                if not url or url in seen or re.search(r"\.(?:txt|zip|rar|pdf|epub|jpg|jpeg|png|gif|js|css)(?:$|\?)", url, re.I):
                    continue
                if label in {"下载", "全文下载", "txt下载", "开始阅读", "立即阅读"}:
                    continue
                seen.add(url)
                entries.append((title, url, anchor))
        return entries

    def coherent(self, entries, scope=""):
        if not entries:
            return []
        if scope:
            scoped = [entry for entry in entries if urlparse(entry[1]).path.startswith(scope + "/")]
            if scoped:
                return scoped
        frequencies = Counter(self.family(url) for _, url, _ in entries)
        dominant = frequencies.most_common(1)[0][0]
        return [entry for entry in entries if self.family(entry[1]) == dominant]

    def catalog_links(self, url, soup):
        base = soup.select_one("base[href]")
        link_base = self.link(url, base["href"]) if base else url
        link_base = link_base or url
        if "chapter_link_selector" in self.rules:
            return [(title, href) for title, href, _ in self.anchors(link_base, self.select_rule("chapter_link_selector", soup), True)]

        scope = urlparse(link_base).path.rpartition("/")[0].rstrip("/")

        # 行级章节标记是结构证据，不依赖域名、目录路径或章节标题格式。
        marked = soup.select("[chapter-id], [data-chapter-id]")
        if marked:
            entries = self.coherent(self.anchors(link_base, marked, True), scope)
            if entries:
                return [(title, href) for title, href, _ in entries]

        entries = self.anchors(link_base, soup.select("a[href]"))
        groups = {}
        for entry in entries:
            for parent in entry[2].parents:
                if parent.name in {"ul", "ol", "dl", "div", "section", "table", "main", "article", "body"}:
                    groups.setdefault(id(parent), (parent, []))[1].append(entry)
                if parent.name == "body":
                    break
        scored = []
        heading = soup.find("h1")
        directory_heading = bool(heading and re.search(r"目录|章节列表|contents|chapters", heading.get_text(), re.I))
        for container, candidates in groups.values():
            attributes = " ".join([container.get("id", ""), *container.get("class", [])])
            semantic = bool(re.search(r"chapter|catalog|\btoc\b|目录|章节|listmain", attributes, re.I))
            semantic = semantic or (directory_heading and container.name in {"ol", "dl"})
            candidates = candidates if semantic else self.coherent(candidates, scope)
            count = len(candidates)
            if count < 2:
                continue
            headings = sum(bool(self.HEADING.match(title)) for title, _, _ in candidates) / count
            same_branch = bool(scope and self.family(candidates[0][1])[0].startswith(scope + "/")) or bool(scope and self.family(candidates[0][1])[0] == scope)
            if not semantic and headings < 0.5 and not same_branch:
                continue
            density = count / max(1, len(container.select("a[href]")))
            score = count * (2 + 2 * headings + 2 * density + int(same_branch)) + min(count, 10) * int(semantic)
            scored.append((score, count, candidates))
        if scored:
            chosen = max(scored, key=lambda item: (item[0], item[1]))[2]
            return [(title, href) for title, href, _ in chosen]
        return self.structured_chapters(url, soup)

    @staticmethod
    def json_documents(soup):
        for script in soup.select('script[type="application/ld+json"], script[type="application/json"], script#__NEXT_DATA__'):
            try:
                yield json.loads(script.string or script.get_text())
            except (ValueError, TypeError):
                continue

    @staticmethod
    def walk_json(value, depth=0):
        if depth > 24:
            return
        yield value
        if isinstance(value, dict):
            children = [v for k, v in value.items() if k.lower() not in {"recommendations", "related", "recommend", "suggestions"}]
        elif isinstance(value, list):
            children = value
        else:
            children = []
        for child in children:
            yield from NovelPageParser.walk_json(child, depth + 1)

    def structured_chapters(self, url, soup):
        lists = []
        for document in self.json_documents(soup):
            for value in self.walk_json(document):
                if not isinstance(value, dict):
                    continue
                for key in ("chapters", "chapterList", "chapter_list", "catalog", "catalogList", "toc", "itemListElement"):
                    items = value.get(key)
                    if not isinstance(items, list):
                        continue
                    result = []
                    seen = set()
                    if items and all(isinstance(item, dict) and type(item.get("position")) is int for item in items):
                        items = sorted(items, key=lambda item: item["position"])
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        node = item.get("item") if isinstance(item.get("item"), dict) else item
                        title = node.get("title") or node.get("name") or node.get("chapterName") or item.get("name")
                        href = node.get("url") or node.get("href") or node.get("chapterUrl") or node.get("link") or node.get("@id")
                        if isinstance(item.get("item"), str):
                            href = item["item"]
                        target = self.link(url, href)
                        if isinstance(title, str) and target and target not in seen:
                            seen.add(target)
                            result.append((self.text(title), target))
                    if result:
                        lists.append(result)
        return max(lists, key=len) if lists else []

    def structured_content(self, soup):
        for document in self.json_documents(soup):
            for node in self.walk_json(document):
                if isinstance(node, dict):
                    for key in ("articleBody", "chapterContent", "chapter_content"):
                        value = node.get(key)
                        if isinstance(value, str) and value.strip():
                            return value
                    if (isinstance(node.get("content"), str) and node["content"].strip()
                            and any(key in node for key in ("chapterId", "chapter_id", "chapterName"))):
                        return node["content"]
        return ""

    def catalog_target(self, url, soup):
        if "catalog_link_selector" in self.rules:
            nodes = self.select_rule("catalog_link_selector", soup)
            return next((self.link(url, node.get("href")) for node in nodes if self.link(url, node.get("href"))), url)
        if self.catalog_links(url, soup):
            return url
        candidates = []
        for node in soup.select("a[href], link[rel][href]"):
            target = self.link(url, node.get("href"))
            if not target or target == url:
                continue
            label = self.text(node.get_text(" ", strip=True)).lower()
            rel = node.get("rel", [])
            path = urlparse(target).path.lower()
            if (re.search(r"(?:sitemap|\.xml$|\.rss$)", path)
                    or label in {"首页", "网站地图", "分类", "书架", "home", "sitemap", "about", "login", "register"}):
                continue
            score = 0
            if re.search(r"目录|全部章节|章节列表|contents|catalog|chapter list|table of contents|\btoc\b", label):
                score += 8
            if any(value in rel for value in ("index", "up")):
                score += 8
            if re.search(r"(?:catalog|contents|index|toc)(?:[./_?-]|$)", path):
                score += 3
            if label in {"阅读", "开始阅读", "立即阅读", "read", "read now", "start reading"} or label.endswith("全文阅读"):
                score += 4
            if score >= 2:
                candidates.append((score, len(path), target))
        return sorted(candidates, key=lambda item: (-item[0], item[1]))[0][2] if candidates else url

    @classmethod
    def pagination_identity(cls, url):
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        path = re.sub(r"/(catalog|chapters|contents|toc|list)/\d+$", r"/\1", path, flags=re.I)
        path = re.sub(r"/(?:index(?:[_-]\d+)?|[01]_\d+)\.(?:html?|php)$", "", path, flags=re.I)
        path = re.sub(r"/page/\d+$", "", path, flags=re.I)
        path = re.sub(r"([_-])\d+(\.(?:html?|php))$", r"\2", path, flags=re.I)
        stable = tuple(sorted((k, v) for k, v in parse_qsl(parsed.query) if k.lower() not in cls.PAGE_KEYS))
        return path, stable

    @staticmethod
    def chapter_number(title):
        match = re.match(r"^(?:第([\d零〇一二三四五六七八九十百千万两]+)[章节回卷篇]|chapter\s+([\divxlcdm]+)\b|(\d+)\s*[.、:：)])", title.strip(), re.I)
        if not match:
            return None
        value = next(part for part in match.groups() if part)
        if value.isdigit():
            return int(value)
        if re.fullmatch(r"[ivxlcdm]+", value, re.I):
            roman = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
            total = previous = 0
            for char in reversed(value.lower()):
                current = roman[char]
                total += -current if current < previous else current
                previous = max(previous, current)
            return total
        digits = dict(zip("零〇一二三四五六七八九两", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 2)))
        units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
        if not any(char in units for char in value):
            return int("".join(str(digits[char]) for char in value))
        total = number = section = 0
        for char in value:
            if char in digits:
                number = digits[char]
            elif units[char] == 10000:
                total += (section + number) * 10000
                section = number = 0
            else:
                section += (number or 1) * units[char]
                number = 0
        return total + section + number

    def catalog_pagination_candidate(self, current, target):
        return bool(target and target != current and self.same_site(urlparse(current).hostname or "", urlparse(target).hostname or "")
                    and self.pagination_identity(current) == self.pagination_identity(target))

    def next_catalog_page(self, url, soup):
        if "catalog_next_selector" in self.rules:
            nodes = self.select_rule("catalog_next_selector", soup)
            return next((self.link(url, node.get("href") or node.get("value")) for node in nodes
                         if self.link(url, node.get("href") or node.get("value"))), "")
        for node in soup.select("a[href], link[rel][href]"):
            label = self.text(node.get("aria-label") or node.get_text(" ", strip=True)).strip("【】[]()（） »›→").lower()
            if label in {"下一页", "下页", "next", "next page"} or "next" in node.get("rel", []):
                target = self.link(url, node.get("href"))
                if self.catalog_pagination_candidate(url, target):
                    return target
        # 下拉目录分页常常没有“下一页”按钮，按当前选中项向后寻找。
        for select in soup.select("select"):
            options = select.select("option[value]")
            for index, option in enumerate(options):
                target = self.link(url, option.get("value"))
                if option.has_attr("selected") or target == url:
                    for following in options[index + 1:]:
                        target = self.link(url, following.get("value"))
                        if self.catalog_pagination_candidate(url, target):
                            return target
                    break
        current_number = 1
        for key, value in parse_qsl(urlparse(url).query):
            if key.lower() in self.PAGE_KEYS - {"offset", "start"} and value.isdigit():
                current_number = int(value)
        numbered_path = re.search(r"(?:[_-]|/page/|/(?:catalog|chapters|contents|toc|list)/)(\d+)(?:\.[a-z]+)?$", urlparse(url).path, re.I)
        if numbered_path:
            current_number = int(numbered_path.group(1))
        candidates = []
        for anchor in soup.select("a[href]"):
            label = self.text(anchor.get_text())
            target = self.link(url, anchor.get("href"))
            if label.isdigit() and int(label) > current_number and self.catalog_pagination_candidate(url, target):
                candidates.append((int(label), target))
        if candidates:
            return min(candidates)[1]
        return ""

    @staticmethod
    def declared_count(soup):
        meta = soup.select_one('meta[property="og:novel:chapter_count"], [data-chapter-count]')
        if meta:
            count = meta.get("content") or meta.get("data-chapter-count", "")
            if count.isdigit():
                return int(count)
        matches = {int(value) for value in re.findall(r"(?:共(?:计)?|全书)\s*(\d+)\s*[章节節]", soup.get_text(" ", strip=True))}
        return next(iter(matches)) if len(matches) == 1 else 0
