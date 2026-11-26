# Problem Analysis Report v5.0 -- Sanguosha Terminal Project

**Date**: 2026-02-21
**Project**: D:\Newidea-3\sanguosha_backup_20260121_071454
**Benchmark**: Sanguosha Online (三国杀OL)
**Total problems identified**: 28 (5x P0 / 10x P1 / 8x P2 / 5x P3)

---

## Priority Legend

- **P0 (Critical)**: Crashes, security vulnerabilities, or fundamentally broken functionality
- **P1 (High)**: Major feature gaps or architectural flaws limiting the product
- **P2 (Medium)**: Code quality, missing patterns, maintainability concerns
- **P3 (Low)**: Nice-to-have improvements, polish, future-proofing

---

## P0 -- Critical (5 issues)

### P0-1: time.sleep() Blocks Textual Event Loop
- **File**: game/game_controller.py line 12 (import time), lines 288/297/301/339/375
- **Problem**: time.sleep() pauses the entire OS thread. In a Textual app running on asyncio, this freezes the UI. No rendering, no input, no event dispatch.
- **Evidence**: Textual docs: "Never use time.sleep() in a Textual app". Used for AI turn delay and auto-skip delay.
- **Impact**: UI appears frozen during AI turns; unresponsive to user input.

### P0-2: player.is_ai Gating on Combat Skills
- **File**: game/combat.py lines 155, 184, 195
- **Problem**: Skills Longdan and Wusheng have `if player.is_ai:` checks. Human players CANNOT use these skills at all.
- **Evidence**: Line 155: `if sha_cards and player.is_ai:` -- Longdan (Sha as Shan). Line 184: `if red_cards and player.is_ai:` -- Wusheng (red card as Sha).
- **Impact**: Core character abilities unavailable to human players. Characters using these skills are unplayable for humans.

### P0-3: Origin Validation Fail-Open (CWE-1385)
- **File**: net/security.py lines 149-163
- **Problem**: OriginValidator.is_allowed() returns True when whitelist is empty. This is the exact CWE-1385 anti-pattern. Any website can open a WebSocket to the server.
- **Evidence**: `if not self._allowed: return True` on line 158-159. Real-world: Gitpod 2023 CSWSH, Apache Zeppelin CVE-2024-51775, Mailpit CVE-2026-22689.
- **Impact**: Cross-Site WebSocket Hijacking. Attacker page can connect and impersonate users.

### P0-4: GameEngine God Object
- **File**: game/engine.py, 167-line __init__, 9+ subsystem dependencies
- **Problem**: GameEngine directly manages deck, players, combat, skills, events, turns, scoring, AI, UI notifications. Violates Single Responsibility. 11 imports in __init__ via deferred imports.
- **Impact**: Cannot test, extend, or refactor any subsystem independently. Any change risks cascading failures.

### P0-5: raw input() / Blocking UI Calls in Textual Context
- **File**: game/game_controller.py -- ui.get_player_action() and similar synchronous UI calls
- **Problem**: The game controller calls blocking synchronous UI methods inside what should be an async Textual app. The entire game loop (run/start_new_game/_game_loop) is synchronous.
- **Impact**: Textual app cannot render updates while waiting for player input; terminal state corruption possible.

---

## P1 -- High (10 issues)

### P1-1: Server Has No Game Logic (Relay-Only)
- **File**: net/server.py line 452-496 (_run_game), line 498-510 (_handle_game_action)
- **Problem**: _run_game() creates a headless engine that runs to completion immediately. _handle_game_action() just relays messages without validation. No interactive server-side game loop.
- **Impact**: Multiplayer is fundamentally broken; any client can cheat.

### P1-2: Synchronous EventBus
- **File**: game/events.py line 213-246 (publish method)
- **Problem**: EventBus.publish() calls handlers synchronously. A slow handler blocks all subsequent handlers.
- **Impact**: Skill trigger chains execute serially causing lag. No concurrent event processing.

### P1-3: No FSM Transition Validation
- **File**: game/turn_manager.py
- **Problem**: Phase transitions not validated. Code can skip from Draw to End, bypassing Play and Discard.
- **Impact**: Game rule integrity not enforced at framework level.

### P1-4: No Reconnection in Live Games
- **File**: net/server.py -- reconnect_player() exists but _run_game() completes instantly
- **Problem**: reconnect_player() framework exists (good) but there is no live game loop to reconnect to. Disconnect = game over.
- **Impact**: Any network hiccup terminates the entire game session.

### P1-5: No Rate Limiting on Game Actions
- **File**: net/server.py lines 498-510
- **Problem**: While rate limiter exists for general messages, game actions are relayed without server-side validation.
- **Impact**: Rapid-fire cheating possible; no server authority over game state.

