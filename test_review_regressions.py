import importlib
import json
import os
import runpy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from bs4 import BeautifulSoup
from PyQt6.QtGui import QAction
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from download_dialog import WebDownloadDialog
from library_manager import LibraryManager
from library_view import LibraryView
from main import MoYuApp
from reader_logic import ReaderLogic
from reader_window import ReaderWindow
from test_core_behaviors import StubManager, StubWindowLogic
from web_novel_downloader import ChapterLink, WebDownloadError, WebNovelDownloader


class LibraryStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / "library.json"
        self.manager = LibraryManager(str(self.path))
        self.novel = self.manager.add_novel("测试小说", str(self.root / "novel.txt"))

    def test_partial_json_write_preserves_original_and_rolls_back_progress(self):
        original = self.path.read_bytes()

        def fail(_data, file, **_kwargs):
            file.write('{"未完成":')
            raise OSError("模拟磁盘写入失败")

        with patch("library_manager.json.dump", side_effect=fail):
            with self.assertRaises(OSError):
                self.manager.update_progress(self.novel["path"], 200, 10, 100)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.novel["last_pos"], 0)
        self.assertEqual(list(self.root.glob(".library-*.tmp")), [])

    def test_replace_failure_rolls_back_added_book(self):
        original = self.path.read_bytes()
        with patch("library_manager.os.replace", side_effect=PermissionError("模拟文件占用")):
            with self.assertRaises(PermissionError):
                self.manager.add_novel("新书", str(self.root / "new.txt"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.manager.data["library"], [self.novel])
        self.assertEqual(list(self.root.glob(".library-*.tmp")), [])

    def test_failed_remove_restores_same_book_object(self):
        with patch.object(self.manager, "save", side_effect=OSError("模拟写入失败")):
            with self.assertRaises(OSError):
                self.manager.remove_novel(self.novel["path"])
        self.assertIs(self.manager.data["library"][0], self.novel)

    def test_failed_settings_save_restores_shared_settings_reference(self):
        settings = self.manager.get_settings()
        old_font = settings["font_size"]
        settings["font_size"] = old_font + 5
        with patch("library_manager.os.replace", side_effect=OSError("模拟写入失败")):
            with self.assertRaises(OSError):
                self.manager.update_settings(settings)
        self.assertIs(self.manager.get_settings(), settings)
        self.assertEqual(settings["font_size"], old_font)
        self.assertEqual(LibraryManager(str(self.path)).get_settings()["font_size"], old_font)

    def test_corrupt_or_invalid_library_is_never_treated_as_empty(self):
        samples = ["{坏数据", "[]", '{"library": {}}', '{"library": [null]}',
                   '{"library": [], "settings": null}',
                   '{"library": [{"title": "测试", "path": "x", "last_pos": "1"}]}']
        for content in samples:
            with self.subTest(content=content):
                self.path.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    LibraryManager(str(self.path))
                self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_legacy_library_retains_progress_and_unknown_fields(self):
        data = {"library": [{"title": "旧书", "path": "old.txt", "last_pos": 1234}],
                "settings": {"font_size": 16}, "custom": {"version": 7}}
        self.path.write_text(json.dumps(data), encoding="utf-8")
        loaded = LibraryManager(str(self.path))
        self.assertEqual(loaded.data["library"][0]["last_pos"], 1234)
        self.assertEqual(loaded.data["custom"], {"version": 7})
        self.assertEqual(loaded.get_settings()["text_opacity"], 1.0)

    def test_invalid_settings_are_normalized_without_touching_books(self):
        self.manager.data["settings"].update(font_size="很大", text_opacity=float("nan"),
                                             language="unknown", reading_mode="true")
        self.path.write_text(json.dumps(self.manager.data), encoding="utf-8")
        loaded = LibraryManager(str(self.path))
        self.assertEqual(loaded.get_settings()["font_size"], 18)
        self.assertEqual(loaded.get_settings()["text_opacity"], 1.0)
        self.assertEqual(loaded.get_settings()["language"], "CN")
        self.assertFalse(loaded.get_settings()["reading_mode"])
        self.assertEqual(loaded.data["library"], [self.novel])

    def test_importing_relative_and_absolute_paths_keeps_one_book(self):
        self.manager.update_progress(self.novel["path"], 200)
        previous_directory = Path.cwd()
        try:
            os.chdir(self.root)
            returned = self.manager.add_novel("重复导入", "novel.txt")
        finally:
            os.chdir(previous_directory)
        self.assertIs(returned, self.novel)
        self.assertEqual(len(self.manager.data["library"]), 1)
        self.assertEqual(returned["last_pos"], 200)


class ReaderAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_reader(self, manager=None, logic=None):
        window = ReaderWindow(manager or StubManager(), logic or StubWindowLogic())
        self.addCleanup(window.close)
        return window

    def wait_for_restore(self, window):
        deadline = time.monotonic() + 5
        while window._restoring_progress and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertFalse(window._restoring_progress)

    def test_failed_first_load_preserves_saved_position(self):
        manager = StubManager()
        manager.data["library"][0]["last_pos"] = 800

        class FailedLogic:
            def load_txt(self, _path):
                return "", []

        window = self.make_reader(manager, FailedLogic())
        self.assertFalse(window.load_novel({"path": "test.txt", "last_pos": 800}))
        window.show()
        QTest.qWait(180)
        self.assertIsNone(window.current_novel)
        self.assertEqual(manager.data["library"][0]["last_pos"], 800)

    def test_failed_switch_keeps_current_document_and_menu(self):
        window = self.make_reader()
        window.load_novel({"path": "test.txt", "last_pos": 0})
        before = window.reader_area.toPlainText()
        actions = list(window.toc_menu.actions())
        with patch.object(window.logic, "load_txt", return_value=("", [])):
            self.assertFalse(window.load_novel({"path": "missing.txt", "last_pos": 900}))
        self.assertEqual(window.reader_area.toPlainText(), before)
        self.assertEqual(window.current_novel["path"], "test.txt")
        self.assertEqual(window.toc_menu.actions(), actions)

    def test_repeated_loads_do_not_leak_toc_actions(self):
        window = self.make_reader()
        window.load_novel({"path": "test.txt", "last_pos": 0})
        action_count = len(window.findChildren(QAction))
        for _ in range(5):
            window.load_novel({"path": "test.txt", "last_pos": 0})
        self.assertEqual(len(window.findChildren(QAction)), action_count)

    def test_unchanged_book_reuses_document_and_reloads_after_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "book.txt"
            path.write_text("第1章 开始\n这是正文。\n第2章 继续\n这是另一段正文。", encoding="utf-8")
            logic = ReaderLogic()
            manager = StubManager()
            manager.data["library"][0]["path"] = str(path)
            window = self.make_reader(manager, logic)
            window.load_novel({"path": str(path), "last_pos": 0})
            target = logic.get_chapters(str(path))[1]["pos"]
            with patch.object(logic, "load_txt", wraps=logic.load_txt) as load:
                with patch.object(window.reader_area, "setPlainText", wraps=window.reader_area.setPlainText) as set_text:
                    window.load_novel({"path": str(path), "last_pos": target, "_restore_saved_scroll": False})
                    window.show()
                    self.wait_for_restore(window)
                    load.assert_not_called()
                    set_text.assert_not_called()
            self.assertEqual(window.reader_area.textCursor().position(), target)
            with open(path, "a", encoding="utf-8") as file:
                file.write("\n第3章 新增\n追加正文。")
            with patch.object(logic, "load_txt", wraps=logic.load_txt) as load:
                window.load_novel({"path": str(path), "last_pos": target})
                self.wait_for_restore(window)
                load.assert_called_once()
            self.assertEqual(window.chapters[-1]["title"], "第3章 新增")
            window.close()

    def test_failed_progress_save_reports_once_and_allows_retry(self):
        window = self.make_reader()
        window.load_novel({"path": "test.txt", "last_pos": 0})
        window.show()
        self.wait_for_restore(window)
        previous = window.current_novel.copy()
        errors = []
        window.save_failed.connect(errors.append)
        with patch.object(window.manager, "update_progress", side_effect=OSError("模拟磁盘已满")):
            window.persist_progress(force=True)
            window.persist_progress(force=True)
        self.assertEqual(window.current_novel, previous)
        self.assertEqual(len(errors), 1)
        self.assertIsNotNone(window.persist_progress(force=True))

    def test_failed_settings_save_restores_library_controls(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = LibraryManager(str(Path(directory) / "library.json"))
            manager.save()
            view = LibraryView(manager, ReaderLogic())
            self.addCleanup(view.close)
            original = manager.get_settings()["font_size"]
            with patch("library_manager.os.replace", side_effect=OSError("模拟写入失败")):
                with patch("library_view.QMessageBox.warning") as warning:
                    view.fs_slider.setValue(original + 5)
                    warning.assert_called_once()
            self.assertEqual(view.fs_slider.value(), original)
            self.assertEqual(view.settings["font_size"], original)

    def test_tray_quit_waits_for_running_download(self):
        class FakeApp:
            quit_calls = 0

            def quit(self):
                self.quit_calls += 1

        with tempfile.TemporaryDirectory() as directory:
            parent = QWidget()
            self.addCleanup(parent.close)
            dialog = WebDownloadDialog(parent=parent)
            self.addCleanup(dialog.close)
            dialog.download_dir = directory
            dialog.url_input.setText("https://example.com/")
            controller = MoYuApp.__new__(MoYuApp)
            controller._quitting = False
            controller._shutdown_pending = 0
            controller.app = FakeApp()
            controller.reader_win = self.make_reader()
            controller.library_win = parent
            controller.main_win = parent

            def download(downloader, *_args):
                while not downloader.is_cancelled:
                    time.sleep(0.01)
                raise WebDownloadError("下载已取消。")

            with patch.object(WebNovelDownloader, "download", download):
                dialog.show()
                dialog.start_download()
                QTest.qWait(30)
                controller.quit_app()
                self.assertEqual(controller.app.quit_calls, 0)
                deadline = time.monotonic() + 3
                while dialog.thread is not None and time.monotonic() < deadline:
                    QTest.qWait(20)
                self.assertIsNone(dialog.thread)
                self.assertEqual(controller.app.quit_calls, 1)
                controller.quit_app()
                self.assertEqual(controller.app.quit_calls, 1)

    def test_tray_quit_handles_already_stopped_thread_once(self):
        controller = MoYuApp.__new__(MoYuApp)
        controller._quitting = False
        controller.app = Mock()
        controller.reader_win = Mock()
        controller.main_win = Mock()
        controller.library_win = Mock()
        dialog = Mock()
        thread = dialog.thread
        thread.isRunning.return_value = False
        controller.library_win.findChildren.return_value = [dialog]
        controller.quit_app()
        controller.app.quit.assert_called_once()
        callback = thread.finished.connect.call_args.args[0]
        callback()
        controller.app.quit.assert_called_once()

    def test_startup_uses_project_library_and_reports_invalid_data(self):
        import main
        with patch("main.QApplication"), patch("main.QMessageBox.critical") as error:
            with patch("main.LibraryManager", side_effect=ValueError("书库损坏")) as manager:
                with self.assertRaises(SystemExit):
                    MoYuApp()
                self.assertEqual(Path(manager.call_args.args[0]), Path(main.__file__).resolve().with_name("library.json"))
                error.assert_called_once()

    def test_windowless_entry_reuses_main_application(self):
        with patch("main.MoYuApp") as application:
            runpy.run_path(str(Path(__file__).resolve().with_name("main.pyw")), run_name="__main__")
        application.assert_called_once_with()
        application.return_value.run.assert_called_once_with()


class ScraperAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.downloader = WebNovelDownloader(self.temporary.name)

    def test_story_paragraph_containing_navigation_words_is_preserved(self):
        text = "他翻看收藏的旧书，又想起了朋友昨天的评论。\n下一章的故事，由他说了算。"
        self.assertEqual(self.downloader.filter_content_lines(text), text)

    def test_intentionally_repeated_long_paragraphs_are_preserved(self):
        paragraph = "他又一次回想起那个雨夜，往事历历在目，耳畔的那句话始终没有消散，久久不能忘怀。"
        text = f"{paragraph}\n其他正文\n{paragraph}"
        self.assertEqual(self.downloader.filter_content_lines(text), text)

    def test_standalone_navigation_and_explicit_prompts_are_removed(self):
        text = "上一章\n正常正文\n下一章\n请收藏本站以便下次阅读\n本章未完，请点击下一页继续阅读"
        self.assertEqual(self.downloader.filter_content_lines(text), "正常正文")

    def test_site_specific_collection_footer_is_removed(self):
        footer = "喜欢测试小说请大家收藏：(m.fhxs.com)测试小说凤凰小说网更新速度最快。"
        self.assertEqual(self.downloader.filter_content_lines(f"正常正文\n{footer}"), "正常正文")

    def test_nested_body_container_excludes_outer_recommendations(self):
        soup = BeautifulSoup('<main><div class="content"><p>这是真正的小说正文。</p></div>'
                             '<div>这是推荐书籍广告。</div></main>', "html.parser")
        self.assertEqual(self.downloader.extract_content(soup), "这是真正的小说正文。")

    def test_old_lossy_chapter_cache_is_refetched(self):
        link = ChapterLink("第1章", "https://example.com/read/1.html", 0)
        path = self.downloader._chapter_cache_path(link.url)
        path.parent.mkdir()
        path.write_text(json.dumps({"version": 1, "url": link.url, "title": link.title,
                                   "content": "旧版残缺正文"}), encoding="utf-8")
        with patch.object(self.downloader, "download_generic_chapter", return_value=(link.title, "完整正文")) as fetch:
            chapters = self.downloader.download_chapter_batch([link])
        fetch.assert_called_once()
        self.assertEqual(chapters, [(link.title, "完整正文")])

    def test_online_smoke_module_import_has_no_network_or_disk_side_effects(self):
        with patch("web_novel_downloader.WebNovelDownloader") as downloader:
            importlib.reload(importlib.import_module("test_bqg5"))
        downloader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
