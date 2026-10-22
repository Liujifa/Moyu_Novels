# main.py
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QMessageBox, QSystemTrayIcon

from library_manager import LibraryManager
from library_view import LibraryView
from download_dialog import WebDownloadDialog
from reader_logic import ReaderLogic
from reader_window import ReaderWindow
from app_paths import APP_VERSION, data_directory, resource_path


class MoYuApp:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("MoYu Reader")
        self.app.setApplicationVersion(APP_VERSION)
        self.app.setWindowIcon(QIcon(str(resource_path("assets/moyu.ico"))))
        self.app.setStyle("Fusion")
        self.app.setQuitOnLastWindowClosed(False)
        self._quitting = False
        self._shutdown_pending = set()

        try:
            self.manager = LibraryManager(str(data_directory() / "library.json"))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(None, "无法读取书库", str(exc))
            raise SystemExit(1) from exc
        self.logic = ReaderLogic()

        self.reader_win = ReaderWindow(self.manager, self.logic)
        self.library_win = LibraryView(self.manager, self.logic)

        self.main_win = QMainWindow()
        self.main_win.setCentralWidget(self.library_win)
        self.main_win.setWindowTitle(f"MoYu Reader · 摸鱼看小说 {APP_VERSION}")
        self.main_win.setMinimumSize(860, 620)
        self.main_win.resize(1080, 760)
        available = self.app.primaryScreen().availableGeometry()
        self.main_win.resize(min(1080, available.width()), min(760, available.height()))

        self.setup_tray()
        self.setup_connections()
        self.main_win.show()

    def show_first_run_message(self):
        settings = self.manager.get_settings()
        if not settings.get("first_run", True):
            return

        message = QMessageBox(self.main_win)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("\u6b22\u8fce / Welcome")
        message.setText(
            "MoYu \u652f\u6301\u672c\u5730 TXT \u9605\u8bfb\uff0c"
            "\u4e5f\u652f\u6301\u4ece\u7f51\u9875\u4e0b\u8f7d\u5c0f\u8bf4\u5e76\u81ea\u52a8\u5165\u5e93\u3002"
        )
        message.exec()

        settings["first_run"] = False
        self.manager.update_settings(settings)

    def setup_connections(self):
        self.library_win.novel_selected.connect(self.open_novel)
        self.library_win.settings_changed.connect(self.reader_win.apply_settings)
        self.reader_win.progress_changed.connect(self.library_win.sync_progress)
        self.reader_win.save_failed.connect(lambda message: QMessageBox.warning(self.main_win, "保存失败", message))

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self.app)

        icon = QIcon(str(resource_path("assets/moyu.ico")))
        if icon.isNull():
            from PyQt6.QtGui import QColor, QPainter, QPixmap

            pixmap = QPixmap(32, 32)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setBrush(QColor("#4CAF50"))
            painter.drawEllipse(4, 4, 24, 24)
            painter.end()
            icon = QIcon(pixmap)

        self.tray_icon.setIcon(icon)

        menu = QMenu()
        show_lib_action = QAction("打开书库 / Library", self.app)
        show_lib_action.triggered.connect(self.main_win.show)

        show_reader_action = QAction("返回阅读 / Reader", self.app)
        show_reader_action.triggered.connect(self.reader_win.show)

        quit_action = QAction("退出 / Quit", self.app)
        quit_action.triggered.connect(self.quit_app)

        menu.addAction(show_lib_action)
        menu.addAction(show_reader_action)
        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_activated)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.main_win.show()

    def open_novel(self, novel_data, start_pos=0):
        novel_data.setdefault("_restore_saved_scroll", start_pos == novel_data.get("last_pos", 0))
        novel_data["last_pos"] = start_pos
        if self.reader_win.load_novel(novel_data) is False:
            QMessageBox.warning(self.main_win, "无法打开小说", f"{novel_data['path']}\n{self.reader_win.last_load_error}")
            return
        self.reader_win.show()
        self.main_win.hide()

    def quit_app(self):
        if self._quitting:
            return
        self._quitting = True
        self.reader_win.persist_progress()
        downloads = [dialog for dialog in self.library_win.findChildren(WebDownloadDialog)
                     if dialog.thread is not None]
        self._shutdown_pending = {dialog.thread for dialog in downloads}
        if not downloads:
            self.app.quit()
            return
        # 托盘退出也必须等工作线程结束，不能直接销毁下载中的对话框。
        self.main_win.setEnabled(False)
        for dialog in downloads:
            thread = dialog.thread
            thread.finished.connect(lambda thread=thread: self._download_stopped_for_shutdown(thread))
            dialog.reject()
            # 线程可能在收集列表与连接信号之间结束，补查并通过集合避免重复处理。
            if not thread.isRunning():
                self._download_stopped_for_shutdown(thread)

    def _download_stopped_for_shutdown(self, thread):
        if thread not in self._shutdown_pending:
            return
        self._shutdown_pending.remove(thread)
        if not self._shutdown_pending:
            self.app.quit()

    def run(self):
        sys.exit(self.app.exec())


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from release_smoke import run

        sys.exit(run(sys.argv[2]))
    else:
        app = MoYuApp()
        app.run()
