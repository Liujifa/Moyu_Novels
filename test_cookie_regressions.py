import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from requests import Request, Response

from browser_cookie_importer import CookieImportError, _aes_gcm_decrypt, _decrypt_chromium_value, import_cookies_from_file
from web_novel_downloader import WebDownloadError, WebNovelDownloader


class CookieImportRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "cookies.txt"

    def test_windows_aes_gcm_known_vector(self):
        # NIST 的公开 AES-GCM 测试向量，不读取浏览器真实密钥或 Cookie。
        decrypted = _aes_gcm_decrypt(bytes(16), bytes(12),
                                     bytes.fromhex("0388dace60b6a392f328c2b971b2fe78"),
                                     bytes.fromhex("ab6e47d42cec13bdf53a67b21257bddf"), "EN")
        self.assertEqual(decrypted, bytes(16))

    def test_app_bound_cookie_reports_file_export_workaround(self):
        with self.assertRaisesRegex(CookieImportError, "App-Bound Encryption"):
            _decrypt_chromium_value(b"v20" + bytes(40), bytes(32), "EN")

    def test_chromium_domain_hash_is_not_part_of_cookie_value(self):
        host = ".example.com"
        plain = hashlib.sha256(host.encode()).digest() + b"session-token"
        with patch("browser_cookie_importer._aes_gcm_decrypt", return_value=plain):
            value = _decrypt_chromium_value(b"v10" + bytes(40), bytes(32), "CN", host)
        self.assertEqual(value, "session-token")

    def test_json_import_matches_parent_domain_and_excludes_lookalikes(self):
        self.path.write_text(json.dumps([
            {"domain": ".example.com", "name": "session", "value": "valid"},
            {"domain": ".notexample.com", "name": "wrong", "value": "unrelated"},
            {"domain": "example.com", "hostOnly": True, "name": "host-only", "value": "root-only"},
            {"domain": ".example.com", "name": "expired", "value": "old", "expirationDate": 1},
        ]), encoding="utf-8")
        result = import_cookies_from_file(str(self.path), "www.example.com")
        self.assertEqual(result.cookie_header, "session=valid")

    def test_netscape_httponly_cookie_is_preserved(self):
        self.path.write_text("# Netscape HTTP Cookie File\n#HttpOnly_.example.com\tTRUE\t/\tTRUE\t0\tsession\tvalid\n", encoding="utf-8")
        self.assertEqual(import_cookies_from_file(str(self.path), "www.example.com").cookie_header, "session=valid")

    def test_file_import_reaches_downloader_session(self):
        self.path.write_text(json.dumps({"cookies": [{"domain": ".example.com", "name": "session", "value": "valid"}]}), encoding="utf-8")
        downloader = WebNovelDownloader(self.temporary.name)
        downloader._import_browser_cookie(str(self.path), "www.example.com")
        self.assertEqual(downloader.session.prepare_request(Request("GET", "https://www.example.com/")).headers["Cookie"], "session=valid")
        self.assertEqual(downloader._cookie_domains("www.example.com"), ["www.example.com"])

    def test_http_200_captcha_is_not_accepted_as_novel(self):
        downloader = WebNovelDownloader(self.temporary.name)
        response = Response()
        response.status_code = 200
        response.url = "https://www.example.com/WAF/VERIFY/CAPTCHA"
        response.encoding = "utf-8"
        response._content = b'<input name="GOEDGE_WAF_CAPTCHA_CODE">'
        with patch.object(downloader.session, "get", return_value=response):
            with self.assertRaisesRegex(WebDownloadError, "身份验证"):
                downloader.download("https://www.example.com/book/")
        self.assertEqual(list(Path(self.temporary.name).glob("*.txt")), [])


if __name__ == "__main__":
    unittest.main()
