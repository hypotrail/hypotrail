"""Study state ``hypotrail.study/1``: schema, validation, integrity, and derived views.

``.hypotrail/state.json`` is the single source of truth for decisions. It is written
only by :class:`mlkit.study.store.StudyStore` through
:func:`mlkit.reliability.apply_command`. Plan §3.1 and §3.2 define its content:

* ``facts``: what the case states, with an epistemic status. A fact is never
  "confirmed": confirmation is a human act and belongs to decisions.
* ``decisions``: the five study decisions. A decision moves
  ``open -> proposed -> confirmed -> reconfirm_required | superseded``. A confirmed
  decision carries a ``confirmation`` with the user's verbatim words.
* ``proposals``: first-class proposals the agent made, each with a restatement the
  user answers. A future webview "Confirm" button confirms a proposal by id.
* ``current``, ``stale``, ``executions``, ``invalidations``: result bookkeeping that
  later activities fill in.
* ``receipts``: idempotency receipts of :func:`mlkit.reliability.apply_command`.

This module is pure: it reads and writes no file, and imports neither pandas, numpy,
nor scikit-learn, so ``status`` and ``plan`` stay fast.
"""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from typing import Any, Mapping

from . import trials
from .case import EPISTEMIC_STATUSES, Case, require_supported
from .errors import StudyError

SCHEMA = 'hypotrail.study/1'
STATE_FILE = 'state.json'
SHA_FILE = 'state.sha256'

# The decisions of a binary study (frozen by the contract). A regression study has the same
# pauses, but its third decision is ``model_choice`` (adopt the candidate model or keep the
# mean baseline): a decision rule on scores has no meaning for a numeric target.
# :func:`decision_ids` gives the decisions of a study's task.
DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'policy', 'conclusion')
REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', 'model_choice',
                           'conclusion')
BINARY, REGRESSION = 'binary', 'regression'
TASKS = (BINARY, REGRESSION)
DEFAULT_TASK = BINARY
# v0.2a (WP-A4): two decisions follow the split, before any model is seen.
# ``success_criterion`` fixes, before the models, the gain over the baseline that would make
# the candidate worth adopting; ``preprocessing`` (EDA governance class b) says how the
# model prepares the variables (missing-value indicators, rare categories, caps, log
# transforms), fitted on training rows only. A study created by ``init`` since WP-A4 has the
# seven decisions; a study created before has the five above and keeps them (it is never
# migrated): :func:`decision_ids` reads which set a state holds.
SUCCESS_CRITERION, PREPROCESSING = 'success_criterion', 'preprocessing'
WP_A4_DECISIONS = (SUCCESS_CRITERION, PREPROCESSING)
FULL_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', SUCCESS_CRITERION,
                     PREPROCESSING, 'policy', 'conclusion')
FULL_REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split',
                                SUCCESS_CRITERION, PREPROCESSING, 'model_choice', 'conclusion')
DECISION_IDS_BY_TASK = {BINARY: DECISION_IDS, REGRESSION: REGRESSION_DECISION_IDS}
FULL_DECISION_IDS_BY_TASK = {BINARY: FULL_DECISION_IDS, REGRESSION: FULL_REGRESSION_DECISION_IDS}
# v0.2b (WP-B1, ADR 0006 amendment): two more decisions. ``model_variant`` names the one
# analytical variant of the candidate model the junior compares under the same evaluation
# protocol (a regularisation strength or a feature group left out); ``final_test`` opens the
# sealed final test once, in the junior's words, after the choice. A study created by
# ``init`` originally wrote these nine decisions; a study created before keeps its five,
# seven, or nine decisions (never migrated): :func:`decision_ids` reads the set in the state.
MODEL_VARIANT, FINAL_TEST = 'model_variant', 'final_test'
WP_B1_DECISIONS = (MODEL_VARIANT, FINAL_TEST)
B1_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', SUCCESS_CRITERION,
                   PREPROCESSING, MODEL_VARIANT, 'policy', FINAL_TEST, 'conclusion')
B1_REGRESSION_DECISION_IDS = ('prediction_time', 'feature_availability', 'split',
                              SUCCESS_CRITERION, PREPROCESSING, MODEL_VARIANT, 'model_choice',
                              FINAL_TEST, 'conclusion')
B1_DECISION_IDS_BY_TASK = {BINARY: B1_DECISION_IDS, REGRESSION: B1_REGRESSION_DECISION_IDS}
# New binary studies record the selected model separately from the rule. Existing B1
# studies keep their nine decisions and are never migrated implicitly.
B2_DECISION_IDS = ('prediction_time', 'feature_availability', 'split', SUCCESS_CRITERION,
                   PREPROCESSING, MODEL_VARIANT, 'model_choice', 'policy', FINAL_TEST,
                   'conclusion')
ALL_DECISION_IDS = tuple(dict.fromkeys(B2_DECISION_IDS + B1_REGRESSION_DECISION_IDS))
# The decision of the third pause, per task (the choice made on validation results).
CHOICE_DECISION = {BINARY: 'policy', REGRESSION: 'model_choice'}
DECISION_STATUSES = ('open', 'proposed', 'confirmed', 'reconfirm_required', 'superseded')
PROPOSAL_STATUSES = ('open', 'confirmed', 'withdrawn', 'superseded')
AVAILABILITY_DECISIONS = ('available_at_prediction', 'not_available', 'uncertain_excluded',
                          'uncertain_included')
CHANNELS = ('chat', 'cli', 'webview')
# v0.3 (WP-B, R16): ``choice`` is a confirmation channel only: the junior picked the adoption
# option of an interactive choice the agent offered in the chat (Claude Code's
# AskUserQuestion, or the client's equivalent); the option label is the recorded words.
# A proposal never comes from it.
CHOICE_CHANNEL = 'choice'
CONFIRMATION_CHANNELS = CHANNELS + (CHOICE_CHANNEL,)
CONFIRMATION_KEYS = ('user_words', 'proposal_id', 'restatement', 'authenticated', 'channel',
                     'actor', 'revision', 'time')
# How the user decided (D1). ``explicit``: their own reply to the restatement.
# ``delegated_default``: they explicitly delegated to the assistant's recommended default,
# which the restatement stated. Optional in the record: a confirmation without it (written
# before the basis existed) is explicit.
EXPLICIT, DELEGATED_DEFAULT = 'explicit', 'delegated_default'
# Guided confirmation (ADR 0005, v0.2a): a confirmation in the junior's own words is recorded
# as ``endorsed`` (an explicit endorsement of the proposal it is bound to, "oui je confirme
# cela") or ``restated`` (the reply repeats content of the proposal's value or restatement).
# ``explicit`` stays readable in studies written before v0.2a, and stays the request value of
# ``decide confirm --basis`` for "the junior's own words": the engine records which of
# ``endorsed`` and ``restated`` they are.
ENDORSED, RESTATED = 'endorsed', 'restated'
# Owner session 2026-10-26 (L9, R20; ADR 0005 amendment of 2026-10-26): ``automatic``, a
# decision the automatic mode chosen at launch recorded with the engine's value
# (``actor: assistant``, ``user_words: null``). It is never the junior's own words and never
# a delegation: it stays in the review queue until the junior adopts or changes it.
AUTOMATIC = 'automatic'
CONFIRMATION_BASES = (EXPLICIT, ENDORSED, RESTATED, DELEGATED_DEFAULT, AUTOMATIC)
# What ``decide confirm --basis`` accepts (the junior's own words, a delegation, or, in an
# automatic study only, the automatic mode).
REQUEST_BASES = (EXPLICIT, DELEGATED_DEFAULT, AUTOMATIC)
# Bases of a decision taken in the junior's own words (not delegated).
OWN_WORDS_BASES = (EXPLICIT, ENDORSED, RESTATED)
DEFAULT_BASIS = EXPLICIT
# The scope of a delegation (R1). ``this_decision``: the junior delegated at this very
# pause. ``standing``: an earlier delegation that covers every question the junior cannot
# answer ("for questions I can't answer, use your recommended default"). A standing
# delegation covers only STANDING_DELEGATION_DECISIONS; the policy and the conclusion need
# the junior's own words or a delegation given at that pause (``this_decision``).
THIS_DECISION, STANDING = 'this_decision', 'standing'
DELEGATION_SCOPES = (THIS_DECISION, STANDING)
STANDING_DELEGATION_DECISIONS = ('prediction_time', 'feature_availability', 'split')
# v0.2b (WP-B2, ADR 0005): in the ``express`` mode a standing delegation also covers the two
# framing decisions that follow the split. The choice of the third pause, the conclusion
# (and any decision added later) are never covered by a standing delegation (R1 of v0.1).
EXPRESS_STANDING_DELEGATION_DECISIONS = STANDING_DELEGATION_DECISIONS + (
    'success_criterion', 'preprocessing')
# ``agent_concern`` (R3, ADR 0005): a point the agent raised about the junior's words before
# confirming, kept by the junior; ``null`` when none was raised. Written by every v0.2a
# confirmation; a confirmation recorded before has none. ``mode`` (v0.2b, WP-B2): the
# confirmation mode in force when the words were accepted; a confirmation recorded before
# has none (it was guided, or v0.1 rules).
CONFIRMATION_OPTIONAL_KEYS = ('basis', 'delegation_scope', 'agent_concern', 'mode', 'warnings',
                              # v0.3 (WP-B, R27): whether the junior's words give a reason,
                              # for the trade-offs only; and whether they answer the closed
                              # adoption question (written only when true).
                              'reason_given', 'adoption_question',
                              # L9 (R20): a confirmation in the junior's words that adopts,
                              # with the same value, an automatic one (its review):
                              # ``{basis: automatic, proposal_id, revision}`` of the
                              # automatic confirmation it replaced.
                              'adopted_from')
ADOPTED_FROM_KEYS = ('basis', 'proposal_id', 'revision')

# Confirmation modes (ADR 0005). ``guided`` is the default (v0.2a); ``training`` and
# ``express`` are implemented in v0.2b (WP-B2). ``MODE_STRICTNESS`` orders them: lowering the
# strictness (training to guided to express) needs the user's words; raising it does not.
GUIDED, TRAINING, EXPRESS = 'guided', 'training', 'express'
MODES = (GUIDED, TRAINING, EXPRESS)
SUPPORTED_MODES = MODES
DEFAULT_MODE = GUIDED
# Modes refused by ``mode set`` with ``unsupported_capability`` and the version that brings
# them (v0.2a refused training and express with ``available_in: v0.2b``; none is left).
MODES_AVAILABLE_IN: dict[str, str] = {}
MODE_STRICTNESS = {EXPRESS: 0, GUIDED: 1, TRAINING: 2}
MODE_CHANGE_KEYS = ('mode', 'previous', 'user_words', 'revision', 'time', 'request_id')
# L9 (R20): the end of an automatic mode is recorded in ``mode_history`` with this optional
# key, ``{previous, reason}``: ``previous`` the automation that ended, ``reason``
# ``reached_end`` (the run reached what it covers; no words needed) or ``stopped`` (the
# junior's words stopped it midway). The confirmation mode itself does not change.
MODE_CHANGE_OPTIONAL_KEYS = ('automation',)
AUTOMATION_END_KEYS = ('previous', 'reason')
# L9 (R20, D17): the automatic mode, chosen at ``init`` only (``init --automation``).
# ``until_final_test`` (the default variant) records every decision before the final test;
# ``full_demo`` also opens the final test and concludes (a demonstration, never defensible
# until reviewed). ``state.automation`` is ``{mode, status, started_revision, ended}``;
# ``status`` goes one way, ``running`` to ``ended``. A study without the key has no
# automation (every study created before L9, and every study created without the flag).
UNTIL_FINAL_TEST, FULL_DEMO = 'until_final_test', 'full_demo'
AUTOMATION_MODES = (UNTIL_FINAL_TEST, FULL_DEMO)
AUTOMATION_RUNNING, AUTOMATION_ENDED = 'running', 'ended'
AUTOMATION_STATUSES = (AUTOMATION_RUNNING, AUTOMATION_ENDED)
AUTOMATION_KEYS = ('mode', 'status', 'started_revision', 'ended')
AUTOMATION_ENDED_KEYS = ('revision', 'reason', 'user_words', 'time', 'request_id')
AUTOMATION_END_REASONS = ('reached_end', 'stopped')
# The decisions ``full_demo`` covers beyond ``until_final_test``.
DEMO_ONLY_DECISIONS = ('final_test', 'conclusion')
# The actor of an automatic confirmation.
AUTOMATIC_ACTOR = 'assistant'
# The study language (``init --lang``): proposals may carry a restatement per language
# (``labels``) and surfaces show the one of the study language.
LANGUAGES = ('en', 'fr')
DEFAULT_LANGUAGE = 'en'

# Which confirmed decisions a decision rests on. Changing one of them makes the
# dependants need reconfirmation (plan §3.7, rows 1, 2, 4, and 5).
DEPENDS_ON = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': (),
    'policy': ('prediction_time', 'feature_availability', 'split'),
    'conclusion': ('prediction_time', 'feature_availability', 'split', 'policy'),
}
REGRESSION_DEPENDS_ON = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': (),
    'model_choice': ('prediction_time', 'feature_availability', 'split'),
    'conclusion': ('prediction_time', 'feature_availability', 'split', 'model_choice'),
}
DEPENDS_ON_BY_TASK = {BINARY: DEPENDS_ON, REGRESSION: REGRESSION_DEPENDS_ON}
# The same tables for a study with the WP-A4 decisions: the success criterion and the
# preprocessing rest on no other decision; the choice rests on the preprocessing (its
# models are fitted with it) and the conclusion on every decision.
FULL_DEPENDS_ON = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': (),
    SUCCESS_CRITERION: (),
    PREPROCESSING: (),
    'policy': ('prediction_time', 'feature_availability', 'split', PREPROCESSING),
    'conclusion': ('prediction_time', 'feature_availability', 'split', SUCCESS_CRITERION,
                   PREPROCESSING, 'policy'),
}
FULL_REGRESSION_DEPENDS_ON = {
    'prediction_time': (),
    'feature_availability': ('prediction_time',),
    'split': (),
    SUCCESS_CRITERION: (),
    PREPROCESSING: (),
    'model_choice': ('prediction_time', 'feature_availability', 'split', PREPROCESSING),
    'conclusion': ('prediction_time', 'feature_availability', 'split', SUCCESS_CRITERION,
                   PREPROCESSING, 'model_choice'),
}
FULL_DEPENDS_ON_BY_TASK = {BINARY: FULL_DEPENDS_ON, REGRESSION: FULL_REGRESSION_DEPENDS_ON}
# v0.2b (WP-B1): the variant rests on no decision (its value is checked against the case when
# it is fitted); the choice rests on the variant (it compares it), the opening of the final
# test on every decision before it, and the conclusion on every decision.
_B1_COMMON = ('prediction_time', 'feature_availability', 'split', SUCCESS_CRITERION,
              PREPROCESSING, MODEL_VARIANT)


