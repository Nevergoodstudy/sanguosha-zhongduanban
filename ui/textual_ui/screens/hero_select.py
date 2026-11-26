"""武将选择界面"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Static

from i18n import t as _t

if TYPE_CHECKING:
    from game.hero import Hero


class HeroSelectScreen(Screen):
    """武将选择界面"""

    CSS = """
    HeroSelectScreen {
        align: center middle;
    }
    #hero-box {
        width: 80;
        height: auto;
        max-height: 90%;
        border: double magenta;
        padding: 1 2;
        overflow-y: auto;
    }
    #hero-title {
        text-align: center;
        text-style: bold;
        color: magenta;
        margin-bottom: 1;
    }
    .hero-btn {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    def __init__(
        self, player_count: int, difficulty: str, role_preference: str = "lord", *,
        practice: bool = False,
    ):
        super().__init__()
        self.player_count = player_count
        self.difficulty = difficulty
        self.role_preference = role_preference
        self.practice = practice
        self.heroes: list[Hero] = []
        self.is_lord = False

    def on_mount(self) -> None:
        """初始化引擎并准备武将选项"""
        from game.engine import GameEngine
        from game.player import Identity
        from game.skill import SkillSystem

        engine = GameEngine()
        engine.setup_game(
            self.player_count, human_player_index=0, role_preference=self.role_preference,
            seed=42 if self.practice else None,
        )

        skill_system = SkillSystem(engine)
        engine.set_skill_system(skill_system)

        self.app._engine = engine
        self.app._difficulty = self.difficulty

        # 准备武将选项
        all_heroes = engine.hero_repo.get_all_heroes()
        self.is_lord = engine.human_player.identity == Identity.LORD

        lord_heroes = [h for h in all_heroes if any(s.is_lord_skill for s in h.skills)]
        normal_heroes = [h for h in all_heroes if not any(s.is_lord_skill for s in h.skills)]

        if self.practice:
            self.heroes = [engine.hero_repo.get_hero("liubei")]
        elif self.is_lord:
            available = lord_heroes.copy()
            remaining = 5 - len(available)
            if remaining > 0:
                extra = engine.rng.sample(normal_heroes, min(remaining, len(normal_heroes)))
                available.extend(extra)
            engine.rng.shuffle(available)
            self.heroes = available[:5]
        else:
            self.heroes = engine.rng.sample(normal_heroes, min(3, len(normal_heroes)))

        # 动态创建按钮
        box = self.query_one("#hero-box")
        title = _t("ui.hero.practice") if self.practice else _t("ui.hero.choose")
        if self.is_lord and not self.practice:
            title = _t("ui.hero.lord")
        box.query_one("#hero-title").update(f"🎭 {title}")

        for i, hero in enumerate(self.heroes):
            kingdom = hero.kingdom.chinese_name
            skills_text = " / ".join(f"【{s.name}】" for s in hero.skills)
            label = f"{hero.name} [{kingdom}] HP:{hero.max_hp}  {skills_text}"
            btn = Button(label, id=f"hero-{i}", classes="hero-btn", variant="primary")
            box.mount(btn)
        self.call_after_refresh(lambda: self.query_one("#hero-0").focus())

    def compose(self) -> ComposeResult:
        yield Container(
            Static(_t("ui.hero.choose"), id="hero-title"),
            id="hero-box",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("hero-"):
            idx = int(btn_id.split("-")[1])
            chosen = self.heroes[idx]
            self._finish_setup(chosen)

    def _finish_setup(self, chosen_hero: Hero) -> None:
        """完成选将并进入游戏"""
        from ai.bot import AIBot, AIDifficulty
        from game.player import Identity

        engine = self.app._engine
        hero = copy.deepcopy(chosen_hero)
        engine.human_player.set_hero(hero)

        if self.practice:
            engine.choose_heroes({1: "ganning"})
            self._arrange_practice_deck()
        if not self.practice:
            available = [h for h in engine.hero_repo.get_all_heroes() if h.id != hero.id]
            ai_choices = {}
            for p in engine.players:
                if not p.is_ai or p.hero is not None:
                    continue
                lord_pool = [
                    h for h in available if any(s.is_lord_skill for s in h.skills)
                ] if p.identity == Identity.LORD else []
                choice = engine.rng.choice(lord_pool or available)
                ai_choices[p.id] = choice.id
                available.remove(choice)
            engine.choose_heroes(ai_choices)

        # 设置 AI
        difficulty = AIDifficulty(self.app._difficulty)
        for p in engine.players:
            if p.is_ai:
                engine.ai_bots[p.id] = AIBot(p, difficulty)

        engine.start_game()
        if self.practice:
            engine.players[0].hp = 2
            engine.players[1].hp = 1

        # 跳过所有 setup screens，进入游戏
        from .game_play import GamePlayScreen

        self.app.switch_screen(GamePlayScreen(practice=self.practice))

    def _arrange_practice_deck(self) -> None:
        from game.card import CardName

        deck = self.app._engine.deck
        opening = [
            CardName.SHA, CardName.SHAN, CardName.SHAN, CardName.SHAN,
            CardName.SHAN, CardName.SHA, CardName.SHA, CardName.SHA,
            CardName.SHAN, CardName.SHAN, CardName.SHA, CardName.SHA,
            CardName.SHA, CardName.SHAN,
        ]
        arranged = []
        for name in opening:
            index = next(i for i, card in enumerate(deck.draw_pile) if card.name == name)
            arranged.append(deck.draw_pile.pop(index))
        deck.put_on_top(list(reversed(arranged)))
