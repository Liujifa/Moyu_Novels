import os

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import styles
from download_dialog import WebDownloadDialog
from app_paths import APP_VERSION, data_directory, resource_path


TRANSLATIONS = {
    "CN": {
        "lib_title": "\u5c0f\u8bf4\u4e66\u5e93",
        "add_novel": "\u6dfb\u52a0\u5c0f\u8bf4 (TXT)",
        "delete_novel": "\u5220\u9664\u5c0f\u8bf4",
        "download_web": "\u7f51\u9875\u4e0b\u8f7d TXT",
        "start_reading": "\u5f00\u59cb\u9605\u8bfb",
        "settings": "\u9605\u8bfb\u8bbe\u7f6e",
        "font_size": "\u5b57\u4f53\u5927\u5c0f",
        "text_opacity": "\u6587\u5b57\u900f\u660e\u5ea6",
        "stealth_mode": "\u9605\u8bfb\u6a21\u5f0f",
        "change_color": "\u66f4\u6539\u6587\u5b57\u989c\u8272",
        "preview_title": "\u6837\u5f0f\u9884\u89c8",
        "lang_toggle": "\u5207\u6362\u8bed\u8a00 / English",
        "preview_text": "\u8fd9\u91cc\u662f\u6837\u5f0f\u9884\u89c8\u533a\uff0c\u7528\u6765\u68c0\u67e5\u5b57\u4f53\u5927\u5c0f\u3001\u989c\u8272\u548c\u900f\u660e\u5ea6\u662f\u5426\u5408\u9002\u3002\n\n\u8c03\u6574\u53f3\u4fa7\u8bbe\u7f6e\u540e\uff0c\u8fd9\u91cc\u7684\u663e\u793a\u4f1a\u7acb\u5373\u66f4\u65b0\u3002",
        "chapter_select": "\u7ae0\u8282\u5b9a\u4f4d",
        "current_progress": "\u5f53\u524d\u7eed\u8bfb\u7ae0\u8282\uff1a",
        "next_start": "\u5373\u5c06\u4ece\u8fd9\u91cc\u5f00\u59cb\uff1a",
        "no_chapters": "\u672a\u8bc6\u522b\u5230\u7ae0\u8282\uff0c\u5c06\u6309\u4e0a\u6b21\u9605\u8bfb\u4f4d\u7f6e\u7ee7\u7eed\u3002",
        "delete_confirm_title": "\u5220\u9664\u5c0f\u8bf4",
        "storage_failed": "保存书库失败",
        "delete_confirm_text": "\u786e\u5b9a\u8981\u5c06\u300a{title}\u300b\u4ece\u4e66\u5e93\u4e2d\u79fb\u9664\u5417\uff1f\n\n\u8fd9\u4e0d\u4f1a\u5220\u9664\u539f\u59cb TXT \u6587\u4ef6\u3002",
    },
    "EN": {
        "lib_title": "Novel Library",
        "add_novel": "Add Novel (TXT)",
        "delete_novel": "Remove Novel",
        "download_web": "Download TXT",
        "start_reading": "Start Reading",
        "settings": "Reading Settings",
        "font_size": "Font Size",
        "text_opacity": "Text Opacity",
        "stealth_mode": "Reading Mode",
        "change_color": "Change Text Color",
        "preview_title": "Style Preview",
        "lang_toggle": "Language / \u4e2d\u6587",
        "preview_text": "This preview area reflects the current font size, color, and opacity.\n\nChanges on the right are applied immediately.",
        "chapter_select": "Chapter Position",
        "current_progress": "Current chapter: ",
        "next_start": "Will start from: ",
        "no_chapters": "No chapters detected. Reading will resume from the last saved position.",
        "delete_confirm_title": "Remove Novel",
        "storage_failed": "Could Not Save Library",
        "delete_confirm_text": "Remove \"{title}\" from the library?\n\nThis will not delete the original TXT file.",
    },
}

