"""Verifier: deterministic checks on everything an LLM agent writes.

It never calls a model. Problems it finds are sent back to the agent as
feedback for one retry; if the agent still fails, the orchestrator falls back
to a template card. Checks:

* **numbers**: every number in the text must appear in the facts (in any of
  its reasonable spellings: 0.27, 27%, 1-2, 59', 45+2'), apart from a few
  harmless ones like 0-3 and "10 men";
* **players**: no player who isn't in this match;
* **language**: Urdu/Arabic text must be in Arabic script, English in Latin;
* **length**: titles and bodies stay short enough for an overlay.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from typing import Any

from matchmind.generator.clubs import build_league

ALWAYS_OK = {"0", "1", "2", "3", "10", "11", "45", "90"}
_NUM = re.compile(r"\d+(?:\.\d+)?")
# Arabic-Indic (U+0660..) and Extended Arabic-Indic / Urdu (U+06F0..) digits, plus the
# Arabic decimal separator (U+066B), mapped to ASCII. Built from code points to stay encoding-proof.
_DIGITS = str.maketrans(
    "".join(chr(c) for c in range(0x0660, 0x066A))
    + "".join(chr(c) for c in range(0x06F0, 0x06FA))
    + chr(0x066B),
    "01234567890123456789.",
)
_ARABIC_LETTER = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")

MAX_LEN = {"title": 70, "body": 320, "why_it_matters": 260, "line": 220, "summary": 900}


def _canon(token: str) -> str:
    try:
        d = Decimal(token)
    except InvalidOperation:
        return token
    text = format(d.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def allowed_numbers(facts: Any) -> set[str]:
    """Every acceptable spelling of every number in the facts."""
    out: set[str] = set(ALWAYS_OK)

    def add_number(v: float) -> None:
        v = abs(v)  # text extraction drops the sign ("-0.37" is read as 0.37)
        out.add(_canon(str(v)))
        for digits in (0, 1, 2):
            out.add(_canon(str(round(v, digits))))
        if 0 < abs(v) <= 1:  # fractions may be quoted as percentages
            out.add(_canon(str(round(v * 100))))
            out.add(_canon(str(round(v * 100, 1))))

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, int | float):
            add_number(float(node))
        elif isinstance(node, str):
            for tok in _NUM.findall(node.translate(_DIGITS)):
                add_number(float(tok))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(k)
                walk(v)
        elif isinstance(node, list | tuple):
            for v in node:
                walk(v)

    walk(facts)
    return out


def numbers_in(text: str) -> list[str]:
    return [_canon(t) for t in _NUM.findall(text.translate(_DIGITS))]


_WORD = re.compile(r"[A-Za-z][A-Za-z']*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?:;])\s+|\n+")


def _strings(node: Any) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for k, v in node.items() for s in (*_strings(k), *_strings(v))]
    if isinstance(node, list | tuple):
        return [s for v in node for s in _strings(v)]
    return []


class Verifier:
    def __init__(self, match_player_names: Iterable[str], proper_nouns: Iterable[str] = ()):
        self.match_players = set(match_player_names)
        league = build_league()
        self.other_players = {
            p.name for club in league.values() for p in club.players
        } - self.match_players
        # Names stay in Latin letters in every language; ignore them for the script check.
        nouns = {*self.match_players, *proper_nouns, "xG", "km/h"}
        nouns |= {c.name for c in league.values()} | {c.venue for c in league.values()}
        self._nouns = sorted(nouns, key=len, reverse=True)

    def check_text(
        self,
        fields: dict[str, str | None],
        facts: Any,
        language: str = "en",
        forbidden: Iterable[tuple[str, str]] = (),
    ) -> list[str]:
        """`forbidden`: (regex, reason) pairs that English text must not match, e.g. an
        equaliser described as "restores the lead" (see facts.goal_effect)."""
        allowed = allowed_numbers(facts)
        problems: list[str] = []
        for name, text in fields.items():
            if not text:
                if name in ("title", "body", "line", "headline", "summary"):
                    problems.append(f"{name} is empty")
                continue
            limit = MAX_LEN.get(name)
            if limit and len(text) > limit:
                problems.append(f"{name} is {len(text)} characters; keep it under {limit}")
            bad = sorted({n for n in numbers_in(text) if n not in allowed})
            if bad:
                problems.append(f"{name} uses numbers not in FACTS: {', '.join(bad)}")
            for other in self.other_players:
                if other in text:
                    problems.append(f"{name} mentions {other}, who is not in this match")
            # English titles are often Title Case, so names are only checked in running text.
            title_case = language == "en" and name in ("title", "headline")
            unknown = [] if title_case else self._unknown_names(text, facts, language)
            if unknown:
                problems.append(
                    f"{name} mentions names not in FACTS: {', '.join(unknown)} "
                    "(only use players and clubs from FACTS)"
                )
            if language == "en":
                for pattern, reason in forbidden:
                    if re.search(pattern, text, re.IGNORECASE):
                        problems.append(f"{name} contradicts FACTS: {reason}")
            problems.extend(self._language(name, text, language))
        return problems

    def _unknown_names(self, text: str, facts: Any, language: str) -> list[str]:
        """Capitalised words that look like names but appear nowhere in FACTS.

        English: mid-sentence capitalised words (sentence starts are ordinary words).
        Urdu/Arabic: every Latin-letter word, since only names stay in Latin script.
        """
        vocab = {"xG", "km", "h", "I", "VAR"}
        for phrase in [*self._nouns, *_strings(facts)]:
            vocab.update(_WORD.findall(phrase))
        found: list[str] = []
        for sentence in _SENTENCE_SPLIT.split(text):
            words = _WORD.findall(sentence)
            for i, w in enumerate(words):
                w = w.removesuffix("'s").rstrip("'")  # possessives: Rovers's, Rovers'
                if language == "en" and (i == 0 or not w[0].isupper()):
                    continue
                if w not in vocab and w not in found:
                    found.append(w)
        return found

    def _language(self, name: str, text: str, language: str) -> list[str]:
        for noun in self._nouns:
            text = text.replace(noun, " ")
        arabic = len(_ARABIC_LETTER.findall(text))
        latin = len(_LATIN_LETTER.findall(text))
        letters = arabic + latin
        if letters == 0:
            return []
        if language in ("ur", "ar"):
            if arabic / letters < 0.8:
                label = "Urdu" if language == "ur" else "Arabic"
                return [f"{name} must be written in {label} script (names may stay in English)"]
        elif arabic > 0:
            return [f"{name} must be in English only"]
        return []
