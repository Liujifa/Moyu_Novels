# Windows 发布流程

应用使用 PyInstaller 的目录模式，把 Python、Qt 和运行依赖放入 `MoYuReader.exe` 旁的 `_internal`。用户解压整个 ZIP 即可运行，数据保存到 `%LOCALAPPDATA%\MoYuReader`，不写入资源目录。

## 构建

在 Windows x64 / Python 3.13 的独立虚拟环境安装根目录 `requirements-build.txt`，运行回归测试和 `python build_release.py`。`assets/moyu.ico` 用于窗口、托盘及 EXE，`version_info.txt` 声明 Windows 文件版本。

版本变更时同步修改 `app_paths.APP_VERSION`、`version_info.txt` 和 README 下载文件名。构建脚本输出 `release-artifacts/MoYuReader-v<版本>-Windows-x64.zip` 与 `SHA256SUMS.txt`。

ZIP 生成前会在不含 Python 路径的环境中自动执行 EXE 自检，自检失败时停止生成本次压缩包。脚本同时检查是否误带书库、小说目录、Cookie 或章节索引。构建日志位于终端输出；无控制台 EXE 的错误写入数据目录 `startup.log`。

打包配置排除 Windows 自带的 ICU、UCRT 和系统 API DLL，防止构建机第三方同名 DLL 或新版 SDK 文件覆盖目标操作系统组件。

## 验证和发布

1. 运行 `python -m unittest discover -v`。
2. 运行 `python main.py --smoke-test build/ui-preview`，检查截图排版。
3. 构建 ZIP，将其解压到独立目录，运行 `MoYuReader.exe --smoke-test <报告目录>`，等待进程退出，确认报告 `success` 为 `true`。
4. 检查 ZIP 只包含应用、依赖、帮助、许可证和文档，没有个人小说、`library.json` 或 Cookie。
5. 提交并推送代码，针对该提交创建版本标签和 GitHub Release，上传 ZIP 与校验文件。说明系统要求、启动方式、数据目录和验证范围。

## 许可证和来源

构建脚本收集 Python 与各运行依赖的原始许可证，并记录精确版本和源代码获取地址。应用源码保留仓库中的 Apache-2.0 许可；含 PyQt6 的组合发布包还适用 PyQt6 的 GPL-3.0 条款，第三方组件继续按各自许可证分发。Qt 采用动态链接，可替换为兼容版本。

## 限制

- 本发布目标是 Windows 10 / 11 x64，尚未制作 ARM64、macOS 或 Linux 包。
- EXE 未进行商业代码签名。请从本仓库 Releases 获取并核对 SHA-256。
- 自检使用当前 Windows 环境，并不代替不同机器和系统版本的兼容性测试。
- 更新只需替换应用目录。用户数据独立保留，本地小说路径改变时仍需重新导入。
