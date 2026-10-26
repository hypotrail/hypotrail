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
