from PyQt6.QtCore import QPoint, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QCursor, QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QPushButton,
    QSizeGrip,
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
    save_failed = pyqtSignal(str)

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
        self._restore_generation = 0
        self._restore_target = None
        self._restore_saved_scroll = True
        self._loaded_file_signature = None
        self.last_load_error = ""
        self._last_save_error = None

        self.setWindowTitle("MoYu Reader")
        self.setMinimumSize(520, 360)
        self.resize(640, 740)
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
        self.btn_close.setObjectName("CloseButton")
        self.btn_close.setStyleSheet("padding: 0; font-size: 16px;")
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

        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setToolTip("拖动调整窗口大小 / Resize")
        self.layout.addWidget(self.resize_grip, 0, Qt.AlignmentFlag.AlignRight)
        self.btn_close.setToolTip("隐藏阅读窗口 / Hide reader")
        self.header_frame.setToolTip("拖动顶部区域移动窗口 / Drag to move")

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
            self.resize_grip.hide()
            self.reader_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.central_widget.setStyleSheet(
                "QWidget#CentralWidget { background-color: rgba(0, 0, 0, 0.01); border: none; }"
            )
        else:
            self.header_frame.show()
            self.resize_grip.show()
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
        if not self.current_novel or self._restoring_progress:
            return None

        state = self.current_progress_state()
        if state is None:
            return None

        path = self.current_novel["path"]
        pos = state["pos"]
        scroll_ratio = state["last_scroll_ratio"]
        signature = (path, pos, round(scroll_ratio, 5))

        saved = False
        if force or signature != self._last_saved_signature:
            try:
                saved = self.manager.update_progress(path, pos, state["scroll_value"], state["scroll_max"])
            except (OSError, ValueError) as exc:
                self._report_save_error(exc)
                return None
            self._last_saved_signature = signature
            self._last_save_error = None

        self.current_novel["last_pos"] = pos
        self.current_novel["last_scroll_ratio"] = scroll_ratio

        if force or saved:
            self.progress_changed.emit(path, pos)

        return dict(self.current_novel)

    def _report_save_error(self, error):
        message = f"保存阅读状态失败：{error}"
        if message != self._last_save_error:
            self._last_save_error = message
            self.save_failed.emit(message)

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
        if not use_saved_scroll:
            # 手动选章时把标题移到视口顶部，不能只保证它在当前页面内可见。
            top = self.reader_area.cursorRect().top()
            margin = int(self.reader_area.document().documentMargin())
            scroll_bar.setValue(scroll_bar.value() + top - margin)

    def toggle_stealth_mode(self):
        state = self.persist_progress(force=True) or self._restore_target
        use_saved_scroll = self._restore_saved_scroll if self._restoring_progress else True
        self.settings["reading_mode"] = not self.settings["reading_mode"]
        if not self._save_reader_settings():
            return
        self.apply_settings()
        if state:
            self._begin_progress_restore(state, use_saved_scroll)

    def change_font_size(self, delta):
        state = self.persist_progress(force=True) or self._restore_target
        use_saved_scroll = self._restore_saved_scroll if self._restoring_progress else True
        self.settings["font_size"] = max(10, min(50, self.settings["font_size"] + delta))
        if not self._save_reader_settings():
            return
        self.apply_settings()
        if state:
            self._begin_progress_restore(state, use_saved_scroll)

    def _save_reader_settings(self):
        try:
            self.manager.update_settings(self.settings)
            self._last_save_error = None
            return True
        except (OSError, ValueError) as exc:
            self._report_save_error(exc)
            return False

    def load_novel(self, novel_data):
        self.last_load_error = ""
        try:
            signature = self.logic.file_signature(novel_data["path"])
        except (OSError, AttributeError):
            signature = None
        reuse_document = (
            signature is not None and signature == self._loaded_file_signature
            and self.current_novel and self.current_novel["path"] == novel_data["path"]
        )
        if not reuse_document:
            content, chapters = self.logic.load_txt(novel_data["path"])
            if not content:
                # 读取失败不能清空正在阅读的文档，更不能把原书进度覆盖为零。
                self.last_load_error = getattr(self.logic, "last_error", "") or "文件为空或无法读取。"
                return False
        self.persist_progress(force=True)
        self.progress_save_timer.stop()
        self._restoring_progress = True
        self.current_novel = novel_data.copy()
        self._hidden_progress_state = None
        self._last_saved_signature = None
        restore_saved_scroll = self.current_novel.pop("_restore_saved_scroll", True)

        if not reuse_document:
            self.chapters = chapters
            self.reader_area.setPlainText(content)
            self._loaded_file_signature = signature
            self.toc_menu.clear()
            for idx, chapter in enumerate(chapters):
                # 菜单持有动作，clear 时一并销毁，反复切书不会累积旧动作。
                action = QAction(chapter["title"], self.toc_menu)
                action.triggered.connect(lambda checked=False, i=idx: self.jump_to_chapter(i))
                self.toc_menu.addAction(action)

        self._begin_progress_restore(self.current_novel, restore_saved_scroll)
        return True

    def _begin_progress_restore(self, state, use_saved_scroll):
        self.progress_save_timer.stop()
        self._restoring_progress = True
        self._restore_generation += 1
        generation = self._restore_generation
        # 使用位置快照，悬停、隐藏和旧计时器都不能把布局中的临时位置当成目标。
        self._restore_target = dict(state)
        self._restore_saved_scroll = use_saved_scroll
        self.restore_progress(use_saved_scroll, self._restore_target)
        self._queue_progress_restore(generation)

    def _queue_progress_restore(self, generation):
        QTimer.singleShot(
            0,
            lambda: self._finish_initial_restore(generation, False),
        )
        QTimer.singleShot(
            120,
            lambda: self._finish_initial_restore(generation, True),
        )

    def _finish_initial_restore(self, generation, persist):
        if generation != self._restore_generation or not self._restore_target:
            return

        # 长篇文档会延迟计算高度，先完成布局，再等待滚动范围同步。
        document_height = self.reader_area.document().documentLayout().documentSize().height()
        self.restore_progress(self._restore_saved_scroll, self._restore_target)
        if persist and self.isVisible():
            expected_maximum = max(0, int(document_height) - self.reader_area.viewport().height())
            if self.reader_area.verticalScrollBar().maximum() + 2 < expected_maximum:
                QTimer.singleShot(0, lambda: self._finish_initial_restore(generation, True))
                return
            self._restoring_progress = False
            self._restore_target = None
            self.persist_progress(force=True)

    def jump_to_chapter(self, index):
        if 0 <= index < len(self.chapters):
            pos = self.chapters[index]["pos"]
            self._begin_progress_restore({"last_pos": pos}, False)

    def showEvent(self, event):
        super().showEvent(event)
        # 隐藏窗口加载后可能很晚才显示，真正显示时再完成布局和位置恢复。
        if self._restore_target:
            self._queue_progress_restore(self._restore_generation)

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
