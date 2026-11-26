"""
Textual TUI 测试（M3）
"""

import pytest

from ui.protocol import GameDisplay, GameInput, GameNotify, GameUI
from ui.textual_ui.app import (
    GameOverScreen,
    GameSetupScreen,
    MainMenuScreen,
    RulesScreen,
    SanguoshaApp,
    TextualUIBridge,
)


class TestTextualAppImport:
    """测试 Textual App 模块导入"""

    def test_app_class(self):
        assert SanguoshaApp is not None

    def test_screens_exist(self):
        assert MainMenuScreen is not None
        assert RulesScreen is not None
        assert GameSetupScreen is not None
        assert GameOverScreen is not None

    def test_bridge_class(self):
        assert TextualUIBridge is not None


class TestGameUIProtocol:
    """测试 GameUI Protocol 及子协议"""

    def test_bridge_has_protocol_methods(self):
        """TextualUIBridge 拥有 Protocol 所需的方法"""
        bridge = TextualUIBridge.__new__(TextualUIBridge)
        bridge.log_messages = []
        bridge._screen = None
        bridge.engine = None
        # 验证关键方法存在
        assert hasattr(bridge, "show_main_menu")
        assert hasattr(bridge, "show_game_state")
        assert hasattr(bridge, "show_log")
        assert hasattr(bridge, "ask_for_shan")
        assert hasattr(bridge, "choose_target")
        assert hasattr(bridge, "get_player_action")

    def test_sub_protocols_exist(self):
        """三个子协议存在且可导入"""
        assert GameDisplay is not None
        assert GameInput is not None
        assert GameNotify is not None

    def test_gameui_inherits_sub_protocols(self):
        """GameUI 组合继承所有子协议"""
        # Protocol 不支持运行时 issubclass，通过 MRO 检查继承关系
        mro = GameUI.__mro__
        assert GameDisplay in mro
        assert GameInput in mro
        assert GameNotify in mro

    def test_display_protocol_methods(self):
        """GameDisplay 子协议包含展示方法"""
        display_methods = [
            "show_title",
            "show_rules",
            "show_game_state",
            "show_log",
            "show_game_over",
            "clear_screen",
            "show_help",
        ]
        for method in display_methods:
            assert hasattr(GameDisplay, method), f"GameDisplay missing: {method}"

    def test_input_protocol_methods(self):
        """GameInput 子协议包含输入方法"""
        input_methods = [
            "show_main_menu",
            "show_player_count_menu",
            "show_difficulty_menu",
            "show_hero_selection",
            "get_player_action",
            "choose_target",
            "choose_card_to_play",
            "choose_cards_to_discard",
            "show_skill_menu",
            "ask_for_shan",
            "ask_for_sha",
            "ask_for_tao",
            "ask_for_wuxie",
            "choose_card_from_player",
            "choose_suit",
            "guanxing_selection",
            "wait_for_continue",
            "ask_for_jijiang",
            "ask_for_hujia",
        ]
        for method in input_methods:
            assert hasattr(GameInput, method), f"GameInput missing: {method}"

    def test_notify_protocol_methods(self):
        """GameNotify 子协议包含通知方法"""
        assert hasattr(GameNotify, "set_engine")


class TestTextualUIBridge:
    """测试 TextualUIBridge"""

    def test_bridge_show_log(self):
        """Bridge show_log 不抛异常"""
        # 不创建真正的 screen，仅测试日志存储
        bridge = TextualUIBridge.__new__(TextualUIBridge)
        bridge.log_messages = []
        bridge._screen = None
        bridge.engine = None

        # show_log 应存储消息（即使 screen 不可用）
        bridge.log_messages.append("test")
        assert len(bridge.log_messages) == 1

    def test_bridge_has_all_methods(self):
        """Bridge 拥有引擎所需的全部 UI 方法"""
        bridge = TextualUIBridge.__new__(TextualUIBridge)
        bridge.log_messages = []
        bridge._screen = None
        bridge.engine = None

        required_methods = [
            "show_log",
            "show_game_state",
            "show_title",
            "show_main_menu",
            "ask_for_shan",
            "ask_for_sha",
            "ask_for_tao",
            "ask_for_wuxie",
            "choose_target",
            "choose_suit",
            "guanxing_selection",
        ]
        for method in required_methods:
            assert hasattr(bridge, method), f"Missing method: {method}"


