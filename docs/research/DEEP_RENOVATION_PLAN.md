# 三国杀命令行版 深度焕新可执行计划

## 一、项目现状全面诊断

### 1.1 项目概况
本项目是一款 Python 命令行终端版三国杀卡牌游戏（v1.3.0），位于 `sanguosha_backup_20260121_071454/`。支持2-8人身份局，包含20+武将、完整的卡牌系统（标准+军争）、3级AI难度、事件总线和动作系统。另有一个仅完成主菜单壳的 Textual TUI v2 原型 (`sanguosha_v2/`)。

### 1.2 运行机理分析
**启动流程**: `main.py` → `SanguoshaGame` → 主菜单循环 → 选人数/难度 → `GameEngine.setup_game()` 分配身份 → 选将 → `start_game()` 发牌 → `_game_loop()` 回合循环
**回合流程**: 准备→判定（延时锦囊）→摸牌→出牌→弃牌→结束，每阶段由 `engine.py` 中对应 `phase_*()` 方法驱动
**卡牌机制**: `Deck` 从 `cards.json` 加载，使用时通过 `_card_handlers` 字典路由到具体处理方法（如 `_use_sha`, `_use_juedou` 等），结果经 `DamageSystem` 处理伤害/濒死/死亡/铁索传导
**技能机制**: `SkillSystem` 维护 `_skill_handlers` 映射表，每个技能是一个硬编码的 Python 方法，武将数据从 `heroes.json` 加载
**AI决策**: `AIBot` 根据难度执行不同策略：简单=随机，普通=优先级出牌，困难=嘲讽值+局势评估+身份推断
**UI层**: `RichTerminalUI`(默认) 或 `TerminalUI` 负责渲染和交互，通过 `engine.ui` 引用双向通信
**事件系统**: `EventBus` 实现观察者模式（有40+事件类型定义），但实际只用于日志转发，未深度集成

### 1.3 核心问题诊断

**P0 - 架构级（阻碍扩展）**
- `engine.py` (83KB/2000+行) 是上帝对象，聚合了回合管理、卡牌处理、伤害系统、请求系统、无懈可击逻辑等全部职责
- `main.py` 中 `_handle_play_specific_card()` 包含大量卡牌使用逻辑，本应由引擎统一处理
- 技能系统全部硬编码，新增武将需修改 `skill.py` 源码
- 事件总线和动作系统虽已定义但几乎未被使用，架构重构一半

**P1 - 设计级（影响质量）**
- 卡牌效果处理器散落在 `engine.py` 和 `card_handlers.py` 中，无统一抽象
- UI 和游戏逻辑耦合严重（`engine` 直接调用 `self.ui.show_log`, `self.ui.ask_for_shan` 等）
- `damage_system.py` 已解耦但 `engine.py` 仍有部分 `deal_damage` 逻辑
- `constants.py` 定义了枚举但多数模块仍用硬编码字符串比较

**P2 - 功能级（影响体验）**
- 无存档/读档功能
- 无网络对战能力
- v2 Textual TUI 仅完成菜单壳，未对接游戏引擎
- 无完善的观战/回放系统（虽有 `tools/replay.py` 但功能简陋）
- 部分武将技能实现不完整或有 bug

## 二、焕新目标与原则

### 2.1 目标
将项目从「单文件可运行的原型」演进为「模块化、数据驱动、可扩展的终端桌游引擎」，具备：
- 清晰的分层架构（数据层/逻辑层/表现层完全分离）
- 数据驱动的技能和卡牌系统（JSON/YAML配置即可新增内容）
- 现代 TUI 交互体验（基于 Textual 框架）
- 网络对战基础能力
- 完善的测试覆盖和CI/CD

### 2.2 原则
- **渐进式重构**：每个里程碑都产出可运行版本，不做大爆炸重写
- **向后兼容**：保留 v1 作为 fallback，v2 逐步接管
- **测试驱动**：每个重构步骤先写测试再改代码
- **数据与代码分离**：规则、武将、卡牌效果尽量配置化

## 三、焕新路线图（4个里程碑）

### M1: 引擎解耦与核心重构 (预估 3-4 周)

**目标**: 将上帝类 `GameEngine` 拆分为职责单一的模块

**M1-T01: 回合管理器拆分**
- 从 `engine.py` 提取 `TurnManager` 类（已有 `turn_manager.py` 文件但未使用）
- 职责：回合流转、阶段推进、跳过判定
- 将 `phase_prepare/judge/draw/play/discard/end` 和 `next_turn/run_turn` 移入
- 验收：现有测试全部通过

**M1-T02: 卡牌效果处理器抽象**
- 定义 `CardEffect` 抽象基类（target_type, can_use, resolve 方法）
- 为每种牌创建独立的 Effect 类：`ShaEffect`, `TaoEffect`, `JuedouEffect` 等
- 引入 `CardEffectRegistry` 注册表，按卡牌名称自动路由
- 将 `engine.py` 中的 `_use_sha/_use_juedou/...` 全部迁移
- 验收：所有卡牌效果测试通过，engine.py 减少 40%+ 代码

