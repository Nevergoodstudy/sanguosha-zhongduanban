# 三国杀终端版项目审查报告

审查日期为 2026 年 11 月 24 日。源码位于 `sanguosha_backup_20260121_071454/`，声明版本为 4.0.0。本文的文件位置均以该源码目录为基准。

## 结论

本次记录 31 项问题，包含 4 项发布阻塞。标准 Python 安装无法构建，联机依赖声明有缺项，正常开局会在首个回合状态广播时报错，CI 前置的 Ruff 检查也未通过。补齐依赖后，现有测试 1523 项全部通过，按仓库口径覆盖率为 78.20%。覆盖报告显示联机主循环未被执行，TUI 实际游戏屏幕被配置排除。单机优先修复乐不思蜀、翻面、拒绝出牌后的手牌状态和技能交互，再把联机接到同一套规则入口。

- **P0** 表示安装、部署或明确宣称的主要功能受阻。
- **P1** 表示可能破坏对局规则、状态一致性、数据或对外部署边界。
- **P2** 表示具体的维护、兼容性或体验缺口。
- **运行确认** 表示在隔离副本观测到结果。**源码确认** 表示入口、调用链或配置能够直接证明。**待联验** 表示需要在目标环境或更完整场景验证影响。

## 2026 年 11 月 25 日 Mac 适配复验

**Apple Silicon 单机版已可运行。** 成品在项目的 `dist/sanguosha-macos-arm64`，由 arm64 Python 3.12.14 和 PyInstaller 6.22.3 构建，大小约 18.4 MiB。把下面这一行粘贴到 Mac「终端」即可启动。

```zsh
"./sanguosha-4.0.0-macos-arm64"
```

选择「开始新游戏」，确认设置并选将。进入自己的出牌阶段后按 `Q` 退出。项目成品和从 wheel 安装的 `sanguosha` 命令均在源码目录之外完成这一路径，退出状态码均为 0。成品的 Mach-O 架构为 arm64，本机 `codesign --verify` 校验通过。

### 修复与证据

- **包构建与运行依赖。** `pyproject.toml` 显式声明多个顶层包与两个根级模块，并将卡牌及武将数据、译文和 Textual 样式纳入发行包。补齐 Pydantic 2 的运行依赖。wheel 与 sdist 均已构建，安装后 `pip check` 通过。原报告 P0-01 的 Python 分发包构建问题已通过复验，P0-02 的项目元数据缺项已修复。Docker、旧依赖清单和独立发布流程仍需按原条目复验。
- **对局退出。** `ui/textual_ui/screens/game_play.py` 原先将 `Q` 发送成结束出牌，后台线程可能随即进入弃牌流程。现在退出请求唤醒等待中的游戏线程，让它在弃牌前结束，然后由 Textual 的 UI 线程退出。已验证常规出牌等待路径的 `Q`。
- **AI 回合卡死。** 3 人自动对局回溯进入「无中生有」结算。构造一张在手牌、一张在弃牌堆、摸牌堆为空的状态后，可以稳定复现。普通 AI 每次使用一张后摸回另一张，重复同一过程，外层的总回合上限在此期间不会递增。普通策略现沿用简单策略已有的 `ai_max_actions` 配置，默认每次出牌阶段最多 10 轮行动决策，困难策略也通过复用普通策略受此限制。新增回归用例验证出牌阶段返回且两张牌仍在手牌与弃牌堆中。
- **测试。** 修改后的全量套件按默认收集顺序和乱序种子 42 分别运行，均为 1,524 项通过，其中包含 46 项 Textual 测试。终端验证覆盖主菜单、设置、选将、首个人类出牌阶段及退出。Intel Mac、所有弹窗中的退出路径和真人联机完整对局未做端到端验证。

### 在 Apple Silicon 上重建

在源码目录内执行以下命令，需先有 arm64 Python 3.12。现有 `build.py` 会清理构建目录中的 `dist/` 和 `build/`，因此先复制到独立目录，可保留备份内的 Windows 成品。

```zsh
stage="$(mktemp -d "${TMPDIR:-/tmp}/sanguosha-macos.XXXXXX")"
rsync -a --exclude='.git/' --exclude='build/' --exclude='dist/' \
  --exclude='__pycache__/' --exclude='.venv/' "$PWD/" "$stage/src/"
cd "$stage/src"
python3.12 -m venv "$stage/venv"
"$stage/venv/bin/python" -m pip install . 'PyInstaller==6.22.3'
"$stage/venv/bin/python" build.py --name sanguosha-macos-arm64
file dist/sanguosha-macos-arm64
codesign --verify --verbose=2 dist/sanguosha-macos-arm64
"$PWD/dist/sanguosha-macos-arm64"
```

