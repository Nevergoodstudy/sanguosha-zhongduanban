# Improvement Suggestions v5.0 -- Sanguosha Terminal Project

**Date**: 2026-02-21
**Companion**: problem_analysis_v5.md
**Approach**: Each problem gets a targeted, code-level fix with concrete implementation steps.

---

## P0-1 FIX: Replace time.sleep() with Async Sleep

**Problem**: game/game_controller.py uses time.sleep() which freezes the Textual UI.

**Solution**: Replace all time.sleep() calls with non-blocking alternatives.

**Step 1**: Make GameController methods async:
`python
# game/game_controller.py - change _run_ai_turn to async
async def _run_ai_turn(self, player: Player) -> None:
    # ... existing setup code ...
    cfg = get_config()
    if cfg.ai_turn_delay > 0:
        await asyncio.sleep(cfg.ai_turn_delay)  # NON-BLOCKING
    # ... rest of method ...
`

**Step 2**: For the game loop, use Textual's run_worker:
`python
def on_mount(self) -> None:
    self.run_worker(self._game_loop_async(), exclusive=True)

async def _game_loop_async(self) -> None:
    while not self.engine.is_game_over():
        current = self.engine.current_player
        if current.is_ai:
            await self._run_ai_turn(current)
        else:
            await self._run_human_turn(current)
        self.engine.next_turn()
`

**Step 3**: Remove `import time` from game_controller.py entirely. Add `import asyncio`.

**Effort**: Medium (2-3 hours). All 5 call sites need conversion.

---

## P0-2 FIX: Remove player.is_ai Gate from Combat Skills

**Problem**: game/combat.py lines 155, 184, 195 restrict skills to AI only.

**Solution**: Replace is_ai checks with request_handler calls for human players.

**Step 1**: Fix Longdan in request_shan (line 152-161):
`python
# BEFORE (broken):
if player.has_skill(SkillId.LONGDAN):
    sha_cards = player.get_cards_by_name(CardName.SHA)
    if sha_cards and player.is_ai:  # BUG: human can't use
        card = sha_cards[0]
        ...

# AFTER (fixed):
if player.has_skill(SkillId.LONGDAN):
    sha_cards = player.get_cards_by_name(CardName.SHA)
    if sha_cards:
        if player.is_ai:
            card = sha_cards[0]  # AI auto-selects first
        else:
            card = ctx.request_handler.request_skill_card(
                player, "longdan_as_shan", sha_cards
            )
        if card:
            player.remove_card(card)
            ctx.deck.discard([card])
            ctx.log_event("skill", _t("combat.longdan_as_shan", ...))
            shan_played += 1
            continue
`

**Step 2**: Apply same pattern to Wusheng in request_sha (line 182-190).
**Step 3**: Apply same pattern to Longdan in request_sha (line 193-201).
**Step 4**: Add request_skill_card method to RequestHandler for human UI integration.

**Effort**: Low (1-2 hours). 3 call sites, straightforward pattern.

---

## P0-3 FIX: Origin Validation Fail-Closed

**Problem**: net/security.py OriginValidator returns True on empty whitelist.

**Solution**: Invert the default to DENY when whitelist is empty.

`python
# net/security.py - OriginValidator.is_allowed()
def is_allowed(self, origin: str | None) -> bool:
    if not self._allowed:
        return False  # FAIL-CLOSED: no whitelist = deny all
    if not origin:
        return False
    normalized = origin.strip().rstrip("/").lower()
    return normalized in self._allowed
`

**Additional hardening**:
`python
# Add to GameServer.__init__:
if not allowed_origins.strip():
    logger.warning(
        "No allowed_origins configured. All WebSocket connections "
        "will be rejected. Set ALLOWED_ORIGINS env var or --origins flag."
    )
`

**Step 2**: Add WSS enforcement warning:
`python
async def start(self) -> None:
    ssl_ctx = self._build_ssl_context()
    if not ssl_ctx:
        logger.warning("Running without TLS (ws://). "
                       "Use --ssl-cert and --ssl-key for production.")
`

**Effort**: Very low (30 min). Single line change + warning logs.

---

## P0-4 FIX: Decompose GameEngine God Object

**Problem**: GameEngine has 9+ subsystems in __init__.

**Solution**: The project has ALREADY started decomposition (CombatSystem, EquipmentSystem, JudgeSystem, CardResolver, TurnManager, RequestHandler exist). Complete the pattern.

**Step 1**: Extract PlayerManager:
`python
# game/player_manager.py
class PlayerManager:
    def __init__(self):
        self.players: list[Player] = []
        self.current_index: int = 0

    def get_alive(self) -> list[Player]: ...
    def get_others(self, player) -> list[Player]: ...
    def get_next(self, player) -> Player: ...
    def calculate_distance(self, from_p, to_p) -> int: ...
    def is_in_range(self, attacker, target) -> bool: ...
`

**Step 2**: Extract GameStateManager:
`python
# game/game_state.py
class GameStateManager:
    def __init__(self):
        self.state: GameState = GameState.NOT_STARTED
        self.phase: GamePhase = GamePhase.PREPARE
        self.round_count: int = 0
        self.winner: Identity | None = None
    def check_game_over(self, players) -> bool: ...
`

