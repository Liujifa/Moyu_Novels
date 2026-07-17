import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from bs4 import BeautifulSoup
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from library_view import LibraryView
from reader_window import ReaderWindow
from web_novel_downloader import WebNovelDownloader


class StubManager:
    def __init__(self):
        self.data = {
            "library": [
                {
                    "title": "测试小说",
                    "path": "test.txt",
                    "last_pos": 0,
                }
            ],
            "settings": {
                "font_size": 18,
                "font_color": "#e0e0e0",
                "text_opacity": 1.0,
                "reading_mode": False,
                "language": "CN",
                "first_run": False,
            },
        }

    def get_settings(self):
        return self.data["settings"]

    def update_settings(self, settings):
        self.data["settings"] = settings

    def update_progress(self, path, pos, scroll_value=0, scroll_max=0):
        for novel in self.data["library"]:
            if novel["path"] == path:
                novel["last_pos"] = pos
                return True
        return False


class StubReaderLogic:
    def get_chapters(self, _path):
        return [
            {"title": "第一章", "pos": 0, "index": 0},
            {"title": "第二章", "pos": 100, "index": 1},
            {"title": "第三章", "pos": 200, "index": 2},
        ]


class StubWindowLogic:
    content = "第一章\n" + ("第一章正文\n" * 80) + "第二章\n" + ("第二章正文\n" * 80) + "第三章\n第三章正文"

    def load_txt(self, _path):
        positions = [
            self.content.index("第一章"),
            self.content.index("第二章"),
            self.content.index("第三章"),
        ]
        chapters = [
            {"title": title, "pos": pos, "index": index}
            for index, (title, pos) in enumerate(zip(("第一章", "第二章", "第三章"), positions))
        ]
        return self.content, chapters


class ChapterSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_delayed_progress_does_not_override_pending_chapter(self):
        view = LibraryView(StubManager(), StubReaderLogic())
        self.addCleanup(view.close)
        view.novel_list.setCurrentRow(0)
        self.app.processEvents()

        view.chapter_combo.setCurrentIndex(2)
        view.chapter_combo.activated.emit(2)
        self.assertEqual(view.pending_chapter_pos, 200)

        view.sync_progress("test.txt", 0)
        self.assertEqual(view.chapter_combo.currentIndex(), 2)
        self.assertEqual(view.pending_chapter_pos, 200)

        opened_positions = []
        view.novel_selected.connect(lambda _novel, pos: opened_positions.append(pos))
        view.on_read_selected()

        self.assertEqual(opened_positions, [200])
        self.assertIsNone(view.pending_chapter_pos)

    def test_reselecting_current_chapter_marks_it_for_restart(self):
        view = LibraryView(StubManager(), StubReaderLogic())
        self.addCleanup(view.close)
        view.novel_list.setCurrentRow(0)
        self.app.processEvents()

        self.assertEqual(view.chapter_combo.currentIndex(), 0)
        view.chapter_combo.activated.emit(0)

        self.assertEqual(view.pending_chapter_pos, 0)

    def test_reader_finishes_loading_at_selected_chapter(self):
        manager = StubManager()
        logic = StubWindowLogic()
        window = ReaderWindow(manager, logic)
        self.addCleanup(window.close)
        target_pos = logic.content.index("第三章")

        window.load_novel(
            {
                "title": "测试小说",
                "path": "test.txt",
                "last_pos": target_pos,
                "_restore_saved_scroll": False,
            }
        )
        window.show()
        QTest.qWait(180)

        self.assertEqual(window.reader_area.textCursor().position(), target_pos)
        self.assertFalse(window._restoring_progress)


class DownloaderBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.downloader = WebNovelDownloader("test_downloads")

    def test_next_chapter_is_not_treated_as_chapter_pagination(self):
        current_url = "http://m.bikuxs.com/book/5481804.html?page=3"
        next_chapter_url = "http://m.bikuxs.com/book/5481805.html"
        soup = BeautifulSoup(
            '<a href="5481805.html">下一章</a>',
            "html.parser",
        )

        self.assertFalse(
            self.downloader.is_chapter_pagination_candidate(current_url, next_chapter_url)
        )
        self.assertEqual(self.downloader.find_next_chapter_page(current_url, soup), "")

    def test_next_page_of_same_chapter_is_followed(self):
        current_url = "http://m.bikuxs.com/book/5481804.html"
        soup = BeautifulSoup(
            '<a href="5481804.html?page=2">下一页</a>'
            '<a href="5481805.html">下一章</a>',
            "html.parser",
        )

        self.assertEqual(
            self.downloader.find_next_chapter_page(current_url, soup),
            "http://m.bikuxs.com/book/5481804.html?page=2",
        )

    def test_bikuxs_prefers_desktop_chapter_and_falls_back_as_a_whole(self):
        calls = []

        def fake_collect(url, _title_hint):
            calls.append(url)
            if "www.bikuxs.com" in url:
                return "第一章", []
            return "第一章", ["正文"]

        self.downloader.collect_chapter_pages = fake_collect
        title, content = self.downloader.download_generic_chapter(
            "http://m.bikuxs.com/book/5481804.html",
            "第一章",
        )

        self.assertEqual(title, "第一章")
        self.assertEqual(content, "正文")
        self.assertEqual(
            calls,
            [
                "http://www.bikuxs.com/book/5481804.html",
                "http://m.bikuxs.com/book/5481804.html",
            ],
        )

    def test_rate_limiter_slows_down_and_recovers(self):
        default_interval = self.downloader.DEFAULT_REQUEST_INTERVAL
        self.downloader._register_rate_limit(2.0)

        slowed_interval = self.downloader._request_interval
        self.assertGreater(slowed_interval, default_interval)
        self.assertGreater(self.downloader._cooldown_until, time.monotonic())

        for _ in range(self.downloader.RATE_LIMIT_SUCCESS_WINDOW):
            self.downloader._register_request_success()

        self.assertLess(self.downloader._request_interval, slowed_interval)
        self.assertGreaterEqual(self.downloader._request_interval, default_interval)


if __name__ == "__main__":
    unittest.main()
