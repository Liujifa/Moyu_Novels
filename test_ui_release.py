import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import app_paths
from download_dialog import WebDownloadDialog
from library_manager import LibraryManager
from library_view import LibraryView
from reader_logic import ReaderLogic


class ReleasePathsTests(unittest.TestCase):
    def test_frozen_data_is_outside_bundle(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"LOCALAPPDATA": temporary}):
            with patch.dict(os.environ, {"MOYU_DATA_DIR": ""}), patch.object(app_paths.sys, "frozen", True, create=True):
                path = app_paths.data_directory()
            self.assertEqual(path, Path(temporary) / "MoYuReader")
            self.assertTrue(path.is_dir())

    def test_explicit_test_data_directory_is_created(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "独立数据"
            with patch.dict(os.environ, {"MOYU_DATA_DIR": str(target)}):
                self.assertEqual(app_paths.data_directory(), target.resolve())
            self.assertTrue(target.is_dir())

    def test_source_data_remains_backward_compatible(self):
        with patch.dict(os.environ, {"MOYU_DATA_DIR": ""}), patch.object(app_paths.sys, "frozen", False, create=True):
            self.assertEqual(app_paths.data_directory(), Path(app_paths.__file__).resolve().parent)


class LibraryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.manager = LibraryManager(str(Path(self.temporary.name) / "library.json"))
        self.view = LibraryView(self.manager, ReaderLogic())
        self.addCleanup(self.view.close)

    def add_book(self, title):
        path = Path(self.temporary.name) / (title + ".txt")
        path.write_text("第一章 开始\n故事的正文。\n第二章 继续\n故事还在继续。", encoding="utf-8")
        self.manager.add_novel(title, str(path))
        self.view.refresh_library()
        self.view.select_novel_by_path(str(path))
        return path

    def test_empty_library_disables_actions(self):
        self.assertFalse(self.view.btn_read.isEnabled())
        self.assertFalse(self.view.btn_delete.isEnabled())
        self.assertFalse(self.view.empty_label.isHidden())

    def test_search_hiding_selected_book_clears_reading_target(self):
        self.add_book("星河")
        self.assertTrue(self.view.btn_read.isEnabled())
        self.view.search_input.setText("其他书")
        self.assertIsNone(self.view.get_selected_novel())
        self.assertFalse(self.view.btn_read.isEnabled())
        self.assertFalse(self.view.chapter_combo.isEnabled())
        self.view.search_input.clear()
        self.assertFalse(self.view.novel_list.item(0).isHidden())

    def test_search_and_language_change_keep_manual_chapter(self):
        self.add_book("Star 星河")
        self.view.chapter_combo.setCurrentIndex(1)
        position = self.view.pending_chapter_pos
        self.view.search_input.setText("STAR")
        self.view.toggle_language()
        self.assertEqual(self.view.pending_chapter_pos, position)
        self.assertTrue(self.view.btn_read.isEnabled())
        self.assertEqual(self.view.search_input.placeholderText(), "Search your library…")
        self.assertIn("18 pt", self.view.fs_label.text())

    def test_selecting_imported_book_clears_unmatched_search(self):
        self.view.search_input.setText("其他书")
        path = self.add_book("星河")
        self.assertEqual(self.view.search_input.text(), "")
        self.assertEqual(self.view.get_selected_novel()["path"], str(path))
        self.assertTrue(self.view.btn_read.isEnabled())

    def test_expanded_download_form_can_scroll_at_small_height(self):
        dialog = WebDownloadDialog(parent=self.view)
        self.addCleanup(dialog.close)
        dialog.resize(660, 600)
        dialog.rules_group.setChecked(True)
        dialog.show()
        self.app.processEvents()
        self.assertEqual(dialog.height(), 600)
        self.assertGreater(dialog.content_scroll.verticalScrollBar().maximum(), 0)
        self.assertLess(dialog.btn_download.geometry().bottom(), dialog.height())


if __name__ == "__main__":
    unittest.main()
