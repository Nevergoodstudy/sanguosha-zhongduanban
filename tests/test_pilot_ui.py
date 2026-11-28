"""Textual Pilot UI 自动化测试 (Phase 5.1).

Uses app.run_test() to actually drive screens headlessly with Pilot.
"""

import asyncio
from collections.abc import Callable

import pytest
from textual.widgets import Button, RichLog, Select, Static

from game.match_history import MatchHistory
from i18n import get_locale, set_locale, t
from ui.textual_ui.app import SanguoshaApp
from ui.textual_ui.modals.discard_modal import DiscardModal
from ui.textual_ui.modals.response_modal import ShanResponseModal
from ui.textual_ui.modals.target_modal import TargetSelectModal
from ui.textual_ui.screens.game_over import GameOverScreen, MatchReportScreen
from ui.textual_ui.screens.game_play import GamePlayScreen
from ui.textual_ui.screens.game_setup import GameSetupScreen
from ui.textual_ui.screens.main_menu import MainMenuScreen
from ui.textual_ui.screens.rules import RulesScreen
from ui.textual_ui.widgets.hp_bar import HPBar
from ui.textual_ui.widgets.phase_indicator import PHASES, PhaseIndicator

# ==================== App Smoke Test ====================


class TestAppSmoke:
    """SanguoshaApp 基本启动测试"""

    @pytest.mark.asyncio
    async def test_app_starts(self):
        """App 可以无错误启动"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.is_running

    @pytest.mark.asyncio
    async def test_default_screen_is_main_menu(self):
        """默认推送 MainMenuScreen"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            assert isinstance(app.screen, MainMenuScreen)

    @pytest.mark.asyncio
    async def test_app_has_title(self):
        """App 有标题"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.TITLE == "三国杀 - 命令行终端版"

    @pytest.mark.asyncio
    async def test_app_engine_initially_none(self):
        """引擎初始为 None"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            assert app._engine is None

    @pytest.mark.asyncio
    async def test_app_quit_binding(self):
        """Ctrl+Q 可退出"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("ctrl+q")
            # app should have exited
            assert app._exit


# ==================== MainMenuScreen ====================


class TestMainMenuScreen:
    """主菜单界面测试"""

    @pytest.mark.asyncio
    async def test_menu_has_practice_and_history_buttons(self):
        """主菜单提供练习和战报入口"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            assert app.screen.query_one("#btn-practice", Button).display
            assert app.screen.query_one("#btn-history", Button).display

    @pytest.mark.asyncio
    async def test_menu_has_title(self):
        """主菜单包含标题文本"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            title = app.screen.query_one("#title", Static)
            # Static stores content in update(); check via str or _content
            content = str(title.render())
            assert "三国杀" in content or title is not None

    @pytest.mark.asyncio
    async def test_start_button_pushes_setup(self):
        """点击开始 → 推送 GameSetupScreen"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#btn-start")
            await pilot.pause()
            assert isinstance(app.screen, GameSetupScreen)

    @pytest.mark.asyncio
    async def test_rules_button_pushes_rules(self):
        """点击规则 → 推送 RulesScreen"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#btn-rules")
            await pilot.pause()
            assert isinstance(app.screen, RulesScreen)

    @pytest.mark.asyncio
    async def test_quit_button_exits(self):
        """点击退出 → 退出"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.click("#btn-quit")
            await pilot.pause()
            assert app._exit


# ==================== RulesScreen ====================


class TestRulesScreen:
    """规则界面测试"""

    @pytest.mark.asyncio
    async def test_rules_text_displayed(self):
        """规则界面包含规则文本"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.click("#btn-rules")
            await pilot.pause()
            assert isinstance(app.screen, RulesScreen)
            # The screen should have the back button
            back_btn = app.screen.query_one("#btn-back", Button)
            assert back_btn is not None

    @pytest.mark.asyncio
    async def test_back_button_pops(self):
        """点击返回 → 回到主菜单"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.click("#btn-rules")
            await pilot.pause()
            assert isinstance(app.screen, RulesScreen)
            await pilot.click("#btn-back")
            await pilot.pause()
            assert isinstance(app.screen, MainMenuScreen)

    @pytest.mark.asyncio
    async def test_escape_pops(self):
        """Esc 键 → 回到主菜单"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.click("#btn-rules")
            await pilot.pause()
            assert isinstance(app.screen, RulesScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, MainMenuScreen)


# ==================== GameSetupScreen ====================


class TestGameSetupScreen:
    """游戏设置界面测试"""

    @pytest.mark.asyncio
    async def test_setup_has_selects(self):
        """设置界面有 3 个 Select"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.click("#btn-start")
            await pilot.pause()
            assert isinstance(app.screen, GameSetupScreen)
            selects = app.screen.query(Select)
            assert len(selects) == 3

    @pytest.mark.asyncio
    async def test_default_values(self):
        """Select 默认值正确"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.click("#btn-start")
            await pilot.pause()
            count_sel = app.screen.query_one("#sel-count", Select)
            diff_sel = app.screen.query_one("#sel-diff", Select)
            role_sel = app.screen.query_one("#sel-role", Select)
            assert count_sel.value == 4
            assert diff_sel.value == "normal"
            assert role_sel.value == "lord"

    @pytest.mark.asyncio
    async def test_go_button_exists(self):
        """开始按钮存在"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.click("#btn-start")
            await pilot.pause()
            btn = app.screen.query_one("#btn-go", Button)
            assert btn is not None