**Step 3**: GameEngine becomes thin facade:
`python
class GameEngine:
    def __init__(self, data_dir="data"):
        self.event_bus = EventBus()
        self.deck = Deck(...)
        self.hero_repo = HeroRepository(...)
        self.players = PlayerManager()
        self.state = GameStateManager()
        self.turn_manager = TurnManager(self)
        self.combat = CombatSystem(self)
        self.equipment_sys = EquipmentSystem(self)
        self.judge_sys = JudgeSystem(self)
        self.card_resolver = CardResolver(self)
        self.request_handler = DefaultRequestHandler(self)
        # Removed: effect_registry stays as-is (already clean)
`

**Effort**: High (1-2 days). But incremental -- extract one manager at a time.

---

## P0-5 FIX: Make Game Controller Async

**Problem**: GameController.run() is synchronous, blocking Textual's event loop.

**Solution**: Convert game controller to async, integrate with Textual's worker system.

**Step 1**: Make _game_loop async (see P0-1 fix).
**Step 2**: Convert human input to async:
`python
async def _run_human_turn(self, player: Player) -> None:
    # Instead of blocking ui.get_player_action():
    action = await self.ui.get_player_action_async()
    # Textual Screen can use asyncio.Event or message passing
`

**Step 3**: Add async UI protocol:
`python
# ui/protocol.py - add async methods
class GameUI(Protocol):
    async def get_player_action_async(self) -> str: ...
    async def choose_target_async(self, player, targets, prompt) -> Player | None: ...
`

**Effort**: High (1-2 days). Core architecture change; all UI interactions affected.

---

## P1-1 FIX: Implement Server-Side Game Loop

**Problem**: Server runs headless game to completion immediately.

**Solution**: Replace instant _run_game with interactive async game loop.

`python
async def _run_game(self, room: Room) -> None:
    engine = GameEngine()
    room.engine = engine
    player_count = room.max_players if room.ai_fill else room.player_count
    engine.setup_game(player_count)
    # ... hero selection phase via messages ...
    engine.start_game()

    while engine.state == GameState.IN_PROGRESS:
        current = engine.current_player
        player_conn = room.players.get(current.id)

        if player_conn:
            # Wait for human player action via asyncio.Future
            action_future = asyncio.get_event_loop().create_future()
            room._pending_action = (current.id, action_future)
            try:
                action = await asyncio.wait_for(action_future, timeout=60.0)
                self._apply_action(engine, current, action)
            except asyncio.TimeoutError:
                # Auto-skip on timeout
                engine.next_turn()
        else:
            # AI turn
            engine.run_headless_turn()
            engine.next_turn()

        await self._broadcast_game_state(room, engine)
`

**Effort**: Very high (3-5 days). Core server architecture change.

---

## P1-2 FIX: Async EventBus

**Problem**: EventBus.publish() is synchronous.

**Solution**: Add async emit method alongside sync one (backward compatible).

`python
# game/events.py - add async publish
async def async_publish(self, event: GameEvent) -> GameEvent:
    self._event_history.append(event)
    if len(self._event_history) > self._max_history:
        self._event_history = self._event_history[-self._max_history:]

    for _, _, handler in self._global_handlers:
        if event.cancelled:
            break
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
        except Exception as e:
            logger.exception("[EventBus] handler error: %s", e)

    if not event.cancelled:
        for _, _, handler in self._handlers.get(event.event_type, []):
            if event.cancelled:
                break
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.exception("[EventBus] handler error: %s", e)

    return event

async def async_emit(self, event_type: EventType, **kwargs) -> GameEvent:
    event = GameEvent(event_type=event_type, data=kwargs)
    return await self.async_publish(event)
`

**Key**: Keep sync publish() working for existing code. Migrate incrementally.

**Effort**: Medium (3-4 hours). Non-breaking addition.

---

## P1-3 FIX: FSM-Based Phase Validation

**Problem**: No state machine guards invalid phase transitions (e.g. playing cards during draw phase).

**Solution**: Implement explicit FSM with transition rules.

`python
# game/phase_fsm.py
from enum import Enum, auto
from typing import Dict, Set

class Phase(Enum):
    PREPARE = auto()
    JUDGE = auto()
    DRAW = auto()
    PLAY = auto()
    DISCARD = auto()
    END = auto()

VALID_TRANSITIONS: Dict[Phase, Set[Phase]] = {
    Phase.PREPARE: {Phase.JUDGE},
    Phase.JUDGE: {Phase.DRAW},
    Phase.DRAW: {Phase.PLAY},
    Phase.PLAY: {Phase.DISCARD},
    Phase.DISCARD: {Phase.END},
    Phase.END: {Phase.PREPARE},  # next player's turn
}

class PhaseFSM:
    def __init__(self):
        self._phase = Phase.PREPARE

    @property
    def current(self) -> Phase:
        return self._phase

    def transition(self, target: Phase) -> None:
        if target not in VALID_TRANSITIONS.get(self._phase, set()):
            raise InvalidPhaseTransition(
                f"Cannot go from {self._phase.name} to {target.name}"
            )
        self._phase = target

    def can_play_card(self) -> bool:
        return self._phase == Phase.PLAY

    def reset(self) -> None:
        self._phase = Phase.PREPARE
`

