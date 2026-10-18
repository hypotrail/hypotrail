"""Numbers written in words, read back for ``hypotrail check`` (final acceptance F3).

An agent that may not compute in prose can still write a self-made ratio or count in
words ("roughly one call in nine", "the eleven kept columns"), which the digit parser
of :mod:`mlkit.study.cite` does not see. :func:`parse` finds the common English and
French forms and returns them as :class:`WordNumber` items that ``check`` traces like
digits.

What is read (English and French):

* cardinals from 0 to 100 ("eleven", "twenty-one", "vingt et un", "quatre-vingt-dix",
  "a hundred", "cent"), and "dozen" / "douzaine" (12; "two dozen" is 24);
* ratios: "one in nine", "one call in nine", "two out of three", "un sur neuf",
  "un client sur neuf";
* simple fractions: "half", "a third", "two thirds", "a quarter", "three quarters", "a
  fifth", "a tenth"; "la moitié", "un tiers", "deux tiers", "un quart", "trois quarts",
  "un cinquième", "un dixième";
* "<cardinal> percent" / "per cent" / "pour cent" is a percentage.

A word is read as a number **only when it is used quantitatively**, so ordinary prose is
not flagged:

* a cardinal is followed by a count noun (calls, clients, rows, columns, features, ...;
  "appels", "clients", "lignes", "colonnes", ...), possibly with one word between ("the
  eleven kept columns"), or by "percent", "times", "fois";
* "one" / "un" / "une" alone is never a count ("one model", "a single", "un modèle"); it
  counts only in a ratio ("one in nine") or a fraction ("one third");
* a ratio needs "in", "out of", or "sur" between two cardinals;
* a fraction needs "of", "the", "de", "des", "du", "d'", or a count noun after it ("half
  of the rows", "la moitié des clients"); "the first half", "the other half" are not read;
* ordinals ("first", "premier") are never numbers.

How a word number matches a registered value (:meth:`WordNumber.matches`):

* a cardinal or "dozen" is an integer written with no decimals, as digits would be;
* a percentage is that integer with a percent sign;
* a ratio "k in N" matches a rate ``v`` when ``k / v`` rounds to ``N`` ("one in nine"
  matches 0.1153, since 1 / 0.1153 is about 8.7), or a recorded value equal to ``k / N``;
* a fraction ``p / q`` matches a value within 0.02 of it (``FRACTION_TOLERANCE``: "half"
  is 0.48 to 0.52, not "about half" of 0.45).

Limits (documented in ``docs/specs/CLI-CONTRACT.md``): cardinals above 100 ("two hundred")
are not read; "a few", "several", "most", "dozens", and "a majority" are vague and not
read; a word number not followed by a listed count noun is not read (for example "nine
models"); compound forms beyond the ones listed are not read. Like digits, a word number
traces to the first registered value it matches at its precision.

Pure: no file I/O, no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- vocabulary -------------------------------------------------------------------------

_EN_UNITS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
             'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
             'seventeen', 'eighteen', 'nineteen']
_EN_TENS = {'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70,
            'eighty': 80, 'ninety': 90}
_FR_UNITS = ['zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
             'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize', 'dix-sept',
             'dix-huit', 'dix-neuf']
_FR_TENS = {'vingt': 20, 'trente': 30, 'quarante': 40, 'cinquante': 50, 'soixante': 60}


def _cardinals() -> dict[str, int]:
    out: dict[str, int] = {w: i for i, w in enumerate(_EN_UNITS)}
    for word, tens in _EN_TENS.items():
        out[word] = tens
        for i in range(1, 10):
            out[f'{word}-{_EN_UNITS[i]}'] = tens + i
            out[f'{word} {_EN_UNITS[i]}'] = tens + i
    out.update({'hundred': 100, 'a hundred': 100, 'one hundred': 100})
    out.update({w: i for i, w in enumerate(_FR_UNITS)})
    out['zero'] = 0
    out['une'] = 1
    for word, tens in _FR_TENS.items():
        out[word] = tens
        out[f'{word} et un'] = tens + 1
        out[f'{word} et une'] = tens + 1
        for i in range(2, 10):
            out[f'{word}-{_FR_UNITS[i]}'] = tens + i
    # 70-79: soixante-dix, soixante et onze, soixante-douze ... soixante-dix-neuf
    out['soixante-dix'] = 70
    out['soixante et onze'] = 71
    for i in range(12, 20):
        out[f'soixante-{_FR_UNITS[i]}'] = 60 + i
    # 80-99: quatre-vingts, quatre-vingt-un, ... quatre-vingt-dix-neuf
    out['quatre-vingts'] = 80
    out['quatre-vingt'] = 80
    for i in range(1, 20):
        out[f'quatre-vingt-{_FR_UNITS[i]}'] = 80 + i
    out['cent'] = 100
    out['dozen'] = 12
    out['a dozen'] = 12
    out['une douzaine'] = 12
    out['douzaine'] = 12
    return out


CARDINALS = _cardinals()
# Words that never count alone ("one model", "un modèle"): only in a ratio or a fraction.
SINGULAR = {'one', 'un', 'une'}
DOZEN = {'dozen': 12, 'douzaine': 12}

# Fractions: the denominator word and its value; numerators are cardinals or "a" / "un(e)".
_FRACTIONS = {'half': 2, 'halves': 2, 'third': 3, 'thirds': 3, 'quarter': 4, 'quarters': 4,
              'fifth': 5, 'fifths': 5, 'tenth': 10, 'tenths': 10,
              'moitié': 2, 'tiers': 3, 'quart': 4, 'quarts': 4, 'cinquième': 5,
              'cinquièmes': 5, 'dixième': 10, 'dixièmes': 10}

COUNT_NOUNS = (
    # English
    'calls', 'clients', 'customers', 'people', 'persons', 'contacts', 'rows', 'observations',
    'records', 'columns', 'features', 'variables', 'subscribers', 'subscriptions', 'members',
    'positives', 'negatives', 'cases', 'renewals', 'buyers', 'accounts', 'samples',
    'percentage points', 'percent', 'per cent', 'times',
    # French
    'appels', 'personnes', 'lignes', 'colonnes', 'abonnés', 'souscripteurs',
    'souscriptions', 'membres', 'positifs', 'négatifs', 'cas', 'comptes', 'échantillons',
    'pour cent', 'fois', 'points de pourcentage',
)
PERCENT_WORDS = ('percent', 'per cent', 'pour cent')
POINTS_WORDS = ('percentage points', 'points de pourcentage')
FRACTION_FOLLOWERS = ('of', 'the', 'de', 'des', 'du', "d'", 'd’')
FRACTION_TOLERANCE = 0.02
RATIO_LINKS = ('in', 'out of', 'sur')
# "the first half", "the other half", "la première moitié": positions, not quantities.
FRACTION_BLOCKERS = ('first', 'second', 'last', 'other', 'next', 'première', 'seconde',
                     'dernière', 'autre')


def _alt(words) -> str:
    return '|'.join(re.escape(w) for w in sorted(words, key=len, reverse=True))


_CARD = _alt(CARDINALS)
_NOUN = _alt(COUNT_NOUNS)
_FRAC = _alt(_FRACTIONS)
_WORD = r"[^\W\d_][\w'’-]*"
_B = r'(?<![\w-])'           # a word boundary that also refuses "-" ("twenty-one" is one word)
_E = r'(?![\w-])'

RATIO = re.compile(
    rf"{_B}(?P<k>{_CARD})(?:\s+(?P<mid>{_WORD}))?\s+(?P<link>in|out of|sur)\s+"
    rf"(?P<n>{_CARD}){_E}", re.IGNORECASE)
FRACTION = re.compile(
    rf"{_B}(?:(?P<num>{_CARD}|a|an|la|une?)\s+)?(?P<den>{_FRAC}){_E}"
    rf"(?=\s+(?:{_alt(FRACTION_FOLLOWERS)}|{_NOUN})\b|\s*d['’])", re.IGNORECASE)
COUNT = re.compile(
    rf"{_B}(?P<k>{_CARD}){_E}(?:\s+(?P<mid>{_WORD}))?\s+(?P<noun>{_NOUN})(?![\w])",
    re.IGNORECASE)
MULTIPLE_DOZEN = re.compile(rf"{_B}(?P<k>{_CARD})\s+(?P<d>dozen|douzaines?){_E}", re.IGNORECASE)


@dataclass(frozen=True)
class WordNumber:
    """A number written in words: its text, kind, value, and position.

    ``kind`` is ``count`` (an integer), ``percent`` (an integer percentage), ``points``
    (percentage points: a registered difference times 100, matched by ``check``),
    ``ratio`` ("k in N", value k / N) or ``fraction`` (p / q).
    """

    text: str
    kind: str
    value: float
    start: int
    end: int
    k: int = 0
    n: int = 0

    def matches(self, value: float, *, literal: bool = False) -> bool:
        """True when this word number is ``value`` at its precision (module docstring)."""
        if literal and abs(value - self.value) < 1e-9:
            return True
        if self.kind == 'count':
            return abs(value - self.value) <= 0.5 + 1e-12
        if self.kind in ('percent', 'points'):
            return abs(100 * value - self.value) <= 0.5 + 1e-12
        if self.kind == 'ratio':
            return 0 < value <= 1 and self.k > 0 and round(self.k / value) == self.n
        if self.kind == 'fraction':
            return abs(value - self.value) <= FRACTION_TOLERANCE + 1e-12
        return False


def _value(word: str) -> int | None:
    return CARDINALS.get(re.sub(r'\s+', ' ', word.lower()))


def _overlaps(span, taken) -> bool:
    return any(span[0] < e and s < span[1] for s, e in taken)


def parse(text: str) -> list[WordNumber]:
    """The numbers written in words in ``text``, used quantitatively, in text order."""
    out: list[WordNumber] = []
    taken: list[tuple[int, int]] = []

    def add(item: WordNumber) -> None:
        out.append(item)
        taken.append((item.start, item.end))

    for m in RATIO.finditer(text):
        k, n = _value(m.group('k')), _value(m.group('n'))
        if k is None or n is None or n == 0 or k > n:
            continue
        add(WordNumber(m.group(0), 'ratio', k / n, m.start(), m.end(), k=k, n=n))
    for m in FRACTION.finditer(text):
        if _overlaps(m.span(), taken):
            continue
        before = text[max(0, m.start() - 12):m.start()].lower().split()
        if before and before[-1] in FRACTION_BLOCKERS:
            continue
        num_word = (m.group('num') or '').lower()
        q = _FRACTIONS[m.group('den').lower()]
        p = _value(num_word) if num_word not in ('a', 'an', 'la', 'un', 'une', '') else 1
        if p is None or p == 0 or p > q:
            continue
        add(WordNumber(m.group(0), 'fraction', p / q, m.start(), m.end(), k=p, n=q))
    for m in MULTIPLE_DOZEN.finditer(text):
        if _overlaps(m.span(), taken):
            continue
        k = _value(m.group('k'))
        if k is None or k == 12:
            continue
        add(WordNumber(m.group(0), 'count', float(12 * k), m.start(), m.end(), k=12 * k))
    for m in COUNT.finditer(text):
        word = m.group('k')
        span = (m.start(), m.start() + len(word))
        if _overlaps(span, taken):
            continue
        k = _value(word)
        if k is None or word.lower() in SINGULAR:
            continue
        mid = (m.group('mid') or '').lower()
        if mid in ('of', 'de', 'des', 'in', 'sur', 'hundred', 'cent') or _value(mid) is not None:
            continue                     # "two hundred clients" is above 100: not read
        previous = text[:span[0]].split()
        if previous and _value(previous[-1].strip('-')) is not None:
            continue                     # "two hundred": the "hundred" of a larger number
        noun = re.sub(r'\s+', ' ', m.group('noun').lower())
        kind = ('percent' if noun in PERCENT_WORDS else 'points' if noun in POINTS_WORDS
                else 'count') if not mid else 'count'
        end = m.end() if kind in ('percent', 'points') else span[1]
        add(WordNumber(text[span[0]:end], kind, float(k), span[0], end, k=k))
    for word, value in DOZEN.items():           # "a dozen", "une douzaine" alone
        for m in re.finditer(rf"{_B}(?:a |une )?{word}{_E}", text, re.IGNORECASE):
            if not _overlaps(m.span(), taken):
                add(WordNumber(m.group(0), 'count', float(value), m.start(), m.end(), k=value))
    return sorted(out, key=lambda w: w.start)
