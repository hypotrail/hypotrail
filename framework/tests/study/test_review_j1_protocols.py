"""Independent contract oracles for reliability-roadmap J1."""
import pytest

from mlkit.study import evaluation_plan as ep
from mlkit.study.errors import StudyError


def future_plan(**kwargs):
    keys = [f'L{i}' for i in range(1, 13)]
    return ep.build(keys, {'method': 'forward_chaining', 'folds': 2, 'gap': 0},
                    prediction_order=list(range(1, 13)),
                    outcome_available_order=list(range(3, 15)), **kwargs)


def test_j1_a01_forward_memberships_are_exact():
    plan = future_plan()
    assert plan['folds'][0]['validation_keys'] == [f'L{i}' for i in range(5, 9)]
    assert plan['folds'][0]['train_keys'] == ['L1', 'L2']
    assert plan['folds'][1]['validation_keys'] == [f'L{i}' for i in range(9, 13)]
    assert plan['folds'][1]['train_keys'] == [f'L{i}' for i in range(1, 7)]
    assert plan['unscored_keys'] == [f'L{i}' for i in range(1, 5)]


def test_j1_a02_equal_outcome_time_is_excluded():
    plan = future_plan()
    assert 'L3' not in plan['folds'][0]['train_keys']  # outcome tick 5 == window start
    assert 'L3' in plan['folds'][0]['excluded_train_keys']


def test_j1_a03_prediction_ties_never_split():
    keys = [f'L{i}' for i in range(1, 13)]
    ticks = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    plan = ep.build(keys, {'method': 'ordered_retrospective', 'folds': 2, 'gap': 0},
                    prediction_order=ticks)
    memberships = [{ticks[int(k[1:]) - 1] for k in f['validation_keys']}
                   for f in plan['folds']]
    assert memberships[0].isdisjoint(memberships[1])


def test_j1_a04_overlap_group_is_purged_without_moving_validation():
    groups = ['a', 'b', 'c', 'x', 'x', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
    plan = future_plan(groups=groups, group_goal='unseen_groups')
    assert 'L4' in plan['folds'][0]['excluded_train_keys']
    assert 'L5' in plan['folds'][0]['validation_keys']


def test_j1_a05_entity_and_duplicate_links_are_transitive():
    keys = [f'L{i}' for i in range(1, 9)]
    plan = ep.build(keys, {'method': 'group_disjoint', 'folds': 2, 'seed': 1},
                    strata=[0, 1, 0, 1, 0, 1, 0, 1],
                    groups=['a', 'a', 'b', 'c', 'd', 'e', 'f', 'g'],
                    duplicate_groups=['u', 'v', 'v', 'w', 'x', 'y', 'z', 'q'])
    for fold in plan['folds']:
        assert ({'L1', 'L2', 'L3'} <= set(fold['train_keys']) or
                {'L1', 'L2', 'L3'} <= set(fold['validation_keys']))


def test_j1_a06_every_returned_key_is_within_outer_subset():
    plan = future_plan()
    outer = set(future_plan()['folds'][1]['train_keys'])
    inner = ep.build(sorted(outer), {'method': 'ordered_retrospective', 'folds': 2, 'gap': 0},
                     prediction_order={k: int(k[1:]) for k in outer})
    assert all(set(f['train_keys'] + f['validation_keys']) <= outer for f in inner['folds'])


def test_j1_a07_infeasible_inner_plan_never_falls_back_to_shuffle():
    with pytest.raises(StudyError) as err:
        ep.build(['L1', 'L2'], {'method': 'forward_chaining', 'folds': 3, 'gap': 0},
                 prediction_order=[1, 2], outcome_available_order=[1, 2])
    assert err.value.details['reason'] == 'too_few_distinct_times'


def test_j1_a10_warmup_is_provenance_not_scored_membership():
    plan = future_plan()
    scored = {k for fold in plan['folds'] for k in fold['validation_keys']}
    assert set(plan['unscored_keys']).isdisjoint(scored)
    assert scored | set(plan['unscored_keys']) == {f'L{i}' for i in range(1, 13)}


def test_plan_digest_is_canonical_and_changes_with_membership():
    assert ep.digest(future_plan()) == ep.digest(future_plan())
    changed = future_plan()
    changed['folds'][0]['train_keys'].pop()
    assert ep.digest(changed) != ep.digest(future_plan())