**Integration with TurnManager**:
`python
# game/turn_manager.py - add FSM
class TurnManager:
    def __init__(self, engine):
        self.engine = engine
        self.fsm = PhaseFSM()

    def execute_turn(self, player):
        self.fsm.reset()
        self._do_prepare(player)
        self.fsm.transition(Phase.JUDGE)
        self._do_judge(player)
        self.fsm.transition(Phase.DRAW)
        self._do_draw(player)
        self.fsm.transition(Phase.PLAY)
        self._do_play(player)  # only here can cards be played
        self.fsm.transition(Phase.DISCARD)
        self._do_discard(player)
        self.fsm.transition(Phase.END)
`

**Effort**: Medium (4-6 hours). New file + TurnManager integration.

---

## P1-4 FIX: Session Reconnection

**Problem**: No reconnection support; disconnected players lose game state.

**Solution**: Token-based session persistence.

`python
# net/session.py
import secrets, time
from dataclasses import dataclass, field

@dataclass
class PlayerSession:
    player_id: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    room_id: str | None = None
    connected: bool = True
    last_seen: float = field(default_factory=time.time)
    game_seat: int | None = None  # position in game

class SessionManager:
    def __init__(self, timeout: float = 300.0):
        self._sessions: dict[str, PlayerSession] = {}
        self._token_index: dict[str, str] = {}  # token -> player_id
        self._timeout = timeout

    def create(self, player_id: str) -> PlayerSession:
        session = PlayerSession(player_id=player_id)
        self._sessions[player_id] = session
        self._token_index[session.token] = player_id
        return session

    def reconnect(self, token: str, new_ws) -> PlayerSession | None:
        pid = self._token_index.get(token)
        if not pid:
            return None
        session = self._sessions.get(pid)
        if not session or time.time() - session.last_seen > self._timeout:
            return None
        session.connected = True
        session.last_seen = time.time()
        return session

    def disconnect(self, player_id: str) -> None:
        session = self._sessions.get(player_id)
        if session:
            session.connected = False
            session.last_seen = time.time()
`

**Client-side reconnect**:
`python
# net/client.py - add reconnect logic
async def connect(self, uri: str, token: str | None = None) -> None:
    msg = {"type": "auth", "player_id": self.player_id}
    if token:
        msg["type"] = "reconnect"
        msg["token"] = token
    await self.ws.send(json.dumps(msg))
    resp = json.loads(await self.ws.recv())
    if resp.get("status") == "reconnected":
        await self._restore_game_state(resp["game_state"])
`

**Effort**: High (1-2 days). New module + server/client changes.

---

## P1-5 FIX: Complete Wuxie Nullification Chain

**Problem**: game/card_resolver.py handles only single-level Wuxie; no recursive chain.

**Solution**: Implement recursive Wuxie resolution.

`python
# game/card_resolver.py - replace _try_nullify
def _try_nullify(self, card, source, target, ctx) -> bool:
    return self._wuxie_chain(card, source, target, ctx, depth=0)

def _wuxie_chain(self, card, source, target, ctx, depth: int) -> bool:
    MAX_DEPTH = 10  # prevent infinite loops
    if depth >= MAX_DEPTH:
        return False

    # Ask all players in turn order if they want to play Wuxie
    alive = self.engine.get_alive_players()
    start_idx = alive.index(target) if target in alive else 0

    for i in range(len(alive)):
        player = alive[(start_idx + i) % len(alive)]
        wuxie_cards = player.get_cards_by_name(CardName.WUXIEKEJI)
        if not wuxie_cards:
            continue

        # Request decision (AI or human)
        should_play = ctx.request_handler.request_wuxie(
            player, card, source, target, depth
        )
        if not should_play:
            continue

        wuxie = wuxie_cards[0]
        player.remove_card(wuxie)
        ctx.deck.discard([wuxie])
        action = "nullify" if depth % 2 == 0 else "counter_nullify"
        ctx.log_event("wuxie", f"{player.hero.name} plays Wuxie ({action})")

        # Recursive: can someone nullify THIS Wuxie?
        counter_nullified = self._wuxie_chain(
            wuxie, player, target, ctx, depth + 1
        )
        if counter_nullified:
            continue  # This Wuxie was itself nullified
        else:
            # Wuxie stands: odd depth = card NOT nullified, even = nullified
            return depth % 2 == 0

    return False  # No one played Wuxie
`

**Effort**: Medium (3-4 hours). Single method rewrite + RequestHandler addition.

---

## P1-6 FIX: Message Schema Validation

**Problem**: Server accepts unvalidated JSON; no schema enforcement.

**Solution**: Add pydantic or dataclass-based message validation.

`python
# net/messages.py
from dataclasses import dataclass
from typing import Literal, Any

@dataclass
class BaseMessage:
    type: str

@dataclass
class AuthMessage(BaseMessage):
    type: Literal["auth"] = "auth"
    player_id: str = ""
    player_name: str = ""

@dataclass
class GameActionMessage(BaseMessage):
    type: Literal["game_action"] = "game_action"
    action: str = ""
    card_id: int | None = None
    target_id: str | None = None

MESSAGE_TYPES = {
    "auth": AuthMessage,
    "game_action": GameActionMessage,
    # ... add more as needed
}

def parse_message(raw: str) -> BaseMessage:
    import json
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidMessage(f"Invalid JSON: {e}")
    msg_type = data.get("type")
    if msg_type not in MESSAGE_TYPES:
        raise InvalidMessage(f"Unknown type: {msg_type}")
    cls = MESSAGE_TYPES[msg_type]
    try:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    except TypeError as e:
        raise InvalidMessage(f"Bad fields for {msg_type}: {e}")
`

