"""Lot 2026-10-28, engine (T-E1 with the cuts of LOT spec §8, plus §9's R66 and R67): one
real-CLI walkthrough of a new Auto MPG study in the automatic ``full_demo`` mode, to the end,
then ``status --summary --digest`` (both languages) and the report.

It checks, on what the panel and the agent read:

* EN-9, EN-11: 14 steps, ``error_metric`` just before ``success_criterion``, recorded ``mae``
  with the basis ``automatic``; the final test opened once (§8.15);
* EN-14: every card has its full name (``companion_env.STEP_NAMES``);
* EN-5, EN-8: every answered question has a reading whose every digit run is the text of one
  of its cites, built with the length caps enforced (``HYPOTRAIL_STRICT_TEXTS=1``); cites
  equal across languages (§8.12);
* EN-15 (cut to the plan): ``diag.final_test`` current, its scatter holding every final row;
* EN-17: ``strata_counts`` sums to the 318 development and 80 sealed rows;
* EN-18: the moment's timeline has a slider over four milestones, positions computed;
* EN-10: the made-up error example, MAE 2 and RMSE √8;
* EN-21: no « moyenne de référence », « à k plis » or « lignes d'entraînement » in any French
  digest text;
* R66: the brief in the digest and in the report's first chapter;
* R67: the business bar of the criterion, judged on the final test, said in the conclusion;
* R65: the defensibility checklist;
* §8.11: ``status --summary`` without ``--digest`` keeps its keys.

The automatic mode's values are the engine's; this is not a Copilot session.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

import companion_contract as cc
import flowkit as fk
import test_journey_walkthrough as jw
from mlkit.study import companion_env as ce, read, state as st, step_cards as sc

FORBIDDEN_FR = ('moyenne de référence', 'à k plis', "lignes d'entraînement")


@pytest.fixture(scope='module')
def demo(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv(sc.STRICT_ENV, '1')
    f = fk.Flow(tmp_path_factory.mktemp('lot-1028') / 'study', jw.AUTO_MPG, prefix='d')
    f.call('init', '--case', jw.AUTO_MPG, '--study', f.study, '--lang', 'fr',
           '--automation', 'full_demo')
    run = f.call('automation', 'run', '--study', f.study, '--json', '--request-id', 'auto',
                 '--expected-revision', f.rev())
    digest = f.call('status', '--summary', '--digest', '--study', f.study)
    plain = f.call('status', '--summary', '--study', f.study)
    render = f.call('render', '--study', f.study)
    yield {'f': f, 'run': run, 'digest': digest, 'plain': plain, 'render': render,
           'state': read.open(f.study).state}
    mp.undo()


def _cards(digest, lang='fr'):
    return digest['texts'][lang]['step_cards']


def _question(digest, qid, lang='fr'):
    return next(q for s in _cards(digest, lang)['steps'] for q in s['questions']
                if q['id'] == qid)


def test_the_automatic_study_reaches_the_end_with_fourteen_steps(demo):
    run, digest, state = demo['run'], demo['digest'], demo['state']
    assert run['status'] == 'ended' and run['reason'] == 'reached_end', run
    ids = [s['id'] for s in digest['plan']]
    assert len(ids) == 14
    assert ids.index('error_metric') + 1 == ids.index('success_criterion')
    decision = state['decisions']['error_metric']
    assert decision['status'] == 'confirmed' and decision['value'] == {'metric': 'mae'}
    assert st.confirmation_basis(decision['confirmation']) == st.AUTOMATIC
    assert 'error_metric' in [i['decision_id'] for i in digest['review_queue']['items']]
    # The final test is opened once (§8.15), and its diagnostics join the plan (EN-15).
    assert digest['ledger']['final_test'] == {'openings': 1, 'max': 1}
    assert digest['results']['diag.final_test']['current'] is True
    values = read.open(demo['f'].study).result(
        digest['results']['diag.final_test']['result_id'])['output']['values']
    scatter = values['models']['fit.linear']['scatter']
    assert scatter['n_shown'] == scatter['n_rows'] == 80


def test_every_card_is_named_and_every_reading_cites_its_numbers(demo):
    digest = demo['digest']
    for lang in ('en', 'fr'):
        cards = _cards(digest, lang)
        assert cards['schema'] == sc.SCHEMA and cards['total'] == 14
        assert tuple(cards) == sc.CARDS_KEYS
        assert [s['step'] for s in cards['steps']] == [s['id'] for s in digest['plan']]
        for card in cards['steps']:
            assert tuple(card) == sc.STEP_KEYS
            assert card['name'] == ce.STEP_NAMES[lang][card['step']]
            assert card['picture']['kind'] in sc.PICTURE_KINDS
            for q in card['questions']:
                assert tuple(q) == sc.QUESTION_KEYS and q['chart'] in sc.CHART_KINDS
                assert q['frame']['evidence'] in sc.EVIDENCE
                if q['status'] != 'answered':
                    continue
                reading = ' '.join(q['reading'][k] for k in sc.READING_KEYS)
                texts = [c['text'] for c in q['cites']]
                for run in re.findall(r'\d+', reading):
                    assert any(run in t for t in texts), (q['id'], run, reading)
                assert all(tuple(c) == sc.CITE_KEYS for c in q['cites'])
    # Every card of a study at its end is done, each question answered with a reading.
    fr = _cards(digest)['steps']
    answered = [q for s in fr for q in s['questions'] if q['status'] == 'answered']
    assert len(answered) == len(sc.QUESTIONS)
    # The cites are the same values at the same paths in both languages (§8.12).
    for s_en, s_fr in zip(_cards(digest, 'en')['steps'], fr):
        for q_en, q_fr in zip(s_en['questions'], s_fr['questions']):
            assert [(c['name'], c['path'], c['value']) for c in q_en['cites']] == \
                [(c['name'], c['path'], c['value']) for c in q_fr['cites']], q_en['id']


def test_the_pictures_of_the_framing_steps(demo):
    digest, state = demo['digest'], demo['state']
    counts = state['partition']['strata_counts']
    assert sum(s['development'] for s in counts) == 318
    assert sum(s['sealed'] for s in counts) == 80
    sealed = _question(digest, 'split.sealed')
    assert sealed['chart_data']['strata'] == counts and sealed['reading'] is not None
    timeline = _question(digest, 'moment.when')['chart_data']
    assert timeline['slider'] is True and len(timeline['milestones']) == 4
    assert timeline['status'] == 'scenario_assumption'
    assert [p['after'] for p in timeline['positions']] == ['design', 'body', 'tests']
    body = next(p for p in timeline['positions'] if p['after'] == 'body')
    assert 'weight' in body['kept'] and body['uncertain'] == ['acceleration']
    assert next(c for c in timeline['columns'] if c['column'] == 'acceleration')['known_at'] \
        is None
    folds = _question(digest, 'split.folds')['chart_data']
    assert folds['illustrative'] is False and folds['order_column'] == 'année du modèle'
    assert sum(b['n_rows'] for b in folds['blocks']) == 318
    metric = _question(digest, 'metric.weigh')
    assert metric['chart_data']['mae'] == 2.0
    assert math.isclose(metric['chart_data']['rmse'], math.sqrt(8))
    assert '2,83' in metric['reading']['see'] and metric['frame']['evidence'] == 'illustration'


def test_the_french_texts_name_the_reference_and_the_folds(demo):
    texts = json.loads(json.dumps(demo['digest']['texts']['fr']))
    split = next(s for s in texts['step_cards']['steps'] if s['step'] == 'split')
    # EN-21: the term « k plis » is defined in the split picture's « En savoir plus » only.
    assert 'k plis' in split['picture'].pop('more')
    flat = json.dumps(texts, ensure_ascii=False)
    for phrase in FORBIDDEN_FR:
        assert phrase not in flat, phrase


def test_the_brief_and_the_two_level_criterion(demo):
    digest, state = demo['digest'], demo['state']
    # R66: the brief in the digest, the business numbers from the PO.
    assert digest['case_brief'] == {
        'fictitious': True,
        'current_method_error': {'value': 4.5, 'unit': 'mpg', 'measure': 'mae'},
        'target_error': {'value': 3.5, 'unit': 'mpg', 'measure': 'mae'}}
    assert '4,5 mpg' in digest['texts']['fr']['case_brief']['problem']
    assert digest['case_display']['columns']['model_year']['fr'] == 'année du modèle'
    report = (demo['f'].study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert demo['render']['status'] == 'ok' and 'data-brief="fictitious"' in report
    # R67: the business bar fixed with the criterion, judged on the final test.
    value = state['decisions']['success_criterion']['value']
    assert value == {'metric': 'mae_reduction', 'min_share': 0.1, 'business_max_error': 4.5}
    business = digest['criterion_configurations']['business']
    assert business['judged_on'] == 'final_test' and business['met'] is True
    assert business['final_test']['value'] <= 4.5
    assert 'barre métier' in digest['texts']['fr']['criterion_words']
    reading = _question(digest, 'conclusion.criterion')['reading']['conclude']
    assert 'barre métier' in reading and _question(digest, 'conclusion.criterion')[
        'verdict']['met'] is True
    # R65: the checklist (an automatic study: nothing in the junior's words yet).
    checklist = {i['id']: i['done'] for i in digest['defensibility']['checklist']}
    assert checklist['final_test_opened_once'] is True
    assert checklist['framing_in_your_words'] is False
    assert set(digest['texts']['fr']['defensibility_note']['checklist']) == set(checklist)


def test_the_plain_summary_keeps_its_keys(demo):
    assert tuple(demo['plain']) == cc.SUMMARY_KEYS
    assert tuple(demo['digest']) == cc.DIGEST_SUMMARY_KEYS
    for lang in ('en', 'fr'):
        assert tuple(demo['digest']['texts'][lang]) == cc.LANGUAGE_TEXT_KEYS
