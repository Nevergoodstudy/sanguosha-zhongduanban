"""WebSocket 游戏服务端 (M4-T02)
基于 asyncio 的三国杀网络对战服务端

功能:
- 房间管理 (创建/加入/开始)
- 游戏状态同步 (增量事件广播)
- 断线重连 (基于事件序号重放)
- 心跳检测
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from threading import Event
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from websockets.exceptions import ConnectionClosed

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

from i18n import t as _t

from .models import validate_client_message
from .protocol import ClientMsg, MsgType, RoomState, ServerMsg
from .security import (
    DEFAULT_HEARTBEAT_TIMEOUT,
    DEFAULT_MAX_CONNECTIONS,
    DEFAULT_MAX_CONNECTIONS_PER_IP,
    DEFAULT_MAX_MESSAGE_SIZE,
    ConnectionTokenManager,
    IPConnectionTracker,
    OriginValidator,
    RateLimiter,
    sanitize_chat_message,
)

logger = logging.getLogger(__name__)


# ==================== 数据模型 ====================


@dataclass
class ConnectedPlayer:
    """已连接的玩家"""

    player_id: int
    name: str
    websocket: ServerConnection
    room_id: str | None = None
    ready: bool = False
    last_heartbeat: float = field(default_factory=time.time)
    last_seq: int = 0  # 最后收到的事件序号 (用于断线重连)
    auth_token: str = ""  # 连接令牌 (用于重连验证)
    remote_ip: str = ""  # 客户端 IP
    # 速率限制: 滑动窗口内的消息时间戳
    _msg_timestamps: list[float] = field(default_factory=list)


@dataclass
class PendingRequest:
    player_id: int
    request_id: int
    message: ServerMsg
    future: asyncio.Future


@dataclass
class Room:
    """游戏房间"""

    room_id: str
    host_id: int  # 房主 player_id
    max_players: int = 4
    ai_fill: bool = True  # 不足时 AI 填充
    state: RoomState = RoomState.WAITING
    players: dict[int, ConnectedPlayer] = field(default_factory=dict)
    # 游戏事件日志 (用于断线重连)
    event_log: list[ServerMsg] = field(default_factory=list)
    event_seq: int = 0
    pending: PendingRequest | None = None
    views: dict[int, ServerMsg] = field(default_factory=dict)
    disconnected: dict[int, ConnectedPlayer] = field(default_factory=dict)
    task: asyncio.Task | None = None
    stop: Event = field(default_factory=Event)
    result: ServerMsg | None = None

    @property
    def player_count(self) -> int:
        return len(self.players)

    @property
    def is_full(self) -> bool:
        return self.player_count >= self.max_players

    def player_list_data(self) -> list[dict[str, Any]]:
        """返回玩家列表的序列化数据"""
        return [
            {"player_id": p.player_id, "name": p.name, "ready": p.ready}
            for p in self.players.values()
        ]

    def next_seq(self) -> int:
        """获取下一个事件序号"""
        self.event_seq += 1
        return self.event_seq


# ==================== 服务端核心 ====================

# 速率限制默认值
RATE_LIMIT_WINDOW: float = 1.0  # 滑动窗口 (秒)
RATE_LIMIT_MAX_MSGS: int = 30  # 窗口内最大消息数


class GameServer:
    """三国杀 WebSocket 游戏服务端

    职责:
    1. 管理 WebSocket 连接
    2. 房间生命周期管理
    3. 将引擎事件广播给客户端
    4. 路由客户端消息到对应处理器
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        rate_limit_window: float = RATE_LIMIT_WINDOW,
        rate_limit_max_msgs: int = RATE_LIMIT_MAX_MSGS,
        max_connections: int = DEFAULT_MAX_CONNECTIONS,
        max_connections_per_ip: int = DEFAULT_MAX_CONNECTIONS_PER_IP,
        max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE,
        heartbeat_timeout: float = DEFAULT_HEARTBEAT_TIMEOUT,
        allowed_origins: str = "",
        ssl_cert: str = "",
        ssl_key: str = "",
        lan_preview: bool = False,
    ):
        self.host = host
        self.port = port
        self.lan_preview = lan_preview
        # 安全参数
        self._max_connections = max_connections
        self._max_message_size = max_message_size
        self._heartbeat_timeout = heartbeat_timeout
        # TLS
        self._ssl_cert = ssl_cert
        self._ssl_key = ssl_key
        # 连接管理
        self.connections: dict[int, ConnectedPlayer] = {}  # player_id → player
        self.ws_to_player: dict[ServerConnection, int] = {}  # websocket → player_id
        self._next_player_id: int = 1
        # 安全组件
        self._token_manager = ConnectionTokenManager()
        self._ip_tracker = IPConnectionTracker(max_per_ip=max_connections_per_ip)
        self._origin_validator = OriginValidator(allowed_origins)
        if not allowed_origins.strip() and not lan_preview:
            logger.warning("未配置 WebSocket Origin 白名单")
        self._rate_limiter = RateLimiter(rate_limit_window, rate_limit_max_msgs)
        # 房间管理
        self.rooms: dict[str, Room] = {}  # room_id → room
        # 消息路由表
        self._handlers: dict[MsgType, Callable[[ConnectedPlayer, ClientMsg], Awaitable[None]]] = {
            MsgType.HEARTBEAT: self._handle_heartbeat,
            MsgType.ROOM_CREATE: self._handle_room_create,
            MsgType.ROOM_JOIN: self._handle_room_join,
            MsgType.ROOM_LEAVE: self._handle_room_leave,
            MsgType.ROOM_LIST: self._handle_room_list,
            MsgType.ROOM_READY: self._handle_room_ready,
            MsgType.ROOM_START: self._handle_room_start,
            MsgType.GAME_ACTION: self._handle_game_action,
            MsgType.GAME_RESPONSE: self._handle_game_response,
            MsgType.HERO_CHOSEN: self._handle_hero_chosen,
            MsgType.CHAT: self._handle_chat,
        }
        # 服务端状态
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

    # ==================== 连接管理 ====================

    def _assign_player_id(self) -> int:
        """分配唯一玩家 ID"""
        pid = self._next_player_id
        self._next_player_id += 1
        return pid

    def _get_remote_ip(self, websocket: ServerConnection) -> str:
        """获取客户端 IP 地址"""
        try:
            peername = websocket.transport.get_extra_info("peername")
            if peername:
                return peername[0]
        except Exception:
            pass
        return "unknown"

    async def _register(self, websocket: ServerConnection) -> ConnectedPlayer | None:
        """注册新连接 (含连接数限制和令牌签发)"""
        remote_ip = self._get_remote_ip(websocket)

        # 总连接数检查
        if len(self.connections) >= self._max_connections:
            logger.warning(f"连接数已达上限 ({self._max_connections}), 拒绝 {remote_ip}")
            await websocket.close(1013, _t("server.full"))  # 1013 = Try Again Later
            return None

        # 单 IP 连接数检查
        if not self._ip_tracker.can_connect(remote_ip):
            logger.warning(f"IP {remote_ip} 连接数超限, 拒绝")
            await websocket.close(1008, _t("server.ip_limit"))  # 1008 = Policy Violation
            return None

        pid = self._assign_player_id()
        token = self._token_manager.issue(pid)
        player = ConnectedPlayer(
            player_id=pid,
            name=_t("game.player_name", index=pid),
            websocket=websocket,
            auth_token=token,
            remote_ip=remote_ip,
        )
        self.connections[pid] = player
        self.ws_to_player[websocket] = pid
        self._ip_tracker.add(remote_ip)

        # 发送欢迎消息 (包含令牌)
        welcome = ServerMsg(
            type=MsgType.HEARTBEAT_ACK,
            data={
                "player_id": pid,
                "token": token,
            },
        )
        await self._send(player, welcome)
        logger.info(f"玩家 {pid} 已连接 (IP: {remote_ip})")
        return player

    async def _unregister(self, websocket: ServerConnection) -> None:
        """注销连接"""
        pid = self.ws_to_player.pop(websocket, None)
        if pid is None:
            return
        player = self.connections.pop(pid, None)
        if player:
            self._ip_tracker.remove(player.remote_ip)
            self._rate_limiter.remove_player(pid)
            room = self.rooms.get(player.room_id or "")
            if room and room.state == RoomState.PLAYING and self.lan_preview:
                room.players.pop(pid, None)
                room.disconnected[pid] = player
                await self._broadcast_room_update(room)
                return
            self._token_manager.revoke(player_id=pid)
            if room:
                await self._remove_from_room(room, player)
        logger.info(f"玩家 {pid} 已断开")

    # ==================== 消息收发 ====================

    async def _send(self, player: ConnectedPlayer, msg: ServerMsg) -> None:
        """发送消息给单个玩家"""
        try:
            await asyncio.wait_for(player.websocket.send(msg.to_json()), timeout=3)
        except (TimeoutError, ConnectionClosed, OSError) as e:
            logger.warning(f"发送消息失败 (玩家{player.player_id}): {e}")

    async def _broadcast_room(self, room: Room, msg: ServerMsg, exclude: int | None = None) -> None:
        """广播消息给房间内所有玩家"""
        await asyncio.gather(
            *(
                self._send(player, msg)
                for pid, player in tuple(room.players.items())
                if pid != exclude
            )
        )

    async def _broadcast_room_update(self, room: Room) -> None:
        """广播房间状态更新"""
        msg = ServerMsg.room_update(room.room_id, room.player_list_data(), room.state)
        await self._broadcast_room(room, msg)

    async def _broadcast_game_event(
        self, room: Room, event_type: str, event_data: dict[str, Any]
    ) -> None:
        """广播游戏事件并记录到事件日志"""
        seq = room.next_seq()
        msg = ServerMsg.game_event(event_type, event_data, seq=seq)
        room.event_log.append(msg)
        await self._broadcast_room(room, msg)

    # ==================== 消息路由 ====================

    def _check_rate_limit(self, player: ConnectedPlayer) -> bool:
        """检查玩家是否超出消息速率限制。

        Returns:
            True 表示允许处理, False 表示应丢弃
        """
        return self._rate_limiter.check(player.player_id)

    async def _handle_message(self, websocket: ServerConnection, raw: str) -> None:
        """路由消息到对应处理器（含 Pydantic 校验）"""
        pid = self.ws_to_player.get(websocket)
        player = self.connections.get(pid)
        if not player:
            return
        try:
            parsed = validate_client_message(raw)
        except ValidationError:
            await self._send(player, ServerMsg.error(_t("server.invalid_format")))
            return

        try:
            msg_type = MsgType(parsed.type)
        except ValueError:
            await self._send(player, ServerMsg.error(_t("server.unknown_type", type=parsed.type)))
            return
        if msg_type != MsgType.HEARTBEAT and not self._check_rate_limit(player):
            await self._send(player, ServerMsg.error(_t("server.rate_limited")))
            return
        handler = self._handlers.get(msg_type)
        if not handler:
            await self._send(player, ServerMsg.error(_t("server.unknown_type", type=parsed.type)))
            return

        await handler(player, ClientMsg(msg_type, player.player_id, parsed.data, parsed.timestamp))

    # ==================== 房间管理处理器 ====================

    async def _handle_heartbeat(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        player.last_heartbeat = time.time()
        await self._send(player, ServerMsg.heartbeat_ack())

    async def _handle_room_create(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        if player.room_id:
            await self._send(player, ServerMsg.error(_t("server.already_in_room")))
            return

        room_id = str(uuid.uuid4())[:8]
        player_name = msg.data.get("player_name", player.name)
        player.name = player_name
        max_players = msg.data.get("max_players", 4)
        ai_fill = msg.data.get("ai_fill", True)

        room = Room(
            room_id=room_id,
            host_id=player.player_id,
            max_players=max_players,
            ai_fill=ai_fill,
        )
        room.players[player.player_id] = player
        player.room_id = room_id
        self.rooms[room_id] = room

        logger.info(f"房间 {room_id} 已创建 (房主: {player.name})")
        await self._send(
            player,
            ServerMsg.room_created(
                room_id,
                {
                    "max_players": max_players,
                    "ai_fill": ai_fill,
                    "host_id": player.player_id,
                },
            ),
        )

    async def _handle_room_join(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        if player.room_id:
            await self._send(player, ServerMsg.error(_t("server.already_in_room")))
            return

        room_id = msg.data.get("room_id", "")
        if self.lan_preview and msg.data.get("reconnect"):
            await self._restore_seat(player, room_id, msg.data["token"])
            return
        room = self.rooms.get(room_id)
        if not room:
            await self._send(player, ServerMsg.error(_t("server.room_not_found")))
            return
        if room.is_full:
            await self._send(player, ServerMsg.error(_t("server.room_full")))
            return
        if room.state != RoomState.WAITING:
            await self._send(player, ServerMsg.error(_t("server.game_started")))
            return

        player_name = msg.data.get("player_name", player.name)
        player.name = player_name
        room.players[player.player_id] = player
        player.room_id = room_id

        logger.info(f"玩家 {player.name} 加入房间 {room_id}")
        await self._send(
            player,
            ServerMsg.room_joined(room_id, player.player_id, player.name, room.player_list_data()),
        )
        await self._broadcast_room_update(room)

    async def _handle_room_leave(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        if not player.room_id:
            return
        room = self.rooms.get(player.room_id)
        if room:
            await self._remove_from_room(room, player)
        player.room_id = None
        player.ready = False
        await self._send(player, ServerMsg(type=MsgType.ROOM_LEFT))

    async def _remove_from_room(self, room: Room, player: ConnectedPlayer) -> None:
        room.players.pop(player.player_id, None)
        if room.state == RoomState.PLAYING:
            room.stop.set()
            if room.pending and not room.pending.future.done():
                room.pending.future.set_result({})
        if room.players:
            if room.host_id == player.player_id:
                room.host_id = next(iter(room.players))
            await self._broadcast_room_update(room)
            return
        if not room.disconnected:
            self.rooms.pop(room.room_id, None)

    async def _handle_room_list(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        rooms_data = [
            {
                "room_id": r.room_id,
                "host_id": r.host_id,
                "player_count": r.player_count,
                "max_players": r.max_players,
                "state": r.state.value,
            }
            for r in self.rooms.values()
        ]
        await self._send(player, ServerMsg.room_listing(rooms_data))

    async def _handle_room_ready(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        player.ready = msg.data.get("ready", True)
        room = self.rooms.get(player.room_id or "")
        if room:
            await self._broadcast_room_update(room)

    async def _handle_room_start(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        """房主开始游戏"""
        room = self.rooms.get(player.room_id or "")
        if not room:
            await self._send(player, ServerMsg.error(_t("server.not_in_room")))
            return
        if room.host_id != player.player_id:
            await self._send(player, ServerMsg.error(_t("server.not_owner")))
            return
        if room.state != RoomState.WAITING:
            await self._send(player, ServerMsg.error(_t("server.game_in_progress")))
            return

        if not self.lan_preview:
            await self._send(player, ServerMsg.error("请用 --lan-preview 启用局域网对局"))
            return
        if room.player_count < 2 or not all(p.ready for p in room.players.values()):
            await self._send(player, ServerMsg.error("需要至少两位玩家并全部准备"))
            return

        room.state = RoomState.PLAYING
        names = {pid: member.name for pid, member in room.players.items()}
        await self._broadcast_room(room, ServerMsg(type=MsgType.ROOM_STARTED))
        room.task = asyncio.create_task(self._run_game(room, names))
        logger.info(f"房间 {room.room_id} 游戏开始 ({room.player_count} 人)")

    # ==================== 游戏逻辑 ====================

    # 人类玩家操作超时（秒）
    _ACTION_TIMEOUT: float = 60.0

    async def _run_game(self, room: Room, names: dict[int, str]) -> None:
        """Run the room's engine in one worker while sockets stay on the event loop."""
        from .match import LanMatch

        loop = asyncio.get_running_loop()
        count = room.max_players if room.ai_fill else len(names)

        def ask(pid, kind, options):
            return asyncio.run_coroutine_threadsafe(
                self._request(room, pid, kind, options), loop
            ).result()

        def sync(messages):
            asyncio.run_coroutine_threadsafe(self._publish_views(room, messages), loop).result()

        try:
            match = LanMatch(names, count, ask, sync, room.stop.is_set)
            room.result = await asyncio.to_thread(match.run)
        except Exception:
            logger.exception("房间 %s 对局异常", room.room_id)
            room.result = ServerMsg.game_over("unknown", "match_error")
        finally:
            room.state = RoomState.FINISHED
            room.pending = None
            room.task = None
            for pid in room.disconnected:
                self._token_manager.revoke(player_id=pid)
            room.disconnected.clear()
            if not room.players:
                self.rooms.pop(room.room_id, None)

        await self._broadcast_room(room, room.result)

    async def _publish_views(self, room: Room, messages: dict[int, ServerMsg]) -> None:
        for pid, message in messages.items():
            if message.type == MsgType.GAME_STATE:
                room.views[pid] = message
        await asyncio.gather(
            *(
                self._send(room.players[pid], message)
                for pid, message in messages.items()
                if pid in room.players
            )
        )

    async def _request(self, room: Room, pid: int, kind: str, options: dict) -> dict:
        if room.stop.is_set():
            return {}
        request_id = room.next_seq()
        message = ServerMsg.game_request(kind, pid, options, self._ACTION_TIMEOUT)
        message.data["request_id"] = request_id
        pending = PendingRequest(
            pid, request_id, message, asyncio.get_running_loop().create_future()
        )
        room.pending = pending
        try:
            if pid in room.players:
                await self._send(room.players[pid], message)
            return await asyncio.wait_for(pending.future, timeout=self._ACTION_TIMEOUT)
        except TimeoutError:
            if pid in room.disconnected:
                room.stop.set()
            return {}
        finally:
            room.pending = None

    async def _handle_game_action(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        await self._complete_request(player, msg)

    async def _handle_game_response(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        await self._complete_request(player, msg)

    async def _handle_hero_chosen(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        await self._complete_request(player, msg)

    async def _complete_request(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        room = self.rooms.get(player.room_id or "")
        pending = room.pending if room else None
        if (
            pending is None
            or pending.future.done()
            or pending.player_id != player.player_id
            or pending.request_id != msg.data.get("request_id")
            or not self._response_matches(pending.message, msg)
        ):
            await self._send(player, ServerMsg.error("当前没有匹配此操作的请求"))
            return
        pending.future.set_result(msg.data)

    @staticmethod
    def _response_matches(request: ServerMsg, response: ClientMsg) -> bool:
        kind = request.data["request_type"]
        options = request.data["options"]
        data = response.data
        if kind == "choose_hero":
            return response.type == MsgType.HERO_CHOSEN and any(
                hero["id"] == data["hero_id"] for hero in options["heroes"]
            )
        card_ids = {card["id"] for card in options["cards"]}
        if kind == "play":
            if response.type != MsgType.GAME_ACTION:
                return False
            action = data["action_type"]
            if action == "end_turn":
                return True
            targets = {target["id"] for target in options["targets"]}
            selected_targets = set(data["target_ids"])
            if len(selected_targets) != len(data["target_ids"]) or not selected_targets <= targets:
                return False
            if action == "play_card":
                return data["card_id"] in card_ids
            skill_cards = {card["id"] for card in options["skill_cards"]}
            return (
                action == "use_skill"
                and data["skill_id"] in options["skills"]
                and (
                    len(set(data["card_ids"])) == len(data["card_ids"])
                    and set(data["card_ids"]) <= skill_cards
                )
            )
        if kind == "discard":
            if response.type != MsgType.GAME_ACTION or data["action_type"] != "discard":
                return False
            all_selected = set(data["card_ids"])
            return len(data["card_ids"]) == len(all_selected) == options["count"] and (
                all_selected <= card_ids
            )
        return (
            response.type == MsgType.GAME_RESPONSE
            and data["request_type"] == kind
            and (not data["accepted"] or data["card_id"] in card_ids)
        )

    async def _handle_chat(self, player: ConnectedPlayer, msg: ClientMsg) -> None:
        """处理聊天 (含输入净化)"""
        room = self.rooms.get(player.room_id or "")
        if not room:
            return

        text = msg.data.get("message", "")
        text = sanitize_chat_message(text)
        if text:
            await self._broadcast_room(
                room,
                ServerMsg.chat_broadcast(player.name, text),
                exclude=player.player_id,
            )

    # ==================== 断线重连 ====================

    async def _restore_seat(self, player: ConnectedPlayer, room_id: str, token: str) -> None:
        room = self.rooms.get(room_id)
        previous = (
            next(
                (
                    seat
                    for seat in room.disconnected.values()
                    if self._token_manager.verify(token, seat.player_id)
                ),
                None,
            )
            if room
            else None
        )
        if room is None or previous is None:
            await self._send(player, ServerMsg.error(_t("server.invalid_token")))
            return

        temporary_id = player.player_id
        self.connections.pop(temporary_id)
        self._token_manager.revoke(player_id=temporary_id)
        self._rate_limiter.remove_player(temporary_id)
        restored_id = previous.player_id
        room.disconnected.pop(restored_id)
        player.player_id = restored_id
        player.name = previous.name
        player.room_id = room_id
        player.ready = previous.ready
        player.auth_token = self._token_manager.issue(restored_id)
        self.connections[restored_id] = player
        self.ws_to_player[player.websocket] = restored_id
        room.players[restored_id] = player
        message = ServerMsg.room_joined(room_id, restored_id, player.name, room.player_list_data())
        message.data.update(token=player.auth_token, resumed=True)
        await self._send(player, message)
        if restored_id in room.views:
            await self._send(player, room.views[restored_id])
        pending = room.pending
        if pending and pending.player_id == restored_id and not pending.future.done():
            await self._send(player, pending.message)
        await self._broadcast_room_update(room)

    async def reconnect_player(
        self, player: ConnectedPlayer, room_id: str, last_seq: int, token: str = ""
    ) -> bool:
        """断线重连: 验证令牌并重放玩家缺失的事件

        Args:
            player: 重连的玩家
            room_id: 房间 ID
            last_seq: 玩家最后收到的事件序号
            token: 重连令牌

        Returns:
            是否成功重连
        """
        # 令牌验证
        if token and not self._token_manager.verify(token, player.player_id):
            logger.warning(f"重连令牌验证失败: 玩家 {player.player_id}")
            await self._send(player, ServerMsg.error(_t("server.invalid_token")))
            return False

        room = self.rooms.get(room_id)
        if not room:
            await self._send(player, ServerMsg.error(_t("server.room_not_found")))
            return False

        # 重新加入房间
        room.players[player.player_id] = player
        player.room_id = room_id

        # 重放缺失的事件
        missed = [e for e in room.event_log if e.seq > last_seq]
        for event in missed:
            await self._send(player, event)

        logger.info(f"玩家 {player.name} 重连成功 (重放 {len(missed)} 条事件)")
        return True

    # ==================== 心跳超时检测 ====================

    async def _heartbeat_checker(self) -> None:
        """后台任务: 定期检查心跳超时的连接并清理。"""
        while self._running:
            await asyncio.sleep(self._heartbeat_timeout / 2)
            now = time.time()
            stale: list[int] = []
            for pid, player in list(self.connections.items()):
                if now - player.last_heartbeat > self._heartbeat_timeout:
                    stale.append(pid)
            for pid in stale:
                player = self.connections.get(pid)
                if player:
                    logger.info(f"玩家 {pid} 心跳超时，断开连接")
                    try:
                        await player.websocket.close(1001, _t("server.heartbeat_timeout"))
                    except Exception:
                        pass
                    await self._unregister(player.websocket)
            # 定期清理过期令牌
            self._token_manager.cleanup_expired()

    # ==================== 服务端生命周期 ====================

    async def _connection_handler(self, websocket: ServerConnection) -> None:
        """处理单个 WebSocket 连接"""
        # Origin 验证
        if not self._check_origin(websocket):
            await websocket.close(1008, "Origin not allowed")
            return

        player = await self._register(websocket)
        if player is None:
            return  # 连接被拒绝
        try:
            async for raw_message in websocket:
                await self._handle_message(websocket, raw_message)
        except Exception as e:
            logger.warning(f"连接异常 (玩家{player.player_id}): {e}")
        finally:
            await self._unregister(websocket)

    def _build_ssl_context(self):
        """构建 SSL 上下文 (如果配置了证书)。"""
        if not self._ssl_cert or not self._ssl_key:
            return None
        import ssl

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(self._ssl_cert, self._ssl_key)
        logger.info("已加载 TLS 证书")
        return ctx

    def _check_origin(self, websocket: ServerConnection) -> bool:
        """检查 WebSocket 握手中的 Origin 头。"""
        if not self._origin_validator.is_enabled:
            return not self.lan_preview or websocket.request.headers.get("Origin") is None
        origin = None
        try:
            origin = websocket.request.headers.get("Origin")
        except Exception:
            pass
        if not self._origin_validator.is_allowed(origin):
            logger.warning(f"Origin 验证失败: {origin}")
            return False
        return True

    def _get_serve_origins(self) -> list[str] | None:
        """为 websockets.serve 提供 origins 参数。"""
        if not self._origin_validator.is_enabled:
            return None
        return list(self._origin_validator.allowed_origins)

    async def start(self) -> None:
        """启动服务端"""
        try:
            import websockets
        except ImportError:
            logger.error("需要安装 websockets: pip install websockets")
            return

        self._running = True
        ssl_ctx = self._build_ssl_context()
        if not ssl_ctx:
            logger.warning(
                "Running without TLS (ws://). Auth tokens will be transmitted "
                "in plaintext. Use --ssl-cert and --ssl-key for production."
            )
        protocol = "wss" if ssl_ctx else "ws"
        logger.info(f"三国杀服务端启动: {protocol}://{self.host}:{self.port}")

        # 启动心跳超时检测后台任务
        self._heartbeat_task = asyncio.create_task(self._heartbeat_checker())
        serve_origins = self._get_serve_origins()

        try:
            async with websockets.serve(
                self._connection_handler,
                self.host,
                self.port,
                max_size=self._max_message_size,
                origins=serve_origins,
                ssl=ssl_ctx,
            ) as listening:
                self.port = listening.sockets[0].getsockname()[1]
                while self._running:
                    await asyncio.sleep(0.1)
        finally:
            rooms = tuple(self.rooms.values())
            tasks = [room.task for room in rooms if room.task]
            self.stop()
            await asyncio.gather(*tasks)

    def stop(self) -> None:
        """停止服务端"""
        self._running = False
        for room in self.rooms.values():
            room.stop.set()
            if room.pending and not room.pending.future.done():
                room.pending.future.set_result({})
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        logger.info("服务端停止")


# ==================== CLI 入口 ====================


def main():
    """命令行启动服务端"""
    import argparse

    parser = argparse.ArgumentParser(description="三国杀 WebSocket 服务端")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    parser.add_argument("--lan-preview", action="store_true", help="启用局域网对局")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    server = GameServer(host=args.host, port=args.port, lan_preview=args.lan_preview)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