**Server integration**:
`python
# net/server.py - in _handle_client
async def _handle_client(self, ws, path):
    async for raw in ws:
        try:
            msg = parse_message(raw)
        except InvalidMessage as e:
            await ws.send(json.dumps({"error": str(e)}))
            continue
        await self._dispatch(msg, ws)
`

**Effort**: Medium (4-6 hours). New file + server dispatch refactor.

---

## P1-7 FIX: Rate Limiting and Anti-Abuse

**Problem**: No rate limiting on WebSocket messages.

**Solution**: Token bucket rate limiter per connection.

`python
# net/rate_limiter.py
import time

class TokenBucket:
    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate      # tokens per second
        self.burst = burst    # max tokens
        self.tokens = float(burst)
        self.last_refill = time.monotonic()

    def consume(self, n: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.last_refill = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

class ConnectionRateLimiter:
    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}

    def check(self, conn_id: str) -> bool:
        if conn_id not in self._buckets:
            self._buckets[conn_id] = TokenBucket()
        return self._buckets[conn_id].consume()

    def remove(self, conn_id: str) -> None:
        self._buckets.pop(conn_id, None)
`

**Server integration**:
`python
# In _handle_client:
if not self.rate_limiter.check(conn_id):
    await ws.send(json.dumps({"error": "rate_limited"}))
    continue
`

**Effort**: Low (1-2 hours). Simple standalone module.

---

## P1-8 FIX: Equipment Effect Event Integration

**Problem**: Equipment effects (Qinglong, Zhuge) bypass event bus.

**Solution**: Fire equipment events through EventBus for proper interception.

`python
# game/equipment.py - fire events for equip effects
def _handle_zhuge_crossbow(self, player, ctx):
    event = ctx.event_bus.emit(EventType.EQUIPMENT_EFFECT,
        equipment="zhuge_crossbow", player=player,
        effect="unlimited_sha")
    if not event.cancelled:
        player.sha_limit = 999  # effectively unlimited
        ctx.log_event("equip", _t("equip.zhuge_unlimited", ...))

def _handle_qinglong_blade(self, player, target, ctx):
    event = ctx.event_bus.emit(EventType.EQUIPMENT_EFFECT,
        equipment="qinglong_blade", player=player, target=target,
        effect="extra_sha")
    if not event.cancelled:
        # Trigger additional SHA play opportunity
        ctx.combat.request_sha(player, target, ctx, is_qinglong=True)
`

**Add EventType entries**:
`python
# game/events.py
class EventType(Enum):
    # ... existing ...
    EQUIPMENT_EFFECT = "equipment_effect"
    BEFORE_EQUIP = "before_equip"
    AFTER_EQUIP = "after_equip"
`

**Effort**: Medium (3-4 hours). Touch equipment.py + events.py.

---

## P1-9 FIX: i18n Missing Key Fallback

**Problem**: i18n returns raw key on missing translation; no fallback chain.

**Solution**: Add fallback language and warning logs.

`python
# i18n/__init__.py - improve _t function
_FALLBACK_LANG = "zh_CN"

def _t(key: str, **kwargs) -> str:
    text = _current_translations.get(key)
    if text is None and _current_lang != _FALLBACK_LANG:
        text = _fallback_translations.get(key)
        if text:
            logger.debug("i18n fallback: %s not in %s, using %s",
                         key, _current_lang, _FALLBACK_LANG)
    if text is None:
        logger.warning("i18n missing key: %s (lang=%s)", key, _current_lang)
        return f"[{key}]"  # clearly marked as missing
    try:
        return text.format(**kwargs)
    except KeyError as e:
        logger.warning("i18n format error: key=%s, missing=%s", key, e)
        return text
`

**Effort**: Low (1 hour). Single function enhancement.

---

## P1-10 FIX: Logging Standardization

**Problem**: Mix of print() and logging; no structured log format.

**Solution**: Replace all print() with proper logging; add JSON formatter option.

**Step 1**: Find and replace all print() calls:
`python
# Replace throughout codebase:
# BEFORE:
print(f"Game started with {n} players")
# AFTER:
logger.info("Game started with %d players", n)
`

**Step 2**: Centralize log config:
`python
# tools/log_config.py
import logging, sys

def setup_logging(level="INFO", json_format=False):
    root = logging.getLogger("sanguosha")
    root.setLevel(getattr(logging, level))
    handler = logging.StreamHandler(sys.stderr)
    if json_format:
        import json
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                return json.dumps({
                    "ts": self.formatTime(record),
                    "level": record.levelname,
                    "module": record.module,
                    "msg": record.getMessage(),
                })
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    root.addHandler(handler)
`

**Effort**: Medium (3-4 hours). Codebase-wide print() replacement.

---

## P2-1 FIX: Comprehensive Test Coverage

**Problem**: tests/ only covers hero data parsing; no game logic tests.

**Solution**: Add test layers following the testing pyramid.

