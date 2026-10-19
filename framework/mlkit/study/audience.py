"""Who a message of the engine is written for (v0.2a, WP-A1; CLI-CONTRACT §3.3).

Every sentence the engine emits for a surface carries ``audience``:

* ``junior``: the text may be shown to the junior as it is. It speaks to them in the
  second person or neutrally, and names no command, flag, decision id, or field;
* ``agent``: the text instructs the assistant ("Show the restatement and record the user's
  own words") or describes the junior in the third person. A surface never shows it to the
  junior; the junior variant next to it (``junior_message`` or ``junior_text``) is written
  for them.

The functions here are pure and additive: they never change an existing key, they add
``audience`` and the junior variant. Free of pandas, numpy, and scikit-learn.
"""
from __future__ import annotations

from typing import Mapping

JUNIOR, AGENT = 'junior', 'agent'
AUDIENCES = (JUNIOR, AGENT)

# Decisions in words, for the junior (a regression study's model choice included).
DECISION_WORDS = {'prediction_time': 'the prediction moment',
                  'feature_availability': 'the feature availability', 'split': 'the split',
                  'policy': 'the decision policy', 'model_choice': 'the model choice',
                  'conclusion': 'the conclusion',
                  # v0.2a (WP-A4)
                  'success_criterion': 'the success criterion',
                  'preprocessing': 'the preparation of the variables',
                  # v0.2b (WP-B1)
                  'model_variant': 'the variant to compare',
                  'final_test': 'the opening of the final test'}
# Plan steps in words (the steps without a decision of their own).
STEP_WORDS = {'train_eda': 'the exploration of the training rows', 'models': 'the model fits',
              'discover_data': 'the discovery of the data'}


def decision_words(decision_id) -> str:
    return DECISION_WORDS.get(decision_id) or STEP_WORDS.get(decision_id) \
        or ' '.join(str(decision_id).split('_'))


# v0.2a (WP-A7): activities in words, for the junior (an activity id is a raw token). A
# regression study never runs ``policy.*``, so no word here names a decision rule there.
ACTIVITY_WORDS = {'split': 'the split', 'eda.target_rate': 'the outcome rate',
                  'eda.target_summary': 'the target summary',
                  'eda.special_values': 'the special-value check',
                  'eda.rate_by': 'an outcome rate by group',
                  'eda.mean_by': 'a target mean by group',
                  'eda.distribution': 'the distribution of a column',
                  'eda.quality': 'the data quality check',
                  'eda.single_feature_signal': 'the single-feature signal check',
                  'fit.baseline': 'the baseline model', 'fit.logistic': 'the logistic model',
                  'fit.linear': 'the linear model', 'policy.evaluate': 'the policy evaluation',
                  'policy.evaluation': 'the policy evaluation',
                  'evaluate.regression': 'the model comparison',
                  # v0.2b (WP-B1)
                  'fit.variant': 'the variant model',
                  'final_test.evaluation': 'the final test evaluation'}


def activity_words(activity) -> str:
    """An activity id (or a slot, ``eda.rate_by:job``) in words: "an outcome rate by group
    (job)"; an unknown activity reads "an analysis"."""
    base, sep, column = str(activity or '').partition(':')
    words = ACTIVITY_WORDS.get(base, 'an analysis')
    return f'{words} ({column})' if sep and column else words


# Recorded values in words (v0.2a, WP-A7): a rule, a model slot, a verdict. The numbers are
# the value's own; nothing is computed.
MODEL_WORDS = {'fit.linear': 'the linear model', 'fit.baseline': 'the mean baseline',
               'fit.logistic': 'the logistic model', 'fit.variant': 'the variant'}
VERDICT_WORDS = {'adopt_policy': 'adopt the policy', 'adopt_model': 'adopt the chosen model',
                 'keep_baseline': 'keep the baseline', 'inconclusive': 'inconclusive'}


