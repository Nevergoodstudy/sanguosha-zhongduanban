# 第二轮研究：异步网络安全、Textual TUI测试与网络游戏同步

## 研究时间
2026-02-19

## 研究范围
asyncio WebSocket安全最佳实践、Textual TUI测试框架、网络游戏状态同步、Python异步模式

---

## 1. WebSocket安全最佳实践

### 1.1 核心安全要求（来源：websocket.org、websockets官方文档）
1. **Origin验证** — 防止跨站WebSocket劫持(CSWSH)，必须在握手阶段验证Origin头
2. **WSS加密** — 生产环境必须使用WSS(TLS)加密所有通信
3. **消息验证** — 验证所有传入消息，实施速率限制防止滥用
4. **消息大小限制** — 防止内存耗尽攻击
5. **认证机制** — websockets库原生支持HTTP Basic Auth (RFC 7235/7617)

### 1.2 对本项目的关键安全问题
**P0-4: Origin验证默认禁用**
- `net/security.py` line 158: `OriginValidator` 默认允许所有来源
- 这是一个严重的安全漏洞，任何来源都可以建立WebSocket连接
- **修复**：默认应拒绝所有，显式配置允许列表

**缺失的安全措施**：
- 无TLS/WSS支持
- 无消息大小限制配置
- Token管理存在但安全性需要审计
- 无针对重放攻击的防护

### 1.3 websockets库最佳实践（来源：websockets v16.0文档）
- 使用`serve()`参数：`origins`控制允许的来源
- `max_size=1048576`（默认1MB）限制消息大小
- `ping_interval=20, ping_timeout=20` 心跳检测
- `close_timeout=10` 关闭超时
- 使用`process_request`钩子自定义认证逻辑
- `basic_auth()`工厂函数实现HTTP基本认证

---

## 2. asyncio与WebSocket游戏服务器

### 2.1 asyncio并发模型优势（来源：websocket.org guide）
- asyncio事件循环高度优化I/O密集操作
- 单进程可处理数千并发WebSocket连接
- 对于多数应用，开发效率和可维护性优势远大于性能差异

### 2.2 游戏状态同步模式（来源：websockets官方教程）
标准模式：
```
客户端发送事件 → 服务器处理 → 更新应用状态 → 同步到所有客户端
```
- asyncio的并发模型保证更新的序列化
- 使用broadcast()分发状态到所有连接
- 连接/断开事件需要通知其他客户端

### 2.3 对本项目的意义
- `net/server.py` 中GameServer的engine引用从未初始化（P1-2）
- 服务器有room管理shell但缺少完整的游戏逻辑集成
- 需要实现完整的状态同步协议
- 需要断线重连和状态恢复机制

---

## 3. Textual TUI测试

### 3.1 Textual Pilot API（来源：textual.textualize.io/guide/testing）
- `App.run_test()` 返回`Pilot`对象用于程序化操作
- 支持模拟操作：`click()`, `press()`, `hover()`
- 支持CSS选择器定位Widget
- 异步测试框架：需要pytest + pytest-asyncio
- 每个async测试需要`@pytest.mark.asyncio`装饰器

### 3.2 快照测试（来源：pytest-textual-snapshot）
- 生成SVG截图进行视觉回归测试
- `snap_compare`夹具注入
- 支持模拟按键操作后截图
- 支持`run_before`参数在截图前执行自定义代码
- 首次运行总会失败（无历史对比基准）
- `--snapshot-update`标志保存新基准

### 3.3 TUI测试策略（来源：blog.waleedkhan.name）
两大类测试方法：
1. **集成测试** — 钩入应用事件循环注入合成事件
   - 更直接，更少flaky
   - 可在用户级别或应用级别输入
2. **端到端测试** — 通过PTY与实际终端交互
   - 更广泛的覆盖
   - 但更脆弱

**关键洞察**：
- 结构化TUI应用为事件驱动对测试至关重要
- 用户级输入更完整测试界面但更脆弱
- 应用级输入更稳定但测试覆盖较窄

### 3.4 对本项目的意义
- 项目使用Textual TUI（6个Screen + 5+模态框 + 多Widget）
- 当前测试1256个，75.71%覆盖率，但TUI测试覆盖不明
- **P0-1**: `time.sleep()` 阻塞Textual事件循环
- **P0-2**: `input()` 绕过UI抽象
- 需要为所有TUI交互添加Pilot测试
- 需要添加快照测试防止视觉回归

---

## 4. Python异步模式最佳实践

### 4.1 避免阻塞事件循环
- `time.sleep()` 在asyncio上下文中是致命的（本项目P0-1）
- 应使用 `asyncio.sleep()` 或 Textual 的 `set_timer()`
- `input()` 是阻塞调用，不能在async上下文使用（本项目P0-2）
- 应使用Textual的Input Widget

### 4.2 异步事件处理
- python-statemachine 支持 AsyncMachine
- pytransitions 支持异步回调
- 可以混用同步和异步回调，但可能有副作用
- 异步事件需要被await，事件循环由开发者管理

### 4.3 连接管理
- WebSocket连接可以是长期存活的
- 需要心跳检测断线
- `connect()`可用作无限异步迭代器自动重连
- process_exception区分可重试和致命错误

---

## 5. 网络多人游戏状态同步

### 5.1 同步架构选项
- **权威服务器** — 服务器是唯一真相来源
- **客户端预测** — 客户端预测执行，服务器验证修正
- **锁步同步** — 所有客户端在同一帧执行同一输入

### 5.2 对三国杀类回合制游戏
- 回合制游戏最适合权威服务器模式
- 每个玩家动作发送到服务器验证
- 服务器计算结果后广播给所有客户端
- 不需要客户端预测（回合制无延迟敏感性）

### 5.3 断线重连
- FreeKill（开源三国杀）已实现断线重连和录像回放
- 需要：完整的游戏状态快照能力
- 需要：操作日志可重放能力
- 本项目P1-4: 无重连回放机制

---

## 研究结论

### 核心发现
1. **安全优先**：Origin验证、TLS、消息限制、速率限制缺一不可
2. **异步一致**：整个项目必须统一到asyncio，消除所有阻塞调用
3. **测试工具完善**：Textual Pilot + 快照测试可提供强大的TUI测试能力
4. **权威服务器**：回合制卡牌游戏应使用权威服务器架构
5. **断线重连**：是网络游戏的基本要求，需要状态快照+操作日志

### 映射到本项目的关键改进方向
- 修复所有安全漏洞（Origin验证、TLS支持）
- 消除time.sleep()和input()
- 添加Textual Pilot测试和快照测试
- 实现权威服务器架构
- 实现断线重连机制
