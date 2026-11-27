"""Drive the shared practice screen over a local JSON-lines process connection."""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Literal

from pydantic import BaseModel, ValidationError
from rich.text import Text
from textual.widgets import Button, Static

from i18n import card_name
from ui.textual_ui.app import GameOverScreen, GamePlayScreen, SanguoshaApp
from ui.textual_ui.screens.game_over import MatchReportScreen
from ui.textual_ui.screens.main_menu import MainMenuScreen


class DesktopInput(BaseModel):
    revision: int
    kind: Literal["key", "button", "refresh", "quit"]
    value: str = ""


KEYS = {"enter", "escape", "tab", "shift+tab", "e", *"0123456789"}


def view(app: SanguoshaApp, revision: int) -> dict[str, object]:
    """Return the controls on the current screen and the local player's view."""
    screen = app.screen
    buttons = [
        {"id": button.id, "label": button.label.plain, "disabled": button.disabled}
        for button in screen.query(Button)
        if button.id and (
            not isinstance(screen, MainMenuScreen) or button.id == "btn-practice"
        )
    ]
    prompts = []
    for widget in screen.query(Static):
        if widget.id in {"hero-title", "target-title", "discard-title", "discard-status",
                         "modal-title", "result-text"}:
            render = widget.render()
            prompts.append(render.plain if isinstance(render, Text) else str(render))
    engine = app._engine
    human = engine.human_player if engine is not None else None
    active = isinstance(screen, GamePlayScreen) and screen._play_request is not None
    hand = []
    rivals = []
    events = []
    if human is not None and engine is not None and human.hero is not None:
        hand = [
            {"label": card_name(card.name), "suit": card.suit.symbol, "number": card.number_str}
            for card in human.hand
        ]
        rivals = [
            {"name": player.hero.name, "hp": player.hp, "maxHp": player.max_hp,
             "handCount": player.hand_count}
            for player in engine.players
            if player is not human and player.hero is not None
        ]
        events = engine.match_events[-14:]
    if isinstance(screen, MatchReportScreen) and screen.report is not None:
        events = screen.report.events
    if isinstance(screen, GameOverScreen):
        prompts.append(screen._message)
    return {
        "protocol": 1, "revision": revision, "screen": type(screen).__name__,
        "buttons": buttons, "prompts": prompts, "hand": hand, "canPlay": active,
        "opponents": rivals, "hp": human.hp if human is not None else None,
        "maxHp": human.max_hp if human is not None else None,
        "round": engine.round_count if engine is not None else 0, "events": events,
    }


async def run() -> None:
    """Process one command at a time until the window closes or stdin ends."""
    app = SanguoshaApp()
    revision = 0
    input_pipe = sys.stdin.buffer
    output_pipe = sys.stdout
    async with app.run_test(size=(120, 44)) as pilot:
        await pilot.pause()
        print(json.dumps(view(app, revision), ensure_ascii=False), file=output_pipe, flush=True)
        while line := await asyncio.to_thread(input_pipe.readline):
            try:
                command = DesktopInput.model_validate_json(line)
            except ValidationError:
                print(json.dumps({"protocol": 1, "error": "Invalid command"}), file=output_pipe, flush=True)
                continue
            if command.kind == "quit":
                await pilot.press("ctrl+q")
                return
            if command.revision != revision:
                print(json.dumps(view(app, revision), ensure_ascii=False), file=output_pipe, flush=True)
                continue
            if command.kind == "key" and command.value in KEYS:
                await pilot.press(command.value)
            if command.kind == "button":
                shown = view(app, revision)["buttons"]
                if any(button["id"] == command.value and not button["disabled"] for button in shown):
                    await pilot.click(f"#{command.value}")
            await pilot.pause()
            revision += 1
            print(json.dumps(view(app, revision), ensure_ascii=False), file=output_pipe, flush=True)
