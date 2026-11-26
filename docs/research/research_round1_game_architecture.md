# 第一轮研究：Python游戏引擎架构与卡牌游戏设计模式

## 研究时间
2026-02-19

## 研究范围
Python游戏引擎架构、卡牌游戏设计模式、ECS模式、有限状态机、数据驱动设计

---

## 1. 卡牌游戏架构核心组件

### 1.1 游戏架构七大功能角色（来源：Benny Cheung - RFTG系列）
- **(1) Game Story & Game Asset** — 卡牌设计数据 + 图像资源
- **(2) Game Model** — 数据模型（Deck, Player, GameResource）
- **(3) Game Engine** — 规则引擎，状态维护，合法性检查
- **(4) Game Interface** — 玩家交互，偏好设置，操作呈现
- **(5) Game AI** — AI决策逻辑
- **(6) Game Physics** — 仅物理类游戏需要
- **(7) Hardware Abstraction** — 平台适配

### 1.2 核心定义
> "Game Engine is just a real-time database with a pretty front end and definite rules."

**关键洞察**：游戏引擎本质上是一个状态追踪的信息系统，玩家（人类或AI）通过合法动作与之交互。

### 1.3 对本项目的映射分析
| 架构组件 | 本项目现状 | 问题 |
|---------|-----------|------|
| Game Model | game/models.py 存在 | 模型与引擎耦合 |
| Game Engine | game/engine.py (Facade) | 167行__init__，职责过重 |
| Game Interface | ui/ (Textual TUI) | 存在input()绕过UI抽象 |
| Game AI | ai/ (3-tier) | AI与人类玩家逻辑分裂 |
| Game Asset | data/ (YAML) | DSL系统不完整 |

---

## 2. MVC + Mediator模式（来源：pygame wiki - tut_design）

### 2.1 核心模式
- **MVC (Model-View-Controller)** 是图形游戏的自然选择
- **Mediator/EventManager** 实现多视图和多控制器的解耦
- EventManager允许动态添加/移除监听者，发布者无需知道监听者数量

### 2.2 事件处理顺序问题
pygame wiki明确指出了事件管理器的一个关键缺陷：
> 如果代码顺序生成事件A和B，监听者捕获A后生成C，简单的EventManager会按A,C,B顺序处理，而非期望的A,B,C。

**对本项目的意义**：
- 本项目EventBus（game/events.py）是同步的，50+事件类型
- 当事件处理器内部再次触发事件时，可能出现类似的顺序问题
- 需要考虑事件队列化而非递归调用

---

## 3. 有限状态机（FSM）在游戏中的应用

### 3.1 FSM适用场景（来源：gameprogrammingpatterns.com）
FSM在以下情况最有用：
- 实体行为基于内部状态变化
- 状态可以严格划分为有限个离散选项
- 实体响应一系列输入/事件

### 3.2 FSM的局限性
- FSM不是图灵完备的
- 没有历史记忆概念
- 对复杂AI，推荐行为树或规划系统
- 可用层级状态机(HSM)或下推自动机(PDA)扩展

### 3.3 Python FSM库
- **pytransitions/transitions** — 轻量级FSM，支持AsyncMachine
- **python-statemachine** — 声明式API，支持async/sync，StatechChart复合状态，守卫条件
- 两者都支持Observer模式和事件分发

### 3.4 对本项目的意义
- 游戏阶段（准备→判定→出牌→弃牌→结束）天然适合FSM
- 武将技能触发时机也可用FSM建模
- 当前项目的回合管理使用硬编码的方法调用链，缺乏状态机的形式化

---

## 4. 数据驱动游戏设计

### 4.1 核心原则（来源：gamedev.net、gamedevelopment.tutsplus）
- 对象由数据描述符初始化（XML/JSON/YAML/脚本）
- 初始化链贯穿所有子对象
- 对象通常由工厂创建（非直接实例化）
- 使用组合优于继承

### 4.2 卡牌游戏数据驱动（来源：RFTG案例）
- 卡牌设计存储在文本文件中（cards.txt）
- 每行一个命令，由单字符代码驱动
- 卡牌属性适用于游戏的多个阶段

### 4.3 DSL for Card Games
- **Haskell CardgameDSL** — 7种数据类型构建卡牌规则
- **Squib (Ruby)** — "Don't Repeat Yourself"原则的数据驱动卡牌原型
- DSL让游戏设计师而非程序员定义规则

### 4.4 对本项目的意义
- 本项目已有YAML数据定义 + DSL系统（game/skill.py）
- 但DSL不完整，Python fallback成为主要路径
- 技能使用硬编码到3个技能（P1-6）
- 需要完善DSL让所有技能可数据驱动定义

---

## 5. 卡牌游戏系统架构（来源：critpoints.net）

### 5.1 卡牌生命周期 = 软件对象生命周期
- 卡牌经历 创建→进场→状态变化→离场 的生命周期
- 触发条件是卡牌的"生命周期钩子"
- 类似React/Angular组件的 onMount, onChange, onDestroy

### 5.2 卡牌效果解析
- 需要维护卡牌数据库，支持按属性过滤
- 每张新卡需要检查与已有卡牌的交互
- Magic: The Gathering 允许在栈上反制其他法术
- 游戏王依赖时序链（连锁），需要响应特定事件

### 5.3 对本项目的意义
- 三国杀的技能触发时机系统 = 生命周期钩子系统
- 当前EventBus需要更精细的事件链管理
- 武圣/龙胆等转换技能的实现不应依赖player.is_ai检查

---

## 6. MTG Python Engine架构参考（来源：github/wanqizhu）

### 6.1 架构特点
- 每张卡牌生成独立的类（继承card.Card）
- 静态信息（法术力、力量、防御力）与动态能力分离
- 能力在卡牌成为永久物时才激活
- 非法操作通过Deepcopy回滚

### 6.2 对本项目的启发
- 卡牌类应该分离静态属性和动态效果
- 操作回滚机制对于复杂技能交互很重要
- 能力激活应该在正确的时机而非硬编码

---

## 研究结论

### 核心发现
1. **架构分层**：成熟的卡牌游戏引擎严格分离 Model/Engine/Interface/AI
2. **事件系统**：需要队列化事件处理，避免递归调用导致的顺序问题
3. **状态机**：游戏阶段和技能触发应使用FSM形式化
4. **数据驱动**：卡牌和技能应完全由数据定义，非硬编码
5. **生命周期**：卡牌效果系统应基于生命周期钩子

### 映射到本项目的关键改进方向
- engine.py 的 Facade 过于臃肿，应拆分为独立的规则引擎和状态管理
- EventBus 需要从同步改为队列化异步
- 技能系统的 DSL 需要完善到覆盖所有技能
- AI 和人类玩家的交互路径应统一
