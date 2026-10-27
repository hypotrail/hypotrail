"""Whether the study panel is on, at which stage, where it shows the current step, and
where it shows what the command just produced (owner session 2026-10-26, remarks R1 and
R1b; contract P1, CLI-CONTRACT §17.1: ``next_action.panel`` version 2).

The flagged study panel (``clients/vscode-companion``, ADR 0003, ADR 0004) is off by
default. The agent's chat names the place of the panel that shows a step only when the
panel is on, so the engine tells it, in ``next_action.panel``. The rules are the
extension's own (``clients/vscode-companion/lib/flag.js``):

* on when the environment variable ``HYPOTRAIL_COMPANION`` is exactly ``1``, or when the
  study's ``.vscode/settings.json`` sets ``"hypotrail.companion.enabled": true`` (JSON
  ``true`` only). The terminal an agent runs the CLI in inherits VS Code's environment.
  The file is read as VS Code writes it (comments and trailing commas allowed); a file
  that cannot be read or parsed reads as no setting. User-level settings are not visible
  here: the environment variable covers them;
* the stage is ``HYPOTRAIL_COMPANION_STAGE`` when set and not empty, else the setting
  ``hypotrail.companion.stage``, else ``v0``; a known stage stays, a higher ``vN`` reads as
  the highest known, anything else as ``v0`` (``normalizeStage``).

Version 2 (ADR 0004 decision 13: one page instead of tabs). The panel is one page of
blocks (COMPANION-ADVANCED §6): **Now** (what the chat waits for), **To handle** (an
interrupted run, stale deliverables, the checks, changed sources, a result whose integrity
failed), **the path** (the plan's steps with their decisions, bases, headlines and
figures) and the **Tools** drawers (the data, What if?, my notions, the deliverables). The
engine names a place by an **anchor** (:data:`ANCHOR_RE`): ``now``, ``todo:<kind>``,
``path``, ``path:<step_id>``, ``path:<step_id>/<slot>``, ``tools:<drawer>``; the panel gives
the element of each anchor the attribute ``data-anchor`` with that exact string.

``where`` names the place of the *next* step (:func:`where_anchor`); ``shown`` names the
place that shows what *this* command produced (:func:`shown_anchor`), or is null when it
produced nothing the panel shows (a read, a failed run). A place the stage does not show
reads as the closest place it shows (:func:`at_stage`). The labels and the lines are the
panel's copy, verbatim (``media/copy/page.js`` and ``media/copy-fr/page.js`` keys
``anchors``, ``contents``, ``drawers``; the step names are ``media/copy*/overview.js``
``journeyLabels``), checked equal by ``clients/vscode-companion/test/test_panel_labels.py``.
The engine never writes a panel setting and the panel's behaviour does not depend on this
module.

Pure apart from reading the environment and that one settings file; it writes nothing.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable, Mapping

ENV_VAR = 'HYPOTRAIL_COMPANION'
STAGE_ENV = 'HYPOTRAIL_COMPANION_STAGE'
SETTINGS = '.vscode/settings.json'          # launch.SETTINGS
SETTING_ENABLED = 'hypotrail.companion.enabled'
SETTING_STAGE = 'hypotrail.companion.stage'
STAGES = ('v0', 'v1', 'v2', 'v3')
DEFAULT_STAGE = 'v0'

# Contract P1 (CLI-CONTRACT §17.1): the version of ``next_action.panel``; the digest gives it
# as ``panel_contract`` (§17.1.5). Version 1 was the tab form, which had no ``version`` key.
PANEL_CONTRACT = 2
PANEL_KEYS = ('version', 'stage', 'title', 'where', 'shown')
WHERE_KEYS = ('anchor', 'label', 'line')
SHOWN_KEYS = ('anchor', 'label', 'line')

TODO_KINDS = ('execution', 'deliverables', 'checks', 'sources', 'integrity')
DRAWERS = ('data', 'whatif', 'notions', 'deliverables')
ANCHOR_RE = re.compile(
    r'now|todo:(?:execution|deliverables|checks|sources|integrity)|path'
    r'|path:[a-z][a-z0-9_]*(?:/\S+)?|tools:(?:data|whatif|notions|deliverables)')
# The first stage that shows each place (CLI-CONTRACT §17.1.1). ``path:<step>`` is a v0
# place, ``path:<step>/<slot>`` (a figure in the step's detail) a v2 one.
ANCHOR_STAGE = {'now': 'v0', 'todo:execution': 'v0', 'todo:deliverables': 'v0',
                'todo:checks': 'v1', 'todo:sources': 'v0', 'todo:integrity': 'v0',
                'path': 'v0', 'path:step': 'v0', 'path:figure': 'v2',
                'tools:data': 'v2', 'tools:whatif': 'v2', 'tools:notions': 'v3',
                'tools:deliverables': 'v0'}
# The contents of Now (§17.1.4); ``figure:<slot>`` and the data card from v2 (Now has no
# figure below v2).
CONTENTS = ('data_card', 'question', 'review', 'reopened', 'choice', 'hold', 'answer_rules',
            'running', 'blocked', 'done')
FIGURE_CONTENTS_FROM = 'v2'

# The panel's copy, verbatim (media/copy*/page.js, media/copy*/overview.js journeyLabels).
TITLES = {'en': 'Hypotrail study', 'fr': 'Étude Hypotrail'}
ANCHOR_LABELS = {
    'en': {'now': 'Now', 'todo': 'To handle', 'path': 'the path',
           'path_ledger': 'its ledger line', 'tools': 'Tools',
           'todo:execution': 'the interrupted run',
           'todo:deliverables': 'the deliverables out of date',
           'todo:checks': 'the checks of the deliverables',
           'todo:sources': 'the changed sources',
           'todo:integrity': 'a result that failed its integrity check'},
    'fr': {'now': 'Maintenant', 'todo': 'À traiter', 'path': 'le parcours',
           'path_ledger': 'sa ligne de registre', 'tools': 'Outils',
           'todo:execution': "l'exécution interrompue",
           'todo:deliverables': 'les livrables périmés',
           'todo:checks': 'les vérifications des livrables',
           'todo:sources': 'les sources modifiées',
           'todo:integrity': "un résultat dont l'intégrité a échoué"},
}
CONTENT_LABELS = {
    'en': {'data_card': 'the data card', 'question': 'the question waiting for you',
           'review': 'the decision to review', 'reopened': 'the decision to confirm again',
           'choice': 'the options to choose from', 'hold': 'your condition on hold',
           'answer_rules': 'what counts as your answer', 'running': 'the step being computed',
           'blocked': 'what the step waits for', 'done': 'what the study can claim'},
    'fr': {'data_card': 'la fiche des données', 'question': 'la question qui vous attend',
           'review': 'la décision à relire', 'reopened': 'la décision à confirmer de nouveau',
           'choice': 'les options du choix', 'hold': 'votre condition en suspens',
           'answer_rules': 'ce qui compte comme votre réponse',
           'running': "l'étape en calcul", 'blocked': "ce que l'étape attend",
           'done': "ce que l'étude peut affirmer"},
}
DRAWER_LABELS = {
    'en': {'data': 'The data', 'whatif': 'What if? (without deciding)', 'notions': 'My notions',
           'deliverables': 'Deliverables'},
    'fr': {'data': 'Les données', 'whatif': 'Et si ? (sans décider)', 'notions': 'Mes notions',
           'deliverables': 'Livrables'},
}
STEP_LABELS = {
    'en': {'discover_data': 'Data', 'prediction_time': 'Moment',
           'feature_availability': 'Variables', 'split': 'Split',
           'success_criterion': 'Criterion', 'structural_eda': 'Quality',
           'train_eda': 'Explore', 'preprocessing': 'Preparation', 'models': 'Models',
           'model_variant': 'Variants', 'policy': 'Rule', 'model_choice': 'Choice',
           'final_test': 'Final test', 'conclusion': 'Conclusion'},
    'fr': {'discover_data': 'Données', 'prediction_time': 'Moment',
           'feature_availability': 'Variables', 'split': 'Découpage',
           'success_criterion': 'Critère', 'structural_eda': 'Qualité',
           'train_eda': 'Exploration', 'preprocessing': 'Préparation', 'models': 'Modèles',
           'model_variant': 'Variantes', 'policy': 'Règle', 'model_choice': 'Choix',
           'final_test': 'Test final', 'conclusion': 'Conclusion'},
}
# An EDA figure is named by its card's name (the first part of the eyebrow of the panel's
# chart, media/copy*/eda.js ``eyebrows``), then its column for a per-column chart.
EDA_CARD_LABELS = {
    'en': {'eda.quality': 'Data quality', 'eda.target_rate': 'Outcome rate',
           'eda.target_summary': 'Target', 'eda.special_values': 'Special values',
           'eda.rate_by': 'Outcome rate by group', 'eda.mean_by': 'Target mean by group',
           'eda.single_feature_signal': 'Single-feature signal',
           'eda.correlation': 'Correlation', 'eda.distribution': 'Distribution'},
    'fr': {'eda.quality': 'Qualité des données', 'eda.target_rate': 'Taux de résultat',
           'eda.target_summary': 'Cible', 'eda.special_values': 'Valeurs spéciales',
           'eda.rate_by': 'Taux de résultat par groupe',
           'eda.mean_by': 'Moyenne de la cible par groupe',
           'eda.single_feature_signal': 'Signal par variable',
           'eda.correlation': 'Corrélation', 'eda.distribution': 'Distribution'},
}
# The other figures, by activity (§17.1.4).
FIGURE_LABELS = {
    'en': {'split': 'the split', 'models': 'the model comparison', 'variants': 'the variants',
           'diagnostics': 'the diagnostics', 'final_test': 'the final test result'},
    'fr': {'split': 'le découpage', 'models': 'la comparaison des modèles',
           'variants': 'les variantes', 'diagnostics': 'les diagnostics',
           'final_test': 'le résultat du test final'},
}
# The line the agent starts a message with (CLAUDE.md rule 6), by place.
LINES = {
    'en': {'now': 'In the panel: Now, {content}.', 'todo': 'In the panel: To handle, {kind}.',
           'path': 'In the panel: the path, its ledger line.',
           'path_step': 'In the panel: the path, {step}.',
           'path_figure': 'In the panel: the path, {step} → {figure}.',
           'tools': 'In the panel: Tools → {drawer}.'},
    'fr': {'now': 'Dans le panneau : Maintenant, {content}.',
           'todo': 'Dans le panneau : À traiter, {kind}.',
           'path': 'Dans le panneau : le parcours, sa ligne de registre.',
           'path_step': 'Dans le panneau : le parcours, {step}.',
           'path_figure': 'Dans le panneau : le parcours, {step} → {figure}.',
           'tools': 'Dans le panneau : Outils → {drawer}.'},
}

# The commands that only read: they produce nothing new, so ``shown`` is null, except at
# step 0 (the data card) and at a choice the chat asks (R16), where the next action itself
# is what the message shows.
READ_COMMANDS = ('status', 'plan')
# A run whose result the panel shows (``executions`` statuses).
SHOWN_RUN_STATUSES = ('promoted', 'already_current')
INTERRUPTED = 'interrupted_unknown'
OPENED = ('promoted', 'already_current', 'opened')
# Activities that compute nothing the panel draws (a capture of the predictor).
NO_FIGURE = ('predictor.capture',)
EXECUTION_KINDS = ('outcome_unknown', 'acknowledge_interruption')
MODEL_FIGURES = ('policy.evaluation', 'policy.evaluate', 'evaluate.regression')
FINAL_ACTIVITIES = ('final_test.evaluation', 'diag.final_test')


def _strip_jsonc(text: str) -> str:
    """``text`` without ``//`` and ``/* */`` comments and trailing commas, strings kept."""
    out, i, n, in_string = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
        elif text.startswith('//', i):
            end = text.find('\n', i)
            i = n if end < 0 else end
        elif text.startswith('/*', i):
            end = text.find('*/', i + 2)
            i = n if end < 0 else end + 2
        else:
            out.append(ch)
            i += 1
    text, out, in_string = ''.join(out), [], False
    for i, ch in enumerate(text):
        if in_string:
            if ch == '"' and not _escaped(text, i):
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == ',':
            rest = text[i + 1:].lstrip()
            if rest[:1] in ('}', ']'):
                continue
        out.append(ch)
    return ''.join(out)


