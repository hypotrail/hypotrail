"""Post-v0.1 fixes D4, D8, and D10 (``docs/acceptance/runs/
claude-code-2026-10-18-p-fixes.md``; ``docs/specs/CLI-CONTRACT.md`` §3, §4, §8).

* D4: the small-data thresholds are inclusive (at most 30 validation rows, at most 5
  positive rows), and ``preview policy`` carries the G.12 warnings of its rules.
* D8: ``check`` traces a count of the study's own structure ("the seven columns we kept")
  to the view when it matches, and only before a structural noun.
* D10: a binary recap cites the headline policy result (precision and recall at one
  evaluated rule, with the result id prefix), and stays five flat lines that ``check``
  finds clean.

Studies live in ``tmp_path``.
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / 'deliverables'))

import phase3_study as fx  # noqa: E402
from phase3_study import full_study, full_study_template  # noqa: E402,F401
from mlkit.study import cli, cmd_check, cmd_preview, read, view, wordnum  # noqa: E402


def _run(*argv, expect=0):
    outcome = cli.run([str(a) for a in argv])
    json.dumps(outcome.payload)
    if expect is not None:
        assert outcome.exit_code == expect, outcome.payload
    return outcome.payload


def _split(n, positives):
    return {'partitions': {'validation': {'n_rows': n, 'n_positive': positives}}}


# --- D4 -----------------------------------------------------------------------------------

@pytest.mark.parametrize('n, positives, warned', [
    (30, 7, True),      # the 3a split: 30 rows is "small" at the boundary
    (31, 5, True),      # 5 positives is small at the boundary
    (31, 6, False),
    (18, 4, True),
    (200, 40, False)])
def test_small_validation_thresholds_are_inclusive(n, positives, warned):
    item = view.small_partition_warning(_split(n, positives), True)
    assert (item is not None) == warned
    if item:
        assert (item['n_rows'], item['n_positive']) == (n, positives)
        assert (item['min_rows'], item['min_positive']) == (view.SMALL_VALIDATION_ROWS,
                                                            view.SMALL_VALIDATION_POSITIVES)
    # A regression study has no positives: only the rows count.
    assert (view.small_partition_warning(_split(n, None), False) is not None) == (n <= 30)


def test_capacity_warning_names_the_capacities_that_select_every_row():
    assert view.capacity_warning(['capacity:100', 'capacity:10', 'threshold:0.3'], 30) == {
        'id': 'capacity_exceeds_validation', 'rules': ['capacity:100'], 'n_rows': 30,
        'text': 'A capacity at least as large as the 30 validation rows selects every row: its '
                'figures describe selecting everyone, not a ranking.'}
    assert view.capacity_warning(['capacity:30'], 30)['rules'] == ['capacity:30']
    assert view.capacity_warning(['capacity:29', 'threshold:0.1'], 30) is None


def test_preview_carries_the_capacity_warning(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models')
    out = _run('preview', 'policy', '--rule', 'capacity:100', '--rule', 'capacity:20',
               '--study', b.study)
    assert tuple(out) == cmd_preview.PAYLOAD_KEYS
    assert out['warnings'] == [view.capacity_warning(['capacity:100'], 90)]
    assert out['recorded'] is False
    out = _run('preview', 'policy', '--rule', 'capacity:20', '--study', b.study)
    assert out['warnings'] == []          # 90 validation rows, 11 positive: not small


# --- D8 -----------------------------------------------------------------------------------

WORDS = {v: w for w, v in wordnum.CARDINALS.items() if ' ' not in w and '-' not in w
         and w.isascii() and w not in ('une', 'un', 'cent', 'zero')}


def _view_without_term_count(study):
    """The view, with the fit's ``n_terms`` moved off the feature count, so a count of the
    features can only be traced as the study's structure."""
    v = copy.deepcopy(view.build(study))
    v['results']['fit.logistic']['values']['n_terms'] = 999
    return v


def _errors(v, text):
    findings, traced = cmd_check.check_text(v, text)
    return [f for f in findings if f['severity'] == 'error'], traced