def _b1_depends(choice: str) -> dict:
    return {'prediction_time': (), 'feature_availability': ('prediction_time',), 'split': (),
            SUCCESS_CRITERION: (), PREPROCESSING: (), MODEL_VARIANT: (),
            choice: ('prediction_time', 'feature_availability', 'split', PREPROCESSING,
                     MODEL_VARIANT),
            FINAL_TEST: _B1_COMMON + (choice,),
            'conclusion': _B1_COMMON + (choice, FINAL_TEST)}


B1_DEPENDS_ON_BY_TASK = {BINARY: _b1_depends('policy'), REGRESSION: _b1_depends('model_choice')}


def _b2_binary_depends() -> dict:
    out = _b1_depends('policy')
    out['model_choice'] = _B1_COMMON
    out['policy'] = ('prediction_time', 'feature_availability', 'split', PREPROCESSING,
                     MODEL_VARIANT, 'model_choice')
    out[FINAL_TEST] = _B1_COMMON + ('model_choice', 'policy')
    out['conclusion'] = _B1_COMMON + ('model_choice', 'policy', FINAL_TEST)
    return out


B2_BINARY_DEPENDS_ON = _b2_binary_depends()

DEFAULT_SETTINGS = {'bootstrap': {'replicates': 2000, 'seed': 20261017, 'level': 0.95}}

# The plan (§4, three pauses). A step is done when its decision is confirmed and
# every listed result slot is current. With both, the decision comes first unless
# ``decide_first`` is False (a policy is confirmed only after it is evaluated).
STEPS = (
    {'id': 'prediction_time', 'pause': 1, 'decision': 'prediction_time', 'activities': (),
     'requires': (),
     'title': 'Define the prediction moment',
     'question': 'At what moment is the prediction made, and what is known at that moment?',
     'expected_output': 'A confirmed prediction time, restated and answered in your own words.',
     'completion': 'Decision prediction_time is confirmed.'},
    {'id': 'feature_availability', 'pause': 1, 'decision': 'feature_availability',
     'activities': (), 'requires': ('prediction_time',),
     'title': 'Decide which variables are available at prediction time',
     'question': 'Which variables are known at the prediction moment, and which must be '
                 'excluded?',
     'expected_output': 'A confirmed availability status for every candidate feature, with the '
                        'exclusions listed in your own words.',
     'completion': 'Decision feature_availability is confirmed.'},
    {'id': 'split', 'pause': 2, 'decision': 'split', 'activities': ('split',),
     'requires': ('prediction_time', 'feature_availability'),
     'title': 'Split the data before exploring it',
     'question': 'How are rows divided between training and validation, before any '
                 'exploration of the target?',
     'expected_output': 'A confirmed split decision and a recorded split result.',
     'completion': 'Decision split is confirmed and the split result is current.'},
    {'id': 'train_eda', 'pause': None, 'decision': None,
     'activities': ('eda.target_rate', 'eda.special_values'), 'requires': ('split',),
     'title': 'Explore the training partition',
     # WP-A9 (M5): the step names the rows it reads and the wider catalog, and says that
     # each look at the outcome is counted.
     'question': 'What do the training rows show about the outcome and the special values? '
                 'Other explorations (the quality overview, rates by variable, distributions, '
                 'the single-feature signal) each answer a question stated first; every look '
                 'at the outcome is counted.',
     'expected_output': 'Target rate and special-value results on training rows, with their '
                        'exposure recorded.',
     'completion': 'The training EDA results are current.'},
    {'id': 'models', 'pause': None, 'decision': None,
     'activities': ('fit.baseline', 'fit.logistic'), 'requires': ('split',),
     'title': 'Fit a baseline and a logistic model',
     'question': 'How much does a simple model improve on a constant baseline on validation?',
     'expected_output': 'Persisted validation predictions for the baseline and the logistic '
                        'model.',
     'completion': 'Both fit results are current.'},
    {'id': 'policy', 'pause': 3, 'decision': 'policy', 'activities': ('policy.evaluation',),
     'requires': ('models',), 'decide_first': False,
     'title': 'Choose a decision policy',
     'question': 'Which rule turns scores into actions (a threshold, a capacity or a share), '
                 'and what does it cost and gain?',
     'expected_output': 'A current policy evaluation and a confirmed policy adoption.',
     'completion': 'The policy evaluation is current and decision policy is confirmed.'},
    {'id': 'conclusion', 'pause': 3, 'decision': 'conclusion', 'activities': (),
     'requires': ('models',),
     'title': 'Conclude proportionately',
     'question': 'What can be said, for which use, and with which limits? Keeping the '
                 'baseline is a valid result.',
     'expected_output': 'A confirmed conclusion that names its limits.',
     'completion': 'Decision conclusion is confirmed.'},
)
STEP_IDS = tuple(s['id'] for s in STEPS)
ACTIVITY_SLOTS = tuple(a for s in STEPS for a in s['activities'])

# The plan of a regression study: the same pauses, a numeric target. The training EDA
# summarises the target distribution, the models are the training mean and a linear
# model, and the third pause chooses a model on the validation error (MAE and RMSE in the
# target unit, with paired bootstrap intervals), not a decision rule on scores.
REGRESSION_STEPS = (
    STEPS[0], STEPS[1], STEPS[2],
    {'id': 'train_eda', 'pause': None, 'decision': None,
     'activities': ('eda.target_summary', 'eda.special_values'), 'requires': ('split',),
     'title': 'Explore the training partition',
     'question': 'What do the training rows show about the distribution of the target and '
                 'the special values? Other explorations (the quality overview, means by '
                 'variable, distributions, the single-feature signal) each answer a question '
                 'stated first; every look at the target is counted.',
     'expected_output': 'A target summary (count, mean, standard deviation, quantiles, missing '
                        'values) and special-value counts on training rows, with their exposure '
                        'recorded.',
     'completion': 'The training EDA results are current.'},
    {'id': 'models', 'pause': None, 'decision': None,
     'activities': ('fit.baseline', 'fit.linear'), 'requires': ('split',),
     'title': 'Fit a mean baseline and a linear model',
     'question': 'Which predictions do the training mean and a linear model give for the '
                 'validation rows?',
     'expected_output': 'Persisted validation predictions for the mean baseline and the linear '
                        'model.',
     'completion': 'Both fit results are current.'},
    {'id': 'model_choice', 'pause': 3, 'decision': 'model_choice',
     'activities': ('evaluate.regression',), 'requires': ('models',), 'decide_first': False,
     'title': 'Choose the model',
     'question': 'Does the linear model reduce the validation error of the mean baseline, in the '
                 'target unit, by enough to adopt it, given the paired intervals and the '
                 'residuals?',
     'expected_output': 'A current regression evaluation and a confirmed model choice.',
     'completion': 'The regression evaluation is current and decision model_choice is '
                   'confirmed.'},
    STEPS[6],
)
STEPS_BY_TASK = {BINARY: STEPS, REGRESSION: REGRESSION_STEPS}
REGRESSION_STEP_IDS = tuple(s['id'] for s in REGRESSION_STEPS)
REGRESSION_ACTIVITY_SLOTS = tuple(a for s in REGRESSION_STEPS for a in s['activities'])
ACTIVITY_SLOTS_BY_TASK = {BINARY: ACTIVITY_SLOTS, REGRESSION: REGRESSION_ACTIVITY_SLOTS}

# v0.2a (WP-A4, remark R2). Step 0, "Discover the data", is informational: no decision, no
# activity, no confirmation. The junior reads the data card (``hypotrail data``) before any
# proposal; the step is done once the study holds a proposal, and ``next_action`` is
# ``show_data_card`` until then. Every study shows it (a study created before WP-A4 holds
# proposals, so it reads as done).
DISCOVER_DATA = 'discover_data'
DISCOVER_STEP = {
    'id': DISCOVER_DATA, 'pause': None, 'decision': None, 'activities': (), 'requires': (),
    'title': 'Discover the data',
    'question': 'What does one row describe, which columns are there and what does each one '
                'mean, and what do a few rows look like?',
    'expected_output': 'The data card read with you: the row unit, the columns grouped with '
                       'their meaning and availability, and a few example rows. Nothing is '
                       'decided at this step.',
    'completion': 'Done once a first proposal is made.'}
# The success criterion is fixed at the split pause, before any model is fitted.
SUCCESS_STEP = {
    'id': SUCCESS_CRITERION, 'pause': 2, 'decision': SUCCESS_CRITERION, 'activities': (),
    'requires': ('split',),
    'title': 'Fix the success criterion before seeing a model',
    # WP-A9 (M6): the terms first, then the question. v0.3 (WP-C, R18): a metric and a
    # minimum; the metric options and the reference value are in
    # ``next_action.criterion_options`` (``governance.criterion_options``).
    'question': 'Precision is the share of the rows a rule selects that turn out positive; '
                'recall is the share of all positive rows the rule reaches. The baseline gives '
                'every row the same score, so its precision is the overall positive rate. The '
                'rule says which rows you act on: the top share or number of scores, or the '
                'rows above a score threshold. With a fixed number of rows acted on, precision, '
                'recall and lift rank the models the same way; with a threshold they differ. '
                'Choose the metric first. How many percentage points above the baseline, at '
                'the rule you will adopt, would make the model worth using? It is fixed now, '
                'before any model is fitted.',
    'expected_output': 'A confirmed metric and minimum gain over the baseline, stated before '
                       'any model result is seen.',
    'completion': 'Decision success_criterion is confirmed.'}
REGRESSION_SUCCESS_STEP = dict(
    SUCCESS_STEP,
    question='The mean absolute error is the average size of a prediction\'s error, in the '
             'unit of the target. The mean baseline predicts, for every row of the validation '
             'set, the mean of the target on the training set. '
             'How much smaller than the error of the mean baseline should the validation '
             'error of the model be for it to be worth using? It is fixed now, before any '
             'model is fitted.',
    expected_output='A confirmed minimum relative error reduction over the mean baseline, '
                    'stated before any model result is seen.')
# The preprocessing (EDA governance class b) follows the training exploration that motivates
# it and comes before the models, which apply it.
PREPROCESSING_STEP = {
    'id': PREPROCESSING, 'pause': 2, 'decision': PREPROCESSING, 'activities': (),
    'requires': ('split',),
    'title': 'Decide how the model prepares the variables',
    'question': 'How should the model treat missing values, rare categories, extreme values '
                'and skewed variables? Every parameter is learnt on training rows only.',
    'expected_output': 'A confirmed preprocessing, with the explorations that motivated it.',
    'completion': 'Decision preprocessing is confirmed.'}


def _models_after_decisions(step: dict) -> dict:
    return dict(step, requires=('split', SUCCESS_CRITERION, PREPROCESSING))


# Owner session 2026-10-26 (lot L5, R5, R7, owner decision D5). A study created by ``init``
# since then writes ``exploration_order: "structural_first"``: its plan checks the structure of
# the development rows without the target (``eda.quality``, step ``structural_eda``) and
# decides the preparation from it **before** any look at the target; the target exploration
# (``train_eda``) follows the preparation. The view drafts the preparation from the
# target-free results and the variants from the diagnostics (:mod:`mlkit.study.drafts`) only
# in such a study. A study without the key keeps its plan, its drafts and its open proposals
# (never migrated). The WP-A9 M1 rule is unchanged: a preparation proposed after a look at the
# target is still stamped data-contingent.
EXPLORATION_ORDER_KEY = 'exploration_order'
STRUCTURAL_FIRST = 'structural_first'
EXPLORATION_ORDERS = (STRUCTURAL_FIRST,)
STRUCTURAL_EDA = 'structural_eda'
STRUCTURAL_EDA_STEP = {
    'id': STRUCTURAL_EDA, 'pause': None, 'decision': None, 'activities': ('eda.quality',),
    'requires': ('split',),
    'title': 'Check the structure of the data',
    'question': 'Which columns have missing cells, rare categories, or values outside their '
                'possible range? This check reads the development rows without the target, so '
                'the preparation decided from it comes before any look at the target.',
    'expected_output': 'A current quality overview of the development rows, read without the '
                       'target.',
    'completion': 'The quality overview is current.'}
# The target exploration once the preparation is decided (structural-first plan), by task and
# by evaluation scheme (``True``: cross-validation).
STRUCTURAL_TRAIN_EDA_TEXTS = {
    (BINARY, True): {
        'title': 'Explore the target on the development rows',
        'question': 'What do the development rows show about the outcome and the special '
                    'values? Each of these analyses is a look at the target: it reads the '
                    'variable to predict, and every look is counted. The preparation is already '
                    'decided, before these looks.'},
    (BINARY, False): {
        'title': 'Explore the target on the training rows',
        'question': 'What do the training rows show about the outcome and the special values? '
                    'Each of these analyses is a look at the target: it reads the variable to '
                    'predict, and every look is counted. The preparation is already decided, '
                    'before these looks.'},
    (REGRESSION, True): {
        'title': 'Explore the target on the development rows',
        'question': 'What do the development rows show about the distribution of the target '
                    'and the special values? Each of these analyses is a look at the target: it '
                    'reads the variable to predict, and every look is counted. The preparation '
                    'is already decided, before these looks.'},
    (REGRESSION, False): {
        'title': 'Explore the target on the training rows',
        'question': 'What do the training rows show about the distribution of the target and '
                    'the special values? Each of these analyses is a look at the target: it '
                    'reads the variable to predict, and every look is counted. The preparation '
                    'is already decided, before these looks.'},
}
STRUCTURAL_PREPROCESSING_QUESTION = (
    'How should the model treat missing values, rare categories, extreme values and skewed '
    'variables? The draft reads the quality check, which does not read the target; every '
    'parameter is learnt only on the rows each model is fitted on.')


