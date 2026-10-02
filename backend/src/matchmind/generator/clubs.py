"""The fictional league: four clubs with stable, seeded squads.

Every name here is invented. Surnames were written to be unlikely to match any
real professional footballer, and squads are built from a fixed league seed so
a club's players are identical in every generated match.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from matchmind.models import Club, Player, Position

LEAGUE_SEED = 2026
COMPETITION = "MatchMind Synthetic League"


@dataclass(frozen=True)
class ClubSpec:
    id: str
    name: str
    short_name: str
    venue: str
    primary_color: str
    secondary_color: str
    strength: int  # average squad rating


CLUB_SPECS: dict[str, ClubSpec] = {
    s.id: s
    for s in (
        ClubSpec("RIV", "Rivermouth Rovers", "Rovers", "Estuary Park", "#0FA3B1", "#F5F5F5", 78),
        ClubSpec(
            "IRN", "Ironmere Athletic", "Ironmere", "Kilnworks Stadium", "#C0392B", "#2C2C2C", 76
        ),
        ClubSpec("KES", "Kestrel Vale", "Kestrels", "Vale Meadow", "#F5A623", "#1B2A49", 74),
        ClubSpec(
            "DUN", "Duncairn Harbour", "Harbour", "Lighthouse Arena", "#1F3A93", "#8EC5FC", 77
        ),
    )
}

FIRST_NAMES = (
    "Adam", "Amir", "Bruno", "Caio", "Dario", "Elias", "Emeka", "Felix", "Gabriel", "Hugo",
    "Idris", "Ivan", "Jonas", "Kofi", "Luca", "Malik", "Mateo", "Nico", "Omar", "Pavel",
    "Rafael", "Samir", "Theo", "Tomas", "Yusuf", "Zane", "Arlo", "Bilal", "Cian", "Dani",
    "Enzo", "Farid", "Goran", "Hamza", "Ilyas", "Joel", "Kenji", "Leon", "Milo", "Nadir",
    "Oscar", "Pablo", "Rami", "Sami", "Tariq", "Umar", "Viktor", "Wale", "Yannick", "Zaid",
    "Ali", "Bram", "Cyrus", "Dev", "Emil", "Femi", "Gio", "Hassan", "Isak", "Jude",
    "Kai", "Lars", "Marek", "Noel",
)  # fmt: skip

SURNAMES = (
    "Arvelle", "Bastrum", "Caldane", "Dorsetti", "Elkwood", "Farrowby", "Gravell", "Hollinde",
    "Istrane", "Jorvell", "Kesslar", "Lunetti", "Maraval", "Nesbury", "Orlund", "Pellacor",
    "Quenby", "Rastelli", "Sorvane", "Tamberly", "Ulvric", "Vantor", "Wexley", "Yarrowby",
    "Zevalo", "Okarie", "Mbanta", "Tshavu", "Nkoro", "Abimbe", "Diallen", "Kourama",
    "Sefane", "Benhadi", "Ouazar", "Taleni", "Morankwe", "Adesoro", "Valenzor", "Castellane",
    "Duvarro", "Esperon", "Ferraldi", "Guimardes", "Hernavo", "Iturrino", "Landeiro", "Montaval",
    "Navarel", "Orbeza", "Prestano", "Rovarro", "Salvetti", "Tavrelle", "Uribarri", "Vasconel",
    "Brannick", "Coldbeck", "Drummore", "Fenwright", "Glenholt", "Harrowell", "Lochrane",
    "Ravensby",
)  # fmt: skip

# Formation slots (4-3-3) then bench, with conventional shirt numbers.
SQUAD_TEMPLATE: tuple[tuple[Position, int], ...] = (
    (Position.GK, 1),
    (Position.RB, 2),
    (Position.CB, 4),
    (Position.CB, 5),
    (Position.LB, 3),
    (Position.DM, 6),
    (Position.CM, 8),
    (Position.CM, 10),
    (Position.RW, 7),
    (Position.LW, 11),
    (Position.ST, 9),
    # bench
    (Position.GK, 13),
    (Position.CB, 15),
    (Position.CM, 16),
    (Position.RW, 17),
    (Position.ST, 19),
)

# Attribute shaping per position: (pace, passing, finishing, defending) offsets.
_PROFILE: dict[Position, tuple[int, int, int, int]] = {
    Position.GK: (-15, -5, -30, 10),
    Position.RB: (6, -2, -12, 4),
    Position.LB: (6, -2, -12, 4),
    Position.CB: (-4, -4, -14, 10),
    Position.DM: (-2, 4, -8, 6),
    Position.CM: (0, 7, -2, 0),
    Position.AM: (2, 8, 4, -8),
    Position.RW: (10, 2, 4, -10),
    Position.LW: (10, 2, 4, -10),
    Position.ST: (5, -2, 10, -14),
}

SQUAD_SIZE = len(SQUAD_TEMPLATE)


def _clamp(v: float, lo: int = 40, hi: int = 99) -> int:
    return int(max(lo, min(hi, round(v))))


def build_league() -> dict[str, Club]:
    """Build all clubs deterministically from LEAGUE_SEED."""
    rng = random.Random(LEAGUE_SEED)
    surnames = list(SURNAMES)
    rng.shuffle(surnames)

    clubs: dict[str, Club] = {}
    for idx, spec in enumerate(CLUB_SPECS.values()):
        club_surnames = surnames[idx * SQUAD_SIZE : (idx + 1) * SQUAD_SIZE]
        players = []
        for (pos, shirt), surname in zip(SQUAD_TEMPLATE, club_surnames, strict=True):
            base = spec.strength + rng.gauss(0, 4)
            pace, passing, finishing, defending = _PROFILE[pos]
            players.append(
                Player(
                    id=f"{spec.id}-{shirt:02d}",
                    name=f"{rng.choice(FIRST_NAMES)} {surname}",
                    shirt=shirt,
                    position=pos,
                    rating=_clamp(base),
                    pace=_clamp(base + pace + rng.gauss(0, 4)),
                    passing=_clamp(base + passing + rng.gauss(0, 4)),
                    finishing=_clamp(base + finishing + rng.gauss(0, 4)),
                    defending=_clamp(base + defending + rng.gauss(0, 4)),
                )
            )
        clubs[spec.id] = Club(
            id=spec.id,
            name=spec.name,
            short_name=spec.short_name,
            venue=spec.venue,
            primary_color=spec.primary_color,
            secondary_color=spec.secondary_color,
            players=players,
        )
    return clubs
