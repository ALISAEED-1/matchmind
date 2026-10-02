"""Facts: the only material the LLM agents are allowed to use.

For each moment we build two views of the same numbers:

* `facts`: nested JSON shown to the model (team names instead of home/away,
  numbers already rounded the way they should be quoted);
* `fields`: a flat dict of display strings used by the deterministic templates.

The Verifier later checks that every number an agent writes appears here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from matchmind.models import MatchMeta, Player, Side
from matchmind.stats import MatchSnapshot, Moment, MomentKind

POSITION_WORDS = {
    "GK": "goalkeeper",
    "RB": "right-back",
    "LB": "left-back",
    "CB": "centre-back",
    "DM": "defensive midfielder",
    "CM": "midfielder",
    "AM": "attacking midfielder",
    "RW": "right winger",
    "LW": "left winger",
    "ST": "striker",
}


def display_minute(period: int, minute: int) -> str:
    """Broadcast-style minute: 0-based 17 -> "18'", stoppage -> "45+2'" / "90+3'"."""
    shown = minute + 1
    if period == 1 and shown > 45:
        return f"45+{shown - 45}'"
    if period == 2 and shown > 90:
        return f"90+{shown - 90}'"
    return f"{shown}'"


def _pct(v: float) -> int:
    return round(v * 100)


@dataclass(frozen=True)
class MomentFacts:
    facts: dict[str, Any]
    fields: dict[str, str]
    players: dict[str, str]  # player_id -> name, for every player in this match


class FactBuilder:
    def __init__(self, meta: MatchMeta):
        self.meta = meta
        self.players: dict[str, tuple[Player, Side]] = {
            p.id: (p, side)
            for side, club in ((Side.HOME, meta.home), (Side.AWAY, meta.away))
            for p in club.players
        }

    def club(self, side: Side) -> str:
        return (self.meta.home if side is Side.HOME else self.meta.away).name

    def player_name(self, player_id: str | None) -> str:
        return self.players[player_id][0].name if player_id in self.players else ""

    def score_line(self, snap: MatchSnapshot) -> str:
        return f"{self.meta.home.name} {snap.score.home}-{snap.score.away} {self.meta.away.name}"

    def momentum_words(self, value: float) -> str:
        """-1..+1 momentum as words, e.g. 'Rivermouth Rovers on top (0.62)'."""
        side = self.meta.home.name if value > 0 else self.meta.away.name
        strength = round(abs(value), 2)
        if strength >= 0.3:
            return f"{side} on top ({strength})"
        if strength >= 0.1:
            return f"{side} slightly on top ({strength})"
        return f"evenly balanced ({strength})"

    def match_stats(self, snap: MatchSnapshot) -> dict[str, Any]:
        h, a = snap.home, snap.away
        hn, an = self.meta.home.name, self.meta.away.name
        lead = hn if snap.momentum > 0.1 else an if snap.momentum < -0.1 else "neither side"
        return {
            "possession_pct": {hn: _pct(h.possession), an: _pct(a.possession)},
            "xg": {hn: round(h.shooting.xg, 2), an: round(a.shooting.xg, 2)},
            "shots": {hn: h.shooting.shots, an: a.shooting.shots},
            "shots_on_target": {hn: h.shooting.on_target, an: a.shooting.on_target},
            "pass_accuracy_pct": {hn: _pct(h.passing.accuracy), an: _pct(a.passing.accuracy)},
            "pressure_index_last_10_min": {
                hn: round(h.pressure_index_10min, 2),
                an: round(a.pressure_index_10min, 2),
            },
            "momentum": {"favours": lead, "strength": round(abs(snap.momentum), 2)},
            "game_state_last_10_min": {
                "label": snap.control_chaos_10min.label,
                "chaos_index": round(snap.control_chaos_10min.index, 2),
            },
        }

    def for_moment(self, moment: Moment, snap: MatchSnapshot) -> MomentFacts:
        d = moment.data
        team = self.club(moment.team) if moment.team else ""
        opp = self.club(moment.team.other) if moment.team else ""
        player = self.player_name(moment.player_id)
        minute = display_minute(moment.period, moment.minute)

        details: dict[str, Any] = {}
        fields: dict[str, str] = {
            "team": team,
            "opp": opp,
            "player": player,
            "minute": minute,
            "score": self.score_line(snap),
            "home": self.meta.home.name,
            "away": self.meta.away.name,
        }

        def put(key: str, value: Any, field: str | None = None, fmt: str = "{}") -> None:
            details[key] = value
            fields[field or key] = fmt.format(value)

        k = moment.kind
        if k is MomentKind.GOAL:
            put("xg", round(float(d.get("xg", 0)), 2))
            put("shot_speed_kmh", round(float(d.get("shot_speed_kmh", 0))), "speed")
            put("player_goals_this_match", int(d.get("player_goals", 1)), "goals")
            if d.get("assist_player_id"):
                put("assist", self.player_name(str(d["assist_player_id"])))
        elif k is MomentKind.BIG_CHANCE:
            put("xg", round(float(d["xg"]), 2))
            put("distance_m", round(float(d["distance_m"])), "distance")
            put("outcome", str(d["outcome"]).replace("_", " "))
        elif k is MomentKind.ROCKET_SHOT:
            put("shot_speed_kmh", round(float(d["speed_kmh"])), "speed")
            put("outcome", str(d["outcome"]).replace("_", " "))
        elif k is MomentKind.ELITE_PASS:
            put("pass_difficulty", int(d["difficulty"]), "difficulty")
            put("distance_m", round(float(d["distance_m"])), "distance")
            put("under_pressure", bool(d["under_pressure"]))
            put("receiver", self.player_name(str(d.get("recipient_id", ""))))
        elif k is MomentKind.TOP_SPEED:
            put("speed_kmh", round(float(d["speed_kmh"]), 1), "speed")
        elif k is MomentKind.PASS_MILESTONE:
            put("completed_passes", int(d["completed_passes"]), "passes")
        elif k is MomentKind.SHOT_MILESTONE:
            put("team_shots", int(d["team_shots"]), "shots")
        elif k is MomentKind.SUBSTITUTION:
            put("coming_on", self.player_name(str(d.get("on_player_id", ""))), "on_player")
        elif k is MomentKind.MOMENTUM_SHIFT:
            # Plain words, not a signed -1..+1 number: models misread the sign and said the
            # side that *gained* momentum had "collapsed".
            details["gaining_momentum"] = team
            put("momentum_5_min_ago", self.momentum_words(float(d["from"])), "from_desc")
            put("momentum_now", self.momentum_words(float(d["to"])), "to_desc")
        elif k is MomentKind.PRESSURE_SURGE:
            put("pressure_index_now", round(float(d["pressure_index"]), 2), "pressure")
            put("pressure_index_previous_10_min", round(float(d["previous"]), 2), "prev")
        elif k is MomentKind.CHAOS_SPELL:
            put("chaos_index", round(float(d["chaos_index"]), 2), "chaos")
            put("turnovers_per_min", round(float(d["turnovers_per_min"]), 1), "turnovers")
            put("passes_per_possession", round(float(d["avg_sequence_passes"]), 1), "seq")

        facts: dict[str, Any] = {
            "moment": k.value.replace("_", " "),
            "minute": minute,
            "period": "first half" if moment.period == 1 else "second half",
            "score": self.score_line(snap),
            "teams": {"home": self.meta.home.name, "away": self.meta.away.name},
        }
        if team:
            facts["team"] = team
        if player:
            pl = self.players[moment.player_id][0]
            facts["player"] = {"name": player, "role": POSITION_WORDS[pl.position.value]}
        if details:
            facts["details"] = details
        facts["match_so_far"] = self.match_stats(snap)
        names = {pid: p.name for pid, (p, _) in self.players.items()}
        return MomentFacts(facts=facts, fields=fields, players=names)

    def for_recap(self, snap: MatchSnapshot, moments: list[Moment]) -> MomentFacts:
        key = [m for m in moments if m.importance >= 0.6 and m.kind is not MomentKind.FULL_TIME]
        timeline = []
        for m in key[:14]:
            entry = {
                "minute": display_minute(m.period, m.minute),
                "moment": m.kind.value.replace("_", " "),
            }
            if m.team:
                entry["team"] = self.club(m.team)
            if m.player_id:
                entry["player"] = self.player_name(m.player_id)
            if m.kind is MomentKind.GOAL:
                entry["score_after"] = f"{m.data['score_home']}-{m.data['score_away']}"
            timeline.append(entry)
        top = [
            {
                "name": p.name,
                "team": self.club(p.team),
                "goals": p.goals,
                "assists": p.assists,
                "pass_accuracy_pct": _pct(p.passing.accuracy),
            }
            for p in snap.top_players[:3]
        ]
        facts = {
            "final_score": self.score_line(snap),
            "venue": self.meta.venue,
            "key_moments": timeline,
            "top_players": top,
            "match_stats": self.match_stats(snap),
        }
        fields = {
            "score": self.score_line(snap),
            "home": self.meta.home.name,
            "away": self.meta.away.name,
            "minute": "FT",
        }
        names = {pid: p.name for pid, (p, _) in self.players.items()}
        return MomentFacts(facts=facts, fields=fields, players=names)
