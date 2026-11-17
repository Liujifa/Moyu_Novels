import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from web_novel_downloader import ChapterLink, WebDownloadError, WebNovelDownloader


class ChapterPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.downloader = WebNovelDownloader(self.temporary.name)
        self.root = "https://novels.example/book/5N3FC-1.html"
        self.second = "https://novels.example/book/5N3FC-1-2.html"
        self.next_chapter = "https://novels.example/book/5N3FC-2.html"
        self.calls = []
        self.pages = {}

        def fetch(url, **_kwargs):
            self.calls.append(url)
            if url not in self.pages:
                raise AssertionError(f"不应请求该页面：{url}")
            return self.pages[url]

        self.downloader.fetch_html = fetch

    def page(self, text, link="", label="下一页 »", title="第1章 开始"):
        return f'<h1>{title}</h1><article><p>{text}</p></article><a href="{link}">{label}</a>'

    def test_hyphen_pages_are_merged_before_next_chapter(self):
        self.pages = {self.root: self.page("上半章正文。", self.second),
                      self.second: self.page("下半章正文。", self.next_chapter, "下一章 »")}
        title, text = self.downloader.download_generic_chapter(self.root)
        self.assertEqual(title, "第1章 开始")
        self.assertEqual(text, "上半章正文。\n\n下半章正文。")
        self.assertEqual(self.calls, [self.root, self.second])

    def test_three_hyphen_pages_keep_order(self):
        third = "https://novels.example/book/5N3FC-1-3.html"
        self.pages = {self.root: self.page("第一页。", self.second),
                      self.second: self.page("第二页。", third),
                      third: self.page("第三页。", self.next_chapter, "下一章")}
        self.assertEqual(self.downloader.download_generic_chapter(self.root)[1], "第一页。\n\n第二页。\n\n第三页。")

    def test_next_chapter_label_can_link_to_same_chapter_page_zero_based(self):
        first = "https://novels.example/xs/13491864/79746279.html"
        second = "https://novels.example/xs/13491864/79746279_1.html"
        following = "https://novels.example/xs/13491864/79746280.html"
        self.pages = {first: self.page("上半章。", second, "下一章", "第1章 开始（第1页）"),
                      second: self.page("后半章。", following, "下一章", "第1章 开始（第2页）")}
        self.assertEqual(self.downloader.download_generic_chapter(first), ("第1章 开始", "上半章。\n\n后半章。"))
        self.assertEqual(self.calls, [first, second])

    def test_numbered_chapter_filenames_are_not_collapsed(self):
        self.assertFalse(self.downloader.is_chapter_pagination_candidate(self.root, self.next_chapter))
        soup = BeautifulSoup(self.page("正文。", self.next_chapter), "html.parser")
        self.assertEqual(self.downloader.find_next_chapter_page(self.root, soup), "")

    def test_underscore_chapter_ids_are_not_mistaken_for_pages(self):
        first = "https://novels.example/book_1.html"
        second = "https://novels.example/book_2.html"
        self.pages = {first: self.page("第一章的正文。", second, "下一章")}
        self.assertEqual(self.downloader.download_generic_chapter(first)[1], "第一章的正文。")
        self.assertEqual(self.calls, [first])

    def test_multiple_underscore_pages_use_original_chapter_root(self):
        first = "https://novels.example/79746279.html"
        second = "https://novels.example/79746279_1.html"
        third = "https://novels.example/79746279_2.html"
        self.pages = {first: self.page("第一页。", second, "下一章"),
                      second: self.page("第二页。", third, "下一章"), third: self.page("第三页。")}
        self.assertEqual(self.downloader.download_generic_chapter(first)[1], "第一页。\n\n第二页。\n\n第三页。")
        self.assertFalse(hasattr(self.downloader._response_state, "chapter_root"))

    def test_chapter_id_containing_underscore_can_have_its_own_pages(self):
        first = "https://novels.example/book_1.html"
        second = "https://novels.example/book_1_2.html"
        self.pages = {first: self.page("第一页。", second), second: self.page("第二页。")}
        self.assertEqual(self.downloader.download_generic_chapter(first)[1], "第一页。\n\n第二页。")

    def test_redirected_first_page_sets_correct_pagination_root(self):
        alias = "https://novels.example/alias"
        self.pages = {alias: self.page("第一页。", self.second), self.second: self.page("第二页。")}
        original_fetch = self.downloader.fetch_html

        def fetch(url, **kwargs):
            text = original_fetch(url, **kwargs)
            self.downloader._response_state.requested_url = url
            self.downloader._response_state.response_url = self.root if url == alias else url
            return text

        self.downloader.fetch_html = fetch
        self.assertEqual(self.downloader.download_generic_chapter(alias)[1], "第一页。\n\n第二页。")

    def test_last_part_does_not_link_to_next_chapter(self):
        soup = BeautifulSoup(self.page("正文。", self.next_chapter, "下一章 »"), "html.parser")
        self.assertEqual(self.downloader.find_next_chapter_page(self.second, soup), "")

    def test_external_pagination_is_not_followed(self):
        soup = BeautifulSoup(self.page("正文。", self.second.replace("novels.example", "external.example")), "html.parser")
        self.assertEqual(self.downloader.find_next_chapter_page(self.root, soup), "")

    def test_missing_second_part_does_not_create_cache(self):
        self.pages = {self.root: self.page("上半章。", self.second), self.second: '<h1>第1章 开始</h1>'}
        with patch("web_novel_downloader.time.sleep"):
            with self.assertRaisesRegex(WebDownloadError, "正文缺失"):
                self.downloader._download_cached_chapter(ChapterLink("第1章 开始", self.root, 0))
        self.assertEqual(list(Path(self.temporary.name).rglob("*.json")), [])

    def test_pagination_loop_does_not_succeed(self):
        self.pages = {self.root: self.page("上半章。", self.second), self.second: self.page("后半章。", self.root)}
        with self.assertRaisesRegex(WebDownloadError, "循环"):
            self.downloader.download_generic_chapter(self.root)

    def test_changed_chapter_title_fails_instead_of_mixing_content(self):
        self.pages = {self.root: self.page("上半章。", self.second),
                      self.second: self.page("其他章节。", title="第2章 继续")}
        with self.assertRaisesRegex(WebDownloadError, "不同章节"):
            self.downloader.download_generic_chapter(self.root)

    def test_page_counter_titles_are_normalized(self):
        self.pages = {self.root: self.page("上半章。", self.second, title="第1章 开始 (1 / 2)"),
                      self.second: self.page("后半章。", title="第1章 开始 (2 / 2)")}
        self.assertEqual(self.downloader.download_generic_chapter(self.root)[0], "第1章 开始")

    def test_pre_fix_half_chapter_cache_is_invalidated(self):
        chapter = ChapterLink("第1章 开始", self.root, 0)
        cache = self.downloader._chapter_cache_path(self.root)
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps({"version": 3, "url": self.root, "title": chapter.title, "content": "旧的半章。"}), encoding="utf-8")
        self.pages = {self.root: self.page("上半章。", self.second), self.second: self.page("后半章。")}
        self.assertEqual(self.downloader._download_cached_chapter(chapter)[1], "上半章。\n\n后半章。")
        self.assertEqual(json.loads(cache.read_text(encoding="utf-8"))["version"], 4)

    def test_static_base64_paragraphs_are_decoded_without_running_js(self):
        paragraphs = ["上半章的正文。", "保留原有段落顺序。"]
        scripts = "".join("<script>document.writeln(qsbs.bb('" + base64.b64encode(f"<p>{text}</p>".encode()).decode() + "'));</script>" for text in paragraphs)
        soup = self.downloader._soup_from_response('<div class="reader-content">' + scripts + '</div>')
        self.assertEqual(self.downloader.extract_content(soup), "\n".join(paragraphs))

    def test_nonliteral_script_is_not_evaluated(self):
        encoded = base64.b64encode(b"<p>not inserted</p>").decode()
        html = f'<script>document.write(atob("{encoded}"));fetch("https://external.example/")</script><script>document.write(atob(variable))</script>'
        soup = self.downloader._soup_from_response(html)
        self.assertEqual(soup.get_text(strip=True), "")

    def test_numbered_heading_wins_over_site_branding(self):
        soup = BeautifulSoup('<h1>小说网站</h1><h2>小说网站 &gt; 测试书 &gt; 第1章 开始（第1页）</h2>', "html.parser")
        self.assertEqual(self.downloader.extract_chapter_title(soup), "第1章 开始（第1页）")

    def test_explicit_catalog_list_beats_latest_and_recommendations(self):
        html = '<div><div>' + ''.join(f'<a href="book-{n}.html">第{n}章 最新</a>' for n in range(20, 25)) + '</div>'
        html += '<div class="chapter_list"><a href="book-1.html">第1章</a><a href="book-2.html">第2章</a></div>'
        html += '<div><a href="other.html">推荐的其他小说</a></div></div>'
        links = self.downloader.parser.catalog_links(self.root, BeautifulSoup(html, "html.parser"))
        self.assertEqual([title for title, _url in links], ["第1章", "第2章"])

    def test_unread_script_catalog_pages_do_not_produce_partial_book(self):
        soup = BeautifulSoup('<div class="chapter_list"><a href="book-1.html">第1章</a><a href="book-2.html">第2章</a></div>'
                             '<select><option value="1">1-100章</option><option value="2">101-200章</option></select>', "html.parser")
        with self.assertRaisesRegex(WebDownloadError, "脚本分页"):
            self.downloader.extract_chapter_links(self.root, soup)


if __name__ == "__main__":
    unittest.main()
