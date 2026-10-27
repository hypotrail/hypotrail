"""The engine's picture of the panel equals the panel (owner session 2026-10-26, R1; the one page,
ADR 0004 d13, PANEL-ONE-PAGE-PLAN P-8).

``mlkit.study.companion_env`` tells the agent, in ``next_action.panel``, whether the panel is
on, at which stage, and the place of the page that shows the current step (an anchor: Now, To
handle, the path, a drawer), with the panel's own labels in the study language (CLI-CONTRACT
§17.1.4). This test reads the panel's copy (``media/copy/page.js``, ``media/copy-fr/page.js``,
run in Node) and the contract's tables, and fails when one of them drifts; the engine's copy of
the labels (``ANCHOR_LABELS``, which also names the kinds of To handle as ``todo:<kind>``,
``CONTENT_LABELS``, ``DRAWER_LABELS``, ``STEP_LABELS``, the EDA card names and the lines) is
compared too, and the flag and its environment variables (``lib/flag.js``). The tabbed panel's
tab and section labels went with the tabs.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from mlkit.study import companion_env as ce

CLIENT = Path(__file__).resolve().parents[1]
CONTRACT = CLIENT.parents[1] / 'docs' / 'specs' / 'CLI-CONTRACT.md'
COPY = """
const fs = require('fs');
const out = {};
for (const [lang, file] of [['en', 'media/copy/page.js'], ['fr', 'media/copy-fr/page.js']]) {
  const HT = { copy: {} };
  new Function('globalThis', fs.readFileSync(file, 'utf8'))({ Hypotrail: HT });
  const c = lang === 'fr' ? HT.copyFr.page : HT.copy.page;
  const OV = { copy: {} };
  new Function('globalThis', fs.readFileSync(file.replace('page.js', 'overview.js'), 'utf8'))({ Hypotrail: OV });
  const EDA = { copy: {} };
  new Function('globalThis', fs.readFileSync(file.replace('page.js', 'eda.js'), 'utf8'))({ Hypotrail: EDA });
  const o = lang === 'fr' ? OV.copyFr.overview : OV.copy.overview;
  const e = lang === 'fr' ? EDA.copyFr.eda : EDA.copy.eda;
  out[lang] = { anchors: c.anchors, contents: c.contents, todoKinds: c.todoKinds, drawers: c.drawers,
                steps: o.journeyLabels, eyebrows: e.binary.eyebrows };
}
process.stdout.write(JSON.stringify(out));
"""


def _read(rel: str) -> str:
    return (CLIENT / rel).read_text(encoding='utf-8')


def _js_strings(body: str) -> list[str]:
    return [a or b for a, b in re.findall(r"'((?:[^'\\]|\\.)*)'|\"((?:[^\"\\]|\\.)*)\"", body)]


@pytest.fixture(scope='module')
def page_copy():
    node = shutil.which('node')
    if not node:
        pytest.skip('node is not installed')
    return json.loads(subprocess.run([node, '-e', COPY], cwd=CLIENT, capture_output=True, text=True, check=True).stdout)


def _table(heading: str) -> dict:
    """A three-column table of CLI-CONTRACT §17.1.4 after the header that starts with `heading`."""
    text = CONTRACT.read_text(encoding='utf-8')
    section = text[text.index('#### 17.1.4'):text.index('#### 17.1.5')]
    rows = {}
    block = section[section.index(f'| {heading}'):].split('\n\n', 1)[0]
    for line in block.splitlines()[2:]:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 3 and cells[1] and cells[2]:
            key = cells[0].strip('`').split(' ')[0].strip('`')
            rows[key] = {'en': cells[1], 'fr': cells[2]}
    return rows


def test_the_page_labels_equal_the_contract_tables(page_copy):
    """CLI-CONTRACT §17.1.4: the contents of Now, the kinds of To handle and the drawers are the
    panel's copy, verbatim, in both languages."""
    for heading, key in (('Content (`now`)', 'contents'), ('`todo` kind', 'todoKinds'), ('Drawer', 'drawers')):
        table = _table(heading)
        assert table, heading
        for lang in ('en', 'fr'):
            assert {k: v[lang] for k, v in table.items()} == page_copy[lang][key], (heading, lang)


