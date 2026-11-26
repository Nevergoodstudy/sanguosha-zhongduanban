"""游戏结束界面"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Static

from game.match_history import MatchResult
from i18n import identity_name, t as _t


class GameOverScreen(Screen):
    """游戏结束界面"""

    CSS = """
    GameOverScreen {
        align: center middle;
    }
    #gameover-box {
        width: 50;
        height: auto;
        border: double red;
        padding: 2;
    }
    #result-text {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    """

    def __init__(
        self, message: str, is_victory: bool, *, practice: bool = False,
        report: MatchResult | None = None, report_saved: bool = True,
    ):
        super().__init__()
        self._message = message
        self._is_victory = is_victory
        self.practice = practice
        self.report = report
        self.report_saved = report_saved

    def compose(self) -> ComposeResult:
        icon = _t("ui.result.win" if self._is_victory else "ui.result.loss")
        color = "green" if self._is_victory else "red"
        with Container(id="gameover-box"):
            yield Static(f"[bold {color}]{icon}[/bold {color}]", id="result-text")
            yield Static(self._message, markup=False)
            if self.report:
                yield Button(_t("ui.result.again"), id="btn-again", variant="success")
                yield Button(_t("ui.menu.history"), id="btn-report")
                if not self.report_saved:
                    yield Static(_t("ui.report.save_failed"))
            yield Button(_t("ui.result.menu"), id="btn-back", variant="primary")
            yield Button(_t("ui.menu.quit"), id="btn-quit", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-report":
            self.app.push_screen(MatchReportScreen(self.report))
            return
        if event.button.id == "btn-again":
            if self.practice:
                from .hero_select import HeroSelectScreen

                self.app.switch_screen(HeroSelectScreen(2, "easy", practice=True))
                return
            from .game_setup import GameSetupScreen

            self.app.switch_screen(GameSetupScreen())
            return
        if event.button.id == "btn-back":
            from .main_menu import MainMenuScreen

            while len(self.app.screen_stack) > 2:
                self.app.pop_screen()
            if not isinstance(self.app.screen, MainMenuScreen):
                self.app.switch_screen(MainMenuScreen())
            return
        if event.button.id == "btn-quit":
            self.app.exit()


class MatchReportScreen(Screen):
    """展示最近一局的结果和对局记录。"""

    BINDINGS = [Binding("escape", "close_report", show=False)]
    CSS = """
    MatchReportScreen { align: center middle; }
    #report-box {
        width: 90%;
        height: 90%;
        border: round $accent;
        padding: 1 2;
    }
    #report-events { height: 1fr; }
    """

    def __init__(self, report: MatchResult | None):
        super().__init__()
        self.report = report

    def compose(self) -> ComposeResult:
        report = self.report
        with Container(id="report-box"):
            yield Static(_t("ui.menu.history"))
            if report:
                yield Static(_t(
                    "ui.report.summary", winner=identity_name(report.winner),
                    players=report.player_count, rounds=report.rounds,
                ), markup=False)
                if report.game_version:
                    yield Static(_t("ui.report.version", version=report.game_version), markup=False)
                with VerticalScroll(id="report-events"):
                    yield Static("\n".join(
                        f"{event['turn']} · {event['message']}" for event in report.events
                    ), markup=False)
            if not report:
                yield Static(_t("ui.report.empty"))
            yield Button(_t("ui.report.back"), id="btn-report-back", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_close_report()

    def action_close_report(self) -> None:
        self.app.pop_screen()
