"""Number tracing: where a number written in a text comes from (v0.3, WP-A).

One module traces the numbers of every free text the engine checks: ``hypotrail check
--text`` (a draft message), the conclusion of ``hypotrail check`` and, at ``decide
propose``, a proposal's restatement, rationale, labels and conclusion text. A text accepted
by one is accepted by the other: both build the same :class:`Pool` from the study's view
(:func:`study_pool`), and ``propose`` only adds the proposed value as a literal.

The matching rules are documented in :mod:`mlkit.study.cmd_check` and in
``docs/specs/CLI-CONTRACT.md`` (``hypotrail check``). Pure apart from :func:`study_pool`,
which reads the study; no pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any, Iterable, Mapping

from . import cite, wordnum

SEVERITY = {'number_outside_result': 'error', 'unknown_result_id': 'error',
            'value_mismatch': 'error', 'stale_result_cited': 'error',
            'feature_without_status': 'error', 'excluded_feature_used': 'error',
            'untraceable_number': 'error', 'stale_number': 'error',
            'causal_wording': 'warning', 'forecast_wording': 'warning',
            'artifact_not_current': 'warning', 'untracked_files': 'warning',
            # Post-v0.1 (P7): a recommended default credited to the analyst.
            'misattributed_delegation': 'error',
            # v0.2a (WP-A4): the conclusion adopts while the success criterion is not met
            # or its paired interval includes 0.
            'verdict_contradicts_criterion': 'warning',
            # B6c (H4): the conclusion keeps the baseline while the criterion is met on the
            # final test.
            'verdict_keeps_baseline_against_criterion': 'warning',
            # B6c (H2): a final-test figure in a text after the choice changed.
            'final_test_figure_outdated': 'error'}
SEVERITY['validity_requirement_missing'] = 'error'
FINDING_CODES = tuple(SEVERITY)

EXEMPT_BEFORE = re.compile(r'(?:revision|revisions|rev\.?|step|steps|pause|pauses|proposal|p_|'
                           r'request|req-|expected-revision|section|§|row|'
                           r'exit|exit code|exit status|exited with|exited with code)'
                           r'\s*[#:=]?\s*$', re.IGNORECASE)
# "revision 26 instead of 24", "revision 24 to 26", "revisions 24 and 26": every number of
# the comparison that follows "revision" is a revision too (D4). "and" and "or" continue
# only after the plural, so "at revision 26 and 115 clients" still checks 115.
REVISION_SPAN = re.compile(
    r'\brevision\s*[#:=]?\s*\d+(?:\s*(?:instead of|rather than|not|vs\.?|versus|to|->|\u2192)'
    r'\s*(?:revision\s*)?\d+(?![.,]\d))+'
    r'|\brevisions\s*\d+(?:\s*(?:,|and|or|to|-|\u2013)\s*\d+(?![.,]\d))+', re.IGNORECASE)
# A rule written as an identifier ("capacity:100", "threshold:0.2") names a rule; it is
# traced when it can be and never reported as a claim (D4).
RULE_IDENTIFIER = re.compile(r'\b(?:threshold|capacity|share)\s*:\s*(-?\d+(?:\.\d+)?)',
                             re.IGNORECASE)
# A result id prefix made only of digits ("(result 52659681)") is an identifier, not a
# figure (R3): at least this many digits, after one of these words or as the start of a
# registry ``result_id``.
RESULT_ID_DIGITS = re.compile(r'\d{6,}')
RESULT_ID_LEAD = re.compile(r'\b(?:results?(?:[ _-]?ids?)?|rids?|ids?|executions?(?:[ _-]?ids?)?)'
                            r'\s*[#:=]?\s*[`(\[]?\s*$', re.IGNORECASE)
# "29.5 percentage points": a difference of two rates, read as a percentage of a registered
# difference (``deltas``), never of a rate (D4).
PERCENTAGE_POINTS = re.compile(r'\s*(?:percentage[- ]points?|pp\b|p\.p\.|points? de pourcentage)',
                               re.IGNORECASE)
# v0.3 (WP-A, R33): "2.8 points", "11,8 pts" are percentage points too: a registered
# difference times 100, or a value already registered in points (``Pool.trace``).
BARE_POINTS = re.compile(r'\s*(?:points?|pts?)(?![\w])', re.IGNORECASE)
LIST_MARKER = re.compile(r'^\s*\d+[.)]\s', re.MULTILINE)
# A date, with an optional time of day (review round 4: the time is ``hh:mm`` with optional
# seconds, fraction and zone, so a number right after a date, "On 2026-10-25 241 clients", is
# still a number to trace).
ISO_DATE = re.compile(r'\b\d{4}-\d{2}-\d{2}'
                      r'(?:[T ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?\b')
HEADING_ORDINAL = re.compile(r'^(\s*#{1,6}\s+)\d+\.', re.MULTILINE)
# D8: nouns that name the study's own structure, by the view count they refer to.
STRUCTURE_NOUNS = {
    'features': ('columns', 'column', 'features', 'feature', 'variables', 'variable', 'inputs',
                 'predictors', 'colonnes', 'colonne'),
    'groups': ('groups', 'groupes'),
    'steps': ('steps', 'étapes'),
    'pauses': ('pauses', 'decision points'),
    'decisions': ('decisions', 'décisions'),
}
_STRUCTURE_NOUN = '|'.join(re.escape(n) for nouns in STRUCTURE_NOUNS.values()
                           for n in sorted(nouns, key=len, reverse=True))
STRUCTURE_AFTER = re.compile(rf"\s+(?:[^\W\d_][\w'’-]*\s+)?(?P<noun>{_STRUCTURE_NOUN})(?![\w])",
                             re.IGNORECASE)
# Review round 3 (E3-2): "2 development rows", "2 lignes de développement" (the count of
# the delayed-label limit, :meth:`Pool.partition_match`).
DEVELOPMENT_ROWS_AFTER = re.compile(r'\s+(?:development\s+rows?|lignes?\s+de\s+d[ée]veloppement)'
                                    r'(?![\w])', re.IGNORECASE)
USABLE_STATUSES = ('available_at_prediction', 'uncertain_included')
EXCLUDED_STATUSES = ('not_available', 'uncertain_excluded')


def finding(code: str, where: str, message: str, *, location: dict | None = None,
            **details) -> dict:
    """One finding. ``location`` (CLI-CONTRACT-COMPANION C10, optional) is
    ``{path, anchor, line}``: the study-relative file, the nearest enclosing HTML ``id``, and
    the 1-based line; ``where`` is unchanged."""
    out = {'code': code, 'severity': SEVERITY[code], 'where': where, 'message': message}
    if details:
        out['details'] = details
    if location is not None:
        out['location'] = location
    return out


LOCATION_KEYS = ('path', 'anchor', 'line')


def location(path: str | None, anchor: str | None = None, line: int | None = None) -> dict:
    return {'path': path, 'anchor': anchor, 'line': line}


# --- number pools -----------------------------------------------------------------------

def _walk_numbers(value: Any, language: str | None = None) -> Iterable[float]:
    if cite.is_number(value):
        yield float(value)
    elif isinstance(value, str):
        for tok in cite.parse_numbers(value, language):
            yield tok.value / 100 if tok.percent else tok.value
        for word in wordnum.parse(value):         # F3: "one in ten" written by the junior
            yield word.value / 100 if word.kind in ('percent', 'points') else word.value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _walk_numbers(v, language)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_numbers(v, language)


# WP-A9 (H2): paths of a result that a free text never cites. They are a result's internals
# (null-band shuffles, the quality card's value ranges, bootstrap replicate counts, seeds,
# settings, coefficients, tie-breaking details), and a figure that happens to equal one of
# them was traced to it ("La précision du modèle est de 10 %" traced to a null band). The
# rendered deliverables cite by path (``data-result-id``) and are not affected.
INTERNAL_SEGMENTS = frozenset({
    'null_band', 'undefined_replicates', 'replicates', 'seed', 'shuffles', 'max_groups',
    'min_group_rows', 'iterations', 'n_terms', 'coefficients', 'intercept', 'cut',
    'tied_at_cut', 'folds', 'rank', 'bin_width', 'n_bins', 'fitted', 'preprocessing',
    'questions', 'co_occurrence',
    # WP-B1 (WP-A9 merge): per-fold metrics and fold sizes, the variant's penalty, the
    # final test's refit details and rule parameters.
    'per_fold', 'fold_rows', 'C', 'candidate_C', 'refit', 'parameter',
    # v0.3 (WP-A): the per-fold figures of a policy evaluation, like a fit's.
    'by_fold'})
INTERNAL_BY_SLOT = {'eda.quality': frozenset({'ranges', 'rare', 'rare_rows'})}
# WP-A9 (H2): words near a number that name what it measures, and the path segments a
# matching registry value must contain ("précision ... 10 %" binds to a precision). A count
# noun ("50 clients") binds a number without a percent sign to a count.
METRIC_WORDS = (
    (re.compile(r'\b(?:precision|pr[ée]cision|hit\s+rate|taux\s+de\s+r[ée]ussite)\b', re.I),
     ('precision',)),
    (re.compile(r'\b(?:recall|rappel|couverture|coverage)\b', re.I), ('recall',)),
    (re.compile(r'\b(?:auc|roc)\b', re.I), ('roc_auc',)),
    (re.compile(r'\blift\b', re.I), ('lift',)),
    # WP-B6b: "la précision gagne 21,4 points" (the French verb) names a gain too.
    (re.compile(r'\b(?:gain|gains|gagn\w*)\b', re.I), ('gain_points', 'deltas', 'gain')),
    (re.compile(r'\b(?:mae|rmse|error|errors|erreur|erreurs|residual\w*|r[ée]sidu\w*)\b', re.I),
     ('mae', 'rmse', 'error', 'residual')),
    (re.compile(r'\b(?:missing|manquant\w*|absent\w*)\b', re.I), ('missing',)),
    (re.compile(r'\b(?:calibra\w*|brier)\b', re.I), ('calibration', 'brier')),
    (re.compile(r'\b(?:distinct\w*|modalit[ée]s?|categor\w*|cat[ée]gor\w*)\b', re.I),
     ('n_distinct', 'groups', 'n_groups')),
)
RATE_WORDS = re.compile(r'\b(?:rate|rates|taux|share|part|proportion|pourcentage|percentage)\b',
                        re.I)
RATE_SEGMENTS = ('rate', 'share', 'precision', 'recall', 'fraction', 'missing', 'gain', 'lift',
                 'deltas', 'interval', 'level', 'average_precision', 'roc_auc', 'point',
                 # WP-B6b (round 2): a calibration bin's observed rate and its interval
                 # bounds (``calibration.bins.N.low``).
                 'calibration')
COUNT_NOUNS = re.compile(
    r'\b(?:clients?|customers?|rows?|lignes?|calls?|appels?|sessions?|observations?|people|'
    r'personnes?|subscribers?|souscripteurs?|souscriptions?|positives?|positifs?|contacts?|'
    r'members?|membres?|cases?|cas|individus?|records?|enregistrements?|visits?|visites?|'
    r'buyers?|acheteurs?|cars?|voitures?)\b', re.I)
COUNT_SEGMENTS = frozenset({'n', 'n_rows', 'n_positive', 'n_negative', 'selected', 'volume',
                            'true_positives', 'false_positives', 'false_negatives', 'capacity',
                            'n_train', 'n_train_positive', 'n_special', 'n_missing', 'n_a',
                            'n_b', 'n_both', 'n_either', 'n_groups', 'n_distinct', 'rows',
                            'development_rows', 'n_rows_with_missing', '@n_rows', 'point',
                            'low', 'high'})
GROUP_COUNT_SEGMENTS = COUNT_SEGMENTS - {'point', 'low', 'high', '@n_rows'}
_NEAR_BEFORE, _NEAR_AFTER = 60, 30


def _rule_texts(values: Any):
    """v0.3 (WP-J): the engine's rule texts inside a result (string values of a key ending
    in ``_rule``, such as a diagnostic's ``small_cell_rule``)."""
    if isinstance(values, Mapping):
        for k, v in values.items():
            if isinstance(v, str) and str(k).endswith('_rule'):
                yield v
            elif isinstance(v, (Mapping, list)):
                yield from _rule_texts(v)
    elif isinstance(values, list):
        for v in values:
            yield from _rule_texts(v)


