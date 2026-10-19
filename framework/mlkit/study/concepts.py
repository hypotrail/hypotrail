"""Concept matching of the training confirmation mode (ADR 0005, v0.2b, WP-B2).

In the ``training`` mode a confirmation must restate the proposal **on its concepts**, not
on shared tokens. :func:`concept_map` builds, from a proposal's decision and value, a small
list of concepts the reply must say; each concept is said when the reply holds one of its
terms, in English or French (``content/concepts.yaml``), or the number it needs:

=========================  ================================================================
Decision                   Concepts
=========================  ================================================================
``prediction_time``        the timing of the value (``timing_before``, ``timing_after``,
                           ``timing_at``, each one the value uses) and ``event``: a word of
                           the value or of a label, or a translation of one (``synonyms``),
                           framing words ("predict", "score", "you") left out
``feature_availability``   each excluded variable by name (``variable:<name>``, the values
                           ``not_available`` and ``uncertain_excluded``) and ``exclude``;
                           ``keep_all`` when nothing is excluded
``split``                  ``validation``, then ``random`` and ``proportion`` (the share held
                           apart, as a fraction or a percentage of either partition), or for an
                           ordinal cutoff ``later_rows`` and ``proportion`` (the cutoff)
``success_criterion``      ``precision`` and ``min_gain`` (binary); ``error``, ``reduction``
                           and ``min_gain`` (regression: the share, as a fraction or percent)
``preprocessing``          one concept per parameter that differs from the default
                           (``missing_indicator``, ``rare_categories``, ``caps``,
                           ``log_transform``), or ``no_preprocessing``
``policy``                 ``capacity`` or ``threshold``, and ``rule_number``
``model_choice``           ``linear_model`` or ``baseline_model``
``conclusion``             the verdict: ``adopt``, ``keep_baseline``, or ``inconclusive``
any other decision         ``restatement``: the reply repeats a word or a number of the
                           value or a label (:func:`confirm.restates`)
=========================  ================================================================

The trade-offs (``confirm.REASON_DECISIONS``) also need a reason connector ("because",
"parce que", "car", "since", ...): in training a restatement is already content, so a
content word is no reason (:func:`has_reason_connector`).

Pure: no state, no I/O beyond the packaged content file.
"""
from __future__ import annotations

import functools
import re
from typing import Any, Iterable, Mapping

from . import state as st
from . import texts

STEM = 5
TIMING = ('timing_before', 'timing_after', 'timing_at')
DEFAULT_PREPROCESSING_PARTS = {'missing': 'none', 'rare_category_min_rows': 0, 'caps': {},
                               'log_transform': []}
EXCLUDED = ('not_available', 'uncertain_excluded')
# Verdicts and the concept that says each.
VERDICT_CONCEPTS = {'adopt_policy': 'adopt', 'adopt_model': 'adopt',
                    'keep_baseline': 'keep_baseline', 'inconclusive': 'inconclusive'}


def _cmd():
    from . import commands
    return commands


def _cf():
    from . import confirm
    return confirm


@functools.cache
def data() -> dict:
    """The parsed ``content/concepts.yaml``."""
    return texts.load('concepts')


def hint(concept: str) -> str:
    """The junior-facing description of a concept."""
    entry = data()['concepts'].get(concept.split(':', 1)[0]) or {}
    if concept.startswith('variable:'):
        return f'the variable {concept.split(":", 1)[1]}, which the proposal leaves out'
    return entry.get('hint') or concept


def fold_tokens(text: str) -> list[str]:
    """Folded word tokens of ``text`` (accents removed, apostrophes split)."""
    return re.findall(r'[^\W_]+', _cmd()._fold(text or ''))


def _word_match(term: str, token: str) -> bool:
    if term.endswith('*'):
        return token.startswith(term[:-1])
    if token == term:
        return True
    if token.endswith('s') and token[:-1] == term or term.endswith('s') and term[:-1] == token:
        return True
    return len(token) >= STEM and len(term) >= STEM and token[:STEM] == term[:STEM]


def term_said(term: str, tokens: list[str]) -> bool:
    """``term`` (one word, a ``stem*``, or several words) occurs in ``tokens``."""
    parts = re.findall(r"[^\W_]+\*?", _cmd()._fold(term))
    if not parts:
        return False
    n = len(parts)
    for i in range(len(tokens) - n + 1):
        if all(_word_match(p, tokens[i + j]) for j, p in enumerate(parts)):
            return True
    return False


def any_said(terms: Iterable[str], tokens: list[str]) -> bool:
    return any(term_said(t, tokens) for t in terms)


