"""对战历史记录系统 (P3-3)

持久化存储每局游戏结果，支持查询和统计分析。
数据以 JSON 格式存储在 data/match_history.json。

用法:
    history = MatchHistory()
    history.record(MatchResult(
        winner="lord",
        player_count=5,
        rounds=12,
        duration_seconds=360.0,
        players=[
            PlayerStat(name="玩家1", hero="曹操", identity="lord",
                       is_ai=False, survived=True, kills=2, damage_dealt=5),
        ],
    ))
    history.save()
    stats = history.get_stats()
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from .engine import GameEngine

logger = logging.getLogger(__name__)

# 默认存储路径
_LEGACY_PATH = Path(__file__).parent.parent / "data" / "match_history.json"


@dataclass(slots=True)
class PlayerStat:
    """单个玩家的对局统计。"""

    name: str = ""
    hero: str = ""
    identity: str = ""  # lord / loyalist / rebel / spy
    is_ai: bool = True
    survived: bool = False
    kills: int = 0
    damage_dealt: int = 0
    damage_taken: int = 0
    cards_played: int = 0


@dataclass(slots=True)
class MatchResult:
    """单局游戏结果。"""

    match_id: str = ""
    timestamp: float = field(default_factory=time.time)
    winner: str = ""  # lord / rebel / spy
    player_count: int = 0
    rounds: int = 0
    duration_seconds: float = 0.0
    players: list[PlayerStat] = field(default_factory=list)
    mode: str = "standard"  # standard / custom / network
    game_version: str = ""
    game_seed: int | None = None
    events: list[dict[str, int | str]] = field(default_factory=list)


class MatchHistory:
    """对战历史管理器。

    支持记录、查询和统计游戏结果。
    数据持久化为 JSON 文件。
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._path = Path(path) if path else self.default_path()
        self._legacy_path = _LEGACY_PATH if path is None else self._path
        self._records: list[MatchResult] = []
        self._next_id: int = 1
        self._unreadable = False

    @property
    def records(self) -> list[MatchResult]:
        return list(self._records)

    def load(self) -> None:
        """从文件加载历史记录。"""
        self._unreadable = False
        source = self._path if self._path.exists() else self._legacy_path
        if not source.exists():
            self._records = []
            return
        try:
            with source.open(encoding="utf-8") as f:
                data = json.load(f)
            self._records = []
            for entry in data.get("matches", []):
                players = [PlayerStat(**p) for p in entry.pop("players", [])]
                result = MatchResult(**entry, players=players)
                self._records.append(result)
            self._next_id = data.get("next_id", len(self._records) + 1)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as e:
            logger.warning("无法读取对战历史 %s: %s", source, e)
            self._records = []
            self._unreadable = True

    def save(self) -> None:
        """保存历史记录到文件。"""
        if self._unreadable:
            raise OSError(f"Cannot overwrite unreadable match history: {self._path}")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.1",
            "next_id": self._next_id,
            "matches": [asdict(r) for r in self._records],
        }
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=self._path.parent, delete=False
        ) as file:
            temporary = Path(file.name)
            try:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.close()
                temporary.replace(self._path)
            finally:
                temporary.unlink(missing_ok=True)

    @staticmethod
    def default_path() -> Path:
        configured = os.environ.get("SANGUOSHA_DATA_HOME")
        if configured:
            return Path(configured) / "match_history.json"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Sanguosha" / "match_history.json"
        if sys.platform == "win32":
            return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sanguosha" / "match_history.json"
        directory = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        return directory / "sanguosha" / "match_history.json"

    def latest(self) -> MatchResult | None:
        self.load()
        return self._records[-1] if self._records else None

    def record(self, result: MatchResult) -> str:
        """记录一局游戏结果。

        Args:
            result: 游戏结果数据

        Returns:
            分配的 match_id
        """
        if not result.match_id:
            result.match_id = f"match_{self._next_id:06d}"
            self._next_id += 1
        self._records.append(result)
        return result.match_id

    def get_recent(self, count: int = 10) -> list[MatchResult]:
        """获取最近 N 局记录。"""
        return list(reversed(self._records[-count:]))

    def get_by_id(self, match_id: str) -> MatchResult | None:
        """按 match_id 查询。"""
        for r in self._records:
            if r.match_id == match_id:
                return r
        return None

    def get_stats(self) -> dict[str, Any]:
        """生成总体统计摘要。"""
        if not self._records:
            return {"total_matches": 0}

        wins: dict[str, int] = {}
        total_rounds = 0
        total_duration = 0.0
        total_kills = 0
        human_wins = 0
        human_total = 0

        for r in self._records:
            wins[r.winner] = wins.get(r.winner, 0) + 1
            total_rounds += r.rounds
            total_duration += r.duration_seconds

            for p in r.players:
                total_kills += p.kills
                if not p.is_ai:
                    human_total += 1
                    if self._player_won(p.identity, r.winner):
                        human_wins += 1

        n = len(self._records)
        return {
            "total_matches": n,
            "win_distribution": wins,
            "avg_rounds": total_rounds / n,
            "avg_duration_seconds": total_duration / n,
            "total_kills": total_kills,
            "human_win_rate": human_wins / human_total if human_total else 0.0,
        }

    def get_hero_stats(self) -> dict[str, dict[str, int]]:
        """按武将统计胜率。

        Returns:
            {hero_name: {"wins": N, "total": N}}
        """
        stats: dict[str, dict[str, int]] = {}
        for r in self._records:
            for p in r.players:
                if p.hero not in stats:
                    stats[p.hero] = {"wins": 0, "total": 0}
                stats[p.hero]["total"] += 1
                if self._player_won(p.identity, r.winner):
                    stats[p.hero]["wins"] += 1
        return stats

    def clear(self) -> None:
        """清空所有记录。"""
        self._records.clear()
        self._next_id = 1

    @staticmethod
    def _player_won(identity: str, winner: str) -> bool:
        """判断玩家身份是否属于获胜方。"""
        if winner == "lord":
            return identity in ("lord", "loyalist")
        if winner == "rebel":
            return identity == "rebel"
        if winner == "spy":
            return identity == "spy"
        return False


def record_completed_match(engine: GameEngine, *, practice: bool) -> tuple[MatchResult, bool]:
    """保存已结算的本地对局，写盘失败时仍可显示本局战报。"""
    try:
        game_version = version("sanguosha")
    except PackageNotFoundError:
        game_version = "source"

    result = MatchResult(
        match_id=uuid4().hex,
        winner=engine.winner_identity.value if engine.winner_identity else "",
        player_count=len(engine.players),
        rounds=engine.round_count,
        players=[
            PlayerStat(
                name=player.name,
                hero=player.hero.name,
                identity=player.identity.value,
                is_ai=player.is_ai,
                survived=player.is_alive,
            )
            for player in engine.players
        ],
        mode="practice" if practice else "standard",
        game_version=game_version,
        game_seed=engine.game_seed,
        events=list(engine.match_events),
    )
    history = MatchHistory()
    history.load()
    history.record(result)
    try:
        history.save()
    except OSError:
        logger.exception("无法保存本局战报")
        return result, False
    return result, True