def rule_words(rule) -> str:
    """``capacity:100`` as "call the top 100 by score", ``threshold:0.2`` as "call everyone
    scored 0.2 or more"; anything else as it is."""
    kind, _, k = str(rule).partition(':')
    if kind == 'capacity' and k:
        return f'call the top {k} by score'
    if kind == 'threshold' and k:
        return f'call everyone scored {k} or more'
    if kind == 'share' and k:
        return f'call the top {share_percent(k)} by score'
    return str(rule)


def share_percent(p) -> str:
    """``0.1`` (or ``"0.1"``) as ``10%``, ``0.125`` as ``12.5%``."""
    pct = 100 * float(p)
    return f'{pct:.0f}%' if abs(pct - round(pct)) < 1e-9 else f'{pct:g}%'


def policy_words(value) -> str:
    """A policy value in words (WP-B1: with the model its rule applies to when it is the
    variant): "call the top 100 by score, with the variant"."""
    rule, sep, model = str(value).partition('@')
    words = rule_words(rule)
    return f'{words}, with {model_words(model)}' if sep and model else words


def variant_words(value) -> str:
    """A ``model_variant`` value in words (WP-B1)."""
    if not isinstance(value, Mapping):
        return str(value)
    if value.get('kind') == 'regularisation':
        return {'weak': 'weaker regularisation', 'strong': 'stronger regularisation'}.get(
            value.get('strength'), 'another regularisation')
    if value.get('kind') == 'drop_group':
        return f'without the group "{value.get("group")}"'
    return str(value.get('kind'))


def model_words(slot) -> str:
    return MODEL_WORDS.get(str(slot), ' '.join(str(slot).replace('fit.', '').split('_')))


def join(words) -> str:
    words = list(words)
    if not words:
        return ''
    return words[0] if len(words) == 1 else ', '.join(words[:-1]) + ' and ' + words[-1]


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


# --- next_action -------------------------------------------------------------------------

def _junior_next(action: Mapping) -> tuple[str, str]:
    """``(audience of message, junior_message)`` of one ``next_action``."""
    kind = action.get('kind')
    message = str(action.get('message') or '')
    if kind == 'outcome_unknown':
        # WP-A7: the run is named in words (the activity id is a raw token).
        return AGENT, (f'A run of {activity_words(action.get("activity"))} stopped before it '
                       'finished, and its outcome is unknown. It is not in progress and does '
                       'not restart by itself; you will be asked before it is recorded as '
                       'interrupted.')
    if kind == 'acknowledge_interruption':
        named = (f'A run of {activity_words(action["activity"])}' if action.get('activity')
                 else 'A run')
        return AGENT, (f'{named} was interrupted and its outcome is unknown. It does not '
                       'restart by itself; you will be asked before it is recorded as '
                       'interrupted.')
    if kind == 'reconfirm':
        return AGENT, (f'Your answer on {decision_words(action.get("decision"))} must be '
                       'confirmed again: something it depends on changed after you confirmed '
                       'it.')
    if kind == 'await_user_words':
        return AGENT, (f'A proposal on {decision_words(action.get("decision"))} is waiting for '
                       'your answer. Read its restatement and reply in your own words; a bare '
                       '"ok" does not decide.')
    if kind == 'blocked':
        needed = join(decision_words(r) for r in action.get('requires') or [])
        return AGENT, (f'This step waits for earlier steps: {needed}.' if needed
                       else 'This step waits for an earlier step.')
    if kind == 'show_data_card':
        # WP-A4 (R2): step 0, informational.
        return AGENT, ('First, look at the data with the assistant: what one row describes, '
                       'the columns and what each one means, and five example rows. Nothing '
                       'is decided at this step.')
    if kind in ('propose', 'run'):
        # The step's question, written for the junior (state.STEPS).
        return JUNIOR, message
    if kind == 'done':
        return AGENT, ('Every step of the plan is done. Before relying on the conclusion, read '
                       'the limits the report lists.')
    return AGENT, message