def concept_terms(concept: str) -> list[str]:
    return list((data()['concepts'].get(concept) or {}).get('terms') or [])


def reply_tokens(words: str) -> list[str]:
    """The reply's tokens with endorsement words and intensifiers left out ("je valide"
    never says "validation")."""
    cf = _cf()
    return [t for t in fold_tokens(words) if t not in cf.ENDORSEMENT_TOKENS]


def said_numbers(words: str) -> set[float]:
    """Numbers in ``words``: digits (decimal comma or point) and number words."""
    cmd = _cmd()
    found = {round(n, 6) for n in cmd._numbers(words)}
    found |= {float(cmd.NUMBER_WORDS[w]) for w in fold_tokens(words) if w in cmd.NUMBER_WORDS}
    return found


def _fraction_forms(f: float, *, complement: bool) -> set[float]:
    forms = {round(float(f), 6), round(100 * float(f), 6)}
    if complement and 0 < f < 1:
        forms.add(round(100 * (1 - float(f)), 6))
        forms.add(round(1 - float(f), 6))
    return forms


def _number_concept(concept: str, forms: set[float]) -> dict:
    return {'concept': concept, 'numbers': sorted(forms)}


def _terms_concept(concept: str, terms: Iterable[str] | None = None) -> dict:
    return {'concept': concept, 'terms': list(terms if terms is not None else concept_terms(concept))}


def _event_terms(value: str, labels: Iterable[str]) -> list[str]:
    """Words of a free-text moment and of the proposal's labels, and their translations;
    filler, timing and framing words left out."""
    cmd = _cmd()
    skip_terms = data().get('framing') or []
    timing_terms = [t for c in TIMING for t in concept_terms(c)]
    out: list[str] = []
    groups = [[w for t in g for w in fold_tokens(str(t))] for g in data().get('synonyms') or []]
    for text in (value, *labels):
        for tok in fold_tokens(text):
            if tok in cmd._FILLER or tok in cmd._ACK or tok.isdigit() or len(tok) < 3:
                continue
            if any(_word_match(t, tok) for t in skip_terms) \
                    or any(term_said(t, [tok]) for t in timing_terms):
                continue
            out.append(tok)
            for group in groups:
                if any(_word_match(g, tok) for g in group):
                    out.extend(group)
    return list(dict.fromkeys(out))


def concept_map(state: Mapping, proposal: Mapping) -> list[dict]:
    """The concepts a training confirmation of ``proposal`` must say, in order.

    Each item is ``{concept, terms}`` (said when one term occurs), ``{concept, numbers}``
    (said when the reply states one of the numbers), ``{concept, variable}`` (said when the
    reply names the variable), or ``{concept: 'restatement'}`` for a decision without a
    map (said when :func:`confirm.restates` holds)."""
    decision_id, value = proposal['decision_id'], proposal['value']
    labels = list((proposal.get('labels') or {}).values())
    task = st.task_of(state)
    items: list[dict] = []
    if decision_id == 'prediction_time' and isinstance(value, str):
        tokens = fold_tokens(value)
        # B6c (M5): one timing concept, the one that places the moment (before or after the
        # event, else at it); a reply says it with any timing word the value uses. "when the
        # session ends, before knowing if it purchased" needs "before" or "at the end", not
        # both.
        timings = [t for t in TIMING if any_said(concept_terms(t), tokens)]
        if timings:
            main = next((t for t in ('timing_before', 'timing_after') if t in timings),
                        timings[0])
            items.append(_terms_concept(main, [term for t in timings
                                               for term in concept_terms(t)]))
        event = _event_terms(value, labels)
        if event:
            items.append(_terms_concept('event', event))
        return items or [{'concept': 'restatement'}]
    if decision_id == 'feature_availability' and isinstance(value, Mapping):
        excluded = [name for name, status in value.items() if status in EXCLUDED]
        if not excluded:
            return [_terms_concept('keep_all')]
        items.append(_terms_concept('exclude', concept_terms('exclude')
                                    + list(_cf().EXCLUDE_WORDS)))
        items += [{'concept': f'variable:{name}', 'variable': name} for name in excluded]
        return items
    if decision_id == 'split' and isinstance(value, Mapping):
        if value.get('method') == 'ordinal_cutoff':
            return [_terms_concept('validation', concept_terms('validation')
                                   + concept_terms('later_rows')),
                    _number_concept('proportion', {round(float(value['cutoff']), 6)})]
        fraction = value.get('validation_fraction')
        items += [_terms_concept('validation'), _terms_concept('random')]
        if isinstance(fraction, (int, float)) and not isinstance(fraction, bool):
            items.append(_number_concept('proportion', _fraction_forms(fraction, complement=True)))
        return items
    if decision_id == st.SUCCESS_CRITERION and isinstance(value, Mapping):
        if task == st.REGRESSION:
            share = value.get('min_share')
            items += [_terms_concept('error'), _terms_concept('reduction')]
            if isinstance(share, (int, float)) and not isinstance(share, bool):
                items.append(_number_concept('min_gain', _fraction_forms(share, complement=False)))
            return items
        points = value.get('min_points')
        items.append(_terms_concept('precision'))
        if isinstance(points, (int, float)) and not isinstance(points, bool):
            items.append(_number_concept('min_gain', {round(float(points), 6)}))
        return items
    if decision_id == st.PREPROCESSING and isinstance(value, Mapping):
        missing = value.get('missing')
        if missing == 'indicator' or (isinstance(missing, Mapping)
                                      and 'indicator' in missing.values()):
            items.append(_terms_concept('missing_indicator'))
        if value.get('rare_category_min_rows'):
            items.append(_terms_concept('rare_categories'))
        if value.get('caps'):
            items.append(_terms_concept('caps'))
        if value.get('log_transform'):
            items.append(_terms_concept('log_transform'))
        return items or [_terms_concept('no_preprocessing')]
    if decision_id == 'policy' and isinstance(value, str):
        rule = _cmd().dep.parse_policy(value)
        if rule is not None:
            kind, number = rule
            items.append(_terms_concept(kind))
            forms = {round(float(number), 6)}
            if kind == 'threshold':
                forms = _fraction_forms(number, complement=False)
            items.append(_number_concept('rule_number', forms))
            return items
    if decision_id == 'model_choice' and isinstance(value, str):
        from . import preconditions
        concept = 'linear_model' if value == preconditions.REGRESSION_CANDIDATE \
            else 'baseline_model'
        return [_terms_concept(concept)]
    if decision_id == 'conclusion' and isinstance(value, Mapping):
        concept = VERDICT_CONCEPTS.get(value.get('verdict'))
        if concept:
            return [_terms_concept(concept)]
    return [{'concept': 'restatement'}]