**Step 1**: Unit tests for core mechanics:
`python
# tests/test_combat.py
import pytest
from game.combat import CombatSystem
from game.engine import GameEngine

class TestCombatSystem:
    def setup_method(self):
        self.engine = GameEngine(data_dir="data")
        self.engine.setup_game(2)
        self.engine.start_game()
        self.ctx = self.engine._build_context()

    def test_sha_reduces_hp(self):
        attacker = self.engine.players[0]
        target = self.engine.players[1]
        initial_hp = target.hp
        # Give attacker a SHA card
        sha = self.engine.deck.find_card("sha")
        attacker.add_card(sha)
        self.engine.combat.resolve_sha(attacker, target, sha, self.ctx)
        # Target didn't play Shan, takes 1 damage
        assert target.hp == initial_hp - 1

    def test_shan_blocks_sha(self):
        attacker = self.engine.players[0]
        target = self.engine.players[1]
        initial_hp = target.hp
        sha = self.engine.deck.find_card("sha")
        shan = self.engine.deck.find_card("shan")
        attacker.add_card(sha)
        target.add_card(shan)
        self.engine.combat.resolve_sha(attacker, target, sha, self.ctx)
        assert target.hp == initial_hp  # blocked

    def test_longdan_sha_as_shan(self):
        # Test that Longdan allows SHA to be used as SHAN
        target = self.engine.players[1]
        target.hero = self._get_hero("zhaoyun")  # has Longdan
        sha = self.engine.deck.find_card("sha")
        target.add_card(sha)
        result = self.engine.combat.request_shan(target, 1, self.ctx)
        assert result >= 1  # should use SHA as SHAN
`

**Step 2**: Integration tests for turn flow:
`python
# tests/test_turn_flow.py
class TestTurnFlow:
    def test_full_turn_cycle(self):
        engine = GameEngine(data_dir="data")
        engine.setup_game(4)
        engine.start_game()
        initial_hand = len(engine.players[0].hand)
        engine.turn_manager.execute_turn(engine.players[0])
        # After turn: drew 2 cards, maybe played some
        assert engine.turn_manager.turn_count == 1

    def test_game_over_detection(self):
        engine = GameEngine(data_dir="data")
        engine.setup_game(2)
        engine.start_game()
        # Kill all rebels
        for p in engine.players:
            if p.identity == Identity.REBEL:
                p.hp = 0
                p.alive = False
        assert engine.check_game_over() is True
`

**Step 3**: Add pytest config:
`ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marks tests as slow
    integration: integration tests
`

**Effort**: High (2-3 days). Ongoing investment; start with combat tests.

---

## P2-2 FIX: Hero Balance Data-Driven Configuration

**Problem**: Hero skills are hardcoded in combat.py; can't adjust without code changes.

**Solution**: Move skill parameters to data files.

`json
// data/skill_config.json
{
    "longdan": {
        "type": "convert",
        "convert_from": ["sha"],
        "convert_to": ["shan"],
        "bidirectional": true,
        "description_key": "skill.longdan.desc"
    },
    "wusheng": {
        "type": "convert",
        "convert_from": ["red_card"],
        "convert_to": ["sha"],
        "filter": "color_red",
        "description_key": "skill.wusheng.desc"
    },
    "jianxiong": {
        "type": "trigger",
        "trigger_event": "after_damage",
        "effect": "pick_damage_card",
        "description_key": "skill.jianxiong.desc"
    },
    "ganglie": {
        "type": "trigger",
        "trigger_event": "after_damage",
        "effect": "judge_retaliate",
        "judge_condition": "not_heart",
        "damage_amount": 1,
        "description_key": "skill.ganglie.desc"
    }
}
`

**Skill resolver**:
`python
# game/skill_resolver.py
class SkillResolver:
    def __init__(self, config_path: str = "data/skill_config.json"):
        with open(config_path) as f:
            self._config = json.load(f)

    def can_convert(self, skill_id: str, from_card: str, to_card: str) -> bool:
        cfg = self._config.get(skill_id)
        if not cfg or cfg["type"] != "convert":
            return False
        if to_card not in cfg["convert_to"]:
            return False
        if "bidirectional" in cfg and cfg["bidirectional"]:
            return from_card in cfg["convert_from"] or to_card in cfg["convert_from"]
        return from_card in cfg["convert_from"]
`

**Effort**: High (2-3 days). New data format + resolver + migration from hardcoded logic.

---

## P2-3 FIX: Consistent Error Handling

**Problem**: Bare except blocks and inconsistent error patterns.

**Solution**: Define exception hierarchy; replace bare excepts.

`python
# game/exceptions.py
class SanguoshaError(Exception):
    """Base exception for all game errors."""

class GameLogicError(SanguoshaError):
    """Invalid game operation."""

class InvalidPhaseTransition(GameLogicError):
    """FSM transition violation."""

class InvalidTarget(GameLogicError):
    """Card target is invalid."""

class InvalidCardPlay(GameLogicError):
    """Card cannot be played now."""

class NetworkError(SanguoshaError):
    """Network-related errors."""

class InvalidMessage(NetworkError):
    """Malformed network message."""

class AuthenticationError(NetworkError):
    """Authentication failure."""
`

**Replace bare excepts**:
`python
# BEFORE (in multiple files):
try:
    ...
except:
    pass

# AFTER:
try:
    ...
except SanguoshaError as e:
    logger.warning("Game error: %s", e)
except Exception as e:
    logger.exception("Unexpected error: %s", e)
`