**M1-T03: 请求-响应系统全面接入**
- 完善 `actions.py` 中的 `GameRequest/GameResponse` 体系
- 引擎所有需要玩家输入的场景（出闪/出杀/出桃/弃牌/选目标）统一走请求系统
- AI 和 UI 都通过同一个 `RequestHandler` 接口响应
- 删除 `engine.py` 中直接调用 `self.ui.ask_for_*` 的代码
- 验收：UI 层不再直接被引擎调用，全部通过请求系统

**M1-T04: 事件总线深度集成**
- 将所有 `log_event()` 调用替换为语义化事件发布
- UI 订阅事件进行渲染（不再由引擎 push）
- 技能系统监听事件触发被动技（如奸雄、反馈、刚烈等受伤后触发的技能）
- 验收：事件驱动的技能触发正确，引擎不直接调用 UI

**M1-T05: 使用 constants.py 统一消灭魔法字符串**
- 将代码中所有 `"杀"`, `"闪"`, `"heart"`, `"paoxiao"` 等硬编码替换为 `CardName.SHA`, `CardSuit.HEART`, `SkillId.PAOXIAO`
- 验收：grep 不到裸字符串比较

### M2: 数据驱动技能系统 (预估 3-4 周)

**目标**: 技能系统从硬编码转为配置驱动

**M2-T01: 技能 DSL 设计**
- 设计技能描述 YAML/JSON schema，支持以下原子操作：
  - `draw` (摸牌), `discard` (弃牌), `damage` (造成伤害)
  - `heal` (回复体力), `transfer` (转移牌), `convert` (转化牌)
  - `judge` (判定), `target_select` (选择目标)
- 复杂技能支持 `condition → action` 链
- 示例：仁德 = `{trigger: "active", phase: "play", limit: 1, steps: [{select_cards: {from: "hand", min: 1}}, {select_target: {filter: "other"}}, {transfer: {cards: "selected", to: "target.hand"}}, {if: {total_given >= 2}, then: {heal: 1}}]}`

**M2-T02: 技能解释器引擎**
- 实现 `SkillInterpreter` 类，读取技能 DSL 并执行
- 保留 Python handler 作为 fallback（复杂技能如观星仍用代码）
- 混合模式：DSL 技能 + Python 扩展技能共存
- 验收：至少 15 个技能迁移到 DSL，行为与原实现一致

**M2-T03: 武将和技能数据外部化**
- 将 `heroes.json` 中的技能描述从纯文本升级为可执行 DSL
- 新增武将只需编辑 JSON/YAML 文件，无需修改 Python 代码
- 添加数据验证器（schema validation）
- 验收：新增一个测试武将仅通过数据文件完成

**M2-T04: 卡牌效果配置化**
- 将简单卡牌效果（桃、无中生有、桃园结义等）迁移到数据配置
- 复杂卡牌（杀、决斗等需要交互的）保留代码实现
- 验收：新增简单锦囊牌只需编辑配置文件

### M3: 现代 TUI 与用户体验 (预估 3-4 周)

**目标**: 用 Textual 框架重写交互界面，完成 v2 TUI

**M3-T01: Textual 应用框架搭建**
- 在 `sanguosha_v2/` 中搭建完整的 Textual App 结构
- 实现 Screen 切换：MainMenu → GameSetup → GamePlay → GameOver
- 复用 v1 的 `game/` 引擎模块作为后端
- 验收：可通过 Textual TUI 启动到选将界面

**M3-T02: 游戏主界面布局**
- 上区：对手信息面板（体力/手牌数/装备/身份/连环状态）
- 中区：战场日志（滚动实时事件流）
- 下区：玩家自己的手牌区（可点击选择）、装备区、技能按钮
- 底部：操作栏（出牌/技能/结束/帮助）
- 验收：界面渲染正确，响应键盘和鼠标操作

**M3-T03: 交互流程对接**
- 将 M1 的请求-响应系统与 Textual 的事件循环对接
- 引擎发出 `GameRequest` → Textual 弹出对话框/选择面板
- 玩家操作产生 `GameResponse` → 返回引擎继续执行
- AI 回合异步执行，不阻塞 UI
- 验收：完整一局游戏可通过 Textual TUI 完成

**M3-T04: 动画与视觉效果**
- 出牌/受伤/治疗/死亡 使用 Textual 动画 API
- 卡牌使用时短暂高亮显示
- 伤害数字浮动效果
- 验收：关键动作有视觉反馈

**M3-T05: Rich UI 保留与适配**
- 保留 `ui/rich_ui.py` 作为轻量级备选 UI
- 统一 UI 接口 `GameUI(Protocol)`，Textual 和 Rich 均实现
- 启动参数选择 UI 模式：`--ui textual` / `--ui rich` / `--ui plain`
- 验收：三种 UI 模式均可运行

### M4: 网络对战与工程质量 (预估 4-5 周)

**目标**: 支持局域网对战，完善工程体系

**M4-T01: 网络协议设计**
- 基于 WebSocket 的 C/S 架构
- 服务端：运行 GameEngine，广播事件
- 客户端：运行 UI，发送 GameAction
- 协议格式：JSON 消息（兼容 action_log 回放格式）
- 验收：协议文档完成，消息格式测试通过

