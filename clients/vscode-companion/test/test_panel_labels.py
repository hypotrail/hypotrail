"""The engine's picture of the panel equals the panel (owner session 2026-10-26, R1).

``mlkit.study.companion_env`` tells the agent, in ``next_action.panel``, whether the panel is
on, at which stage, and the tab that shows the current step, with the panel's own labels in
the study language. This test reads the panel's sources with regular expressions (as
``test_contract_keys.py`` reads the engine's key lists) and fails when one of them drifts:
the flag and its environment variables (``lib/flag.js``), the tab order and the stage from
which tabs show (``media/core.js``), the stage of each tab (``media/views/*.js``), and the
title and tab labels (``media/copy/core.js``, ``media/copy-fr/core.js``).
"""
from __future__ import annotations

import re
from pathlib import Path

from mlkit.study import companion_env as ce

CLIENT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (CLIENT / rel).read_text(encoding='utf-8')


def _js_strings(body: str) -> list[str]:
    return [a or b for a, b in re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", body)]


def _copy(rel: str) -> tuple[str, dict]:
    text = _read(rel)
    title = re.search(r"^\s*title:\s*(['\"])(.*?)\1,\s*$", text, re.M).group(2)
    body = re.search(r'^\s*tabs:\s*\{(.*?)\},\s*$', text, re.M | re.S).group(1)
    pairs = re.findall(r"(\w+):\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")", body)
    return title, {key: a or b for key, a, b in pairs}


def test_the_titles_and_tab_labels_equal_the_panel_copy():
    for lang, rel in (('en', 'media/copy/core.js'), ('fr', 'media/copy-fr/core.js')):
        title, tabs = _copy(rel)
        assert title == ce.TITLES[lang], lang
        assert tabs == ce.TAB_LABELS[lang], lang
        assert list(tabs) == list(ce.TAB_ORDER), lang


def test_the_tabs_of_each_stage_equal_the_panel_views():
    core = _read('media/core.js')
    order = re.search(r'const TAB_ORDER = \[([^\]]*)\]', core).group(1)
    assert tuple(_js_strings(order)) == ce.TAB_ORDER
    assert re.search(r"const tabbed = \(\) => atLeast\('(v\d)'\);", core).group(1) == \
        ce.TABBED_FROM
    stages = {}
    for path in sorted((CLIENT / 'media' / 'views').glob('*.js')):
        for tab, stage in re.findall(
                r"HT\.register\('\w+', \{\s*tab: '(\w+)',\s*stage: '(v\d)'", path.read_text()):
            stages.setdefault(tab, set()).add(stage)
    assert {tab: min(found) for tab, found in stages.items()} == ce.TAB_STAGE


def test_the_flag_and_the_stage_are_read_as_the_extension_reads_them():
    flag = _read('lib/flag.js')
    assert f"const ENV_VAR = '{ce.ENV_VAR}';" in flag
    assert f"const STAGE_ENV = '{ce.STAGE_ENV}';" in flag
    assert f"const SETTING_SECTION = '{ce.SETTING_ENABLED.rsplit('.', 1)[0]}';" in flag
    assert f"const SETTING_KEY = '{ce.SETTING_ENABLED.rsplit('.', 1)[1]}';" in flag
    assert ce.SETTING_STAGE.rsplit('.', 1)[1] == 'stage' and "setting(vscode, 'stage'" in flag
    assert tuple(_js_strings(re.search(r'const STAGES = \[([^\]]*)\]', flag).group(1))) == \
        ce.STAGES
    assert f"stage: '{ce.DEFAULT_STAGE}'" in flag
    # on with exactly "1", or the setting exactly true; a stage above the known ones is the
    # highest known, up to three digits
    assert "if (env[ENV_VAR] === '1') return true;" in flag
    assert 'return setting(vscode, SETTING_KEY, false) === true;' in flag
    assert 'raw.match(/^v([0-9]{1,3})$/)' in flag


# --- R1b: the sections ``next_action.panel.shown`` names --------------------------------------

SECTION_KEYS = {
    'media/copy{}/eda.js': {'data_card': 'cardTitle', 'quality': 'qualityTitle'},
    'media/copy{}/decisions.js': {'waiting': 'waitingTitle', 'choice': 'waitingTitle',
                                  'holds': 'holdsTitle', 'history': 'historyTitle',
                                  'mode': 'modeTitle'},
    'media/copy{}/evidence.js': {'development': 'developmentTitle',
                                 'diagnostics': 'diagnosticsTitle', 'final_test': 'finalTitle'},
}
# The eyebrow key of each EDA card (media/views/eda.js ``eyebrowOf``).
EYEBROW_KEYS = {'eda.target_rate': 'targetRate', 'eda.target_summary': 'targetSummary',
                'eda.special_values': 'special', 'eda.rate_by': 'rateBy', 'eda.mean_by': 'meanBy',
                'eda.single_feature_signal': 'signal', 'eda.correlation': 'correlation',
                'eda.distribution': 'distribution'}


def _string_key(text: str, key: str) -> str:
    found = re.findall(rf"^\s*{key}:\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"),", text, re.M)
    assert len(found) == 1, (key, found)
    return found[0][0] or found[0][1]


def test_the_section_labels_equal_the_panel_copy():
    """Each section heading the engine names is the panel's copy, verbatim, in both languages,
    and is a heading the views render (``media/views/*.js``)."""
    for lang, suffix in (('en', ''), ('fr', '-fr')):
        seen = set()
        for pattern, keys in SECTION_KEYS.items():
            text = _read(pattern.format(suffix))
            for section, key in keys.items():
                assert ce.SECTION_LABELS[lang][section] == _string_key(text, key), (lang, section)
                seen.add(section)
        assert seen == set(ce.SECTION_LABELS[lang]), lang
        eda = _read(f'media/copy{suffix}/eda.js')
        body = re.search(r'^\s*eyebrows:\s*\{(.*?)\},\s*$', eda, re.M | re.S).group(1)
        pairs = re.findall(r"(\w+):\s*(?:'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\")", body)
        eyebrows = {key: a or b for key, a, b in pairs}
        assert set(eyebrows) == set(EYEBROW_KEYS.values()), lang
        for activity, key in EYEBROW_KEYS.items():
            assert ce.EDA_CARD_LABELS[lang][activity] == eyebrows[key].split(' · ')[0], \
                (lang, activity)
    # Rendered as headings: the data card and the quality check (Data & EDA), the waiting,
    # holds, history and mode sections (Decisions), the development evidence, diagnostics and
    # final test (Evidence).
    eda = _read('media/views/eda.js')
    assert "'data-section': 'data_card', text: c.data.cardTitle" in eda
    assert "'data-section': 'quality', text: c.qualityTitle" in eda
    decisions = _read('media/views/decisions.js')
    for key in ('waitingTitle', 'holdsTitle', 'historyTitle', 'modeTitle'):
        assert f'c.{key}' in decisions, key
    evidence = _read('media/views/evidence.js')
    for key in ('developmentTitle', 'diagnosticsTitle', 'finalTitle'):
        assert f"text: c.{key} }}" in evidence, key
    for name in ('targetRate', 'targetSummary', 'special', 'rateBy', 'meanBy', 'signal',
                 'correlation', 'distribution'):
        assert f'e.{name}' in eda, name