def internal_path(slot: str, path: str) -> bool:
    """WP-A9 (H2): a result path a free text never cites (:data:`INTERNAL_SEGMENTS`)."""
    if not path or path in cite.META_PATHS:
        return False
    try:
        segments = cite.parse_path(path)
    except Exception:      # noqa: BLE001 - an unreadable path is not cited either
        return True
    internal = INTERNAL_SEGMENTS
    if slot.startswith(DIAGNOSTIC_SLOTS):
        # WP-B6b: a diagnostic's coefficients and their bootstrap intervals are what the
        # agent is asked to read with the junior (CLAUDE.md, "Diagnostics"); a fit's raw
        # coefficients stay internal. The refit check of the point stays internal.
        # The scatter points are drawn, never shown as figures (WP-B4).
        internal = (internal - {'coefficients'}) | {'point_check', 'scatter'}
    if internal & set(segments):
        return True
    return bool(INTERNAL_BY_SLOT.get(slot, frozenset()) & set(segments))


DIAGNOSTIC_SLOTS = ('diag.',)


INTERVAL_WORDS = re.compile(r'\b(?:intervals?|intervalles?|between|entre|ranges?|fourchette|'
                            r'ci|ic|bounds?|bornes?|resamples?|bootstrap)\b|[\[\]–]'
                            r'|\d\s*%?\s*(?:to|à|-)\s*[-−]?\d', re.I)
# WP-B6b: "model year(s)" (a time column) names no model.
MODEL_WORDS = re.compile(r'\b(?:model(?![\s_-]+years?\b)|mod[èe]le|logisti\w*|linear|'
                         r'lin[ée]aire)\b', re.I)
# WP-B6b: the first bound of a range written after the number ("3.49 à 4.18", "40% to 54%").
RANGE_AFTER = re.compile(r'\s*%?\s*(?:to|à|-|–)\s*[-−]?\d', re.I)
# ... and the second bound ("3.44 à 4.13"): the number follows a bound and a range word.
RANGE_BEFORE = re.compile(r'\d\s*%?\s*(?:to|à|-|–)\s*[-−]?$', re.I)
BASELINE_WORDS = re.compile(r'\b(?:baseline|r[ée]f[ée]rence|constant\w*|base|mean|moyenne)\b',
                            re.I)
INTERVAL_PARENTS = frozenset({'interval', 'intervals', 'deltas'})
SENTENCE_END = re.compile(r'[.!?](?=\s|$)|[;\n]')


# B6c (H2): the evidence a sentence speaks of. A figure said of the final test traces to the
# final evidence only (the one final evaluation and its diagnostics); a figure said of the
# development evidence (out of fold, cross-validated, validation) never traces to it.
FINAL_SCOPE = re.compile(r"\b(?:final[- ]test\w*|tests?[- ]finals?|final evaluation|"
                         r"[ée]valuation finale|sealed rows|lignes scell[ée]es)\b", re.I)
DEVELOPMENT_SCOPE = re.compile(r"\b(?:out[- ]of[- ]fold|hors[- ]pli\w*|cross[- ]validat\w*|"
                               r"validation crois[ée]e|development|d[ée]veloppement|"
                               r"validation)\b", re.I)
FINAL_SLOTS = ('final_test.evaluation', 'diag.final_test')
# B6c (H2): a percentage right after a rule word ("la règle des 20 %", "the top 20%") is the
# rule's share: it matches the rule the evidence of the sentence evaluated.
RULE_WORDS = re.compile(r"\b(?:rules?|r[èe]gles?|top|share|capacit\w*|meilleur\w*|best|"
                        r"premi[èe]r\w*)\b[^\d]{0,14}$", re.I)
# B6c (H2): the bounds of a diagnostic's segments and intervals are internals unless the
# words speak of an interval.
DIAG_BOUNDS = ('low', 'high', 'precision_low', 'precision_high', 'recall_low', 'recall_high')
# B6c (H2): decisions whose change after the opening means the final test no longer measured
# the configuration a text would claim.
CHOICE_CHANGES = ('policy', 'model_choice', 'model_variant', 'preprocessing',
                  'feature_availability', 'split')
# v0.3 (WP-J): a percentage that names an interval's level ("MAE (95% interval)",
# « intervalle de confiance à 95 % », "95% CI") is that level, whatever metric the clause
# names: it matches a registered ``level`` or the bootstrap setting, never a metric's value.
LEVEL_AFTER = re.compile(r'\s*(?:-\s*)?(?:confidence\s+)?(?:intervals?\b|ci\b|confidence\b|'
                         r'bootstrap\b|level\b)', re.I)
LEVEL_BEFORE = re.compile(r'(?:intervalles?(?:\s+de\s+confiance)?|\bic|\bci|confidence(?:\s+level)?|'
                          r'niveau(?:\s+de\s+confiance)?|level)\s*(?:à|at|de|of|:)?\s*$', re.I)
LEVEL_BINDING = ('level',)
# v0.3 (WP-J): a number right after a threshold word ("fewer than 30 rows", « moins de 30
# lignes ») may be one of the thresholds the engine applied and states (``min_group_rows``,
# ``max_groups``, the numbers of a ``*_rule`` text such as a diagnostic's small-cell rule),
# which are internals otherwise.
THRESHOLD_BEFORE = re.compile(r'(?:\b(?:fewer|less|more|greater)\s+than|\bat\s+(?:least|most)|'
                              r'\bunder|\bbelow|\babove|\bover|\bmoins\s+de|\bplus\s+de|'
                              r'\bau\s+(?:moins|plus)|\bmin(?:imum)?(?:\s+(?:of|de))?|'
                              r'\bmax(?:imum)?(?:\s+(?:of|de))?|\bseuil(?:\s+de)?|'
                              r'\bthreshold(?:\s+of)?|[<>≤≥])\s*$', re.I)
THRESHOLD_SEGMENTS = frozenset({'min_group_rows', 'max_groups', 'min_rows',
                                'min_segment_rows', 'min_segment_positives'})
# v0.3 (WP-J): "333 of 459", « 333 étudiants sur 459 »: two counts of one group, the group
# named in another language or in an earlier sentence; both must be counts of the same group
# of a current result.
PAIR_SEPARATOR = re.compile(r'\s*(?:[^\W\d_][\w\'’-]*\s+){0,2}(?:sur|of|out\s+of|parmi|among|/)'
                            r'\s*$', re.I)


