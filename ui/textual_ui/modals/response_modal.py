"""响应类 ModalScreen 弹窗 (M-C C1/C2/C3)

ResponseModalBase — 半透明背景 + 倒计时 + dismiss 模式基类
ShanResponseModal — "是否出闪"
ShaResponseModal  — "是否出杀"（决斗/南蛮/万箭）
TaoResponseModal  — "是否使用桃"（濒死救援）

线程安全模式:
  push_screen(Modal, callback) → user clicks → dismiss(result) → callback

ModalScreen[T] 的 T 为 dismiss 返回值类型:
  - True  → 使用该卡牌
  - False / None → 放弃
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.timer import Timer
from textual.widgets import Button, Static

from i18n import card_name
from i18n import t as _t
from ui.textual_ui.modals.base import AnimatedModalScreen

if TYPE_CHECKING:
    pass


class ResponseModalBase(AnimatedModalScreen[bool]):
    """响应类弹窗基类

    半透明背景覆盖，居中弹窗框，可选倒计时自动拒绝。
    子类只需定义 title_text / body_text / confirm_label / reject_label。
    """

    BINDINGS = [Binding("escape", "reject", show=False)]

    DEFAULT_CSS = """
    ResponseModalBase {
        align: center middle;
        background: $background 70%;
    }
    ResponseModalBase > #modal-container {
        width: 55;
        max-width: 80%;
        height: auto;
        max-height: 80%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ResponseModalBase #modal-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    ResponseModalBase #modal-body {
        text-align: center;
        margin-bottom: 1;
    }
    ResponseModalBase #modal-countdown {
        text-align: center;
        color: $warning;
        text-style: bold;
        margin-bottom: 1;
    }
    ResponseModalBase #modal-cards-info {
        margin-bottom: 1;
        text-align: center;
    }
    ResponseModalBase .btn-row {
        layout: horizontal;
        height: auto;
        margin-top: 1;
    }
    ResponseModalBase Button:focus {
        text-style: bold reverse;
    }
    ResponseModalBase .btn-row Button {
        width: 1fr;
        margin: 0 1;
    }
    """

    # 子类可覆盖
    title_key = "ui.modal.choose"
    body_key: str | None = None
    confirm_key = "ui.modal.confirm"
    countdown_seconds = 0

    def __init__(
        self,
        title: str = "",
        body: str = "",
        cards: list | None = None,
        countdown: int | None = None,
    ):
        super().__init__()
        self.title_text = title or _t(self.title_key)
        self.body_text = body or (_t(self.body_key) if self.body_key else "")
        self.countdown_seconds = self.countdown_seconds if countdown is None else countdown
        self._remaining = self.countdown_seconds
        self._countdown_timer: Timer | None = None
        self.cards_info = "  ".join(
            f"{card.suit.symbol}{card.number_str} {card_name(card.name)}" for card in (cards or ())
        )

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Static(self.title_text, id="modal-title", markup=False)
            if self.body_text:
                yield Static(self.body_text, id="modal-body", markup=False)
            if self.cards_info:
                yield Static(
                    _t("ui.modal.cards_available", cards=self.cards_info),
                    id="modal-cards-info",
                    markup=False,
                )
            if self.countdown_seconds > 0:
                yield Static(_t("ui.play.countdown", seconds=self._remaining), id="modal-countdown")
            with Horizontal(classes="btn-row"):
                yield Button(_t(self.confirm_key), id="btn-confirm", variant="success")
                yield Button(_t("ui.modal.pass"), id="btn-reject", variant="error")

    def on_mount(self) -> None:
        super().on_mount()  # 淡入动画
        if self.countdown_seconds > 0:
            self._countdown_timer = self.set_interval(1.0, self._tick)

    def _tick(self) -> None:
        """倒计时每秒 tick"""
        self._remaining -= 1
        try:
            cd_widget = self.query_one("#modal-countdown", Static)
            cd_widget.update(_t("ui.play.countdown", seconds=self._remaining))
        except Exception:
            pass
        if self._remaining <= 0:
            if self._countdown_timer:
                self._countdown_timer.stop()
            self.dismiss(False)  # 超时自动拒绝

    def action_reject(self) -> None:
        self._answer(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self._answer(event.button.id == "btn-confirm")

    def _answer(self, accepted: bool) -> None:
        if self._countdown_timer:
            self._countdown_timer.stop()
        self.dismiss(accepted)


class ShanResponseModal(ResponseModalBase):
    """Respond to a Strike with Dodge."""

    title_key = "ui.modal.shan_title"
    body_key = "ui.modal.shan_body"
    confirm_key = "ui.modal.shan"
    countdown_seconds = 15


class ShaResponseModal(ResponseModalBase):
    """Respond with Strike."""

    title_key = "ui.modal.sha_title"
    body_key = "ui.modal.sha_body"
    confirm_key = "ui.modal.sha"
    countdown_seconds = 15


class TaoResponseModal(ResponseModalBase):
    """Offer Peach to a dying player."""

    title_key = "ui.modal.tao_title"
    body_key = "ui.modal.tao_body"
    confirm_key = "ui.modal.tao"
    countdown_seconds = 20

    def __init__(self, dying_name: str = "", cards=None, **kwargs):
        body = _t("ui.modal.tao_dying", name=dying_name) if dying_name else ""
        super().__init__(body=body, cards=cards, **kwargs)