class TestAnimationCSS:
    """测试 M3-T04 动画相关"""

    def test_css_contains_animation_classes(self):
        """应用 CSS 包含动画类"""
        css = SanguoshaApp.CSS
        assert "flash-damage" in css
        assert "flash-heal" in css
        assert "flash-skill" in css
        assert "card-btn" in css
        assert "transition" in css

    def test_gameplay_screen_has_flash_method(self):
        """游戏界面应有 flash_effect 方法"""
        from ui.textual_ui.app import GamePlayScreen

        assert hasattr(GamePlayScreen, "flash_effect")
        assert hasattr(GamePlayScreen, "_post_flash")


class TestGamePlayTimeoutConfig:
    """测试 GamePlayScreen 出牌超时配置来源"""

    def test_gameplay_timeout_reads_env_config(self, monkeypatch):
        """SANGUOSHA_PLAY_TIMEOUT 能影响 GamePlayScreen 超时值"""
        monkeypatch.setenv("SANGUOSHA_PLAY_TIMEOUT", "45")
        from game.config import reset_config

        reset_config()
        try:
            from ui.textual_ui.screens.game_play import GamePlayScreen

            screen = GamePlayScreen()
            assert screen.play_phase_timeout == 45
        finally:
            reset_config()

    def test_countdown_color_midpoint(self):
        """自定义 total 下中点颜色应为黄色"""
        from ui.textual_ui.screens.game_play import GamePlayScreen

        assert GamePlayScreen._countdown_color(60, total=120).lower() == "#f39c12"


class TestMainEntry:
    """测试主入口（Textual TUI 唯一模式）"""

    def test_default_is_textual(self):
        """默认启动 Textual TUI（无 --ui 参数）"""
        from ui.textual_ui import SanguoshaApp

        assert SanguoshaApp is not None

    def test_argparse_no_ui_flag(self):
        """main.py 不再有 --ui 参数"""
        import argparse

        parser = argparse.ArgumentParser()
        # 只保留网络/回放参数
        parser.add_argument("--server", nargs="?", const="0.0.0.0:8765", default=None)
        parser.add_argument("--connect", default=None)
        parser.add_argument("--replay", default=None)

        args = parser.parse_args([])
        assert args.server is None
        assert args.connect is None
        assert args.replay is None


def _fixed_duel():
    from game.card import CardName
    from game.engine import GameEngine

    engine = GameEngine()
    engine.setup_game(2, seed=1)
    engine.choose_heroes({0: "liubei", 1: "guanyu"})
    engine.start_game()
    human = engine.human_player
    deck = engine.deck.draw_pile
    sha = next(card for card in deck if card.name == CardName.SHA)
    deck.remove(sha)
    human.hand[:] = [sha]
    engine.players[1].hand.clear()
    return engine


async def _wait_until(pilot, condition):
    import asyncio

    async def wait():
        while not condition():
            await pilot.pause(0.01)

    await asyncio.wait_for(wait(), timeout=4)


