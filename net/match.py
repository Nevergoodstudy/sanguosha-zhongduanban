"""Bridge a LAN room's requests to the synchronous game engine."""

from collections.abc import Callable

from ai.bot import AIBot, AIDifficulty
from game.actions import PlayCardAction, UseSkillAction
from game.card import Card, CardName, CardSubtype
from game.engine import GameEngine
from game.player import Identity, Player
from game.request_handler import DefaultRequestHandler
from game.skill import SkillSystem

from .protocol import ServerMsg

Request = Callable[[int, str, dict], dict]


class LanMatch(DefaultRequestHandler):
    """Own one engine on its room worker and expose requests to the room."""

    def __init__(
        self,
        names: dict[int, str],
        player_count: int,
        ask: Request,
        sync: Callable[[dict[int, ServerMsg]], None],
        should_stop: Callable[[], bool],
    ):
        engine = GameEngine()
        super().__init__(engine)
        self.connection_by_seat = dict(enumerate(names))
        self.ask = ask
        self.sync = sync
        self.should_stop = should_stop
        engine.setup_game(player_count, human_player_index=-1, role_preference="random")
        engine.set_skill_system(SkillSystem(engine))
        engine.request_handler = self
        for seat in engine.players:
            connection_id = self.connection_by_seat.get(seat.id)
            if connection_id is None:
                engine.ai_bots[seat.id] = AIBot(seat, AIDifficulty.NORMAL)
                continue
            seat.name = names[connection_id]
            seat.is_ai = False

    @staticmethod
    def _card_options(
        cards: list[Card], exclude_responses: bool = False
    ) -> list[dict[str, str | int]]:
        return [
            {"id": index, "name": card.name, "display": card.display_name}
            for index, card in enumerate(cards)
            if not exclude_responses or card.subtype not in {CardSubtype.COUNTER, CardSubtype.DODGE}
        ]

    def _sync(self) -> None:
        engine = self.engine
        public = [
            {
                "id": seat.id,
                "name": seat.name,
                "hero": seat.hero.name,
                "hp": seat.hp,
                "max_hp": seat.max_hp,
                "alive": seat.is_alive,
                "hand_count": seat.hand_count,
                "identity": seat.identity.value if seat.identity == Identity.LORD else None,
            }
            for seat in engine.players
        ]
        self.sync(
            {
                connection_id: ServerMsg.game_state(
                    {
                        "protocol_version": 1,
                        "current_player": engine.current_player.id,
                        "round": engine.round_count,
                        "phase": engine.phase.value,
                        "players": public,
                        "seat_id": seat_id,
                        "identity": engine.players[seat_id].identity.value,
                        "hand": self._card_options(engine.players[seat_id].hand),
                    }
                )
                for seat_id, connection_id in self.connection_by_seat.items()
            }
        )

    def run(self) -> ServerMsg:
        engine = self.engine
        heroes = engine.hero_repo.get_all_heroes()
        engine.rng.shuffle(heroes)
        choices = {}
        for seat_id, connection_id in self.connection_by_seat.items():
            if self.should_stop():
                return ServerMsg.game_over("unknown", "match_cancelled")
            candidates = heroes[:3]
            response = self.ask(
                connection_id,
                "choose_hero",
                {"heroes": [{"id": hero.id, "name": hero.name} for hero in candidates]},
            )
            chosen = next(
                (hero for hero in candidates if hero.id == response.get("hero_id")), candidates[0]
            )
            choices[seat_id] = chosen.id
            heroes.remove(chosen)
        for seat in engine.players:
            if seat.is_ai:
                choices[seat.id] = heroes.pop().id
        engine.choose_heroes(choices)
        engine.start_game()
        self._sync()
        for _ in range(200 * len(engine.players)):
            if self.should_stop() or engine.is_game_over():
                break
            engine.turn_manager.run_turn(
                engine.current_player,
                play_human=self._play,
                discard_human=self._discard,
                should_stop=self.should_stop,
            )
            self._sync()
            if not engine.is_game_over():
                engine.next_turn()
        winner = engine.winner_identity.value if engine.winner_identity else "unknown"
        reason = "match_cancelled" if self.should_stop() else "round_limit"
        if engine.winner_identity:
            reason = "complete"
        return ServerMsg.game_over(winner, reason, {"rounds": engine.round_count})

    def _play(self, player: Player) -> None:
        engine = self.engine
        for _ in range(50):
            if self.should_stop() or engine.is_game_over():
                return
            self._sync()
            cards = player.hand[:]
            response = self.ask(
                self.connection_by_seat[player.id],
                "play",
                {
                    "cards": self._card_options(cards, exclude_responses=True),
                    "targets": [
                        {"id": seat.id, "name": seat.name} for seat in engine.get_alive_players()
                    ],
                    "skills": engine.skill_system.get_usable_skills(player),
                    "skill_cards": self._card_options(cards),
                },
            )
            action = response.get("action_type", "end_turn")
            if action == "end_turn":
                return
            match action:
                case "play_card":
                    command = PlayCardAction(
                        player.id,
                        card_id=cards[response["card_id"]].id,
                        target_ids=response["target_ids"],
                    )
                case "use_skill":
                    command = UseSkillAction(
                        player.id,
                        skill_id=response["skill_id"],
                        target_ids=response["target_ids"],
                        card_ids=[id(cards[index]) for index in response["card_ids"]],
                    )
            if not engine.execute_action(command):
                self.sync({self.connection_by_seat[player.id]: ServerMsg.error("当前出牌无效")})

    def _discard(self, player: Player, count: int) -> None:
        self._sync()
        cards = player.hand[:]
        response = self.ask(
            self.connection_by_seat[player.id],
            "discard",
            {"cards": self._card_options(cards), "count": count},
        )
        if self.should_stop():
            return
        indices = response.get("card_ids", list(range(count)))
        self.engine.discard_for_turn(player, [cards[index] for index in indices])

    def _respond(self, player: Player, kind: str, cards: list[Card]) -> Card | None:
        if not cards or self.should_stop():
            return None
        self._sync()
        response = self.ask(
            self.connection_by_seat[player.id], kind, {"cards": self._card_options(cards)}
        )
        return cards[response["card_id"]] if response.get("accepted") else None

    def request_shan(self, player: Player) -> Card | None:
        if player.is_ai:
            return super().request_shan(player)
        return self._respond(player, "play_shan", player.get_cards_by_name(CardName.SHAN))

    def request_sha(self, player: Player) -> Card | None:
        if player.is_ai:
            return super().request_sha(player)
        cards = [
            card
            for card in player.hand
            if card.subtype
            in {CardSubtype.ATTACK, CardSubtype.FIRE_ATTACK, CardSubtype.THUNDER_ATTACK}
        ]
        return self._respond(player, "play_sha", cards)

    def request_tao(self, savior: Player, dying: Player) -> Card | None:
        if savior.is_ai:
            return super().request_tao(savior, dying)
        return self._respond(savior, "play_tao", savior.get_cards_by_name(CardName.TAO))

    def request_wuxie(
        self,
        responder: Player,
        trick_card: Card,
        source: Player,
        target: Player | None,
        is_cancelled: bool,
    ) -> Card | None:
        if responder.is_ai:
            return super().request_wuxie(responder, trick_card, source, target, is_cancelled)
        return self._respond(responder, "play_wuxie", responder.get_cards_by_name(CardName.WUXIE))

    def request_skill_card(
        self, player: Player, skill_name: str, candidates: list[Card]
    ) -> Card | None:
        if player.is_ai:
            return super().request_skill_card(player, skill_name, candidates)
        return self._respond(player, skill_name, candidates)