def _variable_said(name: str, words: str) -> bool:
    cmd = _cmd()
    folded = cmd._fold(words)
    target = cmd._fold(str(name))
    tokens = re.findall(r"[^\W]+(?:[._][^\W]+)*", folded)
    if target in tokens:
        return True
    spaced = fold_tokens(re.sub(r'[._]', ' ', target))
    return bool(spaced) and term_said(' '.join(spaced), fold_tokens(folded))


def said(item: Mapping, words: str, tokens: list[str], proposal: Mapping) -> bool:
    """Whether the reply says the concept ``item`` of :func:`concept_map`."""
    if 'variable' in item:
        return _variable_said(item['variable'], words)
    if 'numbers' in item:
        return bool(said_numbers(words) & set(item['numbers']))
    if item['concept'] == 'restatement':
        texts_ = (proposal['restatement'], *(proposal.get('labels') or {}).values())
        return _cf().restates(words, value=proposal['value'], texts=texts_)
    if item['concept'] == 'adopt':   # "j'adopte" is the verdict itself, not only an endorsement
        return any_said(item['terms'], fold_tokens(words))
    return any_said(item['terms'], tokens)


def check(state: Mapping, proposal: Mapping, words: str) -> dict:
    """``{concepts, said, missing}`` of a training confirmation: the concept ids, the ids
    the reply says, and ``[{concept, hint}]`` of the ones it does not say."""
    items = concept_map(state, proposal)
    tokens = reply_tokens(words)
    found, missing = [], []
    for item in items:
        if said(item, words, tokens, proposal):
            found.append(item['concept'])
        else:
            missing.append({'concept': item['concept'], 'hint': hint(item['concept'])})
    return {'concepts': [i['concept'] for i in items], 'said': found, 'missing': missing}


def has_reason_connector(words: str) -> bool:
    """A reason connector ("because", "since", "given", "parce que", "car", "puisque", "vu
    que", ...): in training a reason is a clause that says why (:data:`confirm.REASON_CONNECTOR`)."""
    cf = _cf()
    return bool(cf.REASON_CONNECTOR.search(_cmd()._fold(words)))


def mode_named(mode: str, words: str) -> bool:
    """The words name ``mode`` (``content/concepts.yaml``, ``modes``)."""
    terms = (data().get('modes') or {}).get(mode) or [mode]
    return any_said(terms, fold_tokens(words))
