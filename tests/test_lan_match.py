"""Two actual clients exercising a LAN game over loopback."""

import asyncio

import pytest

from game.card import CardName
from game.engine import GameEngine
from net.client import GameClient
from net.protocol import MsgType, RoomState
from net.server import GameServer


@pytest.mark.asyncio
async def test_two_lan_players_finish_and_can_restore_their_prompt(monkeypatch):
    start_game = GameEngine.start_game

    def start_with_reproducible_hand(engine):
        start_game(engine)
        player = engine.current_player
        opponent = next(p for p in engine.players if p is not player)
        for seat, names in (
            (player, [CardName.WUZHONG, CardName.SHA]),
            (opponent, [CardName.SHAN]),
        ):
            engine.deck.discard(seat.hand[:])
            seat.hand.clear()
            for name in names:
                card = next(c for c in engine.deck.draw_pile if c.name == name)
                engine.deck.draw_pile.remove(card)
                seat.hand.append(card)
        opponent.hp = 1
        # Cover two turn draws, Yingzi's extra draw, and two Wuzhong draws.
        safe_draws = [card for card in engine.deck.draw_pile if card.name == CardName.SHAN][:5]
        for card in safe_draws:
            engine.deck.draw_pile.remove(card)
        engine.deck.draw_pile.extend(safe_draws)

    monkeypatch.setattr(GameEngine, "start_game", start_with_reproducible_hand)
    server = GameServer(host="127.0.0.1", port=0, lan_preview=True)
    listening = asyncio.create_task(server.start())
    first, second = GameClient(), GameClient()
    clients = (first, second)
    events = asyncio.Queue()
    tasks = []
    for client in clients:
        client.reconnect_delay = 0.05
        for kind in (
            MsgType.HEARTBEAT_ACK,
            MsgType.ROOM_CREATED,
            MsgType.ROOM_JOINED,
            MsgType.GAME_REQUEST,
            MsgType.GAME_STATE,
            MsgType.GAME_OVER,
            MsgType.ERROR,
        ):
            client.on(kind, lambda msg, client=client: events.put_nowait((client, msg)))

    async def receive(kind, sender=None, request_type=None):
        async def matching():
            while True:
                client, message = await events.get()
                if message.type == MsgType.ERROR:
                    pytest.fail(message.data["message"])
                if (
                    message.type == kind
                    and (sender is None or client is sender)
                    and (request_type is None or message.data["request_type"] == request_type)
                ):
                    return client, message.data

        return await asyncio.wait_for(matching(), 5)

    try:

        async def wait_until_listening():
            while not server.port:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_until_listening(), 5)
        for client in clients:
            client.server_url = f"ws://127.0.0.1:{server.port}"
            tasks.append(asyncio.create_task(client.run()))
            await receive(MsgType.HEARTBEAT_ACK, client)

        await first.create_room("甲", max_players=2, ai_fill=False)
        _, created = await receive(MsgType.ROOM_CREATED, first)
        room_id = created["room_id"]
        await second.join_room("乙", room_id)
        await receive(MsgType.ROOM_JOINED, second)
        for client in clients:
            await client.set_ready()
        room = server.rooms[room_id]

        async def wait_until_ready():
            while not all(player.ready for player in room.players.values()):
                await asyncio.sleep(0.01)

        await asyncio.wait_for(wait_until_ready(), 5)
        await first.start_game()

        for _ in clients:
            client, request = await receive(MsgType.GAME_REQUEST, request_type="choose_hero")
            await client.choose_hero(request["options"]["heroes"][0]["id"])

        _, first_view = await receive(MsgType.GAME_STATE, first)
        _, second_view = await receive(MsgType.GAME_STATE, second)
        assert first_view["seat_id"] != second_view["seat_id"]
        for view in (first_view, second_view):
            assert "seed" not in view
            assert all("hand" not in seat for seat in view["players"])
            assert all(seat["identity"] in {"lord", None} for seat in view["players"])
        actor, play = await receive(MsgType.GAME_REQUEST, request_type="play")
        defender = second if actor is first else first
        defender_view = second_view if defender is second else first_view
        original_id, original_token = actor.player_id, actor.auth_token

        # Simulate losing the transport while the player is choosing a card.
        await actor._ws.close()
        _, joined = await receive(MsgType.ROOM_JOINED, actor)
        assert joined["resumed"]
        assert actor.player_id == original_id
        assert actor.auth_token != original_token
        _, restored = await receive(MsgType.GAME_STATE, actor)
        assert restored["seat_id"] != defender_view["seat_id"]
        _, restored_prompt = await receive(MsgType.GAME_REQUEST, actor, "play")
        assert restored_prompt == play

        wuzhong = next(c for c in play["options"]["cards"] if c["name"] == CardName.WUZHONG)
        await actor.play_card(wuzhong["id"])
        _, play = await receive(MsgType.GAME_REQUEST, actor, "play")
        assert all(c["name"] != CardName.WUZHONG for c in play["options"]["cards"])
        sha = next(c for c in play["options"]["cards"] if c["name"] == CardName.SHA)
        await actor.play_card(sha["id"], [defender_view["seat_id"]])
        await receive(MsgType.GAME_REQUEST, defender, "play_shan")
        await defender.respond("play_shan", False)

        _, result = await receive(MsgType.GAME_OVER, request_type=None)
        assert result["winner"] == "lord"
        assert result["reason"] == "complete"
        assert room.state == RoomState.FINISHED
        assert room.task is None
        assert room.pending is None
    finally:
        await asyncio.gather(*(client.disconnect() for client in clients))
        await asyncio.gather(*tasks)
        server.stop()
        await asyncio.wait_for(listening, 5)
