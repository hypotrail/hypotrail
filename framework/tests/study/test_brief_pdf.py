"""R68, minimal version (owner decision of 2026-10-28): start a study from the product owner's
PDF. Real ``hypotrail`` processes on a temporary Auto MPG study: ``brief import`` extracts the
sample PO page, ``brief set`` records a draft citing its pages with the junior's words, and
the study's brief then replaces the use case's one in the digest and the report. A page the
PDF does not have, a field that cites nothing, and a stale revision are refused."""
from __future__ import annotations

import json

import pytest
import yaml

from mlkit.study import case_brief as cb
from mlkit.study import cmd_brief

from flowkit import REPO, hyp

pytest.importorskip('pypdf')

AUTO = REPO / 'use-cases' / 'auto-mpg'
PDF = AUTO / 'po' / 'fiche-cas-usage-mpg.pdf'
PROBLEM = ("L'équipe Conception annonce la consommation dès la validation de la fiche "
           "technique ; aujourd'hui l'écart moyen est d'environ {current_method_error}.")


def _draft(**changes) -> dict:
    draft = {
        'schema': cb.SCHEMA,
        'source': {'fictitious': True, 'text': 'Fiche du PO (PDF), scénario fictif'},
        'problem': PROBLEM,
        'decision': 'Quels prototypes envoyer d\'abord aux essais.',
        'objective': 'Viser un écart moyen d\'environ {target_error}, avec une fourchette.',
        'production': 'Un service appelé par l\'outil de conception.',
        'data_provenance': {'real': 'UCI Auto MPG.', 'scenario': 'Historique provisoire.'},
        'users_and_cost_of_error': {'users': 'Les ingénieurs.', 'cost': 'Trop bas : correction.'},
        'out_of_scope_and_risks': {'out_of_scope': 'L\'homologation.', 'risks': 'La dérive.'},
        'links': {'prediction_moment': 'Étape 2.', 'error_measure': 'Étape 5.',
                  'conclusion': 'La conclusion.'},
        'current_method_error': {'value': 4.5, 'unit': 'mpg', 'measure': 'mae'},
        'target_error': {'value': 3.5, 'unit': 'mpg', 'measure': 'mae'},
        'citations': {'problem': [1], 'decision': [1], 'objective': [2], 'production': [2],
                      'data_provenance': [2], 'users_and_cost_of_error': [1, 2],
                      'out_of_scope_and_risks': [3], 'current_method_error': [1],
                      'target_error': [2]},
        'open_questions': [{'about': 'objective',
                            'text': 'Quelle largeur de fourchette le PO attend-il ?'}]}
    draft.update(changes)
    return draft


def _write(path, document) -> str:
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding='utf-8')
    return str(path)


def test_a_study_starts_from_the_po_pdf(tmp_path):
    study = tmp_path / 'study'
    code, out = hyp('init', '--case', AUTO, '--study', study, '--lang', 'fr', cwd=tmp_path)
    assert code == 0, out
    rev = out['revision']
    code, out = hyp('status', '--study', study, cwd=tmp_path)
    assert out['view']['brief'] == {'source': None, 'confirmed': None}

    # Not a PDF, then a stale revision: refused, nothing written.
    not_pdf = tmp_path / 'notes.pdf'
    not_pdf.write_text('plain text', encoding='utf-8')
    code, out = hyp('brief', 'import', '--study', study, '--pdf', not_pdf,
                    '--expected-revision', rev, cwd=tmp_path)
    assert code == 2 and out['error']['details']['reason'] == 'not_a_pdf', out
    code, out = hyp('brief', 'import', '--study', study, '--pdf', PDF,
                    '--expected-revision', rev - 1, cwd=tmp_path)
    assert code == 2 and out['error']['code'] == 'stale_revision', out
    assert not (study / 'brief').exists()

    # The import: the text page by page, the PDF copied, the revision bumped.
    code, out = hyp('brief', 'import', '--study', study, '--pdf', PDF,
                    '--expected-revision', rev, cwd=tmp_path)
    assert code == 0, out
    assert out['revision'] == rev + 1 and out['result']['pages'] == 3
    assert tuple(out['then']) == cmd_brief.THEN_KEYS
    assert out['then']['options'] == list(cmd_brief.OPTIONS['fr'])
    rev = out['revision']
    source = json.loads((study / 'brief' / 'source.json').read_text(encoding='utf-8'))
    assert [p['n'] for p in source['pages']] == [1, 2, 3]
    assert '4,5 mpg' in source['pages'][0]['text'] and '3,5 mpg' in source['pages'][1]['text']
    assert 'fictif' in source['pages'][0]['text'].lower()
    assert (study / 'brief' / PDF.name).read_bytes() == PDF.read_bytes()
    code, out = hyp('status', '--study', study, cwd=tmp_path)
    brief = out['view']['brief']
    assert tuple(brief['source']) == cb.SOURCE_RECORD_KEYS and brief['confirmed'] is None
    # The digest still reads the use case's own brief.
    code, out = hyp('status', '--study', study, '--summary', '--digest', cwd=tmp_path)
    assert 'aujourd\'hui l\'écart' not in out['texts']['fr']['case_brief']['problem']

    words = "J'adopte la fiche"
    # A page the PDF does not have, and a field that cites nothing: refused.
    bad = _draft(citations={**_draft()['citations'], 'out_of_scope_and_risks': [4]})
    code, out = hyp('brief', 'set', '--study', study, '--file', _write(tmp_path / 'b.yaml', bad),
                    '--user-words', words, '--expected-revision', rev, cwd=tmp_path)
    assert code == 2 and 'pages [4]' in out['error']['message'], out
    uncited = _draft(citations={k: v for k, v in _draft()['citations'].items()
                                if k != 'production'})
    code, out = hyp('brief', 'set', '--study', study,
                    '--file', _write(tmp_path / 'u.yaml', uncited), '--user-words', words,
                    '--expected-revision', rev, cwd=tmp_path)
    assert code == 2 and "['production']" in out['error']['message'], out
    good = _write(tmp_path / 'draft.yaml', _draft())
    code, out = hyp('brief', 'set', '--study', study, '--file', good, '--user-words', words,
                    '--expected-revision', rev - 1, cwd=tmp_path)
    assert code == 2 and out['error']['code'] == 'stale_revision', out

    # Adopted in the junior's words: the study's brief replaces the use case's one.
    code, out = hyp('brief', 'set', '--study', study, '--file', good, '--user-words', words,
                    '--expected-revision', rev, cwd=tmp_path)
    assert code == 0, out
    assert out['revision'] == rev + 1 and out['result']['user_words'] == words
    code, out = hyp('status', '--study', study, cwd=tmp_path)
    confirmed = out['view']['brief']['confirmed']
    assert tuple(confirmed) == cb.CONFIRMED_KEYS and confirmed['user_words'] == words
    assert confirmed['citations']['problem'] == [1]
    assert confirmed['open_questions'][0]['about'] == 'objective'
    code, out = hyp('status', '--study', study, '--summary', '--digest', cwd=tmp_path)
    assert out['case_brief']['current_method_error'] == {'value': 4.5, 'unit': 'mpg',
                                                         'measure': 'mae'}
    problem = out['texts']['fr']['case_brief']['problem'].replace('\u00a0', ' ') \
        .replace('\u202f', ' ')                      # French spacing, written by the engine
    assert problem == PROBLEM.replace('{current_method_error}', '4,5 mpg'), problem
    report = (study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'Un service appelé par l&#x27;outil de conception.' in report \
        or "Un service appelé par l'outil de conception." in report