@dataclasses.dataclass(frozen=True)
class Binding:
    """WP-A9 (H2): what the words near a number say it measures. ``segments``: path
    segments a matching value must hold (None: any). ``interval``: interval words are near,
    so an interval's bound may match (without them only point values do). ``model``: a model
    is named and the baseline is not, so the baseline's values do not match. B6c (H2):
    ``scope`` is ``final`` or ``development`` when the sentence speaks of one evidence only;
    ``rule`` when the number is a rule's share ("la règle des 20 %").

    v0.3 (WP-A, scope-bound matching): ``results`` is the set of result ids the sentence
    names (a result id or its prefix, a slot name) or the check runs in (``check
    --result``); a number then matches values of those results only, never a coincident
    value of another result. ``labels`` are the group labels the sentence names ("Nov",
    "Returning_Visitor", a feature of the single-feature signal): a value inside a group
    then matches only when its group is named."""
    segments: tuple | None = None
    interval: bool = False
    model: bool = False
    scope: str | None = None
    rule: bool = False
    results: frozenset | None = None
    labels: frozenset = frozenset()


def scope_of(sentence: str) -> str | None:
    """B6c (H2): ``final``, ``development``, or None (both, or neither, named)."""
    final = bool(FINAL_SCOPE.search(sentence))
    development = bool(DEVELOPMENT_SCOPE.search(FINAL_SCOPE.sub(' ', sentence)))
    if final and not development:
        return 'final'
    if development and not final:
        return 'development'
    return None


def final_item(item: Mapping) -> bool:
    """B6c (H2): a pool item of the final evidence: the final evaluation, its diagnostics,
    or the criterion judged on the final test (WP-B6b's ``criterion.final_test`` items)."""
    return item.get('slot') in FINAL_SLOTS or (
        item.get('slot') == 'criterion'
        and str(item.get('path') or '').startswith('criterion.final_test'))


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    ends = [m.end() for m in SENTENCE_END.finditer(text, 0, start)]
    lo = ends[-1] if ends else 0
    m = SENTENCE_END.search(text, end)
    return lo, (m.start() if m else len(text))


def _sentence_around(text: str, start: int, end: int) -> str:
    lo, hi = _sentence_bounds(text, start, end)
    return text[lo:hi]


def binding(text: str, start: int, end: int, percent: bool) -> Binding:
    """WP-A9 (H2): the :class:`Binding` of a number at ``text[start:end]``, from the words
    near it in its sentence (:data:`METRIC_WORDS`, a count noun after a number without a
    percent sign, interval and model words)."""
    lo = max(0, start - _NEAR_BEFORE)
    hi = min(len(text), end + _NEAR_AFTER)
    before, after = text[lo:start], text[end:hi]
    # The clause: a sentence end (never the point of a decimal number), a semicolon.
    ends = [m.end() for m in SENTENCE_END.finditer(before)]
    if ends:
        before = before[ends[-1]:]
    stops = [i for i in (after.find('. '), after.find('\n'), after.find(';'), after.find(','),
                         after.find(':'), after.find('('), after.find(')')) if i >= 0]
    if stops:
        after = after[:min(stops)]
    # The words that name what a number measures: before it in its clause, or the first
    # three words after it ("42 % precision", "50 clients").
    soon = ' '.join(after.split()[:3])
    named = before + ' ' + soon
    near = before + ' ' + after
    # A count noun right after the number, or after one qualifying word ("90 validation
    # rows", "50 clients").
    count = not percent and bool(COUNT_NOUNS.search(' '.join(soon.split()[:2])))
    out: list[str] = []
    if not count:
        for pattern, segments in METRIC_WORDS:
            if pattern.search(named):
                out.extend(segments)
        if RATE_WORDS.search(named):
            out.extend(RATE_SEGMENTS)
    return Binding(segments=('#count',) if count else (tuple(dict.fromkeys(out)) or None),
                   interval=bool(INTERVAL_WORDS.search(near) or RANGE_AFTER.match(text, end)
                                 or RANGE_BEFORE.search(text, max(0, start - 20), start)),
                   model=bool(MODEL_WORDS.search(named)) and not BASELINE_WORDS.search(near),
                   scope=scope_of(_sentence_around(text, start, end)),
                   rule=percent and bool(RULE_WORDS.search(text[max(0, start - 30):start])))


def _bound(item: Mapping, bind: Binding | None) -> bool:
    """A registry item a number with the binding ``bind`` may match."""
    if bind is None:
        return True
    path = item['path']
    try:
        segments = cite.parse_path(path) if path not in cite.META_PATHS else [path]
    except Exception:      # noqa: BLE001
        return False
    slot = str(item.get('slot') or '')
    # B6c (H2): the evidence the sentence speaks of.
    if bind.scope == 'final' and not final_item(item):
        return False
    if bind.scope == 'development' and final_item(item):
        return False
    # v0.3 (WP-A): a number of a sentence that names results binds to them only.
    if bind.results is not None and item.get('result_id') not in bind.results:
        return False
    labels = item.get('labels') or ()
    if labels and bind.labels and labels[-1] not in bind.labels:
        # The sentence names groups: a value of another group is not what it speaks of.
        return False
    if bind.rule:
        # A rule's share matches the share of a rule that evidence evaluated.
        return segments[-1] == 'capacity_share'
    if slot.startswith('diag.') and not bind.interval and segments[-1] in DIAG_BOUNDS:
        return False
    if slot.startswith('diag.') and 'segments' in segments \
            and not (labels and labels[-1] in bind.labels):
        # v0.3 (WP-A): a diagnostic's segment figures (selected, precision, recall of one
        # group) are citable when the sentence names the group, never by coincidence.
        return False
    if not bind.interval and segments[-1] in ('low', 'high') \
            and INTERVAL_PARENTS & set(segments[:-1]):
        return False
    if bind.model and any(seg == 'fit.baseline' or seg.startswith('baseline')
                          for seg in segments):
        return False
    if bind.segments is None:
        return True
    if bind.segments == ('#count',):
        return segments[-1] in COUNT_SEGMENTS
    if any(b in seg for seg in segments for b in bind.segments):
        return True
    # v0.3 (WP-A): a result that states its metric (the single-feature signal's scores are
    # out-of-fold AUCs, ``metric: roc_auc``) answers to that metric's words.
    metric = item.get('metric')
    return isinstance(metric, str) and any(b in metric for b in bind.segments)


def group_labels(values: Any) -> list[str]:
    """WP-B6b: the text labels of a result's groups (``groups: [{value|label: "<text>"}]``,
    as the EDA, the residuals by period and the diagnostics by variable print them)."""
    out: list[str] = []
    if isinstance(values, Mapping):
        for key, v in values.items():
            if key == 'groups' and isinstance(v, list):
                out += [g[k] for g in v if isinstance(g, Mapping)
                        for k in ('value', 'label') if isinstance(g.get(k), str)]
            out += group_labels(v)
    elif isinstance(values, list):
        for v in values:
            out += group_labels(v)
    return out


CRITERION_FIGURES = ('gain', 'low', 'high')


def criterion_items(criterion: Mapping | None) -> list[dict]:
    """WP-B6b: the citable figures of ``view.criterion`` (development, then final test),
    as pool items of the result each was read from."""
    if not isinstance(criterion, Mapping):
        return []
    metric = criterion.get('metric') or 'criterion'
    out = []
    for prefix, block in (('criterion', criterion),
                          ('criterion.final_test', criterion.get('final_test'))):
        if not isinstance(block, Mapping) or not isinstance(block.get('result_id'), str):
            continue
        for key in CRITERION_FIGURES:
            value = block.get(key)
            if cite.is_number(value):
                out.append({'result_id': block['result_id'], 'slot': 'criterion',
                            'path': f'{prefix}.{metric}.{key}', 'value': value})
    return out


# v0.3 (WP-A): the last path segments that name a difference of two shares: a gap (the
# calibration's mean absolute gap, the single-feature signal's gap) or a gain.
DIFFERENCE_LEAVES = ('gap', 'mean_absolute_gap', 'gain')


def _is_difference(path: str) -> bool:
    """True when a value path addresses a registered difference (``deltas``, a gap, a
    gain): a figure written in percentage points is one of these times 100."""
    if not path or path in cite.META_PATHS:
        return False
    segments = cite.parse_path(path)
    return any('delta' in seg or 'difference' in seg for seg in segments) \
        or segments[-1] in DIFFERENCE_LEAVES


def _points_valued(path: str) -> bool:
    """v0.3 (WP-A): a value the engine already registers in percentage points (the gain of
    the top shares, ``gain_points``; the success criterion of a scoring study): a figure
    written in points matches it as it is."""
    if not path or path in cite.META_PATHS:
        return False
    segments = cite.parse_path(path)
    return segments[0] == 'criterion' or segments[-1] == 'gain_points'


# v0.3 (WP-A): keys of a list item that name its group (a segment's ``column``, a group's
# ``value`` or ``label``, a signal's ``feature``).
LABEL_KEYS = ('column', 'value', 'label', 'feature')
# Group labels too common in prose to name a group.
COMMON_LABELS = frozenset({'yes', 'no', 'oui', 'non', 'true', 'false', 'other', 'autre',
                           'unknown', 'none', 'may', 'all', 'total', 'missing'})


