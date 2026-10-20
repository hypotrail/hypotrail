"""WP-B6a: the agent instructions for v0.2b (CLAUDE.md template and skill).

The split pause proposes the engine's cross-validation, with the fold-spread vocabulary; one
analytical variant is offered and chosen by the junior, with the trial count disclosed;
the diagnostics are run after the fits and before the choice, as development evidence; the
final test is opened in a ritual (confirmed choice, nothing stale, the junior's words and
reason, opened once, then ``diag.final_test``; later changes labelled). Each phrase names a
real activity, key or glossary term of the engine; the "never" count stays capped.
"""
from __future__ import annotations

import re

import pytest

from mlkit.study import activities as act, agent_files as af, fit, partition, texts

from test_agent_files import Flat, _rule

SKILL = 'dot-claude/skills/hypotrail-study/SKILL.md'


def _text(rel: str, task: str) -> Flat:
    return Flat(af.select_task((af.SOURCE / rel).read_text(), task))


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_instructions_carry_the_v0_2b_workflow(task):
    text = _text('CLAUDE.md.in', task)
    rule3 = _rule(text, 3)
    # the split as an evaluation scheme: the engine's draft, the vocabulary, the spread
    for phrase in ('**The split as an evaluation scheme**', '`next_action.default_value`',
                   '**cross-validation**', '**out-of-fold predictions**', '**fold spread**',
                   '`cross_validation.spread`'):
        assert phrase in rule3, phrase
    # one analytical variant, the junior's choice, the trials disclosed
    for phrase in ('**The variant**', 'let the junior choose it', '**regularisation**',
                   'dropping one feature group', '(`trials` in the summary)', 'run fit.variant'):
        assert phrase in rule3, phrase
    # the diagnostics after the fits, before the choice, as development evidence
    diag = 'diag.binary' if task == 'binary' else 'diag.regression'
    for phrase in ('**Diagnostics** (v0.2b). After the fits and the variant, before proposing',
                   f'run `{diag}` and read it with the junior', 'It is development evidence'):
        assert phrase in rule3, phrase
    assert ('**calibration**' in rule3) == (task == 'binary')
    assert '**final test opening** (rule 10)' in rule3
    # the opening ritual
    rule10 = _rule(text, 10)
    for phrase in ('**The opening ritual.**', 'nothing is stale or waiting for reconfirmation',
                   'is opened once, for this configuration',
                   # v0.3 (WP-B, R27): adopted in the junior's words, a reason optional.
                   'whether they adopt the opening', 'a reason is optional',
                   'a delegation is refused', 'run `diag.final_test`',
                   'read the final figures first, as **final evidence**',
                   '`final_test.changed_after`', '`excluded_prior_exposed`'):
        assert phrase in rule10, phrase
    # the modes paragraph is kept; under cross-validation "validation rows" are re-read
    assert '**Modes** (ADR 0005' in text
    assert '"the out-of-fold predictions of the development rows"' in text
    assert '`scenario_defaults` in `status --summary`' in text or task == 'regression'
    # no new prohibitions
    assert len(re.findall(r'\bnever\b', text, re.I)) <= 16


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_skill_carries_the_v0_2b_pedagogy(task):
    skill = _text(SKILL, task)
    for phrase in ('## Cross-validation, the variant, the diagnostics and the final test (v0.2b)',
                   '**out-of-fold predictions**', '**fold spread**', 'the junior chooses',
                   '(`trials`)', 'before the choice', 'run `diag.final_test`',
                   '"after the final test"', 'the final test\'s figures come first, as final '
                   'evidence'):
        assert phrase in skill, phrase
    assert 'in a later version' not in skill               # the opening exists now
    assert len(re.findall(r'\bnever\b', skill, re.I)) <= 7


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_named_terms_and_keys_exist(task):
    for term in ('cross_validation', 'out_of_fold', 'fold_spread', 'regularisation'):
        entry = texts.glossary(term, task)
        assert entry and entry['term'] and entry['definition'], term
        assert not re.search(r'\d', entry['definition']), term
    assert {'min', 'max'} <= set(fit.SPREAD_KEYS)
    for activity in ('fit.variant', 'diag.binary', 'diag.regression', 'diag.final_test'):
        assert activity in act.MODULES, activity
    assert 'excluded_prior_exposed' in partition.STATUS_VIEW_KEYS
    assert 'changed_after' in partition.STATUS_VIEW_KEYS
