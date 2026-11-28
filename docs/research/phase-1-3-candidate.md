# 终端版架构换新与验收

项目只维护 Textual 终端版。候选构建覆盖 macOS arm64、Windows x64 和 Linux x64。沿用阶段 0 的发布基线，由草稿 PR #2 汇总变更。2026 年 11 月 26 日的路线图为历史调研资料。[新手指南](../playing.md) · [草稿 PR #2](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/pull/2) · [终端候选构建](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/workflows/ci.yml?query=branch%3Aarchitecture%2Fphase-1)

## 阶段 1 · 规则与续局

- Textual、三档 AI 和 LAN 共用 `GameEngine.execute_action` 的手牌出牌及回合弃牌入口。动作记录包含顺序、回合、阶段和卡牌数据编号。取消选择目标时，手牌、弃牌堆和动作记录均保持原状态。
- 终端练习局在回合开始前原子替换存档。存档记录牌堆顺序、随机状态、席位、阶段和动作记录。中途退出后重新执行当时未完成的回合，结算成功保存战报后移除续局文件。[续局命令](../playing.md#保存与恢复练习局) · [Python 随机状态接口](https://docs.python.org/3.12/library/random.html#random.getstate) · [Textual 自动化测试](https://textual.textualize.io/guide/testing/)
- Mac 上用两次独立的打包终端进程验证存档、退出、重新打开、继续出牌及结算。固定种子 42 的同一练习在真实终端、无界面规则引擎和 LAN 请求适配器上，胜负与 33 条事件一致。后两者从同一快照驱动时，牌区、阶段、随机状态与 5 条动作记录也一致。
- 20 个种子的测试分别比较续局与连续运行的胜负、事件、动作、牌区与随机状态。新增续局文件记录格式、规则版本和牌库及技能数据指纹。早期的续局文件仍可读取，带版本指纹的文件会检查数据是否匹配。
- 从相同快照运行无界面引擎和 LAN 请求适配器，乐不思蜀、翻面、无懈抵消、非法目标和 LAN 请求超时的回合结果、事件、牌区与随机状态一致。当前统一入口覆盖主动使用手牌及回合弃牌，技能和响应沿用现有请求处理路径。
- 候选构建提交 `51c71d0` 的本机全量测试通过 1,566 项。GitHub Actions 通过六组跨平台测试、三个终端构建、安装后的 wheel 检查和打包后的 LAN 冒烟。MyPy 本机仍报告 40 个文件中的 287 项问题，当前工作流将其作为非阻断检查。[候选 CI](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/46161023374)

## 终端界面与平台验收

- 提交 `cef3e17` 修复 80×24 时战斗日志、信息面板和结束出牌按钮的可见性。手牌保留三行内容，窗口恢复至 120×40 后自动恢复常规布局。Mac ARM64 成品在 80×24 中文和 120×40 英文中各完成一次纯键盘练习，两份战报都记录了双方成功闪避及最终胜负，两个进程均正常退出。
- Windows x64 的 `51c71d0` 成品在 GitHub Windows runner 的 ConPTY 分别以 80×24 和 120×40 完成中文键盘练习、保存战报并退出。验收脚本读取候选构建并核对 SHA-256，同时检查双方闪避事件。实体机上的首次启动及字体显示仍待核验。[Windows 终端验证](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/46161444585)
- Docker 按项目的多阶段配方构建。Docker Hub 当时连接超时，本机验证使用公共 ECR 的 Python 基础镜像及已安装的 BuildKit 前端。容器通过依赖与健康检查，以 UID 999 运行。Mac 打包客户端和 Linux 容器客户端通过 WebSocket 完成进房、准备、选将、查看首个对局状态及退出。

## 阶段 3 · 受控 LAN

- LAN 服务默认监听 `127.0.0.1`。跨设备内测时，房主指定自己的局域网地址并传入 `--lan-preview`。[房主和玩家操作](../playing.md#局域网内测)
- Windows 终端用后台线程读取标准输入，WebSocket 事件循环可以同时收到对局消息。CI 使用打包程序验证两个命令行客户端建房、进房和退出。[Python 接入标准输入的限制](https://docs.python.org/3.14/library/asyncio-eventloop.html#working-with-pipes)
- 本机自动化测试通过实际 WebSocket 连接运行双客户端完整对局，覆盖断线后恢复待处理请求、席位视图隔离和胜负结算。当前验收运行于本机回环接口，Mac 与 Windows 跨设备重连和对局仍需两台实体设备联验。

## 待完成的验收

| 项目 | 通过条件 |
| --- | --- |
| 技能与响应入口 | Textual、AI 和 LAN 共享提交路径，保留目标取消、手牌消耗、技能转换、请求超时和旧存档行为。回归同时核对动作记录、牌区和结算。 |
| 技能完整性与类型检查 | 确定两项缺失技能的原创效果，以行为测试替换 `yijue`、`yajiao` 的引用例外。清理 MyPy 报告的类型错误后，再将现有检查设为阻断。 |
| Windows 实体机 | 在干净的 Windows x64 设备下载并核对成品哈希。用 Windows Terminal 在 80×24 中文与 120×40 英文分别确认手牌、提示和响应弹窗可见，再打完一局并检查战报及退出码。 |
| Mac 与 Windows 联机 | 两台设备连接同一个局域网。在待出牌的客户端上短暂断网，恢复网络后检查自己的手牌和原请求，继续出牌至两端显示同一个胜负。各自终端只显示对方的公开状态及手牌数量。[操作步骤](../playing.md#局域网内测) |
| 首次玩家试玩 | 记录构建提交、系统、终端尺寸、从显示主菜单到发动第一张合法牌的用时，以及卡住的步骤。邀请 3–5 位首次玩家，5 人参与时以至少 4 人在 90 秒内出第一张合法牌为通过条件。 |
| 正式发布 | 确认项目代码和游戏数据的授权方、许可范围与著作权声明。Mac 单文件内已找到 Pydantic、Textual 和 websockets 的许可文本，还需核对其他实际打包依赖的许可和随附方式。平台验收完成后，从已验证提交制作正式发布包及校验清单。 |
