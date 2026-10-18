"""Fixtures of the Phase 3 deliverable tests (HTML report, notebooks, check, render).

Phase 2 (activities) is built in parallel, so these fixtures create results the way
Phase 2 will: ``registry.put`` under the writer lock, an exposure record per read, and a
registered test action (``test.promote``) that sets ``state['current'][slot]`` through
``commands.apply``, which also triggers the automatic render (WP3.4).

The value shapes are the ones Phase 3 assumes (listed in ``PHASE2_SHAPES`` below):
predictions are a gzip CSV blob ``row_key,y,score``; a policy evaluation lists its rules
with per-model metrics (volume, precision, recall, ``tied_at_cut``, percentile
intervals) and paired differences. Everything lives in ``tmp_path``.
"""
from __future__ import annotations

import gzip
import shutil
from pathlib import Path

import pytest

from mlkit.reliability import Handler
from mlkit.study import commands as cmd, exposure, lock, read, registry
from mlkit.study.store import StudyStore

PROMOTE = 'test.promote'
CODE_MODULES = ['mlkit.study.records']
SPLIT_VALUE = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}
NOT_AVAILABLE = 'desk_followups'
UNCERTAIN_INCLUDED = 'reminders_sent'
POLICY_RULE = 'capacity:20'

# The shapes of Phase 2 result values that Phase 3 renders and checks.
PHASE2_SHAPES = {
    'split': ['train_rows', 'validation_rows', 'train_positives', 'validation_positives',
              'train_rate', 'validation_rate'],
    'eda.target_rate': ['rate', 'positives', 'rows'],
    'eda.special_values': ['values[] {column, value, rows, share}', 'co_occurrence.rows'],
    'fit.*': ['auc', 'n', 'n_positive', 'features (also params.features)',
              'blob predictions: gzip CSV row_key,y,score'],
    'policy.evaluation': ['params.rules', 'n', 'n_positive', 'bootstrap{replicates,seed,level}',
                          'rules[] {rule, models{slot: {volume, volume_rate, true_positives, '
                          'precision, recall, tied_at_cut, intervals{metric: [lo, hi]}}}, '
                          'paired{metric: {difference, interval: [lo, hi]}}}'],
}


def _promote(ctx):
    def run(state, params):
        state['current'][params['slot']] = params['result_id']
        state['stale'].pop(params['result_id'], None)
        return {'slot': params['slot'], 'result_id': params['result_id']}
    return Handler(frozenset({'slot', 'result_id'}), run)


if PROMOTE not in cmd.ACTIONS:
    cmd.register_action(PROMOTE, _promote)


class Builder:
    """Drives one study through commands, like the agent and Phase 2 would."""

    def __init__(self, study: Path, case_dir: Path):
        self.study = study
        self.case_dir = case_dir
        self.n = 0
        self.outcomes: list[cmd.Outcome] = []

    @property
    def revision(self) -> int:
        return read.open(self.study).revision

    def apply(self, action, params) -> cmd.Outcome:
        self.n += 1
        out = cmd.apply(self.study, action=action, params=params, request_id=f'req-{self.n}',
                        expected_revision=self.revision)
        self.outcomes.append(out)
        return out

    def decide(self, decision_id, value, restatement, words) -> cmd.Outcome:
        out = self.apply(cmd.ACTION_PROPOSE, {'decision_id': decision_id, 'value': value,
                                              'restatement': restatement,
                                              'rationale': 'The agent recommends it.'})
        pid = out.payload['result']['proposal_id']
        return self.apply(cmd.ACTION_CONFIRM, {'proposal_id': pid, 'user_words': words,
                                               'channel': 'chat', 'actor': 'user'})

    def put(self, slot, values, *, params=None, inputs=None, blobs=None, partition='train',
            purpose='train_eda', keys=None, promote=True) -> str:
        state = read.open(self.study).state
        store = StudyStore(self.study)
        keys = keys or self.train_keys
        eid = exposure.new_exposure_id()
        with lock.writer_lock(self.study):
            put = registry.put(store, activity=slot, params=params or {},
                               inputs={'dataset_sha256': state['dataset']['sha256'],
                                       **(inputs or {})},
                               code=registry.code_fingerprint(CODE_MODULES), values=values,
                               blobs=blobs, partition=partition, n_rows=len(keys),
                               exposure_id=eid, started_revision=state['revision'])
            exposure.record(store, exposure_id=eid, revision=state['revision'], activity=slot,
                            result_id=put['result_id'], purpose=purpose, partition=partition,
                            row_keys=keys, dataset_sha256=state['dataset']['sha256'],
                            columns=['outcome'])
        if promote:
            self.apply(PROMOTE, {'slot': slot, 'result_id': put['result_id']})
        return put['result_id']

    # rows of the synthetic case: L2 .. L301
    @property
    def all_keys(self):
        return [f'L{i}' for i in range(2, 302)]

    @property
    def train_keys(self):
        return self.all_keys[:210]

    @property
    def validation_keys(self):
        return self.all_keys[210:]


def predictions_blob(keys, ys, scores) -> bytes:
    text = 'row_key,y,score\n' + ''.join(f'{k},{y},{s}\n' for k, y, s in zip(keys, ys, scores))
    return gzip.compress(text.encode(), mtime=0)


def features_of(case_dir: Path) -> list[str]:
    from mlkit.study import case as c

    return [v['name'] for v in c.load_case(case_dir).document['variables']
            if v['role'] == 'feature']


