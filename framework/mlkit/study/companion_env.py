"""Whether the study panel is on, at which stage, where it shows the current step, and
where it shows what the command just produced (owner session 2026-10-26, remarks R1 and
R1b; CLI-CONTRACT §3.2, ``next_action.panel``).

The flagged study panel (``clients/vscode-companion``, ADR 0003, ADR 0004) is off by
default. The agent's chat names the panel tab that shows a step only when the panel is on,
so the engine tells it, in ``next_action.panel``. The rules are the extension's own
(``clients/vscode-companion/lib/flag.js``):

* on when the environment variable ``HYPOTRAIL_COMPANION`` is exactly ``1``, or when the
  study's ``.vscode/settings.json`` sets ``"hypotrail.companion.enabled": true`` (JSON
  ``true`` only). The terminal an agent runs the CLI in inherits VS Code's environment.
  The file is read as VS Code writes it (comments and trailing commas allowed); a file
  that cannot be read or parsed reads as no setting. User-level settings are not visible
  here: the environment variable covers them;
* the stage is ``HYPOTRAIL_COMPANION_STAGE`` when set and not empty, else the setting
  ``hypotrail.companion.stage``, else ``v0``; a known stage stays, a higher ``vN`` reads as
  the highest known, anything else as ``v0`` (``normalizeStage``).

The tabs of each stage and their labels, in the study language, are the panel's
(``media/views/*.js`` register each view with its tab and stage; ``media/copy/core.js`` and
``media/copy-fr/core.js`` hold ``title`` and ``tabs``); a test checks they are equal
(``clients/vscode-companion/test/test_panel_labels.py``). The engine never writes a panel
setting and the panel's behaviour does not depend on this module.

``where`` names the tab of the *next* step; ``shown`` (R1b) names the tab and the section
that show what *this* command produced (a proposal under "Waiting for your answer", a
confirmation in "Decision history", a fit in "Development evidence", a chart by its card),
or is null when it produced nothing the panel shows (a read, a failed run). The section
headings are the panel's copy, verbatim, checked by the same test.

Pure apart from reading the environment and that one settings file; it writes nothing.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Mapping

ENV_VAR = 'HYPOTRAIL_COMPANION'
STAGE_ENV = 'HYPOTRAIL_COMPANION_STAGE'
SETTINGS = '.vscode/settings.json'          # launch.SETTINGS
SETTING_ENABLED = 'hypotrail.companion.enabled'
SETTING_STAGE = 'hypotrail.companion.stage'
STAGES = ('v0', 'v1', 'v2', 'v3')
DEFAULT_STAGE = 'v0'
# The panel's tab order (media/core.js TAB_ORDER) and the stage each tab appears at
# (media/views/<tab>.js). Until v1 the panel is one page without tabs (``tabbed``).
TAB_ORDER = ('overview', 'eda', 'decisions', 'evidence', 'whatif', 'learn')
TAB_STAGE = {'overview': 'v0', 'decisions': 'v0', 'eda': 'v2', 'evidence': 'v2',
             'whatif': 'v2', 'learn': 'v3'}
TABBED_FROM = 'v1'
# The panel's copy, verbatim (media/copy/core.js, media/copy-fr/core.js).
TITLES = {'en': 'Hypotrail study', 'fr': 'Étude Hypotrail'}
TAB_LABELS = {
    'en': {'overview': 'Overview', 'eda': 'Data & EDA', 'decisions': 'Decisions',
           'evidence': 'Evidence', 'whatif': 'What if?', 'learn': 'Learn & hand off'},
    'fr': {'overview': "Vue d'ensemble", 'eda': 'Données et EDA', 'decisions': 'Décisions',
           'evidence': 'Preuves', 'whatif': 'Et si ?', 'learn': 'Apprendre et transmettre'},
}
# The line the agent ends a message with (CLAUDE.md rule 6).
LINES = {'en': {'tab': 'In the panel: the {label} tab.', 'page': 'In the "{label}" panel.'},
         'fr': {'tab': 'Dans le panneau : onglet {label}.', 'page': 'Dans le panneau « {label} ».'}}
PANEL_KEYS = ('stage', 'title', 'tabs', 'where', 'shown')
WHERE_KEYS = ('tab', 'label', 'line')
# Owner session 2026-10-26, R1b: where the panel shows what the command just produced.
SHOWN_KEYS = ('tab', 'section', 'label', 'line')
# The sections the engine names: their tab and the stage from which the panel shows them
# (media/views/*.js). A section of an EDA card is the card's slot (``eda.rate_by:job``).
SECTIONS = {'data_card': ('eda', 'v2'), 'quality': ('eda', 'v2'), 'eda_card': ('eda', 'v2'),
            'waiting': ('decisions', 'v0'), 'holds': ('decisions', 'v0'),
            'choice': ('decisions', 'v1'), 'history': ('decisions', 'v1'),
            'mode': ('decisions', 'v1'), 'development': ('evidence', 'v2'),
            'diagnostics': ('evidence', 'v2'), 'final_test': ('evidence', 'v2')}
# The panel's headings of these sections, verbatim (media/copy*/eda.js ``data.cardTitle``,
# ``qualityTitle``; media/copy*/decisions.js ``waitingTitle`` (also the heading of the
# choice card, R16), ``holdsTitle``, ``historyTitle``, ``modeTitle``; media/copy*/evidence.js
# ``developmentTitle``, ``diagnosticsTitle``, ``finalTitle``). Checked by
# clients/vscode-companion/test/test_panel_labels.py.
SECTION_LABELS = {
    'en': {'data_card': 'Data card', 'quality': 'Data quality',
           'waiting': 'Waiting for your answer', 'choice': 'Waiting for your answer',
           'holds': 'On hold', 'history': 'Decision history',
           'mode': 'What counts as your answer',
           'development': 'Development evidence · used to choose',
           'diagnostics': 'Diagnostics', 'final_test': 'Final test'},
    'fr': {'data_card': 'Fiche des données', 'quality': 'Qualité des données',
           'waiting': 'En attente de votre réponse', 'choice': 'En attente de votre réponse',
           'holds': 'En suspens', 'history': 'Historique des décisions',
           'mode': 'Ce qui compte comme votre réponse',
           'development': 'Preuves de développement · ont servi à choisir',
           'diagnostics': 'Diagnostics', 'final_test': 'Test final'},
}
# An EDA card is named by the first part of its eyebrow (media/copy*/eda.js ``eyebrows``,
# the text before " · "), then its column for a per-column chart ("Distribution · age").
EDA_CARD_LABELS = {
    'en': {'eda.target_rate': 'Outcome rate', 'eda.target_summary': 'Target',
           'eda.special_values': 'Special values', 'eda.rate_by': 'Outcome rate by group',
           'eda.mean_by': 'Target mean by group',
           'eda.single_feature_signal': 'Single-feature signal',
           'eda.correlation': 'Correlation', 'eda.distribution': 'Distribution'},
    'fr': {'eda.target_rate': 'Taux de résultat', 'eda.target_summary': 'Cible',
           'eda.special_values': 'Valeurs spéciales',
           'eda.rate_by': 'Taux de résultat par groupe',
           'eda.mean_by': 'Moyenne de la cible par groupe',
           'eda.single_feature_signal': 'Signal par variable',
           'eda.correlation': 'Corrélation', 'eda.distribution': 'Distribution'},
}
SHOWN_LINES = {'en': {'tab': 'In the panel: {tab} → {section}.',
                      'page': 'In the "{title}" panel: {section}.'},
               'fr': {'tab': 'Dans le panneau : {tab} → {section}.',
                      'page': 'Dans le panneau « {title} » : {section}.'}}
# The commands that only read: they produce nothing new, so ``shown`` is null, except at
# step 0 (the data card) and at a choice the chat asks (R16), where the next action itself
# is what the message shows.
READ_COMMANDS = ('status', 'plan')
# A run whose result the panel shows (``executions`` statuses).
SHOWN_RUN_STATUSES = ('promoted', 'already_current')
OPENED = ('promoted', 'already_current', 'opened')
# The tab that shows a step (CLAUDE.md rule 6), then the closest tabs when the stage has
# not got it.
FALLBACK = {'overview': ('overview',), 'eda': ('eda', 'overview'),
            'decisions': ('decisions', 'overview'),
            'evidence': ('evidence', 'overview'),
            'whatif': ('whatif', 'decisions', 'overview'), 'learn': ('learn', 'overview')}
CHOICE_STEPS = ('policy', 'model_choice')
DECISION_KINDS = ('propose', 'await_user_words', 'reconfirm', 'resolve_hold')


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


def tabs(stage_id: str) -> tuple[str, ...]:
    """The tabs the panel shows at ``stage_id``, in its order; none before v1 (one page)."""
    rank = STAGES.index(stage_id)
    if rank < STAGES.index(TABBED_FROM):
        return ()
    return tuple(t for t in TAB_ORDER if STAGES.index(TAB_STAGE[t]) <= rank)


def wanted_tab(action: Mapping | None) -> str:
    """The tab that shows ``action``'s step (CLAUDE.md rule 6): the data card and the
    charts in Data & EDA, a proposal in Decisions, the fits, diagnostics and final test in
    Evidence, the decision rule (a binary study) or the model choice (a regression study)
    in What if?, everything else (done, blocked, an interrupted run) in the Overview."""
    action = action or {}
    kind, step = action.get('kind'), action.get('step')
    activity = str(action.get('activity') or '')
    if kind == 'show_data_card':
        return 'eda'
    if kind == 'run':
        if activity.startswith('eda.'):
            return 'eda'
        if activity.startswith('policy.'):
            return 'whatif'
        return 'evidence'
    if kind in DECISION_KINDS:
        return 'whatif' if step in CHOICE_STEPS else 'decisions'
    return 'overview'


def where(action: Mapping | None, stage_id: str, lang: str = 'en') -> dict:
    """``{tab, label, line}``: the tab showing ``action`` at ``stage_id``, or the closest
    one the stage has; ``tab`` None (the panel's one page, named by its title) at v0."""
    lang = lang if lang in TAB_LABELS else 'en'
    present = tabs(stage_id)
    tab = next((t for t in FALLBACK[wanted_tab(action)] if t in present), None)
    if tab is None:
        label = TITLES[lang]
        return {'tab': None, 'label': label, 'line': LINES[lang]['page'].format(label=label)}
    label = TAB_LABELS[lang][tab]
    return {'tab': tab, 'label': label, 'line': LINES[lang]['tab'].format(label=label)}


def _run_section(produced: Mapping) -> str | None:
    """The section that shows the result of a ``run`` (R1b), or None (a failed or
    interrupted run, an acknowledgement, a capture: nothing the panel shows)."""
    if produced.get('status') not in SHOWN_RUN_STATUSES:
        return None
    activity = str(produced.get('activity') or '')
    slot = str(produced.get('slot') or activity)
    if activity == 'eda.quality':
        return 'quality'
    if activity.startswith('eda.'):
        return slot if slot.startswith('eda.') else activity
    if activity in ('final_test.evaluation', 'diag.final_test'):
        return 'final_test'
    if activity in ('diag.binary', 'diag.regression'):
        return 'diagnostics'
    if (activity.startswith('fit.') or activity == 'split'
            or activity in ('policy.evaluation', 'policy.evaluate', 'evaluate.regression')):
        return 'development'
    return None


def _decide_section(produced: Mapping) -> str | None:
    """The section that shows what a ``decide`` (or ``mode set``) recorded (R1b)."""
    action = produced.get('action')
    if action == 'decide.propose':
        return 'waiting'
    if action == 'decide.confirm':
        opening = produced.get('opening') or {}
        return 'final_test' if opening.get('status') in OPENED else 'history'
    if action == 'decide.withdraw':
        return 'history'               # "Proposals that were not confirmed", in the history
    if action == 'decide.note':
        return 'history' if produced.get('kind') == 'correction' else 'holds'
    if action == 'decide.resolve_note':
        return 'waiting'               # the open card shows "Your condition, resolved"
    if action == 'study.set_mode':
        return 'mode'
    return None                        # decide.withdraw_note: nothing new is shown


def shown_section(produced: Mapping | None, action: Mapping | None) -> str | None:
    """The id of the section that shows what the command reported (R1b), before the stage
    is considered: ``data_card``, ``quality``, an EDA card's slot, ``waiting``, ``holds``,
    ``history``, ``mode``, ``development``, ``diagnostics``, ``final_test``; None when the
    command produced nothing the panel shows (a read, a failed run, an acknowledgement).
    ``produced`` is ``{command, action?, activity?, slot?, status?, opening?, kind?}``; an
    absent ``produced`` reads as a read. A choice the chat asks (``choice_options``, R16) is
    handled by :func:`shown`, since its card exists from stage v1 only."""
    produced = produced or {}
    action = action or {}
    command = produced.get('command')
    if action.get('kind') == 'show_data_card' and command in (None, 'init') + READ_COMMANDS:
        return 'data_card'
    if command == 'run':
        return _run_section(produced)
    if command == 'decide':
        return _decide_section(produced)
    return None


def _section_of(section: str) -> tuple[str, str]:
    return SECTIONS['eda_card'] if section.startswith('eda.') else SECTIONS[section]


def section_label(section: str, lang: str = 'en') -> str:
    """The panel's heading of ``section`` in ``lang``, verbatim; an EDA card's name (and
    its column for a per-column chart)."""
    lang = lang if lang in SECTION_LABELS else 'en'
    if section.startswith('eda.'):
        activity, _, column = section.partition(':')
        name = EDA_CARD_LABELS[lang].get(activity, activity)
        return f'{name} · {column}' if column else name
    return SECTION_LABELS[lang][section]


def shown(produced: Mapping | None, action: Mapping | None, stage_id: str,
          lang: str = 'en') -> dict | None:
    """``{tab, section, label, line}`` (``SHOWN_KEYS``): where the panel at ``stage_id``
    shows what the command produced (R1b), or None when it produced nothing the panel shows.

    When the next action is a choice the chat asks (``choice_options``, R16), the message
    ends with that question, and from v1 the Decisions tab shows it as a read-only card
    under "Waiting for your answer": that card is named. A section of a later stage reads as
    the closest tab the stage has (``FALLBACK``, no section); at v0 the panel is one page,
    named by its title (with the section when the page shows it)."""
    lang = lang if lang in TAB_LABELS else 'en'
    rank = STAGES.index(stage_id)
    section = None
    if (action or {}).get('choice_options') and rank >= STAGES.index(SECTIONS['choice'][1]):
        section = 'choice'
    if section is None:
        section = shown_section(produced, action)
    if section is None:
        return None
    tab, since = _section_of(section)
    present = tabs(stage_id)
    if rank >= STAGES.index(since):
        label = section_label(section, lang)
        if tab in present:
            line = SHOWN_LINES[lang]['tab'].format(tab=TAB_LABELS[lang][tab], section=label)
            return {'tab': tab, 'section': section, 'label': label, 'line': line}
        if not present:
            line = SHOWN_LINES[lang]['page'].format(title=TITLES[lang], section=label)
            return {'tab': None, 'section': section, 'label': label, 'line': line}
    found = next((t for t in FALLBACK[tab] if t in present), None)
    if found is None:
        label = TITLES[lang]
        return {'tab': None, 'section': None, 'label': label,
                'line': LINES[lang]['page'].format(label=label)}
    label = TAB_LABELS[lang][found]
    return {'tab': found, 'section': None, 'label': label,
            'line': LINES[lang]['tab'].format(label=label)}


def panel(action: Mapping | None, study_dir, lang: str = 'en',
          env: Mapping | None = None, produced: Mapping | None = None) -> dict | None:
    """``next_action.panel`` (``PANEL_KEYS``) when the panel is on, else None."""
    settings = read_settings(study_dir)
    if not enabled(study_dir, env, settings):
        return None
    lang = lang if lang in TAB_LABELS else 'en'
    stage_id = stage(study_dir, env, settings)
    return {'stage': stage_id, 'title': TITLES[lang],
            'tabs': {t: TAB_LABELS[lang][t] for t in tabs(stage_id)},
            'where': where(action, stage_id, lang),
            'shown': shown(produced, action, stage_id, lang)}


def annotate(action, study_dir, lang: str = 'en', env: Mapping | None = None,
             produced: Mapping | None = None):
    """Add ``panel`` (last key) to the ``next_action`` dict ``action`` in place when the
    panel is on; ``action`` unchanged (no key) otherwise. Returns ``action``. ``produced``
    describes the command whose output carries ``action`` (:func:`shown_section`)."""
    if isinstance(action, dict):
        found = panel(action, study_dir, lang, env, produced)
        if found is not None:
            action['panel'] = found
    return action


__all__ = ['ENV_VAR', 'STAGE_ENV', 'SETTINGS', 'SETTING_ENABLED', 'SETTING_STAGE', 'STAGES',
           'TAB_ORDER', 'TAB_STAGE', 'TITLES', 'TAB_LABELS', 'PANEL_KEYS', 'WHERE_KEYS',
           'SHOWN_KEYS', 'SECTIONS', 'SECTION_LABELS', 'EDA_CARD_LABELS', 'SHOWN_LINES',
           'read_settings', 'normalize_stage', 'enabled', 'stage', 'tabs', 'wanted_tab',
           'where', 'shown_section', 'section_label', 'shown', 'panel', 'annotate']
