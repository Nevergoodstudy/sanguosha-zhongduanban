"""目标选择弹窗 (M-C C5)

替代原 info-panel 纯文本编号选择。
可选目标以按钮网格排列，点击选中后 dismiss(index)。

dismiss(int)  → 选中目标索引
dismiss(None) → 取消选择
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Button, Static

from game.player import Identity
from i18n import card_name, identity_name
from i18n import t as _t
from ui.textual_ui.modals.base import AnimatedModalScreen

if TYPE_CHECKING:
    pass


class TargetSelectModal(AnimatedModalScreen[Optional[int]]):
    """目标选择弹窗 — 点击目标按钮选中"""

    BINDINGS = [Binding("escape", "cancel", show=False)]

    def action_cancel(self) -> None:
        self.dismiss()

    DEFAULT_CSS = """
    TargetSelectModal {
        align: center middle;
        background: $background 70%;
    }
    TargetSelectModal > #target-container {
        width: 60;
        max-width: 85%;
        height: auto;
        max-height: 80%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
        overflow-y: auto;
    }
    TargetSelectModal #target-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    TargetSelectModal .target-btn {
        width: 100%;
        margin: 0 0 1 0;
    }
    TargetSelectModal Button:focus {
        text-style: bold reverse;
    }
    TargetSelectModal #btn-cancel-target {
        width: 100%;
        margin-top: 1;
    }
    """

    def __init__(self, targets: list, prompt: str | None = None):
        """Args:
        targets: Player 对象列表
        prompt: 提示文字
        """
        super().__init__()
        self._targets = targets
        self._prompt = prompt or _t("ui.modal.target")

    def compose(self) -> ComposeResult:
        with Container(id="target-container"):
            yield Static(self._prompt, id="target-title", markup=False)
            for i, t in enumerate(self._targets):
                hero_name = t.hero.name if t.hero else "?"
                hp_bar = "●" * t.hp + "○" * (t.max_hp - t.hp)
                # 身份信息（主公公开）
                identity_str = ""
                if hasattr(t, "identity") and t.identity == Identity.LORD:
                    identity_str = f" · {identity_name(Identity.LORD.value)}"
                # 装备简要
                equip_parts = []
                if hasattr(t, "equipment"):
                    if t.equipment.weapon:
                        equip_parts.append(f"⚔{card_name(t.equipment.weapon.name)}")
                    if t.equipment.armor:
                        equip_parts.append(f"🛡{card_name(t.equipment.armor.name)}")
                equip_str = " ".join(equip_parts)
                label = (
                    f"{t.name} ({hero_name}){identity_str}  "
                    f"{hp_bar} {t.hp}/{t.max_hp}  "
                    f'{_t("ui.modal.hand_count", count=t.hand_count)}  {equip_str}'
                )
                yield Button(label, id=f"target-{i}", classes="target-btn", variant="primary")
            yield Button(_t("ui.modal.cancel"), id="btn-cancel-target", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("target-"):
            idx = int(btn_id.split("-")[1])
            self.dismiss(idx)
        elif btn_id == "btn-cancel-target":
            self.dismiss(None)