TRANSLATIONS["CN"].update({
    "tagline": "把片刻空闲，留给好故事。", "search": "搜索书名…",
    "count": "{count} 本藏书", "empty": "你的下一段故事，从这里开始",
    "empty_hint": "导入本地 TXT，或从网页下载小说。", "no_matches": "没有找到匹配的书籍",
    "choose": "选择一本书，继续阅读", "choose_hint": "阅读进度会自动保存。",
    "chapter_hint": "手动选择章节后，点击开始阅读即可跳转。", "data_folder": "打开数据目录",
})
TRANSLATIONS["EN"].update({
    "tagline": "A little time. A good story.", "search": "Search your library…",
    "count": "{count} books", "empty": "Your next story starts here",
    "empty_hint": "Import a local TXT or download a novel from the web.", "no_matches": "No matching books",
    "choose": "Choose a book to continue", "choose_hint": "Your reading position is saved automatically.",
    "chapter_hint": "Select a chapter, then start reading to jump there.", "data_folder": "Open data folder",
})


class LibraryView(QWidget):
    novel_selected = pyqtSignal(dict, int)
    settings_changed = pyqtSignal()

    def __init__(self, manager, logic):
        super().__init__()
        self.manager = manager
        self.logic = logic
        self.settings = self.manager.get_settings()
        self.current_chapters = []
        self.current_novel_path = None
        self.pending_chapter_pos = None
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(styles.LIBRARY_QSS)

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(28, 24, 28, 18)
        self.root_layout.setSpacing(18)
        header = QHBoxLayout()
        brand = QLabel("MoYu Reader")
        brand.setObjectName("BrandTitle")
        header.addWidget(brand)
        header.addStretch()
        version = QLabel(f"v{APP_VERSION}  /  TXT & WEB")
        version.setObjectName("Badge")
        header.addWidget(version)
        self.root_layout.addLayout(header)
        self.tagline_label = QLabel(self.t("tagline"))
        self.tagline_label.setObjectName("Subtitle")
        self.root_layout.addWidget(self.tagline_label)

        self.main_layout = QHBoxLayout()
        self.main_layout.setSpacing(20)
        self.root_layout.addLayout(self.main_layout, 1)

        self.left_layout = QVBoxLayout()
        self.left_layout.setSpacing(16)
        self.lib_group = QGroupBox(self.t("lib_title"))
        self.lib_layout = QVBoxLayout(self.lib_group)
        self.lib_layout.setSpacing(12)

        library_header = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.t("search"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.filter_library)
        library_header.addWidget(self.search_input, 1)
        self.count_label = QLabel()
        self.count_label.setObjectName("Badge")
        library_header.addWidget(self.count_label)
        self.lib_layout.addLayout(library_header)

        import_row = QHBoxLayout()
        self.btn_add = QPushButton(self.t("add_novel"))
        self.btn_add.clicked.connect(self.on_add_novel)
        import_row.addWidget(self.btn_add)
        self.btn_download = QPushButton(self.t("download_web"))
        self.btn_download.clicked.connect(self.on_download_web)
        import_row.addWidget(self.btn_download)
        self.lib_layout.addLayout(import_row)

        self.novel_list = QListWidget()
        self.novel_list.setSpacing(5)
        self.novel_list.itemDoubleClicked.connect(lambda _item: self.on_read_selected())
        self.lib_layout.addWidget(self.novel_list, 1)

        self.empty_label = QLabel()
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lib_layout.addWidget(self.empty_label, 1)

        self.btn_layout = QHBoxLayout()
        self.btn_layout.setSpacing(10)

        self.btn_delete = QPushButton(self.t("delete_novel"))
        self.btn_delete.setObjectName("DangerButton")
        self.btn_delete.clicked.connect(self.on_delete_selected)
        self.btn_layout.addWidget(self.btn_delete)

        self.btn_read = QPushButton(self.t("start_reading"))
        self.btn_read.setObjectName("PrimaryButton")
        self.btn_read.clicked.connect(self.on_read_selected)
        self.btn_layout.addWidget(self.btn_read)

        self.lib_layout.addLayout(self.btn_layout)
        self.left_layout.addWidget(self.lib_group)
        self.main_layout.addLayout(self.left_layout, 3)

        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setMinimumWidth(310)
        self.right_layout = QVBoxLayout(self.sidebar)
        self.right_layout.setContentsMargins(0, 0, 8, 0)
        self.right_layout.setSpacing(16)

        self.chapter_group = QGroupBox(self.t("chapter_select"))
        self.chapter_layout = QVBoxLayout(self.chapter_group)
        self.chapter_layout.setSpacing(10)
        self.selected_title = QLabel(self.t("choose"))
        self.selected_title.setObjectName("SelectedTitle")
        self.selected_title.setWordWrap(True)
        self.chapter_layout.addWidget(self.selected_title)
        self.chapter_combo = QComboBox()
        self.chapter_combo.setMaxVisibleItems(16)
        self.chapter_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.chapter_combo.setMinimumContentsLength(12)
        self.chapter_combo.currentIndexChanged.connect(self.on_chapter_changed)
        self.chapter_combo.activated.connect(self.on_chapter_changed)
        self.chapter_layout.addWidget(self.chapter_combo)

        self.progress_label = QLabel()
        self.progress_label.setWordWrap(True)
        self.chapter_layout.addWidget(self.progress_label)
        self.chapter_hint = QLabel(self.t("chapter_hint"))
        self.chapter_hint.setObjectName("Muted")
        self.chapter_hint.setWordWrap(True)
        self.chapter_layout.addWidget(self.chapter_hint)
        self.right_layout.addWidget(self.chapter_group)

        self.settings_group = QGroupBox(self.t("settings"))
        self.settings_layout = QVBoxLayout(self.settings_group)
        self.settings_layout.setSpacing(10)

        self.fs_label = QLabel(self.t("font_size"))
        self.settings_layout.addWidget(self.fs_label)
        self.fs_slider = QSlider(Qt.Orientation.Horizontal)
        self.fs_slider.setRange(10, 50)
        self.fs_slider.setValue(self.settings["font_size"])
        self.fs_slider.valueChanged.connect(self.update_settings)
        self.settings_layout.addWidget(self.fs_slider)

        self.to_label = QLabel(self.t("text_opacity"))
        self.settings_layout.addWidget(self.to_label)
        self.to_slider = QSlider(Qt.Orientation.Horizontal)
        self.to_slider.setRange(10, 100)
        self.to_slider.setValue(int(self.settings["text_opacity"] * 100))
        self.to_slider.valueChanged.connect(self.update_settings)
        self.settings_layout.addWidget(self.to_slider)

        self.btn_color = QPushButton(self.t("change_color"))
        self.btn_color.clicked.connect(self.on_change_color)
        self.settings_layout.addWidget(self.btn_color)

        self.rm_check = QCheckBox(self.t("stealth_mode"))
        self.rm_check.setChecked(self.settings.get("reading_mode", False))
        self.rm_check.stateChanged.connect(self.update_settings)
        self.settings_layout.addWidget(self.rm_check)

        self.btn_lang = QPushButton(self.t("lang_toggle"))
        self.btn_lang.clicked.connect(self.toggle_language)
        self.settings_layout.addWidget(self.btn_lang)

        self.right_layout.addWidget(self.settings_group)

        self.preview_group = QGroupBox(self.t("preview_title"))
        self.preview_layout = QVBoxLayout(self.preview_group)
        self.preview_box = QTextEdit()
        self.preview_box.setMinimumHeight(150)
        self.preview_box.setMaximumHeight(200)
        self.preview_box.setReadOnly(True)
        self.preview_box.setPlainText(self.t("preview_text"))
        self.preview_layout.addWidget(self.preview_box)
        self.right_layout.addWidget(self.preview_group)

        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setObjectName("SidebarScroll")
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_scroll.setWidget(self.sidebar)
        self.sidebar_scroll.setMinimumWidth(338)
        self.main_layout.addWidget(self.sidebar_scroll, 2)

        footer = QHBoxLayout()
        self.footer_hint = QLabel(self.t("choose_hint"))
        self.footer_hint.setObjectName("Muted")
        footer.addWidget(self.footer_hint)
        footer.addStretch()
        self.btn_data = QPushButton(self.t("data_folder"))
        self.btn_data.setObjectName("QuietButton")
        self.btn_data.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_directory()))))
        footer.addWidget(self.btn_data)
        self.root_layout.addLayout(footer)

        self.refresh_library()
        self.apply_preview_settings()
        self.update_selection_state()
        self.update_progress_label()

    def t(self, key):
        lang = self.settings.get("language", "CN")
        return TRANSLATIONS[lang].get(key, key)

    def toggle_language(self):
        new_lang = "EN" if self.settings.get("language", "CN") == "CN" else "CN"
        self.settings["language"] = new_lang
        if not self._save_settings():
            return
        self.retranslate_ui()
        self.settings_changed.emit()

    def retranslate_ui(self):
        self.lib_group.setTitle(self.t("lib_title"))
        self.btn_add.setText(self.t("add_novel"))
        self.btn_delete.setText(self.t("delete_novel"))
        self.btn_download.setText(self.t("download_web"))
        self.btn_read.setText(self.t("start_reading"))
        self.chapter_group.setTitle(self.t("chapter_select"))
        self.settings_group.setTitle(self.t("settings"))
        self.fs_label.setText(f"{self.t('font_size')} · {self.fs_slider.value()} pt")
        self.to_label.setText(f"{self.t('text_opacity')} · {self.to_slider.value()}%")
        self.btn_color.setText(self.t("change_color"))
        self.rm_check.setText(self.t("stealth_mode"))
        self.btn_lang.setText(self.t("lang_toggle"))
        self.preview_group.setTitle(self.t("preview_title"))
        self.preview_box.setPlainText(self.t("preview_text"))
        self.tagline_label.setText(self.t("tagline"))
        self.search_input.setPlaceholderText(self.t("search"))
        self.chapter_hint.setText(self.t("chapter_hint"))
        self.footer_hint.setText(self.t("choose_hint"))
        self.btn_data.setText(self.t("data_folder"))
        self.filter_library()
        self.update_selection_state()
        self.update_progress_label()

    def refresh_library(self):
        self.novel_list.clear()
        try:
            self.novel_list.itemSelectionChanged.disconnect(self.on_novel_selection_changed)
        except Exception:
            pass

        for item in self.manager.data["library"]:
            self.novel_list.addItem(item["title"])
            self.novel_list.item(self.novel_list.count() - 1).setData(Qt.ItemDataRole.UserRole, item["path"])
            self.novel_list.item(self.novel_list.count() - 1).setToolTip(item["path"])
            self.novel_list.item(self.novel_list.count() - 1).setIcon(QIcon(str(resource_path("assets/moyu.ico"))))

        self.novel_list.itemSelectionChanged.connect(self.on_novel_selection_changed)
        self.filter_library()
        self.update_selection_state()

    def filter_library(self, *_):
        query = self.search_input.text().strip().casefold()
        visible = 0
        for index in range(self.novel_list.count()):
            item = self.novel_list.item(index)
            hidden = query not in item.text().casefold()
            item.setHidden(hidden)
            visible += int(not hidden)
        # 隐藏的选中项不能继续触发“开始阅读”，避免搜索后误开另一本书。
        if any(item.isHidden() for item in self.novel_list.selectedItems()):
            self.novel_list.clearSelection()
        self.count_label.setText(self.t("count").format(count=self.novel_list.count()))
        self.novel_list.setVisible(visible > 0)
        self.empty_label.setVisible(visible == 0)
        self.empty_label.setText(self.t("no_matches") if query else self.t("empty") + "\n\n" + self.t("empty_hint"))

    def update_selection_state(self):
        novel = self.get_selected_novel()
        self.btn_read.setEnabled(novel is not None)
        self.btn_delete.setEnabled(novel is not None)
        self.chapter_combo.setEnabled(bool(novel and self.current_chapters))
        self.selected_title.setText(novel["title"] if novel else self.t("choose"))

    def current_chapter_index_for_pos(self, pos):
        if not self.current_chapters:
            return -1

        current_idx = 0
        for i, chapter in enumerate(self.current_chapters):
            if chapter["pos"] <= pos:
                current_idx = i
            else:
                break
        return current_idx

    def update_progress_label(self, pos=None):
        if pos is None:
            novel = self.get_selected_novel()
            pos = novel.get("last_pos", 0) if novel else 0

        if not self.current_chapters:
            self.progress_label.setText(self.t("no_chapters"))
            return

        if self.pending_chapter_pos is not None and self.chapter_combo.currentIndex() >= 0:
            chapter_title = self.chapter_combo.currentText().strip()
            self.progress_label.setText(f"{self.t('next_start')}{chapter_title}")
            return

        index = self.current_chapter_index_for_pos(pos)
        chapter_title = self.current_chapters[index]["title"].strip()
        self.progress_label.setText(f"{self.t('current_progress')}{chapter_title}")

    def sync_combo_to_progress(self, pos):
        index = self.current_chapter_index_for_pos(pos)
        if index < 0:
            self.update_progress_label(pos)
            return

        self.chapter_combo.blockSignals(True)
        self.chapter_combo.setCurrentIndex(index)
        self.chapter_combo.blockSignals(False)
        self.update_progress_label(pos)

    def get_selected_novel(self):
        selected = self.novel_list.selectedItems()
        if not selected or selected[0].isHidden():
            return None

        path = selected[0].data(Qt.ItemDataRole.UserRole)
        for novel in self.manager.data["library"]:
            if novel["path"] == path:
                return novel
        return None

    def select_novel_by_title(self, title: str):
        for index in range(self.novel_list.count()):
            item = self.novel_list.item(index)
            if item.text() == title:
                if item.isHidden():
                    self.search_input.clear()
                self.novel_list.setCurrentItem(item)
                self.on_novel_selection_changed()
                break

    def select_novel_by_path(self, path: str):
        for index in range(self.novel_list.count()):
            item = self.novel_list.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                if item.isHidden():
                    self.search_input.clear()
                self.novel_list.setCurrentItem(item)
                self.on_novel_selection_changed()
                break

    def on_novel_selection_changed(self):
        novel = self.get_selected_novel()
        if not novel:
            self.current_novel_path = None
            self.current_chapters = []
            self.pending_chapter_pos = None
            self.chapter_combo.clear()
            self.update_progress_label(0)
            self.update_selection_state()
            return

        self.current_novel_path = novel["path"]
        self.current_chapters = self.logic.get_chapters(novel["path"])
        self.pending_chapter_pos = None

        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        for chapter in self.current_chapters:
            self.chapter_combo.addItem(chapter["title"], chapter["pos"])
        self.chapter_combo.blockSignals(False)

        self.sync_combo_to_progress(novel.get("last_pos", 0))
        self.update_selection_state()

    def on_chapter_changed(self, index):
        if index >= 0 and self.current_chapters:
            chapter_pos = self.chapter_combo.itemData(index)
            self.pending_chapter_pos = int(chapter_pos) if chapter_pos is not None else None
            self.update_progress_label()

    def sync_progress(self, path, pos):
        for novel in self.manager.data["library"]:
            if novel["path"] == path:
                novel["last_pos"] = pos
                break

        if path != self.current_novel_path:
            return

        # 阅读器的延迟进度信号不能覆盖用户尚未执行的章节选择。
        if self.pending_chapter_pos is not None:
            self.update_progress_label()
            return

        self.sync_combo_to_progress(pos)

    def on_add_novel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open TXT", "", "TXT Files (*.txt)")
        if path:
            title = os.path.splitext(os.path.basename(path))[0]
            try:
                novel = self.manager.add_novel(title, path)
            except (OSError, ValueError) as exc:
                self._show_storage_error(exc)
                return
            self.refresh_library()
            self.select_novel_by_path(novel["path"])

    def on_download_web(self):
        dialog = WebDownloadDialog(self.settings.get("language", "CN"), self)
        if dialog.exec() and dialog.result_data:
            title = dialog.result_data["title"]
            file_path = dialog.result_data["file_path"]
            try:
                novel = self.manager.add_novel(title, file_path)
            except (OSError, ValueError) as exc:
                self._show_storage_error(exc)
                return
            self.refresh_library()
            self.select_novel_by_path(novel["path"])

    def on_delete_selected(self):
        novel = self.get_selected_novel()
        if not novel:
            return

        answer = QMessageBox.question(
            self,
            self.t("delete_confirm_title"),
            self.t("delete_confirm_text").format(title=novel["title"]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        current_row = self.novel_list.currentRow()
        try:
            self.manager.remove_novel(novel["path"])
        except (OSError, ValueError) as exc:
            self._show_storage_error(exc)
            return
        self.current_novel_path = None
        self.current_chapters = []
        self.pending_chapter_pos = None
        self.refresh_library()

        if self.novel_list.count() > 0:
            next_row = min(current_row, self.novel_list.count() - 1)
            self.novel_list.setCurrentRow(max(0, next_row))
        else:
            self.chapter_combo.clear()
            self.update_progress_label(0)

    def on_read_selected(self):
        novel = self.get_selected_novel()
        if not novel:
            return

        start_pos = novel.get("last_pos", 0)
        if self.pending_chapter_pos is not None:
            start_pos = self.pending_chapter_pos

        payload = novel.copy()
        # 手动选章即使恰好等于旧游标，也不能恢复与它不一致的旧滚动比例。
        payload["_restore_saved_scroll"] = self.pending_chapter_pos is None
        self.novel_selected.emit(payload, start_pos)
        self.pending_chapter_pos = None

    def on_change_color(self):
        color = QColorDialog.getColor(QColor(self.settings["font_color"]), self)
        if color.isValid():
            self.settings["font_color"] = color.name()
            self.update_settings()

    def update_settings(self):
        self.settings["font_size"] = self.fs_slider.value()
        self.settings["text_opacity"] = self.to_slider.value() / 100.0
        self.settings["reading_mode"] = self.rm_check.isChecked()
        if not self._save_settings():
            controls = (self.fs_slider, self.to_slider, self.rm_check)
            blocked = [control.blockSignals(True) for control in controls]
            try:
                self.fs_slider.setValue(self.settings["font_size"])
                self.to_slider.setValue(round(self.settings["text_opacity"] * 100))
                self.rm_check.setChecked(self.settings["reading_mode"])
            finally:
                for control, previous in zip(controls, blocked):
                    control.blockSignals(previous)
        self.apply_preview_settings()
        self.settings_changed.emit()

    def _show_storage_error(self, error):
        QMessageBox.warning(self, self.t("storage_failed"), str(error))

    def _save_settings(self):
        try:
            self.manager.update_settings(self.settings)
            return True
        except (OSError, ValueError) as exc:
            self._show_storage_error(exc)
            return False

    def apply_preview_settings(self):
        s = self.settings
        font = QFont()
        font.setPointSize(s["font_size"])
        self.preview_box.setFont(font)

        color = QColor(s["font_color"])
        r, g, b = color.red(), color.green(), color.blue()
        a = s["text_opacity"]
        self.fs_label.setText(f"{self.t('font_size')} · {s['font_size']} pt")
        self.to_label.setText(f"{self.t('text_opacity')} · {round(a * 100)}%")

        self.preview_box.setStyleSheet(f"""
            QTextEdit {{
                color: rgba({r}, {g}, {b}, {a});
                background-color: #0f1716;
                border: 1px solid #30463f;
                border-radius: 14px;
                padding: 14px;
                font-size: {s['font_size']}pt;
            }}
        """)