def policy_values(fit_rid: str, base_rid: str) -> dict:
    def metrics(volume, tp, n_pos, intervals):
        return {'volume': volume, 'volume_rate': volume / 90, 'true_positives': tp,
                'precision': tp / volume, 'recall': tp / n_pos, 'tied_at_cut': None,
                'intervals': intervals}
    logistic = metrics(20, 7.0, 11, {'precision': [0.15, 0.55], 'recall': [0.3, 0.9]})
    baseline = metrics(20, 2.4444, 11, {'precision': [0.1222, 0.1222], 'recall': [0.1, 0.35]})
    baseline['tied_at_cut'] = {'n_tied': 90, 'accepted_fraction': 0.2222}
    thr = metrics(31, 8.0, 11, {'precision': [0.12, 0.45], 'recall': [0.4, 0.95]})
    return {
        'n': 90, 'n_positive': 11,
        'bootstrap': {'replicates': 2000, 'seed': 20261017, 'level': 0.95},
        'predictions': {'fit.logistic': fit_rid, 'fit.baseline': base_rid},
        'rules': [
            {'rule': 'capacity:20',
             'models': {'fit.logistic': logistic, 'fit.baseline': baseline},
             'paired': {'precision': {'difference': 0.2278, 'interval': [0.05, 0.4]},
                        'recall': {'difference': 0.4141, 'interval': [0.1, 0.7]}}},
            {'rule': 'threshold:0.3', 'models': {'fit.logistic': thr},
             'paired': {}},
        ],
    }


def build(study: Path, case_dir: Path, upto: str = 'conclusion') -> Builder:
    """A study taken through every step (or up to ``upto``) with fixture results."""
    cmd.init(case_dir, study)
    b = Builder(study, case_dir)
    b.decide('prediction_time', 'when the membership expires, before any reminder',
             'You predict when the membership expires, before any reminder is sent.',
             'Yes: at expiry, before the first reminder.')
    if upto == 'prediction_time':
        return b
    features = features_of(case_dir)
    value = {f: 'available_at_prediction' for f in features}
    value[NOT_AVAILABLE] = 'not_available'
    value[UNCERTAIN_INCLUDED] = 'uncertain_included'
    b.decide('feature_availability', value,
             'Everything is known at expiry except the desk follow-ups, which are logged later; '
             'the reminders count is uncertain and kept as a limit.',
             'Right, drop the desk follow-ups and keep reminders as a listed limit.')
    b.decide('split', SPLIT_VALUE, 'Stratified split with 30% validation and seed 20261017.',
             'Use that split before we look at anything.')
    split = b.put('split', {'train_rows': 210, 'validation_rows': 90, 'train_positives': 25,
                            'validation_positives': 11, 'train_rate': 25 / 210,
                            'validation_rate': 11 / 90},
                  params=dict(SPLIT_VALUE), partition='all', purpose='structural_inspection',
                  keys=b.all_keys)
    if upto == 'split':
        return b
    b.put('eda.target_rate', {'rate': 25 / 210, 'positives': 25, 'rows': 210},
          inputs={'results': {'split': split}})
    b.put('eda.special_values', {'values': [{'column': 'days_since_last_lapse', 'value': '-1',
                                             'rows': 122, 'share': 122 / 210}],
                                 'co_occurrence': {'rows': 122}},
          inputs={'results': {'split': split}})
    if upto == 'train_eda':
        return b
    used = sorted(f for f, s in value.items() if s in ('available_at_prediction',
                                                       'uncertain_included'))
    vkeys = b.validation_keys
    ys = [1 if i % 8 == 0 else 0 for i in range(90)]
    base = b.put('fit.baseline', {'auc': 0.5, 'prior': 0.119, 'n': 90},
                 inputs={'results': {'split': split}}, partition='validation',
                 purpose='validation_model_evaluation', keys=vkeys,
                 blobs={'predictions': predictions_blob(vkeys, ys, [0.119] * 90)})
    fit = b.put('fit.logistic', {'auc': 0.714, 'n': 90, 'n_positive': 11, 'features': used},
                params={'features': used}, inputs={'results': {'split': split}},
                partition='validation', purpose='validation_model_evaluation', keys=vkeys,
                blobs={'predictions': predictions_blob(vkeys, ys,
                                                       [round(0.05 + (i % 17) / 20, 3)
                                                        for i in range(90)])})
    if upto == 'models':
        return b
    b.put('policy.evaluation', policy_values(fit, base),
          params={'rules': ['capacity:20', 'threshold:0.3']},
          inputs={'results': {'fit.logistic': fit, 'fit.baseline': base}},
          partition='validation', purpose='validation_policy_selection', keys=vkeys)
    b.decide('policy', POLICY_RULE, 'Call the 20 highest-scored members.',
             'Yes, twenty calls is what the desk can handle.')
    if upto == 'policy':
        return b
    b.decide('conclusion', {'verdict': 'keep_baseline',
                            'text': 'Keep the simple rule for now; the model ranks better on '
                                    'validation rows that were used to choose it.'},
             'You keep the baseline and record the limits.',
             'I keep the baseline and note why.')
    return b


@pytest.fixture(scope='module')
def full_study_template(tmp_path_factory, synthetic_case_dir) -> Path:
    study = tmp_path_factory.mktemp('full') / 'study'
    build(study, synthetic_case_dir)
    return study


@pytest.fixture
def full_study(tmp_path, full_study_template) -> Path:
    """A private copy of the fully built study."""
    target = tmp_path / 'study'
    shutil.copytree(full_study_template, target, symlinks=True)
    return target