def test_a_count_of_the_study_s_structure_is_traced_both_ways(full_study):
    v = _view_without_term_count(full_study)
    k = len(v['results']['fit.logistic']['values']['features'])
    counts = {item['value'] for item in cmd_check.Pool(v).structure}
    assert k in counts
    word = WORDS[k]
    other = WORDS[next(n for n in range(k + 1, 20) if n not in counts)]
    # The same count before a non-structural noun matches nothing: the pool has no k.
    errors, _ = _errors(v, f'We could make {word} calls.')
    assert [e['code'] for e in errors] == ['untraceable_number'], errors
    errors, _ = _errors(v, f'We could make {k} calls.')
    assert [e['code'] for e in errors] == ['untraceable_number'], errors
    # Before a structural noun, the count of the fit's features is traced as structure.
    for text in (f'It uses the {word} columns we kept.', f'The model uses {k} features.',
                 f'It uses the {word} kept columns.'):
        errors, traced = _errors(v, text)
        assert not errors, (text, errors)
        assert [t['source'] for t in traced] == ['structure'], traced
        assert traced[0]['value'] == k
    # A count that matches no structure is still flagged.
    errors, _ = _errors(v, f'It uses the {other} columns we kept.')
    assert [e['code'] for e in errors] == ['untraceable_number']
    # The plan: steps, pauses, decisions.
    free = [n for n in range(2, 60) if _errors(v, f'We could make {n} calls.')[0]]
    # A plan whose counts no other figure of this view matches (the real one has three
    # pauses and seven steps, both also figures of the fixture's results).
    steps, pauses = next((n, n - 1) for n in free if n - 1 in free)
    v['plan'] = [{'id': f's{i}', 'pause': i + 1 if i < pauses else None} for i in range(steps)]
    assert len({s['pause'] for s in v['plan'] if s['pause']}) == pauses
    errors, traced = _errors(v, f'The plan has {len(v["plan"])} steps and {pauses} pauses.')
    assert not errors and [t['id'] for t in traced] == ['plan.steps', 'plan.pauses']
    wrong = next(n for n in free if n not in (pauses, len(v['plan']), len(v['decisions'])))
    assert [e['code'] for e in _errors(v, f'The plan has {wrong} pauses.')[0]] == \
        ['untraceable_number']


def test_feature_availability_counts_are_structure(full_study):
    v = _view_without_term_count(full_study)
    # An availability decision whose size no other figure of this view matches.
    free = [n for n in range(2, 20) if _errors(v, f'We could make {n} calls.')[0]
            and n != len(v['results']['fit.logistic']['values']['features'])]
    total = free[-1]
    v['decisions']['feature_availability']['value'] = {
        f'f{i}': 'available_at_prediction' if i else 'not_available' for i in range(total)}
    errors, traced = _errors(v, f'The case lists {WORDS[total]} candidate variables.')
    assert not errors, errors
    assert [t['id'] for t in traced] == ['feature_availability.decision.all']
    assert [e['code'] for e in _errors(v, f'The case lists {WORDS[total]} candidate calls.')[0]] \
        == ['untraceable_number']


# --- D10 ----------------------------------------------------------------------------------

def _check_recap(study, recap):
    v = view.build(study)
    for line in recap:
        findings, _ = cmd_check.check_text(v, line)
        assert not [f for f in findings if f['severity'] == 'error'], (line, findings)


def test_binary_recap_cites_the_adopted_policy_result(full_study):
    summary = _run('status', '--summary', '--study', full_study)
    recap = summary['recap']
    assert len(recap) == 5 and all('\n' not in line for line in recap)
    rid = summary['results']['policy.evaluation']['result_id'][:8]
    decided = recap[1]
    m = re.search(r'policy capacity:20 \(the logistic model at capacity:20 on the 90 validation '
                  r'rows: precision (\d+\.\d)%, recall (\d+\.\d)%, result ([0-9a-f]{8})\)', decided)
    assert m, decided
    model = read.open(full_study).result(summary['results']['policy.evaluation']['result_id'])
    values = model['output']['values']['rules']['capacity:20']['models']['fit.logistic']
    assert m.group(1) == f'{100 * values["precision"]:.1f}'
    assert m.group(2) == f'{100 * values["recall"]:.1f}'
    assert m.group(3) == rid
    assert 'latest policy evaluation' not in recap[2]
    _check_recap(full_study, recap)


def test_binary_recap_gives_the_latest_evaluation_before_adoption(tmp_path, synthetic_case_dir):
    b = fx.build(tmp_path / 'study', synthetic_case_dir, upto='models')
    fx.put_policy_evaluation(b)
    summary = _run('status', '--summary', '--study', b.study)
    now = summary['recap'][2]
    assert 'latest policy evaluation: the logistic model at capacity:20 on the 90 validation ' \
           'rows: precision' in now, now
    assert summary['results']['policy.evaluation']['result_id'][:8] in now
    assert 'capacity:20 (' not in summary['recap'][1]
    _check_recap(b.study, summary['recap'])
    # Without an evaluation, the recap holds no result id.
    c = fx.build(tmp_path / 'other', synthetic_case_dir, upto='models')
    summary = _run('status', '--summary', '--study', c.study)
    assert 'policy evaluation' not in ' '.join(summary['recap'])
