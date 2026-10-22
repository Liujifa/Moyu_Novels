import os
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from bs4 import BeautifulSoup
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from library_view import LibraryView
from download_dialog import DownloadWorker, WebDownloadDialog
from main import MoYuApp
from reader_logic import ReaderLogic
from reader_window import ReaderWindow
from web_novel_downloader import ChapterLink, WebDownloadError, WebNovelDownloader


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

    def make_reader(self):
        manager = StubManager()
        logic = StubWindowLogic()
        window = ReaderWindow(manager, logic)
        self.addCleanup(window.close)
        return manager, logic, window

    def test_loading_progress_save_cannot_replace_selected_chapter(self):
        manager, logic, window = self.make_reader()
        target = logic.content.index("第三章")
        window.load_novel({"path": "test.txt", "last_pos": target, "_restore_saved_scroll": False})
        window.show()
        window.reader_area.verticalScrollBar().setValue(0)
        self.assertIsNone(window.persist_progress(force=True))
        QTest.qWait(180)
        self.assertEqual(window.reader_area.textCursor().position(), target)
        self.assertGreater(window.reader_area.verticalScrollBar().value(), 0)

    def test_hidden_load_restores_when_shown_later(self):
        _, logic, window = self.make_reader()
        target = logic.content.index("第二章")
        window.load_novel({"path": "test.txt", "last_pos": target, "_restore_saved_scroll": False})
        QTest.qWait(180)
        self.assertTrue(window._restoring_progress)
        window.show()
        QTest.qWait(180)
        self.assertFalse(window._restoring_progress)
        self.assertEqual(window.reader_area.textCursor().position(), target)
        self.assertLessEqual(window.reader_area.cursorRect().top(), 8)

    def test_old_callback_cannot_finish_new_restore_for_same_book(self):
        _, logic, window = self.make_reader()
        window.load_novel({"path": "test.txt", "last_pos": logic.content.index("第三章")})
        old_generation = window._restore_generation
        target = logic.content.index("第二章")
        window.load_novel({"path": "test.txt", "last_pos": target, "_restore_saved_scroll": False})
        window.show()
        window._finish_initial_restore(old_generation, True)
        self.assertTrue(window._restoring_progress)
        QTest.qWait(180)
        self.assertEqual(window.reader_area.textCursor().position(), target)

    def test_toc_jump_supersedes_pending_initial_restore(self):
        _, logic, window = self.make_reader()
        window.load_novel({"path": "test.txt", "last_pos": 0})
        window.show()
        window.jump_to_chapter(1)
        QTest.qWait(180)
        self.assertEqual(window.reader_area.textCursor().position(), logic.content.index("第二章"))
        self.assertLessEqual(window.reader_area.cursorRect().top(), 8)

    def test_same_title_books_are_selected_by_path(self):
        manager = StubManager()
        manager.data["library"].append({"title": "测试小说", "path": "other.txt", "last_pos": 0})
        view = LibraryView(manager, StubReaderLogic())
        self.addCleanup(view.close)
        view.novel_list.setCurrentRow(1)
        self.assertEqual(view.get_selected_novel()["path"], "other.txt")
        view.novel_list.setCurrentRow(0)
        view.select_novel_by_path("other.txt")
        self.assertEqual(view.get_selected_novel()["path"], "other.txt")

    def test_full_library_to_reader_flow_ignores_old_scroll_ratio(self):
        manager = StubManager()
        logic = StubWindowLogic()
        target = logic.content.index("第二章")
        manager.data["library"][0].update(last_pos=target, last_scroll_ratio=0.0)
        view_logic = StubReaderLogic()
        view_logic.get_chapters = lambda _path: logic.load_txt(_path)[1]
        view = LibraryView(manager, view_logic)
        self.addCleanup(view.close)
        reader = ReaderWindow(manager, logic)
        self.addCleanup(reader.close)
        controller = MoYuApp.__new__(MoYuApp)
        controller.reader_win = reader
        controller.main_win = QWidget()
        self.addCleanup(controller.main_win.close)
        view.novel_selected.connect(controller.open_novel)
        reader.progress_changed.connect(view.sync_progress)
        view.novel_list.setCurrentRow(0)
        view.chapter_combo.activated.emit(1)
        view.btn_read.click()
        QTest.qWait(180)
        self.assertEqual(reader.reader_area.textCursor().position(), target)
        self.assertGreater(reader.reader_area.verticalScrollBar().value(), 0)
        self.assertLessEqual(reader.reader_area.cursorRect().top(), 8)

    def test_changing_combo_index_is_respected_on_start(self):
        view = LibraryView(StubManager(), StubReaderLogic())
        self.addCleanup(view.close)
        view.novel_list.setCurrentRow(0)
        view.chapter_combo.setCurrentIndex(2)
        opened = []
        view.novel_selected.connect(lambda novel, pos: opened.append((novel, pos)))
        view.btn_read.click()
        self.assertEqual(opened[0][1], 200)
        self.assertFalse(opened[0][0]["_restore_saved_scroll"])

    def test_long_novel_waits_for_lazy_layout_before_saving(self):
        class LongNovelLogic:
            content = "第1章 开始\n" + ("这是长篇文档中的一段正文。\n" * 120000) + "第2章 目标\n" + ("后续正文。\n" * 2000)

            def load_txt(self, _path):
                return self.content, ReaderLogic().parse_chapters(self.content)

        logic = LongNovelLogic()
        manager = StubManager()
        manager.data["settings"].update(font_size=11, reading_mode=True)
        window = ReaderWindow(manager, logic)
        self.addCleanup(window.close)
        target = logic.content.index("第2章 目标")
        window.load_novel({"path": "test.txt", "last_pos": target, "_restore_saved_scroll": False})
        window.show()
        deadline = time.monotonic() + 5
        while window._restoring_progress and time.monotonic() < deadline:
            QTest.qWait(25)
        self.assertFalse(window._restoring_progress)
        self.assertEqual(window.reader_area.textCursor().position(), target)
        self.assertGreaterEqual(window.current_view_position(), target)
        self.assertLessEqual(window.reader_area.cursorRect().top(), 8)


class DownloaderBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.downloader = WebNovelDownloader(self.temporary.name)

    def make_links(self):
        return [ChapterLink(f"第{n}章 测试", f"https://example.com/read/{n}.html", n - 1) for n in range(1, 4)]

    def test_fhxs_download_page_resolves_to_catalog(self):
        self.assertEqual(
            self.downloader.resolve_catalog_url("https://m.fhxs.com/txtxz/100859.html", BeautifulSoup("", "html.parser")),
            "https://m.fhxs.com/read/100859/",
        )

    def test_fhxs_pagination_and_chapter_scope_preserve_site_order(self):
        root = "https://m.fhxs.com/read/100859/"
        pages = {
            root: '<a href="/read/100859/999.html">第1283章 最新</a>'
                  '<li chapter-id="1"><a href="1.html">第276章 甲</a></li>'
                  '<a href="/xiaoshuo_77.html">心眼子训练100天</a>'
                  '<a href="0_2.html">下一页</a>',
            root + "0_2.html": '<li chapter-id="2"><a href="2.html">第285章 乙</a></li>'
                                   '<li chapter-id="3"><a href="3.html">第276章 丙</a></li>'
                                   '<li chapter-id="4"><a href="/read/77/4.html">第4章 推荐书</a></li>',
        }
        self.downloader.fetch_soup = lambda url, referer="": BeautifulSoup(pages[url], "html.parser")
        links = self.downloader.extract_chapter_links(root, self.downloader.fetch_soup(root))
        self.assertEqual([link.title for link in links], ["第276章 甲", "第285章 乙", "第276章 丙"])
        self.assertEqual([link.index for link in links], [0, 1, 2])

    def test_fhxs_catalog_rejects_chapters_and_other_books_as_next_page(self):
        current = "https://m.fhxs.com/read/100859/"
        self.assertFalse(self.downloader.is_catalog_pagination_candidate(current, current + "999.html"))
        self.assertFalse(self.downloader.is_catalog_pagination_candidate(current, "https://m.fhxs.com/read/55/0_2.html"))

    def test_catalog_page_limit_does_not_silently_truncate(self):
        self.downloader.MAX_CATALOG_PAGES = 1
        soup = BeautifulSoup('<a href="0_2.html">下一页</a>', "html.parser")
        with self.assertRaises(WebDownloadError):
            self.downloader.collect_catalog_pages("https://m.fhxs.com/read/100859/", soup)

    def test_declared_catalog_count_must_match_before_download(self):
        soup = BeautifulSoup('<div>共 4 章</div>', "html.parser")
        self.downloader.fetch_soup_with_site_fallback = lambda url, referer="": (url, soup)
        self.downloader.extract_chapter_links = lambda *_: self.make_links()
        with self.assertRaisesRegex(WebDownloadError, "目录不完整"):
            self.downloader.download("https://m.fhxs.com/txtxz/100859.html")
        self.assertEqual(list(Path(self.temporary.name).glob("*.txt")), [])

    def test_generic_sort_keeps_unnumbered_chapters(self):
        titles = ["序章", "第3章 丙", "第1章 甲", "第2章 乙", "尾声"]
        links = [ChapterLink(t, str(i), i) for i, t in enumerate(titles)]
        self.assertEqual([c.title for c in self.downloader.sort_chapter_links(links)],
                         ["序章", "第1章 甲", "第2章 乙", "第3章 丙", "尾声"])

    def test_generic_descending_catalog_is_reversed(self):
        links = list(reversed(self.make_links()))
        links = [ChapterLink(c.title, c.url, i) for i, c in enumerate(links)]
        self.assertEqual([c.title for c in self.downloader.sort_chapter_links(links)], [c.title for c in self.make_links()])

    def test_partial_download_is_resumed_without_redownloading_good_chapters(self):
        links = self.make_links()
        calls = []

        def flaky(url, title):
            calls.append(url)
            if url == links[1].url:
                raise WebDownloadError("模拟网络失败")
            return title, "可读的章节正文"

        self.downloader.download_generic_chapter = flaky
        with self.assertRaisesRegex(WebDownloadError, "1/3"):
            self.downloader.download_chapter_batch(links)
        self.assertEqual(list(Path(self.temporary.name).glob("*.txt")), [])
        self.assertEqual(calls.count(links[0].url), 1)
        self.assertEqual(calls.count(links[1].url), 2)
        resumed = WebNovelDownloader(self.temporary.name)
        resumed_calls = []

        def finish(url, title):
            resumed_calls.append(url)
            return title, "补齐的章节正文"

        resumed.download_generic_chapter = finish
        chapters = resumed.download_chapter_batch(links)
        self.assertEqual(resumed_calls, [links[1].url])
        self.assertEqual([c[0] for c in chapters], [c.title for c in links])
        result = resumed._save_txt("测试小说", chapters, "https://example.com/")
        self.assertTrue(Path(result.file_path).is_file())
        self.assertEqual(list((Path(self.temporary.name) / ".chapter_cache").glob("*.json")), [])

    def test_transient_failure_is_retried(self):
        calls = []

        def flaky(url, title):
            calls.append(url)
            if len(calls) == 1:
                raise WebDownloadError("临时失败")
            return title, "有效正文"

        self.downloader.download_generic_chapter = flaky
        self.assertEqual(len(self.downloader.download_chapter_batch(self.make_links()[:1])), 1)
        self.assertEqual(len(calls), 2)

    def test_missing_later_chapter_page_fails_entire_chapter(self):
        self.downloader.fetch_chapter_page_content = lambda url, referer="": (
            ("第一页正文", "第1章", url + "?page=2") if "?" not in url else ("", "第1章", "")
        )
        with self.assertRaisesRegex(WebDownloadError, "正文缺失"):
            self.downloader.collect_chapter_pages("https://example.com/read/1.html")

    def test_cancellation_interrupts_rate_limit_wait(self):
        self.downloader.is_cancelled = True
        self.downloader._cooldown_until = time.monotonic() + 60
        started = time.monotonic()
        with self.assertRaises(WebDownloadError):
            self.downloader._wait_for_request_slot()
        self.assertLess(time.monotonic() - started, 0.5)

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


class ChapterIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.logic = ReaderLogic()
        self.downloader = WebNovelDownloader(str(self.root))

    def test_downloaded_index_excludes_headings_inside_body(self):
        result = self.downloader._save_txt("测试", [
            ("第1章 开始", "正文\n第一章……\n继续正文\n\n孤立段落\n\n尾段"),
            ("人物表", "张三和李四"),
        ], "https://example.com/")
        content, chapters = self.logic.load_txt(result.file_path)
        self.assertEqual([c["title"] for c in chapters], ["第1章 开始", "人物表"])
        self.assertIn("第一章……", content)
        self.assertEqual(self.logic.get_chapters(result.file_path), chapters)

    def test_legacy_download_uses_verified_paragraph_boundaries(self):
        content = ("测试\nSource: https://example.com/\nChapters: 2\n\n"
                   "第1章 开始\n\n正文\n第一章……\n其他正文\n\n第2章 继续\n\n正文\n\n")
        self.assertEqual([c["title"] for c in self.logic.parse_chapters(content)], ["第1章 开始", "第2章 继续"])

    def test_modified_txt_invalidates_sidecar_and_chapter_cache(self):
        result = self.downloader._save_txt("测试", [("第1章", "正文\n第一章……\n继续")], "https://example.com/")
        self.assertEqual(len(self.logic.get_chapters(result.file_path)), 1)
        with open(result.file_path, "a", encoding="utf-8") as file:
            file.write("第2章 新增\n新增正文\n")
        self.assertIsNone(self.logic._load_chapter_index(result.file_path))
        titles = [c["title"] for c in self.logic.get_chapters(result.file_path)]
        self.assertIn("第2章 新增", titles)

    def test_corrupt_index_falls_back_to_txt_parser(self):
        result = self.downloader._save_txt("测试", [("第1章", "正文")], "https://example.com/")
        Path(result.file_path + ".chapters.json").write_text("{坏数据", encoding="utf-8")
        self.assertEqual(self.logic.get_chapters(result.file_path)[0]["title"], "第1章")

    def test_chapter_offsets_use_qt_utf16_positions_for_emoji(self):
        content = "第一章\n正文😀𠮷\n第二章\n正文"
        expected = len(content[:content.index("第二章")].encode("utf-16-le")) // 2
        chapters = self.logic.parse_chapters(content)
        self.assertEqual(next(c["pos"] for c in chapters if c["title"] == "第二章"), expected)
        path = self.root / "emoji.txt"
        path.write_text(content, encoding="utf-8")
        self.assertEqual(self.logic.get_chapters(str(path)), self.logic.load_txt(str(path))[1])

    def test_chapter_index_checksum_matches_exact_saved_bytes(self):
        result = self.downloader._save_txt("测试", [("第1章", "正文😀"), ("第2章", "正文")], "https://example.com/")
        metadata = json.loads(Path(result.file_path + ".chapters.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["sha256"], hashlib.sha256(Path(result.file_path).read_bytes()).hexdigest())
        self.assertEqual(len(metadata["chapters"]), 2)

    def test_saving_same_title_quickly_never_overwrites_previous_file(self):
        paths = [self.downloader._save_txt("测试", [("第1章", str(i))], "https://example.com/").file_path for i in range(3)]
        self.assertEqual(len(set(paths)), 3)
        for i, path in enumerate(paths):
            self.assertIn(f"\n\n{i}\n\n", Path(path).read_text(encoding="utf-8"))

    def test_index_write_failure_removes_incomplete_output(self):
        with patch.object(self.downloader, "_write_json_atomic", side_effect=OSError("模拟磁盘失败")):
            with self.assertRaises(OSError):
                self.downloader._save_txt("测试", [("第1章", "正文")], "https://example.com/")
        self.assertEqual(list(self.root.glob("*.txt")), [])


class DownloadDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_abort_before_worker_starts_is_preserved(self):
        worker = DownloadWorker("https://example.com/", "", "none", "unused")
        worker.abort()
        failures = []
        worker.failed.connect(failures.append)
        with tempfile.TemporaryDirectory() as directory:
            worker.download_dir = directory
            with patch.object(WebNovelDownloader, "_download_generic_book") as fetch:
                worker.run()
                fetch.assert_not_called()
        self.assertEqual(len(failures), 1)

    def test_cancel_keeps_dialog_alive_until_thread_exits(self):
        dialog = WebDownloadDialog()
        self.addCleanup(dialog.close)
        dialog.show()

        class RunningThread:
            def isRunning(self):
                return True

        class Worker:
            aborted = False

            def abort(self):
                self.aborted = True

        dialog.thread = RunningThread()
        worker = Worker()
        dialog.worker = worker
        dialog.reject()
        self.assertTrue(dialog.isVisible())
        self.assertTrue(worker.aborted)
        dialog.on_thread_finished()
        self.assertFalse(dialog.isVisible())
        self.assertIsNone(dialog.thread)

    def test_real_worker_thread_finishes_before_dialog_accepts(self):
        with tempfile.TemporaryDirectory() as directory:
            dialog = WebDownloadDialog()
            self.addCleanup(dialog.close)
            dialog.download_dir = directory
            dialog.url_input.setText("https://example.com/")

            def download(downloader, *_):
                return downloader._save_txt("线程测试", [("第1章", "正文")], "https://example.com/")

            with patch.object(WebNovelDownloader, "download", download), patch("download_dialog.QMessageBox.information"):
                dialog.show()
                dialog.start_download()
                deadline = time.monotonic() + 3
                while dialog.thread is not None and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertIsNone(dialog.thread)
                self.assertEqual(dialog.result_data["chapter_count"], 1)
                self.assertFalse(dialog.isVisible())

    def test_cancel_real_worker_exits_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            dialog = WebDownloadDialog()
            self.addCleanup(dialog.close)
            dialog.download_dir = directory
            dialog.url_input.setText("https://example.com/")

            def download(downloader, *_):
                while not downloader.is_cancelled:
                    time.sleep(0.01)
                raise WebDownloadError("下载已取消。")

            with patch.object(WebNovelDownloader, "download", download), patch("download_dialog.QMessageBox.critical") as message:
                dialog.show()
                dialog.start_download()
                QTest.qWait(30)
                dialog.close()
                deadline = time.monotonic() + 3
                while dialog.thread is not None and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertIsNone(dialog.thread)
                self.assertIsNone(dialog.result_data)
                self.assertFalse(dialog.isVisible())
                message.assert_not_called()

    def test_failed_thread_allows_retry_in_same_dialog(self):
        with tempfile.TemporaryDirectory() as directory:
            dialog = WebDownloadDialog()
            self.addCleanup(dialog.close)
            dialog.download_dir = directory
            dialog.url_input.setText("https://example.com/")
            attempts = []

            def download(downloader, *_):
                attempts.append(1)
                if len(attempts) == 1:
                    raise WebDownloadError("模拟网络失败")
                return downloader._save_txt("线程重试", [("第1章", "正文")], "https://example.com/")

            with (patch.object(WebNovelDownloader, "download", download),
                  patch("download_dialog.QMessageBox.critical"),
                  patch("download_dialog.QMessageBox.information")):
                dialog.show()
                for _ in range(2):
                    dialog.start_download()
                    deadline = time.monotonic() + 3
                    while dialog.thread is not None and time.monotonic() < deadline:
                        QTest.qWait(20)
                    self.assertIsNone(dialog.thread)
                    if len(attempts) == 1:
                        self.assertTrue(dialog.btn_download.isEnabled())
                        self.assertTrue(dialog.isVisible())
                self.assertEqual(dialog.result_data["chapter_count"], 1)


if __name__ == "__main__":
    unittest.main()
