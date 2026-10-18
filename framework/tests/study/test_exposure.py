"""Append-only data exposure keyed by row key (plan WP1.3, §3.5)."""
from __future__ import annotations

import pytest

from mlkit.study import exposure, records as rec
from mlkit.study.errors import StudyError

TRAIN = [f'L{i}' for i in range(2, 12)]
VALID = [f'L{i}' for i in range(12, 17)]


def _record(store, purpose, partition, keys, columns=('a', 'b'), result_id='r1'):
    return exposure.record(store, exposure_id=exposure.new_exposure_id(), revision=3,
                           activity='eda.target_rate', result_id=result_id, purpose=purpose,
                           partition=partition, row_keys=keys, dataset_sha256='d' * 64,
                           columns=columns)


def test_record_stores_row_keys_blob_and_summary_counts_distinct_rows(new_study):
    a = _record(new_study, 'train_eda', 'train', TRAIN)
    _record(new_study, 'train_eda', 'train', TRAIN[:4])
    _record(new_study, 'validation_policy_selection', 'validation', VALID)
    assert set(a) == set(rec.EXPOSURE_KEYS)
    assert a['n_rows'] == len(TRAIN)
    assert exposure.rows(new_study, a) == sorted(TRAIN)
    summary = exposure.summary(new_study, new_study.load_state())
    assert summary['records'] == 3
    assert summary['rows_exposed'] == len(TRAIN) + len(VALID)
    assert summary['by_purpose'] == {'train_eda': len(TRAIN),
                                     'validation_policy_selection': len(VALID)}
    assert summary['by_partition']['validation'] == {'validation_policy_selection': len(VALID)}
    assert summary['validation_rows_used_for_selection'] == len(VALID)


def test_prior_exposure_is_surfaced_not_subtracted(new_study):
    state = new_study.load_state()
    state['prior_exposure'] = [{'value': 'published', 'status': 'observed', 'source': 'x'}]
    summary = exposure.summary(new_study, state)
    assert summary['rows_exposed'] == 0 and summary['prior_exposure'] == state['prior_exposure']


def test_exposure_is_retained_after_a_split_change_and_overlap_is_reported(new_study):
    _record(new_study, 'train_eda', 'train', TRAIN)
    _record(new_study, 'validation_model_evaluation', 'validation', VALID)
    before = exposure.records(new_study)
    old_split = {'train': TRAIN, 'validation': VALID}
    new_split = {'train': TRAIN[3:] + VALID[:2], 'validation': TRAIN[:3] + VALID[2:]}
    report = exposure.overlap(old_split, new_split, store=new_study)
    assert exposure.records(new_study) == before            # nothing is removed
    assert report['moved'] == 5
    assert report['transitions']['validation'] == {'train': 3, 'validation': 3}
    # The new validation rows include three rows already explored in training EDA.
    assert report['previously_exposed']['validation'] == {'train_eda': 3,
                                                           'validation_model_evaluation': 3}
    assert report['previously_exposed']['train'] == {'train_eda': 7,
                                                      'validation_model_evaluation': 2}
    assert 'not make previously explored rows unseen' in report['note']
    pure = exposure.overlap(old_split, new_split)
    assert pure['previously_exposed'] == {'train': {}, 'validation': {}}


def test_exposure_is_retained_after_a_column_addition(new_study):
    _record(new_study, 'train_eda', 'train', TRAIN, columns=('a',))
    _record(new_study, 'train_eda', 'train', TRAIN, columns=('a', 'a_is_special'))
    summary = exposure.summary(new_study)
    assert summary['records'] == 2 and summary['rows_exposed'] == len(TRAIN)
    assert [r['columns'] for r in exposure.records(new_study)] == [['a'], ['a', 'a_is_special']]


@pytest.mark.parametrize('field, value', [('purpose', 'curiosity'), ('partition', 'test')])
def test_invalid_purpose_or_partition_is_refused(new_study, field, value):
    kwargs = dict(purpose='train_eda', partition='train')
    kwargs[field] = value
    with pytest.raises(StudyError) as err:
        _record(new_study, kwargs['purpose'], kwargs['partition'], TRAIN)
    assert err.value.code == 'invalid_exposure'
    assert exposure.records(new_study) == []


def test_exposure_ids_are_unique_and_records_append_only(new_study):
    eid = exposure.new_exposure_id()
    exposure.record(new_study, exposure_id=eid, revision=1, activity='x', result_id=None,
                    purpose='structural_inspection', partition='all', row_keys=TRAIN,
                    dataset_sha256='d' * 64, columns=[])
    with pytest.raises(StudyError):
        exposure.record(new_study, exposure_id=eid, revision=1, activity='x', result_id=None,
                        purpose='structural_inspection', partition='all', row_keys=TRAIN,
                        dataset_sha256='d' * 64, columns=[])
    assert len(exposure.records(new_study)) == 1