**Effort**: Medium (3-4 hours). New file + grep/replace across codebase.

---

## P2-4 FIX: Distance Calculation Caching

**Problem**: Distance calculated fresh every time, O(n) per query.

**Solution**: Cache distance matrix; invalidate on player death or equipment change.

`python
# game/distance_cache.py
class DistanceCache:
    def __init__(self):
        self._cache: dict[tuple[str, str], int] = {}
        self._dirty = True

    def invalidate(self):
        self._dirty = True
        self._cache.clear()

    def get(self, from_id: str, to_id: str) -> int | None:
        if self._dirty:
            return None
        return self._cache.get((from_id, to_id))

    def set(self, from_id: str, to_id: str, dist: int):
        self._cache[(from_id, to_id)] = dist

    def rebuild(self, players: list, calc_fn):
        self._cache.clear()
        alive = [p for p in players if p.alive]
        for a in alive:
            for b in alive:
                if a is not b:
                    self._cache[(a.id, b.id)] = calc_fn(a, b)
        self._dirty = False
`

**Integration**: Hook invalidate() to EventBus on PLAYER_DEATH, EQUIP_CHANGE events.

**Effort**: Low (2 hours). Simple cache with event-driven invalidation.

---

## P2-5 FIX: Configuration Validation

**Problem**: Config loaded from YAML without validation; missing keys cause runtime errors.

**Solution**: Add pydantic or dataclass-based config validation.

`python
# tools/config_schema.py
from dataclasses import dataclass, field

@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 8765
    max_rooms: int = 10
    allowed_origins: str = ""
    ssl_cert: str = ""
    ssl_key: str = ""

@dataclass
class GameConfig:
    player_count: int = 5
    ai_turn_delay: float = 1.0
    hand_limit_base: int = 4

@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    game: GameConfig = field(default_factory=GameConfig)
    log_level: str = "INFO"

def load_and_validate(path: str) -> AppConfig:
    import yaml
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    # Validate types and ranges
    cfg = AppConfig(
        server=ServerConfig(**raw.get("server", {})),
        game=GameConfig(**raw.get("game", {})),
        log_level=raw.get("log_level", "INFO"),
    )
    if cfg.game.player_count < 2 or cfg.game.player_count > 10:
        raise ValueError(f"player_count must be 2-10, got {cfg.game.player_count}")
    if cfg.server.port < 1 or cfg.server.port > 65535:
        raise ValueError(f"port must be 1-65535, got {cfg.server.port}")
    return cfg
`

**Effort**: Low (1-2 hours). New file + replace raw dict access.

---

## P2-6 FIX: Card/Deck Integrity Validation

**Problem**: No runtime check that deck has correct card counts.

**Solution**: Add deck validation on creation and during play.

`python
# game/deck.py - add validation
EXPECTED_CARD_COUNTS = {
    "sha": 30, "shan": 15, "tao": 8,
    "wuxiekeji": 4, "nanmanruqin": 3,
    "wanjianqifa": 1, "juedou": 3,
    # ... complete list per standard Sanguosha rules
}

def validate_deck(self) -> list[str]:
    errors = []
    counts = {}
    for card in self._all_cards:
        counts[card.name] = counts.get(card.name, 0) + 1
    for name, expected in EXPECTED_CARD_COUNTS.items():
        actual = counts.get(name, 0)
        if actual != expected:
            errors.append(f"{name}: expected {expected}, got {actual}")
    return errors
`

**Effort**: Low (1-2 hours). Data validation function.

---

## P2-7 FIX: Proper Player Death Flow

**Problem**: Player death lacks reward/punishment mechanics (Sanguosha OL standard).

**Solution**: Implement kill rewards per official rules.

`python
# game/death_handler.py
class DeathHandler:
    def __init__(self, engine):
        self.engine = engine

    def handle_death(self, victim, killer, ctx):
        victim.alive = False
        # Discard all cards (hand + equipment + judge area)
        all_cards = victim.hand + victim.get_equipment_cards() + victim.judge_area
        victim.hand.clear()
        ctx.deck.discard(all_cards)
        ctx.log_event("death", f"{victim.hero.name} has been eliminated")

        if killer is None:
            return

        # Reward/punishment per Sanguosha OL rules:
        if victim.identity == Identity.REBEL:
            # Killer draws 3 cards (regardless of killer identity)
            ctx.log_event("reward", f"{killer.hero.name} draws 3 for killing rebel")
            for _ in range(3):
                card = ctx.deck.draw()
                if card:
                    killer.add_card(card)

        elif victim.identity == Identity.LOYALIST and killer.identity == Identity.LORD:
            # Lord kills loyalist: Lord discards entire hand + equipment
            ctx.log_event("punishment",
                f"{killer.hero.name} discards all for killing loyalist")
            penalty_cards = killer.hand + killer.get_equipment_cards()
            killer.hand.clear()
            killer.clear_equipment()
            ctx.deck.discard(penalty_cards)
`

**Effort**: Medium (3-4 hours). New module + integrate with game over checks.

---

## P2-8 FIX: TypedDict/Protocol for Engine Context

**Problem**: Engine context (ctx) passed as ad-hoc object; no type safety.

**Solution**: Define explicit context Protocol.

