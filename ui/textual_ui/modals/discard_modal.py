"""弃牌阶段弹窗 (P0-3)

让人类玩家在弃牌阶段选择要弃掉的手牌。
支持多选，必须恰好弃掉 need_count 张牌才能确认。

dismiss(List[int]) → 选中的手牌索引列表
dismiss(None)      → 超时/异常（自动弃末尾的牌）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.timer import Timer
from textual.widgets import Button, Static

from i18n import card_name
from i18n import t as _t
from ui.textual_ui.modals.base import AnimatedModalScreen

if TYPE_CHECKING:
    from game.card import Card


class DiscardModal(AnimatedModalScreen[Optional[list[int]]]):
    """弃牌阶段弹窗"""

    DEFAULT_CSS = """
    DiscardModal {
        align: center middle;
        background: $background 70%;
    }
    DiscardModal > #discard-container {
        width: 70;
        max-width: 90%;
        height: auto;
        max-height: 85%;
        border: thick $warning;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    DiscardModal #discard-title {
        text-align: center;
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    DiscardModal #discard-status {
        text-align: center;
        margin-bottom: 1;
    }
    DiscardModal #discard-countdown {
        text-align: center;
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    DiscardModal .card-row {
        height: auto;
        layout: horizontal;
        overflow-x: auto;
    }
    DiscardModal .discard-card-btn {
        min-width: 18;
        margin: 0 1 1 0;
    }
    DiscardModal Button:focus {
        text-style: bold reverse;
    }
    DiscardModal .discard-card-btn.selected {
        border: heavy $error;
        background: $error-darken-2;
    }
    DiscardModal #btn-confirm-discard {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, cards: list[Card], need_count: int, countdown: int = 30):
        """Args:
        cards: 玩家当前手牌列表
        need_count: 需要弃掉的张数
        countdown: 倒计时秒数，0 表示不倒计时
        """
        super().__init__()
        self._cards = cards
        self._need_count = need_count
        self._selected: set[int] = set()
        self._remaining = countdown
        self._countdown = countdown
        self._timer: Timer | None = None

    def compose(self) -> ComposeResult:
        with Container(id="discard-container"):
            yield Static(
                _t("ui.modal.discard_title", count=self._need_count),
                id="discard-title",
            )
            yield Static(
                self._status_text(),
                id="discard-status",
            )
            if self._countdown > 0:
                yield Static(_t("ui.play.countdown", seconds=self._remaining), id="discard-countdown")

            with Horizontal(classes="card-row"):
                for i, card in enumerate(self._cards):
                    label = f"{card.suit.symbol}{card.number_str} {card_name(card.name)}"
                    yield Button(
                        label,
                        id=f"dcard-{i}",
                        classes="discard-card-btn",
                        variant="default",
                    )

            yield Button(
                _t("ui.modal.discard"),
                id="btn-confirm-discard",
                variant="success",
                disabled=True,
            )

    def on_mount(self) -> None:
        super().on_mount()  # 淡入动画
        if self._countdown > 0:
            self._timer = self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        self._remaining -= 1
        try:
            cd = self.query_one("#discard-countdown", Static)
            cd.update(_t("ui.play.countdown", seconds=self._remaining))
        except Exception:
            pass
        if self._remaining <= 0:
            if self._timer:
                self._timer.stop()
            # 超时：自动选择最后 N 张牌
            auto = list(range(len(self._cards) - self._need_count, len(self._cards)))
            self.dismiss(auto)

    def _status_text(self) -> str:
        selected = len(self._selected)
        color = "green" if selected == self._need_count else "yellow"
        status = _t("ui.modal.cards_selected", count=selected, total=self._need_count)
        return f"[{color}]{status}[/{color}]"

    def _refresh_ui(self) -> None:
        """刷新选中状态"""
        try:
            self.query_one("#discard-status", Static).update(self._status_text())
        except Exception:
            pass

        # 更新按钮样式
        for i in range(len(self._cards)):
            try:
                btn = self.query_one(f"#dcard-{i}", Button)
                if i in self._selected:
                    btn.add_class("selected")
                    btn.variant = "error"
                else:
                    btn.remove_class("selected")
                    btn.variant = "default"
            except Exception:
                pass

        # 更新确认按钮
        try:
            confirm = self.query_one("#btn-confirm-discard", Button)
            ok = len(self._selected) == self._need_count
            confirm.disabled = not ok
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        if btn_id.startswith("dcard-"):
            idx = int(btn_id.split("-")[1])
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                if len(self._selected) < self._need_count:
                    self._selected.add(idx)
            self._refresh_ui()

        elif btn_id == "btn-confirm-discard":
            if len(self._selected) == self._need_count:
                if self._timer:
                    self._timer.stop()
                self.dismiss(sorted(self._selected))