单独构建 wheel 与 sdist 时，在安装了 PyPA `build` 的环境中运行 `pyproject-build`。项目根目录已有 `build.py`，会占用从该目录执行 `python -m build` 时的模块名。

检索参考包括 Setuptools 的自定义包发现配置、PyInstaller 的 macOS 多架构构建说明及 Textual 的 Pilot 测试示例。本轮使用了 `build-macos-apps:build-run-debug` 与 `debugging-and-error-recovery` 技能。[Setuptools 包发现](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html) · [PyInstaller macOS 架构](https://pyinstaller.org/en/stable/feature-notes.html#macos-multi-arch-support) · [Textual 测试](https://textual.textualize.io/guide/testing/)

## P0｜安装和联机阻塞

### P0-01 · README 的安装命令和 CI 的 Python 构建无法生成分发包

**运行确认** · `pyproject.toml:12`、`pyproject.toml:32`、`README.md:91`、`.github/workflows/ci.yml` 中的 Build Package、`Dockerfile` 的 builder。

Setuptools 84.2.1 在隔离副本的 wheel 元数据阶段报告 `Multiple top-level packages discovered in a flat-layout`，列出了 `ui`、`ai`、`net`、`game`、`i18n` 和 `data`。仓库把多个顶层包和平铺模块置于根目录，配置却没有显式声明发现范围。只补包发现仍可能漏掉 `main.py`、`logging_config.py`、卡牌与武将 JSON、翻译 JSON 和 Textual 样式。Docker builder 只复制 `pyproject.toml` 即安装本项目，也绕开了这些实际文件与 README。

**修复与验收。** 先显式纳入运行所需的包与根级模块，给 JSON 和 TCSS 设定明确的包内归属与打包规则。内置资源用稳定的包资源入口读取，保留旧版外置数据路径的实际用户配置。Docker 先装已解析的运行依赖，再装同一个 wheel。CI 分别构建 sdist 和 wheel，从临时工作目录安装 wheel，实际执行命令入口、构造引擎、加载两个 locale，并用 Textual Pilot 挂载样式。Docker 另做容器启动冒烟检查。

### P0-02 · 联机服务器导入了未声明的 Pydantic 2 依赖

**运行确认** · `net/models.py:17`、`net/server.py:29`、`pyproject.toml:12`、`requirements.txt`、`.github/workflows/release.yml` 的 Install dependencies。

服务器加载时即导入 `BaseModel`、`ConfigDict` 和 `field_validator`。运行依赖、项目安装清单及发布构建清单均未声明 Pydantic。隔离 Python 导入 `net.server` 报 `ModuleNotFoundError: No module named 'pydantic'`，提供 Pydantic 2 的测试环境则可导入。测试自收集阶段也有直接导入，例如 `tests/test_net_models.py:8`。

**修复与验收。** 把 Pydantic 2 写入统一的运行依赖元数据，让 CI、Docker 和 PyInstaller 使用同一份解析后的依赖。清洁虚拟环境只装发行包后，验证 `import net.server`、`python -m net.server --help`，再对生成的独立可执行文件执行服务端启动冒烟。

### P0-03 · 联机入口无法完成一次真人出牌

**运行确认加源码确认** · `net/server.py:490`、`net/server.py:510`、`net/server.py:552`、`net/server.py:572`、`game/engine.py:1072`、`net/client.py:303`。

服务器用 `setup_headless_game` 初始化全部 AI，连接 ID 从 1 起步，引擎座位从 0 起步，两者没有显式映射。进程内正常开局冒烟确认第一次常规状态广播因读取不存在的 `Player.alive` 抛出 `AttributeError`，房间随后被标记为结束。正确字段是 `is_alive`。即使进入真人等待分支，Future 的结果也只用于结束等待，动作没有提交引擎，服务器随后直接推进回合。响应和选将处理器仅广播消息。CLI 只注册收包日志回调，缺少建房、选将、出牌等交互输入。

**修复与验收。** 先在对外入口纠正功能标注。实现时创建显式的连接、会话、座位映射，由同一对局任务串行处理动作。引擎完成校验与结算后再发送结果。真人出牌循环应允许连续出牌，只有结束、超时或对局结束才退出。选将、响应和主动动作分别关联待处理请求。用两个真实客户端完成建房、就绪、开局、出牌、响应、回合切换和正常结束，断言收到状态、血量与牌区确实改变。单独运行这一测试也应通过。

### P0-04 · Ruff 检查失败，CI 的构建依赖该检查

**运行确认** · `.github/workflows/ci.yml` 的 Lint & Format 与 Build Package、`pyproject.toml:40`、`.pre-commit-config.yaml:36`。

隔离环境的 Ruff 0.17.6 报 1399 条，其中 1014 条为文档字符串末尾标点规则 D415，208 条为公开方法文档字符串规则 D102。还有 30 条未使用变量、24 条未使用导入，以及 2 个会被重新格式化的文档。CI 安装无固定版本的 Ruff，本地 pre-commit 固定为 0.1.9，工具和规则基线不同。构建任务依赖该检查，即使解决 P0-01 也会被当前门槛拦截。

**修复与验收。** 用同一已验证 Ruff 版本运行 CI 与 pre-commit，先处理影响可读性和可靠性的 F、B、I 等规则，再明确中文文档字符串标点和历史文档中的示例代码是否由格式检查约束。分批消除已有问题，对有意保留的规则差异在配置里明确适用范围。对干净检出运行 `ruff check` 与 `ruff format --check`，两个命令都应退出 0。

## P1｜联机正确性与部署边界

初始版本的审查覆盖了重连、玩家视角隔离、消息校验、连接配置、房间和广播生命周期。新版局域网内测与验证状态见[改进计划](macos-improvement-plan.md)。

## P1｜单机规则、交互及数据一致性

### P1-07 · Textual 的正式回合入口绕过阶段状态机和乐不思蜀

**源码确认** · `ui/textual_ui/screens/game_play.py:211`、`ui/textual_ui/screens/game_play.py:249`、`ui/textual_ui/screens/game_play.py:274`、`game/turn_manager.py:89`、`game/turn_manager.py:225`、`game/judge_system.py:78`。

TUI 自己推进阶段，AI 直接调用 BOT 出牌，真人直接进入出牌循环。乐不思蜀的跳过逻辑仅位于 `TurnManager._execute_play_phase`，二者都跳过了它。TUI 的判断链也没有在判定致死后立刻终止该回合。现有 headless 的阶段测试可以通过而 TUI 行为仍然不同。

**修复与验收。** 让 TurnManager 成为阶段流转的单一入口，给真人阶段提供等待决策的适配器。引擎统一处理从判定阶段到出牌、死亡、结算结束的转移。以同一状态分别驱动 Textual 与 headless，断言跳过出牌、跳过摸牌、判定致死和回合事件一致。

### P1-08 · 武将翻面只改变标记，缺少跳过回合消费点

**源码确认** · `game/player.py:278`、`game/player.py:447`、`game/turn_manager.py:89`、`ui/textual_ui/widgets/player_panel.py:147`、`tests/test_skills.py:771`。

当前路径能翻转标记并在面板显示状态，回合执行路径没有据此翻回并跳过回合。现有相关测试检验的是布尔值改变。回合与翻面之间断开，会使有关技能的代价和收益失真。

**修复与验收。** 在统一的回合入口处理活人翻面，翻回并按项目规则发出跳过事件。明确结束技能在被跳过的整回合是否触发。构造翻面后接两个回合的规则测试，断言仅跳过一次，并在 Textual 界面走同一规则。

### P1-09 · 输入和弹窗没有绑定当前请求，旧操作会流入下一阶段

**源码确认** · `ui/textual_ui/screens/game_play.py:172`、`ui/textual_ui/screens/game_play.py:490`、`ui/textual_ui/screens/game_play.py:686`、`ui/textual_ui/screens/game_play.py:1106`、`ui/textual_ui/bridge.py:42`。

TUI 整局共享一个无界动作队列，`_respond` 不判断当前是否等待该种请求，快捷键发的是手牌索引。连续点击、AI 回合输入或对话结束后遗留的输入，都可能被下一次出牌请求消费。弹窗等待超时只让 worker 返回，未必关闭仍在屏幕上的那个弹窗。退出时主回合线程没有统一停止信号。

**修复与验收。** 每次交互建立一次性请求，带请求 ID、动作类型和稳定对象 ID。输入只提交到当前请求，超时、弹窗关闭、结束或退出都通过同一生命周期失效。Textual Pilot 覆盖快速双击、AI 回合抢按、取消目标、超时和退出后无状态变动。

### P1-10 · 部分主动技能和人类响应只有自动路径

**源码确认** · `ui/textual_ui/screens/game_play.py:482`、`ui/textual_ui/screens/game_play.py:1058`、`ui/textual_ui/bridge.py:226`、`game/request_handler.py:228`、`game/skill.py:157`。

技能按钮只提交第一项可用技能，执行时没有收集目标和代价牌。观星桥返回固定牌序，激将、护驾桥返回空值。火攻亮牌与弃同花色牌也缺少 Textual 桥接实现，从而走默认选择。不同武将或技能在单机真人局里的效果和预期交互不一致。

**修复与验收。** 按技能元数据生成可选技能、目标和代价牌请求，响应交还统一动作入口。观星、激将、护驾、火攻明确支持主动选择、取消和超时。Pilot 以两个可用技能的武将开局，分别验收带牌和目标的技能及防守交互。

### P1-11 · 拒绝出牌仍可能改变牌区

**运行确认** · `game/engine.py:654`、`game/combat.py:37`、`game/actions.py:87`、`game/actions.py:283`。

在最小单机引擎场景，使用手里的「杀」且目标为空时，返回 `False`，手牌减少 1，弃牌堆增加 1。原因是 `use_card` 在结算器判断之前移除手牌，部分分支自行退牌，部分分支直接弃牌。UI、AI 与动作对象也没有统一走同一验证。动作对象用实例内存地址或定义 ID 找牌，牌组同定义复制后无法提供可靠的跨进程标识。

**修复与验收。** 引擎在改变牌区之前验证出牌者、目标数与状态、牌所有权、阶段和卡牌条件。区分动作被拒绝和合法动作被无懈可击抵消。给实体牌稳定实例 ID，显式表达转换产生的虚拟牌及其代价。从不同入口验证非法动作前后手牌、弃牌、体力和回合计数不变，合法抵消只消耗一次。

### P1-12 · 全局随机状态破坏多局隔离和复现

**运行确认** · `game/engine.py:1055`、`game/card.py:322`、`net/server.py:487`、`tools/replay.py:53`。

调用 `setup_headless_game(seed=…)` 会改变 Python 进程的全局随机状态。服务端在同一进程创建多局，牌堆、AI 和部分技能直接使用全局 `random`，所以不同对局会相互影响。只保存一个开局种子不足以恢复中途随机位置。

**修复与验收。** 为每局创建独立 `random.Random`，通过已有引擎上下文提供给牌堆、AI、技能和随机 UI 后备决策。服务端种子生成与局内随机隔离。测试同种子单独运行与跨局交错运行时初始状态和后续动作一致。

### P1-13 · 存档、回放和战绩历史缺少运行入口与一致格式

**运行确认加源码确认** · `game/save_system.py:93`、`game/save_system.py:134`、`game/save_system.py:144`、`game/engine.py:206`、`main.py:123`、`tools/replay.py:75`、`game/match_history.py:66`。

将玩家 `flipped` 设为真后，序列化输出的 `is_flipped` 仍是假。存档只保留两個牌堆的计数，省略了牌堆顺序、实例 ID、随机状态和部分临时标志。`load_game` 返回字典，项目主要入口没有接续玩。普通 headless 局也可产生零条 action log，因为日志只在 `execute_action` 成功后追加，正常回合常直接调规则。导出工具读取 `actions`，主入口回放读取 `action_log`。主入口只打印步骤，结束时仍使用播放前取得的进度摘要。战绩类有独立测试，正常结算路径缺少记录调用。

**修复与验收。** 先明确产品要恢复对局还是只浏览事件，分别定义快照与事件契约。恢复版本应含显示名以外的稳定 ID、顺序、当前阶段及随机游标等可重建数据，只在明确的安全阶段持久化。接通正式对局动作和结束记录，采用原子写入和避免同秒覆盖的 ID。兼容旧 schema 的历史展示，保证一局确切续玩、整局事件回放相同结局，以及战绩只写一次。

## P2｜维护、质量与体验

### P2-01 · 单机、控制器、AI 和服务器维护多套回合与校验入口

**源码确认** · `game/game_controller.py:212`、`game/engine.py:206`、`game/turn_manager.py:89`、`ui/textual_ui/screens/game_play.py:211`、`net/server.py:510`。

PhaseFSM、ActionExecutor 和 EventBus 已存在，关键入口的接法并不统一。增加一条规则时需要在 TUI、headless 和 controller 多处比对，已经导致 P1-07 与 P1-11。先以公开案例固定各入口已有行为，再依次迁移真人 TUI、AI 与联机消费者，最后删除确认无调用的旧路径。验收应按相同的对局输入比较结构化阶段事件与状态。

### P2-02 · DSL 代价不是一次提交，失败回退可能继续改变状态

**源码确认** · `game/skill_interpreter.py:126`、`game/skill_interpreter.py:187`、`game/skill.py:129`。

解释器逐项支付代价再运行步骤。弃牌分支可把未实际移除的对象也写进弃牌堆，异常发生后 `SkillSystem` 会回退到 Python 实现，已发生的更改没有回滚。先解析并验证全部代价及目标，再提交一次。Python 兜底只在没有可用 DSL 实现时选择，已选中的实现失败应以明确错误收束。验收覆盖两项联合代价、执行拒绝、合规取消和牌守恒。

### P2-03 · 插件加载器、技能系统和扩展数据未接通

**源码确认** · `game/skill_plugin.py:55`、`game/skill_plugin.py:145`、`game/skill.py:43`、`game/engine.py:123`、`docs/architecture.md:119`。

正式 `SkillSystem` 直接加载内置 DSL，从项目内调用点看没有使用 `SkillPluginLoader` 的结果。`heroes_new.json` 仍是待合并数据。插件 `_meta` 在调用 `.get()` 前也没有检查对象形状，单个坏包可能打断后续文件的发现。接通一个明确的扩展配置入口，校验整份清单、依赖和冲突，并把插件的载入状态交给界面或日志。用实际开局验证已启用、冲突、坏插件和关闭插件四种情况。

### P2-04 · 困难 AI 的目标评估和身份推断未用于主要决策

**源码确认** · `ai/hard_strategy.py:154`、`ai/hard_strategy.py:233`、`ai/hard_strategy.py:311`、`ai/normal_strategy.py:75`、`ai/bot.py:120`、`ai/strategy.py:28`。

困难模式在危险时尝试回血，然后调用 `NormalStrategy.play_phase`。普通策略使用自己的目标选择，行为记录入口在正常对局没有对应调用点。困难模式的评估器因此不决定这部分选牌目标。规则和文档还需要明确 AI 能看见哪些身份，当前基础阵营判断直接读取引擎身份。给策略传入经过过滤的玩家视图，将困难评估接入正常出牌流程的一处决策点，并用固定种子和相同局面证明普通、困难两条路径实际存在可解释差异。

### P2-05 · 配置项存在但未在正式启动链生效

**源码确认** · `game/config.py:136`、`game/config.py:191`、`game/engine.py:469`、`game/engine.py:1124`、`game/turn_manager.py:165`。

`GameConfig.validate()` 没有在 `get_config()` 调用。玩家数量的配置范围与 headless 和网络边界的 2–8 不完全一致，初始手牌、基础摸牌数仍由规则代码硬编码，引擎 `max_actions` 参数没有下传。把可部署的参数在各启动入口验证一次，把产品规则常量与用户可配置项定清，并在行为测试中证明配置真的改变牌量、超时或连接限制。无法支持的开关应从文档与配置移除。

### P2-06 · 英文语言表齐全，但实际游戏界面混有中文且渲染依赖文案

**源码确认加静态检查** · `i18n/__init__.py:73`、`ui/textual_ui/screens/game_play.py:249`、`ui/textual_ui/screens/game_play.py:703`、`ui/textual_ui/modals/card_pick_modal.py:75`、`net/server.py:665`。

两份 JSON 各有 439 个键（含元数据），键集合与共有翻译的格式占位符一致。静态扫描到 325 个不同的直接翻译键，其中 `server.invalid_token` 在两个 JSON 均缺失。TUI 多处把中文直接拼进消息，对牌局动画和表现还按日志文本匹配分流，切换英文会影响显示一致性。用结构化事件驱动效果，再本地化展示。以 Pilot 验收英文开局、出牌、选目标、结算和错误消息，同时保留缺键与占位符检查。

### P2-07 · WebSocket 版本兼容范围未对应真实 API

**源码确认，待版本矩阵联验** · `pyproject.toml:15`、`requirements.txt:7`、`net/server.py:23`、`net/server.py:745`、`net/server.py:781`。

依赖允许 WebSocket 库从 12 起，服务器代码使用新 asyncio 连接形状，且从顶级 `serve` 取得实现。即使网络单元测试通过，也无法证明所有声明版本都提供相同的请求头、连接对象与关闭行为。显式采用所选 API 所属的导入路径，再以干净环境验证最低版本与当前支持上界。将发布依赖与兼容性矩阵分开，发布用可复现的已验证版本。

### P2-08 · 二进制发布没有检验架构、启动能力和完整资产

**源码确认，待三平台联验** · `build.py:28`、`.github/workflows/ci.yml` 的 Build EXE、`.github/workflows/release.yml` 的 Build 与 Create Release、`dist/`。

所有平台都硬编码 amd64 文件名，构建命令没有固定架构，发布步骤只是罗列文件，允许缺少匹配的 release assets。备份里的 Windows 可执行文件名为 3.5.0，而项目元数据为 4.0.0。使用显式架构矩阵，产物在同平台执行版本、帮助、启动与资源加载冒烟，检查预期文件名与架构并生成校验和。发布任务须验证三类预期资产与标签版本，再授权写入 Release。

### P2-09 · CI 测试与覆盖率存在交付视角的盲区

**源码确认** · `pyproject.toml:126`、`.github/workflows/ci.yml` 的 Test/Build/Import Check/Security Scan、`tests/test_net_server.py:187`、`tests/test_skills.py:771`、`README.md:269`。

覆盖策略排除了 GamePlayScreen、桥接层及多数弹窗和控件。许多网络测试直接调用处理器和模拟连接，无法发现启动、序列化、真实多人回合和断线恢复链的问题。CI 中的构建阶段上传分发包后缺少安装与运行验证。先补 clean-install 冒烟、真实客户端功能联验、TUI 规则路径测试和坏存档回归。用分模块覆盖与关键端到端结果说明验证范围，README 的数字使用同一份可重跑命令得出。

### P2-10 · 日志和存档路径分散，CLI 用户可能收不到状态反馈

**源码确认** · `main.py:82`、`net/client.py:308`、`logging_config.py`、`tools/log_config.py`、`game/save_system.py:188`。

主入口把控制台日志关闭后也用于联机客户端。客户端的连接、房间和错误主要经 logger 提示，用户终端反馈取决于选择的入口与日志处理器。两套日志配置和相对工作目录的存档路径还会让发布包在不同启动位置表现不一致。统一数据目录、轮转与日志来源，TUI 继续使用界面反馈，CLI 直接输出连接与操作结果。验收从任意目录启动，检查无权限目录时提示及日志、存档的实际落点。

### P2-11 · 安装要求、功能说明、许可和历史审查相互漂移

**源码确认** · `README.md:91`、`README.md:249`、`CHANGELOG.md:8`、`CONTRIBUTING.md:123`、`pyproject.toml:3`、外层 `problem_analysis_v5.md`。

README 宣称全异步引擎、联机重连、回放、战绩及插件都可用，代码已提供组件但交付路径存在上述缺口。CHANGELOG 最新段落停在 3.3.0。元数据声明 MIT，当前文件清单没有可分发的 LICENSE，仓库还缺失其跟踪的 `py.typed` 文件。发布前按确认能力更新文档，补许可文件并验证产物包含应发布的声明文件。两个历史报告中关于“完全没有 EventBus 异步支持、测试或 TLS”的表述应按现有实现改写为接入和验证缺口。

### P2-12 · 卡牌和武将数据存在多处规则来源

**源码确认** · `game/card.py:257`、`game/card.py:419`、`game/hero.py:291`、`game/effects/registry.py:42`、`data/skill_config.json`、`data/skill_dsl.json`。

卡牌数量在牌组数据和 `EXPECTED_CARD_COUNTS` 双写，部分技能横跨英雄配置、DSL、参数配置与 Python handler。加载器设计允许部分定义缺失或覆盖，错误能以对局中才遇到的行为差异出现。构建时产出数据引用图，检查牌种、效果、武将技能 ID 与处理器映射。牌组数量规则与数据如果有独立的产品验收价值可保留两套来源，并在 CI 明确比较两者。每个扩展武将和每种牌至少有一条可运行的接入场景。

### P2-13 · 回合事件与日志记录共用语义通道，订阅失败缺少明确处置

**源码确认** · `game/engine.py:274`、`game/engine.py:842`、`game/events.py:217`、`game/events.py:267`。

日志分类部分映射为语义事件，回合和伤害流程又自行发布结构化事件。现有 EventBus 有异步 API，但规则入口主要使用同步发布，普通订阅的返回和异常多数只写日志。某些订阅承担修改游戏状态的技能，和 UI 遥测订阅应采用不同失败约定。逐事件指定唯一发布点与强类型字段，区分可改变状态的规则步骤与可独立失败的观察器，测试每类触发只结算一次以及订阅异常后的对局状态。

### P2-14 · 二进制备份与受版本控制文件需要区分

**文件盘点确认** · 外层备份目录、仓库 `build/`、`dist/`、`coverage.xml`、`.gitignore`。

内层 Git 跟踪 198 条路径。排除生成文件与缓存后，审查副本包含 199 个当前文件。忽略行尾 CR 差异并单独排除旧 `coverage.xml` 后，`git diff` 只列出四个缺失的跟踪文件，其中包含 Python 类型标记和属性测试目录标记。Windows 旧二进制、覆盖率历史和测试缓存不能作为当前版本的通过证据。先明确哪些缺失文件属于正常的备份裁剪。发布和验证从干净、可追溯的检出版本生成，备份保留原样以便比对。

## 修复顺序与验收门槛

| 顺序 | 交付结果 | 可执行验收 |
|---|---|---|
| 1 | 构建和安装可重复，启动条件清楚 | 安装 wheel，确认入口、数据、样式和联机服务器导入。对发布二进制执行冒烟。维护一份运行依赖来源。 |
| 2 | 单机规则收敛 | 优先接通 TUI 的乐不思蜀、翻面、判定致死和人类技能。验证失败不改牌区，所有入口使用同一组规则回归。 |
| 3 | 联机最小竖切可玩 | 两个真实客户端完成确定性短局。每名玩家只收到授权视图，房主离开、超时、慢连接和断线恢复均有明确结果。 |
| 4 | 推出持久化和扩展功能 | 选择续玩与事件浏览的契约，验证历史兼容、整局复现、战绩入库及插件开关的真实入口。 |
| 5 | 多平台交付质量与文档对齐 | 三平台分别从发布资产启动，版本、架构、安装、资源和关键功能均与 README 声明一致。 |

## 覆盖和验证记录

- 运行与内容检查使用 macOS arm64 和 Python 3.12.14，操作位于临时副本。未改动内层源码、测试和构建配置。
- 运行了 `python -m pytest -o addopts='' -q --cov=game --cov=ai --cov=ui --cov=net --cov-report=term-missing`。1523 项通过，分支统计口径下的汇总覆盖率为 78.20%，其中 `net/server.py` 为 51%，`net/client.py` 为 40%，`game/skill_interpreter.py` 为 42%。测试环境额外提供 Pydantic 2.14.3，使用 pytest 9.2.0、Textual 8.2.8、WebSocket 库 17.4 和 coverage 7.17.5。
- Ruff 0.17.6 的 lint 检查有 1399 条诊断，格式检查有两个文件待格式化。依赖版本按审查环境实测记录。
- 所有 161 个 Python 文件及 2 个 PyInstaller spec 以 Python 3.10 语法模式解析。8 个 JSON 逐文件解析并排查重复键，`pyproject.toml` 由结构化 TOML 解析器读取。
- 定向阅读覆盖 CLI、AI、TUI 屏幕和模态框、引擎与规则、网络协议和安全、存档回放、i18n、依赖和两个发布工作流。测试、旧文档和数据用于交叉核对，逐文件语法盘点不代表逐行验证了所有规则组合。
- Setuptools 实测元数据阶段失败。单机最小运行确认了无目标出杀扣牌、翻面序列化错误、随机状态为全局以及 headless 动作日志为空。联机开局错误已在进程内确认，完整的双客户端对局仍待端到端验收。
- 使用 `debugging-and-error-recovery` 核查失败和最小场景，使用 `codex-security:security-scan` 核对输入、授权、身份可见性与部署边界。已调用 Codex Security 插件，工作台启动在 300 秒后超时，未返回可总结的插件扫描结果。本文的安全发现来自本地源码审阅。
- 生成缓存和 Git 内部对象按用途盘点。未运行备份中的 Windows 二进制，未验证线上部署、三平台发布结果、全部武将与卡牌交互或当前第三方依赖公告。
