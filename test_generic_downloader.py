import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from bs4 import BeautifulSoup
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from download_dialog import WebDownloadDialog
from reader_logic import ReaderLogic
from requests import Response
from web_novel_downloader import WebDownloadError, WebNovelDownloader


class GenericDownloaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.downloader = WebNovelDownloader(self.temporary.name)

    def soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def pages(self, pages):
        self.calls = []

        def fetch(url, referer="", **_kwargs):
            self.calls.append(url)
            if url not in pages:
                raise AssertionError(f"不应访问该地址：{url}")
            return pages[url]

        self.downloader.fetch_html = fetch

    def catalog(self, html, url="https://unlisted.example/story/alpha/index.html"):
        return self.downloader.extract_chapter_links(url, self.soup(html))

    def test_two_unnumbered_chapters_in_unknown_container(self):
        links = self.catalog('<div class="x91"><ul><li><a href="dawn.html">黎明之前</a></li>'
                             '<li><a href="journey.html">踏上旅程</a></li></ul></div>')
        self.assertEqual([c.title for c in links], ["黎明之前", "踏上旅程"])

    def test_latest_header_and_recommendations_are_not_chapters(self):
        html = ('<header><a href="99.html">第99章 最新</a></header>'
                '<aside><a href="/other/1.html">第1章 推荐书</a></aside>'
                '<div class="chapter-list"><a href="1.html">第1章 评论</a>'
                '<a href="2.html">第2章 收藏</a></div>')
        self.assertEqual([c.title for c in self.catalog(html)], ["第1章 评论", "第2章 收藏"])

    def test_recommended_book_list_on_download_page_is_not_a_catalog(self):
        html = ('<h1>未知小说下载</h1><a href="/read/42/">阅读</a><div class="box"><h2>作者推荐</h2><ul>'
                '<li><a href="/book/11.html">星海旅途</a></li><li><a href="/book/12.html">黎明之前</a></li>'
                '<li><a href="/book/13.html">森林往事</a></li></ul></div>'
                '<footer><a href="/sitemap/index.xml">网站地图</a><a href="/index.html">首页</a></footer>')
        url = "https://unlisted.example/download/42.html"
        self.assertEqual(self.catalog(html, url), [])
        self.assertEqual(self.downloader.resolve_catalog_url(url, self.soup(html)), "https://unlisted.example/read/42/")

    def test_volume_paths_and_reset_numbers_keep_original_order(self):
        html = '<div class="catalog">' + ''.join(
            f'<a href="{volume}/{number}.html">第{number}章 {volume}</a>'
            for volume in ("volume-one", "volume-two") for number in (1, 2)
        ) + '</div>'
        self.assertEqual([c.title for c in self.catalog(html)],
                         ["第1章 volume-one", "第2章 volume-one", "第1章 volume-two", "第2章 volume-two"])

    def test_misnumbered_catalog_is_not_sorted_numerically(self):
        html = '<ol>' + ''.join(f'<li><a href="{i}.html">第{n}章</a></li>' for i, n in enumerate((285, 276, 277))) + '</ol>'
        self.assertEqual([c.title for c in self.catalog(html)], ["第285章", "第276章", "第277章"])

    def test_chinese_and_roman_descending_catalogs_are_reversed(self):
        for titles in (("第三章 丙", "第二章 乙", "第一章 甲"), ("Chapter III", "Chapter II", "Chapter I")):
            with self.subTest(titles=titles):
                html = '<ul>' + ''.join(f'<li><a href="{i}.html">{title}</a></li>' for i, title in enumerate(titles)) + '</ul>'
                self.assertEqual([c.title for c in self.catalog(html)], list(reversed(titles)))

    def test_embedded_framework_json_chapters(self):
        data = {"props": {"pageProps": {"chapters": [
            {"title": "无编号的开始", "href": "a.html"}, {"name": "无编号的结尾", "url": "b.html"},
        ]}}}
        html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        self.assertEqual([c.title for c in self.catalog(html)], ["无编号的开始", "无编号的结尾"])

    def test_jsonld_item_list_uses_declared_positions(self):
        data = {"@type": "ItemList", "itemListElement": [
            {"position": 2, "item": {"name": "远行", "url": "b.html"}},
            {"position": 1, "item": {"name": "晨光", "url": "a.html"}},
        ]}
        html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
        self.assertEqual([c.title for c in self.catalog(html)], ["晨光", "远行"])

    def test_raw_json_api_catalog_and_chapter_body_download_end_to_end(self):
        source = "https://unknown.example/api/books/alpha"
        catalog = {"data": {"chapters": [
            {"chapterName": "第一章 开始", "chapterUrl": "/api/chapter/one"},
            {"chapterName": "第二章 结束", "chapterUrl": "/api/chapter/two"},
        ]}}
        self.pages({source: json.dumps(catalog),
                    "https://unknown.example/api/chapter/one": json.dumps({"chapterId": 1, "content": "这是开始的正文。"}),
                    "https://unknown.example/api/chapter/two": json.dumps({"chapterId": 2, "content": "这是结束的正文。"})})
        result = self.downloader.download(source, "未知站点小说")
        self.assertEqual(result.chapter_count, 2)
        content, index = ReaderLogic().load_txt(result.file_path)
        self.assertIn("这是开始的正文。", content)
        self.assertEqual([c["title"] for c in index], ["第一章 开始", "第二章 结束"])

    def test_plain_txt_download_and_index(self):
        source = "https://books.example/files/%E6%B5%8B%E8%AF%95.txt"
        self.pages({source: "\ufeff第一章 开始\r\n这是正文😀。\r\n第二章 结束\r\n这是结尾。"})
        result = self.downloader.download(source)
        self.assertEqual(result.title, "测试")
        self.assertEqual(result.chapter_count, 2)
        self.assertEqual(len(ReaderLogic().get_chapters(result.file_path)), 2)

    def test_text_mime_download_endpoint_without_txt_extension(self):
        url = "https://downloads.example/api/export?book=42"
        response = Response()
        response.status_code = 200
        response.url = url
        response.encoding = "utf-8"
        response.headers["Content-Type"] = "text/plain; charset=utf-8"
        response._content = "第一章 开始\n这是正文。\n第二章 结束\n这是结尾。".encode("utf-8")
        with patch.object(self.downloader.session, "get", return_value=response) as fetch:
            result = self.downloader.download(url, "无扩展名下载")
        fetch.assert_called_once()
        self.assertEqual(result.chapter_count, 2)

    def test_redirected_catalog_uses_final_url_for_relative_chapters(self):
        source = "https://redirect.example/book/42"
        responses = {
            source: (source + "/", '<h1>重定向测试</h1><ol><li><a href="one.html">第一章</a></li><li><a href="two.html">第二章</a></li></ol>'),
            source + "/one.html": (source + "/one.html", '<article><p>第一段正文。</p></article>'),
            source + "/two.html": (source + "/two.html", '<article><p>第二段正文。</p></article>'),
        }

        def fetch(url, **_kwargs):
            final_url, text = responses[url]
            response = Response()
            response.status_code = 200
            response.url = final_url
            response.encoding = "utf-8"
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            response._content = text.encode("utf-8")
            return response

        with patch.object(self.downloader.session, "get", side_effect=fetch), patch.object(self.downloader, "_wait_for_request_slot"):
            result = self.downloader.download(source)
        self.assertEqual(result.chapter_count, 2)
        self.assertEqual(result.source_url, source + "/")

    def test_book_page_can_follow_direct_txt_download(self):
        source = "https://unknown.example/book/alpha"
        self.pages({source: '<h1>通用小说</h1><a download href="/files/full.txt">全文 TXT 下载</a>',
                    "https://unknown.example/files/full.txt": "第一章 开始\n正文内容。"})
        result = self.downloader.download(source)
        self.assertEqual(result.title, "通用小说")
        self.assertEqual(result.chapter_count, 1)

    def test_html_response_is_not_saved_as_txt(self):
        source = "https://unknown.example/file.txt"
        self.pages({source: "<!doctype html><html><body>登录页面</body></html>"})
        with self.assertRaisesRegex(WebDownloadError, "网页而非 TXT"):
            self.downloader.download(source)
        self.assertEqual(list(Path(self.temporary.name).glob("*.txt")), [])

    def test_discovery_can_follow_book_page_then_reader_then_catalog(self):
        source = "https://any.example/books/alpha"
        catalog = "https://any.example/series/alpha/contents"
        self.pages({source: '<h1>新世界</h1><a href="/reader/alpha/1">开始阅读</a>',
                    "https://any.example/reader/alpha/1": '<header><a href="/series/alpha/contents">全部章节</a></header><article><p>正文。</p></article>',
                    catalog: '<h1>新世界</h1><ol><li><a href="/reader/alpha/1">第一章</a></li><li><a href="/reader/alpha/2">第二章</a></li></ol>',
                    "https://any.example/reader/alpha/2": '<article><p>第二章的正文。</p></article>'})
        result = self.downloader.download(source)
        self.assertEqual(result.chapter_count, 2)
        self.assertEqual(result.source_url, catalog)

    def test_query_pagination_keeps_book_id_and_excludes_other_books(self):
        source = "https://query.example/catalog.php?bookid=42"
        following = source + "&p=2"
        first = '<div class="chapter-list"><a href="read.php?bookid=42&cid=1">第一章</a><a href="read.php?bookid=42&cid=2">第二章</a></div>'
        second = '<div class="chapter-list"><a href="read.php?bookid=42&cid=3">第三章</a><a href="read.php?bookid=42&cid=4">第四章</a></div>'
        self.pages({following: second})
        links = self.downloader.extract_chapter_links(source, self.soup(first + f'<a href="{following}">下一页</a>'))
        self.assertEqual(len(links), 4)
        self.assertFalse(self.downloader.is_catalog_pagination_candidate(source, "https://query.example/catalog.php?bookid=99&p=2"))

    def test_single_page_fallback_uses_discovered_reading_page(self):
        source = "https://any.example/books/alpha"
        reader = "https://any.example/reader/alpha/1"
        self.pages({source: '<h1>新世界</h1><a href="/reader/alpha/1">开始阅读</a>',
                    reader: '<h1>第一章</h1><article><p>这是阅读页面的正文。</p></article>'})
        result = self.downloader.download(source)
        self.assertEqual(result.source_url, reader)
        self.assertEqual(result.chapter_count, 1)
        self.assertIn("这是阅读页面的正文。", Path(result.file_path).read_text(encoding="utf-8"))

    def test_txt_link_on_discovered_page_is_used(self):
        source = "https://any.example/books/alpha"
        reader = "https://any.example/reader/alpha/1"
        self.pages({source: '<h1>新世界</h1><a href="/reader/alpha/1">开始阅读</a>',
                    reader: '<a href="full.txt">TXT 全文下载</a>',
                    "https://any.example/reader/alpha/full.txt": "第一章 开始\n阅读正文。"})
        result = self.downloader.download(source)
        self.assertEqual(result.chapter_count, 1)
        self.assertIn("阅读正文。", Path(result.file_path).read_text(encoding="utf-8"))

    def test_explicit_catalog_entry_overrides_detected_latest_chapters(self):
        self.downloader = WebNovelDownloader(self.temporary.name, extraction_rules={"catalog_link_selector": "a.full"})
        source = "https://any.example/books/alpha/"
        soup = self.soup('<div class="chapters"><a href="99.html">第99章</a><a href="100.html">第100章</a></div>'
                         '<a class="full" href="contents.html">全部章节</a>')
        self.assertEqual(self.downloader.resolve_catalog_url(source, soup), source + "contents.html")

    def test_select_option_catalog_pagination(self):
        source = "https://novels.example/alpha/"
        following = source + "index_2.html"
        first = '<ul><li><a href="c1.html">第一章</a></li><li><a href="c2.html">第二章</a></li></ul>'
        options = '<select><option selected value="index_1.html">1-2</option><option value="index_2.html">3-4</option></select>'
        self.pages({following: '<ol><li><a href="c3.html">第三章</a></li><li><a href="c4.html">第四章</a></li></ol>'})
        self.assertEqual(len(self.downloader.extract_chapter_links(source, self.soup(first + options))), 4)

    def test_numeric_pagination_without_next_label(self):
        url = "https://novels.example/alpha/catalog.html"
        soup = self.soup('<div class="pagination"><a href="catalog.html">1</a><a href="catalog.html?page=2">2</a></div>')
        self.assertEqual(self.downloader.find_next_catalog_page(url, soup), url + "?page=2")

    def test_rel_next_and_pg_parameter_follow_same_chapter_only(self):
        url = "https://novels.example/alpha/c1.html"
        soup = self.soup('<link rel="next" href="c1.html?pg=2"><a href="c2.html">下一章</a>')
        self.assertEqual(self.downloader.find_next_chapter_page(url, soup), url + "?pg=2")
        self.assertEqual(self.downloader.find_next_chapter_page(url, self.soup('<a rel="next" href="c2.html">Next chapter</a>')), "")

    def test_unknown_class_text_container_beats_navigation(self):
        text = "这是一段没有特定正文类名的小说内容，仍然应该完整识别。"
        soup = self.soup(f'<nav><a href="/">首页</a></nav><div class="x93"><p>{text}</p><p>继续正文。</p></div>')
        self.assertEqual(self.downloader.extract_content(soup), text + "\n继续正文。")

    def test_jsonld_article_body_is_readable_without_dom_content(self):
        data = {"@type": "Article", "articleBody": "<p>正文一。</p><p>正文二。</p>"}
        soup = self.soup(f'<script type="application/ld+json">{json.dumps(data)}</script>')
        self.assertEqual(self.downloader.extract_content(soup), "正文一。\n正文二。")

    def test_base_url_resolves_relative_chapters(self):
        html = '<base href="/novels/alpha/"><ol><li><a href="one.html">第一章</a></li><li><a href="two.html">第二章</a></li></ol>'
        links = self.catalog(html, "https://base.example/catalog.php")
        self.assertEqual(links[0].url, "https://base.example/novels/alpha/one.html")

    def test_mobile_and_desktop_hosts_are_same_site_but_external_is_not(self):
        self.assertTrue(self.downloader.is_same_site("m.unknown.example", "www.unknown.example"))
        self.assertFalse(self.downloader.is_same_site("unknown.example", "unknown.example.evil.test"))

    def test_custom_rules_allow_unusual_dom_without_site_adapter(self):
        self.downloader = WebNovelDownloader(self.temporary.name, extraction_rules={
            "chapter_link_selector": "nav.x a", "content_selector": ".unusual p",
            "book_title_selector": ".book-label", "catalog_next_selector": "a.continue",
        })
        soup = self.soup('<nav class="x"><a href="dawn.html">Home</a><a href="night.html">Night</a></nav>'
                         '<span class="book-label">自定义书名</span><div class="unusual"><p>正文。</p></div>'
                         '<a class="continue" href="different-route.html">更多条目</a>')
        self.assertEqual([c.title for c in self.downloader.extract_chapter_links(
            "https://rules.example/book/index.html", self.soup('<nav class="x"><a href="dawn.html">Home</a><a href="night.html">Night</a></nav>'))], ["Home", "Night"])
        self.assertEqual(self.downloader.extract_content(soup), "正文。")
        self.assertEqual(self.downloader.extract_book_title(soup, "https://rules.example/"), "自定义书名")
        self.assertEqual(self.downloader.find_next_catalog_page("https://rules.example/", soup), "https://rules.example/different-route.html")

    def test_custom_content_rule_must_not_silently_fall_back(self):
        self.downloader = WebNovelDownloader(self.temporary.name, extraction_rules={"content_selector": ".missing"})
        with self.assertRaisesRegex(WebDownloadError, "未匹配"):
            self.downloader.extract_content(self.soup('<article>其他内容。</article>'))

    def test_invalid_css_rule_reports_configuration_error(self):
        with self.assertRaisesRegex(WebDownloadError, "CSS 选择器无效"):
            WebNovelDownloader(self.temporary.name, extraction_rules={"content_selector": "[bad"})

    def test_empty_directory_page_does_not_produce_partial_success(self):
        source = "https://novels.example/alpha/catalog.html"
        html = '<ol><li><a href="one.html">第一章</a></li><li><a href="two.html">第二章</a></li></ol><a href="catalog.html?page=2">下一页</a>'
        self.pages({source + "?page=2": '<h1>请登录</h1>'})
        with self.assertRaisesRegex(WebDownloadError, "目录分页没有匹配"):
            self.downloader.extract_chapter_links(source, self.soup(html))

    def test_online_checker_accepts_arbitrary_url_and_rules(self):
        import test_bqg5
        url = "https://unlisted.example/books/alpha/contents"
        with patch("test_bqg5.WebNovelDownloader") as factory, patch("builtins.print"):
            factory.return_value.extract_chapter_links.return_value = [object(), object()]
            test_bqg5.main([url, "--chapter-links", ".items a", "--next-page", "a.more"])
        factory.return_value.fetch_soup.assert_called_once_with(url)
        self.assertEqual(factory.call_args.kwargs["extraction_rules"],
                         {"chapter_link_selector": ".items a", "catalog_next_selector": "a.more"})


class GenericRulesDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_advanced_rules_reach_actual_download_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            dialog = WebDownloadDialog()
            self.addCleanup(dialog.close)
            dialog.download_dir = directory
            dialog.url_input.setText("https://unknown.example/")
            dialog.rules_group.setChecked(True)
            dialog.rule_inputs["content_selector"].setText("#body")
            received = []

            def download(downloader, *_args):
                received.append(downloader.parser.rules.copy())
                return downloader._save_txt("规则测试", [("第一章", "正文内容。")], "https://unknown.example/")

            with patch.object(WebNovelDownloader, "download", download), patch("download_dialog.QMessageBox.information"):
                dialog.show()
                dialog.start_download()
                deadline = time.monotonic() + 3
                while dialog.thread is not None and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertIsNone(dialog.thread)
                self.assertEqual(received, [{"content_selector": "#body"}])


if __name__ == "__main__":
    unittest.main()
