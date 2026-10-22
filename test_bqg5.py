import tempfile

from web_novel_downloader import WebNovelDownloader


def main():
    # 在线冒烟测试仅在显式运行脚本时执行，测试发现和模块导入均不访问网络。
    with tempfile.TemporaryDirectory(prefix="reader_catalog_test_") as directory:
        downloader = WebNovelDownloader(directory, log_callback=print)
        url = "https://m.bqg5.com/1_1771/"
        print(f"正在检查目录：{url}")
        soup = downloader.fetch_soup(url)
        # extract_chapter_links 已遍历目录分页，不能为每页再次重复遍历。
        chapters = downloader.extract_chapter_links(url, soup)
        if not chapters:
            raise RuntimeError("未发现有效章节，在线目录检查失败。")
        print(f"目录检查通过，共 {len(chapters)} 章。")


if __name__ == "__main__":
    main()

