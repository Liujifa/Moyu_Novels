from PyQt6.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import styles


TRANSLATIONS = {
    "CN": {
        "toc": "\u76ee\u5f55",
        "font_plus": "A+",
        "font_minus": "A-",
        "mode_stealth": "\u9605\u8bfb\u6a21\u5f0f",
        "mode_normal": "\u666e\u901a\u6a21\u5f0f",
        "close": "X",
    },
    "EN": {
        "toc": "TOC",
        "font_plus": "A+",
        "font_minus": "A-",
        "mode_stealth": "Reading",
        "mode_normal": "Normal",
        "close": "X",
    },
}


class CustomReader(QTextEdit):
    pass


class ReaderWindow(QMainWindow):
    progress_changed = pyqtSignal(str, int)

    def __init__(self, manager, logic):
        super().__init__()
        self.manager = manager
        self.logic = logic
        self.settings = self.manager.get_settings()
        self.chapters = []
        self.current_novel = None
        self._hidden_progress_state = None
        self._last_saved_signature = None
        self._restoring_progress = False

        self.setWindowTitle("MoYu Reader")
        self.setMinimumSize(420, 620)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self.init_ui()
        self.apply_settings()

        self._dragging = False
        self._drag_pos = QPoint()

        self.hover_timer = QTimer(self)
        self.hover_timer.timeout.connect(self.check_hover_state)
        self.hover_timer.start(120)
        self._is_hovering = True

        self.progress_save_timer = QTimer(self)
        self.progress_save_timer.setSingleShot(True)
        self.progress_save_timer.timeout.connect(self.persist_progress)

    def init_ui(self):
        self.central_widget = QWidget()
        self.central_widget.setObjectName("CentralWidget")
        self.central_widget.setMouseTracking(True)
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.header_frame = QFrame()
        self.header_frame.setObjectName("Header")
        self.header_frame.setMouseTracking(True)
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(12, 8, 12, 8)

        self.btn_toc = QPushButton()
        self.btn_toc.setObjectName("TOCButton")
        self.toc_menu = QMenu(self)
        self.btn_toc.setMenu(self.toc_menu)
        self.header_layout.addWidget(self.btn_toc)

        self.btn_font_plus = QPushButton()
        self.btn_font_plus.clicked.connect(lambda: self.change_font_size(1))
        self.header_layout.addWidget(self.btn_font_plus)

        self.btn_font_minus = QPushButton()
        self.btn_font_minus.clicked.connect(lambda: self.change_font_size(-1))
        self.header_layout.addWidget(self.btn_font_minus)

        self.header_layout.addStretch()

        self.btn_mode = QPushButton()
        self.btn_mode.clicked.connect(self.toggle_stealth_mode)
        self.header_layout.addWidget(self.btn_mode)

        self.btn_close = QPushButton()
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.clicked.connect(self.hide)
        self.header_layout.addWidget(self.btn_close)

        self.layout.addWidget(self.header_frame)

        self.reader_area = CustomReader()
        self.reader_area.setObjectName("ReaderArea")
        self.reader_area.setReadOnly(True)
        self.reader_area.setMouseTracking(True)
        self.reader_area.setFrameStyle(0)
        self.reader_area.verticalScrollBar().valueChanged.connect(self.schedule_progress_save)
        self.opacity_effect = QGraphicsOpacityEffect(self.reader_area)
        self.reader_area.setGraphicsEffect(self.opacity_effect)
        self.layout.addWidget(self.reader_area)

        self.setStyleSheet(styles.READER_QSS)
        self.retranslate_ui()

    def t(self, key):
        lang = self.settings.get("language", "CN")
        return TRANSLATIONS[lang].get(key, key)

    def retranslate_ui(self):
        self.btn_toc.setText(self.t("toc"))
        self.btn_font_plus.setText(self.t("font_plus"))
        self.btn_font_minus.setText(self.t("font_minus"))
        self.btn_close.setText(self.t("close"))
        if self.settings.get("reading_mode"):
            self.btn_mode.setText(self.t("mode_stealth"))
        else:
            self.btn_mode.setText(self.t("mode_normal"))

    def apply_settings(self):
        self.retranslate_ui()
        self.setStyleSheet(styles.READER_QSS)

        font = QFont()
        font.setPointSize(self.settings["font_size"])
        self.reader_area.setFont(font)

        if self.settings.get("reading_mode"):
            self.header_frame.hide()
            self.reader_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.central_widget.setStyleSheet(
                "QWidget#CentralWidget { background-color: rgba(0, 0, 0, 0.01); border: none; }"
            )
        else:
            self.header_frame.show()
            self.reader_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self.central_widget.setStyleSheet("")

        color = QColor(self.settings["font_color"])
        r, g, b = color.red(), color.green(), color.blue()
        self.reader_area.setStyleSheet(
            f"#ReaderArea {{ color: rgb({r}, {g}, {b}); background-color: transparent; border: none; }}"
        )

        self.update_text_visibility(True)

    def update_text_visibility(self, visible):
        if self.settings.get("reading_mode"):
            opacity = 0.0 if not visible else self.settings.get("text_opacity", 1.0)
        else:
            opacity = self.settings.get("text_opacity", 1.0)

        self.setWindowOpacity(1.0)
        self.opacity_effect.setOpacity(opacity)

    def schedule_progress_save(self, *_):
        if self.current_novel and not self._restoring_progress:
            self.progress_save_timer.start(450)

    def current_view_position(self):
        document = self.reader_area.document()
        if document.isEmpty():
            return 0

        viewport = self.reader_area.viewport()
        probe_y = min(max(18, viewport.height() // 5), max(18, viewport.height() - 18))
        cursor = self.reader_area.cursorForPosition(QPoint(18, probe_y))
        return cursor.position()

    def current_progress_state(self):
        if not self.current_novel:
            return None

        scroll_bar = self.reader_area.verticalScrollBar()
        scroll_value = scroll_bar.value()
        scroll_max = scroll_bar.maximum()
        scroll_ratio = (scroll_value / scroll_max) if scroll_max else 0.0
        pos = self.current_view_position()

        return {
            "pos": pos,
            "last_pos": pos,
            "last_scroll_ratio": scroll_ratio,
            "scroll_value": scroll_value,
            "scroll_max": scroll_max,
        }

    def set_cursor_position(self, pos):
        document_length = max(0, self.reader_area.document().characterCount() - 1)
        pos = max(0, min(int(pos), document_length))
        cursor = self.reader_area.textCursor()
        cursor.setPosition(pos)
        self.reader_area.setTextCursor(cursor)
        return pos

    def persist_progress(self, force=False):
        if not self.current_novel:
            return None

        state = self.current_progress_state()
        if state is None:
            return None

        path = self.current_novel["path"]
        pos = state["pos"]
        scroll_ratio = state["last_scroll_ratio"]
        signature = (path, pos, round(scroll_ratio, 5))

        self.current_novel["last_pos"] = pos
        self.current_novel["last_scroll_ratio"] = scroll_ratio

        saved = False
        if force or signature != self._last_saved_signature:
            saved = self.manager.update_progress(path, pos, state["scroll_value"], state["scroll_max"])
            self._last_saved_signature = signature

        if force or saved:
            self.progress_changed.emit(path, pos)

        return dict(self.current_novel)

    def restore_progress(self, use_saved_scroll=True, state=None):
        if not self.current_novel:
            return

        target = state or self.current_novel
        self.set_cursor_position(target.get("last_pos", 0))

        scroll_bar = self.reader_area.verticalScrollBar()
        if use_saved_scroll:
            scroll_ratio = target.get("last_scroll_ratio")
            if scroll_ratio is not None and scroll_bar.maximum() > 0:
                scroll_value = round(scroll_ratio * scroll_bar.maximum())
                scroll_bar.setValue(max(0, min(scroll_value, scroll_bar.maximum())))
                return

        self.reader_area.ensureCursorVisible()

    def toggle_stealth_mode(self):
        self.persist_progress(force=True)
        self.settings["reading_mode"] = not self.settings["reading_mode"]
        self.manager.update_settings(self.settings)
        self.apply_settings()
        QTimer.singleShot(0, lambda: self.restore_progress(True))

    def change_font_size(self, delta):
        self.persist_progress(force=True)
        self.settings["font_size"] = max(10, min(50, self.settings["font_size"] + delta))
        self.manager.update_settings(self.settings)
        self.apply_settings()
        QTimer.singleShot(0, lambda: self.restore_progress(True))

    def load_novel(self, novel_data):
        self.progress_save_timer.stop()
        self._restoring_progress = True
        self.current_novel = novel_data
        self._hidden_progress_state = None
        self._last_saved_signature = None
        restore_saved_scroll = novel_data.pop("_restore_saved_scroll", True)
        expected_path = novel_data["path"]

        content, chapters = self.logic.load_txt(novel_data["path"])
        self.chapters = chapters
        self.reader_area.setPlainText(content)

        self.toc_menu.clear()
        for idx, chapter in enumerate(chapters):
            action = QAction(chapter["title"], self)
            action.triggered.connect(lambda checked=False, i=idx: self.jump_to_chapter(i))
            self.toc_menu.addAction(action)

        self.restore_progress(restore_saved_scroll, self.current_novel)
        QTimer.singleShot(
            0,
            lambda: self._finish_initial_restore(expected_path, restore_saved_scroll, False),
        )
        QTimer.singleShot(
            120,
            lambda: self._finish_initial_restore(expected_path, restore_saved_scroll, True),
        )

    def _finish_initial_restore(self, expected_path, use_saved_scroll, persist):
        if not self.current_novel or self.current_novel.get("path") != expected_path:
            return

        self.restore_progress(use_saved_scroll, self.current_novel)
        if persist:
            self._restoring_progress = False
            self.persist_progress(force=True)

    def jump_to_chapter(self, index):
        if 0 <= index < len(self.chapters):
            pos = self.chapters[index]["pos"]
            self.set_cursor_position(pos)
            self.reader_area.ensureCursorVisible()
            self.persist_progress(force=True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def check_hover_state(self):
        if not self.settings.get("reading_mode"):
            return

        cursor_pos = self.mapFromGlobal(QCursor.pos())
        is_hovering = self.rect().contains(cursor_pos)
        if is_hovering == self._is_hovering:
            return

        self._is_hovering = is_hovering
        
        if not is_hovering:
            self.persist_progress(force=True)

        self.update_text_visibility(is_hovering)

    def hideEvent(self, event):
        self.persist_progress(force=True)
        super().hideEvent(event)
