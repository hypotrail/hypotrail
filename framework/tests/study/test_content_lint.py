"""Lot 2026-10-28 (T-E2; LOT spec EN-2, EN-3 and the review conclusions §8.4 and §8.7): the
lint of the engine's content files.

* no digit outside a ``{placeholder}`` in the step cards' texts and in the other content files
  the engine package owns (``drafts``, ``digest``, ``steps``): every number comes from a
  registered value, cited;
* every text is an ``{en, fr}`` pair whose two sides hold the same placeholders;
* a "what we conclude" text never recommends: none of the verbs essayer, choisir, garder,
  retenir, and no option of a decision (the error measures, the variant families);
* « moyenne de référence » and « moyenne d'entraînement » appear in no French text of the
  content files nor of the engine's strings (EN-21: « référence (prédire la moyenne) »).
"""
from __future__ import annotations

import re
import string
from pathlib import Path

import pytest
import yaml

from mlkit.study import step_cards as sc

STUDY_PKG = Path(__file__).resolve().parents[2] / 'mlkit' / 'study'
CONTENT = STUDY_PKG / 'content'
ENGINE_CONTENT = ('step_cards', 'drafts', 'digest', 'steps')
PLACEHOLDER = re.compile(r'\{[^{}]*\}')
DIGIT = re.compile(r'[0-9]')
# A "conclude" text never recommends (LOT §8.7).
RECOMMENDING_VERBS_FR = re.compile(r"\b(essa[iy]\w*|choisi\w*|gard\w*|reten\w*|retien\w*)",
                                   re.IGNORECASE)
OPTION_NAMES = re.compile(r'\b(MAE|RMSE|EBM|ridge|Explainable Boosting)\b', re.IGNORECASE)
FORBIDDEN_FR = ('moyenne de référence', "moyenne d'entraînement")


def _load(name: str) -> dict:
    return yaml.safe_load((CONTENT / f'{name}.yaml').read_text(encoding='utf-8'))


def _strings(node, path=()):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, path + (str(k),))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _strings(v, path + (str(i),))


def _pairs(node, path=()):
    """Every ``{en, fr}`` pair of a content tree."""
    if isinstance(node, dict):
        if set(node) == {'en', 'fr'}:
            yield path, node
            return
        for k, v in node.items():
            yield from _pairs(v, path + (str(k),))


def _names(text: str) -> set[str]:
    return {f for _, f, _, _ in string.Formatter().parse(text) if f}


@pytest.mark.parametrize('name', ENGINE_CONTENT)
def test_no_digit_outside_a_placeholder(name):
    found = [('.'.join(path), text) for path, text in _strings(_load(name))
             if path and path[-1] not in ('schema', 'fmt')  # identifiers, not texts
             and DIGIT.search(PLACEHOLDER.sub('', text))]
    assert not found, found[:5]


def test_every_step_card_text_is_a_pair_with_the_same_placeholders():
    data = sc.content()
    for sid, texts in data['steps'].items():
        for key in ('caption', 'more', 'prepares', 'limit', 'next'):
            assert set(texts[key]) == {'en', 'fr'}, (sid, key)
    for qid, q in data['questions'].items():
        assert qid in sc.QUESTION_IDS, qid
        for key in ('text', 'how', 'trap'):
            assert set(q[key]) == {'en', 'fr'} and all(q[key].values()), (qid, key)
        for variant, parts in q['reading'].items():
            assert set(parts) == set(sc.READING_KEYS), (qid, variant)
    for path, pair in _pairs(data):
        assert pair['en'].strip() and pair['fr'].strip(), path
        assert _names(pair['en']) == _names(pair['fr']), path
    # Every question of the registry has its texts, every step of the registry its card.
    assert set(sc.QUESTION_IDS) == set(data['questions'])
    assert {q['step'] for q in sc.QUESTIONS} <= set(data['steps'])
    assert set(sc.PICTURES) <= set(data['steps'])


def test_what_we_conclude_never_recommends():
    data = sc.content()
    found = []
    for qid, q in data['questions'].items():
        for variant, parts in q['reading'].items():
            fr, en = parts['conclude']['fr'], parts['conclude']['en']
            if RECOMMENDING_VERBS_FR.search(fr) or OPTION_NAMES.search(fr) \
                    or OPTION_NAMES.search(en):
                found.append((qid, variant))
    for key, pair in data['business'].items():
        if RECOMMENDING_VERBS_FR.search(pair['fr']):
            found.append(('business', key))
    assert not found, found


def test_the_regression_reference_is_named_as_the_reference():
    """EN-21: no « moyenne de référence » nor « moyenne d'entraînement » in a French text of
    the content files or of the engine's strings (recorded words and test fixtures aside)."""
    found = []
    for path in sorted(CONTENT.glob('*.yaml')):
        for where, text in _strings(yaml.safe_load(path.read_text(encoding='utf-8'))):
            if any(f in text for f in FORBIDDEN_FR):
                found.append((path.name, '.'.join(where)))
    for path in sorted(STUDY_PKG.glob('*.py')):
        flat = ' '.join(path.read_text(encoding='utf-8').split())
        for f in FORBIDDEN_FR:
            if f in flat:
                found.append((path.name, f))
    assert not found, found