### P1-6: No WSS (TLS) Enforcement
- **File**: net/server.py -- ssl_cert/ssl_key optional, default is ws://
- **Problem**: Default WebSocket is unencrypted. Auth tokens transmitted in plaintext.
- **Impact**: Man-in-the-middle attacks can intercept all game data.

### P1-7: Incomplete Wuxie Response Chain
- **File**: game/combat.py lines 284-333 (request_wuxie)
- **Problem**: Wuxie chain implementation exists but depends on synchronous request_handler calls. In Sanguosha OL, each player gets an opportunity to respond with Wuxie in turn order, with UI timeout.
- **Impact**: Human players cannot participate in Wuxie chains interactively.

### P1-8: Distance System Exists But Not Fully Integrated
- **File**: game/engine.py lines 479-540 -- calculate_distance, is_in_attack_range exist
- **Problem**: Distance calculation exists and handles horse modifiers (good). But not all card effects check distance correctly (e.g., Shunshouchenyang only checked in controller, not in engine).
- **Impact**: Inconsistent distance enforcement across code paths.

### P1-9: Equipment System Partial
- **File**: game/equipment_system.py, game/player.py Equipment class
- **Problem**: Equipment slots and equip/unequip exist. But some weapon effects are hardcoded in combat.py instead of being data-driven equipment hooks.
- **Impact**: Adding new equipment requires modifying combat code.

### P1-10: Delayed Scroll System Incomplete
- **File**: game/judge_system.py
- **Problem**: JudgeSystem exists for delayed scrolls. But Lebusishu and Bingliang only set skip flags; Lightning judgment chain propagation may have edge cases.
- **Impact**: Delayed scroll mechanics may not match Sanguosha OL rules precisely.

---

## P2 -- Medium (8 issues)

### P2-1: Skills Hardcoded in Combat Logic
- **File**: game/combat.py, game/skill.py
- **Problem**: Skills like Longdan, Wusheng, Kongcheng are hardcoded as if-checks in combat flow. Not registered via a plugin/hook system like FreeKill's TriggerSkill pattern.
- **Impact**: Adding a new skill requires modifying engine code.

### P2-2: i18n Exists But Incomplete
- **File**: i18n/zh_CN.py, i18n/en_US.py, i18n/__init__.py
- **Problem**: i18n system exists and is used (good). But some strings still hardcoded in Chinese in UI/log messages.
- **Impact**: Inconsistent language switching.

### P2-3: Logging Uses Python logging Module (Good) But Some print() Remains
- **File**: Various modules
- **Problem**: Most code uses logging module (good improvement). Some debug print() statements may remain.
- **Impact**: Minor; mostly clean.

### P2-4: Incomplete Type Hints
- **File**: Multiple modules
- **Problem**: Many functions have type annotations (good). Some return types unspecified, especially in callback chains.
- **Impact**: mypy/pyright coverage incomplete.

### P2-5: Configuration Partially Centralized
- **File**: game/config.py exists with get_config()
- **Problem**: Config system exists (good). But some settings (e.g., deck composition, hero pool) still in separate data files without validation.
- **Impact**: Minor; config architecture is reasonable.

### P2-6: Test Coverage Gaps in Critical Paths
- **File**: tests/ (1256 tests, 75.71% coverage)
- **Problem**: Good test count. But async event flow, UI interactions (Textual Pilot), skill chains, and multi-player scenarios undertested.
- **Impact**: Regressions in complex game logic go undetected.

### P2-7: No Error Boundary in Some Event Handlers
- **File**: game/events.py publish() -- has try/except (good), but some direct handler calls skip it
- **Problem**: EventBus.publish() has exception logging (good). But trigger_skill and direct handler calls may propagate exceptions.
- **Impact**: One buggy skill handler could crash the game.

### P2-8: Circular Import Risk from God Object
- **File**: game/engine.py imports from 7+ sibling modules via deferred imports
- **Problem**: Engine uses deferred imports (from .combat import CombatSystem inside __init__) to avoid cycles. This works but is fragile.
- **Impact**: Refactoring can accidentally create import cycles.

---

## P3 -- Low (5 issues)

### P3-1: No Replay/Spectator System
- **Problem**: action_log and export_action_log exist (good foundation). But no replay playback or spectator mode.

### P3-2: No Sound/Visual Feedback
- **Problem**: Terminal-only; no animations or sound. Textual supports rich rendering that could be leveraged.

### P3-3: No Match History / Statistics
- **Problem**: No persistent storage of game results or player statistics.

### P3-4: No Plugin/Extension System
- **Problem**: Skill DSL system exists (skill_dsl.json + interpreter -- good start). But no full plugin architecture like FreeKill's Git-based packages.

### P3-5: No Accessibility Support
- **Problem**: No screen reader support or high-contrast mode. Textual has some built-in accessibility support not leveraged.
