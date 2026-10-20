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
    # the split as an evaluation scheme: the vocabulary, the spread (v0.3, WP-D: the
    # engine drafts the value; R15: the standard term)
    for phrase in ('the split, as **k-fold cross-validation**', '**out-of-fold predictions**',
                   '**fold spread**', '`cross_validation.spread`'):
        assert phrase in rule3, phrase
    # the variants, the junior's choice, the trials disclosed (ADR 0007 since v0.3)
    for phrase in ('**Variants and model families**', 'unless the junior wants another variant',
                   '**regularisation**', 'dropping one feature group', '(`trials` in the summary)',
                   '`model_variant`'):
        assert phrase in rule3, phrase
    # the diagnostics after the fits, before the variant pause, as development evidence
    diag = 'diag.binary' if task == 'binary' else 'diag.regression'
    for phrase in ('after the fits and their diagnostics, the **variant**',
                   f'When `next_action` names `{diag}`, run it', 'It is development evidence'):
        assert phrase in rule3, phrase
    assert ('**calibration**' in rule3) == (task == 'binary')
    assert '**final test opening** (rule 10)' in rule3
    # the opening ritual
    rule10 = _rule(text, 10)
    for phrase in ('**The opening ritual.**', 'nothing is stale or waiting for reconfirmation',
                   'it is opened once, for this configuration',
                   # v0.3 (WP-B, R27): adopted in the junior's words, a reason optional.
                   'ask whether they adopt the opening', 'run `diag.final_test`',
                   'give the final figures first, as **final evidence**',
                   '`final_test.changed_after`', '`excluded_prior_exposed`'):
        assert phrase in rule10, phrase
    assert 'The final-test opening is never delegated' in _rule(text, 4)
    assert 'A reason is optional' in _rule(text, 4)
    # the modes paragraph is kept
    assert '**Modes** (ADR 0005)' in text
    assert '`scenario_defaults.capacity_share`' in text or task == 'regression'
    # no new prohibitions
    assert len(re.findall(r'\bnever\b', text, re.I)) <= 16


@pytest.mark.parametrize('task', ['binary', 'regression'])
def test_the_skill_carries_the_v0_2b_pedagogy(task):
    """v0.3 (WP-D): the v0.2b rules live in CLAUDE.md only; the skill keeps the reading of
    the evidence (selection optimism, development against final evidence)."""
    skill = _text(SKILL, task)
    for phrase in ('the more trials, the more', 'Development evidence and final evidence are '
                   'never mixed in one sentence', 'standard words: training folds, validation '
                   'fold, out-of-fold predictions', 'a fold spread is not a confidence interval'):
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