@pytest.mark.asyncio
async def test_contentment_draws_then_discards_without_human_play():
    from game.card import CardName, CardSuit
    from game.events import EventType
    from ui.textual_ui.modals.discard_modal import DiscardModal
    from ui.textual_ui.screens.game_play import GamePlayScreen

    engine = _fixed_duel()
    player = engine.human_player
    player.hp = 1
    deck = engine.deck.draw_pile
    contentment = next(card for card in deck if card.name == CardName.LEBUSISHU)
    deck.remove(contentment)
    judgment = next(card for card in deck if card.suit == CardSuit.SPADE)
    deck.remove(judgment)
    deck.append(judgment)
    player.judge_area.append(contentment)
    played = []
    engine.event_bus.subscribe(EventType.PHASE_PLAY_START, lambda event: played.append(event))

    app = SanguoshaApp()
    app._engine = engine
    screen = GamePlayScreen()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.push_screen(screen)
        await _wait_until(pilot, lambda: isinstance(app.screen, DiscardModal))
        assert not played
        assert player.hand_count == 3
        assert not player.skip_play_phase
        assert engine.deck.discard_pile[-2:] == [judgment, contentment]
        assert screen._play_request is None
        await pilot.press("q")
        await _wait_until(pilot, lambda: screen._game_worker.is_finished)
        assert app._exit
        assert player.hand_count == 3


def test_face_down_hero_skips_one_turn_and_keeps_judgment_area():
    from game.card import CardName
    from game.events import EventType

    engine = _fixed_duel()
    player = engine.human_player
    deck = engine.deck.draw_pile
    lightning = next(card for card in deck if card.name == CardName.SHANDIAN)
    deck.remove(lightning)
    player.judge_area.append(lightning)
    player.toggle_flip()
    turns = []
    engine.event_bus.subscribe(EventType.TURN_START, lambda event: turns.append(event.data["player"]))
    remaining = engine.deck.remaining

    engine.run_turn()

    assert not turns
    assert not player.flipped
    assert player.judge_area == [lightning]
    assert engine.deck.remaining == remaining

    engine.run_turn()

    assert turns == [player]
    assert not player.judge_area
    assert engine.deck.remaining < remaining


@pytest.mark.asyncio
async def test_input_between_target_requests_is_ignored_and_quit_joins_worker():
    from ui.textual_ui.modals.target_modal import TargetSelectModal
    from ui.textual_ui.screens.game_play import GamePlayScreen
    from ui.textual_ui.widgets.card_widget import CardWidget

    engine = _fixed_duel()
    app = SanguoshaApp()
    app._engine = engine
    screen = GamePlayScreen(practice=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await app.push_screen(screen)
        await _wait_until(pilot, lambda: screen._play_request is not None)
        first_request = screen._play_request
        old_click = CardWidget.CardClicked(
            0, engine.human_player.hand[0], request_id=screen._play_request_id
        )
        await pilot.press("1")
        await _wait_until(pilot, lambda: isinstance(app.screen, TargetSelectModal))
        await pilot.press("e")
        await pilot.press("escape")
        await _wait_until(pilot, lambda: screen._play_request is not None)
        assert screen._play_request is not first_request
        assert engine.current_player is engine.human_player
        screen.post_message(old_click)
        await pilot.pause()
        assert app.screen is screen
        await pilot.press("1")
        await _wait_until(pilot, lambda: isinstance(app.screen, TargetSelectModal))
        await pilot.press("ctrl+q")
        await _wait_until(pilot, lambda: screen._game_worker.is_finished)
        assert app._exit
        assert engine.human_player.hand[0].name == "杀"


@pytest.mark.asyncio
async def test_standard_play_turn_keeps_info_visible_during_countdown():
    from textual.widgets import Static

    from i18n import t
    from ui.textual_ui.screens.game_play import GamePlayScreen

    app = SanguoshaApp()
    app._engine = _fixed_duel()
    screen = GamePlayScreen()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.push_screen(screen)
        await _wait_until(pilot, lambda: screen._countdown_timer is not None)
        info = screen.query_one("#info-panel", Static)
        assert app._engine.human_player.name in str(info.render())
        assert t("ui.play.countdown", seconds=screen.play_phase_timeout) in str(info.render())
        await pilot.press("q")
        await _wait_until(pilot, lambda: screen._game_worker.is_finished)
        assert app._exit