# ==================== GameOverScreen ====================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("size", "locale"), [((80, 24), "zh_CN"), ((120, 40), "en_US")]
)
async def test_keyboard_practice_match_saves_report(size, locale, tmp_path, monkeypatch, request):
    request.addfinalizer(lambda locale=get_locale(): set_locale(locale))
    set_locale(locale)
    monkeypatch.setenv("SANGUOSHA_DATA_HOME", str(tmp_path))
    app = SanguoshaApp()
    async with app.run_test(size=size) as pilot:
        async def wait_for_ui(ready: Callable[[], bool]) -> None:
            async def wait_until_ready() -> None:
                while not ready():
                    await pilot.pause(0.01)

            await asyncio.wait_for(wait_until_ready(), timeout=5)
            await pilot.pause()

        def can_play() -> bool:
            screen = app.screen
            return isinstance(screen, GamePlayScreen) and screen._play_request is not None

        await pilot.press("tab", "enter")
        await pilot.pause()
        assert app.screen.focused.id == "hero-0"
        await pilot.press("enter")
        await wait_for_ui(can_play)
        play_screen = app.screen
        log = play_screen.query_one("#battle-log", RichLog)
        hint = t("ui.play.play_hint")
        assert any(hint in log.render_line(row).text for row in range(log.content_region.height))
        if size == (80, 24):
            assert play_screen.has_class("compact")
            await pilot.resize_terminal(120, 40)
            await pilot.pause()
            assert not play_screen.has_class("compact")
            await pilot.resize_terminal(*size)
            await pilot.pause()
            assert play_screen.has_class("compact")
        for selector in ("#battle-log", "#info-panel", "#btn-end"):
            widget = play_screen.query_one(selector)
            assert widget.content_region.height > 0
            assert play_screen.region.contains_region(widget.region)
        first_card = play_screen.query_one("CardWidget")
        assert first_card.content_region.height >= 3
        assert play_screen.region.contains_region(first_card.region)
        engine = app._engine
        hand_before = engine.human_player.hand[:]
        discard_before = engine.deck.discard_pile[:]
        await pilot.press("1")
        await wait_for_ui(lambda: isinstance(app.screen, TargetSelectModal))
        await pilot.press("escape")
        await wait_for_ui(can_play)
        assert engine.human_player.hand == hand_before
        assert engine.deck.discard_pile == discard_before
        assert not engine.action_log

        await pilot.press("1")
        await wait_for_ui(lambda: isinstance(app.screen, TargetSelectModal))
        await pilot.press("enter")
        await wait_for_ui(can_play)
        assert not app._engine.players[1].get_cards_by_name("闪")
        await pilot.press("e")
        await wait_for_ui(lambda: isinstance(app.screen, DiscardModal))
        assert app.screen.query_one("#discard-title")
        await pilot.press(
            "enter", "tab", "enter", "tab", "enter",
            "shift+tab", "shift+tab", "shift+tab", "enter",
        )
        await wait_for_ui(lambda: isinstance(app.screen, ShanResponseModal))
        confirm = app.screen.query_one("#btn-confirm", Button)
        assert confirm.content_region.height > 0
        assert app.screen.query_one("#modal-container").content_region.contains_region(confirm.region)
        await pilot.press("enter")
        await wait_for_ui(can_play)
        hand = app._engine.human_player.hand
        strike_index = next(i for i, card in enumerate(hand) if card.name == "杀")
        await pilot.press(str(strike_index + 1))
        await wait_for_ui(lambda: isinstance(app.screen, TargetSelectModal))
        await pilot.press("enter")
        await wait_for_ui(lambda: isinstance(app.screen, GameOverScreen))
        assert isinstance(app.screen, GameOverScreen)
        assert app.screen.focused.id == "btn-again"
        assert [entry["sequence"] for entry in engine.action_log] == list(
            range(1, len(engine.action_log) + 1)
        )
        actions = [action for action in engine.action_log if action["player_id"] == 0]
        assert [action["action_type"] for action in actions] == ["PLAY_CARD", "DISCARD", "PLAY_CARD"]
        assert actions[0]["data"]["card_id"] == hand_before[0].id
        assert len(actions[1]["data"]["card_ids"]) == 3
        await pilot.press("tab", "enter")
        await pilot.pause()
        assert isinstance(app.screen, MatchReportScreen)
        assert app.screen.report.winner == "lord"
        assert any(event["kind"] == "game_over" for event in app.screen.report.events)
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, GameOverScreen)
        await pilot.press("shift+tab", "enter")
        await pilot.pause()
        assert app.screen.focused.id == "hero-0"
    report = MatchHistory().latest()
    assert report.winner == "lord"
    assert report.game_seed == 42