FULL_STEPS = (DISCOVER_STEP, STEPS[0], STEPS[1], STEPS[2], SUCCESS_STEP, STEPS[3],
              PREPROCESSING_STEP, _models_after_decisions(STEPS[4]), STEPS[5], STEPS[6])
FULL_REGRESSION_STEPS = (DISCOVER_STEP, REGRESSION_STEPS[0], REGRESSION_STEPS[1],
                         REGRESSION_STEPS[2], REGRESSION_SUCCESS_STEP, REGRESSION_STEPS[3],
                         PREPROCESSING_STEP, _models_after_decisions(REGRESSION_STEPS[4]),
                         REGRESSION_STEPS[5], REGRESSION_STEPS[6])
FULL_STEPS_BY_TASK = {BINARY: FULL_STEPS, REGRESSION: FULL_REGRESSION_STEPS}
FULL_STEP_IDS = tuple(s['id'] for s in FULL_STEPS)
FULL_REGRESSION_STEP_IDS = tuple(s['id'] for s in FULL_REGRESSION_STEPS)

# v0.2b (WP-B1). The variant follows the model fits: the junior names one variant of the
# candidate, it is fitted under the same evaluation protocol, and the choice compares the
# two (the trial count says how many configurations were evaluated). The opening of the
# final test follows the choice; it is optional for the plan (a study that keeps the
# baseline opens nothing), so a blocked opening never hides the conclusion
# (:func:`next_action`).
# v0.3 (WP-F1, ADR 0007): up to three variants, each declared with its question; the step's
# activities are the slots of the variants the decision names (:func:`steps`).
VARIANT_STEP = {
    'id': MODEL_VARIANT, 'pause': 3, 'decision': MODEL_VARIANT, 'activities': ('fit.variant',),
    'requires': ('models',),
    'title': 'Choose the variants to compare',
    'question': 'Which variants of the candidate model, at most three and each with the '
                'question it answers, should be compared with it under the same evaluation: '
                'the penalty chosen by nested cross-validation, a stronger or weaker '
                'regularisation, the model without one group of variables, or another model '
                'family when the diagnostics show a pattern the linear model cannot follow?',
    'expected_output': 'A confirmed list of variants and their out-of-fold predictions, '
                       'evaluated like the candidate.',
    'completion': 'Decision model_variant is confirmed and every variant fit is current.'}
MODEL_CHOICE_STEP = {
    'id': 'model_choice', 'pause': 3, 'decision': 'model_choice',
    'activities': (), 'requires': (MODEL_VARIANT, 'models'),
    'title': 'Choose the model',
    'question': 'Given the development comparison, which model is retained for the decision '
                'rule? Comparing a model does not select it.',
    'expected_output': 'An explicit confirmed model choice, distinct from the rule.',
    'completion': 'Decision model_choice is confirmed.'}
FINAL_TEST_STEP = {
    'id': FINAL_TEST, 'pause': 3, 'decision': FINAL_TEST,
    'activities': ('final_test.evaluation',), 'requires': (),
    'title': 'Open the final test once',
    'question': 'Now that the model and the rule are chosen, do you open the sealed final test, '
                'once, to measure the chosen configuration on rows nothing has seen? After '
                'this, any change is made after the final test.',
    'expected_output': 'A confirmed opening in your own words, and the one '
                       'evaluation of the chosen configuration on the final test.',
    'completion': 'Decision final_test is confirmed and the final evaluation is recorded.'}


def _b1_steps(full: tuple, choice: str) -> tuple:
    out = []
    for step in full:
        if step['id'] == choice:
            out.append(VARIANT_STEP)
            out.append(dict(step, requires=('models', MODEL_VARIANT)))
            out.append(dict(FINAL_TEST_STEP, requires=(choice,)))
        else:
            out.append(step)
    return tuple(out)


B1_STEPS = _b1_steps(FULL_STEPS, 'policy')
B2_BINARY_STEPS = tuple(
    item
    for step in B1_STEPS
    for item in ((MODEL_CHOICE_STEP, dict(step, requires=('models', MODEL_VARIANT,
                                                          'model_choice')))
                 if step['id'] == 'policy'
                 else ((dict(step, requires=('model_choice', 'policy')),) if
                       step['id'] == FINAL_TEST else (step,)))
)
B1_REGRESSION_STEPS = tuple(
    # B6c (M3): a regression study chooses a model, not a rule.
    dict(s, question='Now that the model is chosen, do you open the sealed final test, once, '
                     'to measure it on rows nothing has seen? After this, any change is made '
                     'after the final test.')
    if s['id'] == FINAL_TEST else s for s in _b1_steps(FULL_REGRESSION_STEPS, 'model_choice'))

# B6c (M3): the words of the plan under cross-validation. Every development row is explored,
# and each is predicted once by a model fitted on the other folds: there are no "training
# rows" or "validation rows" to name. Merged over the step (``steps``).
CV_STEP_TEXTS = {
    'split': {
        # v0.3 (WP-C, R15): the standard words, used correctly: each fold is in turn the
        # validation fold, the other folds are its training folds.
        'question': 'How is the development set divided into folds for k-fold '
                    'cross-validation, before any exploration of the target? Each fold is in '
                    'turn the validation fold, predicted by a model fitted on the other folds, '
                    'the training folds.',
        'expected_output': 'A confirmed cross-validation and a recorded fold assignment.'},
    'train_eda': {
        'title': 'Explore the development rows',
        'question': 'What do the development rows show about the outcome and the special '
                    'values? Other explorations (the quality overview, rates by variable, '
                    'distributions, the single-feature signal) each answer a question stated '
                    'first; every look at the outcome is counted.',
        'expected_output': 'Target rate and special-value results on the development rows, with '
                           'their exposure recorded.'},
    'preprocessing': {
        'question': 'How should the model treat missing values, rare categories, extreme values '
                    'and skewed variables? Every parameter is learnt only on the training folds '
                    'of each model, never on its validation fold.'},
    'models': {
        'question': 'How much does a simple model improve on a constant baseline, measured out '
                    'of fold on the development rows?',
        'expected_output': 'Persisted out-of-fold predictions for the baseline and the logistic '
                           'model.'},
}
REGRESSION_CV_STEP_TEXTS = {
    **CV_STEP_TEXTS,
    'train_eda': {
        'title': 'Explore the development rows',
        'question': 'What do the development rows show about the distribution of the target and '
                    'the special values? Other explorations (the quality overview, means by '
                    'variable, distributions, the single-feature signal) each answer a question '
                    'stated first; every look at the target is counted.',
        'expected_output': 'A target summary and special-value counts on the development rows, '
                           'with their exposure recorded.'},
    'success_criterion': {
        'question': 'The mean absolute error is the average size of a prediction\'s error, in '
                    'the unit of the target. The mean baseline predicts, for every row of a '
                    'validation fold, the mean of the training folds. How much smaller than the '
                    'error of the mean '
                    'baseline should the out-of-fold error of the model be for it to be worth '
                    'using? It is fixed now, before any model is fitted.'},
    'models': {
        'question': 'Which predictions do the mean baseline and a linear model give for each '
                    'development row, predicted out of fold?',
        'expected_output': 'Persisted out-of-fold predictions for the mean baseline and the '
                           'linear model.'},
    'model_choice': {
        'question': 'Does the linear model reduce the out-of-fold error of the mean baseline, in '
                    'the target unit, by enough to adopt it, given the paired intervals and the '
                    'residuals?'},
}
CV_STEP_TEXTS_BY_TASK = {BINARY: CV_STEP_TEXTS, REGRESSION: REGRESSION_CV_STEP_TEXTS}


def uses_cross_validation(state: Mapping | None) -> bool:
    """B6c (M3): the study evaluates by cross-validation: its split decision (or an open
    split proposal) is one, or a study with a final test has not decided it yet (the draft
    is one)."""
    if not isinstance(state, Mapping) or not has_wp_b1_decisions(state):
        return False
    value = (state['decisions'].get('split') or {}).get('value')
    if isinstance(value, Mapping) and value.get('method'):
        return value['method'] in CV_METHODS
    for p in (state.get('proposals') or {}).values():
        if p.get('decision_id') == 'split' and p.get('status') == 'open' \
                and isinstance(p.get('value'), Mapping):
            return p['value'].get('method') in CV_METHODS
    return True
B1_STEPS_BY_TASK = {BINARY: B1_STEPS, REGRESSION: B1_REGRESSION_STEPS}
B1_STEP_IDS = tuple(s['id'] for s in B1_STEPS)
B2_BINARY_STEP_IDS = tuple(s['id'] for s in B2_BINARY_STEPS)
B1_REGRESSION_STEP_IDS = tuple(s['id'] for s in B1_REGRESSION_STEPS)
B1_ACTIVITY_SLOTS_BY_TASK = {task: tuple(a for s in steps_ for a in s['activities'])
                             for task, steps_ in B1_STEPS_BY_TASK.items()}
# The steps a blocked plan may skip: the opening of the final test (nothing to open while no
# model or rule is chosen).
OPTIONAL_STEPS = (FINAL_TEST,)
# Optional slots outside the plan: ``eda.rate_by`` (binary) and ``eda.mean_by``
# (regression) have one slot per column, ``eda.rate_by:<column>``
# (``mlkit.study.activities.slot_of``). They are shown with the training EDA step and
# never block a step. ``eda.distribution:<column>`` (CLI-CONTRACT-COMPANION §8, C8) is a
# per-column activity of both tasks; WP-0 reserves its prefix, WP-E3 implements it.
PER_COLUMN_SLOT_PREFIXES = ('eda.rate_by:', 'eda.mean_by:', 'eda.distribution:')

TOP_KEYS = ('schema', 'revision', 'created', 'updated', 'case', 'dataset', 'facts',
            'structure', 'prior_exposure', 'decisions', 'proposals', 'current', 'stale',
            'executions', 'invalidations', 'receipts', 'settings')
# ``task`` (``binary`` or ``regression``) is written by every new study; a state written
# before it existed has no ``task`` and is a binary study. ``notes`` (post-v0.1, P2) holds
# the conditions the junior states at a pause; it appears with the first note.
# ``partition`` (v0.2a, ADR 0006): the sealed final test assigned at ``init``
# (:mod:`mlkit.study.partition`); a study created before it has none and no final test.
# ``mode`` and ``language`` (ADR 0005, v0.2a) are written by every new study; a state
# without them is a guided study in English. ``mode_history`` appears with the first
# ``mode set``.
# ``understanding`` (ADR 0008): the opt-in understanding and handover review; a state
# without it is ``off`` (``mlkit.study.understanding.model``).
# ``case_l10n`` (owner session 2026-10-26, L3, D4 A): the case's translation sidecar
# recorded at ``init`` (``{path, sha256}``, :mod:`mlkit.study.l10n`); a study whose case has
# none, or created before it existed, has no ``case_l10n`` and shows the case's English.
TOP_OPTIONAL_KEYS = ('task', 'notes', 'partition', 'mode', 'language', 'mode_history',
                     'exploration', 'understanding', 'case_l10n',
                     # Owner session 2026-10-26 (L5, D5): the plan generation that checks the
                     # structure before the target (``structural_first``), written by
                     # ``init``; absent in a study created before.
                     'exploration_order',
                     # Owner session 2026-10-26 (L9, R20): the automatic mode chosen at
                     # ``init --automation`` (AUTOMATION_KEYS); absent otherwise.
                     'automation')
DECISION_KEYS = ('status', 'value', 'proposal_id', 'confirmation', 'depends_on', 'revision',
                 'reason')
PROPOSAL_KEYS = ('proposal_id', 'decision_id', 'value', 'restatement', 'rationale', 'revision',
                 'status', 'created')
# Written by ``hypotrail decide`` (WP1.4): the request that created the proposal, the
# confirmed values it was based on (a change makes it stale), and why it was closed.
# ``origin`` (CLI-CONTRACT-COMPANION §9, C9) is ``{channel}``, where the proposal came from;
# ``decide propose`` writes it on every new proposal; one recorded before C9 has none.
# ``labels`` (ADR 0005) is ``{language: restatement}``, written when the proposal was made
# with a restatement per language; surfaces show the one of the study language.
PROPOSAL_OPTIONAL_KEYS = ('request_id', 'basis', 'closed_revision', 'closed_reason', 'origin',
                          'labels')
ORIGIN_KEYS = ('channel',)
EXECUTION_BUCKETS = ('active', 'interrupted', 'late')
# A junior's condition or hold on a decision (post-v0.1, P2): "don't adopt anything until I
# bring my manager's figure". Recorded verbatim by ``decide note --about``, it stays open
# until the junior's own words resolve it (``decide note --resolve``); while it is open the
# decision cannot be confirmed and ``not_yet_defensible`` lists it (``open_holds``). The
# junior may also withdraw it in their words (``decide note --withdraw``, D5): ``withdrawn``.
NOTE_KEYS = ('note_id', 'decision_id', 'kind', 'user_words', 'status', 'created', 'revision',
             'request_id', 'resolution')
# A ``correction`` (R3, ADR 0005) is a later correction of a decision's reasoning, in the
# junior's words: it is ``recorded`` at once, never blocks, and asks for nothing again.
HOLD, CORRECTION = 'hold', 'correction'
NOTE_KINDS = (HOLD, CORRECTION)
NOTE_STATUSES = ('open', 'resolved', 'withdrawn', 'recorded')
NOTE_RESOLUTION_KEYS = ('user_words', 'revision', 'time', 'request_id')


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# --- task -------------------------------------------------------------------------------

