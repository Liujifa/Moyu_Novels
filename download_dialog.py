from __future__ import annotations

import os

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import styles
from web_novel_downloader import DownloadResult, WebDownloadError, WebNovelDownloader
from novel_page_parser import EXTRACTION_RULE_FIELDS


TRANSLATIONS = {
    "CN": {
        "title": "\u7f51\u9875\u4e0b\u8f7d TXT",
        "url": "小说网页 / TXT 地址",
        "name": "\u4e66\u540d\uff08\u53ef\u9009\uff09",
        "browser": "\u5bfc\u5165\u6d4f\u89c8\u5668 Cookie",
        "none": "\u4e0d\u5bfc\u5165",
        "import_file": "\u4ece\u6587\u4ef6\u5bfc\u5165 (.txt / .json)",
        "how_to_export": "\u5982\u4f55\u5bfc\u51fa?",
        "download": "\u4e0b\u8f7d\u5e76\u5165\u5e93",
        "close": "\u5173\u95ed",
        "status_idle": "\u7b49\u5f85\u5f00\u59cb",
        "logs": "下载日志",
        "cancel": "取消下载",
        "rules": "高级解析规则（可选）",
        "rules_hint": "留空自动识别。自动解析不准确时，可填写 CSS 选择器指定页面区域；仅用于本次下载。",
        "hint": "输入小说页面或 TXT 地址，自动识别目录和正文。识别不准确时可展开高级解析规则。遇到 403 时，请先在浏览器确认页面可访问，再导入对应站点 Cookie。",
        "missing_url": "请先输入 URL。",
        "success": "下载完成，共 {count} 章，已准备入库。",
        "failed": "\u4e0b\u8f7d\u5931\u8d25",
        "progress_web": "\u6b63\u5728\u4e0b\u8f7d\u7f51\u9875\u7ae0\u8282",
        "progress_fanqie": "\u6b63\u5728\u4e0b\u8f7d\u756a\u8304\u7ae0\u8282",
        "progress_format": "{label} ({current}/{total})",
    },
    "EN": {
        "title": "Download TXT From Web",
        "url": "Novel Page / TXT URL",
        "name": "Book Title (Optional)",
        "browser": "Import Browser Cookie",
        "none": "Do Not Import",
        "import_file": "Import from file (.txt / .json)",
        "how_to_export": "How to Export?",
        "download": "Download And Import",
        "close": "Close",
        "status_idle": "Waiting to start",
        "logs": "Download Log",
        "cancel": "Cancel",
        "rules": "Advanced Extraction Rules (Optional)",
        "rules_hint": "Leave blank for automatic detection. CSS selectors can specify page regions when needed; rules apply to this download only.",
        "hint": "Enter a novel page or TXT URL for automatic extraction. Advanced rules can specify page regions when needed. For a 403 response, confirm browser access and import the site's cookies.",
        "missing_url": "Please enter a URL first.",
        "success": "Downloaded {count} chapters and ready to import into the library.",
        "failed": "Download Failed",
        "progress_web": "Downloading web chapters",
        "progress_fanqie": "Downloading Fanqie chapters",
        "progress_format": "{label} ({current}/{total})",
    },
}


class DownloadWorker(QObject):
    progress = pyqtSignal(int, int, str, str)
    log = pyqtSignal(str)
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, url: str, title: str, browser: str, download_dir: str, language: str = "CN", extraction_rules=None):
        super().__init__()
        self.url = url
        self.title = title
        self.browser = browser
        self.download_dir = download_dir
        self.language = language
        self.extraction_rules = dict(extraction_rules or {})
        self.downloader = None
        self._abort_requested = False

    def run(self):
        try:
            self.downloader = WebNovelDownloader(
                download_dir=self.download_dir,
                progress_callback=self.progress.emit,
                log_callback=self.log.emit,
                language=self.language,
                extraction_rules=self.extraction_rules,
            )
            self.downloader.is_cancelled = self._abort_requested
            result = self.downloader.download(self.url, self.title, self.browser)
            payload = {
                "title": result.title,
                "file_path": result.file_path,
                "chapter_count": result.chapter_count,
                "source_url": result.source_url,
            }
            self.finished.emit(payload)
        except WebDownloadError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))

    def abort(self):
        self._abort_requested = True
        if self.downloader:
            self.downloader.is_cancelled = True

