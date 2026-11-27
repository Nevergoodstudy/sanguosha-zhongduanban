"""Versioned checkpoints between practice turns."""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, JsonValue, model_validator

from ai.bot import AIBot, AIDifficulty

from .card import Card
from .engine import GameEngine
from .enums import GamePhase, GameState
from .hero import Hero, Skill
from .player import Player
from .skill import SkillSystem


class PracticeCheckpoint(BaseModel):
    """Store the complete state needed to start the next turn."""

    format: Literal["sanguosha-practice"]
    version: Literal[1]
    rules_version: Literal[1]
    seed: int
    random_state: tuple[int, tuple[int, ...], float | None]
    round_count: int
    current_player_index: int
    phase: GamePhase
    skills_enabled: bool
    players: tuple[Player, Player]
    draw_pile: list[Card]
    discard_pile: list[Card]
    actions: list[dict[str, JsonValue]]
    events: list[dict[str, int | str]]

    @model_validator(mode="after")
    def check_seats(self) -> PracticeCheckpoint:
        if (
            self.round_count < 1
            or self.current_player_index not in (0, 1)
            or [player.id for player in self.players] != [0, 1]
            or not all(player.hero and player.is_alive for player in self.players)
            or not self.players[1].is_ai
        ):
            raise ValueError("Invalid practice checkpoint seats or turn")
        return self


PracticeCheckpoint.model_rebuild(_types_namespace={"Card": Card, "Hero": Hero, "Skill": Skill})


def save_practice_checkpoint(engine: GameEngine, destination: Path) -> None:
    """Save from the game worker after the next seat has been selected."""
    checkpoint = PracticeCheckpoint.model_construct(
        format="sanguosha-practice",
        version=1,
        rules_version=1,
        seed=engine.game_seed,
        random_state=engine.rng.getstate(),
        round_count=engine.round_count,
        current_player_index=engine.current_player_index,
        phase=engine.phase,
        skills_enabled=engine.skill_system is not None,
        players=(engine.players[0], engine.players[1]),
        draw_pile=engine.deck.draw_pile,
        discard_pile=engine.deck.discard_pile,
        actions=engine.action_log,
        events=engine.match_events,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            file.write(checkpoint.model_dump_json().encode("utf-8"))
            file.flush()
            os.fsync(file.fileno())
            file.close()
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def load_practice_checkpoint(source: Path) -> GameEngine:
    """Restore a practice game from a checkpoint made before the next turn."""
    checkpoint = PracticeCheckpoint.model_validate_json(source.read_bytes())
    engine = GameEngine()
    engine.game_seed = checkpoint.seed
    engine.rng.setstate(checkpoint.random_state)
    engine.players.extend(checkpoint.players)
    engine.human_player = next((player for player in engine.players if not player.is_ai), None)
    engine.deck.draw_pile = checkpoint.draw_pile
    engine.deck.discard_pile = checkpoint.discard_pile
    if checkpoint.skills_enabled:
        engine.set_skill_system(SkillSystem(engine))
    for player in engine.players:
        if player.is_ai:
            engine.ai_bots[player.id] = AIBot(player, AIDifficulty.EASY)
    engine.round_count = checkpoint.round_count
    engine.current_player_index = checkpoint.current_player_index
    engine.state = GameState.IN_PROGRESS
    engine.phase = checkpoint.phase
    engine.action_log = checkpoint.actions
    engine.match_events = checkpoint.events
    return engine
