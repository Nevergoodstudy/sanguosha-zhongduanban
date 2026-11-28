"""WebSocket 游戏客户端 (M4-T03)

功能:
- 连接服务端
- 房间管理 (创建/加入/准备/开始)
- 接收游戏事件并驱动 UI 更新
- 发送玩家操作
- 断线自动重连
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

from .protocol import ClientMsg, MsgType, ServerMsg

logger = logging.getLogger(__name__)


class GameClient:
    """三国杀 WebSocket 客户端

    职责:
    1. 维护与服务端的 WebSocket 连接
    2. 收发消息
    3. 通过回调函数将事件通知上层 (UI)
    4. 断线自动重连
    """

    def __init__(self, server_url: str = "ws://localhost:8765"):
        self.server_url = server_url
        self.player_id: int = 0
        self.player_name: str = ""
        self.room_id: str | None = None
        self.last_seq: int = 0  # 最后收到的事件序号
        self.auth_token: str = ""  # 服务端签发的连接令牌
        self.request_id: int = 0

        # WebSocket 连接
        self._ws: ClientConnection | None = None
        self._connected: bool = False
        self._running: bool = False

        # 事件回调
        self._handlers: dict[MsgType, Callable] = {}
        self._on_connect: Callable | None = None
        self._on_disconnect: Callable | None = None

        # 重连配置
        self.auto_reconnect: bool = True
        self.reconnect_delay: float = 2.0
        self.max_reconnect_attempts: int = 5

        # 心跳
        self._heartbeat_interval: float = 15.0

    # ==================== 事件回调注册 ====================

    def on(self, msg_type: MsgType, handler: Callable) -> None:
        """注册消息处理回调"""
        self._handlers[msg_type] = handler

    def on_connect(self, handler: Callable) -> None:
        """注册连接成功回调"""
        self._on_connect = handler

    def on_disconnect(self, handler: Callable) -> None:
        """注册断连回调"""
        self._on_disconnect = handler

    # ==================== 连接管理 ====================

    async def connect(self) -> bool:
        """连接到服务端"""
        try:
            import websockets

            self._ws = await websockets.connect(self.server_url)
            self._connected = True
            logger.info(f"已连接到 {self.server_url}")
            if self._on_connect:
                await self._on_connect()
            return True
        except ImportError:
            logger.error("需要安装 websockets: pip install websockets")
            return False
        except Exception as e:
            logger.error(f"连接失败: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        self._running = False
        self._connected = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.info("已断开连接")
        if self._on_disconnect:
            await self._on_disconnect()

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ws is not None

    # ==================== 消息收发 ====================

    async def send(self, msg: ClientMsg) -> bool:
        """发送消息"""
        if not self.is_connected:
            logger.warning("未连接，无法发送消息")
            return False
        try:
            await self._ws.send(msg.to_json())
            return True
        except Exception as e:
            logger.warning(f"发送失败: {e}")
            self._connected = False
            return False

    async def _receive_loop(self) -> None:
        """消息接收循环"""
        try:
            async for raw in self._ws:
                await self._dispatch(raw)
        except Exception as e:
            logger.warning(f"接收循环中断: {e}")
        finally:
            self._connected = False

    async def _dispatch(self, raw: str) -> None:
        """分发收到的消息"""
        try:
            msg = ServerMsg.from_json(raw)

            # 更新事件序号
            if msg.seq > 0:
                self.last_seq = msg.seq

            # 提取服务端签发的令牌 (欢迎消息)
            if msg.type == MsgType.HEARTBEAT_ACK and "token" in msg.data:
                self.auth_token = msg.data["token"]
                pid = msg.data.get("player_id", 0)
                if pid:
                    self.player_id = pid

            if msg.type in {MsgType.ROOM_JOINED, MsgType.ROOM_CREATED}:
                self.room_id = msg.data["room_id"]
                if msg.type == MsgType.ROOM_JOINED:
                    self.player_id = msg.data["player_id"]
                if "token" in msg.data:
                    self.auth_token = msg.data["token"]
            if msg.type == MsgType.ROOM_LEFT:
                self.room_id = None
            if msg.type == MsgType.GAME_REQUEST:
                self.request_id = msg.data["request_id"]
            if msg.type == MsgType.GAME_OVER:
                self.request_id = 0

            # 调用注册的回调
            handler = self._handlers.get(msg.type)
            if handler:
                if asyncio.iscoroutinefunction(handler):
                    await handler(msg)
                else:
                    handler(msg)
            else:
                logger.debug(f"未处理的消息类型: {msg.type.value}")

        except Exception as e:
            logger.warning(f"消息分发异常: {e}")

    # ==================== 心跳 ====================

    async def _heartbeat_loop(self) -> None:
        """心跳循环"""
        while self._running and self.is_connected:
            await asyncio.sleep(self._heartbeat_interval)
            if self.is_connected:
                await self.send(ClientMsg.heartbeat(self.player_id))

    # ==================== 重连 ====================

    async def _reconnect(self) -> bool:
        """尝试重连 (携带令牌用于身份验证)"""
        token = self.auth_token
        for attempt in range(1, self.max_reconnect_attempts + 1):
            logger.info(f"重连尝试 {attempt}/{self.max_reconnect_attempts}...")
            await asyncio.sleep(self.reconnect_delay * attempt)

            if not self._running:
                return False
            if await self.connect():
                # 重连后请求重放缺失的事件 (携带令牌)
                if self.room_id:
                    await self.send(
                        ClientMsg(
                            type=MsgType.ROOM_JOIN,
                            player_id=self.player_id,
                            data={
                                "room_id": self.room_id,
                                "reconnect": True,
                                "last_seq": self.last_seq,
                                "token": token,
                            },
                        )
                    )
                return True

        logger.error("重连失败，已达最大尝试次数")
        return False

    # ==================== 主循环 ====================

    async def run(self) -> None:
        """客户端主循环"""
        if not self.is_connected and not await self.connect():
            return

        self._running = True

        try:
            while self._running:
                heartbeat = asyncio.create_task(self._heartbeat_loop())
                try:
                    await self._receive_loop()
                finally:
                    heartbeat.cancel()
                    await asyncio.gather(heartbeat, return_exceptions=True)
                if not self._running or not self.auto_reconnect or not await self._reconnect():
                    break
        finally:
            await self.disconnect()

    # ==================== 便捷操作方法 ====================

    async def create_room(
        self, player_name: str, max_players: int = 4, ai_fill: bool = True
    ) -> None:
        """创建房间"""
        self.player_name = player_name
        await self.send(ClientMsg.room_create(self.player_id, player_name, max_players, ai_fill))

    async def join_room(self, player_name: str, room_id: str) -> None:
        """加入房间"""
        self.player_name = player_name
        await self.send(ClientMsg.room_join(self.player_id, player_name, room_id))

    async def leave_room(self) -> None:
        """离开房间"""
        await self.send(ClientMsg.room_leave(self.player_id))
        self.room_id = None

    async def set_ready(self, ready: bool = True) -> None:
        """设置准备状态"""
        await self.send(ClientMsg.room_ready(self.player_id, ready))

    async def start_game(self) -> None:
        """开始游戏 (房主)"""
        await self.send(ClientMsg.room_start(self.player_id))

    async def list_rooms(self) -> None:
        """获取房间列表"""
        await self.send(ClientMsg.room_list())

    async def play_card(self, card_id: int, target_ids: list[int] = None) -> None:
        """出牌"""
        await self.send(
            ClientMsg.game_action(
                self.player_id,
                "play_card",
                {"request_id": self.request_id, "card_id": card_id, "target_ids": target_ids or []},
            )
        )

    async def use_skill(
        self,
        skill_id: str,
        target_ids: list[int] | None = None,
        card_ids: list[int] | None = None,
    ) -> None:
        """使用技能"""
        await self.send(
            ClientMsg.game_action(
                self.player_id,
                "use_skill",
                {
                    "request_id": self.request_id,
                    "skill_id": skill_id,
                    "target_ids": target_ids or [],
                    "card_ids": card_ids or [],
                },
            )
        )

    async def end_turn(self) -> None:
        """结束回合"""
        await self.send(
            ClientMsg.game_action(self.player_id, "end_turn", {"request_id": self.request_id})
        )

    async def discard(self, card_ids: list[int]) -> None:
        """提交弃牌选项。"""
        await self.send(
            ClientMsg.game_action(
                self.player_id, "discard", {"request_id": self.request_id, "card_ids": card_ids}
            )
        )

    async def respond(self, request_type: str, accepted: bool, card_id: int = None) -> None:
        """响应请求"""
        data = {"request_id": self.request_id, "card_id": card_id}
        await self.send(ClientMsg.game_response(self.player_id, request_type, accepted, data))

    async def choose_hero(self, hero_id: str) -> None:
        """选择武将"""
        msg = ClientMsg.hero_chosen(self.player_id, hero_id)
        msg.data["request_id"] = self.request_id
        await self.send(msg)

    async def chat(self, message: str) -> None:
        """发送聊天"""
        await self.send(ClientMsg.chat(self.player_id, message))


# ==================== CLI 客户端 ====================


async def cli_client_main(server_url: str, player_name: str):
    """Run the interactive LAN client."""
    client = GameClient(server_url)
    client.player_name = player_name
    current = None

    def show_request(msg: ServerMsg):
        nonlocal current
        current = msg
        request_type = msg.data["request_type"]
        options = msg.data["options"]
        if request_type == "choose_hero":
            print(
                "选将",
                " / ".join(f"{hero['id']} {hero['name']}" for hero in options["heroes"]),
                flush=True,
            )
            return
        print(
            request_type,
            " / ".join(f"{card['id']} {card['display']}" for card in options["cards"]),
            flush=True,
        )
        if request_type == "play":
            print(
                "目标",
                " / ".join(f"{seat['id']} {seat['name']}" for seat in options["targets"]),
                flush=True,
            )
            if options["skills"]:
                print("可用技能", " / ".join(options["skills"]), flush=True)
        if request_type == "discard":
            print(f"请选择 {options['count']} 张弃牌", flush=True)

    def show_state(msg: ServerMsg):
        data = msg.data
        print(f"第 {data['round']} 轮 · {data['phase']} · 你的身份 {data['identity']}")
        for seat in data["players"]:
            status = f"{seat['hp']}/{seat['max_hp']} 体力" if seat["alive"] else "阵亡"
            print(
                f"  {seat['id']} {seat['name']} · {seat['hero']} · {status} · {seat['hand_count']} 手牌"
            )
        print(
            "你的手牌",
            " / ".join(f"{card['id']} {card['display']}" for card in data["hand"]),
            flush=True,
        )

    client.on(MsgType.GAME_REQUEST, show_request)
    client.on(MsgType.GAME_STATE, show_state)
    for kind in (MsgType.ROOM_CREATED, MsgType.ROOM_JOINED):
        client.on(kind, lambda msg: print(f"房间 {msg.data['room_id']}", flush=True))
    client.on(
        MsgType.ROOM_UPDATE,
        lambda msg: print(
            "房间玩家",
            " / ".join(
                f"{p['name']} ({'已准备' if p['ready'] else '未准备'})" for p in msg.data["players"]
            ),
            flush=True,
        ),
    )
    client.on(
        MsgType.GAME_OVER,
        lambda msg: print(f"对局结束 · {msg.data['winner']} · {msg.data['reason']}", flush=True),
    )
    client.on(MsgType.ERROR, lambda msg: print(msg.data["message"], flush=True))
    if not await client.connect():
        print("连接失败，请检查服务器地址。", flush=True)
        return

    reader = None
    input_transport = None
    if sys.platform != "win32":
        reader = asyncio.StreamReader()
        input_transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), sys.stdin
        )
    connection = asyncio.create_task(client.run())
    print(
        "create [人数] / join 房间号 / ready / start / hero 武将ID / "
        "play 手牌号 [目标号…] / skill 技能ID [目标号…] [--cards 牌号…] / end / "
        "discard 牌号… / respond [牌号] / quit",
        flush=True,
    )
    try:
        while True:
            line = (await reader.readline()).decode() if reader is not None else await asyncio.to_thread(
                sys.stdin.readline
            )
            if not line:
                break
            command, *arguments = line.split() or [""]
            if command == "quit":
                break
            try:
                if command == "create":
                    await client.create_room(player_name, int(arguments[0]) if arguments else 2)
                elif command == "join":
                    await client.join_room(player_name, arguments[0])
                elif command == "ready":
                    await client.set_ready()
                elif command == "start":
                    await client.start_game()
                elif command == "hero":
                    await client.choose_hero(arguments[0])
                elif command == "play":
                    await client.play_card(int(arguments[0]), list(map(int, arguments[1:])))
                elif command == "skill":
                    options = " ".join(arguments[1:])
                    targets, _, cards = options.partition("--cards")
                    await client.use_skill(
                        arguments[0], list(map(int, targets.split())), list(map(int, cards.split()))
                    )
                elif command == "end":
                    await client.end_turn()
                elif command == "discard":
                    await client.discard(list(map(int, arguments)))
                elif command == "respond" and current is not None:
                    kind = current.data["request_type"]
                    await client.respond(
                        kind, bool(arguments), int(arguments[0]) if arguments else None
                    )
                elif command:
                    print("无法识别命令", flush=True)
            except (IndexError, ValueError):
                print("命令参数有误", flush=True)
    finally:
        if input_transport is not None:
            input_transport.close()
        await client.disconnect()
        await connection


def main():
    """命令行客户端入口"""
    import argparse

    parser = argparse.ArgumentParser(description="三国杀客户端")
    parser.add_argument("--server", default="ws://localhost:8765", help="服务端地址")
    parser.add_argument("--name", default="玩家", help="玩家名称")

    args = parser.parse_args()
    asyncio.run(cli_client_main(args.server, args.name))


if __name__ == "__main__":
    main()