def task_of(state: Mapping | str | None) -> str:
    """The task of a study state (``binary`` when the state predates the ``task`` key).
    A task name is returned as it is."""
    if isinstance(state, str):
        return state
    if isinstance(state, Mapping):
        return state.get('task', DEFAULT_TASK)
    return DEFAULT_TASK


def has_wp_b1_decisions(state: Mapping | str | None) -> bool:
    """Whether a study has the WP-B1 decisions (``model_variant``, ``final_test``). A state
    answers by the decisions it holds (a study created before WP-B1 is never migrated); a
    task name or ``None`` describes a new study, which has them."""
    if isinstance(state, Mapping) and isinstance(state.get('decisions'), Mapping):
        return all(d in state['decisions'] for d in WP_B1_DECISIONS)
    return True


def has_explicit_binary_model_choice(state: Mapping | str | None) -> bool:
    """Whether a binary study uses the explicit model -> rule -> final-test flow."""
    if task_of(state) != BINARY:
        return False
    if isinstance(state, Mapping) and isinstance(state.get('decisions'), Mapping):
        return 'model_choice' in state['decisions']
    return True


def has_wp_a4_decisions(state: Mapping | str | None) -> bool:
    """Whether a study has the WP-A4 decisions (``success_criterion``, ``preprocessing``).

    A state answers by the decisions it holds (a study created before WP-A4 has none of
    them and is never migrated); a task name or ``None`` describes a new study, which has
    them."""
    if isinstance(state, Mapping) and isinstance(state.get('decisions'), Mapping):
        return all(d in state['decisions'] for d in WP_A4_DECISIONS)
    return True


def decision_ids(state: Mapping | str | None = None) -> tuple[str, ...]:
    """The decisions of a study (or of a task name, for a new study)."""
    if has_wp_b1_decisions(state):
        if has_explicit_binary_model_choice(state):
            return B2_DECISION_IDS
        return B1_DECISION_IDS_BY_TASK[task_of(state)]
    table = FULL_DECISION_IDS_BY_TASK if has_wp_a4_decisions(state) else DECISION_IDS_BY_TASK
    return table[task_of(state)]


def depends_on(state: Mapping | str | None, decision_id: str) -> tuple[str, ...]:
    if has_wp_b1_decisions(state):
        if has_explicit_binary_model_choice(state):
            return B2_BINARY_DEPENDS_ON[decision_id]
        return B1_DEPENDS_ON_BY_TASK[task_of(state)][decision_id]
    table = FULL_DEPENDS_ON_BY_TASK if has_wp_a4_decisions(state) else DEPENDS_ON_BY_TASK
    return table[task_of(state)][decision_id]


DIAG_SLOT = {BINARY: 'diag.binary', REGRESSION: 'diag.regression'}


def _wp_f1_steps(state: Mapping | str | None, out: tuple) -> tuple:
    """v0.3 (WP-F1, R28): the variant step runs the slots of the variants the decision
    names (``fit.variant`` while none is named), and the development diagnostics are part of
    the plan: after the model fits while no variant is named (the diagnostics of the first
    linear fit, which the shortlist of families reads), then with the choice (run again
    once the variants are fitted, and again at the adopted rule)."""
    if not isinstance(state, Mapping) or not isinstance(state.get('decisions'), Mapping):
        return out
    diag = DIAG_SLOT[task_of(state)]
    decided = trials.confirmed_value(state) is not None
    slots = tuple(trials.declared_slots(state)) or ('fit.variant',)
    choice = choice_decision(state)
    result = []
    from . import assurance
    review = assurance.profile(state) == 'review-v1'
    for step in out:
        if step['id'] == MODEL_VARIANT:
            step = dict(step, activities=slots)
        elif step['id'] == 'models' and not decided:
            step = dict(step, activities=tuple(step['activities']) + (diag,))
        elif step['id'] == choice:
            step = dict(step, activities=tuple(step['activities']) + (diag,))
        elif step['id'] == FINAL_TEST and review:
            step = dict(step, activities=tuple(step['activities']) + ('diag.final_test',))
        result.append(step)
    return tuple(result)


def structural_first(state: Mapping | str | None) -> bool:
    """Owner session 2026-10-26 (L5, D5): whether a study follows the structural-first plan
    (``exploration_order: "structural_first"``, written by ``init``). A study without the key
    (created before) keeps its plan; a task name or ``None`` is not a study."""
    return isinstance(state, Mapping) \
        and state.get(EXPLORATION_ORDER_KEY) == STRUCTURAL_FIRST \
        and has_wp_b1_decisions(state)


def _structural_order(state: Mapping, out: tuple) -> tuple:
    """L5 (D5): the structural check, then the preparation (which requires it), then the
    target exploration; every other step keeps its place and its requirements."""
    cv = uses_cross_validation(state)
    texts = STRUCTURAL_TRAIN_EDA_TEXTS[(task_of(state), cv)]
    by_id = {s['id']: s for s in out}
    result = []
    for step in out:
        if step['id'] == 'train_eda':
            continue
        if step['id'] == PREPROCESSING:
            result.append(STRUCTURAL_EDA_STEP)
            result.append(dict(step, requires=tuple(step['requires']) + (STRUCTURAL_EDA,),
                               question=STRUCTURAL_PREPROCESSING_QUESTION))
            if 'train_eda' in by_id:
                result.append(dict(by_id['train_eda'], **texts))
            continue
        result.append(step)
    return tuple(result)


def steps(state: Mapping | str | None = None) -> tuple[dict, ...]:
    """The plan steps of a study's task. A study created before WP-A4 has the step "Discover
    the data" and its own five decisions' steps (the models then need the split only). A
    structural-first study (L5) checks the structure, then decides the preparation, then
    explores the target (:func:`structural_first`)."""
    if has_wp_b1_decisions(state):
        out = (B2_BINARY_STEPS if has_explicit_binary_model_choice(state)
               else B1_STEPS_BY_TASK[task_of(state)])
        if uses_cross_validation(state):
            texts = CV_STEP_TEXTS_BY_TASK[task_of(state)]
            out = tuple(dict(s, **texts.get(s['id'], {})) for s in out)
        if structural_first(state):
            out = _structural_order(state, out)
        return _wp_f1_steps(state, out)
    full = FULL_STEPS_BY_TASK[task_of(state)]
    if has_wp_a4_decisions(state):
        return full
    out = []
    for step in full:
        if step['decision'] in WP_A4_DECISIONS:
            continue
        out.append(dict(step, requires=tuple(r for r in step['requires']
                                             if r not in WP_A4_DECISIONS)))
    return tuple(out)


def step_ids(state: Mapping | str | None = None) -> tuple[str, ...]:
    return tuple(s['id'] for s in steps(state))


def activity_slots(state: Mapping | str | None = None) -> tuple[str, ...]:
    if has_wp_b1_decisions(state):
        if structural_first(state):
            base = (B2_BINARY_STEPS if has_explicit_binary_model_choice(state)
                    else B1_STEPS_BY_TASK[task_of(state)])
            return tuple(a for s in _structural_order(state, base) for a in s['activities'])
        if has_explicit_binary_model_choice(state):
            return tuple(a for s in B2_BINARY_STEPS for a in s['activities'])
        return B1_ACTIVITY_SLOTS_BY_TASK[task_of(state)]
    return ACTIVITY_SLOTS_BY_TASK[task_of(state)]


def choice_decision(state: Mapping | str | None = None) -> str:
    """The decision of the third pause: ``policy`` (binary) or ``model_choice``."""
    return CHOICE_DECISION[task_of(state)]


# --- construction -----------------------------------------------------------------------

def empty_decision(decision_id: str, task: str = DEFAULT_TASK) -> dict:
    return {'status': 'open', 'value': None, 'proposal_id': None, 'confirmation': None,
            'depends_on': list(depends_on(task, decision_id)), 'revision': None,
            'reason': None}


def mode_of(state: Mapping | None) -> str:
    """The confirmation mode of a study (``guided`` when the state predates modes)."""
    return state.get('mode', DEFAULT_MODE) if isinstance(state, Mapping) else DEFAULT_MODE


def raises_strictness(previous: str, mode: str) -> bool:
    """A change from ``previous`` to ``mode`` that makes confirmations stricter (express to
    guided, guided to training); it needs no user words (ADR 0005, v0.2b)."""
    return MODE_STRICTNESS.get(mode, -1) > MODE_STRICTNESS.get(previous, 99)


def lowers_strictness(previous: str, mode: str) -> bool:
    """A change that makes confirmations less strict (training to guided, guided to
    express); it needs the user's words, naming the mode."""
    return MODE_STRICTNESS.get(mode, 99) < MODE_STRICTNESS.get(previous, -1)


def standing_delegation_decisions(state: Mapping | None) -> tuple[str, ...]:
    """The decisions a standing delegation covers in the study's mode (WP-B2): the three
    framing decisions, and in ``express`` also the success criterion and the preprocessing."""
    if mode_of(state) == EXPRESS:
        return EXPRESS_STANDING_DELEGATION_DECISIONS
    return STANDING_DELEGATION_DECISIONS


def language_of(state: Mapping | None) -> str:
    """The study language (``en`` when the state predates it)."""
    return state.get('language', DEFAULT_LANGUAGE) if isinstance(state, Mapping) \
        else DEFAULT_LANGUAGE


def label_of(proposal: Mapping, language: str) -> str:
    """The restatement of ``proposal`` in ``language``, else its restatement."""
    labels = proposal.get('labels') or {}
    return labels.get(language) or proposal['restatement']


def initial_state(case: Case, *, created: str | None = None,
                  language: str = DEFAULT_LANGUAGE, reliability_profile: str | None = None) -> dict:
    """The state of a new study on ``case``, before its first commit (revision 0).

    Refuses an unsupported case (``unsupported_capability``) without fallback. Facts
    and structure statements are copied from the case with their statuses; no
    decision is taken.
    """
    require_supported(case)
    from . import assurance
    if reliability_profile is not None and reliability_profile not in assurance.PROFILES:
        raise ValueError('Unknown reliability profile')
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    if reliability_profile is not None:
        settings['reliability_profile'] = reliability_profile
    doc = case.document
    stamp = created or now()
    task = case.task
    return {
        'schema': SCHEMA,
        'task': task,
        'revision': 0,
        'created': stamp,
        'updated': stamp,
        'case': {'id': doc['id'], 'path': str(case.path), 'sha256': _sha256_file(case.path)},
        'dataset': {'path': str(case.dataset_path), 'sha256': case.dataset['sha256'],
                    'rows': case.dataset['rows'],
                    'row_key': {'rule': doc['row_key']['rule'],
                                'format': doc['row_key']['format']}},
        'facts': {f['id']: {'value': f['value'], 'status': f['status'], 'source': f['source']}
                  for f in doc['facts']},
        'structure': copy.deepcopy(doc['structure']),
        'prior_exposure': copy.deepcopy(doc.get('prior_exposure', [])),
        'decisions': {d: empty_decision(d, task) for d in decision_ids(task)},
        'proposals': {},
        'current': {},
        'stale': {},
        'executions': {bucket: {} for bucket in EXECUTION_BUCKETS},
        'exploration': {'events': {}},
        'invalidations': [],
        'receipts': {},
        'settings': settings,
        'mode': DEFAULT_MODE,
        'language': language,
    }