def next_action(action: Mapping | None) -> dict | None:
    """``action`` with ``audience`` (of its ``message``) and ``junior_message`` added.

    ``junior_message`` is always present: equal to ``message`` when that is already written
    for the junior (a step question), a second-person sentence without command, flag, or id
    names otherwise."""
    if action is None:
        return None
    out = dict(action)
    audience, junior = _junior_next(action)
    out['audience'] = audience
    out['junior_message'] = junior
    return out


# --- not_yet_defensible ------------------------------------------------------------------

def _junior_limit(item: Mapping) -> str | None:
    """The junior variant of a limit written for the agent, or None when its text is
    already written for the junior."""
    kind = item.get('id')
    if kind == 'unconfirmed_decisions':
        named = join(decision_words(d) for d in item.get('decisions') or [])
        return f'Not confirmed by you yet: {named}.'
    if kind == 'open_holds':
        return ('You set a condition that is not resolved yet, so nothing it covers can be '
                'confirmed until your own words resolve it: '
                + join(decision_words(d) for d in item.get('decisions') or []) + '.')
    if kind == 'conclusion_outdated':
        return ('The conclusion was confirmed before a decision it summarizes changed, so its '
                'text may no longer describe the study; you will be asked to confirm it again.')
    if kind == 'delegated_decisions':
        named = join(decision_words(d) for d in item.get('decisions') or [])
        return (f'You delegated these to the assistant\'s recommended default, so they are not '
                f'your own judgment: {named}.')
    if kind == 'stale_results':
        return 'Some results are out of date and are computed again before they are cited.'
    return None


def limit(item: Mapping) -> dict:
    """A ``not_yet_defensible`` item with ``audience`` (of its ``text``) and
    ``junior_text``: the text itself when it is written for the junior, its junior
    variant otherwise."""
    out = dict(item)
    junior = _junior_limit(item)
    out['audience'] = AGENT if junior is not None else JUNIOR
    out['junior_text'] = junior if junior is not None else str(item.get('text') or '')
    return out


def junior_text(item: Mapping) -> str:
    """The text of a limit that may be shown to the junior."""
    if item.get('junior_text'):
        return item['junior_text']
    junior = _junior_limit(item)
    return junior if junior is not None else str(item.get('text') or '')


# --- deliverables ------------------------------------------------------------------------

ARTIFACT_WORDS = {'report': 'the report', 'notebook': 'the generated notebook',
                  'workbench': 'the workbench'}


def artifact(name: str, item: Mapping) -> dict:
    """``{audience, junior_message}`` of a deliverable's ``message`` (``currency.message``):
    it names paths and asks for a render, so it is written for the agent."""
    label = ARTIFACT_WORDS.get(name, ' '.join(str(name).split('_')))
    status = item.get('status')
    if item.get('generated') is False or name == 'workbench':
        junior = (f'{_capital(label)} is your free space: it is created once, never '
                  'overwritten, and not tracked by the study.')
    elif status == 'ok':
        junior = f'{_capital(label)} is up to date.'
    elif status == 'not_rendered':
        junior = f'{_capital(label)} has not been written yet.'
    elif status == 'failed':
        junior = (f'The last update of {label} failed; do not rely on it until it is '
                  'written again.')
    else:
        junior = (f'{_capital(label)} is out of date: the study changed after it was '
                  'written. Do not rely on it until it is written again.')
    return {'audience': AGENT, 'junior_message': junior}


def annotate_view(view: dict) -> dict:
    """Annotate a built view in place: ``next_action`` and every
    ``not_yet_defensible`` item get their audience (used by :func:`mlkit.study.view.build`)."""
    view['next_action'] = next_action(view.get('next_action'))
    view['not_yet_defensible'] = [limit(x) for x in view.get('not_yet_defensible') or []]
    return view


__all__ = ['JUNIOR', 'AGENT', 'AUDIENCES', 'next_action', 'limit', 'junior_text', 'artifact',
           'annotate_view', 'decision_words', 'join', 'activity_words', 'rule_words',
           'model_words', 'VERDICT_WORDS', 'policy_words', 'variant_words']