def labelled_leaves(values: Any, prefix: tuple = (), labels: tuple = ()):
    """Every numeric leaf of ``values`` as ``(segments, value, labels)``: ``labels`` are the
    names of the list items it sits in (outermost first), as :data:`LABEL_KEYS` give them."""
    if cite.is_number(values):
        yield prefix, values, labels
    elif isinstance(values, Mapping):
        for k in sorted(values, key=str):
            yield from labelled_leaves(values[k], prefix + (str(k),), labels)
    elif isinstance(values, list):
        for i, v in enumerate(values):
            inner = labels
            if isinstance(v, Mapping):
                inner += tuple(v[k] for k in LABEL_KEYS if isinstance(v.get(k), str)
                               and v[k].strip())[:1]
            yield from labelled_leaves(v, prefix + (str(i),), inner)


def _citable_label(label: str) -> bool:
    return len(label) >= 2 and any(ch.isalpha() for ch in label) \
        and label.lower() not in COMMON_LABELS


def _label_pattern(label: str) -> re.Pattern:
    """A label as a whole word; an underscore may also be written as a space."""
    body = r'[_\s]'.join(re.escape(part) for part in label.split('_'))
    return re.compile(rf'(?<![\w]){body}(?![\w])')


# v0.3 (WP-A): literals that are settings or structure, never a metric's value.
STRUCTURAL_LITERALS = frozenset({'setting', 'data_card', 'final_test'})
# v0.3 (WP-A): a result id written in a text, or its prefix (6 or more hexadecimal
# characters, as ``status`` and the recap abbreviate it).
RESULT_ID_TOKEN = re.compile(r'(?<![\w])[0-9a-fA-F]{6,64}(?![\w])')


def resolve_result(slots: Mapping[str, str], ref: str) -> frozenset:
    """The result ids ``ref`` names among ``slots`` (``{slot: result_id}``): a slot name,
    a result id, or a prefix of 6 or more characters of one."""
    ref = str(ref).strip()
    if ref in slots:
        return frozenset({slots[ref]})
    if len(ref) >= 6:
        return frozenset(rid for rid in slots.values() if rid.startswith(ref.lower()))
    return frozenset()


def _fraction_forms(v: float) -> tuple:
    """A recorded number and, for a fraction, its complement and both as whole percents
    (the forms ``decide propose`` accepted for a proposal's own value before v0.3)."""
    if 0 < v < 1:
        return (v, round(1 - v, 9), round(100 * v, 6), round(100 * (1 - v), 6))
    return (v,)


# The literals written in the study language (review round 4, E4-6).
STUDY_LANGUAGE_LITERALS = ('user_words', 'user_text', 'criterion_option')


