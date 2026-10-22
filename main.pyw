from main import MoYuApp


# 与命令行入口共用初始化流程，避免双击时使用过期的界面和进度逻辑。
if __name__ == "__main__":
    app = MoYuApp()
    app.run()
