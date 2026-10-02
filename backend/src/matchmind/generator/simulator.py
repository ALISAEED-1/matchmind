"""Seeded possession-chain match simulator.

How it works
------------
* The match is a loop of *possessions*. Each possession starts from a restart
  (kickoff, throw-in, goal kick, free kick, keeper) or a turnover, and runs
  pass -> pass -> carry -> ... until the ball is lost, goes out, or a shot ends it.
* A hidden **momentum** value (-1..+1, positive favours home) drifts as an
  Ornstein-Uhlenbeck process towards a target set by squad strength, the score,
  red cards and the story. Momentum shifts pass completion, pressing, how direct
  a team plays and how often it shoots, which produces believable swings.
* Probabilities are computed in each team's *attacking frame* (x towards the
  opponent goal); events are emitted in absolute pitch coordinates.
* The generator records only observable facts (who, where, outcome, ball speed).
  Derived metrics such as xG or pass difficulty belong to the stats engine.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from matchmind.generator.clubs import COMPETITION
from matchmind.generator.stories import Story, StoryPlan, plan_story
from matchmind.geometry import dist_m
from matchmind.models import (
    PITCH_LENGTH_M,
    PITCH_WIDTH_M,
    Club,
    Event,
    EventType,
    Match,
    MatchMeta,
    Player,
    Position,
    Score,
    Side,
)

GENERATOR_VERSION = "1.0.0"

# 4-3-3 base positions in the attacking frame, same order as the starting XI.
SLOT_POSITIONS: tuple[tuple[float, float], ...] = (
    (5, 50),  # GK
    (30, 85),  # RB
    (22, 62),  # CB
    (22, 38),  # CB
    (30, 15),  # LB
    (40, 50),  # DM
    (52, 68),  # CM
    (52, 32),  # CM
    (70, 85),  # RW
    (70, 15),  # LW
    (78, 50),  # ST
)
GK_SLOT = 0
DEFENSIVE_SLOTS = (2, 3, 5)  # CBs and DM: candidates for a scripted red card
WIDE_POSITIONS = (Position.RW, Position.LW, Position.RB, Position.LB)
GOAL_HALF_WIDTH = 7.32 / 2 / PITCH_WIDTH_M * 100  # in y-units


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass
class Restart:
    side: Side
    kind: str  # kickoff | throw_in | goal_kick | free_kick | keeper | open_play
    ax: float = 50.0
    ay: float = 50.0
    player: Player | None = None
    delay_s: float = 0.0


@dataclass
class TeamState:
    side: Side
    club: Club
    slots: dict[int, Player]
    bench: list[Player]
    sub_minutes: list[int]
    yellows: set[str] = field(default_factory=set)
    sent_off: int = 0
    goals: int = 0

    def on_pitch(self) -> list[tuple[int, Player]]:
        return sorted(self.slots.items())

    def slot_of(self, player: Player) -> int | None:
        for slot, p in self.slots.items():
            if p.id == player.id:
                return slot
        return None

    def avg_rating(self) -> float:
        return sum(p.rating for p in self.slots.values()) / 11  # missing players count as 0


class MatchSimulator:
    def __init__(self, home: Club, away: Club, seed: int, story: Story = Story.NONE):
        self.rng = random.Random(seed)
        self.seed = seed
        self.home_club, self.away_club = home, away
        self.plan: StoryPlan = plan_story(story, self.rng)

        self.teams = {
            Side.HOME: self._team_state(Side.HOME, home),
            Side.AWAY: self._team_state(Side.AWAY, away),
        }
        self.stoppage = [
            self.rng.randint(1, 4),
            max(self.rng.randint(2, 6), self.plan.min_stoppage_p2),
        ]
        self.pending_goals = sorted(self.plan.goals, key=lambda g: g.minute)
        self.pending_reds = sorted(self.plan.red_cards, key=lambda r: r.minute)

        self.events: list[Event] = []
        self.period = 1
        self.clock_s = 0.0
        self.elapsed_ms = 0.0
        self.momentum = 0.0

    # ------------------------------------------------------------------ setup

    def _team_state(self, side: Side, club: Club) -> TeamState:
        n_subs = self.rng.randint(3, 4)
        minutes = sorted(self.rng.randint(55, 87) for _ in range(n_subs))
        return TeamState(
            side=side,
            club=club,
            slots=dict(enumerate(club.starters)),
            bench=list(club.bench),
            sub_minutes=minutes,
        )

    # ------------------------------------------------------------- clock/state

    @property
    def minute(self) -> int:
        return int(self.clock_s // 60)

    def _tick(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self.clock_s += seconds
        self.elapsed_ms += seconds * 1000
        theta, sigma = 0.004, 0.035
        target = self._momentum_target()
        self.momentum += theta * (target - self.momentum) * seconds
        self.momentum += sigma * math.sqrt(seconds) * self.rng.gauss(0, 1)
        self.momentum = _clamp(self.momentum, -1.0, 1.0)

    def _momentum_target(self) -> float:
        home, away = self.teams[Side.HOME], self.teams[Side.AWAY]
        strength = (home.avg_rating() - away.avg_rating()) / 15
        trailing_push = 0.12 * _clamp(away.goals - home.goals, -2, 2)
        home_advantage = 0.05
        target = strength + trailing_push + home_advantage + self.plan.bias_for_home(self.minute)
        return _clamp(target, -0.9, 0.9)

    def mom(self, side: Side) -> float:
        return self.momentum if side is Side.HOME else -self.momentum

    def _score(self) -> dict[str, int]:
        return {
            "score_home": self.teams[Side.HOME].goals,
            "score_away": self.teams[Side.AWAY].goals,
        }

    # --------------------------------------------------------------- geometry

    @staticmethod
    def to_abs(side: Side, ax: float, ay: float) -> tuple[float, float]:
        return (ax, ay) if side is Side.HOME else (100 - ax, 100 - ay)

    @staticmethod
    def player_pos(slot: int, ball_ax: float) -> tuple[float, float]:
        """A player's position in their own attacking frame, given the ball's x."""
        bx, by = SLOT_POSITIONS[slot]
        if slot == GK_SLOT:
            return bx + max(0.0, ball_ax - 50) * 0.12, by
        return _clamp(bx + (ball_ax - 50) * 0.45, 2, 95), by

    def _opponent_positions(self, side: Side, ax: float) -> list[tuple[Player, float, float]]:
        """Opponents' positions expressed in `side`'s attacking frame."""
        opp = self.teams[side.other]
        out = []
        for slot, p in opp.on_pitch():
            px, py = self.player_pos(slot, 100 - ax)
            out.append((p, 100 - px, 100 - py))
        return out

    def _nearest_opponent(
        self, side: Side, ax: float, ay: float, outfield_only: bool = True
    ) -> Player:
        best, best_d = None, float("inf")
        for p, px, py in self._opponent_positions(side, ax):
            if outfield_only and p.position is Position.GK:
                continue
            d = dist_m(ax, ay, px, py)
            if d < best_d:
                best, best_d = p, d
        assert best is not None
        return best

    def _nearest_teammate(self, side: Side, ax: float, ay: float) -> Player:
        team = self.teams[side]
        best, best_d = None, float("inf")
        for slot, p in team.on_pitch():
            if slot == GK_SLOT:
                continue
            px, py = self.player_pos(slot, ax)
            d = dist_m(ax, ay, px, py)
            if d < best_d:
                best, best_d = p, d
        assert best is not None
        return best

    def _goalkeeper(self, side: Side) -> Player:
        return self.teams[side].slots[GK_SLOT]

    # ---------------------------------------------------------------- emitting

    def _emit(
        self,
        etype: EventType,
        side: Side | None = None,
        player: Player | None = None,
        pos: tuple[float, float] | None = None,
        end: tuple[float, float] | None = None,
        *,
        frame: Side | None = None,
        related: Player | None = None,
        outcome: str | None = None,
        speed: float | None = None,
        under_pressure: bool = False,
        details: dict | None = None,
    ) -> None:
        """Emit an event. `pos`/`end` are in `frame`'s attacking frame (default: `side`)."""
        frame = frame or side
        x = y = ex = ey = None
        if pos is not None:
            x, y = self.to_abs(frame, *pos) if frame else pos
        if end is not None:
            ex, ey = self.to_abs(frame, *end) if frame else end
        self.events.append(
            Event(
                event_id=f"e{len(self.events) + 1:05d}",
                period=self.period,
                minute=self.minute,
                second=int(self.clock_s % 60),
                timestamp_ms=int(self.elapsed_ms),
                type=etype,
                team=side,
                player_id=player.id if player else None,
                related_player_id=related.id if related else None,
                x=None if x is None else round(_clamp(x, 0, 100), 1),
                y=None if y is None else round(_clamp(y, 0, 100), 1),
                end_x=None if ex is None else round(_clamp(ex, 0, 100), 1),
                end_y=None if ey is None else round(_clamp(ey, 0, 100), 1),
                outcome=outcome,
                ball_speed_kmh=None if speed is None else round(speed, 1),
                under_pressure=under_pressure,
                details=details or {},
            )
        )

    def _possession_change(self, new_side: Side, player: Player | None, pos, reason: str) -> None:
        """`pos` is in new_side's attacking frame."""
        self._emit(EventType.POSSESSION_CHANGE, new_side, player, pos, outcome=reason)

    # ----------------------------------------------------------- story checks

    def _goal_due(self, side: Side) -> bool:
        return bool(self.pending_goals) and (
            self.pending_goals[0].side is side and self.minute >= self.pending_goals[0].minute
        )

    # ------------------------------------------------------------------- run

    def run(self) -> Match:
        for period in (1, 2):
            self.period = period
            self.clock_s = 0.0 if period == 1 else 45 * 60.0
            end_s = (45 + self.stoppage[0]) * 60 if period == 1 else (90 + self.stoppage[1]) * 60
            spec = Restart(Side.HOME if period == 1 else Side.AWAY, "kickoff")
            while self.clock_s < end_s:
                spec = self._play(spec, end_s)
            end_type = EventType.HALF_TIME if period == 1 else EventType.FULL_TIME
            self._emit(end_type, details=self._score())
            self._tick(1)

        return Match(
            meta=MatchMeta(
                match_id=f"mm-{self.seed:04d}-{self.plan.story.value}",
                seed=self.seed,
                story=self.plan.story.value,
                generator_version=GENERATOR_VERSION,
                competition=COMPETITION,
                venue=self.home_club.venue,
                home=self.home_club,
                away=self.away_club,
                final_score=Score(
                    home=self.teams[Side.HOME].goals, away=self.teams[Side.AWAY].goals
                ),
                stoppage_minutes=self.stoppage,
            ),
            events=self.events,
        )

    # ---------------------------------------------------------- dead balls

    def _dead_ball_admin(self) -> Restart | None:
        """Substitutions and scripted red cards happen while the ball is dead."""
        for side in (Side.HOME, Side.AWAY):
            team = self.teams[side]
            while team.sub_minutes and self.minute >= team.sub_minutes[0] and team.bench:
                team.sub_minutes.pop(0)
                self._substitute(team)

        if self.pending_reds and self.minute >= self.pending_reds[0].minute:
            red = self.pending_reds.pop(0)
            return self._scripted_red(red.side)
        return None

    def _substitute(self, team: TeamState) -> None:
        outfield_bench = [p for p in team.bench if p.position is not Position.GK]
        candidates = [(s, p) for s, p in team.on_pitch() if s != GK_SLOT]
        if not outfield_bench or not candidates:
            return
        slot, off = self.rng.choice(candidates)
        same_role = [p for p in outfield_bench if p.position is off.position]
        on = self.rng.choice(same_role or outfield_bench)
        team.bench.remove(on)
        team.slots[slot] = on
        self._emit(
            EventType.SUBSTITUTION,
            team.side,
            off,
            related=on,
            details={"position": SLOT_POSITION_NAMES[slot]},
        )
        self._tick(self.rng.uniform(15, 25))

    def _scripted_red(self, side: Side) -> Restart:
        team = self.teams[side]
        slots = [s for s in DEFENSIVE_SLOTS if s in team.slots] or [
            s for s in team.slots if s != GK_SLOT
        ]
        slot = self.rng.choice(slots)
        offender = team.slots[slot]
        victim_side = side.other
        victim = self._attacker(victim_side)
        fx, fy = self.rng.uniform(68, 80), self.rng.uniform(30, 70)  # victim's frame
        self._emit(
            EventType.FOUL,
            side,
            offender,
            (fx, fy),
            frame=victim_side,
            related=victim,
            outcome="free_kick",
            details={"denied_goal_scoring_opportunity": True},
        )
        self._emit(EventType.CARD, side, offender, (fx, fy), frame=victim_side, outcome="red")
        del team.slots[slot]
        team.sent_off += 1
        self.momentum += 0.25 if victim_side is Side.HOME else -0.25
        return Restart(victim_side, "free_kick", fx, fy, victim, self.rng.uniform(50, 80))

    def _attacker(self, side: Side) -> Player:
        team = self.teams[side]
        for slot in (10, 8, 9, 7):
            if slot in team.slots:
                return team.slots[slot]
        return next(p for s, p in team.on_pitch() if s != GK_SLOT)

    # ------------------------------------------------------------- possession

    def _play(self, spec: Restart, end_s: float) -> Restart:
        self._tick(spec.delay_s)
        if spec.kind != "open_play":
            red_restart = self._dead_ball_admin()
            if red_restart is not None:
                return red_restart

        side = spec.side
        team = self.teams[side]
        ax, ay = spec.ax, spec.ay

        carrier = spec.player
        if carrier is None or team.slot_of(carrier) is None:
            carrier = self._restart_taker(side, spec)
        if spec.kind == "kickoff":
            carrier = self._attacker(side)
            ax, ay = 50.0, 50.0
            self._emit(EventType.KICKOFF, side, carrier, (ax, ay), details=self._score())

        forced = self._goal_due(side)
        # Scripted attacks finish from a varied spot: edge of the box to close range.
        shot_x = self.rng.uniform(83, 94) if forced else 100.0
        under = False
        last_passer: Player | None = None

        while self.clock_s < end_s:
            m = self.mom(side)

            # The opponent is overdue for a scripted goal: hand them the ball.
            if not forced and self._goal_due(side.other):
                return self._intercepted(side, carrier, ax, ay, under)

            # --- opponent pressure, possibly a tackle or foul
            if not forced and spec.kind != "kickoff":
                p_press = 0.07 + 0.10 * (ax / 100) + 0.06 * max(0.0, -m)
                if self.rng.random() < p_press:
                    presser = self._nearest_opponent(side, ax, ay)
                    self._emit(
                        EventType.PRESSURE,
                        side.other,
                        presser,
                        (ax, ay),
                        frame=side,
                        related=carrier,
                    )
                    self._tick(self.rng.uniform(0.4, 1.2))
                    under = True
                    if self.rng.random() < 0.50:
                        result = self._tackle(side, carrier, presser, ax, ay, m)
                        if result is not None:
                            return result
            spec.kind = "open_play"

            # --- shot?
            if (forced and ax >= shot_x) or (
                not forced and self.rng.random() < self._shot_prob(ax, ay, m)
            ):
                return self._shoot(side, carrier, ax, ay, under, forced, last_passer)

            # --- carry?
            p_carry = 0.07 + (0.08 if carrier.position in WIDE_POSITIONS else 0.0)
            if carrier.position is not Position.GK and self.rng.random() < p_carry:
                ax, ay = self._carry(side, carrier, ax, ay, under, m)
                under = False
                continue

            # --- pass
            recipient, ex, ey = self._choose_pass(side, carrier, ax, ay, m, forced)
            d = dist_m(ax, ay, ex, ey)
            fwd_m = (ex - ax) * PITCH_LENGTH_M / 100
            p_complete = (
                0.945
                - 0.006 * max(0.0, d - 15)
                - 0.002 * max(0.0, fwd_m)
                - 0.12 * under
                - 0.07 * (ex > 82)
                + 0.004 * (carrier.passing - 75)
                + 0.06 * m
            )
            success = forced or self.rng.random() < _clamp(p_complete, 0.30, 0.98)
            speed = _clamp(22 + d * 1.1 + 5 * under + self.rng.gauss(0, 4), 12, 95)

            if success:
                self._emit(
                    EventType.PASS,
                    side,
                    carrier,
                    (ax, ay),
                    (ex, ey),
                    related=recipient,
                    outcome="complete",
                    speed=speed,
                    under_pressure=under,
                )
                self._tick(1.8 + d / 12 + self.rng.uniform(1.5, 4.5))
                last_passer, carrier = carrier, recipient
                ax, ay = ex, ey
                under = False
                continue

            return self._failed_pass(side, carrier, recipient, ax, ay, ex, ey, speed, under)

        return Restart(side, "open_play", ax, ay, carrier)

    def _restart_taker(self, side: Side, spec: Restart) -> Player:
        if spec.kind in ("goal_kick", "keeper"):
            return self._goalkeeper(side)
        return self._nearest_teammate(side, spec.ax, spec.ay)

    def _shot_prob(self, ax: float, ay: float, m: float) -> float:
        if ax < 70:
            return 0.0
        centrality = 1 - abs(ay - 50) / 50
        return (0.038 + 0.29 * ((ax - 70) / 30) ** 1.5) * (0.5 + 0.5 * centrality) * (1 + 0.5 * m)

    def _choose_pass(
        self, side: Side, carrier: Player, ax: float, ay: float, m: float, forced: bool
    ) -> tuple[Player, float, float]:
        team = self.teams[side]
        weights, options = [], []
        for slot, p in team.on_pitch():
            if p.id == carrier.id or (slot == GK_SLOT and ax > 35):
                continue
            px, py = self.player_pos(slot, ax)
            d = dist_m(ax, ay, px, py)
            fwd = px - ax
            if forced:
                w = (1 + max(0.0, fwd)) ** 2 if fwd > -2 else 0.01
            else:
                w = math.exp(-(((d - 16) / 12) ** 2))
                w *= 1 + (0.6 + 0.5 * m) * max(0.0, fwd) / 15
                if fwd < -10:
                    w *= 0.6
            weights.append(max(w, 1e-4))
            options.append((p, px, py))
        p, px, py = self.rng.choices(options, weights=weights)[0]
        ex = _clamp(px + self.rng.gauss(0, 3), 1, 99)
        ey = _clamp(py + self.rng.gauss(0, 4), 1, 99)
        if forced:
            ex = max(ex, min(ax + self.rng.uniform(12, 22), 95))
            ey = _clamp(ey, 32, 68) if ex > 80 else ey
        return p, ex, ey

    def _carry(
        self, side: Side, carrier: Player, ax: float, ay: float, under: bool, m: float
    ) -> tuple[float, float]:
        wide = carrier.position in WIDE_POSITIONS
        length = self.rng.uniform(4, 30 if wide else 18)
        angle = self.rng.gauss(0, 0.5)
        ex = _clamp(ax + length * math.cos(angle) * 100 / PITCH_LENGTH_M, 1, 97)
        ey = _clamp(ay + length * math.sin(angle) * 100 / PITCH_WIDTH_M, 1, 99)
        real = dist_m(ax, ay, ex, ey)
        speed_mps = _clamp(
            3.0 + carrier.pace / 99 * 4.8 + 0.3 * m + self.rng.gauss(0, 0.5), 2.5, 9.6
        )
        duration_s = max(real / speed_mps, 0.6)
        self._emit(
            EventType.CARRY,
            side,
            carrier,
            (ax, ay),
            (ex, ey),
            outcome="complete",
            under_pressure=under,
            details={"duration_ms": int(duration_s * 1000)},
        )
        self._tick(duration_s)
        return ex, ey

    def _tackle(
        self, side: Side, carrier: Player, defender: Player, ax: float, ay: float, m: float
    ) -> Restart | None:
        defending = side.other
        if self.rng.random() < 0.38:
            self._emit(
                EventType.FOUL, defending, defender, (ax, ay), frame=side, related=carrier,
                outcome="free_kick",
            )  # fmt: skip
            team = self.teams[defending]
            if defender.id not in team.yellows and self.rng.random() < 0.18:
                team.yellows.add(defender.id)
                self._emit(
                    EventType.CARD, defending, defender, (ax, ay), frame=side, outcome="yellow"
                )
            return Restart(side, "free_kick", ax, ay, carrier, self.rng.uniform(22, 40))

        p_win = 0.48 + (defender.defending - carrier.rating) / 200 - 0.10 * m
        if self.rng.random() < _clamp(p_win, 0.2, 0.8):
            self._emit(
                EventType.TACKLE, defending, defender, (ax, ay), frame=side, related=carrier,
                outcome="won",
            )  # fmt: skip
            nx, ny = 100 - ax, 100 - ay
            self._possession_change(defending, defender, (nx, ny), "tackle")
            return Restart(defending, "open_play", nx, ny, defender, self.rng.uniform(0.3, 1.0))

        self._emit(
            EventType.TACKLE, defending, defender, (ax, ay), frame=side, related=carrier,
            outcome="lost",
        )  # fmt: skip
        self._tick(self.rng.uniform(0.3, 1.0))
        return None

    def _intercepted(
        self, side: Side, carrier: Player, ax: float, ay: float, under: bool
    ) -> Restart:
        recipient, ex, ey = self._choose_pass(side, carrier, ax, ay, self.mom(side), False)
        speed = _clamp(22 + dist_m(ax, ay, ex, ey) * 1.1, 12, 95)
        return self._failed_pass(
            side, carrier, recipient, ax, ay, ex, ey, speed, under, force="interception"
        )

    def _failed_pass(
        self,
        side: Side,
        carrier: Player,
        recipient: Player,
        ax: float,
        ay: float,
        ex: float,
        ey: float,
        speed: float,
        under: bool,
        force: str | None = None,
    ) -> Restart:
        defending = side.other
        r = self.rng.random()
        kind = force or ("interception" if r < 0.55 else "out" if r < 0.85 else "recovery")

        if kind == "out":
            ey = 0.5 if ey < 50 else 99.5
            self._emit(
                EventType.PASS, side, carrier, (ax, ay), (ex, ey), related=recipient,
                outcome="out", speed=speed, under_pressure=under,
            )  # fmt: skip
            self._tick(1.0 + dist_m(ax, ay, ex, ey) / 14)
            nx, ny = 100 - ex, 100 - ey
            self._possession_change(defending, None, (nx, ny), "out_of_play")
            return Restart(defending, "throw_in", nx, ny, None, self.rng.uniform(14, 26))

        # Ball cut out somewhere along its path.
        t = self.rng.uniform(0.45, 0.95)
        ix, iy = ax + (ex - ax) * t, ay + (ey - ay) * t
        self._emit(
            EventType.PASS, side, carrier, (ax, ay), (ix, iy), related=recipient,
            outcome="incomplete", speed=speed, under_pressure=under,
        )  # fmt: skip
        self._tick(0.6 + dist_m(ax, ay, ix, iy) / 16)
        winner = self._nearest_opponent(side, ix, iy, outfield_only=ix < 85)
        nx, ny = 100 - ix, 100 - iy
        if kind == "interception":
            self._emit(EventType.INTERCEPTION, defending, winner, (nx, ny), outcome="won")
        self._possession_change(defending, winner, (nx, ny), kind)
        return Restart(defending, "open_play", nx, ny, winner, self.rng.uniform(0.3, 1.0))

    # ------------------------------------------------------------------ shots

    def _shoot(
        self,
        side: Side,
        shooter: Player,
        ax: float,
        ay: float,
        under: bool,
        forced: bool,
        assister: Player | None,
    ) -> Restart:
        defending = side.other
        d = dist_m(ax, ay, 100, 50)
        header = ax > 88 and self.rng.random() < 0.18
        quality = math.exp(-0.13 * max(0.0, d - 6)) * (0.45 + 0.55 * (1 - abs(ay - 50) / 50))
        quality *= 1 + (shooter.finishing - 75) / 100
        quality *= 0.75 if under else 1.0
        quality *= 0.7 if header else 1.0
        p_goal = _clamp(quality * 0.30, 0.01, 0.60)

        if forced:
            outcome = "goal"
        elif self.rng.random() < p_goal:
            outcome = "saved" if self.plan.scripted_goals else "goal"
        else:
            r = self.rng.random()
            outcome = "saved" if r < 0.40 else "blocked" if r < 0.65 else "off_target"

        if outcome == "goal":
            target = (100.0, 50 + self.rng.uniform(-0.9, 0.9) * GOAL_HALF_WIDTH)
        elif outcome == "saved":
            target = (99.0, 50 + self.rng.uniform(-0.8, 0.8) * GOAL_HALF_WIDTH)
        elif outcome == "blocked":
            target = (
                min(ax + self.rng.uniform(2, 6), 97.0),
                _clamp(ay + self.rng.gauss(0, 3), 1, 99),
            )
        else:
            target = (
                100.0,
                50 + self.rng.choice([-1, 1]) * self.rng.uniform(1.2, 3.0) * GOAL_HALF_WIDTH,
            )

        if header:
            speed = self.rng.uniform(38, 70)
        else:
            speed = _clamp(self.rng.uniform(62, 112) * (0.9 + shooter.finishing / 750), 40, 130)

        self._emit(
            EventType.SHOT, side, shooter, (ax, ay), target, outcome=outcome, speed=speed,
            under_pressure=under, details={"body_part": "head" if header else "foot"},
        )  # fmt: skip
        self._tick(self.rng.uniform(1.0, 2.0))

        if outcome == "goal":
            team = self.teams[side]
            team.goals += 1
            if forced:
                self.pending_goals.pop(0)
            self.momentum += 0.15 if side is Side.HOME else -0.15
            self._emit(
                EventType.GOAL, side, shooter, target, related=assister, details=self._score()
            )
            return Restart(defending, "kickoff", delay_s=self.rng.uniform(55, 80))

        if outcome == "blocked":
            if self.rng.random() < 0.5:
                bx, by = _clamp(ax - self.rng.uniform(3, 10), 1, 99), ay
                return Restart(side, "open_play", bx, by, self._nearest_teammate(side, bx, by), 1.0)
            nx, ny = 100 - target[0], 100 - target[1]
            blocker = self._nearest_opponent(side, *target)
            self._possession_change(defending, blocker, (nx, ny), "shot_blocked")
            return Restart(defending, "open_play", nx, ny, blocker, 1.0)

        keeper = self._goalkeeper(defending)
        if outcome == "saved":
            self._possession_change(defending, keeper, (6, 50), "shot_saved")
            return Restart(defending, "keeper", 6, 50, keeper, self.rng.uniform(8, 16))
        self._possession_change(defending, keeper, (6, 50), "shot_off_target")
        return Restart(defending, "goal_kick", 6, 50, keeper, self.rng.uniform(22, 38))


SLOT_POSITION_NAMES = ("GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "LW", "ST")


def generate_match(home: Club, away: Club, seed: int, story: Story = Story.NONE) -> Match:
    return MatchSimulator(home, away, seed, story).run()