`python
# game/context.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class GameContext(Protocol):
    event_bus: EventBus
    deck: Deck
    players: list
    combat: CombatSystem
    equipment_sys: EquipmentSystem
    judge_sys: JudgeSystem
    request_handler: RequestHandler

    def get_alive_players(self) -> list: ...
    def log_event(self, category: str, message: str) -> None: ...
`

**Effort**: Low (1 hour). Type annotation improvement.

---

## P3-1 FIX: AI Decision Transparency and Logging

**Problem**: AI decisions are opaque; hard to debug or improve.

**Solution**: Add structured decision logging for AI actions.

`python
# ai/decision_log.py
from dataclasses import dataclass, field
from typing import Any
import json, time

@dataclass
class AIDecision:
    timestamp: float = field(default_factory=time.time)
    player_id: str = ""
    ai_tier: str = ""  # "random", "rule", "strategic"
    phase: str = ""
    action: str = ""
    candidates: list[dict] = field(default_factory=list)
    chosen: dict = field(default_factory=dict)
    reason: str = ""
    score: float = 0.0

class AIDecisionLogger:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled
        self._history: list[AIDecision] = []

    def log(self, decision: AIDecision):
        if not self._enabled:
            return
        self._history.append(decision)
        logger.debug("AI[%s] %s: %s (score=%.2f, reason=%s)",
            decision.ai_tier, decision.player_id,
            decision.action, decision.score, decision.reason)

    def export_json(self, path: str):
        import dataclasses
        with open(path, "w") as f:
            json.dump([dataclasses.asdict(d) for d in self._history],
                      f, indent=2, default=str)
`

**Integration with AI tiers**:
`python
# ai/strategy_ai.py - add logging
def choose_action(self, player, ctx):
    candidates = self._evaluate_all_actions(player, ctx)
    best = max(candidates, key=lambda c: c["score"])
    self.decision_logger.log(AIDecision(
        player_id=player.id,
        ai_tier="strategic",
        phase=ctx.current_phase.name,
        action=best["action"],
        candidates=candidates,
        chosen=best,
        reason=best.get("reason", "highest_score"),
        score=best["score"],
    ))
    return best["action"]
`

**Effort**: Low (2-3 hours). New module; opt-in per game.

---

## P3-2 FIX: UI Accessibility and Theming

**Problem**: Hardcoded colors; no theme support; limited accessibility.

**Solution**: Add Textual CSS theming system.

`css
/* ui/themes/default.tcss */
GameBoard {
    background: ;
}

PlayerPanel {
    border: solid ;
    padding: 1;
}

PlayerPanel.current-turn {
    border: double ;
    background: ;
}

.hp-bar {
    color: ;
}

.hp-bar.critical {
    color: 设置“WindowTitle”时发生异常:“窗口标题的长度不能超过 1023 个字符。” fatal: not a git repository (or any of the parent directories): .git fatal: not a git repository (or any of the parent directories): .git 找不到与参数名称“PredictionSource”匹配的参数。 设置“WindowTitle”时发生异常:“窗口标题的长度不能超过 1023 个字符。” fatal: not a git repository (or any of the parent directories): .git fatal: not a git repository (or any of the parent directories): .git 找不到与参数名称“PredictionSource”匹配的参数。 设置“WindowTitle”时发生异常:“窗口标题的长度不能超过 1023 个字符。” fatal: not a git repository (or any of the parent directories): .git fatal: not a git repository (or any of the parent directories): .git 找不到与参数名称“PredictionSource”匹配的参数。 设置“WindowTitle”时发生异常:“窗口标题的长度不能超过 1023 个字符。” fatal: not a git repository (or any of the parent directories): .git fatal: not a git repository (or any of the parent directories): .git 找不到与参数名称“PredictionSource”匹配的参数。 设置“WindowTitle”时发生异常:“窗口标题的长度不能超过 1023 个字符。” fatal: not a git repository (or any of the parent directories): .git fatal: not a git repository (or any of the parent directories): .git 找不到与参数名称“PredictionSource”匹配的参数。 fatal: not a git repository (or any of the parent directories): .git fatal: not a git repository (or any of the parent directories): .git 找不到与参数名称“PredictionSource”匹配的参数。 找不到与参数名称“PredictionSource”匹配的参数。;
}

CardWidget {
    min-width: 12;
    height: 3;
    border: round ;
}

CardWidget.red {
    color: red;
}

CardWidget.black {
    color: white;
}
`

**Theme switching**:
`python
# ui/theme_manager.py
THEMES = {
    "default": "ui/themes/default.tcss",
    "high_contrast": "ui/themes/high_contrast.tcss",
    "dark": "ui/themes/dark.tcss",
}

class ThemeManager:
    def __init__(self, app):
        self.app = app
        self._current = "default"

    def switch(self, name: str):
        if name in THEMES:
            self.app.stylesheet.clear()
            self.app.stylesheet.load(THEMES[name])
            self._current = name
`

**Effort**: Medium (4-6 hours). CSS files + theme manager.

---

## P3-3 FIX: Game Replay System

**Problem**: No ability to review past games.

**Solution**: Record all game events; implement replay viewer.