def _escaped(text: str, i: int) -> bool:
    count = 0
    while i - count - 1 >= 0 and text[i - count - 1] == '\\':
        count += 1
    return count % 2 == 1


def read_settings(study_dir) -> dict:
    """The study's ``.vscode/settings.json`` as a dict; ``{}`` when absent or unreadable."""
    try:
        text = (Path(study_dir) / SETTINGS).read_text(encoding='utf-8')
        data = json.loads(_strip_jsonc(text))
    except (OSError, UnicodeDecodeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def normalize_stage(raw) -> str:
    """``flag.js`` ``normalizeStage``: a known stage, the highest known for a higher
    ``vN``, else ``v0``."""
    if raw in STAGES:
        return raw
    m = re.fullmatch(r'v([0-9]{1,3})', raw) if isinstance(raw, str) else None
    if m and int(m.group(1)) > len(STAGES) - 1:
        return STAGES[-1]
    return DEFAULT_STAGE


def enabled(study_dir, env: Mapping | None = None, settings: Mapping | None = None) -> bool:
    env = os.environ if env is None else env
    if env.get(ENV_VAR) == '1':
        return True
    settings = read_settings(study_dir) if settings is None else settings
    return settings.get(SETTING_ENABLED) is True


def stage(study_dir, env: Mapping | None = None, settings: Mapping | None = None) -> str:
    env = os.environ if env is None else env
    raw = env.get(STAGE_ENV)
    if isinstance(raw, str) and raw:
        return normalize_stage(raw)
    settings = read_settings(study_dir) if settings is None else settings
    return normalize_stage(settings.get(SETTING_STAGE, DEFAULT_STAGE))


def _lang(lang) -> str:
    return lang if lang in TITLES else 'en'


def _rank(stage_id: str) -> int:
    return STAGES.index(stage_id)


# --- the step of a result -------------------------------------------------------------------

def step_of(activity: str | None, slot: str | None, plan: Iterable[Mapping],
            target_read: bool | None = None) -> str | None:
    """The plan step that files a result (§17.1.1): the first step whose ``activities`` lists
    its slot or its activity; else, for an ``eda.*`` activity, ``structural_eda`` when the
    result read no target (``target_read`` False) and the plan has that step, else
    ``train_eda``; else ``models`` for ``fit.*`` and ``diag.*``; else the step of the
    decision the activity serves (``final_test`` for the final evaluation and its
    diagnostics). None when the plan has none of them."""
    plan = list(plan or [])
    ids = [s.get('id') for s in plan]
    activity = str(activity or '')
    slot = str(slot or activity)
    for wanted in (slot, activity):
        for step in plan:
            if wanted and wanted in (step.get('activities') or ()):
                return step.get('id')

    def first(*candidates):
        return next((c for c in candidates if c in ids), None)
    if activity in FINAL_ACTIVITIES:
        return first('final_test')
    if activity.startswith('eda.'):
        if target_read is False:
            return first('structural_eda', 'train_eda')
        return first('train_eda', 'structural_eda')
    if activity.startswith(('fit.', 'diag.')):
        return first('models')
    if activity in MODEL_FIGURES:
        return first('policy', 'model_choice', 'models')
    if activity == 'split':
        return first('split')
    return None


def decision_step(decision: str | None, plan: Iterable[Mapping]) -> str | None:
    """The plan step whose decision is ``decision``."""
    return next((s.get('id') for s in plan or () if decision and s.get('decision') == decision),
                None)


def current_step(action: Mapping | None, plan: Iterable[Mapping]) -> str | None:
    """The step of a ``next_action``: its ``step``, else the step of its ``decision``."""
    action = action or {}
    return action.get('step') or decision_step(action.get('decision'), plan)


# --- labels and lines -----------------------------------------------------------------------

def figure_label(slot: str, lang: str = 'en') -> str:
    """The name of the figure of result ``slot`` (§17.1.4): an EDA card's name (and its
    column), else the figure of its activity."""
    lang = _lang(lang)
    activity, _, column = str(slot).partition(':')
    if activity.startswith('eda.'):
        name = EDA_CARD_LABELS[lang].get(activity, activity)
        return f'{name} · {column}' if column else name
    names = FIGURE_LABELS[lang]
    if activity == 'split':
        return names['split']
    if activity == 'fit.variant':
        return names['variants']
    if activity in FINAL_ACTIVITIES[:1]:
        return names['final_test']
    if activity.startswith('diag.'):
        return names['diagnostics']
    return names['models']


def step_label(step_id: str, lang: str = 'en') -> str:
    lang = _lang(lang)
    return STEP_LABELS[lang].get(step_id, str(step_id).replace('_', ' '))


def content_label(content: str, lang: str = 'en') -> str:
    lang = _lang(lang)
    if content.startswith('figure:'):
        return figure_label(content.split(':', 1)[1], lang)
    return CONTENT_LABELS[lang][content]


def line_of(anchor: str, content: str | None = None, lang: str = 'en') -> str:
    """The ready sentence that names ``anchor`` (with ``content`` for ``now``)."""
    lang = _lang(lang)
    lines = LINES[lang]
    if anchor == 'now':
        return lines['now'].format(content=content_label(content or 'question', lang))
    if anchor.startswith('todo:'):
        return lines['todo'].format(kind=ANCHOR_LABELS[lang][anchor])
    if anchor.startswith('tools:'):
        return lines['tools'].format(drawer=DRAWER_LABELS[lang][anchor.split(':', 1)[1]])
    if anchor == 'path':
        return lines['path']
    step, _, slot = anchor.split(':', 1)[1].partition('/')
    if slot:
        return lines['path_figure'].format(step=step_label(step, lang),
                                           figure=figure_label(slot, lang))
    return lines['path_step'].format(step=step_label(step, lang))


def label_of(line: str) -> str:
    """The part of a line after its first colon, without the final period."""
    text = line.split(':', 1)[1].strip()
    return text[:-1] if text.endswith('.') else text


def place(anchor: str | None, content: str | None = None, lang: str = 'en') -> dict | None:
    """``{anchor, label, line}`` of a place, or None."""
    if anchor is None:
        return None
    line = line_of(anchor, content, lang)
    return {'anchor': anchor, 'label': label_of(line), 'line': line}


# --- where and shown ------------------------------------------------------------------------

def _anchor_stage(anchor: str) -> str:
    if anchor.startswith('path:'):
        return ANCHOR_STAGE['path:figure' if '/' in anchor else 'path:step']
    return ANCHOR_STAGE[anchor]


def at_stage(anchor: str | None, content: str | None, stage_id: str
             ) -> tuple[str | None, str | None]:
    """``(anchor, content)`` as the panel at ``stage_id`` shows them (§17.1.3, stage
    fallback): a figure in Now or the data card below v2 reads as Now's question; a figure
    of the path below v2 as its step; the checks at v0 as the Deliverables drawer; the data
    and What if? drawers below v2 as Now; My notions below v3 as nothing."""
    if anchor is None:
        return None, None
    rank = _rank(stage_id)
    if anchor == 'now':
        if content is not None and (content == 'data_card' or content.startswith('figure:')) \
                and rank < _rank(FIGURE_CONTENTS_FROM):
            return 'now', 'question'
        return 'now', content
    if rank >= _rank(_anchor_stage(anchor)):
        return anchor, content if anchor == 'now' else None
    if anchor.startswith('path:'):
        return anchor.split('/', 1)[0], None
    if anchor == 'todo:checks':
        return 'tools:deliverables', None
    if anchor in ('tools:data', 'tools:whatif'):
        return 'now', 'question'
    return None, None


def now_content(action: Mapping | None) -> str:
    """What Now shows for a next action (§17.1.4): the data card, a review, a decision to
    confirm again, a choice, a held condition, a question, a step being computed, a blocked
    step, or what the study can claim."""
    action = action or {}
    kind = action.get('kind')
    if kind == 'show_data_card':
        return 'data_card'
    if kind == 'run':
        return 'running'
    if kind == 'blocked':
        return 'blocked'
    if kind == 'done':
        return 'done'
    if kind == 'resolve_hold':
        return 'hold'
    if action.get('review'):
        return 'review'
    if action.get('choice_options'):
        return 'choice'
    if kind == 'reconfirm':
        return 'reopened'
    return 'question'


def where_anchor(action: Mapping | None) -> tuple[str, str | None]:
    """``(anchor, content)`` of the next step (§17.1.2): an unknown or interrupted run in To
    handle, everything else in Now."""
    action = action or {}
    if action.get('kind') in EXECUTION_KINDS:
        return 'todo:execution', None
    return 'now', now_content(action)


def where(action: Mapping | None, stage_id: str, lang: str = 'en') -> dict:
    """``{anchor, label, line}`` (``WHERE_KEYS``): where the panel at ``stage_id`` shows the
    step of ``action``."""
    anchor, content = at_stage(*where_anchor(action), stage_id)
    return place(anchor, content, lang)


def _run_anchor(produced: Mapping, action: Mapping, plan) -> tuple[str | None, str | None]:
    status = produced.get('status')
    if status == INTERRUPTED:
        return 'todo:execution', None
    activity = str(produced.get('activity') or '')
    if status not in SHOWN_RUN_STATUSES or activity in NO_FIGURE:
        return None, None
    slot = str(produced.get('slot') or activity)
    step = step_of(activity, slot, plan, produced.get('target_read'))
    if step is None:
        return None, None
    if step == current_step(action, plan):
        return 'now', f'figure:{slot}'
    return f'path:{step}/{slot}', None


def _decide_anchor(produced: Mapping, action: Mapping, plan) -> tuple[str | None, str | None]:
    kind = produced.get('action')
    if kind in ('decide.propose', 'decide.resolve_note'):
        return 'now', 'review' if action.get('review') else 'question'
    if kind == 'decide.note':
        if produced.get('kind') == 'correction':
            step = decision_step(produced.get('decision_id'), plan)
            return (f'path:{step}', None) if step else ('path', None)
        return 'now', 'hold'
    if kind == 'study.set_mode':
        return 'now', 'answer_rules'
    if kind == 'decide.confirm':
        opening = produced.get('opening') or {}
        if opening.get('status') in OPENED:
            return 'path:final_test/final_test.evaluation', None
    if kind in ('decide.confirm', 'decide.withdraw'):
        step = decision_step(produced.get('decision_id'), plan)
        return (f'path:{step}', None) if step else ('path', None)
    return None, None                   # decide.withdraw_note: nothing new is shown


def shown_anchor(produced: Mapping | None, action: Mapping | None,
                 plan: Iterable[Mapping] = ()) -> tuple[str | None, str | None]:
    """``(anchor, content)`` of what the command reported (§17.1.3), before the stage is
    considered; ``(None, None)`` when it produced nothing the panel shows. ``produced`` is
    ``{command, action?, activity?, slot?, status?, opening?, kind?, decision_id?,
    target_read?}``; an absent ``produced`` reads as a read. D3: a command that produced
    something names it, even when the next action is a choice."""
    produced = produced or {}
    action = action or {}
    plan = list(plan or ())
    command = produced.get('command')
    if command in (None, 'init') + READ_COMMANDS:
        if action.get('kind') == 'show_data_card':
            return 'now', 'data_card'
        if command != 'init' and action.get('choice_options'):
            return 'now', 'choice'
        return None, None
    if command == 'run':
        return _run_anchor(produced, action, plan)
    if command == 'decide':
        return _decide_anchor(produced, action, plan)
    return None, None


def shown(produced: Mapping | None, action: Mapping | None, stage_id: str, lang: str = 'en',
          plan: Iterable[Mapping] = ()) -> dict | None:
    """``{anchor, label, line}`` (``SHOWN_KEYS``): where the panel at ``stage_id`` shows what
    the command produced, or None."""
    anchor, content = at_stage(*shown_anchor(produced, action, plan), stage_id)
    return place(anchor, content, lang)


def panel(action: Mapping | None, study_dir, lang: str = 'en',
          env: Mapping | None = None, produced: Mapping | None = None,
          plan: Iterable[Mapping] | None = None) -> dict | None:
    """``next_action.panel`` (``PANEL_KEYS``, version 2) when the panel is on, else None.
    ``plan`` is the study's plan (``state.derive_plan``), read from the study when not
    given; it files a result under its step."""
    settings = read_settings(study_dir)
    if not enabled(study_dir, env, settings):
        return None
    lang = _lang(lang)
    stage_id = stage(study_dir, env, settings)
    if plan is None:
        plan = _plan_of(study_dir)
    return {'version': PANEL_CONTRACT, 'stage': stage_id, 'title': TITLES[lang],
            'where': where(action, stage_id, lang),
            'shown': shown(produced, action, stage_id, lang, plan)}


def _plan_of(study_dir) -> list[dict]:
    try:
        from . import read, state as st
        return st.derive_plan(read.open(Path(study_dir)).state)
    except Exception:                    # noqa: BLE001 - no plan: a result has no step
        return []


def annotate(action, study_dir, lang: str = 'en', env: Mapping | None = None,
             produced: Mapping | None = None, plan: Iterable[Mapping] | None = None):
    """Add ``panel`` (last key) to the ``next_action`` dict ``action`` in place when the
    panel is on; ``action`` unchanged (no key) otherwise. Returns ``action``. ``produced``
    describes the command whose output carries ``action`` (:func:`shown_anchor`)."""
    if isinstance(action, dict):
        found = panel(action, study_dir, lang, env, produced, plan)
        if found is not None:
            action['panel'] = found
    return action


__all__ = ['ENV_VAR', 'STAGE_ENV', 'SETTINGS', 'SETTING_ENABLED', 'SETTING_STAGE', 'STAGES',
           'PANEL_CONTRACT', 'PANEL_KEYS', 'WHERE_KEYS', 'SHOWN_KEYS', 'ANCHOR_RE',
           'TODO_KINDS', 'DRAWERS', 'TITLES', 'ANCHOR_LABELS', 'CONTENT_LABELS', 'DRAWER_LABELS',
           'STEP_LABELS', 'EDA_CARD_LABELS', 'FIGURE_LABELS', 'LINES', 'read_settings',
           'normalize_stage', 'enabled', 'stage', 'step_of', 'at_stage', 'where_anchor',
           'shown_anchor', 'where', 'shown', 'panel', 'annotate']