class WebDownloadDialog(QDialog):
    def __init__(self, language: str = "CN", parent=None):
        super().__init__(parent)
        self.language = language if language in TRANSLATIONS else "CN"
        self.result_data: dict | None = None
        self.thread: QThread | None = None
        self.worker: DownloadWorker | None = None
        self._cancel_requested = False
        self._pending_result = None
        self._pending_error = None
        self.download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "novel_downloads")
        self.init_ui()

    def t(self, key: str) -> str:
        return TRANSLATIONS[self.language].get(key, key)

    def init_ui(self):
        self.setWindowTitle(self.t("title"))
        self.setMinimumWidth(620)
        self.setStyleSheet(styles.LIBRARY_QSS)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel(self.t("hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)

        self.url_input = QLineEdit()
        self.title_input = QLineEdit()
        self.browser_combo = QComboBox()
        self.browser_combo.addItem(self.t("none"), "none")
        self.browser_combo.addItem("Edge", "edge")
        self.browser_combo.addItem("Chrome", "chrome")
        self.browser_combo.addItem("Firefox", "firefox")
        self.browser_combo.addItem(self.t("import_file"), "file")

        form.addRow(self.t("url"), self.url_input)
        form.addRow(self.t("name"), self.title_input)
        form.addRow(self.t("browser"), self.browser_combo)
        layout.addLayout(form)

        self.rules_group = QGroupBox(self.t("rules"))
        self.rules_group.setCheckable(True)
        self.rules_group.setChecked(False)
        rules_layout = QVBoxLayout(self.rules_group)
        self.rules_body = QWidget()
        rules_form = QFormLayout(self.rules_body)
        rules_hint = QLabel(self.t("rules_hint"))
        rules_hint.setWordWrap(True)
        rules_form.addRow(rules_hint)
        self.rule_inputs = {}
        for key, chinese_label, english_label, example in EXTRACTION_RULE_FIELDS:
            field = QLineEdit()
            field.setPlaceholderText(example)
            self.rule_inputs[key] = field
            rules_form.addRow(chinese_label if self.language == "CN" else english_label, field)
        rules_layout.addWidget(self.rules_body)
        self.rules_group.toggled.connect(self.rules_body.setVisible)
        self.rules_body.hide()
        layout.addWidget(self.rules_group)

        help_row = QHBoxLayout()
        self.help_btn = QPushButton(self.t("how_to_export"))
        self.help_btn.setFlat(True)
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.setStyleSheet("color: #4CAF50; text-decoration: underline; text-align: left; font-size: 11px;")
        self.help_btn.clicked.connect(self.show_export_help)
        help_row.addWidget(self.help_btn)
        help_row.addStretch()
        layout.addLayout(help_row)

        self.status_label = QLabel(self.t("status_idle"))
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumBlockCount(1000)
        self.log_box.setPlaceholderText(self.t("logs"))
        layout.addWidget(self.log_box)

        button_row = QHBoxLayout()
        self.btn_download = QPushButton(self.t("download"))
        self.btn_download.clicked.connect(self.start_download)
        button_row.addWidget(self.btn_download)

        self.btn_close = QPushButton(self.t("close"))
        self.btn_close.clicked.connect(self.reject)
        button_row.addWidget(self.btn_close)
        layout.addLayout(button_row)

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, self.t("title"), self.t("missing_url"))
            return

        self.result_data = None
        self._cancel_requested = False
        self._pending_result = None
        self._pending_error = None
        self.log_box.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText(self.t("status_idle"))
        self.btn_download.setEnabled(False)
        self.btn_close.setText(self.t("cancel"))
        self.url_input.setEnabled(False)
        self.title_input.setEnabled(False)
        self.browser_combo.setEnabled(False)
        self.rules_group.setEnabled(False)

        browser = self.browser_combo.currentData()
        if browser == "file":
            from PyQt6.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                self, self.t("import_file"), "", "Cookie Files (*.txt *.json);;All Files (*)"
            )
            if not file_path:
                self.btn_download.setEnabled(True)
                self.btn_close.setText(self.t("close"))
                self.url_input.setEnabled(True)
                self.title_input.setEnabled(True)
                self.browser_combo.setEnabled(True)
                self.rules_group.setEnabled(True)
                return
            browser = file_path # Pass the path as the "browser" param

        self.thread = QThread(self)
        self.worker = DownloadWorker(
            url=url,
            title=self.title_input.text().strip(),
            browser=browser,
            download_dir=self.download_dir,
            language=self.language,
            extraction_rules={key: field.text().strip() for key, field in self.rule_inputs.items()
                              if self.rules_group.isChecked() and field.text().strip()},
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.failed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.on_thread_finished)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def on_progress(self, current: int, total: int, message: str, chapter_title: str):
        percentage = int((current / total) * 100) if total else 0
        self.progress_bar.setValue(max(0, min(100, percentage)))
        self.status_label.setText(self.format_progress_status(message, current, total))

    def format_progress_status(self, message: str, current: int, total: int) -> str:
        label = self.t(message) if message in TRANSLATIONS[self.language] else message
        if total > 0:
            return self.t("progress_format").format(label=label, current=current, total=total)
        return label

    def append_log(self, message: str):
        self.log_box.appendPlainText(message)

    def on_finished(self, payload: dict):
        self._pending_result = payload

    def on_failed(self, message: str):
        self._pending_error = message

    def on_thread_finished(self):
        # 工作线程完全退出后才能关闭对话框，避免销毁仍在运行的 QThread。
        self.thread = None
        self.worker = None
        if self._cancel_requested:
            super().reject()
            return
        if self._pending_error is not None:
            self.show_download_error(self._pending_error)
            return
        payload = self._pending_result
        if payload is None:
            self.show_download_error("下载线程已结束，但没有返回结果。")
            return
        self.result_data = payload
        self.progress_bar.setValue(100)
        success = self.t("success").format(count=payload["chapter_count"])
        self.status_label.setText(success)
        self.append_log(payload["file_path"])
        self.btn_close.setText(self.t("close"))
        QMessageBox.information(self, self.t("title"), success)
        self.accept()

    def show_download_error(self, message: str):
        self.progress_bar.setValue(0)
        self.status_label.setText(self.t("failed"))
        self.append_log(message)
        QMessageBox.critical(self, self.t("failed"), message)
        self.btn_download.setEnabled(True)
        self.btn_close.setText(self.t("close"))
        self.btn_close.setEnabled(True)
        self.url_input.setEnabled(True)
        self.title_input.setEnabled(True)
        self.browser_combo.setEnabled(True)
        self.rules_group.setEnabled(True)

    def show_export_help(self):
        guide_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookie_export_guide.md")
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Basic markdown to plain text conversion for MessageBox
            import re
            content = re.sub(r"#+ (.*)", r"--- \1 ---", content)
            content = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", content)
            QMessageBox.information(self, self.t("how_to_export"), content)
        except Exception:
            QMessageBox.information(self, self.t("how_to_export"), "Please refer to cookie_export_guide.md for instructions.")

    def reject(self):
        self._cancel_requested = True
        if self.thread and self.thread.isRunning():
            if self.worker:
                self.worker.abort()
            self.append_log("正在取消下载，等待当前请求结束；已完成章节会保留缓存。")
            self.btn_close.setEnabled(False)
            return
        super().reject()
