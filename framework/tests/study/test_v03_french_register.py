"""v0.3 owner decision (2026-10-21): the French register is "vous" everywhere.

A French study's junior texts never address the junior with the second person singular:
no "tu", "toi", "te", "t'", "ton", "ta", "tes", and no inverted "-tu" question. Checked on
the texts a walk through a French study emits (``next_action``: message, digest, question,
recommendation, criterion options; the limits; ``status --summary``: ``recap_junior`` and
its limits; the deliverables' messages; the data card), on every branch of the engine's
French text functions (step texts, limits, questions, agent-facing junior messages), and on
the rendered report and notebook.

Quoted material (« ... » and "..."), which holds the junior's or the case's own words, is
left out. Temporary synthetic studies only (``flowkit``).
"""
from __future__ import annotations

import inspect
import re

import pytest

from mlkit.study import (audience, criterion, governance, junior, render_notebook,
                         render_trials, trials)
from mlkit.study import state as st
from mlkit.study import view as view_mod

import flowkit as fk
import test_wp_c_junior_payloads as wpc

# Second person singular forms. "t'" only before a letter (an elision: "t'appuyer");
# "ta"/"te"/"tes"/"ton" as whole words only, never inside a word or an identifier.
TU = re.compile(r"(?<![\w'’-])(?:tu|toi|ton|ta|tes|te)(?![\w'’-])|(?<![\w'’-])t['’](?=[^\W\d_])"
                r"|\w-(?:tu|toi)\b", re.I)


def tu_forms(text: str) -> list[str]:
    """The singular second-person forms of ``text`` once quoted material is removed."""
    text = re.sub(r'«[^»]*»', ' ', str(text))
    text = re.sub(r'"[^"]*"', ' ', text)
    return TU.findall(text)


def test_the_detector_flags_tu_forms_and_spares_vous_forms():
    for bad in ('Est-ce que tu adoptes cette décision ?', 'Ouvres-tu le test final ?',
                "Avant de t'appuyer sur la conclusion", 'Avec tes mots', 'Ton action',
                'Pas encore confirmé par toi', 'on te demandera', 'en attente de ta réponse'):
        assert tu_forms(bad), bad
    for good in ('Adoptez-vous cette décision ?', 'Ouvrez-vous le test final ?',
                 "Avant de vous appuyer sur la conclusion", 'Avec vos mots', 'Votre action',
                 'la table de contingence', "l'étude est terminée", 'quantile, état',
                 'Proposition : « Tu décides comme indiqué. »'):
        assert not tu_forms(good), good


def _assert_vous(flow, seen: dict) -> None:
    for where, text in wpc._junior_texts(flow):
        found = tu_forms(text)
        assert not found, (where, found, text)
        seen[where.split(':')[0]] = seen.get(where.split(':')[0], 0) + 1