def _sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for block in iter(lambda: handle.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def confirmation(*, user_words: str | None, proposal: dict, channel: str, actor: str,
                 revision: int, time: str | None = None, basis: str = DEFAULT_BASIS,
                 delegation_scope: str | None = None, agent_concern: str | None = None,
                 mode: str | None = None, warnings: list | None = None,
                 reason_given: bool | None = None, adoption_question: bool = False,
                 adopted_from: Mapping | None = None) -> dict:
    """The confirmation record of ``proposal`` (plan §3.2, §9 bis).

    ``user_words`` is the user's verbatim reply to the proposal's restatement.
    ``authenticated`` is always False: the engine cannot verify who typed the words.
    ``basis`` is ``explicit`` or ``delegated_default`` (:data:`CONFIRMATION_BASES`).
    ``delegation_scope`` is ``None`` for an explicit confirmation, else ``this_decision``,
    ``standing``, or ``None`` when the delegation did not state it (:data:`DELEGATION_SCOPES`).
    ``agent_concern`` is the point the agent raised before the junior confirmed (R3), or None.
    ``mode`` is the confirmation mode in force (v0.2b); the record omits it when None.
    ``warnings`` (WP-A9, H3) are the ``words_contradict_value`` warnings the words raised
    and the junior kept; the record omits them when there are none.
    ``reason_given`` (v0.3, WP-B) says, for a trade-off confirmed in the junior's own words,
    whether the words give a reason; the record omits it otherwise. ``adoption_question``
    (v0.3, WP-B) is written, true, when the words answer the closed adoption question.
    """
    record = {'user_words': user_words, 'proposal_id': proposal['proposal_id'],
              'restatement': proposal['restatement'], 'authenticated': False,
              'channel': channel, 'actor': actor, 'revision': revision, 'time': time or now(),
              'basis': basis, 'delegation_scope': delegation_scope,
              'agent_concern': agent_concern}
    if mode is not None:
        record['mode'] = mode
    if warnings:
        record['warnings'] = [dict(w) for w in warnings]
    if reason_given is not None:
        record['reason_given'] = bool(reason_given)
    if adoption_question:
        record['adoption_question'] = True
    if adopted_from is not None:
        record['adopted_from'] = {k: adopted_from.get(k) for k in ADOPTED_FROM_KEYS}
    problems = _confirmation_problems(record, 'confirmation')
    if problems:
        raise StudyError('invalid_confirmation', 'The confirmation is incomplete.',
                         details={'problems': problems})
    return record


# --- validation -------------------------------------------------------------------------

def _keys(node: Any, path: str, keys, problems: list) -> bool:
    if not isinstance(node, dict):
        problems.append({'path': path, 'problem': 'must be a mapping'})
        return False
    for k in keys:
        if k not in node:
            problems.append({'path': f'{path}.{k}' if path else k, 'problem': 'is required'})
    for k in node:
        if k not in keys:
            problems.append({'path': f'{path}.{k}' if path else str(k),
                             'problem': 'is not part of the schema'})
    return all(k in node for k in keys)


def _text(node: Any) -> bool:
    return isinstance(node, str) and bool(node.strip())


def confirmation_basis(c: Any) -> str:
    """The basis of a confirmation record (``explicit`` when it predates the basis)."""
    return c.get('basis', DEFAULT_BASIS) if isinstance(c, dict) else DEFAULT_BASIS


def basis_class(basis: str | None) -> str | None:
    """``own_words`` for a decision taken in the junior's words (``explicit``, ``endorsed``,
    ``restated``), ``delegated`` for a delegation, ``automatic`` for the automatic mode (L9);
    None stays None. The conclusion's credit
    line depends on this class only (:func:`dependencies.outdates_conclusion`)."""
    if basis is None:
        return None
    if basis == AUTOMATIC:       # L9 (R20): neither the junior's words nor a delegation
        return 'automatic'
    return 'delegated' if basis == DELEGATED_DEFAULT else 'own_words'


def _confirmation_problems(c: Any, path: str) -> list[dict]:
    problems: list[dict] = []
    present = tuple(k for k in CONFIRMATION_OPTIONAL_KEYS if isinstance(c, dict) and k in c)
    if not _keys(c, path, CONFIRMATION_KEYS + present, problems):
        return problems
    if 'basis' in present and c['basis'] not in CONFIRMATION_BASES:
        problems.append({'path': f'{path}.basis',
                         'problem': f'must be one of {", ".join(CONFIRMATION_BASES)}'})
    if 'mode' in present and c['mode'] not in MODES:
        problems.append({'path': f'{path}.mode', 'problem': f'must be one of {", ".join(MODES)}'})
    if 'warnings' in present and (not isinstance(c['warnings'], list) or not all(
            isinstance(w, dict) and _text(w.get('variable')) for w in c['warnings'])):
        problems.append({'path': f'{path}.warnings',
                         'problem': 'must be a list of warnings naming their variable'})
    if 'agent_concern' in present and c['agent_concern'] is not None \
            and not _text(c['agent_concern']):
        problems.append({'path': f'{path}.agent_concern',
                         'problem': 'must be null or a non-empty string'})
    if 'delegation_scope' in present and c['delegation_scope'] is not None:
        if c['delegation_scope'] not in DELEGATION_SCOPES:
            problems.append({'path': f'{path}.delegation_scope',
                             'problem': f'must be null or one of {", ".join(DELEGATION_SCOPES)}'})
        elif confirmation_basis(c) != DELEGATED_DEFAULT:
            problems.append({'path': f'{path}.delegation_scope',
                             'problem': 'must be null unless the basis is delegated_default'})
    automatic = confirmation_basis(c) == AUTOMATIC
    for key in ('user_words', 'proposal_id', 'restatement', 'actor', 'time'):
        if key == 'user_words' and automatic:
            # L9 (R20): an automatic decision has no words of the junior.
            if c[key] is not None:
                problems.append({'path': f'{path}.{key}',
                                 'problem': 'must be null for an automatic confirmation'})
            continue
        if not _text(c[key]):
            problems.append({'path': f'{path}.{key}', 'problem': 'must be a non-empty string'})
    if 'adopted_from' in present and (
            not isinstance(c['adopted_from'], dict)
            or set(c['adopted_from']) != set(ADOPTED_FROM_KEYS)
            or c['adopted_from'].get('basis') != AUTOMATIC or automatic):
        problems.append({'path': f'{path}.adopted_from',
                         'problem': 'must be {basis: automatic, proposal_id, revision} on a '
                                    'confirmation in the junior\'s words'})
    if c['authenticated'] is not False:
        problems.append({'path': f'{path}.authenticated',
                         'problem': 'must be false: user words are not authenticated'})
    if c['channel'] not in CONFIRMATION_CHANNELS:
        problems.append({'path': f'{path}.channel',
                         'problem': f'must be one of {", ".join(CONFIRMATION_CHANNELS)}'})
    for key in ('reason_given', 'adoption_question'):
        if key in present and not isinstance(c[key], bool):
            problems.append({'path': f'{path}.{key}', 'problem': 'must be true or false'})
    if type(c['revision']) is not int or c['revision'] < 0:
        problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
    return problems


def _decision_problems(decision_id: str, d: Any, proposals: dict,
                       task: Mapping | str = DEFAULT_TASK) -> list[dict]:
    path = f'decisions.{decision_id}'
    problems: list[dict] = []
    if not _keys(d, path, DECISION_KEYS, problems):
        return problems
    if d['status'] not in DECISION_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(DECISION_STATUSES)}'})
    expected = list(depends_on(task, decision_id))
    if d['depends_on'] != expected:
        problems.append({'path': f'{path}.depends_on', 'problem': f'must be {expected}'})
    if d['status'] == 'confirmed':
        problems += _confirmation_problems(d['confirmation'], f'{path}.confirmation')
        if isinstance(d['confirmation'], dict) and d['confirmation'].get('proposal_id') != d['proposal_id']:
            problems.append({'path': f'{path}.proposal_id',
                             'problem': 'must be the proposal named by the confirmation'})
    elif d['status'] == 'open' and (d['value'] is not None or d['confirmation'] is not None):
        problems.append({'path': path, 'problem': 'an open decision has no value or confirmation'})
    elif d['status'] in ('reconfirm_required', 'superseded') and not _text(d['reason']):
        problems.append({'path': f'{path}.reason', 'problem': 'must say why'})
    if d['proposal_id'] is not None and d['proposal_id'] not in proposals:
        problems.append({'path': f'{path}.proposal_id', 'problem': 'names no proposal'})
    if decision_id == 'feature_availability' and d['value'] is not None:
        if not isinstance(d['value'], dict) or not all(
                isinstance(k, str) and v in AVAILABILITY_DECISIONS for k, v in d['value'].items()):
            problems.append({'path': f'{path}.value',
                             'problem': 'must map each feature to one of '
                                        + ', '.join(AVAILABILITY_DECISIONS)})
    return problems


def _proposal_problems(pid: Any, p: Any, task: Mapping | str = DEFAULT_TASK) -> list[dict]:
    path = f'proposals.{pid}'
    problems: list[dict] = []
    present = tuple(k for k in PROPOSAL_OPTIONAL_KEYS if isinstance(p, dict) and k in p)
    if not _keys(p, path, PROPOSAL_KEYS + present, problems):
        return problems
    if p['proposal_id'] != pid:
        problems.append({'path': f'{path}.proposal_id', 'problem': 'must equal its key'})
    if p['decision_id'] not in decision_ids(task):
        problems.append({'path': f'{path}.decision_id',
                         'problem': f'must be one of {", ".join(decision_ids(task))}'})
    if p['status'] not in PROPOSAL_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(PROPOSAL_STATUSES)}'})
    for key in ('restatement', 'rationale', 'created'):
        if not _text(p[key]):
            problems.append({'path': f'{path}.{key}', 'problem': 'must be a non-empty string'})
    if type(p['revision']) is not int or p['revision'] < 0:
        problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
    if 'labels' in p:
        labels = p['labels']
        if not isinstance(labels, dict) or not labels \
                or any(k not in LANGUAGES or not _text(v) for k, v in labels.items()):
            problems.append({'path': f'{path}.labels',
                             'problem': f'must map languages ({", ".join(LANGUAGES)}) to '
                                        f'non-empty restatements'})
    if 'origin' in p:
        # C9: where the proposal came from, ``{channel}``; absent before C9.
        origin = p['origin']
        if not isinstance(origin, dict) or tuple(origin) != ORIGIN_KEYS \
                or origin['channel'] not in CHANNELS:
            problems.append({'path': f'{path}.origin',
                             'problem': f'must be {{channel}} with channel one of '
                                        f'{", ".join(CHANNELS)}'})
    return problems


def _notes_problems(notes: Any, task: Mapping | str = DEFAULT_TASK) -> list[dict]:
    if not isinstance(notes, dict):
        return [{'path': 'notes', 'problem': 'must be a mapping'}]
    problems: list[dict] = []
    for nid, n in notes.items():
        path = f'notes.{nid}'
        if not _keys(n, path, NOTE_KEYS, problems):
            continue
        if n['note_id'] != nid:
            problems.append({'path': f'{path}.note_id', 'problem': 'must equal its key'})
        if n['decision_id'] not in decision_ids(task):
            problems.append({'path': f'{path}.decision_id',
                             'problem': f'must be one of {", ".join(decision_ids(task))}'})
        if n['kind'] not in NOTE_KINDS:
            problems.append({'path': f'{path}.kind',
                             'problem': f'must be one of {", ".join(NOTE_KINDS)}'})
        if n['status'] not in NOTE_STATUSES:
            problems.append({'path': f'{path}.status',
                             'problem': f'must be one of {", ".join(NOTE_STATUSES)}'})
        if not _text(n['user_words']):
            problems.append({'path': f'{path}.user_words', 'problem': 'must be a non-empty string'})
        if type(n['revision']) is not int or n['revision'] < 0:
            problems.append({'path': f'{path}.revision', 'problem': 'must be a revision number'})
        if (n['kind'] == CORRECTION) != (n['status'] == 'recorded'):
            problems.append({'path': f'{path}.status',
                             'problem': 'a correction is recorded; a hold is open, resolved or '
                                        'withdrawn'})
        if n['status'] in ('resolved', 'withdrawn'):
            r = n['resolution']
            if _keys(r, f'{path}.resolution', NOTE_RESOLUTION_KEYS, problems) \
                    and not _text(r['user_words']):
                problems.append({'path': f'{path}.resolution.user_words',
                                 'problem': 'must be a non-empty string'})
        elif n['resolution'] is not None:
            problems.append({'path': f'{path}.resolution', 'problem': 'an open note has none'})
    return problems


def validate_state(state: Any) -> list[dict]:
    """Every schema problem of ``state`` (empty when it is valid)."""
    problems: list[dict] = []
    present = tuple(k for k in TOP_OPTIONAL_KEYS if isinstance(state, dict) and k in state)
    if not _keys(state, '', TOP_KEYS + present, problems):
        return problems
    if 'task' in present and state['task'] not in TASKS:
        problems.append({'path': 'task', 'problem': f'must be one of {", ".join(TASKS)}'})
        return problems
    task = task_of(state)
    if 'mode' in present and state['mode'] not in MODES:
        problems.append({'path': 'mode', 'problem': f'must be one of {", ".join(MODES)}'})
    if 'language' in present and state['language'] not in LANGUAGES:
        problems.append({'path': 'language', 'problem': f'must be one of {", ".join(LANGUAGES)}'})
    if 'case_l10n' in present:
        from . import l10n
        problems.extend(l10n.state_problems(state))
    if 'automation' in present:
        problems.extend(automation_problems(state['automation']))
    if 'exploration_order' in present and state['exploration_order'] not in EXPLORATION_ORDERS:
        problems.append({'path': 'exploration_order',
                         'problem': f'must be one of {", ".join(EXPLORATION_ORDERS)}'})
    if 'mode_history' in present:
        history = state['mode_history']
        if not isinstance(history, list):
            problems.append({'path': 'mode_history', 'problem': 'must be a list'})
        else:
            for i, change in enumerate(history):
                extra = tuple(k for k in MODE_CHANGE_OPTIONAL_KEYS
                              if isinstance(change, dict) and k in change)
                end = change.get('automation') if extra else None
                if extra and not (isinstance(end, dict) and set(end) == set(AUTOMATION_END_KEYS)
                                  and end.get('previous') in AUTOMATION_MODES
                                  and end.get('reason') in AUTOMATION_END_REASONS):
                    problems.append({'path': f'mode_history.{i}.automation',
                                     'problem': 'must be {previous, reason} of an automation '
                                                'that ended'})
                # L9: the automatic mode ending when its run reached what it covers needs no
                # words (it makes the study stricter); stopping it midway needs them.
                reached = isinstance(end, dict) and end.get('reason') == 'reached_end'
                if _keys(change, f'mode_history.{i}', MODE_CHANGE_KEYS + extra, problems) \
                        and (change['mode'] not in MODES or change['previous'] not in MODES
                             or not (_text(change['user_words'])
                                     or (change['user_words'] is None
                                         and (reached or raises_strictness(
                                             change['previous'], change['mode']))))):
                    problems.append({'path': f'mode_history.{i}',
                                     'problem': "needs a known mode and the user's words "
                                                "(optional only when the change raises the "
                                                "strictness)"})
    if state['schema'] != SCHEMA:
        problems.append({'path': 'schema', 'problem': f'must be "{SCHEMA}"'})
    if type(state['revision']) is not int or state['revision'] < 0:
        problems.append({'path': 'revision', 'problem': 'must be a non-negative integer'})
    _keys(state['case'], 'case', ('id', 'path', 'sha256'), problems)
    if _keys(state['dataset'], 'dataset', ('path', 'sha256', 'rows', 'row_key'), problems):
        _keys(state['dataset']['row_key'], 'dataset.row_key', ('rule', 'format'), problems)
    if isinstance(state['facts'], dict):
        for fid, fact in state['facts'].items():
            if _keys(fact, f'facts.{fid}', ('value', 'status', 'source'), problems) \
                    and fact['status'] not in EPISTEMIC_STATUSES:
                problems.append({'path': f'facts.{fid}.status',
                                 'problem': 'must be one of ' + ', '.join(EPISTEMIC_STATUSES)
                                            + ' (a fact is never confirmed)'})
    else:
        problems.append({'path': 'facts', 'problem': 'must be a mapping'})
    if not isinstance(state['prior_exposure'], list):
        problems.append({'path': 'prior_exposure', 'problem': 'must be a list'})
    proposals = state['proposals'] if isinstance(state['proposals'], dict) else {}
    if not isinstance(state['proposals'], dict):
        problems.append({'path': 'proposals', 'problem': 'must be a mapping'})
    # The decision set is read from the state (WP-A4): the five decisions of a study created
    # before WP-A4, or the seven of a newer one; anything in between is invalid.
    scope = state
    for pid, p in proposals.items():
        problems += _proposal_problems(pid, p, scope)
    if _keys(state['decisions'], 'decisions', decision_ids(scope), problems):
        for decision_id in decision_ids(scope):
            problems += _decision_problems(decision_id, state['decisions'][decision_id],
                                           proposals, scope)
    if 'notes' in present:
        problems += _notes_problems(state['notes'], scope)
    if 'partition' in present:
        from . import partition
        problems += partition.validate(state['partition'])
    if 'exploration' in present:
        exploration = state['exploration']
        if not isinstance(exploration, dict) or set(exploration) != {'events'} \
                or not isinstance(exploration.get('events'), dict):
            problems.append({'path': 'exploration',
                             'problem': 'must be a mapping containing an events mapping'})
        else:
            for event_id, event in exploration['events'].items():
                if not isinstance(event, dict) or event.get('status') not in (
                        'reserved', 'completed', 'failed', 'outcome_unknown'):
                    problems.append({'path': f'exploration.events.{event_id}',
                                     'problem': 'must have a valid event status'})
    for key in ('current', 'stale', 'receipts'):
        if not isinstance(state[key], dict):
            problems.append({'path': key, 'problem': 'must be a mapping'})
    if isinstance(state['current'], dict):
        for slot, rid in state['current'].items():
            if not _text(rid):
                problems.append({'path': f'current.{slot}', 'problem': 'must be a result id'})
    _keys(state['executions'], 'executions', EXECUTION_BUCKETS, problems)
    if not isinstance(state['invalidations'], list):
        problems.append({'path': 'invalidations', 'problem': 'must be a list'})
    if isinstance(state['receipts'], dict):
        for key, receipt in state['receipts'].items():
            _keys(receipt, f'receipts.{key}', ('signature', 'result', 'revision'), problems)
    if not isinstance(state['settings'], dict) or 'bootstrap' not in state['settings']:
        problems.append({'path': 'settings', 'problem': 'must be a mapping with "bootstrap"'})
    else:
        from . import assurance
        for key in state['settings']:
            if key not in ('bootstrap', 'reliability_profile'):
                problems.append({'path': f'settings.{key}', 'problem': 'is not part of the schema'})
        if 'reliability_profile' in state['settings'] \
                and state['settings']['reliability_profile'] not in assurance.PROFILES:
            problems.append({'path': 'settings.reliability_profile',
                             'problem': 'must be legacy or review-v1'})
    if 'understanding' in present:
        from .understanding import model as understanding
        problems.extend(understanding.check(state['understanding']))
    return problems