class Pool:
    """Numbers a text may cite: current results, then literals, then stale results.

    Literals are recorded values a text may repeat: decision and proposal values, the
    rules evaluated by the current policy evaluation, the junior's recorded words, settings,
    case statements, ``user_texts`` (text the junior wrote, passed with
    ``--allow-user-text``), the sealed final test's counts, and (WP-A8) the figures of the
    data card (``data_card``, the ``hypotrail data`` payload).

    v0.3 (WP-A): ``proposed`` is the value ``decide propose`` records (a literal of its own
    texts, never of a conclusion's); ``scope`` names results (ids, id prefixes, or slots)
    every sentence binds to unless it names others (``check --result``).
    """

    def __init__(self, view: Mapping, user_texts: Iterable[str] = (),
                 result_ids: Iterable[str] | None = None, retired: Iterable[Mapping] = (),
                 data_card: Mapping | None = None, *, proposed: Any = None,
                 scope: Iterable[str] | None = None):
        self.current, self.stale, self.literal = [], [], []
        # Review round 4 (E4-6): the study language reads the numbers of its texts (a French
        # text writes "1,286" for 1.286, never for 1,286).
        self.language = 'fr' if view.get('language') == 'fr' else 'en'
        # Withdrawn and superseded proposals (F3): never literals; only named in the
        # finding when an untraceable number repeats one of their figures.
        self.retired = []
        for p in retired:
            for v in _walk_numbers(_rule_spaced(p.get('value'))):
                self.retired.append({'proposal_id': p.get('proposal_id'),
                                     'status': p.get('status'), 'value': v})
        # Result ids a digit-only prefix may abbreviate (R3): the registry when known,
        # else the results of the view.
        self.result_ids = tuple(result_ids) if result_ids is not None else tuple(
            item['result_id'] for item in view['results'].values()
            if isinstance(item.get('result_id'), str))
        # Target units of the results (a regression study, M3): "about six litres" is read.
        self.units = wordnum.unit_nouns(sorted({
            item['values']['unit'] for item in view['results'].values()
            if isinstance(item.get('values'), Mapping)
            and isinstance(item['values'].get('unit'), str)}))
        self.points_unit = any(u in ('point', 'points') for u in self.units)
        # v0.3 (WP-A): what a sentence may name to bind its numbers (scope-bound
        # matching): the slots and result ids of the view, and the group labels.
        self.slots: dict[str, str] = {}
        self.labels: dict[str, re.Pattern] = {}
        # v0.3 (WP-J): thresholds the engine states, and the counts of each group.
        self.thresholds: list[dict] = []
        self.group_counts: dict[tuple[str, str], list[dict]] = {}
        for slot, item in sorted(view['results'].items()):
            if item['values'] is None:
                continue
            if isinstance(item.get('result_id'), str):
                self.slots[slot] = item['result_id']
            bucket = self.current if item['current'] and item['integrity'] == 'ok' else self.stale
            leaves = list(labelled_leaves(item['values']))
            if cite.is_number(item['n_rows']):
                leaves.append((('@n_rows',), item['n_rows'], ()))
            metric = item['values'].get('metric') if isinstance(item['values'], Mapping) \
                else None
            # v0.3 (WP-H): the variant comparison an evaluation stores (``model_selection``,
            # ADR 0007) states its metric as a field, so its figures answer to that metric's
            # words ("-0.009 of AUC per fold") as the agent is asked to relay them.
            selection = item['values'].get('model_selection') \
                if isinstance(item['values'], Mapping) else None
            selection_metric = selection.get('metric') if isinstance(selection, Mapping) \
                else None
            current = bucket is self.current
            if current:
                for text in _rule_texts(item['values']):
                    for v in _walk_numbers(text):
                        self.thresholds.append({'source': 'threshold', 'id': slot, 'value': v})
            for segments, value, labels in leaves:
                path = cite.format_path(segments)
                if current and segments and segments[-1] in THRESHOLD_SEGMENTS:
                    self.thresholds.append({'source': 'threshold', 'id': f'{slot}:{path}',
                                            'value': value})
                if internal_path(slot, path):
                    continue
                entry = {'result_id': item['result_id'], 'slot': slot, 'path': path,
                         'value': value}
                labels = tuple(x for x in labels if _citable_label(x))
                if labels:
                    entry['labels'] = labels
                    for label in labels:
                        self.labels.setdefault(label, _label_pattern(label))
                if isinstance(metric, str):
                    entry['metric'] = metric
                elif isinstance(selection_metric, str) and segments \
                        and segments[0] == 'model_selection':
                    entry['metric'] = selection_metric
                bucket.append(entry)
                if current and labels and len(segments) > 1 \
                        and segments[-1] in GROUP_COUNT_SEGMENTS:
                    # v0.3 (WP-J): the counts of one group, for "333 of 459".
                    key = (item['result_id'], cite.format_path(segments[:-1]))
                    self.group_counts.setdefault(key, []).append(entry)
        self.scope, self.unknown_scope = None, []
        if scope is not None:
            found = set()
            for ref in scope:
                rids = resolve_result(self.slots, ref)
                if rids:
                    found |= rids
                else:
                    self.unknown_scope.append(ref)
            self.scope = frozenset(found)
        # WP-B6b: the success criterion as ``status`` shows it (``view.criterion``): the
        # gain and its interval on the development evidence (in points for a scoring study,
        # a share of the baseline's MAE for a regression), and on the final test once
        # opened. The path names the metric ("precision_gain", "mae_reduction") so that a
        # number bound to "precision" or "MAE" may match it.
        self.current.extend(criterion_items(view.get('criterion')))
        # WP-B6b: the bounds a group label prints ("81 to 82 year (19xx)", "(2166.8,
        # 2584.4]") are literals of a current result: a text that names the group repeats
        # them.
        for slot, item in sorted(view['results'].items()):
            if item['values'] is not None and item['current'] and item['integrity'] == 'ok':
                for label in group_labels(item['values']):
                    self._literal('group_label', f'{slot}:{label}', label)
        for d in view['decisions'].values():
            if d['value'] is not None and d['decision_id'] != 'conclusion':
                self._literal('decision', d['decision_id'], d['value'], forms=True)
        for p in view['open_proposals']:
            if p['decision_id'] != 'conclusion':
                self._literal('proposal', p['proposal_id'], p['value'], forms=True)
        # v0.3 (WP-C, R19): the engine's illustrative translation of the criterion options
        # (per 1,000 actions, from the development rows) may be repeated as it is given.
        options = (view.get('next_action') or {}).get('criterion_options') or {}
        for cand in options.get('candidates') or []:
            if isinstance(cand.get('per_1000'), Mapping):
                self._literal('criterion_option', 'per_1000', cand['per_1000'])
            # v0.3 (WP-H): a regression option has no per-1,000 translation; its minimum
            # ("5% less error") and the factor its text states ("at most 0.95 E <unit>") are
            # the engine's own words, refused before (WP-H acceptance, round 1).
            self._literal('criterion_option', 'value', cand.get('value'))
            if isinstance(cand.get('text'), str):
                self._literal('criterion_option', 'text', cand['text'])
        if options.get('scale'):
            self._literal('criterion_option', 'scale', options['scale'])
        if proposed is not None:
            # ``decide propose`` (v0.3, WP-A): the value being proposed may be repeated by
            # its own restatement, rationale and labels, as an open proposal's value may.
            self._literal('proposed_value', 'value', proposed, forms=True)
        for d in view['decisions'].values():
            conf = d.get('confirmation')
            if isinstance(conf, Mapping) and isinstance(conf.get('user_words'), str):
                self._literal('user_words', d['decision_id'], conf['user_words'])
        # P2: the junior's recorded conditions and the words that resolved them.
        for n in view.get('notes') or []:
            self._literal('user_words', n['note_id'], n['user_words'])
            if isinstance(n.get('resolution'), Mapping):
                self._literal('user_words', n['note_id'], n['resolution'].get('user_words'))
        for slot, item in sorted(view['results'].items()):
            if item.get('activity') == 'policy.evaluation' and item['current'] \
                    and isinstance(item.get('params'), Mapping):
                for rule in item['params'].get('rules') or []:
                    self._literal('rule', slot, rule)
        for i, text in enumerate(user_texts):
            self._literal('user_text', f'user_text:{i + 1}', text)
        # D8: counts of the study's own structure, matched only before a structural noun.
        self.structure: list[dict] = []

        def count(kind: str, source: str, value) -> None:
            if isinstance(value, int) and not isinstance(value, bool):
                self.structure.append({'kind': kind, 'id': source, 'value': value})
        for slot, item in sorted(view['results'].items()):
            values = item.get('values')
            if not (item['current'] and item['integrity'] == 'ok' and isinstance(values, Mapping)):
                continue
            if isinstance(values.get('features'), list):
                count('features', f'{slot}.features', len(values['features']))
            if isinstance(values.get('groups'), list):
                count('groups', f'{slot}.groups', len(values['groups']))
        availability = [('decision', view['decisions'].get('feature_availability', {})
                         .get('value'))]
        availability += [(p['proposal_id'], p['value']) for p in view['open_proposals']
                         if p['decision_id'] == 'feature_availability']
        for source, value in availability:
            if not isinstance(value, Mapping):
                continue
            count('features', f'feature_availability.{source}.all', len(value))
            count('features', f'feature_availability.{source}.usable',
                  sum(v in USABLE_STATUSES for v in value.values()))
            count('features', f'feature_availability.{source}.excluded',
                  sum(v in EXCLUDED_STATUSES for v in value.values()))
            for status in sorted(set(value.values())):
                count('features', f'feature_availability.{source}.{status}',
                      sum(v == status for v in value.values()))
        plan = view.get('plan') or []
        count('steps', 'plan.steps', len(plan))
        count('pauses', 'plan.pauses', len({s['pause'] for s in plan if s.get('pause')}))
        count('decisions', 'decisions', len(view['decisions']))
        self._literal('setting', 'settings', view['settings'])
        self._literal('case', 'dataset.rows', view['dataset'].get('rows'))
        # WP-A8: the sealed final test's counts (state, ADR 0006) and the data card's figures
        # (step 0 shows them before any result exists): row and column counts, missing,
        # distinct and special-value counts, and the example cells it prints.
        final = view.get('final_test') or {}
        for key in ('rows', 'development_rows'):
            self._literal('final_test', f'final_test.{key}', final.get(key))
        # B6c (H2): the choices changed after the opening; a final-test figure then no
        # longer describes the configuration the study holds.
        self.changed_after = sorted(set(final.get('changed_after') or []) & set(CHOICE_CHANGES))
        for source, value in data_card_figures(data_card):
            self._literal('data_card', source, value)
        for items in view['facts']['by_status'].values():
            for f in items:
                self._literal('case', f['id'], f['value'])
        # Review round 3 (E3-2): the state values the engine's own delayed-label limit cites
        # (``state.delayed_labels_limit``: the partition's final boundary on its clock and the
        # number of development rows left out). Each is traced only in the context the limit
        # writes it ("prediction_tick 241", "2 development rows"), never as a bare literal, so
        # an untraceable number elsewhere stays untraceable.
        self.partition_facts: list[dict] = []
        for item in view.get('not_yet_defensible') or []:
            if not isinstance(item, Mapping) or item.get('id') != 'delayed_labels_excluded':
                continue
            clock, start = item.get('clock'), item.get('final_start')
            if isinstance(clock, str) and clock and cite.is_number(start):
                self.partition_facts.append({
                    'id': 'partition.order.final_start', 'value': float(start),
                    # Review round 4: one space between the clock and the value, as the
                    # limit writes it (a masked date in between is not the limit's context).
                    'before': re.compile(rf'(?<![\w.]){re.escape(clock)}\s?$'), 'after': None})
            if isinstance(item.get('n_rows'), int) and not isinstance(item['n_rows'], bool):
                self.partition_facts.append({
                    'id': 'partition.training_exclusions.n_rows', 'value': float(item['n_rows']),
                    'before': None, 'after': DEVELOPMENT_ROWS_AFTER})

    def _literal(self, kind: str, source: str, value: Any, *, forms: bool = False) -> None:
        """Record the numbers of ``value``. ``forms`` (a decision or proposal value): a
        fraction may also be written as its complement, or as a whole number of percent
        ("70/30" for a validation fraction of 0.3), never another number of the value as a
        percentage ("capacity:100" does not allow "100%")."""
        # Review round 4 (E4-6): the junior's words and texts, and the engine's texts in the
        # study language, are read in that language; recorded values and the case's own
        # statements as written.
        language = self.language if kind in STUDY_LANGUAGE_LITERALS else None
        for v in _walk_numbers(_rule_spaced(value), language):
            for form in (_fraction_forms(v) if forms else (v,)):
                self.literal.append({'source': kind, 'id': source, 'value': form})

    def sentence_scope(self, sentence: str) -> tuple[frozenset | None, frozenset]:
        """v0.3 (WP-A): ``(results, labels)`` a sentence names: the result ids of the slots
        it names (a slot with a dot, ``diag.binary``) or of the result ids it writes (a
        prefix of 6 or more hexadecimal characters); else the check's scope (``check
        --result``), else None. ``labels``: the group labels it names."""
        named = set()
        for slot, rid in self.slots.items():
            if '.' in slot and re.search(rf'(?<![\w.]){re.escape(slot)}(?![\w])', sentence):
                named.add(rid)
        for m in RESULT_ID_TOKEN.finditer(sentence):
            token = m.group(0).lower()
            named.update(rid for rid in self.slots.values() if rid.startswith(token))
        results = frozenset(named) if named else self.scope
        labels = frozenset(label for label, pattern in self.labels.items()
                           if pattern.search(sentence))
        return results, labels

    def trace_words(self, word: wordnum.WordNumber) -> tuple[str, dict | None]:
        """Where a number written in words comes from (F3), like :meth:`trace`: a ratio
        or a fraction matches at its own precision (:meth:`wordnum.WordNumber.matches`),
        percentage points only a registered difference."""
        points = word.kind == 'points'
        for bucket, label in ((self.current, 'current'), (self.literal, 'literal'),
                              (self.stale, 'stale')):
            if points and label == 'literal':
                continue
            for item in bucket:
                if points and not _is_difference(item['path']):
                    continue
                if word.matches(item['value'], literal=label == 'literal'):
                    return label, item
        return 'none', None

    def structure_match(self, text: str, end: int, value: float) -> dict | None:
        """The structure count (D8) a number ending at ``end`` refers to, when a structural
        noun follows it and the count matches; None otherwise."""
        m = STRUCTURE_AFTER.match(text, end)
        if m is None or value != int(value):
            return None
        noun = m.group('noun').lower()
        kind = next(k for k, nouns in STRUCTURE_NOUNS.items() if noun in nouns)
        return next((item for item in self.structure
                     if item['kind'] == kind and item['value'] == int(value)), None)

    def partition_match(self, text: str, tok: cite.Token) -> dict | None:
        """Review round 3 (E3-2): the partition fact (:attr:`partition_facts`) a number
        repeats in the context the engine's delayed-label limit writes it; None otherwise."""
        if tok.percent:
            return None
        for fact in getattr(self, 'partition_facts', ()):
            if abs(fact['value'] - tok.value) > 1e-9:
                continue
            if fact['before'] is not None \
                    and not fact['before'].search(text[max(0, tok.start - 80):tok.start]):
                continue
            if fact['after'] is not None and not fact['after'].match(text, tok.end):
                continue
            return fact
        return None

    def threshold_match(self, tok: cite.Token) -> dict | None:
        """v0.3 (WP-J): the stated engine threshold a number after a threshold word repeats."""
        if tok.percent:
            return None
        return next((t for t in self.thresholds if abs(t['value'] - tok.value) < 1e-9), None)

    def pair_match(self, a: cite.Token, b: cite.Token) -> tuple[dict, dict] | None:
        """v0.3 (WP-J): two counts of one group of a current result ("333 of 459"), the
        first smaller than the second; None when no group holds both."""
        if a.percent or b.percent or a.decimals or b.decimals or not a.value < b.value:
            return None
        for key in sorted(self.group_counts):
            items = self.group_counts[key]
            first = next((i for i in items if abs(i['value'] - a.value) < 1e-9), None)
            second = next((i for i in items if abs(i['value'] - b.value) < 1e-9), None)
            if first is not None and second is not None:
                return first, second
        return None

    def retired_match(self, value: float, *, percent: bool = False) -> dict | None:
        """The withdrawn or superseded proposal whose figure ``value`` repeats, if any."""
        for item in self.retired:
            v = 100 * item['value'] if percent else item['value']
            if abs(v - value) < 1e-9:
                return item
        return None

    def trace(self, tok: cite.Token, *, difference: bool = False,
              bind: 'Binding | None' = None) -> tuple[str, dict | None]:
        """Where ``tok`` comes from. ``difference``: the token is written in percentage
        points, so only a registered difference (``deltas``) can match it. ``bind`` (WP-A9,
        H2): the path segments the words near the number name (:func:`binding`); a result
        whose path holds none of them is not a match.

        v0.3 (WP-A): a figure in points that is no registered difference times 100 may
        still be a value the engine registers in points (:func:`_points_valued`), or a
        recorded literal ("at least 5 points"), as written."""
        label, item = 'none', None
        if bind is not None and bind.labels:
            # A sentence that names a group speaks of that group first.
            label, item = self._trace(tok, difference=difference, bind=bind, grouped=True)
        if label == 'none':
            label, item = self._trace(tok, difference=difference, bind=bind)
        if label == 'none' and difference:
            plain = dataclasses.replace(tok, percent=False)
            label, item = self._trace(plain, bind=bind, points=True)
        return label, item

    def _trace(self, tok: cite.Token, *, difference: bool = False,
               bind: 'Binding | None' = None, points: bool = False,
               grouped: bool = False) -> tuple[str, dict | None]:
        buckets = ((self.current, 'current'), (self.literal, 'literal'), (self.stale, 'stale'))
        if grouped:
            buckets = tuple((tuple(i for i in bucket if (i.get('labels') or ('',))[-1]
                                   in bind.labels), label)
                            for bucket, label in buckets if label == 'current')
        for bucket, label in buckets:
            if difference and label == 'literal':
                continue
            if label == 'literal' and bind is not None and bind.scope == 'final' \
                    and bind.rule:
                continue
            for item in bucket:
                if difference and not _is_difference(item['path']):
                    continue
                if points and label != 'literal' and not _points_valued(item['path']):
                    continue
                if label != 'literal' and not _bound(item, bind):
                    continue
                if label == 'literal' and bind is not None \
                        and bind.segments not in (None, ('#count',), LEVEL_BINDING) \
                        and (item['source'] == 'setting'
                             or (tok.percent and item['source'] in STRUCTURAL_LITERALS)):
                    # v0.3 (WP-A): a figure said of a metric ("95% precision") is no
                    # setting (the bootstrap level), and a percentage of a metric is no
                    # data-card cell or final-test count ("100% precision").
                    continue
                if cite.shown_matches(tok, item['value']) or (
                        not tok.percent and label == 'literal'
                        and abs(item['value'] - tok.value) < 1e-9):
                    return label, item
        return 'none', None


