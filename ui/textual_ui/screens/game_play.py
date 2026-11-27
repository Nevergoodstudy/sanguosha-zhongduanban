"""游戏主界面 (M3-T02)"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import TYPE_CHECKING, TypeVar

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.worker import Worker
from textual.widgets import Button, RichLog, Static

from game.enums import GamePhase
from i18n import card_name
from i18n import t as _t

if TYPE_CHECKING:
    from game.card import Card
    from game.engine import GameEngine
    from game.player import Player


ModalResult = TypeVar("ModalResult")


class GamePlayScreen(Screen):
    """游戏主界面 (M3-T02)"""

    BINDINGS = [
        Binding("e", "end_play", _t("ui.play.end_play")),
        Binding("h", "show_help", _t("ui.play.help")),
        Binding("q", "quit_game", _t("ui.play.quit")),
        Binding("1", "play_card_1", "卡牌1", show=False),
        Binding("2", "play_card_2", "卡牌2", show=False),
        Binding("3", "play_card_3", "卡牌3", show=False),
        Binding("4", "play_card_4", "卡牌4", show=False),
        Binding("5", "play_card_5", "卡牌5", show=False),
        Binding("6", "play_card_6", "卡牌6", show=False),
        Binding("7", "play_card_7", "卡牌7", show=False),
        Binding("8", "play_card_8", "卡牌8", show=False),
        Binding("9", "play_card_9", "卡牌9", show=False),
        Binding("0", "play_card_10", "卡牌10", show=False),
    ]

    CSS = """
    GamePlayScreen {
        layout: grid;
        grid-size: 2 4;
        grid-columns: 3fr 1fr;
        grid-rows: auto auto 1fr auto;
    }
    #phase-bar {
        column-span: 2;
        height: 1;
        dock: top;
        background: $primary-darken-3;
    }
    #opponents {
        row-span: 1;
        column-span: 2;
        height: auto;
        max-height: 14;
        border: round #3498db;
        overflow-y: auto;
        padding: 0 1;
    }
    #play-area {
        column-span: 2;
        height: auto;
        max-height: 5;
    }
    #battle-log {
        height: 100%;
        border: round #2ecc71;
    }
    #info-panel {
        height: 100%;
        border: round #f39c12;
        overflow-y: auto;
    }
    #player-area {
        column-span: 2;
        height: auto;
        max-height: 16;
        border: round #27ae60;
    }
    #equip-section {
        height: auto;
        max-height: 3;
        border: dashed $secondary;
        padding: 0 1;
    }
    #hand-label {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    #hand-cards {
        height: auto;
        min-height: 7;
        layout: horizontal;
        overflow-x: auto;
    }
    .card-btn {
        min-width: 16;
        margin: 0 1;
    }
    #action-bar {
        height: 3;
        layout: horizontal;
        dock: bottom;
    }
    .action-btn {
        margin: 0 1;
    }
    .action-btn:disabled {
        opacity: 50%;
    }
    """

    DEFAULT_PLAY_PHASE_TIMEOUT = 30  # 出牌阶段默认超时秒数

    def __init__(self, *, practice: bool = False):
        super().__init__()
        self.practice = practice
        self._play_request: Future[str | None] | None = None
        self._play_request_id = 0
        self._cancel_modal: Callable[[], None] | None = None
        self._request_modal: ModalScreen | None = None
        self._quit_requested = threading.Event()
        self._game_worker: Worker | None = None
        self._countdown_remaining = 0
        self._countdown_timer = None
        self._info_text = ""
        from game.config import get_config

        self.play_phase_timeout: int | None = None if practice else max(
            1, int(get_config().play_phase_timeout or self.DEFAULT_PLAY_PHASE_TIMEOUT)
        )

    @property
    def engine(self) -> GameEngine:
        return self.app._engine

    def compose(self) -> ComposeResult:
        from ui.textual_ui.widgets.equipment_slots import EquipmentSlots
        from ui.textual_ui.widgets.phase_indicator import PhaseIndicator
        from ui.textual_ui.widgets.play_area import PlayArea

        yield PhaseIndicator(id="phase-bar")
        yield VerticalScroll(id="opponents")
        yield PlayArea(id="play-area")
        yield RichLog(id="battle-log", highlight=True, markup=True, wrap=True)
        yield Static(_t("ui.play.info_panel"), id="info-panel")
        yield Container(
            EquipmentSlots(id="equip-section"),
            Static(_t("ui.play.hand_label"), id="hand-label"),
            Horizontal(id="hand-cards"),
            Horizontal(
                Button(
                    _t("ui.play.btn_play"), id="btn-play", classes="action-btn", variant="primary"
                ),
                Button(
                    _t("ui.play.btn_skill"), id="btn-skill", classes="action-btn", variant="warning"
                ),
                Button(
                    _t("ui.play.btn_end"), id="btn-end", classes="action-btn", variant="default"
                ),
                id="action-bar",
            ),
            id="player-area",
        )
        from textual.widgets import Footer

        yield Footer()

    def on_mount(self) -> None:
        """挂载后设置 UI 桥接，开始游戏循环"""
        engine = self.engine
        # 设置 TextualBridge 作为 UI
        from ui.textual_ui.bridge import TextualUIBridge

        bridge = TextualUIBridge(self)
        engine.set_ui(bridge)

        self._refresh_display()
        self._log(_t("ui.play.game_start"))

        # 显示玩家身份信息
        from game.player import Identity

        human = engine.human_player
        identity_name = human.identity.chinese_name
        self._log(
            _t(
                "ui.play.your_identity",
                name=human.name,
                hero=human.hero.name,
                identity=identity_name,
            )
        )

        # 非主公时弹出身份揭示窗口
        if human.identity != Identity.LORD:
            from ui.textual_ui.modals.identity_reveal_modal import IdentityRevealModal

            modal = IdentityRevealModal(human.identity.value, identity_name)
            self.app.push_screen(modal, callback=lambda _: self._launch_game())
            return

        self._launch_game()

    def _launch_game(self) -> None:
        self._game_worker = self._start_game_loop()

    @work(thread=True)
    def _start_game_loop(self) -> None:
        """在后台线程运行游戏主循环"""
        engine = self.engine
        from game.config import get_config
        from game.practice_checkpoint import save_practice_checkpoint

        checkpoint = self.app.practice_checkpoint if self.practice else None
        delay = get_config().ai_turn_delay
        while not self._quit_requested.is_set() and not engine.is_game_over():
            if checkpoint is not None:
                try:
                    save_practice_checkpoint(engine, checkpoint)
                except OSError as error:
                    self._post_log(_t("ui.practice.checkpoint_error", error=error))
            current = engine.current_player
            if not current.is_ai:
                self._post_log(_t("ui.play.your_turn"))
            engine.turn_manager.run_turn(
                current,
                play_human=self._human_play_loop,
                discard_human=self._human_discard,
                refresh=self._post_refresh,
                should_stop=self._quit_requested.is_set,
            )
            self._post_refresh()

            if current.is_ai:
                self._quit_requested.wait(delay)
            if self._quit_requested.is_set() or engine.is_game_over():
                break
            engine.next_turn()

        if self._quit_requested.is_set():
            return

        # 游戏结束
        winner = engine.winner_identity
        msg = engine.get_winner_message()
        # 胜利判定：基于身份阵营匹配
        from game.player import Identity

        human_id = engine.human_player.identity if engine.human_player else None
        if winner and human_id:
            # 主公和忠臣同阵营
            if winner == Identity.LORD:
                is_victory = human_id in (Identity.LORD, Identity.LOYALIST)
            elif winner == Identity.REBEL:
                is_victory = human_id == Identity.REBEL
            elif winner == Identity.SPY:
                is_victory = human_id == Identity.SPY
            else:
                is_victory = False
        else:
            is_victory = False
        from .game_over import GameOverScreen

        from game.match_history import record_completed_match

        report, saved = record_completed_match(engine, practice=self.practice)
        if checkpoint is not None and saved:
            try:
                checkpoint.unlink(missing_ok=True)
            except OSError as error:
                self._post_log(_t("ui.practice.checkpoint_error", error=error))
        self.app.call_from_thread(
            self.app.push_screen,
            GameOverScreen(
                msg, bool(is_victory), practice=self.practice, report=report, report_saved=saved
            ),
        )

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker is self._game_worker and event.worker.is_finished:
            if self._quit_requested.is_set():
                self.app.exit()

    def _human_play_loop(self, player: Player) -> None:
        """接收当前出牌请求对应的玩家输入。"""
        show_hint = True
        while not self._quit_requested.is_set() and not self.engine.is_game_over():
            action = self._wait_for_response(show_hint=show_hint)
            show_hint = False
            if self._quit_requested.is_set() or action is None or action == "end":
                return
            action_type, value = action.split(":", maxsplit=1)
            if action_type == "card":
                self._handle_card_play(player, player.hand[int(value)])
            if action_type == "skill":
                self._handle_skill_use(player, value)

    def _human_discard(self, player: Player, count: int) -> None:
        """在弃牌阶段收集当前手牌选择。"""
        from ui.textual_ui.modals.discard_modal import DiscardModal

        cards = list(player.hand)
        indices = self.wait_for_modal(
            lambda: DiscardModal(cards=cards, need_count=count, countdown=0 if self.practice else 30),
            timeout=None if self.practice else 35,
        )
        if self._quit_requested.is_set():
            return
        selected = cards[-count:] if indices is None else [cards[i] for i in indices]
        self.engine.discard_for_turn(player, selected)

    def _handle_card_play(self, player: Player, card: Card) -> None:
        """处理出牌"""
        from game.card import CardName, CardSubtype, CardType

        engine = self.engine

        if card.card_type == CardType.EQUIPMENT:
            engine.play_hand_card(player, card)
        elif card.name == CardName.SHA:
            if not player.can_use_sha():
                from game.constants import SkillId

                if not player.has_skill(SkillId.PAOXIAO):
                    self._post_log("⚠ 本回合已使用过杀")
                    return
            targets = engine.get_targets_in_range(player)
            if not targets:
                self._post_log("⚠ 没有可攻击的目标")
                return
            target = self._wait_for_target(
                player, targets, _t("ui.modal.target_for", card=card_name(card.name))
            )
            if target:
                engine.play_hand_card(player, card, [target])
        elif card.name == CardName.TAO:
            if player.hp >= player.max_hp:
                self._post_log("⚠ 体力已满")
                return
            engine.play_hand_card(player, card)
        elif card.name == CardName.SHAN:
            self._post_log("⚠ 闪不能主动使用")
            return
        elif card.name == CardName.WUXIE:
            self._post_log("⚠ 无懈可击不能主动使用")
            return
        elif card.name == CardName.JUEDOU:
            others = engine.get_other_players(player)
            target = self._wait_for_target(
                player, others, _t("ui.modal.target_for", card=card_name(card.name))
            )
            if target:
                engine.play_hand_card(player, card, [target])
        elif card.name in [CardName.GUOHE, CardName.SHUNSHOU]:
            others = engine.get_other_players(player)
            valid = [t for t in others if t.has_any_card()]
            if card.name == CardName.SHUNSHOU:
                valid = [t for t in valid if engine.calculate_distance(player, t) <= 1]
            if not valid:
                self._post_log("⚠ 没有有效目标")
                return
            target = self._wait_for_target(
                player, valid, _t("ui.modal.target_for", card=card_name(card.name))
            )
            if target:
                engine.play_hand_card(player, card, [target])
        elif card.name == CardName.LEBUSISHU:
            # 乐不思蜀: 选择一个非自己的目标（无距离限制）
            others = engine.get_other_players(player)
            # 排除已有乐不思蜀的目标
            valid = [
                t for t in others if not any(c.name == CardName.LEBUSISHU for c in t.judge_area)
            ]
            if not valid:
                self._post_log("⚠ 没有有效目标")
                return
            target = self._wait_for_target(
                player, valid, _t("ui.modal.target_for", card=card_name(card.name))
            )
            if target:
                engine.play_hand_card(player, card, [target])
        elif card.name == CardName.BINGLIANG:
            # 兵粮寸断: 选择距离≤1的非自己目标
            others = engine.get_other_players(player)
            valid = [
                t
                for t in others
                if engine.calculate_distance(player, t) <= 1
                and not any(c.name == CardName.BINGLIANG for c in t.judge_area)
            ]
            if not valid:
                self._post_log("⚠ 没有有效目标（需距离≤1）")
                return
            target = self._wait_for_target(
                player, valid, _t("ui.modal.target_for", card=card_name(card.name))
            )
            if target:
                engine.play_hand_card(player, card, [target])
        elif card.name == CardName.HUOGONG:
            # 火攻: 选择一个有手牌的目标（可选自己）
            alive = [p for p in engine.players if p.is_alive and p.hand_count > 0]
            if not alive:
                self._post_log("⚠ 没有有手牌的目标")
                return
            target = self._wait_for_target(
                player, alive, _t("ui.modal.target_for", card=card_name(card.name))
            )
            if target:
                engine.play_hand_card(player, card, [target])
        elif card.name == CardName.JIEDAO:
            # 借刀杀人: 先选有武器的其他玩家(wielder)，再选 wielder 攻击范围内的目标
            others = engine.get_other_players(player)
            with_weapon = [t for t in others if t.equipment.weapon and t.is_alive]
            if not with_weapon:
                self._post_log("⚠ 没有装备武器的目标")
                return
            wielder = self._wait_for_target(player, with_weapon, _t("ui.modal.target_weapon"))
            if not wielder:
                return
            # 找 wielder 攻击范围内的目标（不含 wielder 自身和 player）
            sha_targets = [
                t
                for t in engine.players
                if t.is_alive
                and t != wielder
                and t != player
                and engine.is_in_attack_range(wielder, t)
            ]
            if not sha_targets:
                self._post_log(f"⚠ {wielder.name} 攻击范围内没有有效目标")
                return
            sha_target = self._wait_for_target(
                player, sha_targets, _t("ui.modal.target_borrowed_strike", name=wielder.name)
            )
            if sha_target:
                engine.play_hand_card(player, card, [wielder, sha_target])
        elif card.name == CardName.TIESUO:
            # 铁索连环: 选择0-2个目标（0=重铸）
            others = [p for p in engine.players if p.is_alive]
            targets = self._wait_for_multi_targets(
                player, others, _t("ui.modal.target_chain"), min_count=0, max_count=2
            )
            if targets is None:
                return  # 取消
            engine.play_hand_card(player, card, targets)
        elif card.subtype == CardSubtype.ALCOHOL:
            # 酒: 检查本回合是否已使用
            if player.alcohol_used:
                self._post_log("⚠ 本回合已使用过酒")
                return
            engine.play_hand_card(player, card)
        else:
            # 群体锦囊(南蛮/万箭/桃园/闪电)/其他
            engine.play_hand_card(player, card)

    def _handle_skill_use(self, player: Player, skill_id: str) -> None:
        """处理技能使用"""
        engine = self.engine
        if engine.skill_system:
            engine.skill_system.use_skill(skill_id, player)

    # ==================== 线程间通信 ====================

    def _wait_for_response(self, *, show_hint: bool) -> str | None:
        """为一次出牌输入建立独立请求。"""
        request: Future[str | None] = Future()
        self.app.call_from_thread(self._set_waiting, request, show_hint=show_hint)
        return request.result()

    def wait_for_modal(
        self, modal_factory: Callable[[], ModalScreen[ModalResult]], *, timeout: float | None
    ) -> ModalResult | None:
        """等待当前弹窗的结果，并在超时或退出时关闭弹窗。"""
        request: Future[ModalResult | None] = Future()

        def finish(result: ModalResult | None) -> None:
            if request.done():
                return
            self._cancel_modal = None
            self._request_modal = None
            request.set_result(result)

        def open_modal() -> None:
            if self._quit_requested.is_set():
                request.set_result(None)
                return
            modal = modal_factory()
            self._request_modal = modal
            self._cancel_modal = lambda: finish(None)
            self.app.push_screen(modal, callback=finish)

        def expire() -> None:
            if request.done():
                return
            modal = self._request_modal
            if self.app.screen is modal:
                modal.dismiss()
                return
            finish(None)

        self.app.call_from_thread(open_modal)
        try:
            return request.result(timeout)
        except TimeoutError:
            self.app.call_from_thread(expire)
            return request.result()

    def _wait_for_target(self, player, targets, prompt: str) -> Player | None:
        from ui.textual_ui.modals.target_modal import TargetSelectModal

        self.app.call_from_thread(self._highlight_targets, targets)
        index = self.wait_for_modal(
            lambda: TargetSelectModal(targets=targets, prompt=prompt),
            timeout=None if self.practice else 65,
        )
        if self.app.is_running:
            self.app.call_from_thread(self._clear_target_highlights)
        return None if index is None else targets[index]

    def _wait_for_multi_targets(
        self, player, targets, prompt: str, min_count: int = 0, max_count: int = 2
    ) -> list[Player] | None:
        from ui.textual_ui.modals.multi_target_modal import MultiTargetModal

        self.app.call_from_thread(self._highlight_targets, targets)
        indices = self.wait_for_modal(
            lambda: MultiTargetModal(
                targets=targets, prompt=prompt, min_count=min_count, max_count=max_count
            ),
            timeout=None if self.practice else 65,
        )
        if self.app.is_running:
            self.app.call_from_thread(self._clear_target_highlights)
        return None if indices is None else [targets[i] for i in indices]

    def _highlight_targets(self, targets: list) -> None:
        """为合法目标的 PlayerPanel 添加 .targetable 高亮 + 呼吸脉冲 (P1-3)"""
        try:
            from ui.textual_ui.widgets.player_panel import PlayerPanel

            opp_container = self.query_one("#opponents", VerticalScroll)
            target_ids = {id(t) for t in targets}
            for panel in opp_container.query(PlayerPanel):
                if id(panel._player) in target_ids:
                    panel.add_class("targetable")
                    panel.start_pulse()
                else:
                    panel.remove_class("targetable")
                    panel.stop_pulse()
        except Exception:
            pass

    def _clear_target_highlights(self) -> None:
        """移除所有 PlayerPanel 的 .targetable 高亮 + 停止脉冲 (P1-3)"""
        try:
            from ui.textual_ui.widgets.player_panel import PlayerPanel

            opp_container = self.query_one("#opponents", VerticalScroll)
            for panel in opp_container.query(PlayerPanel):
                panel.remove_class("targetable")
                panel.stop_pulse()
        except Exception:
            pass

    def _set_waiting(self, request: Future[str | None], *, show_hint: bool) -> None:
        """启用本次出牌输入并开始计时。"""
        if self._quit_requested.is_set():
            request.set_result(None)
            return

        self._play_request = request
        self._play_request_id += 1
        self._refresh_display()
        if show_hint:
            self._log(_t("ui.play.play_hint"))
            self._turn_start_pulse()
        if self.play_phase_timeout is None:
            return
        self._countdown_remaining = self.play_phase_timeout
        self._update_countdown_display()
        self._countdown_timer = self.set_interval(1, lambda: self._tick_countdown(request))

    def _turn_start_pulse(self) -> None:
        """回合开始特效: 对 info-panel 执行快速 opacity 脉冲 (P3-1)"""
        try:
            info_panel = self.query_one("#info-panel", Static)
            info_panel.add_class("active-turn-glow")
            info_panel.styles.animate(
                "opacity",
                value=0.5,
                duration=0.15,
                easing="out_cubic",
                on_complete=lambda: info_panel.styles.animate(
                    "opacity",
                    value=1.0,
                    duration=0.25,
                    easing="in_out_cubic",
                    on_complete=lambda: info_panel.remove_class("active-turn-glow"),
                ),
            )
        except Exception:
            pass

    def _tick_countdown(self, request: Future[str | None]) -> None:
        if self._play_request is not request:
            return
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._respond("end")
            return
        self._update_countdown_display()

    @staticmethod
    def _countdown_color(secs: int, total: int = 30) -> str:
        """根据剩余秒数计算 RGB 渐变色 (P2-2)

        green(#27ae60) → yellow(#f39c12) → red(#e74c3c)
        ratio > 0.5 时 green→yellow，ratio <= 0.5 时 yellow→red
        """
        ratio = max(0.0, min(1.0, secs / total))
        if ratio > 0.5:
            # green → yellow (ratio 1.0→0.5 maps to factor 0→1)
            f = (1.0 - ratio) * 2  # 0→1
            r = int(0x27 + (0xF3 - 0x27) * f)
            g = int(0xAE + (0x9C - 0xAE) * f)
            b = int(0x60 + (0x12 - 0x60) * f)
        else:
            # yellow → red (ratio 0.5→0 maps to factor 0→1)
            f = (0.5 - ratio) * 2  # 0→1
            r = int(0xF3 + (0xE7 - 0xF3) * f)
            g = int(0x9C + (0x4C - 0x9C) * f)
            b = int(0x12 + (0x3C - 0x12) * f)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _update_countdown_display(self) -> None:
        """更新信息面板的倒计时显示 — P2-2: RGB 渐变色"""
        try:
            info = self.query_one("#info-panel", Static)
            secs = self._countdown_remaining
            color = self._countdown_color(secs, self.play_phase_timeout or 1)
            countdown = _t("ui.play.countdown", seconds=secs)
            info.update(f"{self._info_text}\n\n[bold {color}]{countdown}[/bold {color}]")
        except Exception:
            pass

    def _cancel_countdown(self) -> None:
        """取消倒计时"""
        self._countdown_remaining = 0
        if self._countdown_timer is not None:
            self._countdown_timer.stop()
            self._countdown_timer = None

    def _respond(self, response: str | None) -> None:
        """完成当前出牌请求，并忽略没有待处理请求时的输入。"""
        request = self._play_request
        if request is None:
            return
        self._play_request = None
        self._cancel_countdown()
        request.set_result(response)

    # ==================== UI 更新 ====================

    def _post_log(self, msg: str) -> None:
        """线程安全的日志写入"""
        if not self._quit_requested.is_set():
            self.app.call_from_thread(self._log, msg)

    def _post_refresh(self) -> None:
        """线程安全的界面刷新"""
        if not self._quit_requested.is_set():
            self.app.call_from_thread(self._refresh_display)

    def _log(self, msg: str) -> None:
        """写入战斗日志，根据内容添加视觉效果 + PlayArea 中央展示"""
        try:
            log_widget = self.query_one("#battle-log", RichLog)
            if "伤害" in msg or "受到" in msg or "损失" in msg:
                msg = f"[bold red]⚡ {msg}[/bold red]"
                self._flash_by_name(msg, "flash-damage", 0.6)
                self._update_play_area_damage(msg)
            elif "回复" in msg or "治疗" in msg or "桃】" in msg:
                msg = f"[bold green]❤ {msg}[/bold green]"
                self._flash_by_name(msg, "flash-heal", 0.5)
            elif "发动【" in msg:
                msg = f"[bold yellow]✨ {msg}[/bold yellow]"
                self._flash_by_name(msg, "flash-skill", 0.4)
                self._skill_toast(msg)
                self._update_play_area_skill(msg)
            elif "使用了【" in msg or "使用【" in msg:
                self._update_play_area_card(msg)
            elif "死亡" in msg or "阵亡" in msg or "杀死" in msg:
                msg = f"[bold red on black]💀 {msg}[/bold red on black]"
                self._flash_by_name(msg, "flash-damage", 1.0)
                self._trigger_death_shake(msg)
            elif "你的回合" in msg:
                msg = f"[bold cyan]🎮 {msg}[/bold cyan]"
            log_widget.write(msg)
            log_widget.scroll_end(animate=True)
        except Exception:
            pass

    def _update_play_area_card(self, msg: str) -> None:
        """更新中央出牌区显示"""
        try:
            import re

            from ui.textual_ui.widgets.play_area import PlayArea

            play_area = self.query_one("#play-area", PlayArea)
            # 解析 "玩家 对 目标 使用了【卡牌】" 或 "玩家 使用了【卡牌】"
            m = re.search(r"(.+?)\s+(?:对\s+(.+?)\s+)?使用[了]*【(.+?)】", msg)
            if m:
                player_name = m.group(1).strip()
                target_name = m.group(2).strip() if m.group(2) else ""
                card_name = m.group(3).strip()
                play_area.show_card_play(player_name, card_name, target_name)
        except Exception:
            pass

    def _update_play_area_skill(self, msg: str) -> None:
        """更新中央出牌区显示技能"""
        try:
            import re

            from ui.textual_ui.widgets.play_area import PlayArea

            play_area = self.query_one("#play-area", PlayArea)
            m = re.search(r"(.+?)\s+发动【(.+?)】", msg)
            if m:
                player_name = m.group(1).strip()
                skill_name = m.group(2).strip()
                play_area.show_skill_use(player_name, skill_name)
        except Exception:
            pass

    def _update_play_area_damage(self, msg: str) -> None:
        """更新中央出牌区显示伤害"""
        try:
            import re

            from ui.textual_ui.widgets.play_area import PlayArea

            play_area = self.query_one("#play-area", PlayArea)
            m = re.search(r"(.+?)\s+受到[了]*\s*(\d+)\s*点", msg)
            if m:
                target_name = m.group(1).strip()
                amount = int(m.group(2))
                dtype = ""
                if "火焰" in msg:
                    dtype = "fire"
                elif "雷电" in msg:
                    dtype = "thunder"
                play_area.show_damage(target_name, amount, dtype)
        except Exception:
            pass

    def _flash_by_name(self, msg: str, css_class: str, duration: float) -> None:
        """从 log 消息中解析角色名，精准闪烁对应 PlayerPanel (P0-4)"""
        target_widget_id = "#battle-log"
        try:
            from ui.textual_ui.widgets.player_panel import PlayerPanel

            opp_container = self.query_one("#opponents", VerticalScroll)
            for panel in opp_container.query(PlayerPanel):
                if panel._player and panel._player.name in msg:
                    self.flash_effect(
                        css_class, f"#{panel.id}" if panel.id else "#battle-log", duration
                    )
                    return
        except Exception:
            pass
        self.flash_effect(css_class, target_widget_id, duration)

    def _refresh_display(self) -> None:
        """刷新界面显示"""
        engine = self.engine
        if not engine or not engine.human_player:
            return

        human = engine.human_player

        # 更新阶段指示器 + 额外信息
        try:
            from ui.textual_ui.widgets.phase_indicator import PhaseIndicator

            phase_bar = self.query_one("#phase-bar", PhaseIndicator)
            phase_bar.set_phase(engine.phase.value)
            current_name = engine.current_player.name if engine.current_player else ""
            deck_remaining = engine.deck.remaining
            discard_pile = engine.deck.discarded
            phase_bar.set_info(
                round_count=engine.round_count,
                deck_count=deck_remaining,
                discard_count=discard_pile,
                player_name=current_name,
            )
        except Exception:
            pass

        # 更新对手面板——显示所有其他玩家（含已死亡）
        try:
            from ui.textual_ui.widgets.player_panel import PlayerPanel

            opp_container = self.query_one("#opponents", VerticalScroll)
            all_others = engine.get_all_other_players(human)
            existing = list(opp_container.query(PlayerPanel))
            if len(existing) != len(all_others):
                with self.app.batch_update():
                    opp_container.remove_children()
                    for i, p in enumerate(all_others):
                        panel = PlayerPanel(p, index=i, id=f"opp-{i}")
                        if not p.is_alive:
                            panel.add_class("dead")
                        if p == engine.current_player:
                            panel.add_class("active-turn")
                        opp_container.mount(panel)
            else:
                for panel, p in zip(existing, all_others):
                    dist = engine.calculate_distance(human, p) if p.is_alive else -1
                    in_rng = engine.is_in_attack_range(human, p) if p.is_alive else False
                    panel.update_player(p, distance=dist, in_range=in_rng)
                    if p == engine.current_player:
                        panel.add_class("active-turn")
                    else:
                        panel.remove_class("active-turn")
        except Exception:
            pass

        # 更新手牌区——CardWidget + batch_update 防闪烁 + P0-3: .playable 提示
        try:
            from ui.textual_ui.widgets.card_widget import CardWidget

            hand_container = self.query_one("#hand-cards", Horizontal)
            is_player_turn = (
                self._play_request is not None
                and engine.current_player == human
                and engine.phase == GamePhase.PLAY
            )
            can_sha = human.can_use_sha() if hasattr(human, "can_use_sha") else True
            has_targets = bool(engine.get_targets_in_range(human)) if is_player_turn else False
            with self.app.batch_update():
                hand_container.remove_children()
                for i, card in enumerate(human.hand):
                    widget = CardWidget(
                        card, index=i, request_id=self._play_request_id, disabled=not is_player_turn
                    )
                    if is_player_turn and self._is_card_playable(card, human, can_sha, has_targets):
                        widget.add_class("playable")
                    hand_container.mount(widget)
        except Exception:
            pass

        # 更新装备槽
        try:
            from ui.textual_ui.widgets.equipment_slots import EquipmentSlots

            equip_widget = self.query_one("#equip-section", EquipmentSlots)
            equip_widget.update_player(human)
        except Exception:
            pass

        # 更新信息面板
        try:
            hp_bar = "●" * human.hp + "○" * (human.max_hp - human.hp)
            hp_full = "●" * human.hp
            hp_empty = "[dim]○[/dim]" * (human.max_hp - human.hp)
            if human.hp <= 1:
                hp_bar = f"[red]{hp_full}[/red]" + hp_empty
            elif human.hp <= human.max_hp // 2:
                hp_bar = f"[yellow]{hp_full}[/yellow]" + hp_empty
            else:
                hp_bar = f"[green]{hp_full}[/green]" + hp_empty
            skills_lines = ""
            if human.hero:
                for s in human.hero.skills:
                    tag = ""
                    if s.is_compulsory:
                        tag = "[dim]锁定技[/dim] "
                    elif s.is_lord_skill:
                        tag = "[dim]主公技[/dim] "
                    skills_lines += f"  [bold yellow]【{s.name}】[/bold yellow]{tag}\n"
                    skills_lines += f"    [dim]{s.description}[/dim]\n"
            # 显示身份和对应胜利条件
            identity_color = human.identity.color
            identity_name = human.identity.chinese_name
            from game.win_checker import get_identity_win_condition

            win_cond = get_identity_win_condition(human.identity.value)
            info_text = (
                f"[bold]{human.name}[/bold] {human.hero.name if human.hero else ''}\n"
                f"体力: {hp_bar} {human.hp}/{human.max_hp}\n"
                f"身份: [{identity_color}]{identity_name}[/{identity_color}]\n"
                f"目标: {win_cond}\n"
                f"─── 技能 ───\n"
                f"{skills_lines.rstrip()}"
            )
            self._info_text = info_text
            self.query_one("#info-panel", Static).update(info_text)
        except Exception:
            pass

    def _is_card_playable(self, card, player, can_sha: bool, has_targets: bool) -> bool:
        """判断卡牌是否可在出牌阶段主动使用 (P0-3b)"""
        try:
            from game.card import CardName

            name = card.name if hasattr(card, "name") else None
            if name == CardName.SHAN:
                return False
            if name == CardName.WUXIE:
                return False
            if name == CardName.SHA:
                return can_sha and has_targets
            if name == CardName.TAO:
                return player.hp < player.max_hp
            if name == CardName.JIU:
                return not getattr(player, "drunk", False)
            return True
        except Exception:
            return True

    # ==================== M3-T04: 视觉反馈 (animate API) ====================

    def flash_effect(
        self, css_class: str, widget_id: str = "#battle-log", duration: float = 0.5
    ) -> None:
        """对指定 widget 施加两段式 opacity 脉冲闪烁 (P0-1)

        使用 Textual 原生 animate() API:
        阶段1: opacity 1.0→0.3 (快速变暗, out_cubic)
        阶段2: opacity 0.3→1.0 (缓慢恢复, in_out_cubic)
        CSS class 在整个过程中保持，动画结束后移除。
        """
        try:
            widget = self.query_one(widget_id)
            widget.add_class(css_class)
            widget.styles.animate(
                "opacity",
                value=0.3,
                duration=duration * 0.4,
                easing="out_cubic",
                on_complete=lambda: self._flash_restore(widget, css_class, duration * 0.6),
            )
        except Exception:
            pass

    def _flash_restore(self, widget, css_class: str, duration: float) -> None:
        """闪烁第二阶段: 恢复 opacity 并移除 CSS class"""
        try:
            widget.styles.animate(
                "opacity",
                value=1.0,
                duration=duration,
                easing="in_out_cubic",
                on_complete=lambda: widget.remove_class(css_class),
            )
        except Exception:
            widget.remove_class(css_class)

    def _post_flash(
        self, css_class: str, widget_id: str = "#battle-log", duration: float = 0.5
    ) -> None:
        """线程安全的闪烁效果 — 确保在 UI 线程执行 animate() (P0-5)"""
        self.app.call_from_thread(self.flash_effect, css_class, widget_id, duration)

    def _skill_toast(self, msg: str) -> None:
        """P3-2: 技能发动时显示 toast 浮动通知"""
        try:
            import re

            m = re.search(r"发动【(.+?)】", msg)
            if m:
                skill_name = m.group(1)
                self.notify(
                    f"✨ 【{skill_name}】发动！",
                    title="技能",
                    severity="information",
                    timeout=2,
                )
        except Exception:
            pass

    def _trigger_death_shake(self, msg: str) -> None:
        """P2-4: 检测死亡消息并触发对应面板震动"""
        try:
            from ui.textual_ui.widgets.player_panel import PlayerPanel

            opp_container = self.query_one("#opponents", VerticalScroll)
            for panel in opp_container.query(PlayerPanel):
                if panel._player and panel._player.name in msg:
                    panel.death_shake()
                    return
        except Exception:
            pass

    # ==================== 事件处理 ====================

    def on_card_widget_card_clicked(self, event) -> None:
        if event.request_id == self._play_request_id:
            self._action_play_card_by_index(event.index, event.card)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        match event.button.id:
            case "btn-end":
                self.action_end_play()
            case "btn-skill":
                self._handle_skill_button()

    def _handle_skill_button(self) -> None:
        """技能按钮"""
        engine = self.engine
        human = engine.human_player
        if engine.skill_system and human:
            usable = engine.skill_system.get_usable_skills(human)
            if usable:
                self._respond(f"skill:{usable[0]}")
            else:
                self._log("⚠ 当前无可用技能")

    def action_end_play(self) -> None:
        self._respond("end")

    def _action_play_card_by_index(self, idx: int, card: Card | None = None) -> None:
        """只选择当前等待时仍处于该位置的手牌。"""
        if self._play_request is None:
            return
        hand = self.engine.human_player.hand
        if 0 <= idx < len(hand) and (card is None or card is hand[idx]):
            self._respond(f"card:{idx}")

    def action_play_card_1(self) -> None:
        self._action_play_card_by_index(0)

    def action_play_card_2(self) -> None:
        self._action_play_card_by_index(1)

    def action_play_card_3(self) -> None:
        self._action_play_card_by_index(2)

    def action_play_card_4(self) -> None:
        self._action_play_card_by_index(3)

    def action_play_card_5(self) -> None:
        self._action_play_card_by_index(4)

    def action_play_card_6(self) -> None:
        self._action_play_card_by_index(5)

    def action_play_card_7(self) -> None:
        self._action_play_card_by_index(6)

    def action_play_card_8(self) -> None:
        self._action_play_card_by_index(7)

    def action_play_card_9(self) -> None:
        self._action_play_card_by_index(8)

    def action_play_card_10(self) -> None:
        self._action_play_card_by_index(9)

    def action_show_help(self) -> None:
        from .rules import RulesScreen

        self.app.push_screen(RulesScreen())

    def action_quit_game(self) -> None:
        self._quit_requested.set()
        self._respond(None)
        modal = self._request_modal
        if modal is not None and self.app.screen is modal:
            modal.dismiss()
        if self._cancel_modal:
            self._cancel_modal()
        if self._game_worker is None or self._game_worker.is_finished:
            self.app.exit()

    def on_unmount(self) -> None:
        self._quit_requested.set()
        self._respond(None)
        if self._cancel_modal:
            self._cancel_modal()
