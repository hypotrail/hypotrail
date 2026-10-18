"""Fixtures of the Phase 3 deliverable tests (HTML report, notebooks, check, render).

Phase 2 (activities) is built in parallel, so these fixtures create results the way
Phase 2 will: ``registry.put`` under the writer lock, an exposure record per read, and a
registered test action (``test.promote``) that sets ``state['current'][slot]`` through
``commands.apply``, which also triggers the automatic render (WP3.4).

The value shapes are the canonical ones of ``docs/specs/CLI-CONTRACT.md`` §8.5 (the
shapes the Phase 2 producers emit): predictions are a gzip CSV blob ``row_key,y,score``;
a split lists ``partitions.{train,validation}.{n_rows,n_positive,rate}``; a fit reports
``validation.{n_rows,n_positive,roc_auc,average_precision}`` and ``features``; a policy
evaluation maps each rule to ``models`` (the output of ``policy.evaluate``),
``intervals`` and paired ``deltas``. Everything lives in ``tmp_path``.
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

# Canonical value shapes (CLI-CONTRACT.md section 8.5) that these fixtures follow.
CANONICAL_SHAPES = {
    'split': ['n_rows', 'partitions.{train,validation}.{n_rows,n_positive,rate}', 'overlap'],
    'eda.target_rate': ['n_rows', 'n_positive', 'n_negative', 'rate'],
    'eda.special_values': ['n_rows', 'special_values[] {column, value, n_rows, share, '
                           'n_positive, rate}', 'co_occurrence[] {a, b, n_both, n_either, '
                           'same_rows}'],
    'eda.rate_by:<column>': ['column', 'overall_rate', 'groups[] {value, n_rows, n_positive, '
                             'rate, small_count}'],
    'fit.*': ['features', 'n_train', 'validation{n_rows, n_positive, roc_auc, '
              'average_precision}', 'blob predictions: gzip CSV row_key,y,score'],
    'policy.evaluation': ['params.rules', 'n', 'n_positive', 'bootstrap{replicates,seed,level}',
                          'rules{rule: {models{slot: policy.evaluate(...)}, '
                          'intervals{slot: {metric: {low, high}}}, '
                          'deltas{slot: {metric: {point, low, high}}}}}'],
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

    def decide(self, decision_id, value, restatement, words, basis='explicit') -> cmd.Outcome:
        out = self.apply(cmd.ACTION_PROPOSE, {'decision_id': decision_id, 'value': value,
                                              'restatement': restatement,
                                              'rationale': 'The agent recommends it.'})
        pid = out.payload['result']['proposal_id']
        return self.apply(cmd.ACTION_CONFIRM, {'proposal_id': pid, 'user_words': words,
                                               'channel': 'chat', 'actor': 'user',
                                               'basis': basis})

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


def evaluation(rule, kind, parameter, selected, tp, *, n=90, n_positive=11, cut=None) -> dict:
    """A ``policy.evaluate`` output with the given counts (same keys as the producer)."""
    cut = cut or {'score': None, 'n_tied': 0, 'fraction_selected': None}
    return {'rule': rule, 'kind': kind, 'parameter': parameter, 'n': n, 'n_positive': n_positive,
            'selected': selected, 'true_positives': tp, 'false_positives': selected - tp,
            'false_negatives': n_positive - tp,
            'precision': tp / selected if selected else None, 'recall': tp / n_positive,
            'volume': selected, 'volume_rate': selected / n, 'tied_at_cut': cut['n_tied'],
            'cut': cut, 'selection': 'expected' if kind == 'capacity' and cut['n_tied'] else 'exact'}


def interval(low, high) -> dict:
    return {'low': low, 'high': high, 'undefined_replicates': 0}


def policy_values(fit_rid: str, base_rid: str) -> dict:
    tied = {'score': 0.119, 'n_tied': 90, 'fraction_selected': 0.2222}
    capacity = {
        'models': {'fit.logistic': evaluation('capacity:20', 'capacity', 20, 20.0, 7.0),
                   'fit.baseline': evaluation('capacity:20', 'capacity', 20, 20.0, 2.4444,
                                              cut=tied)},
        'intervals': {'fit.logistic': {'precision': interval(0.15, 0.55),
                                       'recall': interval(0.3, 0.9),
                                       'volume': interval(20.0, 20.0)},
                      'fit.baseline': {'precision': interval(0.1222, 0.1222),
                                       'recall': interval(0.1, 0.35),
                                       'volume': interval(20.0, 20.0)}},
        'deltas': {'fit.logistic': {'precision': {'point': 0.2278, **interval(0.05, 0.4)},
                                    'recall': {'point': 0.4141, **interval(0.1, 0.7)},
                                    'volume': {'point': 0.0, **interval(0.0, 0.0)}}},
    }
    threshold = {
        'models': {'fit.logistic': evaluation('threshold:0.3', 'threshold', 0.3, 31.0, 8.0),
                   'fit.baseline': evaluation('threshold:0.3', 'threshold', 0.3, 0.0, 0.0)},
        'intervals': {'fit.logistic': {'precision': interval(0.12, 0.45),
                                       'recall': interval(0.4, 0.95),
                                       'volume': interval(24.0, 38.0)},
                      'fit.baseline': {'precision': {'low': None, 'high': None,
                                                     'undefined_replicates': 2000},
                                       'recall': interval(0.0, 0.0),
                                       'volume': interval(0.0, 0.0)}},
        'deltas': {'fit.logistic': {'precision': {'point': None, 'low': None, 'high': None,
                                                  'undefined_replicates': 2000},
                                    'recall': {'point': 0.7273, **interval(0.4, 0.95)},
                                    'volume': {'point': 31.0, **interval(24.0, 38.0)}}},
    }
    return {
        'rules': {'capacity:20': capacity, 'threshold:0.3': threshold},
        'n': 90, 'n_positive': 11,
        'predictions': {'fit.baseline': base_rid, 'fit.logistic': fit_rid},
        'reference': 'fit.baseline',
        'bootstrap': {'replicates': 2000, 'seed': 20261017, 'level': 0.95,
                      'method': 'paired percentile bootstrap over validation rows'},
        'counts': 'expected counts when a capacity cut splits a tie group (tied_at_cut)',
        'note': 'The rule is chosen on validation rows.',
    }


def _predictions_meta(model: str, features: list) -> dict:
    return {'blob': 'predictions', 'format': 'gzip csv row_key,y,score', 'model': model,
            'partition': 'validation', 'n': 90, 'n_positive': 11, 'features': list(features)}


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
    from mlkit.study import case as c
    case = c.load_case(case_dir, verify_data=False)
    target = {'target': case.target_column, 'positive_label': case.positive_label}
    split = b.put('split', {**SPLIT_VALUE, 'stratified_on': case.target_column, 'n_rows': 300,
                            'partitions': {'train': {'n_rows': 210, 'n_positive': 25,
                                                     'rate': 25 / 210},
                                           'validation': {'n_rows': 90, 'n_positive': 11,
                                                          'rate': 11 / 90}},
                            'implementation': 'fixture', 'overlap': None},
                  params=dict(SPLIT_VALUE), partition='all', purpose='structural_inspection',
                  keys=b.all_keys)
    if upto == 'split':
        return b
    b.put('eda.target_rate', {'partition': 'train', **target, 'n_rows': 210, 'n_positive': 25,
                              'n_negative': 185, 'rate': 25 / 210},
          inputs={'results': {'split': split}})
    specials = [{'column': 'days_since_last_lapse', 'value': -1, 'n_rows': 122, 'n_positive': 14},
                {'column': 'last_lapse_reason', 'value': 'unknown', 'n_rows': 122,
                 'n_positive': 14}]
    b.put('eda.special_values', {
        'partition': 'train', 'n_rows': 210,
        'special_values': [{**sv, 'meaning': 'fixture', 'status': 'documented_fact',
                            'source': 'fixture', 'share': sv['n_rows'] / 210,
                            'rate': sv['n_positive'] / sv['n_rows']} for sv in specials],
        'co_occurrence': [{'a': {'column': specials[0]['column'], 'value': -1},
                           'b': {'column': specials[1]['column'], 'value': 'unknown'},
                           'n_a': 122, 'n_b': 122, 'n_both': 122, 'n_either': 122,
                           'same_rows': True}],
        'note': 'Counts on training rows.'}, inputs={'results': {'split': split}})
    if upto == 'train_eda':
        return b
    used = sorted(f for f, s in value.items() if s in ('available_at_prediction',
                                                       'uncertain_included'))
    vkeys = b.validation_keys
    ys = [1 if i % 8 == 0 and i < 88 else 0 for i in range(90)]     # 11 positive rows
    base = b.put('fit.baseline', {'model': 'constant_prior', 'train_rate': 0.119, 'n_train': 210,
                                  'n_train_positive': 25, 'features': [],
                                  'validation': {'n_rows': 90, 'n_positive': 11, 'roc_auc': 0.5,
                                                 'average_precision': 11 / 90},
                                  'predictions': _predictions_meta('constant_prior', [])},
                 params={'model': 'constant_prior'},
                 inputs={'results': {'split': split}}, partition='validation',
                 purpose='validation_model_evaluation', keys=vkeys,
                 blobs={'predictions': predictions_blob(vkeys, ys, [0.119] * 90)})
    fit = b.put('fit.logistic', {'model': 'logistic', 'features': used,
                                 'special_value_indicators': [], 'n_train': 210,
                                 'n_train_positive': 25, 'n_terms': len(used),
                                 'validation': {'n_rows': 90, 'n_positive': 11, 'roc_auc': 0.714,
                                                'average_precision': 0.31},
                                 'predictions': _predictions_meta('logistic', used)},
                params={'model': 'logistic'},
                inputs={'results': {'split': split}, 'features': used}, partition='validation',
                purpose='validation_model_evaluation', keys=vkeys,
                blobs={'predictions': predictions_blob(vkeys, ys,
                                                       [round(0.05 + (i % 17) / 20, 3)
                                                        for i in range(90)])})
    if upto == 'models':
        return b
    b.put('policy.evaluation', policy_values(fit, base),
          params={'rules': ['capacity:20', 'threshold:0.3'],
                  'models': ['fit.baseline', 'fit.logistic'], 'reference': 'fit.baseline'},
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