def data_card_figures(card: Mapping | None) -> list[tuple[str, Any]]:
    """``(source, value)`` of every figure the data card shows (WP-A8): what ``check`` lets
    a text repeat after step 0. Example cells are quoted data, never statistics."""
    if not isinstance(card, Mapping):
        return []
    dev = card.get('development') or {}
    out = [('data.development.rows', dev.get('rows')),
           ('data.development.columns', dev.get('columns'))]
    for group in card.get('groups') or []:
        for v in group.get('variables') or []:
            name = v.get('name')
            out += [(f'data.{name}.n_missing', v.get('n_missing')),
                    (f'data.{name}.n_distinct', v.get('n_distinct')),
                    (f'data.{name}.examples', v.get('examples'))]
            out += [(f'data.{name}.special_values', s.get('n_rows'))
                    for s in v.get('special_values') or []]
    for item in (card.get('rows') or {}).get('items') or []:
        out.append((f'data.rows.{item.get("row_key")}', item.get('values')))
    return [(source, value) for source, value in out if value is not None]


def _rule_spaced(value: Any) -> Any:
    """A rule identifier with its colon spaced ("capacity 100"), so its figure is read."""
    if isinstance(value, str) and ':' in value:     # "capacity:100", "threshold:0.3"
        return value.replace(':', ' ')
    return value


def _retired_note(pool: 'Pool', value: float, percent: bool = False) -> tuple[str, dict]:
    item = pool.retired_match(value, percent=percent)
    if item is None:
        return '', {}
    return (f' It repeats a figure of the {item["status"]} proposal {item["proposal_id"]}, '
            'which is no longer on the table: name that proposal without its figure.',
            {'retired_proposal': item['proposal_id'], 'proposal_status': item['status']})


def _masked(text: str) -> str:
    """``text`` with exempt numbers (dates, list markers, revision comparisons) blanked,
    same length."""
    text = ISO_DATE.sub(lambda m: ' ' * len(m.group(0)), text)
    text = LIST_MARKER.sub(lambda m: re.sub(r'\d', ' ', m.group(0)), text)
    text = REVISION_SPAN.sub(lambda m: re.sub(r'\d', ' ', m.group(0)), text)
    return text


# Review fix L4 (``decide propose``), shared with ``check`` since v0.3 (WP-A): digits glued
# after a word ("the top250 clients") are a number; an identifier is not (``p_5``,
# ``r_1a2b``, a digest, ``x2``: a single letter names a variable).
GLUED_NUMBER = re.compile(r'(?<=[^\W\d_]{2})(\d+(?:[.,]\d+)?)(?![\w])(\s?%)?')
HEX_IDENTIFIER = re.compile(r'\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{8,}\b', re.I)


# Review round 4: a number with a magnitude suffix or an exponent ("241k", "1.5M", "2bn",
# "241e3") is the number it scales to, at the precision it shows ("241k" is 241,000 to the
# nearest thousand: ``decimals`` is negative), so it is traced like any other number, and
# reported when it matches nothing; it was neither before.
#
# Round 5 (review E, R5E-5): a scale word or symbol after a number changes its value too,
# glued, after a space or after a hyphen, in English and French, singular and plural ("241
# k", "241-thousand", "1.5 millions", "1,5 milliard", "241 mille", "1.5 bn"); "1.5x10^6"
# and "1.5×10⁶" are the exponent forms; "1.5‰" is a per mille (0.15 %); "1.5x" is a
# multiple (1.5). A single-letter symbol after a space is not read before a hyphen and a
# letter ("5 k-fold").
#
# Round 6 (review E, R6E-4): "trillion(s)" is 10^12; in French (the long scale) "billion" is
# 10^12, "billiard" 10^15 and "trillion" 10^18 (:data:`FRENCH_SCALE_WORDS`, read when the
# text is French). A percentage or a per mille written in words after digits ("12 percent",
# "12 per cent", "12 pour cent", "1.5 per mille", "12 pour mille") is read as one
# (:data:`PERCENT_WORDS`, :data:`PER_MILLE_WORDS`), as "twelve percent" is
# (:mod:`mlkit.study.wordnum`): never as the bare number, which a count could match.
_SCALE_SEPARATOR = '[ \u00a0\u202f\u2009-]'
SCALE_WORDS = {'thousand': 3, 'thousands': 3, 'mille': 3, 'millier': 3, 'milliers': 3,
               'million': 6, 'millions': 6, 'mio': 6, 'billion': 9, 'billions': 9,
               'milliard': 9, 'milliards': 9, 'bn': 9, 'md': 9, 'mds': 9, 'mrd': 9,
               'trillion': 12, 'trillions': 12}
FRENCH_SCALE_WORDS = {**SCALE_WORDS, 'billion': 12, 'billions': 12, 'billiard': 15,
                      'billiards': 15, 'trillion': 18, 'trillions': 18}
MAGNITUDE = {'k': 3, 'K': 3, 'M': 6, 'x': 0, '\u00d7': 0}
_WORD_ALTERNATION = '|'.join(sorted(FRENCH_SCALE_WORDS, key=len, reverse=True))
_BODY = r'([1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)'
SUPERSCRIPT = str.maketrans('\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079'
                            '\u207b\u207a', '0123456789-+')
_SUPERSCRIPTS = '\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079'
SCALED_NUMBER = re.compile(
    r'(?<![\w.,])([-\u2212](?=\d))?' + _BODY +
    r'(?:[eE]([-+]?\d{1,3})'
    r'|\s?[x\u00d7*\u00b7]\s?10(?:\^\(?([-+\u2212]?\d{1,3})\)?'
    rf'|([\u207b\u207a]?[{_SUPERSCRIPTS}]{{1,3}}))'
    rf'|{_SCALE_SEPARATOR}?(?i:({_WORD_ALTERNATION}))'
    r'|(k|K|M|x|\u00d7)'
    rf'|{_SCALE_SEPARATOR}(k|K|M)(?!-[^\W\d_]))'
    r'(?![\w])(\s?%)?')
