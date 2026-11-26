# Round 3 Research: Sanguosha Game Mechanics, Open-Source Implementations & Testing (v5.0)

**Date**: 2026-02-20
**Scope**: Sanguosha OL rules, FreeKill/QSanguosha architecture, card game testing strategies
**Pages reviewed**: ~55+

---

## 1. Sanguosha OL Rule Mechanics (Benchmark)

### 1.1 Core Game Flow
Standard turn structure (6 phases):
1. Prepare Phase -- skill triggers (e.g., Lightning judgment)
2. Judge Phase -- delayed scroll resolution
3. Draw Phase -- default draw 2 cards (modifiable by skills)
4. Play Phase -- play cards/skills, default 1 Sha per turn
5. Discard Phase -- discard to hand limit (= current HP)
6. End Phase -- end-of-turn triggers

### 1.2 Key Mechanics
- Wuxie Keji: Can be chained; each player gets opportunity to respond in turn order
- Distance calculation: Physical seat distance modified by +1/-1 horses
- Armor effects: Persistent equipment modifying damage/card interactions
- Kill count: Per-turn limit (default 1), modified by Zhuge Crossbow
- Linked damage: Chain transfers fire/lightning damage to all chained players

### 1.3 Skill Categories
- Lock skills: Always active, cannot be opted out
- Trigger skills: Triggered by specific events (on-damage, on-draw, etc.)
- Active skills: Player-initiated during play phase
- Limited skills: Once per game

---

## 2. Open-Source Sanguosha Implementations

### 2.1 FreeKill (Active, Modern)
Source: github.com/Qsgs-Fans/FreeKill
- Language: Qt C++ core + Lua scripting
- Architecture: Authoritative server, thin client
- Skill system: All skills defined as Lua TriggerSkill objects with event hooks:
  - events = {fk.Damaged} -- which events to listen for
  - can_trigger(self, event, target, player, data) -- guard condition
  - on_use(self, event, target, player, data) -- effect
- Example (jianxiong): listens to fk.Damaged, checks if card in processing area, obtains the card
- Extension: Git-based package manager (freekill-core repo)
- Reconnection: Built into framework
- Testing: Lua unit tests per skill

### 2.2 QSanguosha (Legacy, C++/Qt)
Source: github.com/Mogara/QSanguosha
- Language: C++ with Qt GUI, Lua via SWIG bindings
- Architecture: Monolithic, single-process
- Skill system: C++ virtual functions + Lua scripts
- Historical significance: Original open-source Sanguosha

### 2.3 Key Takeaway for This Project
FreeKill's Lua skill system maps directly to Python patterns:
- Skills are data-driven (not hardcoded in engine)
- New skills added without modifying core code
- Event hooks map cleanly to Python async/await
- can_trigger -> guard condition, on_use -> effect

---

## 3. Testing Strategies for Card Games

### 3.1 Testing Pyramid
1. Unit tests (base): Individual card effects, damage calculation, distance
2. Integration tests (middle): Multi-card combos, skill chains, Wuxie chains
3. End-to-end tests (top): Full game scenarios, win condition verification

### 3.2 Textual Testing (Official Docs)
- app.run_test() for headless Textual app testing
- Pilot API for simulating user interactions
- Snapshot testing for UI regression
- All test methods are async

### 3.3 Deterministic Game Testing
Critical pattern for card games:
- Seed the RNG for reproducible deck order (project already does this)
- Create pre-configured game states for specific scenarios
- Test from known state to known outcome
- Use fixtures for common game configurations

### 3.4 Current Project State
- 1256 tests, 75.71% coverage (decent baseline)
- Missing: async tests for event system
- Missing: Textual Pilot UI tests
- Missing: integration tests for skill chains
- Missing: deterministic game state fixtures for edge cases

---

## 4. AI Architecture for Sanguosha

### 4.1 Three-Tier AI Pattern
1. Rule-based (basic): If HP < 2, use Peach; always dodge Sha
2. Heuristic (intermediate): Card value evaluation, target priority
3. MCTS/Neural (advanced): Monte Carlo Tree Search with card probability

### 4.2 Current Project AI
- Three-tier structure exists (easy/normal/hard strategies)
- BUT: Some skills gated by player.is_ai -- human players cannot use them
- AI decision logic mixed with game rules (separation of concerns violation)

---

## Key Conclusions

1. FreeKill's event-hook skill system is the reference for Sanguosha implementation
2. Skill definitions should be data-driven, not hardcoded in combat.py
3. Testing must include deterministic game state fixtures
4. Textual provides built-in testing (Pilot API) that this project doesn't use
5. AI logic must be separated from game rules -- is_ai checks in combat.py are wrong
