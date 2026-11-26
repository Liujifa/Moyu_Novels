"""用虚拟时钟验证真实请求调度，避免测试等待数分钟。"""

import json
import tempfile
import unittest
from email.utils import formatdate
from unittest.mock import patch

from requests import Response

from web_novel_downloader import WebDownloadError, WebNovelDownloader, WebRateLimitError


class RequestPacingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.downloader = WebNovelDownloader(self.temporary.name)
        self.clock = 1000.0
        self.wall = 1800000000.0
        self.url = "https://novel.example/book/1.html"
        for name, replacement in (("monotonic", lambda: self.clock),
                                  ("time", lambda: self.wall + self.clock - 1000),
                                  ("sleep", self.sleep)):
            mock = patch("web_novel_downloader.time." + name, replacement)
            mock.start()
            self.addCleanup(mock.stop)

    def sleep(self, seconds):
        self.clock += seconds

    def response(self, status=200, retry_after=None):
        response = Response()
        response.status_code = status
        response.url = self.url
        response.encoding = "utf-8"
        response._content = b"<article>body</article>"
        if retry_after is not None:
            response.headers["Retry-After"] = retry_after
        return response

    def test_retry_after_supports_long_delays_and_http_dates(self):
        for raw, expected in (("1200", 1200), (formatdate(self.wall + 180, usegmt=True), 180),
                              ("nan", 60), ("invalid", 60), ("0", 0)):
            with self.subTest(raw=raw):
                self.assertEqual(self.downloader._retry_after_seconds(self.response(429, raw), 0), expected)
        self.assertEqual(self.downloader._retry_after_seconds(self.response(429), 1), 120)

    def test_in_flight_429s_share_one_penalty_and_next_failure_escalates(self):
        self.downloader._register_rate_limit(1, self.url)
        profile = self.downloader._request_profile(self.url)
        self.assertEqual((profile.interval, profile.penalties), (6, 1))
        self.downloader._register_rate_limit(1, self.url)
        self.assertEqual((profile.interval, profile.penalties), (6, 1))
        self.clock += 61
        self.assertEqual(self.downloader._register_rate_limit(1, self.url), 120)
        self.assertEqual((profile.interval, profile.penalties), (12, 2))

    def test_restart_remembers_interval_and_cooldown_only_for_same_host(self):
        self.downloader._register_rate_limit(1200, self.url)
        restarted = WebNovelDownloader(self.temporary.name)
        profile = restarted._request_profile(self.url)
        self.assertEqual((profile.interval, profile.cooldown_until), (6, self.clock + 1200))
        self.assertEqual(restarted._request_profile("https://other.example/").interval, 1)
        self.assertEqual(restarted._request_profile("https://other.example/").cooldown_until, 0)

    def test_corrupt_saved_policy_does_not_break_downloads(self):
        path = self.downloader._request_profile_path("novel.example")
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({"version": 1, "host": "novel.example", "interval": "nan",
                                    "blocked_until": self.wall + 1200, "penalties": 1, "updated": self.wall}))
        self.assertEqual(self.downloader._request_profile(self.url).interval, 1)

    def test_get_cools_down_then_retains_slow_rate_after_successes(self):
        timestamps = []

        def get(*_args, **_kwargs):
            timestamps.append(self.clock)
            return self.response(429 if len(timestamps) == 1 else 200)

        with patch.object(self.downloader.session, "get", side_effect=get):
            for _ in range(25):
                self.downloader.fetch_html(self.url)
        self.assertGreaterEqual(timestamps[1] - timestamps[0], 60)
        self.assertTrue(all(b - a >= 5.99 for a, b in zip(timestamps[1:], timestamps[2:])))
        self.assertEqual(self.downloader._request_profile(self.url).in_flight, 0)

    def test_post_and_get_share_the_same_pacing_and_retry_after(self):
        timestamps = []

        def post(*_args, **_kwargs):
            timestamps.append(self.clock)
            return self.response(429, "180") if len(timestamps) == 1 else self.response()

        with patch.object(self.downloader.session, "post", side_effect=post), \
                patch.object(self.downloader.session, "get", return_value=self.response()):
            self.downloader.post_html(self.url, {}, self.url)
            self.downloader.fetch_html(self.url)
        self.assertGreaterEqual(timestamps[1] - timestamps[0], 180)
        self.assertGreaterEqual(self.clock - timestamps[1], 6)

    def test_conservative_mode_serializes_in_flight_requests(self):
        downloader = WebNovelDownloader(self.temporary.name, request_mode="conservative")
        self.assertEqual(downloader.MAX_WORKERS, 1)
        downloader._wait_for_request_slot(self.url)
        profile = downloader._request_profile(self.url)
        self.assertEqual(profile.in_flight, 1)
        # 即使下一个时间槽已到，也需要等前一个请求释放。
        self.clock += 10
        waited = []

        def release_on_sleep(seconds):
            waited.append(seconds)
            downloader._release_request_slot(self.url)
            self.sleep(seconds)

        with patch("web_novel_downloader.time.sleep", release_on_sleep):
            downloader._wait_for_request_slot(self.url)
        self.assertTrue(waited)
        self.assertEqual(profile.in_flight, 1)
        downloader._release_request_slot(self.url)

    def test_wait_countdown_can_be_cancelled_without_resetting_progress(self):
        statuses = []

        def status(text):
            statuses.append(text)
            self.downloader.is_cancelled = True

        self.downloader.status_callback = status
        self.downloader._register_rate_limit(60, self.url)
        with self.assertRaisesRegex(WebDownloadError, "取消"):
            self.downloader._wait_for_request_slot(self.url)
        self.assertTrue(statuses)
        self.assertLess(self.clock, 1001)

    def test_repeated_limits_stop_after_bounded_probes_and_remember_cooldown(self):
        with patch.object(self.downloader.session, "get", return_value=self.response(429)) as get:
            with self.assertRaises(WebRateLimitError):
                self.downloader.fetch_html(self.url)
        self.assertEqual(get.call_count, 5)
        self.assertEqual(self.downloader._request_profile(self.url).in_flight, 0)
        restarted = WebNovelDownloader(self.temporary.name)
        self.assertGreater(restarted._request_profile(self.url).cooldown_until, self.clock)


if __name__ == "__main__":
    unittest.main()
