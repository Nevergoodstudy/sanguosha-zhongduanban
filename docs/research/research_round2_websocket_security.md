# Round 2 Research: WebSocket Security & Multiplayer Game Server Architecture (v5.0)

**Date**: 2026-02-20
**Scope**: OWASP WebSocket security, CWE-1385, authoritative game servers, reconnection, FreeKill architecture
**Pages reviewed**: ~55+

---

## 1. WebSocket Security (OWASP / CWE)

### 1.1 Origin Validation (CWE-1385 / OWASP)
OWASP WebSocket Security Cheat Sheet mandates:
- Server MUST validate the Origin header against an allowlist
- Default policy: DENY if origin not in whitelist
- If whitelist empty/unconfigured, REJECT ALL connections (fail-closed)
- Use TLS (wss://) -- never use unencrypted ws:// in production

CWE-1385 (Missing Origin Validation of WebSocket Handshake Request):
- WebSockets can make cross-origin requests not restricted by SOP or CORS
- Without explicit origin validation, CSRF attacks become more powerful
- Allows Cross-Site WebSocket Hijacking (CSWSH)

### 1.2 Deployment scope

The multiplayer feature is a LAN preview. See the [implementation and verification record](../macos-improvement-plan.md).

## 2. Authoritative Game Server Architecture

### 2.1 Core Principle: Server Authority
For competitive card games:
- Server owns ALL game state (deck order, hand contents, hidden cards)
- Client sends intentions only (play_card(id, target))
- Server validates legality, applies effects, broadcasts result
- Client NEVER directly modifies game state

### 2.2 Current Project Gap
net/server.py _run_game() method (line 452-496):
- Creates headless engine but runs it to completion immediately
- No interactive game loop -- no waiting for player input
- Game actions (line 498-510) are just relayed without validation
- Any client can fabricate game state and cheat freely

### 2.3 FreeKill Architecture (Reference Implementation)
FreeKill (Qsgs-Fans/FreeKill on GitHub):
- Qt C++ core + Lua scripting for ALL game logic
- Single-threaded async server using Lua coroutines
- Per-room game instances with isolated state
- All card effects and skill triggers run server-side
- Client only renders UI and sends action intents
- Git-based extension package manager for community skill packs
- Framework-level reconnection with state snapshot on rejoin
- Framework-level replay recording

---

## 3. Reconnection & Replay

### 3.1 Standard Pattern
1. Server assigns session token on first connect
2. On disconnect, server pauses player timer (or substitutes AI)
3. On reconnect with valid token, server replays missed events
4. Client rebuilds UI from replayed events

### 3.2 Current Project State
- ConnectionTokenManager exists with timing-safe verify (good)
- reconnect_player() method exists with event replay (good framework)
- BUT: _run_game() runs to completion instantly -- no live game to reconnect to
- No AI substitution for disconnected players

---

## 4. Rate Limiting & DoS Protection

### 4.1 OWASP Recommendations
- Limit connections per user (preferred) or per IP
- Set message size limits (64KB or less)
- Rate limit messages (100/minute as starting point)
- Heartbeat monitoring with ping/pong for dead connections
- Log WebSocket events including security violations

### 4.2 Current Project State
- RateLimiter class exists (sliding window, O(1) -- good design)
- IPConnectionTracker exists (good)
- Message size limit configurable (good)
- Heartbeat checker exists (good)
- MISSING: These are not fully enforced in the game action path

---

## Key Conclusions

1. Origin validation MUST fail-closed (deny when whitelist empty)
2. Server MUST be authoritative -- current relay architecture allows cheating
3. Reconnection framework exists but needs live game loop integration
4. Rate limiting infrastructure is good but needs tighter enforcement
5. FreeKill demonstrates production-quality Sanguosha server architecture
