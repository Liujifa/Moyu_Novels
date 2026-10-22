"""发布包自检：使用临时书库验证界面、读写和本地 HTTP 下载，不接触个人数据。"""

import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PyQt6.QtTest import QTest

from app_paths import APP_VERSION, data_directory, resource_path
from download_dialog import WebDownloadDialog
from reader_logic import ReaderLogic
from web_novel_downloader import WebNovelDownloader


def run(output_directory):
    from main import MoYuApp

    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="moyu-smoke-") as temporary:
        os.environ["MOYU_DATA_DIR"] = temporary
        controller = MoYuApp()
        view = controller.library_win
        checks = {}

        def snapshot(widget, name):
            QTest.qWait(160)
            if not widget.grab().save(str(output / name)):
                raise RuntimeError(f"无法保存界面截图：{name}")

        try:
            assert data_directory() == Path(temporary).resolve()
            assert not controller.main_win.windowIcon().isNull()
            assert resource_path("cookie_export_guide.md").exists()
            snapshot(controller.main_win, "library-empty.png")
            novel = Path(temporary) / "星河来信.txt"
            novel.write_text("第一章 一封远方的信\n" + "窗外的风掠过树梢，书页轻轻翻动。\n" * 50
                             + "第二章 月光里的旅人\n" + "故事从这里继续。\n" * 50, encoding="utf-8")
            controller.manager.add_novel("星河来信", str(novel))
            controller.manager.add_novel("山海之间", str(Path(temporary) / "example.txt"))
            view.refresh_library()
            view.select_novel_by_path(str(novel))
            assert view.btn_read.isEnabled()
            view.chapter_combo.setCurrentIndex(1)
            assert view.pending_chapter_pos == view.current_chapters[1]["pos"]
            snapshot(controller.main_win, "library.png")
            view.search_input.setText("不存在的书")
            assert not view.btn_read.isEnabled()
            view.search_input.clear()
            view.select_novel_by_path(str(novel))
            view.chapter_combo.setCurrentIndex(1)
            view.btn_read.click()
            QTest.qWait(350)
            assert controller.reader_win.current_novel["path"] == str(novel)
            assert controller.reader_win.reader_area.textCursor().position() >= view.current_chapters[1]["pos"]
            snapshot(controller.reader_win, "reader.png")
            checks["library_and_chapter_navigation"] = True

            dialog = WebDownloadDialog(parent=view)
            dialog.show()
            snapshot(dialog, "download.png")
            dialog.rules_group.setChecked(True)
            snapshot(dialog, "download-rules.png")
            dialog.close()

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/book/":
                        text = '<h1>通用下载自检</h1><ol><li><a href="one">第一章</a></li><li><a href="two">第二章</a></li></ol>'
                    else:
                        text = '<article><p>这是本地服务器提供的章节正文。</p></article>'
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(text.encode("utf-8"))

                def log_message(self, *_):
                    pass

            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                downloader = WebNovelDownloader(str(Path(temporary) / "downloads"))
                downloader.session.trust_env = False
                result = downloader.download(f"http://127.0.0.1:{server.server_port}/book/")
                assert result.chapter_count == 2
                assert len(ReaderLogic().get_chapters(result.file_path)) == 2
                assert downloader.charset
                checks["http_download_and_chapter_index"] = True
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)
            controller.reader_win.persist_progress(force=True)
            assert Path(controller.manager.data_file).exists()
            checks["persistent_data_outside_bundle"] = True
            report = {"version": APP_VERSION, "success": True, "checks": checks}
            (output / "smoke-result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            (output / "smoke-result.json").write_text(json.dumps({"success": False, "error": str(exc)}), encoding="utf-8")
            raise
        finally:
            controller.reader_win.hide()
            controller.reader_win.hover_timer.stop()
            controller.main_win.close()
            controller.tray_icon.hide()
            controller.app.quit()
    return 0
