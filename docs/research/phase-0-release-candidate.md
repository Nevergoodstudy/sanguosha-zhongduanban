# 架构换新与阶段 0 候选验收

记录日期为 2026 年 11 月 27 日。候选构建源自同一提交 [`eea875c`](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/commit/eea875c86f36a1a151fd25beaf9199c2a841c7bd)，游戏版本为 4.0.0。改动通过[草稿 PR #1](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/pull/1)复核。

## 本批变更

- 发布候选分支统一用 Python 3.12 和 PyInstaller 构建。每个平台附带 SHA‑256 和记录源码提交、架构及工具版本的构建清单。
- 打包程序启用 UTF‑8，修复 Windows 默认代码页下中文帮助输出崩溃的问题。构建后从仓库外验证帮助和中文战报回放。

## 候选下载与验收

候选包通过 GitHub Actions 提供，下载需登录 GitHub。解压后核对同名 `.sha256` 文件。Apple Silicon 执行前用 `chmod +x` 恢复运行权限。Windows 请在 Windows Terminal 的 PowerShell 中运行解压后的 `.exe`。

| 平台 | 候选下载 | 已验证 |
| --- | --- | --- |
| Apple Silicon | [macOS arm64](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45934282903/artifacts/15170251468) | 本机签名校验、中文键盘练习、结算、战报及退出。80×24 可完成练习，实测闪避提示未显示。 |
| Windows x64 | [Windows x64](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45934282903/artifacts/15169274048) | Windows runner 完成中文终端练习、战报与退出。详见 [ConPTY 验收](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45935238794)。 |
| Linux x64 | [Linux x64](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45934282903/artifacts/15169598257) | CI 构建、仓库外启动帮助和中文回放。 |

三平台两组 Python 版本共六项测试任务通过。MyPy 仍报告 294 项错误，Bandit 仍报告默认监听全部网卡。[测试记录](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45935444260)

正式双端发行还需完成干净 Windows 真机的下载、字体和首次启动验收，并核对代码与随包内容的分发依据。[现有 Apple Silicon 正式下载](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/releases/tag/macos-2026.11.26)

## 可编辑 PowerPoint

以下演示文稿以 2026 年 11 月 26 日的资料为基准。本页记录次日的阶段 0 实施进展。

- [TUI 跨平台使用调研](presentations/tui-platform-research.pptx)
- [项目风险与严重性排序](presentations/project-risk-review.pptx)
- [架构换新方案](presentations/architecture-roadmap.pptx)
