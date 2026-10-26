"""Whether the study panel is on, at which stage, and where it shows the current step
(owner session 2026-10-26, remark R1; CLI-CONTRACT §3.1, ``next_action.panel``).

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
PANEL_KEYS = ('stage', 'title', 'tabs', 'where')
WHERE_KEYS = ('tab', 'label', 'line')
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


def panel(action: Mapping | None, study_dir, lang: str = 'en',
          env: Mapping | None = None) -> dict | None:
    """``next_action.panel`` (``PANEL_KEYS``) when the panel is on, else None."""
    settings = read_settings(study_dir)
    if not enabled(study_dir, env, settings):
        return None
    lang = lang if lang in TAB_LABELS else 'en'
    stage_id = stage(study_dir, env, settings)
    return {'stage': stage_id, 'title': TITLES[lang],
            'tabs': {t: TAB_LABELS[lang][t] for t in tabs(stage_id)},
            'where': where(action, stage_id, lang)}


def annotate(action, study_dir, lang: str = 'en', env: Mapping | None = None):
    """Add ``panel`` (last key) to the ``next_action`` dict ``action`` in place when the
    panel is on; ``action`` unchanged (no key) otherwise. Returns ``action``."""
    if isinstance(action, dict):
        found = panel(action, study_dir, lang, env)
        if found is not None:
            action['panel'] = found
    return action


__all__ = ['ENV_VAR', 'STAGE_ENV', 'SETTINGS', 'SETTING_ENABLED', 'SETTING_STAGE', 'STAGES',
           'TAB_ORDER', 'TAB_STAGE', 'TITLES', 'TAB_LABELS', 'PANEL_KEYS', 'WHERE_KEYS',
           'read_settings', 'normalize_stage', 'enabled', 'stage', 'tabs', 'wanted_tab',
           'where', 'panel', 'annotate']