def check_state(state: Any) -> dict:
    problems = validate_state(state)
    if problems:
        raise StudyError('invalid_state', f'The study state does not follow {SCHEMA}.',
                         details={'problems': problems})
    return state


# --- serialisation and integrity --------------------------------------------------------

def dumps(state: dict) -> bytes:
    """Canonical bytes of ``state``: sorted keys, two-space indent, final newline."""
    return (json.dumps(state, sort_keys=True, indent=2, ensure_ascii=False) + '\n').encode('utf-8')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_line(hexdigest: str) -> str:
    """Content of ``state.sha256``, in ``sha256sum`` format."""
    return f'{hexdigest}  {STATE_FILE}\n'


def parse_sha_line(text: str) -> str | None:
    parts = text.split()
    if len(parts) == 2 and parts[1] == STATE_FILE and len(parts[0]) == 64:
        return parts[0]
    return None


def verify_integrity(data: bytes, sha_text: str | None, *, pending_sha256: str | None = None) -> None:
    """Refuse state bytes that do not match ``state.sha256`` (``integrity_error``).

    ``pending_sha256`` is the digest of a commit that reached its commit point but did
    not finish writing ``state.sha256``; the state is then consistent and recovery
    completes the commit under the writer lock.
    """
    actual = digest(data)
    recorded = parse_sha_line(sha_text) if sha_text is not None else None
    if actual == recorded or (pending_sha256 is not None and actual == pending_sha256):
        return
    raise StudyError('integrity_error',
                     'state.json does not match state.sha256: the state was changed outside '
                     'hypotrail, or a write was interrupted. Nothing is read from it until the '
                     'difference is explained.',
                     details={'state_sha256': actual, 'recorded_sha256': recorded,
                              'sha_file_present': sha_text is not None})


def loads(data: bytes) -> dict:
    try:
        state = json.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise StudyError('integrity_error', f'state.json is not valid JSON: {exc}') from exc
    return check_state(state)


# --- derived views (read-only) ----------------------------------------------------------

def is_current(state: dict, slot: str) -> bool:
    rid = state['current'].get(slot)
    return rid is not None and rid not in state['stale']


def open_proposals(state: dict) -> list[dict]:
    return [p for p in state['proposals'].values() if p['status'] == 'open']


def notes(state: Mapping) -> list[dict]:
    """The junior's notes (P2), oldest first; empty for a state without ``notes``."""
    items = (state.get('notes') or {}).values()
    return sorted(items, key=lambda n: int(str(n['note_id']).rsplit('_', 1)[-1]))


def open_holds(state: Mapping, decision_id: str | None = None) -> list[dict]:
    """Open holds (P2), for one decision or for all."""
    return [n for n in notes(state) if n['status'] == 'open'
            and (decision_id is None or n['decision_id'] == decision_id)]


def hold_action(state: Mapping, decision_id: str) -> dict | None:
    """Review round 6 (area E): the ``next_action`` of a decision the junior put on hold in
    their own words (an open hold note), whose confirmation is refused
    (``decision_on_hold``): ask the junior whether the condition they set is met; their own
    words resolve the hold (``decide note --resolve``) or keep it. None without an open
    hold. :mod:`mlkit.study.feasibility` names it instead of a confirmation it would refuse."""
    holds = open_holds(state, decision_id)
    if not holds:
        return None
    note = holds[0]
    return {'kind': 'resolve_hold', 'decision': decision_id, 'note_id': note['note_id'],
            'note_ids': [n['note_id'] for n in holds], 'user_words': note['user_words'],
            'message': (f'The junior put the {decision_id} on hold in their own words '
                        f'(note {note["note_id"]}): "{note["user_words"]}". It cannot be '
                        'confirmed while the hold is open. Ask them whether the condition is '
                        f'met; record their reply with decide note --resolve {note["note_id"]} '
                        '(their own words), or leave it on hold. Do not answer for them.')}


def _confirmed(state: dict, decision_id: str) -> bool:
    return state['decisions'][decision_id]['status'] == 'confirmed'


def _step_done(state: dict, step: dict) -> bool:
    if step['id'] == DISCOVER_DATA:
        # Informational (WP-A4): done once the study holds a proposal.
        return bool(state['proposals'])
    if step['decision'] and not _confirmed(state, step['decision']):
        return False
    return all(is_current(state, a) for a in step['activities'])


def _step_requirements_met(state: dict, step: dict) -> bool:
    by_id = {s['id']: s for s in steps(state)}
    return all(_step_done(state, by_id[r]) for r in step['requires'])


def derive_plan(state: dict) -> list[dict]:
    """The plan with a status per step, derived from state only.

    Status is one of ``done``, ``needs_reconfirmation``, ``awaiting_confirmation``
    (a proposal waits for the user's words), ``ready``, or ``blocked`` (a required
    step is not done). ``current`` marks the first step that is not done.
    """
    plan, current_found = [], False
    waiting = {p['decision_id'] for p in open_proposals(state)}
    for step in steps(state):
        decision = state['decisions'][step['decision']] if step['decision'] else None
        missing = [a for a in step['activities'] if not is_current(state, a)]
        if decision is not None and decision['status'] == 'reconfirm_required':
            status = 'needs_reconfirmation'
        elif _step_done(state, step):
            status = 'done'
        elif not _step_requirements_met(state, step):
            status = 'blocked'
        elif step['decision'] in waiting:
            status = 'awaiting_confirmation'
        else:
            status = 'ready'
        is_current_step = status != 'done' and not current_found
        current_found = current_found or is_current_step
        plan.append({'id': step['id'], 'title': step['title'], 'question': step['question'],
                     'expected_output': step['expected_output'],
                     'completion': step['completion'], 'pause': step['pause'],
                     'decision': step['decision'], 'activities': list(step['activities']),
                     'decide_first': step.get('decide_first', True),
                     'missing_results': missing, 'requires': list(step['requires']),
                     'status': status, 'current': is_current_step})
    return plan


def next_action(state: dict, suspected: Mapping | None = None) -> dict:
    """The single next thing to do, in priority order.

    0. an execution recorded as active whose lease nobody holds (``suspected``, from a
       read-only lease probe by ``status``, F1) has an unknown outcome: tell the junior,
       never call it in progress, and ask before acknowledging;
    1. an interrupted execution must be acknowledged (never restarted automatically);
    2. a decision needs reconfirmation (once proposed again, the words awaited on that
       proposal, review round 6);
    3. an open proposal waits for the user's verbatim answer to its restatement;
    4. the current step needs a proposal or a result;
    5. otherwise the plan is finished.

    L9 (R20): in an automatic study, between 2 and 3, a decision the automatic mode recorded
    is reviewed (:func:`review_action`) once the mode ended or wherever it does not cover the
    action 3 to 5 would give.

    Step 0 (WP-A4) comes first in the plan: while the study holds no proposal, the next
    action is ``show_data_card`` (informational, nothing to confirm).
    """
    if suspected:
        eid = sorted(suspected)[0]
        return {'kind': 'outcome_unknown', 'execution_id': eid,
                'activity': suspected[eid].get('activity'),
                'message': 'This execution is recorded as running, but no process holds its '
                           'lease: it stopped and its outcome is unknown. Tell the junior the '
                           'outcome is unknown (never call it in progress) and ask before '
                           'acknowledging it; it is not restarted automatically.'}
    interrupted = sorted(state['executions']['interrupted'])
    if interrupted:
        return {'kind': 'acknowledge_interruption', 'execution_id': interrupted[0],
                'message': 'An execution was interrupted and its outcome is unknown. Inspect it '
                           'and acknowledge it; it is not restarted automatically.'}
    for decision_id in decision_ids(state):
        decision = state['decisions'][decision_id]
        if decision['status'] == 'reconfirm_required':
            # Review round 6 (area E): once proposed again, the junior's words are awaited
            # on that proposal (a ``reconfirm`` named again would only propose once more).
            return decision_action(state, decision_id)
    # L9 (R20): the review of an automatic study. While the automatic mode runs, the plan is
    # followed as it covers it; once it ended, or where it stops (the final test in
    # ``until_final_test``, ``done`` in ``full_demo``), each decision it recorded is
    # reviewed in the plan's order before anything else, in the junior's own words.
    queue = [d for d in review_queue(state) if state['decisions'][d]['status'] == 'confirmed']
    planned = _planned_action(state)
    if queue and not action_covered(state, planned):
        return review_action(state, queue[0])
    return planned


def _planned_action(state: dict) -> dict:
    """Steps 3 to 5 of :func:`next_action`: an open proposal, the current step, ``done``."""
    pending = sorted(open_proposals(state), key=lambda p: (p['revision'], p['proposal_id']))
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        # J2: an early planned challenger is recorded but deliberately non-adoptable.  It
        # must not pull the active workflow away from framing/model diagnostics.
        pending = [p for p in pending if not (
            p.get('decision_id') == MODEL_VARIANT and
            (not all((state['decisions'].get(d) or {}).get('status') == 'confirmed'
                     for d in ('prediction_time', 'feature_availability', 'split',
                               SUCCESS_CRITERION, PREPROCESSING))
             or not all(is_current(state, slot) for slot in
                        (('fit.baseline', 'fit.logistic') if task_of(state) == BINARY
                         else ('fit.baseline', 'fit.linear')))
             or not is_current(state, DIAG_SLOT[task_of(state)])))]
    if pending:
        return _await_action(state, pending[0])
    for step in derive_plan(state):
        if step['status'] == 'done':
            continue
        if step['id'] in OPTIONAL_STEPS and step['status'] == 'blocked':
            # WP-B1: nothing to open while no model or rule is chosen; the conclusion (keep
            # the baseline, inconclusive) does not wait for it.
            continue
        if step['id'] == DISCOVER_DATA:
            # WP-A4 (R2): the junior sees the data before any proposal; nothing to confirm.
            return {'kind': 'show_data_card', 'step': DISCOVER_DATA,
                    'message': 'Before proposing anything, show the junior the data card '
                               '(hypotrail data): the row unit, the grouped columns with their '
                               'meaning and availability, and the eight sample rows. It is '
                               'informational: nothing to confirm. Then propose the prediction '
                               'moment.'}
        if step['status'] == 'blocked':
            return {'kind': 'blocked', 'step': step['id'], 'requires': step['requires'],
                    'message': f'Step {step["id"]} needs: {", ".join(step["requires"])}.'}
        decide = step['decision'] and not _confirmed(state, step['decision'])
        if decide and (step['decide_first'] or not step['missing_results']):
            return _propose_action(state, step)
        return {'kind': 'run', 'step': step['id'], 'activity': step['missing_results'][0],
                'message': step['question']}
    return {'kind': 'done', 'message': 'Every step is done. Review what is not yet defensible.'}


def _reconfirm_action(state: dict, decision_id: str) -> dict:
    """The action of a decision to confirm again (``reconfirm``, or the ``run`` first of a
    result its confirmation needs, E4-3)."""
    decision = state['decisions'][decision_id]
    action = {'kind': 'reconfirm', 'decision': decision_id,
              'message': f'Decision {decision_id} must be confirmed again: '
                         f'{decision["reason"]}'}
    # Review round 4 (E4-3): the value to propose again, so the action is runnable as
    # given (E4-1: a final test on the configuration the study chooses now).
    default = reconfirm_value(state, decision_id)
    if default is not None:
        action['default_value'] = default
    # E4-3: a result the confirmation needs that is not current is run first (the
    # confirmation would be refused): the plan's step question, as any run.
    slot = _reconfirm_needs_run(state, decision_id, default)
    if slot is not None:
        step = next((s for s in derive_plan(state) if s['decision'] == decision_id),
                    None) or {}
        return {'kind': 'run', 'step': step.get('id'), 'activity': slot,
                'reconfirm': decision_id,
                'message': step.get('question') or action['message']}
    return action


