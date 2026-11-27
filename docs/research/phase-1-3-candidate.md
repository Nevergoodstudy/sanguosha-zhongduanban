# 架构换新阶段 1–3 候选验收

候选构建提交为 `b9ce552`，桌面练习版为 `0.1.0`。本轮沿用阶段 0 的发布基线，由草稿 PR #2 汇总变更。[架构换新路线图](presentations/architecture-roadmap.pptx) · [草稿 PR #2](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/pull/2) · [双平台构建](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45943602129)

Apple Silicon 用户可解压后打开 `Sanguosha Practice.app`。Windows 用户可解压后运行 `-setup.exe`，安装后从开始菜单打开 `Sanguosha Practice`。[macOS arm64 候选包](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45943602129/artifacts/15173464754) · [Windows x64 候选包](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45943602129/artifacts/15173489877)

## 阶段 1 · 规则与续局

- Textual、三档 AI 和 LAN 共用 `GameEngine.execute_action` 的手牌出牌及回合弃牌入口。动作记录包含顺序、回合、阶段和卡牌数据编号。取消选择目标时，手牌、弃牌堆和动作记录均保持原状态。
- 终端练习局在回合开始前原子替换存档。存档记录牌堆顺序、随机状态、席位、阶段和动作记录。中途退出后重新执行当时未完成的回合，结算成功保存战报后移除续局文件。[续局命令](../playing.md#保存与恢复练习局) · [Python 随机状态接口](https://docs.python.org/3.12/library/random.html#random.getstate) · [Textual 自动化测试](https://textual.textualize.io/guide/testing/)
- Mac 上用两次独立的打包终端进程验证存档、退出、重新打开、继续出牌及结算。固定种子 42 的同一练习在 Mac 桌面、真实终端、无界面规则引擎和 LAN 请求适配器上，胜负与 33 条事件一致。后两者从同一快照驱动时，牌区、阶段、随机状态与 5 条动作记录也一致。
- 20 个种子的测试分别比较续局与连续运行的胜负、事件、动作、牌区与随机状态。新增续局文件记录格式、规则版本和牌库及技能数据指纹。早期的续局文件仍可读取，带版本指纹的文件会检查数据是否匹配。
- 从相同快照运行无界面引擎和 LAN 请求适配器，乐不思蜀、翻面、无懈抵消、非法目标和 LAN 请求超时的回合结果、事件、牌区与随机状态一致。当前统一入口覆盖主动使用手牌及回合弃牌，技能和响应沿用现有请求处理路径。
- 本机 1,566 项 Python 测试、Ruff 语法检查及 CI 同级别 Bandit 静态检查通过。MyPy 全项目类型检查仍报告 293 项问题。

## 阶段 2 · 桌面练习原型

- Tauri 2 随包启动 Python 规则进程，界面通过本地标准输入输出通信，只读取当前玩家可见的牌桌状态。打包测试会从系统盘根目录启动 Python 进程，跑完固定练习，核对战报和退出。桌面日志默认写入用户数据目录。[Tauri Sidecar](https://v2.tauri.app/develop/sidecar/) · [Tauri 能力配置](https://v2.tauri.app/security/capabilities/)
- macOS arm64 已用实际窗口验证默认启动、键盘选将、出牌、弃牌、出闪、结算、查阅战报和退出。macOS 候选包使用临时签名，可用于本机验收。公证及干净 Mac 的下载启动仍待验证。[Tauri macOS 签名](https://v2.tauri.app/distribute/sign/macos/#ad-hoc-signing)
- Windows CI 构建 x64 NSIS 安装包，静默安装后用已安装的规则进程完成练习，再验证卸载。Windows 实体设备的安装、WebView2 界面、中文键盘流程和卸载仍需实测。[Tauri Windows 安装包](https://v2.tauri.app/distribute/windows-installer/) · [NSIS 静默安装与路径参数](https://nsis.sourceforge.io/Docs/Chapter3.html)
- 按路线图，Mac 和 Windows 各需 20–30 名玩家对照终端与桌面版。与同平台终端版相比，首局完成率至少提高 15 个百分点，或首次合法出牌的中位耗时至少缩短 25%，才达到体验验收条件。[桌面体验验收指标](presentations/architecture-roadmap.pptx)

## 阶段 3 · 受控 LAN

- LAN 服务默认监听 `127.0.0.1`。跨设备内测时，房主指定自己的局域网地址并传入 `--lan-preview`。[房主和玩家操作](../playing.md#局域网内测)
- Windows 终端用后台线程读取标准输入，WebSocket 事件循环可以同时收到对局消息。CI 使用打包程序验证两个命令行客户端建房、进房和退出。[Python 接入标准输入的限制](https://docs.python.org/3.14/library/asyncio-eventloop.html#working-with-pipes)
- 本机自动化测试通过实际 WebSocket 连接运行双客户端完整对局，覆盖断线后恢复待处理请求、席位视图隔离和胜负结算。当前验收运行于本机回环接口，Mac 与 Windows 跨设备重连和对局仍需两台实体设备联验。
