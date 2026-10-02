# Metrics

Every number MatchMind shows or narrates is computed by the deterministic stats engine in
`backend/src/matchmind/stats/`. LLM agents receive these values and explain them; they never
calculate numbers themselves. Each metric is a pure function over the events seen so far, so the
same code drives live replay and the post-match recap.

All models are small and readable on purpose: an analyst can check any value by hand.

| Metric | Module | Range | What it means |
|---|---|---|---|
| Pass difficulty | `passing.py` | 0â€“100 | How hard a pass was to complete |
| Expected goals (xG) | `shooting.py` | 0.01â€“0.95 | Probability a shot becomes a goal |
| Possession | `possession.py` | 0â€“1 | Share of time on the ball |
| Pressure index | `pressure.py` | 0â€“1 | How aggressively a team is pressing |
| Momentum | `momentum.py` | âˆ’1â€¦+1 | Who is creating more danger right now (+ = home) |
| Control vs chaos | `chaos.py` | 0â€“1 | Settled possession (0) vs scrappy end-to-end play (1) |
| Carry speed / sprints | `physical.py` | km/h | Running speed with the ball |
| Key moments | `moments.py` | importance 0â€“1 | What deserves an insight card, and how urgently |

## Pass difficulty

```
z = 3.1 âˆ’ 0.05Â·max(0, distance âˆ’ 12 m) âˆ’ 0.025Â·forward progression (m)
        âˆ’ 0.9 if under pressure âˆ’ 0.5 if it ends in the final third âˆ’ 0.5 if it ends in the box
expected completion = sigmoid(z)
difficulty = 100 Â· (1 âˆ’ expected completion) / 0.75   (clamped 0â€“100)
```

Labels: `routine` < 30 â‰¤ `moderate` < 60 â‰¤ `hard` < 80 â‰¤ `elite`.
**Calibration:** across simulated matches, predicted completion is 87.4% vs 87.6% actual. Elite
completed passes are rare (about 0.5 per match), so they are worth a card.

## Expected goals (xG)

```
z  = âˆ’0.07 âˆ’ 0.147Â·distance to goal (m) âˆ’ 0.51 if header âˆ’ 0.26 if under pressure
xG = sigmoid(z)
```

Fitted by maximum likelihood on 4,797 shots from 200 natural synthetic matches (seeds 100â€“299).
A lateral-offset term came out at about 0 and was dropped. Reference values: 6 m central 0.28,
penalty spot 0.16, 20 m 0.05. **Out-of-sample check** (seeds 1â€“20): 52.4 xG vs 54 goals.

## Possession

Time between consecutive on-ball events (pass, carry, shot, kickoff) is credited to the team that
made the earlier one. Gaps over 15 s are treated as dead ball and ignored.

## Pressure index (PPDA-inspired)

```
work      = Î£ (pressure Ã—1, tackle Ã—1.5, interception Ã—1.5, foul Ã—0.5) Â· (0.5 + height up the pitch)
intensity = work / opponent passes and carries in the window
index     = intensity / (intensity + 0.30)
```

Reported over the last 10 minutes. A typical match averages 0.50; 10-minute spells range from
about 0.29 (5th percentile) to 0.67 (95th).

## Momentum

Each action carries a threat value: shot = xG + 0.05; completed pass into the box 0.04; pass into
the final third 0.02; carry into the box 0.04; ball won in the opponent's half 0.01. Threat is
summed per minute of play, decayed with a 4-minute half-life, and

```
momentum = tanh(1.2 Â· (home âˆ’ away) / (home + away + 0.25))
```

It is causal: the value at minute *t* only uses events up to *t*.

## Control vs chaos

Over the last 10 minutes, both teams together:

```
chaos = 0.40 Â· turnover rate      (scaled 0.8 â†’ 2.0 per min)
      + 0.30 Â· short sequences    (completed passes per possession, scaled 7 â†’ 2)
      + 0.15 Â· foul rate          (scaled 0.05 â†’ 0.40 per min)
      + 0.15 Â· pressured actions  (scaled 5% â†’ 25%)
```

Labels: `controlled` < 0.25 â‰¤ `balanced` â‰¤ 0.50 < `chaotic` (measured on simulated matches: 36% of
10-minute spells are controlled, 47% balanced, 17% chaotic).

## Speed

Carry speed = carry distance / duration. Sprint threshold 25.2 km/h (7 m/s); a top-speed alert
fires at 30 km/h or more (about 0.4 per match).

## Key moments

Detected in code, never by the LLM. Importance drives orchestration: high-importance moments get
the full agent team, low ones may get a template card or nothing.

| Moment | Trigger | Importance |
|---|---|---|
| `goal` | Goal event | 1.0 |
| `red_card` | Red card | 0.9 |
| `full_time` / `half_time` | Period end | 0.85 / 0.7 |
| `big_chance` | Missed shot with xG â‰¥ 0.25 | 0.6 + xG/2 |
| `momentum_shift` | Momentum moves â‰¥ 0.45 in 5 minutes (8-minute cooldown) | 0.6 |
| `pressure_surge` | Team's 10-minute pressure index â‰¥ 0.60 and up â‰¥ 0.12 on the previous 10 minutes | 0.5 |
| `chaos_spell` | Chaos index crosses above 0.55 | 0.45 |
| `rocket_shot` | Shot â‰¥ 108 km/h | 0.4 |
| `elite_pass` | Completed pass with difficulty â‰¥ 80 | 0.35 |
| `top_speed` | Carry â‰¥ 30 km/h | 0.35 |
| `yellow_card` | Yellow card | 0.3 |
| `pass_milestone` | Player's 50th completed pass | 0.3 |
| `shot_milestone` | Team's 10th / 20th shot | 0.25 |
| `substitution` | Substitution | 0.15 |

Trend moments (momentum, pressure, chaos) are evaluated at the end of each completed minute of play
using only earlier events. A test checks that detecting on a partial match returns exactly the full
match's moments up to that point, so live mode and the recap never disagree.

## Snapshot

`compute_snapshot(meta, events)` bundles all of the above (score, per-team possession, passing,
shooting, physical and pressing numbers, current momentum and the last 15 minutes of it, the
control-vs-chaos reading, and the top five players) into one JSON object of about 5 KB. This is
the input the LLM agents receive.