def _await_action(state: dict, proposal: Mapping) -> dict:
    """The action of an open proposal: the junior's words awaited on it."""
    # v0.3 (WP-J): mode-aware; own words are asked only in the training mode (R27).
    message = ('Show the restatement and record the user\'s own words in reply: what '
               'they keep and why. A bare "ok" is not a decision.'
               if mode_of(state) == TRAINING else
               'Show the restatement, then ask the closed question "Do you adopt this '
               'decision?" and record the reply verbatim. A bare "ok" before that '
               'question is not a decision.')
    return {'kind': 'await_user_words', 'proposal_id': proposal['proposal_id'],
            'decision': proposal['decision_id'], 'message': message}


def _propose_action(state: dict, step: Mapping) -> dict:
    """The proposal of a plan step's decision, with the engine's drafted value."""
    action = {'kind': 'propose', 'step': step['id'], 'decision': step['decision'],
              'message': step['question']}
    if step['decision'] == PREPROCESSING:
        # WP-A4: the engine's default, the preparation the models used before the
        # decision existed (results stay comparable).
        from .governance import DEFAULT_PREPROCESSING
        action['default_value'] = copy.deepcopy(DEFAULT_PREPROCESSING)
    default = b1_default_value(state, step['decision'])
    if default is not None:
        action['default_value'] = default
    return action


def decision_action(state: dict, decision_id: str) -> dict | None:
    """Review round 6 (area E): the action ``next_action`` gives for one decision, wherever
    it stands in the plan: ``await_user_words`` on its latest open proposal, else
    ``reconfirm`` (or its ``run`` first) when it must be confirmed again, else its
    ``propose``. None for a decision the study does not have or that is confirmed."""
    decision = state['decisions'].get(decision_id)
    if decision is None or decision['status'] == 'confirmed':
        return None
    pending = sorted((p for p in open_proposals(state) if p['decision_id'] == decision_id),
                     key=lambda p: (p['revision'], p['proposal_id']))
    if pending:
        return _await_action(state, pending[-1])
    if decision['status'] == 'reconfirm_required':
        return _reconfirm_action(state, decision_id)
    step = next((s for s in derive_plan(state) if s['decision'] == decision_id), None)
    return _propose_action(state, step) if step is not None else None


# v0.2b (WP-B1): the evaluation schemes of the ``split`` decision (cross-validation on the
# development rows), one per kind of study, and their defaults.
LEGACY_CV_METHODS = ('kfold_stratified', 'kfold_quantile', 'temporal_folds')
REVIEW_CV_METHODS = ('forward_chaining', 'ordered_retrospective', 'group_disjoint')
CV_METHODS = LEGACY_CV_METHODS + REVIEW_CV_METHODS
CV_KEYS = ('method', 'folds', 'seed')
TEMPORAL_CV_KEYS = ('method', 'folds', 'gap')
DEFAULT_FOLDS = 5
MIN_FOLDS, MAX_FOLDS = 3, 10
DEFAULT_CV_SEED = 20261017
# The variants of the candidate (decision ``model_variant``, :mod:`mlkit.study.trials`): v0.2b
# had one variant of the first two kinds; v0.3 (WP-F1) names up to three, of four kinds.
VARIANT_KINDS = trials.KINDS
VARIANT_STRENGTHS = trials.STRENGTHS
# The v0.2b draft (kept: a value of this form is still accepted, read as one variant).
DEFAULT_VARIANT = dict(kind='regularisation', strength='strong')


def default_variant(state: Mapping) -> dict:
    """v0.3 (WP-F1): the engine's drafted variant, the candidate's penalty chosen by nested
    cross-validation (one trial), with its question in the study language."""
    value = trials.draft(task_of(state), language_of(state))
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        for variant in value[trials.LIST_KEY]:
            variant.update(origin='planned', diagnostic_result_id=None)
    return value


def is_cv_split(value) -> bool:
    """Whether a ``split`` value is a cross-validation scheme (WP-B1)."""
    return isinstance(value, Mapping) and value.get('method') in CV_METHODS


def cv_method(state: Mapping) -> str:
    """The cross-validation method of a study: ``temporal_folds`` when its case declares a
    time column or an order (folds follow time), ``kfold_stratified`` for a binary target,
    ``kfold_quantile`` for a numeric one."""
    from . import assurance
    if assurance.profile(state) == 'review-v1':
        protocol = (state.get('partition') or {}).get('analysis_protocol') or {}
        dependency = protocol.get('dependencies')
        if dependency in ('temporal', 'grouped_temporal'):
            return ('forward_chaining' if protocol.get('intended_use') == 'future_prediction'
                    else 'ordered_retrospective')
        if dependency == 'grouped':
            return 'group_disjoint'
    structure = state.get('structure') or {}
    time_column = ((structure.get('time_column') or {}).get('value'))
    if time_column is not None or (state.get('partition') or {}).get('method') == 'temporal':
        return 'temporal_folds'
    return 'kfold_stratified' if task_of(state) == BINARY else 'kfold_quantile'


def choice_config(state: Mapping) -> dict | None:
    """The configuration the study chose (WP-B1): ``{model, rule}`` from the confirmed policy
    (binary; ``rule`` is its canonical rule, ``model`` the candidate or the variant) or the
    confirmed model choice (regression; ``rule`` is None); None when nothing is chosen."""
    from . import records as rec
    if has_explicit_binary_model_choice(state):
        model = state['decisions']['model_choice']
        policy = state['decisions']['policy']
        if model.get('status') != 'confirmed' or policy.get('status') != 'confirmed':
            return None
        rule = rec.policy_rule(policy.get('value'))
        return ({'model': model.get('value'), 'rule': rule}
                if isinstance(model.get('value'), str) and rule is not None else None)
    choice = choice_decision(state)
    decision = state['decisions'].get(choice) or {}
    if decision.get('status') != 'confirmed':
        return None
    value = decision.get('value')
    if choice == 'policy':
        rule = rec.policy_rule(value)
        return None if rule is None else {'model': rec.policy_model(value), 'rule': rule}
    return {'model': value, 'rule': None} if isinstance(value, str) else None


def _reconfirm_needs_run(state: Mapping, decision_id: str, value) -> str | None:
    """E4-3: the first result a decision to confirm again needs and that is not current
    (stale or missing), so the confirmation would be refused
    (:func:`mlkit.study.preconditions.missing_for_decision` checks the same slots; this one
    reads state only, on the read side): the policy evaluation for the policy, the fits (or
    the regression comparison) for the model choice, every result the opening rests on
    (:func:`mlkit.study.opening.selection_slots`) for the final test. None otherwise."""
    from . import opening
    task = task_of(state)
    if decision_id == 'policy':
        slots = ['policy.evaluation']
    elif decision_id == 'model_choice':
        slots = (['fit.logistic'] + ([value] if isinstance(value, str)
                                     and trials.is_variant_slot(value) else [])
                 if task == BINARY else ['evaluate.regression'])
    elif decision_id == FINAL_TEST:
        slots = opening.selection_slots(state)
    else:
        return None
    return next((slot for slot in slots if not is_current(state, slot)), None)


def reconfirm_value(state: Mapping, decision_id: str):
    """Review round 4 (E4-3): the value a decision to confirm again is proposed with: its
    recorded value, except the final test (the configuration the study chooses now,
    :func:`choice_config`, E4-1) and a binary policy under an explicit model choice (its
    rule, applied to the model chosen now). None when there is no such value."""
    from . import records as rec
    decision = state['decisions'].get(decision_id) or {}
    if decision_id == FINAL_TEST:
        return choice_config(state)
    value = decision.get('value')
    if decision_id == 'policy' and has_explicit_binary_model_choice(state):
        rule = rec.policy_rule(value)
        model = (state['decisions'].get('model_choice') or {}).get('value')
        if rule is None or not isinstance(model, str):
            return copy.deepcopy(value)
        return rule if model == rec.POLICY_CANDIDATE else f'{rule}{rec.POLICY_MODEL_SEP}{model}'
    return copy.deepcopy(value)


def b1_default_value(state: Mapping, decision_id: str):
    """The engine's drafted value of a WP-B1 study's decision for ``next_action``: the
    cross-validation scheme of the split, the default variant, the configuration a final
    test would open. None otherwise."""
    if not has_wp_b1_decisions(state):
        return None
    if decision_id == 'split':
        method = cv_method(state)
        if method in ('forward_chaining', 'ordered_retrospective'):
            return {'method': method, 'folds': DEFAULT_FOLDS, 'gap': 0}
        return {'method': method, 'folds': DEFAULT_FOLDS, 'seed': DEFAULT_CV_SEED}
    if decision_id == MODEL_VARIANT:
        return default_variant(state)
    if decision_id == FINAL_TEST:
        return choice_config(state)
    return None


def final_test_opened(state: Mapping) -> bool:
    """Whether the study's final test was opened (WP-B1)."""
    return (state.get('partition') or {}).get('status') == 'opened'


def delegated_decisions(state: dict) -> list[str]:
    """Decisions whose current confirmation is a delegation to the assistant's default."""
    out = []
    for d in decision_ids(state):
        dec = state['decisions'][d]
        if dec['status'] in ('confirmed', 'reconfirm_required') \
                and isinstance(dec['confirmation'], dict) \
                and confirmation_basis(dec['confirmation']) == DELEGATED_DEFAULT:
            out.append(d)
    return out


# --- automatic mode (owner session 2026-10-26, L9, R20; ADR 0005 and 0006 amendments) ------

def automation_record(mode: str, revision: int) -> dict:
    """The ``state.automation`` record ``init --automation MODE`` writes."""
    return {'mode': mode, 'status': AUTOMATION_RUNNING, 'started_revision': revision,
            'ended': None}


def automation_problems(record: Any) -> list[dict]:
    """Schema problems of ``state.automation`` (empty when valid)."""
    path = 'automation'
    if not isinstance(record, dict) or set(record) != set(AUTOMATION_KEYS):
        return [{'path': path, 'problem': 'must be {' + ', '.join(AUTOMATION_KEYS) + '}'}]
    problems = []
    if record['mode'] not in AUTOMATION_MODES:
        problems.append({'path': f'{path}.mode',
                         'problem': f'must be one of {", ".join(AUTOMATION_MODES)}'})
    if record['status'] not in AUTOMATION_STATUSES:
        problems.append({'path': f'{path}.status',
                         'problem': f'must be one of {", ".join(AUTOMATION_STATUSES)}'})
    ended = record['ended']
    if record['status'] == AUTOMATION_RUNNING and ended is not None:
        problems.append({'path': f'{path}.ended', 'problem': 'a running automation has none'})
    if record['status'] == AUTOMATION_ENDED and (
            not isinstance(ended, dict) or set(ended) != set(AUTOMATION_ENDED_KEYS)
            or ended.get('reason') not in AUTOMATION_END_REASONS
            or (ended.get('reason') == 'stopped' and not _text(ended.get('user_words')))):
        problems.append({'path': f'{path}.ended',
                         'problem': 'an ended automation records {' + ', '.join(
                             AUTOMATION_ENDED_KEYS) + '}; stopping it needs the words'})
    return problems


def automation_of(state: Mapping | None) -> dict | None:
    """The automatic mode chosen at ``init``, or None (a study without one)."""
    record = (state or {}).get('automation') if isinstance(state, Mapping) else None
    return record if isinstance(record, Mapping) else None


def automation_in_force(state: Mapping | None) -> str | None:
    """The automatic mode while it runs (``until_final_test`` or ``full_demo``), else None:
    no automation, or one that ended (one way)."""
    record = automation_of(state)
    if record is None or record.get('status') != AUTOMATION_RUNNING:
        return None
    return record.get('mode')


def automation_covers(state: Mapping, decision_id: str | None) -> bool:
    """Whether the automatic mode in force records ``decision_id``: ``until_final_test``
    every decision before the final test, ``full_demo`` also the final test and the
    conclusion (ADR 0005 and 0006 amendments, 2026-10-26)."""
    mode = automation_in_force(state)
    if mode is None or decision_id not in decision_ids(state):
        return False
    return mode == FULL_DEMO or decision_id not in DEMO_ONLY_DECISIONS


def action_covered(state: Mapping, action: Mapping | None) -> bool:
    """Whether the automatic mode in force carries out ``action`` (a ``next_action``) by
    itself: a run (the final evaluation only in ``full_demo``), the data card, and the
    proposal, confirmation or reconfirmation of a decision it covers. Never a hold, an
    interruption, a blocked step, a review, or ``done``."""
    if not action or automation_in_force(state) is None or action.get('review'):
        return False
    kind = action.get('kind')
    if kind == 'run':
        return action.get('activity') not in ('final_test.evaluation',) \
            or automation_in_force(state) == FULL_DEMO
    if kind == 'show_data_card':
        return True
    if kind in ('propose', 'reconfirm', 'await_user_words'):
        return automation_covers(state, action.get('decision'))
    return False


def review_queue(state: Mapping) -> list[str]:
    """Decisions whose current confirmation is ``automatic`` (confirmed, or waiting to be
    confirmed again), in the plan's order: each one waits for the junior's review, adopted or
    changed in their own words. Empty in a study without automation."""
    out = []
    for d in decision_ids(state):
        dec = state['decisions'][d]
        if dec['status'] in ('confirmed', 'reconfirm_required') \
                and isinstance(dec.get('confirmation'), Mapping) \
                and confirmation_basis(dec['confirmation']) == AUTOMATIC:
            out.append(d)
    return out


def opened_automatically(state: Mapping) -> bool:
    """Whether the final test was opened by the automatic mode (``full_demo``): the opening
    record carries ``basis: automatic``. Permanent: the opening cannot be redone."""
    opening = ((state.get('partition') or {}).get('opening') or {}) \
        if isinstance(state, Mapping) else {}
    return opening.get('basis') == AUTOMATIC