def test_a_french_study_walkthrough_says_vous(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=600)['case'].parent
    flow = wpc.FrenchFlow(tmp_path / 'study', case_dir, prefix='vs')
    seen: dict = {}
    flow.init()
    _assert_vous(flow, seen)
    flow.propose('prediction_time', 'quand la fiche est créée, avant le résultat')
    _assert_vous(flow, seen)                        # await_user_words
    assert flow.view()['next_action']['question'] == 'Adoptez-vous cette décision ?'
    p = flow.view()['open_proposals'][0]
    flow.call('decide', 'confirm', p['proposal_id'], '--user-words',
              fk.default_words('prediction_time'), '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    nxt = flow.view()['next_action']
    _assert_vous(flow, seen)
    flow.decide('feature_availability', nxt['default_value'])
    nxt = flow.view()['next_action']
    _assert_vous(flow, seen)
    flow.decide('split', nxt['default_value'])
    flow.run('split')
    _assert_vous(flow, seen)                        # the criterion options
    flow.decide('success_criterion', {'metric': 'precision_gain', 'min_points': 5})
    flow.run('eda.target_rate')
    flow.run('eda.special_values')
    flow.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    _assert_vous(flow, seen)
    flow.variant()
    flow.decide('model_choice', 'fit.logistic')
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    _assert_vous(flow, seen)
    flow.decide('policy', 'capacity:40',
                words='Yes, I adopt that rule because the desk can make that many calls')
    value = st.b1_default_value(flow.state(), 'final_test')
    _assert_vous(flow, seen)                        # the final-test proposal and its why
    pid = flow.propose('final_test', value)['result']['proposal_id']
    flow.call('decide', 'confirm', pid, '--user-words', wpc.OPEN_WORDS, '--request-id',
              flow.rid(), '--expected-revision', flow.rev(), '--study', flow.study)
    _assert_vous(flow, seen)
    flow.call('render', '--study', flow.study)
    _assert_vous(flow, seen)
    for kind in ('junior_message', 'junior_digest', 'question', 'recommended.why', 'limit',
                 'summary.limit', 'recap_junior', 'artifact', 'step', 'step-title',
                 'criterion.reference', 'criterion.candidate', 'data.final_test', 'data.note'):
        assert seen.get(kind), kind
    # The rendered report and notebook: no French singular second person either.
    items = flow.view()['artifacts']['items']
    rendered = [flow.study / items[name]['path'] for name in ('report', 'notebook')]
    assert all(p.is_file() for p in rendered), rendered
    for path in rendered:
        text = path.read_text(encoding='utf-8')
        if path.suffix == '.html':
            text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', text, flags=re.S)
            text = re.sub(r'<[^>]+>', ' ', text)
        french = [line for line in text.splitlines() if re.search(r'[éèàùçêâ]', line)]
        assert french, path.name                    # the deliverable speaks French
        found = [(line.strip(), tu_forms(line)) for line in french if tu_forms(line)]
        assert not found, (path.name, found[:5])


def test_every_french_text_function_says_vous():
    for text in junior.all_step_texts():
        assert not tu_forms(junior.step_text(text, 'fr')), text
    for kind in junior.LIMIT_IDS_FR:
        for extra in ({}, {'status': 'not_met'}, {'text': 'Out-of-fold'},
                      {'text': 'compare the models and to choose'}, {'text': 'fold'}):
            text = junior.limit_fr(dict({'id': kind, 'decisions': ['split'],
                                         'rules': ['capacity:10'], 'features': ['age'],
                                         'column': 'client', 'share': 0.1,
                                         'changed': ['policy'], 'text': ''}, **extra))
            assert not tu_forms(text), (kind, text)
    # The closed question and every step question, in each confirmation mode and scheme.
    for mode in (st.TRAINING, st.DEFAULT_MODE):
        view = {'mode': mode, 'task': st.BINARY}
        for kind in ('await_user_words', 'reconfirm', 'outcome_unknown', 'show_data_card'):
            q = junior._question({'kind': kind, 'decision': 'split'}, view, 'fr')
            assert q and not tu_forms(q), (mode, kind, q)
    for task in (st.BINARY, st.REGRESSION):
        for decision in ('prediction_time', 'feature_availability', 'split',
                         'success_criterion', 'preprocessing', 'model_variant', 'policy',
                         'model_choice', 'final_test', 'conclusion'):
            for cv in (False, True):
                q = junior._question({'kind': 'propose', 'decision': decision},
                                     {'task': task}, 'fr', cv)
                assert q and not tu_forms(q), (decision, q)
    # The agent-facing junior messages of every next-action kind.
    for kind in ('outcome_unknown', 'acknowledge_interruption', 'reconfirm',
                 'await_user_words', 'blocked', 'show_data_card', 'done'):
        _, text = audience._junior_next({'kind': kind, 'decision': 'split',
                                         'activity': 'fit.logistic', 'requires': ['split']},
                                        'fr')
        assert not tu_forms(text), (kind, text)
    for status in ('ok', 'not_rendered', 'failed', 'stale'):
        for name, generated in (('report', True), ('workbench', False)):
            text = audience.artifact(name, {'status': status, 'generated': generated},
                                     'fr')['junior_message']
            assert not tu_forms(text), (name, status, text)
    assert not tu_forms(render_notebook.RECOMPUTE_NOTE_FR)


def test_the_french_report_translates_every_static_report_label():
    """A new English report label cannot silently leak into a French report."""
    from mlkit.study import texts

    def leaf_paths(value, prefix=()):
        if isinstance(value, dict):
            for key, child in value.items():
                yield from leaf_paths(child, prefix + (key,))
        else:
            yield prefix

    english = texts.load('report')
    french = texts.load('report_fr')
    assert set(leaf_paths(french)) - {('schema',)} == set(leaf_paths(english)) - {('schema',)}


@pytest.mark.parametrize('module', [junior, audience, criterion, view_mod, render_notebook,
                                    trials, render_trials])
def test_the_engine_french_sources_say_vous(module):
    """Every French literal of the modules that write junior text (a literal with a French
    accent), including branches no walk reaches."""
    source = inspect.getsource(module)
    french = re.findall(r"(?:'[^'\n]*[éèàùçê][^'\n]*'|\"[^\"\n]*[éèàùçê][^\"\n]*\")", source)
    found = [s for s in french if tu_forms(s.strip('\'"'))]
    assert not found, (module.__name__, found[:5])
