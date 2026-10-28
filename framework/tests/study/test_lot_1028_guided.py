"""Lot 2026-10-28, engine (T-E3, and the existing-study assertion of LOT spec §8.1): two
real-CLI guided walkthroughs of Auto MPG with the journey walker.

* A new study, where the test junior chooses the RMSE at the new error-measure step:
  the step-1 question names the next step (EN-13, both languages); a criterion on the MAE is
  then refused ``invalid_value`` with ``details.error_metric`` and the picker offers the RMSE
  only (EN-9); after the exploration ``next_action`` is ``read_exploration`` with ``then`` the
  first fit, and it is gone once ``fit.baseline`` is registered (EN-12); the questions of the
  continue/explain pauses name the next step, the propose questions match their options
  (§8.14).
* A study whose state holds the decision set of before this lot (no ``error_metric``, no
  ``strata_counts``): it keeps its 13 steps, its criterion picker offers both metrics, it
  never pauses after the exploration, it has no step cards, and it reaches its end with every
  result current (§8.1: no engine change stales or reshapes an existing study).

The agent's words are a test script; this is not a Copilot session.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import flowkit as fk
import test_journey_walkthrough as jw
from mlkit.study import companion_env as ce, read, state as st

DATA_CARD_Q = {'en': 'The data card is shown. Shall we move on to the prediction moment?',
               'fr': 'La fiche des données est affichée. On passe au moment de la prédiction ?'}
EXPLORATION_Q = {'en': "The exploration's charts are shown. Shall we move on to the models?",
                 'fr': "Les graphiques de l'exploration sont affichés. On passe aux modèles ?"}


class _RmseFlow(fk.Flow):
    """The test junior chooses the RMSE at the error-measure step."""

    def call(self, *args, expect=0):
        args = [str(a) for a in args]
        if args[:3] == ['decide', 'propose', 'error_metric'] and '--value-json' in args:
            args[args.index('--value-json') + 1] = json.dumps({'metric': 'rmse'})
        return super().call(*args, expect=expect)


def _digest(f) -> dict:
    return f.call('status', '--summary', '--digest', '--study', f.study)


def pre_lot(study: Path) -> Path:
    """The study as ``init`` wrote it before this lot: without the decision ``error_metric``
    and without ``strata_counts``. The state bytes are rewritten with their digest, as a study
    of that generation holds them (a test helper; never applied to a real study)."""
    home = Path(study) / '.hypotrail'
    state = json.loads((home / 'state.json').read_text())
    state['decisions'].pop(st.ERROR_METRIC)
    state['partition'].pop('strata_counts')
    data = st.dumps(state)
    (home / 'state.json').write_bytes(data)
    (home / 'state.sha256').write_text(st.sha_line(st.digest(data)))
    return Path(study)


@pytest.fixture(scope='module')
def new_study(tmp_path_factory):
    f = _RmseFlow(tmp_path_factory.mktemp('lot-1028-guided') / 'study', jw.AUTO_MPG,
                  prefix='g')
    f.call('init', '--case', jw.AUTO_MPG, '--study', f.study, '--lang', 'fr')
    seen = {'step1': _digest(f), 'reads': [], 'refused': None, 'options': None,
            'explore': None}

    def on_read(label, action):
        seen['reads'].append(action)
        if action.get('decision') == 'success_criterion' and seen['refused'] is None:
            seen['options'] = action.get('criterion_options')
            seen['refused'] = fk.Flow.call(
                f, 'decide', 'propose', 'success_criterion', '--value-json',
                json.dumps({'metric': 'mae_reduction', 'min_share': 0.1}), '--restatement',
                'x.', '--rationale', 'r', '--request-id', f.rid(), '--expected-revision',
                f.rev(), '--study', f.study, expect=2)
        if action.get('kind') == 'read_exploration' and seen['explore'] is None:
            seen['explore'] = _digest(f)
    jw.walk(f, 'regression', on_read=on_read)
    seen['done'] = _digest(f)
    seen['state'] = read.open(f.study).state
    return f, seen


def test_the_questions_name_the_next_step(new_study):
    _, seen = new_study
    for lang in ('en', 'fr'):
        assert seen['step1']['texts'][lang]['question'] == DATA_CARD_Q[lang]
        assert seen['explore']['texts'][lang]['question'] == EXPLORATION_Q[lang]
    # §8.14: every continue/explain pause names the next step by its full name; a propose
    # question of the error measure names the drafted option.
    names = ce.STEP_NAMES['en']
    assert names['prediction_time'].lower() in DATA_CARD_Q['en']
    assert names['models'].lower() in EXPLORATION_Q['en']
    measure = next(a for a in seen['reads'] if a.get('decision') == 'error_metric'
                   and a.get('kind') == 'propose')
    assert '(MAE)' in measure['question'] and measure['default_value'] == {'metric': 'mae'}


def test_the_criterion_is_fixed_on_the_chosen_measure(new_study):
    _, seen = new_study
    assert seen['state']['decisions']['error_metric']['value'] == {'metric': 'rmse'}
    refusal = seen['refused']['error']
    assert refusal['code'] == 'invalid_value'
    assert refusal['details']['error_metric'] == 'rmse'
    assert [m['metric'] for m in seen['options']['metrics']] == ['rmse_reduction']
    assert all(c['value']['metric'] == 'rmse_reduction' for c in seen['options']['candidates'])
    assert seen['state']['decisions']['success_criterion']['value']['metric'] == 'rmse_reduction'


def test_the_pause_after_the_exploration(new_study):
    _, seen = new_study
    reads = seen['reads']
    pause = [i for i, a in enumerate(reads) if a['kind'] == 'read_exploration']
    assert pause, [a['kind'] for a in reads]
    action = reads[pause[0]]
    assert action['step'] == 'train_eda' and action['then']['activity'] == 'fit.baseline'
    assert action['pause']['options'] == ['continue', 'explain']
    # Stateless: once the first fit is registered, the pause is gone for good.
    fitted = next(i for i, a in enumerate(reads) if i > pause[0] and a['kind'] != 'read_exploration')
    assert all(a['kind'] != 'read_exploration' for a in reads[fitted:])
    # Every exploration chart was current at the pause, and no model fitted yet.
    results = seen['explore']['results']
    assert 'fit.baseline' not in results and results['eda.correlation']['current']
    cards = seen['explore']['texts']['fr']['step_cards']
    assert cards['current'] == 'train_eda'
    explore = next(s for s in cards['steps'] if s['step'] == 'train_eda')
    assert [q['status'] for q in explore['questions']] == ['answered'] * 3
    later = [s for s in cards['steps'] if s['state'] == 'upcoming']
    assert later and all(s['questions'] == [] for s in later)


@pytest.fixture(scope='module')
def old_study(tmp_path_factory):
    f = fk.Flow(tmp_path_factory.mktemp('lot-1028-old') / 'study', jw.AUTO_MPG, prefix='o')
    f.call('init', '--case', jw.AUTO_MPG, '--study', f.study, '--lang', 'fr')
    pre_lot(f.study)
    seen = {'reads': [], 'options': None}

    def on_read(label, action):
        seen['reads'].append(action)
        if action.get('decision') == 'success_criterion' and seen['options'] is None:
            seen['options'] = action.get('criterion_options')
    jw.walk(f, 'regression', on_read=on_read)
    seen['done'] = _digest(f)
    seen['state'] = read.open(f.study).state
    return f, seen


def test_a_study_of_before_the_lot_keeps_its_plan_and_stays_current(old_study):
    _, seen = old_study
    digest, state = seen['done'], seen['state']
    ids = [s['id'] for s in digest['plan']]
    assert len(ids) == 13 and 'error_metric' not in ids
    assert 'error_metric' not in state['decisions'] and not st.has_error_metric(state)
    assert {m['metric'] for m in seen['options']['metrics']} == {'mae_reduction',
                                                                  'rmse_reduction'}
    assert all('business_max_error' not in c['value'] for c in seen['options']['candidates'])
    assert all(a['kind'] != 'read_exploration' for a in seen['reads'])
    assert digest['next_action']['kind'] == 'done'
    assert all(r['current'] for r in digest['results'].values()), \
        [k for k, r in digest['results'].items() if not r['current']]
    for lang in ('en', 'fr'):
        assert digest['texts'][lang]['step_cards'] is None
    assert digest['criterion_configurations']['business'] is None
    assert 'strata_counts' not in state['partition']