def reviews_automatic_opening(state: Mapping, value: Any) -> bool:
    """L9 (ADR 0006 amendment): the junior's review of a final test the demo mode opened.
    The final test was opened automatically, its decision still holds the automatic
    confirmation, and ``value`` is the configuration it opened: confirming it in the junior's
    own words adopts the opening; nothing is opened or measured again."""
    if not final_test_opened(state) or not opened_automatically(state):
        return False
    decision = (state.get('decisions') or {}).get(FINAL_TEST) or {}
    conf = decision.get('confirmation')
    if decision.get('status') != 'confirmed' or not isinstance(conf, Mapping) \
            or confirmation_basis(conf) != AUTOMATIC:
        return False
    from . import records as rec
    return rec.canonical(value) == rec.canonical(decision.get('value'))


def review_action(state: dict, decision_id: str) -> dict:
    """The review of one automatic decision (L9): the junior's words awaited on its open
    proposal, else the decision proposed again with the value automation recorded, for the
    junior to adopt or change in their own words. ``review: true`` marks it."""
    pending = sorted((p for p in open_proposals(state) if p['decision_id'] == decision_id),
                     key=lambda p: (p['revision'], p['proposal_id']))
    if pending:
        action = _await_action(state, pending[-1])
    else:
        action = {'kind': 'reconfirm', 'decision': decision_id,
                  'default_value': copy.deepcopy(state['decisions'][decision_id]['value']),
                  'message': f'Decision {decision_id} was recorded by the automatic mode, '
                             'not in the junior\'s words. Propose it again as it stands, then '
                             'ask the junior whether they adopt it in their own words or '
                             'what they change.'}
    action['review'] = True
    return action


def cited_stale_results(state: Mapping) -> list[dict]:
    """v0.3 (WP-A, R34): ``[{result_id, decision_id, proposal_id}]`` for each stale result a
    decision value (confirmed, to reconfirm, or proposed) or an open proposal names."""
    stale = set(state.get('stale') or {})

    def named(node) -> set:
        if isinstance(node, str):
            return {node} & stale
        if isinstance(node, Mapping):
            return set().union(*(named(v) for v in node.values())) if node else set()
        if isinstance(node, (list, tuple)):
            return set().union(*(named(v) for v in node)) if node else set()
        return set()

    out = []
    for d, dec in sorted((state.get('decisions') or {}).items()):
        if dec.get('status') in ('confirmed', 'reconfirm_required', 'proposed'):
            out += [{'result_id': rid, 'decision_id': d, 'proposal_id': dec.get('proposal_id')}
                    for rid in sorted(named(dec.get('value')))]
    for p in open_proposals(state):
        out += [{'result_id': rid, 'decision_id': p['decision_id'],
                 'proposal_id': p['proposal_id']} for rid in sorted(named(p.get('value')))]
    seen, unique = set(), []
    for item in out:
        key = (item['result_id'], item['decision_id'], item['proposal_id'])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _clock_value(value) -> str:
    """A value of the study's clock written exactly (review round 4, E4-4): an integer in
    full ("20170301", "1700000000", never "2.01703e+07"), a float that is a whole number as
    that integer, any other float in its shortest exact decimal form, without an exponent
    (``repr``: "20170301.5"), so the limit text names the true boundary and
    :mod:`mlkit.study.numtrace` reads it back as the recorded value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if value.is_integer():
        return str(int(value))
    import decimal
    return format(decimal.Decimal(repr(value)), 'f')


def delayed_labels_limit(state: Mapping) -> dict | None:
    """The ``delayed_labels_excluded`` limit (review 2026-10-24 round 2): how many development
    rows are left out of training, selection and validation because their outcome is known
    only at or after the final boundary; None when there are none. The text introduces the
    term, then gives an example in the study's own clock."""
    from . import partition
    n = partition.delayed_label_rows(state)
    if not n:
        return None
    part = partition.of(state) or {}
    order = part.get('order') or {}
    clock, start = order.get('by'), order.get('final_start')
    where = (f'{clock} {_clock_value(start)}' if clock and start is not None
             else 'the start of the final test')
    rows = 'row' if n == 1 else 'rows'
    return {'id': 'delayed_labels_excluded', 'n_rows': n,
            'development_rows': (part.get('development') or {}).get('n_rows'),
            'clock': clock, 'final_start': start,
            'text': (f'A delayed label is an outcome that becomes known only some time after '
                     f'the prediction is made. Here {n} development {rows} had an outcome '
                     f'known only at or after the start of the final test ({where}), the '
                     f'moment the decision is simulated, so their labels were not known yet: '
                     f'they are left out of the split, the exploration of the target, every '
                     f'fit and its validation scores, the final refit and the captured '
                     f'predictor. For example, a row predicted just before {where} whose '
                     f'outcome arrives after it would teach the model an answer nobody had '
                     f'at that moment.')}


def declared_order(state: Mapping) -> dict | None:
    """L7 (R17): the row order the study's final test follows, ``{by}`` (``line`` or a
    column), when the case declares an order and the sealed final test is temporal (the last
    rows in that order); None otherwise (no order, or a study created before the final
    test)."""
    part = state.get('partition') or {}
    if part.get('method') != 'temporal':
        return None
    return {'by': (part.get('order') or {}).get('by')}


def missing_structure(state: Mapping) -> list[str]:
    """L7 (R17): what the ``no_time_or_entity_identifier`` limit names as missing, in this
    order: ``time_column`` when the case declares neither a time column nor an order (a
    declared order makes the final test temporal), ``group_column`` when it declares no
    entity identifier."""
    structure = state['structure']
    out = []
    if structure['time_column']['value'] is None and declared_order(state) is None:
        out.append('time_column')
    if structure['group_column']['value'] is None:
        out.append('group_column')
    return out


def order_words(by) -> str:
    """How the declared order is named in a limit: the file's lines, or a column."""
    return "the order of the file's lines" if by in (None, 'line') else f'the column {by}'


def structure_limit(state: Mapping, missing: list[str]) -> dict:
    """L7 (R17): the ``no_time_or_entity_identifier`` limit, naming only what is missing;
    with a declared order, a second sentence says what the temporal final test can show (a
    shift between periods, not its cause). ``ordered_by`` is the order's ``by`` then, else
    absent."""
    if missing == ['time_column', 'group_column']:
        text = ('The data have no time column or entity identifier, so the study cannot check '
                'drift over time or repeated entities across partitions.')
    elif missing == ['time_column']:
        text = ('The data have no time column and no declared order, so the study cannot '
                'check drift over time.')
    else:
        text = ('The data have no entity identifier, so the study cannot check whether the '
                'same entity appears in several partitions.')
    item = {'id': 'no_time_or_entity_identifier', 'missing': list(missing), 'text': text}
    order = declared_order(state)
    if order is not None:
        item['ordered_by'] = order['by']
        item['text'] += (f' The rows follow a declared order ({order_words(order["by"])}) and '
                         'the final test holds the last rows in it, so the final test can show '
                         'a shift between the development period and the final period, not its '
                         'cause.')
    return item


def not_yet_defensible(state: dict) -> list[dict]:
    """What the study cannot claim yet, from state only (plan §6)."""
    items = []
    unconfirmed = [d for d in decision_ids(state) if not _confirmed(state, d)]
    if unconfirmed:
        items.append({'id': 'unconfirmed_decisions', 'decisions': unconfirmed,
                      'text': 'These decisions are not confirmed: ' + ', '.join(unconfirmed) + '.'})
    split_value = (state['decisions'].get('split') or {}).get('value')
    if is_cv_split(split_value):
        # WP-B1: out-of-fold predictions on the development rows are development evidence.
        # B6c (M3): a regression study chooses a model, not a rule.
        compared = ('the models and the variant' if task_of(state) == REGRESSION
                    else 'the models, the variant and the rule')
        items.append({'id': 'validation_is_not_independent',
                      'text': f'Out-of-fold predictions on the development rows are used to '
                              f'compare {compared}, so they are '
                              'development evidence, not independent evidence of future '
                              'performance. Only the sealed final test, opened once, is.'})
    elif task_of(state) == REGRESSION:
        items.append({'id': 'validation_is_not_independent',
                      'text': 'Validation rows are used to compare the models and to choose '
                              'one, so validation errors are not independent evidence of '
                              'future error.'})
    else:
        items.append({'id': 'validation_is_not_independent',
                      'text': 'Validation rows are used to compare models and to choose the '
                              'policy and its threshold or capacity, so validation results '
                              'are not independent evidence of future performance.'})
    delayed = delayed_labels_limit(state)
    if delayed is not None:
        items.append(delayed)
    if state['prior_exposure']:
        items.append({'id': 'public_data_already_explored',
                      'text': 'The data were explored or published before this study; its rows '
                              'are not unseen.',
                      'sources': [p['source'] for p in state['prior_exposure']]})
    structure = state['structure']
    missing = missing_structure(state)
    group = structure['group_column']['value']
    if group is not None and is_cv_split(split_value):
        # B6c (M3): the same limit in the words of the folds.
        items.append({'id': 'grouped_split_unsupported', 'column': group,
                      'capability': 'grouped split (v0.2)',
                      'text': f'Rows that share a value of {group} can fall in several folds: '
                              f'this version does not group the folds by it, so the split '
                              f'reports how many group values the folds share instead of '
                              f'preventing it. A row predicted out of fold is then not '
                              f'independent of the rows of its group the model was fitted on.'})
    elif group is not None:
        items.append({'id': 'grouped_split_unsupported', 'column': group,
                      'capability': 'grouped split (v0.2)',
                      'text': f'Rows that share a value of {group} can fall in both partitions: '
                              f'this version has no grouped split, so a split reports how many '
                              f'group values its partitions share instead of preventing it. '
                              f'Validation rows of a shared group are not independent of the '
                              f'training rows.'})
    if missing:
        items.append(structure_limit(state, missing))
    availability = state['decisions']['feature_availability']['value'] or {}
    uncertain = sorted(f for f, v in availability.items() if v == 'uncertain_included')
    if uncertain:
        items.append({'id': 'uncertain_features_included', 'features': uncertain,
                      'text': 'These features are used although their availability at prediction '
                              'time is uncertain: ' + ', '.join(uncertain) + '.'})
    holds = open_holds(state)
    if holds:
        said = '; '.join(f'"{n["user_words"]}" ({n["decision_id"]})' for n in holds)
        items.append({'id': 'open_holds', 'notes': [n['note_id'] for n in holds],
                      'decisions': sorted({n['decision_id'] for n in holds}),
                      'text': 'The junior set a condition that is not resolved yet, so these '
                              'decisions cannot be confirmed until their own words resolve it: '
                              + said + '.'})
    conclusion = state['decisions'].get('conclusion') or {}
    if conclusion.get('status') == 'reconfirm_required':
        # D2: a decision the conclusion summarizes changed after it was confirmed.
        items.append({'id': 'conclusion_outdated', 'decisions': ['conclusion'],
                      'reason': conclusion.get('reason'),
                      'text': 'The conclusion was confirmed before a decision it summarizes '
                              'changed, so its text may no longer describe the study: rewrite '
                              'it if needed and ask the junior to confirm it again.'})
    choice = choice_decision(state)
    verdict = (conclusion.get('value') or {}).get('verdict') \
        if isinstance(conclusion.get('value'), Mapping) else None
    if verdict == 'inconclusive' and conclusion.get('status') in ('confirmed', 'reconfirm_required') \
            and not _confirmed(state, choice):
        # D6: an inconclusive conclusion without an adopted policy (or a chosen model).
        what = 'no policy is adopted' if choice == 'policy' else 'no model is chosen'
        items.append({'id': 'inconclusive_without_choice', 'decisions': [choice],
                      'text': f'The conclusion is inconclusive and {what}: the study recommends '
                              'nothing to act on yet; it records why and what would settle it.'})
    delegated = delegated_decisions(state)
    if delegated:
        items.append({'id': 'delegated_decisions', 'decisions': delegated,
                      'text': 'Decided by delegation to the assistant\'s default, not by the '
                              'junior\'s own judgment: ' + ', '.join(delegated) + '.'})
    automatic = review_queue(state)
    if automatic:
        # L9 (R20): an automatic study is not defensible until each automatic decision is
        # reviewed (adopted or changed) in the junior's own words.
        items.append({'id': 'automatic_decisions_to_review', 'decisions': automatic,
                      'text': 'Automatic study: not defensible until reviewed. Recorded by the '
                              'automatic mode chosen at launch, not in the junior\'s words: '
                              + ', '.join(automatic) + '. The junior adopts or changes each '
                              'one in their own words.'})
    if opened_automatically(state):
        # L9 (ADR 0006 amendment): permanent; the opening cannot be redone.
        items.append({'id': 'final_test_opened_automatically',
                      'text': 'The final test was opened automatically by the demonstration '
                              'mode, not by the junior\'s decision. Its one evaluation stands '
                              'and the opening cannot be redone; any change made since is '
                              'marked as made after the final test.'})
    current_stale = sorted(rid for rid in state['stale']
                           if rid != state.get('current', {}).get('policy.inspection'))
    if current_stale:
        # v0.3 (WP-A, R34): a stale result reaches the junior only when a junior surface
        # cites it (a decision or an open proposal names it, as ``motivated_by`` does);
        # otherwise it is the agent's to recompute, and not a limit of the study for them.
        cited = cited_stale_results(state)
        items.append({'id': 'stale_results', 'results': current_stale,
                      'cited_by': cited, 'junior': bool(cited),
                      'text': 'Some results are stale and must be recomputed before they are cited.'})
    if state['executions']['interrupted']:
        items.append({'id': 'interrupted_executions',
                      'executions': sorted(state['executions']['interrupted']),
                      'text': 'An execution has an unknown outcome.'})
    items.append({'id': 'no_causality',
                  'text': 'Associations in observational data do not show that acting on a '
                          'variable would change the outcome.'})
    items.append({'id': 'workbench_not_tracked',
                  'text': 'Experiments in the notebook workbench are not recorded and are not '
                          'decisions.'})
    return items