def test_the_anchor_names_open_the_contract_lines(page_copy):
    """The place names of the panel line (§17.1.4 "In the panel: Now, …") are the copy's anchors."""
    lines = _table('Anchor')
    for lang, start in (('en', 'In the panel: '), ('fr', 'Dans le panneau : ')):
        names = page_copy[lang]['anchors']
        assert lines['now'][lang].strip('`').startswith(f'{start}{names["now"]},'), lang
        assert lines['todo:<kind>'][lang].strip('`').startswith(f'{start}{names["todo"]},'), lang
        assert lines['path'][lang].strip('`').startswith(f'{start}{names["path"]},'), lang
        assert lines['tools:<drawer>'][lang].strip('`').startswith(f'{start}{names["tools"]} →'), lang


# The panel's eyebrow keys (media/copy*/eda.js) and the engine's EDA activities.
EYEBROW_ACTIVITIES = {'targetRate': 'eda.target_rate', 'targetSummary': 'eda.target_summary',
                      'special': 'eda.special_values', 'rateBy': 'eda.rate_by',
                      'meanBy': 'eda.mean_by', 'signal': 'eda.single_feature_signal',
                      'correlation': 'eda.correlation', 'distribution': 'eda.distribution'}


def test_the_engine_labels_equal_the_page(page_copy):
    """CLI-CONTRACT §17.1.4, PG-13 (E-1, P-8): ``companion_env`` copies the panel's labels
    verbatim. The engine keeps the kinds of To handle in ``ANCHOR_LABELS`` as ``todo:<kind>``
    (with ``path_ledger``, the ledger line's name), next to the four place names."""
    for lang in ('en', 'fr'):
        anchors = ce.ANCHOR_LABELS[lang]
        assert {k: anchors[k] for k in page_copy[lang]['anchors']} == page_copy[lang]['anchors'], lang
        assert {k: anchors[f'todo:{k}'] for k in ce.TODO_KINDS} == page_copy[lang]['todoKinds'], lang
        assert set(anchors) == set(page_copy[lang]['anchors']) | {f'todo:{k}' for k in ce.TODO_KINDS} \
            | {'path_ledger'}, lang
        assert ce.CONTENT_LABELS[lang] == page_copy[lang]['contents'], lang
        assert set(ce.CONTENT_LABELS[lang]) == set(ce.CONTENTS), lang
        assert ce.DRAWER_LABELS[lang] == page_copy[lang]['drawers'], lang
        assert tuple(ce.DRAWER_LABELS[lang]) == ce.DRAWERS, lang
        # the path's step names are the panel's journey labels
        assert ce.STEP_LABELS[lang] == page_copy[lang]['steps'], lang
        # an EDA figure is named by its card's name, the first part of the panel's eyebrow
        for key, activity in EYEBROW_ACTIVITIES.items():
            assert ce.EDA_CARD_LABELS[lang][activity] == page_copy[lang]['eyebrows'][key].split(' · ')[0], \
                (lang, key)


def test_the_engine_lines_are_the_contract_lines():
    """CLI-CONTRACT §17.1.4: ``companion_env.LINES`` are the table's lines, and a line built for
    each kind of place starts with the panel's place name (the ledger line's name included)."""
    table = _table('Anchor')
    keys = {'now': 'now', 'todo:<kind>': 'todo', 'path': 'path', 'path:<step>': 'path_step',
            'path:<step>/<slot>': 'path_figure', 'tools:<drawer>': 'tools'}
    for lang in ('en', 'fr'):
        for row, key in keys.items():
            expected = table[row][lang].strip('`').replace('{kind label}', '{kind}')
            assert ce.LINES[lang][key] == expected, (lang, row)
        ledger = ce.ANCHOR_LABELS[lang]['path_ledger']
        assert ce.LINES[lang]['path'].endswith(f'{ledger}.'), lang
        assert ce.line_of('tools:whatif', None, lang) == ce.LINES[lang]['tools'].format(
            drawer=ce.DRAWER_LABELS[lang]['whatif']), lang
        assert ce.label_of(ce.line_of('now', 'data_card', lang)) == \
            f"{ce.ANCHOR_LABELS[lang]['now']}, {ce.CONTENT_LABELS[lang]['data_card']}", lang


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
