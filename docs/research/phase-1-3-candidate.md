# 终端版架构换新与验收

项目只维护 Textual 终端版。候选构建覆盖 macOS arm64、Windows x64 和 Linux x64。沿用阶段 0 的发布基线，由草稿 PR #2 汇总变更。2026 年 11 月 26 日的路线图为历史调研资料。[新手指南](../playing.md) · [草稿 PR #2](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/pull/2) · [终端候选构建](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/workflows/ci.yml?query=branch%3Aarchitecture%2Fphase-1)

## 阶段 1 · 规则与续局

- Textual、三档 AI 和 LAN 共用 `GameEngine.execute_action` 的手牌出牌及回合弃牌入口。动作记录包含顺序、回合、阶段和卡牌数据编号。取消选择目标时，手牌、弃牌堆和动作记录均保持原状态。
- 终端练习局在回合开始前原子替换存档。存档记录牌堆顺序、随机状态、席位、阶段和动作记录。中途退出后重新执行当时未完成的回合，结算成功保存战报后移除续局文件。[续局命令](../playing.md#保存与恢复练习局) · [Python 随机状态接口](https://docs.python.org/3.12/library/random.html#random.getstate) · [Textual 自动化测试](https://textual.textualize.io/guide/testing/)
- Mac 上用两次独立的打包终端进程验证存档、退出、重新打开、继续出牌及结算。固定种子 42 的同一练习在真实终端、无界面规则引擎和 LAN 请求适配器上，胜负与 33 条事件一致。后两者从同一快照驱动时，牌区、阶段、随机状态与 5 条动作记录也一致。
- 20 个种子的测试分别比较续局与连续运行的胜负、事件、动作、牌区与随机状态。新增续局文件记录格式、规则版本和牌库及技能数据指纹。早期的续局文件仍可读取，带版本指纹的文件会检查数据是否匹配。
- 从相同快照运行无界面引擎和 LAN 请求适配器，乐不思蜀、翻面、无懈抵消、非法目标和 LAN 请求超时的回合结果、事件、牌区与随机状态一致。当前统一入口覆盖主动使用手牌及回合弃牌，技能和响应沿用现有请求处理路径。
- 本机 1,566 项 Python 测试通过。GitHub Actions 的六组跨平台测试、Ruff 语法检查及 Bandit 静态检查通过。MyPy 全项目类型检查仍报告 287 项已有问题。[终端版 CI](https://github.com/Nevergoodstudy/sanguosha-zhongduanban/actions/runs/45950845930)

## 阶段 3 · 受控 LAN

- LAN 服务默认监听 `127.0.0.1`。跨设备内测时，房主指定自己的局域网地址并传入 `--lan-preview`。[房主和玩家操作](../playing.md#局域网内测)
- Windows 终端用后台线程读取标准输入，WebSocket 事件循环可以同时收到对局消息。CI 使用打包程序验证两个命令行客户端建房、进房和退出。[Python 接入标准输入的限制](https://docs.python.org/3.14/library/asyncio-eventloop.html#working-with-pipes)
- 本机自动化测试通过实际 WebSocket 连接运行双客户端完整对局，覆盖断线后恢复待处理请求、席位视图隔离和胜负结算。当前验收运行于本机回环接口，Mac 与 Windows 跨设备重连和对局仍需两台实体设备联验。
