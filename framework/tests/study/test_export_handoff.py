"""WP-E2: ``hypotrail export handoff`` (CLI-CONTRACT-COMPANION §7, C7).

The pack is written under ``--out`` only and never changes the study; it is byte-identical
for one study content; ``check --text handoff.md`` is clean; a report that is not current
is not copied (exit 3); a non-empty target, a target inside the study's own folders, and a
read-only process are refused without writing anything; a number that cannot be traced
refuses the export. A regression pack holds no vocabulary of a decision rule.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

import companion_contract as cc
import flowkit as fk
from mlkit.study import cli, cmd_export, read

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
RULE_VOCABULARY = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|'
                             r'calling rule|selected)\b', re.IGNORECASE)


def export(study, *args, code=None):
    outcome = cli.run(['export', 'handoff', *map(str, args), '--study', str(study)])
    if code is not None:
        assert outcome.exit_code == code, outcome.payload
    return outcome.exit_code, outcome.payload


def check_text(study, path):
    return cli.run(['check', '--text', str(path), '--study', str(study)]).payload


@pytest.fixture(scope='module')
def rendered(tmp_path_factory, synthetic_case_dir):
    """A binary study with an adopted policy, an open hold-free state, and a current report."""
    flow = fk.Flow(tmp_path_factory.mktemp('ho-bin') / 'study', synthetic_case_dir, prefix='h')
    flow.init()
    flow.pauses()
    for activity in ('split', 'eda.target_rate', 'eda.special_values', 'fit.baseline',
                     'fit.logistic'):
        flow.run(activity)
    flow.run('policy.evaluate', '--rule', 'capacity:20')
    flow.decide('policy', 'capacity:20', 'Yes, call the twenty best-scored members.')
    flow.call('render', '--study', flow.study)
    return flow


@pytest.fixture
def study(rendered, tmp_path):
    return fk.clone(rendered.study, tmp_path / 'study')


def test_the_pack_with_a_current_report(study, tmp_path):
    before = cc.study_tree_digest(study)
    out = tmp_path / 'pack'
    code, p = export(study, '--out', out, code=0)
    assert p['included_report'] is True and p['out'] == str(out)
    assert [f['path'] for f in p['files']] == list(cmd_export.FILES)
    for f in p['files']:
        data = (out / f['path']).read_bytes()
        assert f['sha256'] == hashlib.sha256(data).hexdigest() and f['bytes'] == len(data)
    assert (out / 'study.html').read_bytes() == (study / 'reports' / 'study.html').read_bytes()
    sums = (out / 'SHA256SUMS').read_text().splitlines()
    assert [line.split('  ')[1] for line in sums] == ['handoff.md', 'handoff.json', 'study.html']
    for line in sums:
        sha, name = line.split('  ')
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == sha
    assert cc.study_tree_digest(study) == before
    assert p['warnings'] == ['unconfirmed_decisions']     # only the conclusion is open
    result = check_text(study, out / 'handoff.md')
    assert result['clean'] and result['counts']['error'] == 0, result['findings']


def test_handoff_json_and_markdown_content(study, tmp_path):
    out = tmp_path / 'pack'
    export(study, '--out', out, code=0)
    handoff = json.loads((out / 'handoff.json').read_text(encoding='utf-8'))
    view = read.open(study)
    assert tuple(handoff) == cmd_export.HANDOFF_KEYS and handoff['revision'] == view.revision
    policy = next(d for d in handoff['decisions'] if d['decision_id'] == 'policy')
    assert policy['value'] == 'capacity:20' and policy['authenticated'] is False
    assert policy['user_words'] == 'Yes, call the twenty best-scored members.'
    assert handoff['exposure']['summary'] == view.exposure_summary()
    current = set(view.state['current'].values())
    assert handoff['results_cited'] and all(c['result_id'] in current
                                            for c in handoff['results_cited'])
    assert handoff['deliverables'] == {'report': 'ok', 'notebook': 'ok'}
    assert handoff['environment']['packages']
    ids = [x['id'] for x in handoff['not_yet_defensible']]
    md = (out / 'handoff.md').read_text(encoding='utf-8')
    for x in handoff['not_yet_defensible']:
        assert x['text'] in md, x['id']
    assert 'unconfirmed_decisions' in ids and 'validation_is_not_independent' in ids
    for c in handoff['results_cited']:
        assert f'{c["shown"]}' in md and c['result_id'][:8] in md
    for heading in ('## Goal', '## Decisions', '## Cited results', '## Exposure ledger',
                    '## Not yet defensible', '## Open items', '## How to reproduce',
                    '## Not for production use'):
        assert heading in md, heading
    # seven confirmed decisions (WP-A4: the success criterion and the preprocessing too;
    # WP-B1: the variant)
    assert md.count(cmd_export.NOT_AUTHENTICATED) == 7
    assert 'does not authorise production use' in md
    assert str(study) not in md and '<study>' in md
    assert 'Yes, call the twenty best-scored members.' in md


def test_two_exports_are_byte_identical(study, tmp_path):
    a, b = tmp_path / 'a', tmp_path / 'b'
    export(study, '--out', a, code=0)
    export(study, '--out', b, code=0)
    assert {f.name: f.read_bytes() for f in a.iterdir()} == {
        f.name: f.read_bytes() for f in b.iterdir()}


def fail_renders(monkeypatch):
    """The render after each commit fails (test hook): the report is kept, not current."""
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')


def test_a_stale_report_is_not_copied(rendered, study, tmp_path, monkeypatch):
    flow = fk.Flow(study, rendered.case_dir, prefix='hs')
    with monkeypatch.context() as m:
        fail_renders(m)
        flow.run('eda.rate_by', '--column', 'home_branch', expect=3)   # no new report
    before = cc.study_tree_digest(study)
    out = tmp_path / 'pack'
    code, p = export(study, '--out', out, code=3)
    assert p['ok'] is True and p['included_report'] is False
    assert p['warnings'][0] == 'report_not_current'
    assert not (out / 'study.html').exists()
    assert [f['path'] for f in p['files']] == ['handoff.md', 'handoff.json', 'SHA256SUMS']
    assert 'is not current' in (out / 'handoff.md').read_text()
    assert 'study.html' not in (out / 'SHA256SUMS').read_text()
    assert cc.study_tree_digest(study) == before
    assert check_text(study, out / 'handoff.md')['clean']


def test_the_default_target_and_its_second_export(study):
    revision = read.open(study).revision
    code, p = export(study, code=0)
    default = study / 'handoff' / f'revision-{revision}'
    assert p['out'] == str(default) and (default / 'handoff.md').is_file()
    code, again = export(study, code=2)
    assert again['error']['code'] == 'export_target_exists'
    assert again['error']['details']['path'] == str(default)
    # The pack is the engine's own output: check does not report it as untracked.
    findings = cli.run(['check', '--study', str(study)]).payload['findings']
    assert 'untracked_files' not in [f['code'] for f in findings]


@pytest.mark.parametrize('inside', ['.hypotrail/pack', 'reports', 'notebooks/pack/deeper'])
def test_a_target_inside_the_study_folders_is_refused(study, inside):
    before = cc.study_tree_digest(study)
    code, p = export(study, '--out', study / inside, code=2)
    assert p['error']['code'] == 'invalid_arguments' and p['error']['details']['field'] == 'out'
    assert cc.study_tree_digest(study) == before


def test_a_file_target_and_an_empty_folder(study, tmp_path):
    target = tmp_path / 'a-file'
    target.write_text('mine')
    code, p = export(study, '--out', target, code=2)
    assert p['error']['code'] == 'export_target_exists' and target.read_text() == 'mine'
    empty = tmp_path / 'empty'
    empty.mkdir()
    export(study, '--out', empty, code=0)
    assert (empty / 'handoff.md').is_file()


def test_read_only_processes_write_nothing(study, tmp_path):
    before = cc.study_tree_digest(study)
    code, p = fk.hyp('export', 'handoff', '--study', study, cwd=tmp_path,
                     extra_env={'HYPOTRAIL_READ_ONLY': '1'})
    assert code == 2 and p['error']['code'] == 'read_only'
    assert not (study / 'handoff').exists() and cc.study_tree_digest(study) == before


def test_an_untraceable_number_writes_nothing(study, tmp_path, monkeypatch):
    original = cmd_export._goal
    monkeypatch.setattr(cmd_export, '_goal', lambda summary: original(summary) + ' About 97.3%.')
    out = tmp_path / 'pack'
    code, p = export(study, '--out', out, code=2)
    assert p['error']['code'] == 'untraceable_number' and not out.exists()
    assert p['error']['details']['findings'][0]['code'] == 'untraceable_number'


def test_open_items_are_listed(rendered, tmp_path, monkeypatch):
    study = fk.clone(rendered.study, tmp_path / 'study')
    flow = fk.Flow(study, rendered.case_dir, prefix='ho')
    fail_renders(monkeypatch)
    flow.call('decide', 'note', '--about', 'conclusion', '--text',
              'Wait until the board meets before concluding.', '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', study, expect=3)
    flow.call('decide', 'propose', 'conclusion', '--value-json',
              json.dumps({'verdict': 'keep_baseline', 'text': 'Keep the baseline for now.'}),
              '--restatement', 'You keep the baseline.', '--rationale', 'Not enough evidence.',
              '--request-id', flow.rid(), '--expected-revision', flow.rev(), '--study', study,
              expect=3)
    monkeypatch.delenv('HYPOTRAIL_FAULT')
    code, p = export(study, '--out', tmp_path / 'pack', code=3)
    assert {'report_not_current', 'open_proposals', 'open_holds',
            'unconfirmed_decisions'} <= set(p['warnings'])
    handoff = json.loads((tmp_path / 'pack' / 'handoff.json').read_text())
    assert handoff['open_items']['proposals'] and handoff['open_items']['holds']
    assert 'report' in handoff['open_items']['stale_deliverables']
    md = (tmp_path / 'pack' / 'handoff.md').read_text()
    assert 'Wait until the board meets before concluding.' in md
    assert check_text(study, tmp_path / 'pack' / 'handoff.md')['clean']


def test_an_auto_mpg_pack_holds_no_rule_vocabulary(tmp_path):
    flow = fk.Flow(tmp_path / 'study', AUTO, prefix='ha')
    flow.init()
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed')
    flow.decide('feature_availability', fk.availability(AUTO))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    flow.model_decisions()          # WP-A4: success criterion and default preprocessing
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'fit.baseline',
                     'fit.linear', 'evaluate.regression'):
        flow.run(activity)
    flow.decide('model_choice', 'fit.linear', 'Yes, the linear model, because it errs less.')
    flow.call('render', '--study', flow.study)
    out = tmp_path / 'pack'
    export(flow.study, '--out', out, code=0)
    for name in ('handoff.md', 'handoff.json'):
        text = (out / name).read_text(encoding='utf-8')
        found = sorted({m.group(0).lower() for m in RULE_VOCABULARY.finditer(text)})
        assert found == [], (name, found)
    assert 'the linear model' in (out / 'handoff.md').read_text()
    assert check_text(flow.study, out / 'handoff.md')['clean']


# --- review fixes: no absolute path in handoff.json; the revision the client showed --------

def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def test_handoff_json_holds_no_absolute_path(study, rendered, tmp_path):
    out = tmp_path / 'pack'
    export(study, '--out', out, code=0)
    raw = (out / 'handoff.json').read_text(encoding='utf-8')
    handoff = json.loads(raw)
    assert handoff['study'] == cmd_export.STUDY == '<study>'
    absolute = [s for s in _strings(handoff) if s.startswith('/') or re.match(r'[A-Za-z]:\\', s)]
    assert absolute == []
    for folder in (study, rendered.case_dir, tmp_path):
        assert str(folder) not in raw, folder
    state = read.open(study).state
    case_dir = fk.Path(state['case']['path']).parent             # outside the study folder
    assert handoff['case']['path'] == '<case>/case.yaml'
    for label in ('case', 'dataset'):
        path = handoff[label]['path']
        assert path.startswith('<case>/'), path
        assert (case_dir / path[len('<case>/'):]).resolve() == \
            fk.Path(state[label]['path']).resolve()
    md = (out / 'handoff.md').read_text(encoding='utf-8')
    assert str(rendered.case_dir) not in md and str(tmp_path) not in md


def test_study_path_rules(tmp_path):
    study, case = tmp_path / 'study', tmp_path / 'cases' / 'bank'
    assert cmd_export.study_path(study, str(study / 'case' / 'case.yaml'), case) == \
        '<study>/case/case.yaml'
    assert cmd_export.study_path(study, str(study)) == '<study>'
    assert cmd_export.study_path(study, str(case / 'data' / 'bank.csv'), case) == \
        '<case>/data/bank.csv'
    assert cmd_export.study_path(study, str(tmp_path / 'elsewhere' / 'x.csv'), case) == \
        '<external>/x.csv'
    assert cmd_export.study_path(study, str(study.parent / 'study-2' / 'a')) == \
        '<external>/a'                                          # a sibling is not inside
    assert cmd_export.study_path(study, 'data/bank.csv') == 'data/bank.csv'
    assert cmd_export.study_path(study, None) is None


def test_the_expected_revision_names_the_folder_or_refuses(study):
    revision = read.open(study).revision
    before = cc.study_tree_digest(study)
    code, stale = export(study, '--expected-revision', revision - 1, code=2)
    assert stale['error']['code'] == 'stale_revision'
    details = stale['error']['details']
    assert details['expected_revision'] == revision - 1
    assert details['current_revision'] == revision
    assert [r['revision'] for r in details['changes_since']] == [revision]
    code, ahead = export(study, '--expected-revision', revision + 5, code=2)
    assert ahead['error']['code'] == 'stale_revision'
    assert ahead['error']['details']['changes_since'] == []
    code, bad = export(study, '--expected-revision', -1, code=2)
    assert bad['error']['code'] == 'invalid_arguments'
    assert cc.study_tree_digest(study) == before                 # nothing was written
    code, p = export(study, '--expected-revision', revision, code=0)
    assert p['revision'] == revision
    assert p['out'] == str(study / 'handoff' / f'revision-{revision}')
    handoff = json.loads((study / 'handoff' / f'revision-{revision}' / 'handoff.json')
                         .read_text(encoding='utf-8'))
    assert handoff['revision'] == revision
