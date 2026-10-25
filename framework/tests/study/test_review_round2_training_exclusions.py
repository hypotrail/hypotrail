"""Delayed labels never reach training (review 2026-10-24, round 2), synthetic studies only.

Under the review-v1 temporal profile with an outcome clock, ``partition.assign`` lists the
development rows whose outcome is available only at or after the final boundary
(``training_exclusions``): their labels were not known at the simulated decision time. These
tests check that no split, training-partition exploration, fit, fold, validation score,
final refit or predictor capture reads them; that the structural inspections (no target, no
split) still do; that the exclusion is visible in the evidence, the status and the report;
that results computed with those rows are not current and cannot be built upon; and that a
study without exclusions keeps exactly the identities it had (the attestation edges of
``mlkit.study.code_compat`` for the 818995c and 506180a engines are exact).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import hypotrail_runtime
from mlkit.study import (activities as act, cli, code_compat, eda, fit, junior, partition,
                         read, records as rec, registry, state as st, store as sto)

import flowkit as fk
from flowkit import Flow

REPO = Path(__file__).resolve().parents[3]
ACTIVITIES_FILE = 'framework/mlkit/study/activities.py'
ACTS = 'mlkit.study.activities'
# The digests of ``activities.py``: at 506180a (the base of library integration v1), at
# 818995c (the commit this fix starts from), and now.
BASE_COMMIT, PREVIOUS_COMMIT = '506180a', '818995c'
BASE = '3065f4d623f1ea2346c43ef27c0dd0f9a948c8eb007355c9cb625967b17cc9e1'
PREVIOUS = 'd6806ce3ff8f40c90eec7342c4ea2693a87c39a387a660dc1633364edd5c1f10'
CURRENT = 'b7c994d2e88edba8156c47756c0c43a496f0e04d4f7005bc1d9014ab639a48c1'
# The attested activity lists, written out (no wildcard, no derivation from the engine).
BASE_ATTESTED = ['split', 'eda.target_rate', 'eda.special_values', 'eda.rate_by',
                 'eda.target_summary', 'eda.mean_by', 'eda.distribution', 'eda.quality',
                 'eda.single_feature_signal', 'eda.correlation', 'fit.baseline',
                 'fit.logistic', 'fit.linear', 'fit.variant', 'policy.evaluation',
                 'policy.inspect', 'evaluate.regression', 'diag.binary', 'diag.regression',
                 'final_test.evaluation', 'diag.final_test']
# diagnostics.population is not attested: its Evidently statistics and snapshot are not
# reproducible bit for bit (code_compat_evidence.UNATTESTED).
PREVIOUS_ATTESTED = list(BASE_ATTESTED)
OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'
CRITERION = {'metric': 'precision_gain', 'min_points': 5, 'decision_rule': 'point_estimate',
             'selection': {'metric': 'precision', 'rule': 'share:0.2',
                           'scope': 'evaluation_window', 'batch_column': None,
                           'aggregation': 'pooled_counts'}}
VARIANT = {'variants': [{'kind': 'regularisation', 'strength': 'strong',
                         'question': 'Does a stronger penalty generalise better?',
                         'origin': 'planned', 'diagnostic_result_id': None}]}
# Exposure purposes of activities that must never read a delayed-label row.
TRAINING_PURPOSES = ('train_eda', 'train_fit', 'cross_validated_fit', 'out_of_fold_evaluation',
                     'out_of_fold_policy_selection', 'validation_model_evaluation',
                     'validation_policy_selection', 'development_diagnostics',
                     'policy_exploration')


# --- driving a review-v1 future study ---------------------------------------------------------

class ReviewFlow(Flow):
    def __init__(self, tmp_path: Path, name: str = 'study', *, outcome_delay: int = 2,
                 language: str = 'en'):
        paths = fk._module.make_review_case(tmp_path / f'case-{name}', future=True,
                                            outcome_delay=outcome_delay)
        super().__init__(tmp_path / name, paths['case'].parent, prefix=name[:3])
        self.case_file, self.language = paths['case'], language

    def init(self):
        return self.call('init', '--case', self.case_file, '--study', self.study,
                         '--reliability-profile', 'review-v1', '--lang', self.language)

    def pauses(self):
        self.decide('prediction_time',
                    'Predict using information available at the planted decision time')
        self.decide('feature_availability', fk.availability(self.case_dir))
        self.decide('split', st.b1_default_value(self.state(), 'split'))
        self.decide('success_criterion', CRITERION)

    def models(self):
        from mlkit.study import governance
        self.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
        self.run('fit.baseline')
        self.run('fit.logistic')
        # A variant declared after scores cites the current development diagnostic.
        self.run('diag.binary')
        self.decide('model_variant', VARIANT)
        self.run('fit.variant')

    def to_final(self):
        self.decide('model_choice', 'fit.logistic',
                    words='Yes, I choose that model because it ranks the rows best for us')
        self.call('run', 'policy.evaluate', '--rule', 'share:0.2', '--request-id', self.rid(),
                  '--expected-revision', self.rev(), '--study', self.study)
        self.run('diag.binary')
        self.decide('policy', 'share:0.2',
                    words='Yes, I adopt that rule because the desk can act on that share')
        self.run('diag.binary')
        self.run('predictor.capture')
        self.decide('final_test', st.b1_default_value(self.state(), 'final_test'), words=OPEN)
        self.run('diag.final_test')


class Spy:
    """Every row frame the engine fits or explores on, by the function that received it."""

    def __init__(self, monkeypatch):
        self.calls: list[tuple[str, list[str]]] = []
        for owner, name, position in ((fit, '_fit_predict', 1), (fit, 'compute_cv', 2),
                                      (fit, 'final_evaluation', 1), (eda, 'compute', 2),
                                      (hypotrail_runtime, 'fit_predictor', 2)):
            monkeypatch.setattr(owner, name, self._wrap(name, getattr(owner, name), position))

    def _wrap(self, name, function, position):
        def spied(*args, **kwargs):
            self.calls.append((name, [str(k) for k in args[position].index]))
            return function(*args, **kwargs)
        return spied

    def rows(self, name: str | None = None) -> set[str]:
        return {k for n, keys in self.calls if name in (None, n) for k in keys}


def _current(study: Path, slot: str) -> dict:
    s = read.open(study)
    return s.result(s.state['current'][slot])


def _blob_keys(study: Path, sha: str) -> set[str]:
    return set(rec.parse_row_keys(read.open(study).blob(sha)))


def _excluded(study: Path) -> set[str]:
    s = read.open(study)
    return set(rec.parse_row_keys(s.blob(s.state['partition']['training_exclusions']
                                         ['row_keys'])))


# --- the excluded rows never reach training, selection or validation --------------------------

@pytest.fixture(scope='module')
def delayed(tmp_path_factory, request):
    """A review-v1 future study whose two last development rows have a delayed label, taken to
    an opened final test, with every frame the engine fitted or explored on recorded."""
    monkeypatch = pytest.MonkeyPatch()
    request.addfinalizer(monkeypatch.undo)
    spy = Spy(monkeypatch)
    f = ReviewFlow(tmp_path_factory.mktemp('round2'))
    f.init()
    f.pauses()
    f.run('split')
    for activity in ('eda.target_rate', 'eda.special_values', 'eda.quality', 'eda.correlation'):
        f.run(activity)
    f.models()
    f.to_final()
    return f, spy


def test_the_partition_lists_the_delayed_label_rows(delayed):
    f, _ = delayed
    part = f.state()['partition']
    assert part['training_exclusions']['n_rows'] == 2
    assert part['training_exclusions']['reasons'] == [
        {'reason': partition.DELAYED_LABEL_REASON, 'count': 2}]
    # outcome = prediction + 2 and the final test starts at tick 241: ticks 239 and 240 (file
    # lines L240 and L241) are development rows whose outcome is known at 241 or later.
    assert part['order']['final_start'] == 241
    assert _excluded(f.study) == {'L240', 'L241'}
    assert _excluded(f.study) <= set(fk.partition_keys(f.study, 'development'))
    assert partition.training_exclusions(f.state()) == {
        'n_rows': 2, 'reasons': [{'reason': partition.DELAYED_LABEL_REASON, 'count': 2}],
        'row_keys': part['training_exclusions']['row_keys']}
    assert partition.delayed_label_rows(f.state()) == 2
    # The exempt activities are exactly the structural inspections (no target, no split).
    assert partition.EXCLUSION_EXEMPT_ACTIVITIES == act.STRUCTURAL_EDA


def test_no_fit_exploration_or_capture_reads_a_delayed_label_row(delayed):
    f, spy = delayed
    excluded = _excluded(f.study)
    development = set(fk.partition_keys(f.study, 'development'))
    eligible = development - excluded
    # Fits (every fold, the inner tuning, the final refit, the capture's engine parity fit)
    # and the runtime's capture fit.
    for name in ('_fit_predict', 'compute_cv', 'final_evaluation', 'fit_predictor'):
        assert spy.rows(name), name
        assert not spy.rows(name) & excluded, name
    # The final refit and the capture fit on every eligible development row, no more.
    final_refits = [keys for n, keys in spy.calls if n == 'final_evaluation']
    assert [set(k) for k in final_refits] == [eligible]
    assert [set(k) for n, k in spy.calls if n == 'fit_predictor'] == [eligible]
    # The explorations of the target read no excluded row; the structural quality check
    # (no target, no split) reads every development row.
    explored = [(keys, len(keys)) for n, keys in spy.calls if n == 'compute']
    assert any(set(keys) == development for keys, _ in explored)        # eda.quality
    assert sum(1 for keys, _ in explored if set(keys) == eligible) >= 2  # target looks


def test_the_split_and_every_result_leave_the_rows_out(delayed):
    f, _ = delayed
    excluded = _excluded(f.study)
    n_dev = len(fk.partition_keys(f.study, 'development'))
    record = partition.training_exclusions(f.state())
    split = _current(f.study, 'split')
    assert split['inputs']['training_exclusions'] == record
    assert split['n_rows'] == n_dev - 2
    assert split['output']['values']['n_development'] == n_dev - 2
    assert split['output']['values']['training_exclusions']['n_rows'] == 2
    assert split['output']['values']['training_exclusions']['note'] == act.DELAYED_LABELS_NOTE
    for blob in ('train', 'validation'):
        assert not _blob_keys(f.study, split['blobs'][blob]) & excluded
    plan = act.evaluation_membership(sto.StudyStore(f.study), split['result_id'])
    for fold in plan['folds']:
        for key in ('train_keys', 'validation_keys', 'excluded_train_keys'):
            assert not set(fold[key]) & excluded, (fold['id'], key)
    assert not set(plan['unscored_keys']) & excluded
    for slot in ('fit.baseline', 'fit.logistic', 'fit.variant'):
        entry = _current(f.study, slot)
        assert entry['inputs']['training_exclusions'] == record
        scored = set(act.read_predictions(sto.StudyStore(f.study), entry['result_id'])
                     ['row_keys'])
        assert scored and not scored & excluded, slot
    for slot in ('eda.target_rate', 'eda.special_values', 'policy.evaluation', 'diag.binary',
                 'predictor.capture', 'final_test.evaluation', 'diag.final_test'):
        assert _current(f.study, slot)['inputs']['training_exclusions'] == record, slot
    assert _current(f.study, 'eda.target_rate')['n_rows'] == n_dev - 2
    final = _current(f.study, 'final_test.evaluation')['output']['values']
    assert final['refit']['n_rows'] == n_dev - 2
    assert final['training_exclusions']['n_rows'] == 2
    assert _current(f.study, 'predictor.capture')['output']['values']['n_train'] == n_dev - 2
    # The structural inspections keep their identity and read every development row.
    for slot in ('eda.quality', 'eda.correlation'):
        entry = _current(f.study, slot)
        assert 'training_exclusions' not in entry['inputs'], slot
    assert _current(f.study, 'eda.quality')['output']['values']['n_rows'] == n_dev
    s = read.open(f.study)
    assert all(s.currency(rid)['current'] for rid in s.state['current'].values())


def test_the_exposure_of_training_activities_leaves_the_rows_out(delayed):
    f, _ = delayed
    excluded = _excluded(f.study)
    s = read.open(f.study)
    seen_by: dict[str, set] = {}
    for record in s.exposure_records():
        keys = set(rec.parse_row_keys(s.blob(record['row_keys'])))
        if keys & excluded:
            seen_by.setdefault(record['activity'], set()).add(record['purpose'])
        if record['purpose'] in TRAINING_PURPOSES:
            assert not keys & excluded, (record['activity'], record['purpose'])
    # Only the structure read at init and the structural inspections saw them.
    assert set(seen_by) <= {'init.structure', 'eda.quality', 'eda.correlation'}, seen_by
    assert seen_by['init.structure'] == {'structural_inspection'}
    assert all(p == {'structural_inspection'} for p in seen_by.values())


def test_the_exclusion_is_visible_in_status_evidence_and_report(delayed):
    f, _ = delayed
    view = f.view()
    [item] = [x for x in view['not_yet_defensible'] if x['id'] == 'delayed_labels_excluded']
    assert item['n_rows'] == 2 and item['clock'] == 'prediction_tick'
    assert item['final_start'] == 241
    assert item['development_rows'] == len(fk.partition_keys(f.study, 'development'))
    # The term first, then a contextual example in the study's own clock.
    text = item['junior_text']
    assert text.startswith('A delayed label is an outcome that becomes known only some time '
                           'after the prediction is made.')
    assert 'Here 2 development rows' in text and '(prediction_tick 241)' in text
    assert text.index('For example, a row predicted just before prediction_tick 241') \
        > text.index('Here 2 development rows')
    assert item['audience'] == 'junior'
    summary = cli.run(['status', '--summary', '--study', str(f.study)]).payload
    ids = [x['id'] for x in summary['not_yet_defensible']['top']] + \
        list(summary['not_yet_defensible']['more'])
    assert 'delayed_labels_excluded' in ids
    evidence = cli.run(['evidence', '--study', str(f.study)]).payload
    [split] = [r for r in evidence['results'] if r['slot'] == 'split']
    assert split['values']['training_exclusions']['n_rows'] == 2
    assert cli.run(['render', '--study', str(f.study)]).exit_code == 0
    html = (f.study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'data-nyd="delayed_labels_excluded"' in html
    assert 'A delayed label is an outcome' in html


def test_the_french_text_introduces_the_term_then_the_example(delayed):
    f, _ = delayed
    item = st.delayed_labels_limit(f.state())
    text = junior.limit_fr(item)
    assert text.startswith('Une étiquette tardive est un résultat connu seulement')
    assert 'Ici, 2 lignes de développement' in text and '(prediction_tick 241)' in text
    assert text.index('Par exemple') > text.index('Ici, 2 lignes')
    assert 'delayed_labels_excluded' in junior.LIMIT_IDS_FR


# --- results computed with the rows are not current, and are not built upon -------------------

def test_results_computed_with_delayed_labels_are_not_current(tmp_path, monkeypatch):
    """A study whose results were computed before the fix (simulated: the engine ignores the
    exclusions while they are computed) loses them, keeps its structural inspection, refuses
    to build on the old split, and recomputes it without the rows; what was seen stays seen."""
    f = ReviewFlow(tmp_path)
    f.init()
    f.pauses()
    with monkeypatch.context() as m:
        m.setattr(partition, 'training_exclusions', lambda state: None)
        f.run('split')
        f.run('eda.target_rate')
        f.run('eda.quality')
        old_split = _current(f.study, 'split')
        assert 'training_exclusions' not in old_split['inputs']
        assert _blob_keys(f.study, old_split['blobs']['train']) >= _excluded(f.study)
    s = read.open(f.study)
    for slot in ('split', 'eda.target_rate'):
        currency = s.currency(s.state['current'][slot])
        assert currency['current'] is False, slot
        assert currency['reason'].get('delayed_labels_included') is True, slot
        assert 'final boundary' in currency['reason']['reason']
    assert s.currency(s.state['current']['eda.quality'])['current'] is True
    exposed_before = {k for r in s.exposure_records() if r['purpose'] == 'train_eda'
                      for k in rec.parse_row_keys(s.blob(r['row_keys']))}
    assert exposed_before & _excluded(f.study)
    # Building on the old split is refused, with the result to recompute named.
    from mlkit.study import governance
    f.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    out = f.run('fit.logistic', expect=2)
    assert out['error']['code'] == 'precondition_missing'
    [missing] = out['error']['details']['missing']
    assert missing['requirement'] == 'computed_without_delayed_labels'
    assert missing['slot'] == 'split' and missing['result_id'] == old_split['result_id']
    # The split computed again leaves them out; the rows explored before stay exposed.
    f.run('split')
    new_split = _current(f.study, 'split')
    assert new_split['result_id'] != old_split['result_id']
    assert not _blob_keys(f.study, new_split['blobs']['train']) & _excluded(f.study)
    f.run('fit.logistic')
    s = read.open(f.study)
    assert s.currency(old_split['result_id'])['current'] is False
    assert s.currency(s.state['current']['fit.logistic'])['current'] is True
    exposed_after = {k for r in s.exposure_records() if r['purpose'] == 'train_eda'
                     for k in rec.parse_row_keys(s.blob(r['row_keys']))}
    assert exposed_before <= exposed_after


# --- without exclusions nothing changes -------------------------------------------------------

def _no_exclusion_flow(f: Flow):
    f.init()
    f.pauses()
    f.run('split')
    f.run('eda.target_rate' if st.task_of(f.state()) == 'binary' else 'eda.target_summary')
    from mlkit.study import governance
    if f.state()['decisions']['preprocessing']['status'] != 'confirmed':
        f.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    f.run('fit.logistic')


@pytest.mark.parametrize('kind', ['review_no_delay', 'legacy'])
def test_a_study_without_exclusions_keeps_its_identities(tmp_path, monkeypatch, kind):
    """No ``training_exclusions`` in any identity, every development row read, and the
    planned identities (input keys) equal to those of the engine with the exclusion code
    paths removed (``partition.training_exclusions`` forced to None)."""
    if kind == 'review_no_delay':
        f = ReviewFlow(tmp_path, outcome_delay=0)
    else:
        f = Flow(tmp_path / 'study', fk.make_case(tmp_path / 'case', n_rows=400)['case'].parent)
    _no_exclusion_flow(f)
    state = f.state()
    if kind == 'review_no_delay':
        assert state['partition']['training_exclusions']['n_rows'] == 0
    assert partition.training_exclusions(state) is None
    assert not any(x['id'] == 'delayed_labels_excluded' for x in f.view()['not_yet_defensible'])
    n_dev = len(fk.partition_keys(f.study, 'development'))
    store = sto.StudyStore(f.study)
    for slot in ('split', 'fit.logistic'):
        entry = _current(f.study, slot)
        assert 'training_exclusions' not in entry['inputs']
        assert 'training_exclusions' not in entry['output']['values']
        replanned = act.plan(store, state, entry['activity'], entry.get('options') or {})
        assert replanned['input_key'] == entry['input_key'], slot
        with monkeypatch.context() as m:
            m.setattr(partition, 'training_exclusions', lambda s: None)
            assert act.plan(store, state, entry['activity'], {})['input_key'] \
                == entry['input_key'], slot
    assert _current(f.study, 'split')['n_rows'] == n_dev
    case, dataset = act.load(act.plan(store, state, 'fit.logistic', {}), store)
    assert len(dataset.frame) == n_dev


# --- the attestation edges are exact ----------------------------------------------------------

def _edges(source: str) -> list[dict]:
    return [r for r in code_compat.ATTESTATIONS if r['module'] == ACTS
            and r['from_sha256'] == source and r['to_sha256'] == CURRENT]


def test_the_round2_edges_target_the_current_bytes():
    now = hashlib.sha256((REPO / ACTIVITIES_FILE).read_bytes()).hexdigest()
    if now != CURRENT:
        # Review round 5 (R5E-2) changed activities.py again: exact edges from the bytes of
        # this round (and from the 818995c ones) to the current bytes must cover every
        # activity these edges cover (test_review_round5_engine.py checks their evidence).
        for source in (CURRENT, PREVIOUS):
            covered = {a for r in code_compat.ATTESTATIONS if r['module'] == ACTS
                       and r['from_sha256'] == source and r['to_sha256'] == now
                       for a in r['activities']}
            assert covered == set(BASE_ATTESTED), (
                'activities.py changed again: re-run code_compat_evidence.py against the new '
                'bytes and, only if it matches, add new edges.')
    assert read._module_path(ACTS).read_bytes() == (REPO / ACTIVITIES_FILE).read_bytes()
    assert code_compat.integrity()
    [base] = _edges(BASE)
    [previous] = _edges(PREVIOUS)
    assert base['activities'] == BASE_ATTESTED
    assert previous['activities'] == PREVIOUS_ATTESTED
    for record in (base, previous):
        assert len(set(record['activities'])) == len(record['activities'])
        assert all(a in act.ACTIVITIES and ACTS in act.MODULES[a] for a in record['activities'])
        # The capture embeds the code fingerprint in its predictor, the population profile
        # is not reproducible bit for bit: never attested.
        assert act.CAPTURE not in record['activities']
        assert act.POPULATION not in record['activities']
        assert 'framework/tests/study/test_review_round2_training_exclusions.py' \
            in record['evidence']
        assert 'framework/tests/study/code_compat_evidence.py' in record['evidence']
    # Every activity of either engine but the capture and the population profile.
    assert set(BASE_ATTESTED) == set(act.ACTIVITIES) - {act.CAPTURE, act.POPULATION}
    assert set(PREVIOUS_ATTESTED) == set(BASE_ATTESTED)


def test_the_round2_edges_start_at_the_recorded_bytes():
    for commit, digest in ((BASE_COMMIT, BASE), (PREVIOUS_COMMIT, PREVIOUS)):
        probe = subprocess.run(['git', '-C', str(REPO), 'cat-file', '-e', f'{commit}^{{commit}}'],
                               capture_output=True)
        if probe.returncode != 0:
            pytest.skip(f'{commit} is not in this clone')
        blob = subprocess.run(['git', '-C', str(REPO), 'show', f'{commit}:{ACTIVITIES_FILE}'],
                              capture_output=True, check=True).stdout
        assert hashlib.sha256(blob).hexdigest() == digest, commit


def _entry(activity: str, digest: str) -> dict:
    modules = dict(registry.code_fingerprint(list(act.MODULES[activity]))['modules'])
    modules[ACTS] = digest
    return {'activity': activity, 'code': {'modules': modules}}


def test_the_round2_edges_are_exact_directed_and_scoped(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200)['case'].parent
    Flow(tmp_path / 'study', case_dir).init()
    study = read.open(tmp_path / 'study')
    for activity in PREVIOUS_ATTESTED:
        assert study.code_changed(_entry(activity, PREVIOUS)) == [], activity
    for activity in BASE_ATTESTED:
        assert study.code_changed(_entry(activity, BASE)) == [], activity
    assert study.code_changed(_entry(act.CAPTURE, PREVIOUS)) == [ACTS]
    assert study.code_changed(_entry(act.POPULATION, PREVIOUS)) == [ACTS]
    assert study.code_changed(_entry(act.POPULATION, BASE)) == [ACTS]
    assert not code_compat.equivalent(ACTS, CURRENT, PREVIOUS, 'split')
    assert not code_compat.equivalent(ACTS, PREVIOUS, CURRENT, act.CAPTURE)
    assert not code_compat.equivalent(ACTS, PREVIOUS, CURRENT, None)
    # An unknown digest stays unknown (no transitivity, no wildcard).
    assert study.code_changed(_entry('split', 'e' * 64)) == [ACTS]


@pytest.mark.skipif(not (os.environ.get('HYPOTRAIL_COMPAT_OLD_PYTHON')
                         and os.environ.get('HYPOTRAIL_COMPAT_OLD_ROOT')),
                    reason='needs a 818995c (or 506180a) checkout and a Python with its '
                           'dependencies (HYPOTRAIL_COMPAT_OLD_PYTHON, HYPOTRAIL_COMPAT_OLD_ROOT)')
def test_byte_comparison_with_the_previous_engine(tmp_path):
    """The evidence itself: the same flows on both engines, then leaf recomputation."""
    script = Path(__file__).with_name('code_compat_evidence.py')
    proc = subprocess.run([sys.executable, str(script), 'evidence',
                           os.environ['HYPOTRAIL_COMPAT_OLD_PYTHON'],
                           os.environ['HYPOTRAIL_COMPAT_OLD_ROOT'], str(tmp_path / 'work')],
                          capture_output=True, text=True, timeout=3600)
    assert proc.returncode == 0, proc.stdout[-4000:] + proc.stderr[-4000:]
    assert 'DIFFERENT' not in proc.stdout and proc.stdout.rstrip().endswith('MATCH')


def test_the_capture_names_the_rows_it_was_fitted_on(tmp_path):
    """The capture's training scope names the rows of its fit: the development blob without
    exclusions, the blob id of the eligible keys when delayed-label rows were left out.
    Round 3 (review A): both are the same digest scheme, the SHA-256 of the canonical row-keys
    blob (sorted, unique, one key per newline-terminated line), the id ``store.put_blob``
    gives the development blob; the excluded case no longer joins the keys without a final
    newline."""
    import hashlib
    from mlkit.contracts import capture
    from mlkit.study import records as rec
    keys = ['L3', 'L1', 'L2', 'L1']
    plain = {'development': {'row_keys': 'blob-of-every-development-row'}}
    assert capture._membership(plain, keys) == 'blob-of-every-development-row'
    excluded = {**plain, 'training_exclusions': {'row_keys': 'blob', 'n_rows': 2}}
    blob = b'L1\nL2\nL3\n'
    assert rec.row_keys_bytes(keys) == blob
    assert capture._membership(excluded, keys) == hashlib.sha256(blob).hexdigest()
    assert capture._membership(excluded, keys) != hashlib.sha256(
        '\n'.join(sorted(set(keys))).encode()).hexdigest()
    # The id the study's blob store gives the same keys.
    from mlkit.study.store import StudyStore
    store = StudyStore(tmp_path / 'study')
    (store.home / 'blobs').mkdir(parents=True, exist_ok=True)
    assert store.put_blob(rec.row_keys_bytes(keys)) == capture._membership(excluded, keys)
