import base64
import json
import tempfile
import unittest
from pathlib import Path

from bs4 import BeautifulSoup
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from ajax_catalog import CatalogProtocolError, EncryptedCatalogSpec, load_encrypted_catalog, parse_cipher_config
from web_novel_downloader import WebDownloadError, WebNovelDownloader


KEY = b"0" * 32
IV = b"1" * 16
CIPHER_SCRIPT = """class AESCrypt {
    constructor(key) { this.iv = CryptoJS.enc.Utf8.parse('1111111111111111'); }
    encrypt(data) { return CryptoJS.AES.encrypt(data, this.key, {mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.Pkcs7}); }
}
function chapterPageAjxa(data) { const crypt = new AESCrypt('00000000000000000000000000000000'); return crypt.encrypt(data); }
"""


class AjaxCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.downloader = WebNovelDownloader(self.temporary.name)
        self.base = "https://unlisted.example/book/AB.html"
        self.html = ('<div class="chapter_list"><a href="AB-1.html">第1章</a><a href="AB-2.html">第2章</a></div>'
                     '<div data-aid="AB"><span class="chapter_page"><select>'
                     '<option value="1">1-2章</option><option value="2">3-4章</option>'
                     '<option value="3">5-6章</option></select></span></div>'
                     '<script src="/jquery.min.js"></script><script src="/catalog-helper.js"></script>')
        self.rows = {page: [{"articleid": "99", "chaptername": f"第{number}章", "chapterurl": f"/book/AB-{number}.html",
                             "chapterorder": str(number)} for number in numbers]
                     for page, numbers in ((1, (1, 2)), (2, (3, 4)), (3, (5,)))}
        self.requested_pages = []
        self.script_urls = []
        self.error_code = 0

        def fetch(url, **_kwargs):
            self.script_urls.append(url)
            return CIPHER_SCRIPT

        def post(url, payload, referer, extra_headers=None):
            self.assertEqual(url, "https://unlisted.example/index.php?action=loadChapterPage")
            self.assertEqual(referer, self.base)
            self.assertEqual(extra_headers, {"X-Requested-With": "XMLHttpRequest"})
            decoded = json.loads(unpad(AES.new(KEY, AES.MODE_CBC, IV).decrypt(base64.b64decode(payload["data"])), 16))
            self.assertEqual(decoded["id"], "AB")
            self.assertIs(type(decoded["page"]), int)
            self.requested_pages.append(decoded["page"])
            return json.dumps({"code": self.error_code, "data": self.rows[decoded["page"]]})

        self.downloader.fetch_html = fetch
        self.downloader.post_html = post

    def load(self):
        return self.downloader.extract_chapter_links(self.base, BeautifulSoup(self.html, "html.parser"))

    def test_unknown_domain_loads_every_catalog_page_in_order(self):
        chapters = self.load()
        self.assertEqual([chapter.title for chapter in chapters], [f"第{n}章" for n in range(1, 6)])
        self.assertEqual([chapter.index for chapter in chapters], list(range(5)))
        self.assertEqual(self.requested_pages, [1, 2, 3])
        self.assertEqual(self.script_urls, ["https://unlisted.example/catalog-helper.js"])

    def test_cross_site_scripts_are_not_requested(self):
        self.html = self.html.replace('<script src="/catalog-helper.js">', '<script src="https://external.example/helper.js"></script><script src="/catalog-helper.js">')
        self.assertEqual(len(self.load()), 5)
        self.assertNotIn("https://external.example/helper.js", self.script_urls)

    def test_missing_middle_page_is_an_error(self):
        self.rows[2] = self.rows[2][:1]
        with self.assertRaisesRegex(WebDownloadError, "章节数量不完整"):
            self.load()

    def test_empty_last_page_is_an_error(self):
        self.rows[3] = []
        with self.assertRaisesRegex(WebDownloadError, "章节数量不完整"):
            self.load()

    def test_server_repeating_first_page_is_an_error(self):
        self.rows[2] = self.rows[1]
        with self.assertRaisesRegex(WebDownloadError, "重复返回章节"):
            self.load()

    def test_different_book_response_is_an_error(self):
        self.rows[2][0]["articleid"] = "100"
        with self.assertRaisesRegex(WebDownloadError, "其他书籍"):
            self.load()

    def test_wrong_order_is_an_error(self):
        self.rows[2][0]["chapterorder"] = "7"
        with self.assertRaisesRegex(WebDownloadError, "顺序或范围不一致"):
            self.load()

    def test_external_chapter_url_is_rejected(self):
        self.rows[2][0]["chapterurl"] = "https://external.example/chapter.html"
        with self.assertRaisesRegex(WebDownloadError, "同站链接"):
            self.load()

    def test_api_error_response_is_not_accepted(self):
        self.error_code = 1
        with self.assertRaisesRegex(WebDownloadError, "请求失败"):
            self.load()

    def test_html_error_response_is_not_accepted(self):
        self.downloader.post_html = lambda *_args, **_kwargs: "<html>server error</html>"
        with self.assertRaisesRegex(WebDownloadError, "有效 JSON"):
            self.load()

    def test_response_must_include_chapters_visible_in_original_page(self):
        self.html = self.html.replace('href="AB-1.html"', 'href="different-1.html"')
        with self.assertRaisesRegex(WebDownloadError, "当前页面的书籍不一致"):
            self.load()

    def test_partial_last_page_must_include_declared_latest_chapter(self):
        self.html = '<meta property="og:novel:latest_chapter_url" content="http://unlisted.example/book/AB-6.html">' + self.html
        with self.assertRaisesRegex(WebDownloadError, "尚未包含.*最新章节"):
            self.load()

    def test_latest_chapter_check_accepts_http_metadata_on_https_page(self):
        self.html = '<meta property="og:novel:latest_chapter_url" content="http://unlisted.example/book/AB-5.html">' + self.html
        self.assertEqual(len(self.load()), 5)

    def test_cancellation_stops_before_following_page(self):
        post = self.downloader.post_html

        def cancel(*args, **kwargs):
            result = post(*args, **kwargs)
            self.downloader.is_cancelled = True
            return result

        self.downloader.post_html = cancel
        with self.assertRaisesRegex(WebDownloadError, "已取消"):
            self.load()
        self.assertEqual(self.requested_pages, [1])

    def test_page_limit_is_checked_before_network_requests(self):
        self.downloader.MAX_CATALOG_PAGES = 2
        with self.assertRaisesRegex(WebDownloadError, "超过 2 页"):
            self.load()
        self.assertEqual(self.script_urls, [])

    def test_noncontiguous_declared_ranges_are_rejected(self):
        soup = BeautifulSoup(self.html.replace("3-4章", "4-5章"), "html.parser")
        with self.assertRaisesRegex(CatalogProtocolError, "不连续"):
            EncryptedCatalogSpec.from_page(soup, 200)

    def test_unrecognized_protocol_preserves_incomplete_catalog_guard(self):
        self.downloader.fetch_html = lambda *_args, **_kwargs: "function unsupported() {}"
        with self.assertRaisesRegex(WebDownloadError, "脚本分页"):
            self.load()
        self.assertEqual(self.requested_pages, [])

    def test_invalid_cipher_key_is_rejected(self):
        with self.assertRaisesRegex(CatalogProtocolError, "AES 配置无效"):
            parse_cipher_config(CIPHER_SCRIPT.replace("00000000000000000000000000000000", "short"))

    def test_explicit_catalog_pagination_rule_takes_priority(self):
        self.downloader.parser.rules["catalog_next_selector"] = "a.more"
        soup = BeautifulSoup(self.html, "html.parser")
        entries = self.downloader.parser.catalog_links(self.base, soup)
        self.assertIsNone(load_encrypted_catalog(self.downloader, self.base, soup, entries))
        self.assertEqual(self.script_urls, [])


if __name__ == "__main__":
    unittest.main()
