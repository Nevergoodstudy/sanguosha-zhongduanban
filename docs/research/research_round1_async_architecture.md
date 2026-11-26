# Round 1 Research: Python Async Architecture & Event-Driven Systems (v5.0)

**Date**: 2026-02-20
**Scope**: asyncio patterns, event bus design, Textual TUI framework, FSM for turn-based games
**Pages reviewed**: ~55+

---

## 1. Async EventBus Best Practices

### 1.1 Key Pattern: asyncio.create_task for Event Dispatch
The standard async event bus uses asyncio.create_task(listener(event)) instead of synchronous handler(event) calls. This enables concurrent handler execution without blocking. (Source: Joel Tok blog, py-async-bus, bubus library)

**Reference (Joel Tok)**: Listeners stored in sets for O(1) lookup; emit() creates async tasks for each listener; handlers are async functions called via create_task.

**bubus library (browser-use)**: Production-ready event bus with Pydantic-based type-safe events, parent-child event tracking, FIFO/concurrency options, and WAL persistence.

### 1.2 Current Project Gap
game/events.py EventBus.publish() calls handlers synchronously in a loop:
- for _, _, handler in self._handlers.get(event.event_type, []): handler(event)
- Each handler must complete before the next runs
- A slow handler blocks ALL subsequent handlers and the entire event chain

---

## 2. Textual Framework & Blocking Calls

### 2.1 Critical Rule: Never use time.sleep() in Textual
From Textual official docs (textual.textualize.io) and community:
- time.sleep() pauses the entire OS thread
- asyncio event loop cannot make progress during sleep
- UI freezes completely (no rendering, no input)
- Must use run_worker() for long-running tasks or await asyncio.sleep()

### 2.2 Textual Worker Pattern
For long-running operations, Textual provides:
- run_worker() method for background coroutines
- @work decorator with thread=True for blocking APIs
- call_from_thread() for safe UI updates from workers
- Worker lifecycle management (cancel, exclusive mode)

### 2.3 Windows-Specific asyncio.sleep Issue
Textual blog (2022-12-30) documents Windows 15ms timer granularity:
- asyncio.sleep on Windows rounds up to 15ms multiples
- Fix: await loop.run_in_executor(None, time_sleep, sleep_for)
- Drop-in replacement achieving < 1% timing error

---

## 3. FSM for Turn-Based Card Games

### 3.1 State Pattern (Game Programming Patterns by Robert Nystrom)
FSM components for games:
- Fixed set of states (prepare/judge/draw/play/discard/end)
- Only one active state at a time
- Transitions triggered by events
- Each state has enter/execute/exit hooks

### 3.2 Hierarchical FSM / Pushdown Automaton
For complex games like Sanguosha where skills can interrupt phases:
- Pushdown Automaton: stack-based state memory
- Push new state for interrupts (e.g., Wuxie response chain)
- Pop to return to previous state after interrupt resolves
- Prevents illegal state transitions

### 3.3 Turn-Based Architecture Patterns (GameDev.net, Outscal)
- State Machine for high-level game flow (PlayerTurn, AITurn)
- Command Pattern for player/AI actions (PlayCard, UseSkill)
- Data-driven design for cards and skills (JSON/ScriptableObject)
- Turn Manager as central controller orchestrating flow

### 3.4 Current Project Gap
game/turn_manager.py has phase handlers but:
- No transition validation (can skip phases illegally)
- No enter/exit hooks for phases
- No state stack for interrupts (Wuxie chains)
- Phase order is a flat list without guard conditions

---

## Key Conclusions

1. EventBus must be async -- use asyncio.create_task() for handler dispatch
2. time.sleep() is fatal in Textual -- must replace with asyncio.sleep or run_worker
3. FSM with State Pattern is the standard for turn-based games
4. Pushdown Automaton needed for skill interrupts (Wuxie chains)
5. Command Pattern should be used for all player/AI actions
