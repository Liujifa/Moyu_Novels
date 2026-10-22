import tempfile
import argparse

from web_novel_downloader import WebNovelDownloader


def main(argv=None):
    parser = argparse.ArgumentParser(description="通用小说目录在线检查（兼容原脚本名）")
    parser.add_argument("url", nargs="?", default="https://m.bqg5.com/1_1771/", help="要检查的目录 URL")
    parser.add_argument("--chapter-links", default="", help="可选的章节链接 CSS 选择器")
    parser.add_argument("--next-page", default="", help="可选的目录下一页 CSS 选择器")
    args = parser.parse_args(argv)
    # 在线冒烟测试仅在显式运行脚本时执行，测试发现和模块导入均不访问网络。
    with tempfile.TemporaryDirectory(prefix="reader_catalog_test_") as directory:
        rules = {key: value for key, value in {"chapter_link_selector": args.chapter_links,
                                             "catalog_next_selector": args.next_page}.items() if value}
        downloader = WebNovelDownloader(directory, log_callback=print, extraction_rules=rules)
        url = args.url
        print(f"正在检查目录：{url}")
        soup = downloader.fetch_soup(url)
        # extract_chapter_links 已遍历目录分页，不能为每页再次重复遍历。
        chapters = downloader.extract_chapter_links(url, soup)
        if not chapters:
            raise RuntimeError("未发现有效章节，在线目录检查失败。")
        print(f"目录检查通过，共 {len(chapters)} 章。")


if __name__ == "__main__":
    main()