PER_MILLE = re.compile(r'(?<![\w.,])([-\u2212](?=\d))?' + _BODY + r'\s?\u2030')
_WORD_GAP = '[ \u00a0\u202f\u2009-]+'
PERCENT_WORDS = re.compile(r'(?<![\w.,])([-\u2212](?=\d))?' + _BODY + _WORD_GAP
                           + r'(?i:(?:per|pour)' + _WORD_GAP + r'cent|percent|pourcent)(?![\w])')
PER_MILLE_WORDS = re.compile(r'(?<![\w.,])([-\u2212](?=\d))?' + _BODY + _WORD_GAP
                             + r'(?i:(?:per|pour)' + _WORD_GAP + r'(?:mille|mil)|permille)'
                             r'(?![\w])')


def _scaled_body(body: str, language: str | None) -> str:
    """The digits of a scaled number as a decimal string: in English a comma followed by
    groups of three digits groups thousands ("12,000 thousand"), otherwise a comma is the
    decimal separator (always in French)."""
    if language != 'fr' and re.fullmatch(r'[1-9]\d{0,2}(?:,\d{3})+(?:\.\d+)?', body):
        return body.replace(',', '')
    return body.replace(',', '.')


def scaled_numbers(text: str, language: str | None = None) -> list[cite.Token]:
    """The numbers of ``text`` written with a magnitude suffix, a scale word, an exponent or
    a per mille sign (:data:`SCALED_NUMBER`, :data:`PER_MILLE`), as tokens; a hexadecimal
    identifier is not one."""
    import decimal
    text = HEX_IDENTIFIER.sub(lambda m: ' ' * len(m.group(0)), text)
    out = []
    for m in SCALED_NUMBER.finditer(text):
        body = _scaled_body(m.group(2), language)
        if m.group(3) is not None:
            exponent = int(m.group(3))
        elif m.group(4) is not None:
            exponent = int(m.group(4).replace('\u2212', '-'))
        elif m.group(5) is not None:
            exponent = int(m.group(5).translate(SUPERSCRIPT))
        elif m.group(6) is not None:
            exponent = (FRENCH_SCALE_WORDS if language == 'fr'
                        else SCALE_WORDS).get(m.group(6).lower())
            if exponent is None:     # a French-only word ("billiard") in English text
                continue
        else:
            exponent = MAGNITUDE[m.group(7) or m.group(8)]
        decimals = (len(body.split('.')[1]) if '.' in body else 0) - exponent
        value = float(decimal.Decimal(body).scaleb(exponent))
        if m.group(1):
            value = -value
        out.append(cite.Token(m.group(0), value, decimals, bool(m.group(9)), m.start(),
                              m.end()))
    taken = [(t.start, t.end) for t in out]
    for pattern, shift in ((PER_MILLE, 1), (PER_MILLE_WORDS, 1), (PERCENT_WORDS, 0)):
        for m in pattern.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            # A per mille is a tenth of a percent: "1.5‰" is 0.15 %, at one more decimal.
            body = _scaled_body(m.group(2), language)
            decimals = (len(body.split('.')[1]) if '.' in body else 0) + shift
            value = float(decimal.Decimal(body).scaleb(-shift))
            out.append(cite.Token(m.group(0), -value if m.group(1) else value, decimals, True,
                                  m.start(), m.end()))
            taken.append(m.span())
    return sorted(out, key=lambda t: t.start)


# Round 5 (review E, R5E-5): numeric forms the engine cannot read as one number are
# reported as untraceable, never left unchecked: digit groups joined by underscores
# ("241_000"), a number with superscript digits ("10²"), a vulgar fraction ("½", "1½"), a
# hexadecimal literal ("0x1F"), and any other number glued to letters ("241kEUR", "241kk",
# "12ms"). An ordinal ("1st", "2nd", "1er", "2e", "3ème") is not a figure; a number glued to
# "pp" or "pts" is read as percentage points.
ODD_FORMS = (
    ('hexadecimal literal', re.compile(r'(?<![\w.,])0[xX][0-9a-fA-F]+(?![\w])')),
    ('digit groups joined by underscores', re.compile(r'(?<![\w.,])\d+(?:_\d+)+(?![\w])')),
    ('superscript digits',
     re.compile(rf'(?<![\w.,])\d+(?:[.,]\d+)?[{_SUPERSCRIPTS}\u207b\u207a]+')),
    ('vulgar fraction', re.compile(r'(?<![\w.,])\d*[\u00bc-\u00be\u2150-\u215f\u2189]')),
    ('number glued to letters', re.compile(r'(?<![\w.,])\d+(?:[.,]\d+)?[^\W\d_]\w*')),
)
ORDINAL_SUFFIX = re.compile(r'(?:st|nd|rd|th|er|re|ère|ere|e|ème|eme|nde?|de?)', re.I)
GLUED_POINTS = re.compile(r'(?<![\w.,])(\d+(?:[.,]\d+)?)(?=(?:pp|pts?)(?![\w]))')


def odd_numbers(text: str) -> list[tuple[str, int, int, str]]:
    """The numeric forms of ``text`` that are neither read as a number nor an identifier
    (:data:`ODD_FORMS`): ``[(text, start, end, form)]`` in text order, non-overlapping.
    Ordinals and numbers glued to "pp" / "pts" are not listed; a hexadecimal identifier is
    masked first."""
    text = HEX_IDENTIFIER.sub(lambda m: ' ' * len(m.group(0)), text)
    taken: list[tuple[int, int]] = []
    out = []
    for form, pattern in ODD_FORMS:
        for m in pattern.finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            if form == 'number glued to letters':
                letters = re.sub(r'^[\d.,]+', '', m.group(0))
                if ORDINAL_SUFFIX.fullmatch(letters) or re.fullmatch(r'(?:pp|pts?)', letters):
                    continue
            taken.append(m.span())
            out.append((m.group(0), m.start(), m.end(), form))
    return sorted(out, key=lambda x: x[1])


def glued_point_numbers(text: str) -> list[cite.Token]:
    """The numbers glued to "pp" or "pts" ("2.8pp"), as tokens of the number alone, so the
    percentage-point reading after them applies (:data:`PERCENTAGE_POINTS`)."""
    out = []
    for m in GLUED_POINTS.finditer(text):
        body = m.group(1).replace(',', '.')
        decimals = len(body.split('.')[1]) if '.' in body else 0
        out.append(cite.Token(m.group(1), float(body), decimals, False, m.start(), m.end()))
    return out


def glued_numbers(text: str) -> list[cite.Token]:
    """The numbers glued after a word (:data:`GLUED_NUMBER`), as tokens."""
    text = HEX_IDENTIFIER.sub(lambda m: ' ' * len(m.group(0)), text)
    out = []
    for m in GLUED_NUMBER.finditer(text):
        body = m.group(1).replace(',', '.')
        decimals = len(body.split('.')[1]) if '.' in body else 0
        out.append(cite.Token(m.group(0), float(body), decimals, bool(m.group(2)),
                              m.start(), m.end()))
    return out


def _exempt(text: str, tok: cite.Token) -> bool:
    return bool(EXEMPT_BEFORE.search(text[max(0, tok.start - 24):tok.start]))


def _result_id_prefix(pool: Pool, text: str, tok: cite.Token) -> bool:
    """True when ``tok`` is an all-digit result id prefix (R3): 6 or more digits, no sign,
    decimals or percent, after "result" / "rid" / "id" / "execution", or the start of a
    registry ``result_id``."""
    body = text[tok.start:tok.end]
    if tok.percent or not RESULT_ID_DIGITS.fullmatch(body):
        return False
    if RESULT_ID_LEAD.search(text[max(0, tok.start - 24):tok.start]):
        return True
    return any(rid.startswith(body) for rid in pool.result_ids)


def _trace_words(pool: Pool, masked: str, word: wordnum.WordNumber, where: str,
                 findings: list, traced: list, locate=None) -> None:
    """Trace one number written in words (F3) and record a finding or a trace."""
    at = locate(word.start) if locate else None
    label, item = pool.trace_words(word)
    shown = word.text.strip()
    structure = (pool.structure_match(masked, word.end, word.value)
                 if label in ('none', 'stale') and word.kind == 'count' else None)
    if structure is not None:
        traced.append({'text': shown, 'source': 'structure', 'id': structure['id'],
                       'value': structure['value'], 'in_words': True})
        return
    if label == 'current':
        traced.append({'text': shown, 'result_id': item['result_id'], 'slot': item['slot'],
                       'path': item['path'], 'value': item['value'], 'in_words': True})
    elif label == 'literal':
        traced.append({'text': shown, 'source': item['source'], 'id': item['id'],
                       'value': item['value'], 'in_words': True})
    elif label == 'stale':
        findings.append(finding('stale_number', where,
                                f'"{shown}" (a number written in words) matches only a stale '
                                'result; recompute before citing it.', number=shown,
                                in_words=True, result_id=item['result_id'], path=item['path'],
                                location=at))
    else:
        note, extra = _retired_note(pool, word.value)
        findings.append(finding('untraceable_number', where,
                                f'"{shown}" is a number written in words ({word.kind}) that '
                                'matches no current registry value. Cite the registered figure '
                                'with its result_id instead of computing or rounding it into '
                                'words.' + note, number=shown, in_words=True, kind=word.kind,
                                value=word.value, location=at, **extra))