`python
# game/replay.py
import json, gzip, time
from dataclasses import dataclass, asdict

@dataclass
class ReplayEvent:
    turn: int
    phase: str
    actor: str
    action: str
    targets: list[str]
    cards: list[str]
    result: str
    timestamp: float

class ReplayRecorder:
    def __init__(self):
        self.events: list[ReplayEvent] = []
        self.metadata: dict = {}

    def start(self, players, heroes):
        self.metadata = {
            "version": "1.0",
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "players": [{"id": p.id, "hero": p.hero.name,
                         "identity": p.identity.name} for p in players],
        }

    def record(self, event: ReplayEvent):
        self.events.append(event)

    def save(self, path: str):
        data = {
            "metadata": self.metadata,
            "events": [asdict(e) for e in self.events],
        }
        with gzip.open(path, "wt", encoding="utf-8") as f:
            json.dump(data, f)

class ReplayPlayer:
    def __init__(self, path: str):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            data = json.load(f)
        self.metadata = data["metadata"]
        self.events = data["events"]
        self._index = 0

    def next_event(self) -> dict | None:
        if self._index >= len(self.events):
            return None
        event = self.events[self._index]
        self._index += 1
        return event

    def reset(self):
        self._index = 0
`

**Integration**: Hook ReplayRecorder into EventBus as global listener.

**Effort**: Medium (4-6 hours). New module + EventBus integration.

---

## P3-4 FIX: Performance Profiling Hooks

**Problem**: No built-in profiling; hard to identify bottlenecks.

**Solution**: Add optional timing decorators and metrics.

`python
# tools/profiling.py
import time, functools, logging

logger = logging.getLogger("sanguosha.perf")

_metrics: dict[str, list[float]] = {}

def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        name = f"{func.__module__}.{func.__qualname__}"
        _metrics.setdefault(name, []).append(elapsed)
        if elapsed > 0.1:  # log slow calls
            logger.warning("SLOW: %s took %.3fs", name, elapsed)
        return result
    return wrapper

def report_metrics() -> dict:
    report = {}
    for name, times in _metrics.items():
        report[name] = {
            "calls": len(times),
            "total_ms": sum(times) * 1000,
            "avg_ms": (sum(times) / len(times)) * 1000,
            "max_ms": max(times) * 1000,
        }
    return report
`

**Usage**: Apply `@timed` to hot paths like combat resolution, card effects.

**Effort**: Low (1-2 hours). Decorator + report function.

---

## P3-5 FIX: Documentation and Developer Onboarding

**Problem**: No architecture docs; README lacks setup/contribution guide.

**Solution**: Add structured documentation.

**Step 1**: Create ARCHITECTURE.md:
`markdown
# Architecture Overview

## Module Dependency Graph
main.py -> GameController -> GameEngine -> [CombatSystem, CardResolver, ...]
                          -> GameUI (Textual)
server.py -> GameServer -> Room -> GameEngine (headless)

## Data Flow
1. Player input -> UI/Network -> RequestHandler -> GameEngine
2. GameEngine -> EventBus -> [CombatSystem, EquipmentSystem, ...]
3. State change -> EventBus -> UI update / Network broadcast

## Key Design Patterns
- Event Bus: Decoupled game event handling
- Strategy Pattern: 3-tier AI (RandomAI -> RuleAI -> StrategyAI)
- Observer: UI reacts to engine state changes
`

**Step 2**: Create CONTRIBUTING.md with:
- Setup instructions (Python 3.11+, pip install, data directory)
- How to run tests
- Code style (ruff/black config)
- PR checklist

**Step 3**: Add inline docstrings to all public classes/methods.

**Effort**: Medium (4-6 hours). One-time documentation investment.

---

# Implementation Roadmap

## Phase 1: Critical Fixes (Week 1)
Priority: P0-1 through P0-5
- Replace time.sleep with async (P0-1)
- Fix combat skill gates (P0-2)
- Fix origin validation (P0-3)
- Begin GameEngine decomposition (P0-4)
- Start async controller conversion (P0-5)

## Phase 2: Core Infrastructure (Week 2-3)
Priority: P1-1 through P1-10
- Server-side game loop (P1-1)
- Async EventBus (P1-2)
- FSM phase validation (P1-3)
- Session reconnection (P1-4)
- Wuxie chain (P1-5)
- Message validation + rate limiting (P1-6, P1-7)
- Equipment events (P1-8)
- i18n fallback + logging (P1-9, P1-10)

## Phase 3: Quality and Polish (Week 4-5)
Priority: P2-1 through P2-8
- Test coverage expansion (P2-1)
- Data-driven skills (P2-2)
- Error handling + config validation (P2-3, P2-5)
- Distance caching (P2-4)
- Deck validation (P2-6)
- Death flow (P2-7)
- Type safety (P2-8)

## Phase 4: Enhancement (Week 6+)
Priority: P3-1 through P3-5
- AI transparency (P3-1)
- Theming (P3-2)
- Replay system (P3-3)
- Profiling (P3-4)
- Documentation (P3-5)

---

## Total Effort Estimate
- P0 fixes: ~5-7 days
- P1 fixes: ~10-15 days
- P2 fixes: ~8-12 days
- P3 fixes: ~5-8 days
- **Total**: ~28-42 developer-days (6-8 weeks solo, 2-3 weeks with team)

---

*Generated by deep analysis of Sanguosha Terminal Project*
*Reference benchmark: Sanguosha OL / FreeKill open-source implementation*