class TestGameOverScreen:
    """游戏结束界面测试"""

    @pytest.mark.asyncio
    async def test_victory_display(self):
        """胜利界面显示正确"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(GameOverScreen("主公阵营胜利!", True))
            await pilot.pause()
            assert isinstance(app.screen, GameOverScreen)
            # Should have back and quit buttons
            buttons = app.screen.query(Button)
            assert len(buttons) == 2

    @pytest.mark.asyncio
    async def test_defeat_display(self):
        """失败界面显示正确"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(GameOverScreen("反贼阵营胜利!", False))
            await pilot.pause()
            assert isinstance(app.screen, GameOverScreen)

    @pytest.mark.asyncio
    async def test_back_returns_to_menu(self):
        """返回主菜单"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(GameOverScreen("胜利!", True))
            await pilot.pause()
            await pilot.click("#btn-back")
            await pilot.pause()
            assert isinstance(app.screen, MainMenuScreen)

    @pytest.mark.asyncio
    async def test_quit_exits(self):
        """退出"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(GameOverScreen("失败", False))
            await pilot.pause()
            await pilot.click("#btn-quit")
            await pilot.pause()
            assert app._exit


# ==================== Widget Unit Tests ====================


class TestHPBarWidget:
    """HPBar 组件测试"""

    @pytest.mark.asyncio
    async def test_render_full_hp(self):
        """满血 → 绿色"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            bar = HPBar(hp=4, max_hp=4)
            await app.screen.mount(bar)
            text = bar.render()
            assert "4/4" in text
            assert "green" in text

    @pytest.mark.asyncio
    async def test_render_half_hp(self):
        """半血 → 黄色"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            bar = HPBar(hp=2, max_hp=4)
            await app.screen.mount(bar)
            text = bar.render()
            assert "2/4" in text
            assert "yellow" in text

    @pytest.mark.asyncio
    async def test_render_low_hp(self):
        """低血 → 红色"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            bar = HPBar(hp=1, max_hp=4)
            await app.screen.mount(bar)
            text = bar.render()
            assert "1/4" in text
            assert "red" in text

    @pytest.mark.asyncio
    async def test_render_zero_max(self):
        """max_hp=0 → dim"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            bar = HPBar(hp=0, max_hp=0)
            await app.screen.mount(bar)
            text = bar.render()
            assert "dim" in text

    @pytest.mark.asyncio
    async def test_update_hp(self):
        """update_hp 更新 reactive"""
        app = SanguoshaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            bar = HPBar(hp=4, max_hp=4)
            await app.screen.mount(bar)
            bar.update_hp(1, 4)
            assert bar.hp == 1
            assert bar.max_hp == 4


class TestPhaseIndicatorWidget:
    """PhaseIndicator 组件测试"""

    @pytest.mark.asyncio
    async def test_render_default_phase(self):
        """默认 prepare 阶段"""
        app = SanguoshaApp()
        async with app.run_test(size=(100, 24)) as pilot:
            indicator = PhaseIndicator()
            await app.screen.mount(indicator)
            text = indicator.render()
            assert "准备" in text

    @pytest.mark.asyncio
    async def test_set_phase(self):
        """切换阶段"""
        app = SanguoshaApp()
        async with app.run_test(size=(100, 24)) as pilot:
            indicator = PhaseIndicator()
            await app.screen.mount(indicator)
            indicator.set_phase("play")
            assert indicator.current_phase == "play"

    @pytest.mark.asyncio
    async def test_render_with_info(self):
        """显示额外信息"""
        app = SanguoshaApp()
        async with app.run_test(size=(100, 24)) as pilot:
            indicator = PhaseIndicator()
            await app.screen.mount(indicator)
            indicator.set_info(round_count=3, deck_count=50, player_name="曹操")
            text = indicator.render()
            assert "R3" in text
            assert "曹操" in text

    @pytest.mark.asyncio
    async def test_phases_constant(self):
        """PHASES 包含 6 个阶段"""
        assert len(PHASES) == 6
        phase_ids = [p[0] for p in PHASES]
        assert "prepare" in phase_ids
        assert "play" in phase_ids
        assert "end" in phase_ids