def trace_text(pool: Pool, text: str, where: str, locate=None, *,
               language: str | None = None) -> tuple[list[dict], list[dict]]:
    """Trace every number of ``text``. ``locate`` (optional) maps an offset of ``text`` to
    the ``location`` of a finding (C10). ``language`` is the language the text is written in
    (review round 4, E4-6: in French a comma is always the decimal separator,
    :func:`mlkit.study.cite.parse_numbers`); by default the study language of the pool."""
    language = language or getattr(pool, 'language', None)
    findings, traced = [], []
    masked = _masked(text)
    scopes: dict[tuple[int, int], tuple] = {}
    identifiers = {m.start(1) for m in RULE_IDENTIFIER.finditer(masked)}
    scaled = scaled_numbers(masked, language)
    # Review round 4: "1.5M" is one number, not "1" followed by ".5M". Round 5 (R5E-5): a
    # form read as no number ("241kEUR") is reported once, and no part of it is read.
    odd = [o for o in odd_numbers(masked)
           if not any(t.start <= o[1] < t.end for t in scaled)]
    inside = [(t.start, t.end) for t in scaled] + [(o[1], o[2]) for o in odd]
    plain = [t for t in cite.parse_numbers(masked, language) + glued_numbers(masked)
             + glued_point_numbers(masked)
             if not any(a <= t.start < b for a, b in inside)]
    for shown, start, _end, form in odd:
        probe = cite.Token(shown, 0.0, 0, False, start, _end)
        if _exempt(masked, probe) or _result_id_prefix(pool, masked, probe) \
                or (re.fullmatch(r'[0-9a-f]+', shown) and RESULT_ID_LEAD.search(
                    masked[max(0, start - 24):start])):
            continue
        findings.append(finding('untraceable_number', where,
                                f'{shown} is a number written in a form the engine does not '
                                f'read ({form}), so it cannot be traced to a result. Write the '
                                'figure with plain digits as the registry shows it, a unit or '
                                'scale word after a space, and cite its result.',
                                number=shown, form=form,
                                location=locate(start) if locate else None))
    items = sorted([(t.start, 0, t) for t in plain + scaled]
                   + [(w.start, 1, w) for w in wordnum.parse(masked, pool.units)],
                   key=lambda x: x[:2])
    # v0.3 (WP-J): "333 of 459" (two counts of one group, its name in another language or
    # in an earlier sentence).
    paired: dict[int, dict] = {}
    digits = [t for _, w, t in items if not w]
    for a, b in zip(digits, digits[1:]):
        if a.end <= b.start and PAIR_SEPARATOR.fullmatch(masked[a.end:b.start] + ' '):
            found = pool.pair_match(a, b)
            if found:
                paired[a.start], paired[b.start] = found
    for _, in_words, tok in items:
        if _exempt(masked, tok):
            continue
        if in_words:
            _trace_words(pool, masked, tok, where, findings, traced, locate)
            continue
        # v0.3 (WP-A, R33): "2.8 points" (bare) is percentage points too.
        # A study whose target unit is "points" (a score) reads a bare "points" as that unit.
        difference = not tok.percent and bool(
            PERCENTAGE_POINTS.match(masked, tok.end)
            or (BARE_POINTS.match(masked, tok.end) and not pool.points_unit))
        if difference:
            tok = dataclasses.replace(tok, percent=True)
        bind = binding(masked, tok.start, tok.end, tok.percent)
        if tok.percent and not difference and not RANGE_AFTER.match(masked, tok.end) and (
                LEVEL_AFTER.match(masked, tok.end)
                or LEVEL_BEFORE.search(masked[max(0, tok.start - 40):tok.start])):
            # v0.3 (WP-J): "95% interval" names the interval's level. WP-H3: the first
            # bound of a range (« intervalle de 7,02 % à 7,55 % ») is a value, not a level.
            bind = dataclasses.replace(bind, segments=LEVEL_BINDING, rule=False)
        # v0.3 (WP-A): the results and groups the sentence names bind its numbers.
        bounds = _sentence_bounds(masked, tok.start, tok.end)
        if bounds not in scopes:
            scopes[bounds] = pool.sentence_scope(masked[bounds[0]:bounds[1]])
            if not scopes[bounds][1] and bounds[0] > 0:
                # v0.3 (WP-J): a sentence that names no group speaks of the group the
                # sentence before it named ("Students are 459. 333 of them are called.").
                before = _sentence_bounds(masked, max(0, bounds[0] - 2), max(0, bounds[0] - 2))
                inherited = pool.sentence_scope(masked[before[0]:before[1]])[1]
                scopes[bounds] = (scopes[bounds][0], inherited)
        results, labels = scopes[bounds]
        bind = dataclasses.replace(bind, results=results, labels=labels)
        label, item = pool.trace(tok, difference=difference, bind=bind)
        if label in ('none', 'stale') and tok.start in paired:
            label, item = 'current', paired[tok.start]
        if label in ('none', 'stale') and THRESHOLD_BEFORE.search(
                masked[max(0, tok.start - 24):tok.start]):
            threshold = pool.threshold_match(tok)
            if threshold is not None:
                label, item = 'literal', threshold
        if label in ('none', 'stale') and tok.start in identifiers:
            traced.append({'text': tok.text.strip(), 'source': 'identifier', 'id': 'rule',
                           'value': tok.value})
            continue
        structure = (pool.structure_match(masked, tok.end, tok.value)
                     if label in ('none', 'stale') and not tok.percent else None)
        if structure is not None:
            traced.append({'text': tok.text.strip(), 'source': 'structure',
                           'id': structure['id'], 'value': structure['value']})
            continue
        fact = (pool.partition_match(masked, tok)
                if label in ('none', 'stale') and not difference else None)
        if fact is not None:
            traced.append({'text': tok.text.strip(), 'source': 'partition', 'id': fact['id'],
                           'value': fact['value']})
            continue
        if label in ('none', 'stale') and _result_id_prefix(pool, masked, tok):
            traced.append({'text': tok.text.strip(), 'source': 'identifier', 'id': 'result_id',
                           'value': tok.value})
            continue
        if label == 'current' and final_item(item) \
                and getattr(pool, 'changed_after', None):
            findings.append(finding(
                'final_test_figure_outdated', where,
                f'{tok.text.strip()} is a figure of the final test, which measured the '
                f'configuration chosen before {", ".join(pool.changed_after)} changed after the '
                f'opening: it does not describe the configuration the study now holds. Say so, '
                f'or cite development evidence of the current choice.',
                number=tok.text.strip(), result_id=item['result_id'], path=item['path'],
                changed_after=list(pool.changed_after),
                location=locate(tok.start) if locate else None))
        elif label == 'current':
            traced.append({'text': tok.text.strip(), 'result_id': item['result_id'],
                           'slot': item['slot'], 'path': item['path'], 'value': item['value']})
        elif label == 'literal':
            traced.append({'text': tok.text.strip(), 'source': item['source'], 'id': item['id'],
                           'value': item['value']})
        elif label == 'stale':
            findings.append(finding('stale_number', where,
                                    f'{tok.text.strip()} matches only a stale result; recompute '
                                    'before citing it.', number=tok.text.strip(),
                                    result_id=item['result_id'], path=item['path'],
                                    location=locate(tok.start) if locate else None))
        else:
            note, extra = _retired_note(pool, tok.value, percent=tok.percent)
            findings.append(finding('untraceable_number', where,
                                    f'{tok.text.strip()} matches no current registry value at its '
                                    'displayed precision. Cite a result instead of computing.'
                                    + note, number=tok.text.strip(),
                                    location=locate(tok.start) if locate else None, **extra))
    return findings, traced


# --- one pool for check and propose (v0.3, WP-A) ------------------------------------------

# The findings that refuse a number of a proposal's text (``literal_number_in_text``).
NUMBER_CODES = ('untraceable_number', 'stale_number', 'final_test_figure_outdated')


def study_pool(study, *, view: Mapping | None = None, user_texts: Iterable[str] = (),
               proposed: Any = None, scope: Iterable[str] | None = None) -> Pool:
    """The :class:`Pool` of a study (a path or an open :class:`mlkit.study.read.Study`), as
    ``hypotrail check --text`` builds it: the view's results, criterion and literals, the
    registry's result ids, the retired proposals, and the data card. ``decide propose``
    builds the same pool with the value it proposes (``proposed``), so a text accepted by
    one is accepted by the other."""
    from . import cmd_check, read, view as view_model
    study = study if isinstance(study, read.Study) else read.open(study)
    view = view if view is not None else view_model.build(study)
    return Pool(view, user_texts, cmd_check.registry_ids(study),
                cmd_check.retired_proposals(study), cmd_check._data_card(study.study_dir),
                proposed=proposed, scope=scope)


def number_findings(pool: Pool, text: str, where: str, *,
                    language: str | None = None) -> list[dict]:
    """The findings of :func:`trace_text` that refuse a number (:data:`NUMBER_CODES`)."""
    findings, _ = trace_text(pool, text, where, language=language)
    return [f for f in findings if f['code'] in NUMBER_CODES]