**M4-T02: 服务端实现**
- 基于 `asyncio` + `websockets` 库
- 房间管理：创建/加入/开始
- 游戏状态同步：增量事件广播
- 断线重连：基于 action_log 重放
- 验收：2个客户端可连接并完成一局

**M4-T03: 客户端适配**
- Textual TUI 客户端：接入 WebSocket
- 命令行客户端：简化版
- 验收：网络对战功能端到端通过

**M4-T04: 测试体系完善**
- 目标覆盖率 ≥ 80%
- 新增：集成测试（完整游戏流程）、性能测试（1000局压力）、模糊测试（随机操作序列）
- 每个卡牌效果至少2个测试用例
- 每个技能至少3个测试用例（正常/边界/交互）
- 验收：CI 全绿，覆盖率达标

**M4-T05: CI/CD 与发布流程**
- GitHub Actions：lint(ruff) → typecheck(mypy) → test(pytest) → build(PyInstaller)
- 版本号自动管理（基于 git tag）
- 自动构建 Windows exe 和 PyPI 包
- 变更日志自动生成
- 验收：push main 自动触发完整流水线

**M4-T06: 存档与回放系统**
- 基于 `action_log` 实现存档：序列化完整游戏状态 + 动作历史
- 读档：从存档恢复游戏状态
- 完善 `tools/replay.py`：支持单步前进/后退、变速播放
- 验收：存档→退出→读档→继续游戏 全流程通过

## 四、目录结构目标

```
sanguosha/
├── pyproject.toml
├── README.md
├── src/sanguosha/
│   ├── __init__.py
│   ├── app.py                    # Textual TUI 入口
│   ├── cli.py                    # CLI 入口 (argparse)
│   ├── core/                     # 核心引擎（零 UI 依赖）
│   │   ├── engine.py             # 精简的游戏引擎（状态管理+规则调度）
│   │   ├── turn_manager.py       # 回合管理器
│   │   ├── card.py               # 卡牌数据模型
│   │   ├── hero.py               # 武将数据模型
│   │   ├── player.py             # 玩家数据模型
│   │   ├── skill_interpreter.py  # 技能 DSL 解释器
│   │   ├── damage_system.py      # 伤害系统
│   │   ├── win_checker.py        # 胜负判定
│   │   ├── events.py             # 事件总线
│   │   ├── actions.py            # 动作/请求/响应
│   │   └── constants.py          # 所有枚举和常量
│   ├── effects/                  # 卡牌效果处理器
│   │   ├── base.py               # CardEffect 抽象基类
│   │   ├── basic.py              # 杀/闪/桃/酒
│   │   ├── trick.py              # 锦囊牌效果
│   │   ├── equipment.py          # 装备效果
│   │   └── registry.py           # 效果注册表
│   ├── skills/                   # 技能处理器（代码级 fallback）
│   │   ├── shu.py                # 蜀国技能
│   │   ├── wei.py                # 魏国技能
│   │   ├── wu.py                 # 吴国技能
│   │   └── qun.py                # 群雄技能
│   ├── ai/                       # AI 模块
│   │   ├── bot.py                # AI 基类
│   │   ├── strategies.py         # 策略模式
│   │   └── evaluator.py          # 局势评估器
│   ├── ui/                       # UI 模块
│   │   ├── protocol.py           # UI 接口协议 (Protocol)
│   │   ├── textual_ui/           # Textual TUI
│   │   ├── rich_ui.py            # Rich 轻量 UI
│   │   └── plain_ui.py           # 纯文本 UI
│   ├── net/                      # 网络模块
│   │   ├── server.py             # WebSocket 服务端
│   │   ├── client.py             # WebSocket 客户端
│   │   └── protocol.py           # 网络协议定义
│   └── data/                     # 数据文件
│       ├── cards.yaml             # 卡牌数据（含效果配置）
│       ├── heroes.yaml            # 武将数据（含技能 DSL）
│       └── schemas/               # 数据验证 schema
├── tests/
│   ├── unit/
│   ├── integration/
│   └── stress/
└── tools/
    ├── replay.py
    └── balance_analyzer.py        # 平衡性分析工具
```

## 五、风险与缓解
- **风险1: 引擎重构导致回归 bug** → 缓解: M1 每步先跑全量测试，保持 v1 可回退
- **风险2: 数据驱动技能表达力不足** → 缓解: 混合模式，复杂技能保留 Python 实现
- **风险3: Textual 框架限制** → 缓解: 保留 Rich UI 作为备选
- **风险4: 网络同步复杂度** → 缓解: 先完成单机重构再上网络

## 六、优先级排序
**必做 (M1+M2)**: 引擎解耦 + 数据驱动技能 → 这是所有后续工作的基础
**应做 (M3)**: Textual TUI → 显著提升用户体验
**可做 (M4)**: 网络对战 + 完善工程体系 → 锦上添花

建议按 M1 → M2 → M3 → M4 顺序推进，每个里程碑结束时发布一个可运行版本。
