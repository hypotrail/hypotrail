"""WP-E2: the ``location`` of ``check`` findings (CLI-CONTRACT-COMPANION §10, C10).

``location`` is ``{path, anchor, line}``: the study-relative file, the nearest enclosing
HTML ``id``, and the 1-based line. It is added after ``details``; ``where`` and every other
key of a finding are unchanged.
"""
from __future__ import annotations

import io

import pytest

import flowkit as fk
from mlkit.study import cli, cmd_check, read, view as view_model


def check(study, *args, stdin=None, monkeypatch=None):
    if stdin is not None:
        monkeypatch.setattr('sys.stdin', io.StringIO(stdin))
    return cli.run(['check', *map(str, args), '--study', str(study)]).payload


@pytest.fixture(scope='module')
def rendered(tmp_path_factory, synthetic_case_dir):
    flow = fk.Flow(tmp_path_factory.mktemp('loc') / 'study', synthetic_case_dir, prefix='l')
    flow.init()
    flow.pauses()
    for activity in ('split', 'eda.target_rate', 'fit.baseline', 'fit.logistic'):
        flow.run(activity)
    flow.call('render', '--study', flow.study)
    return flow


@pytest.fixture
def study(rendered, tmp_path):
    return fk.clone(rendered.study, tmp_path / 'study')


def test_text_findings_carry_their_line(study):
    note = study / 'drafts' / 'note.md'
    note.parent.mkdir()
    note.write_text('A first line.\n\nThe model reaches 97.3% here.\n'
                    'Use `code that hides causes` then: calls cause renewals.\n'
                    'We followed the analyst\'s recommended defaults.\n', encoding='utf-8')
    p = check(study, '--text', note)
    by_code = {f['code']: f for f in p['findings']}
    assert by_code['untraceable_number']['location'] == {'path': 'drafts/note.md',
                                                         'anchor': None, 'line': 3}
    assert by_code['causal_wording']['location']['line'] == 4
    assert by_code['misattributed_delegation']['location']['line'] == 5
    for f in p['findings']:
        assert tuple(f) == ('code', 'severity', 'where', 'message', 'details', 'location')
        assert f['where'] == 'text'


def test_stdin_and_a_file_outside_the_study(study, tmp_path, monkeypatch):
    p = check(study, '--text', '-', stdin='Line one.\nIt is 97.3% now.\n',
              monkeypatch=monkeypatch)
    assert p['findings'][0]['location'] == {'path': None, 'anchor': None, 'line': 2}
    outside = tmp_path / 'outside.md'
    outside.write_text('It is 97.3% now.\n')
    p = check(study, '--text', outside)
    assert p['findings'][0]['location']['path'] == outside.resolve().as_posix()


def test_check_text_keeps_its_frozen_signature_and_output(study):
    view = view_model.build(read.open(study))
    findings, _ = cmd_check.check_text(view, 'It is 97.3% now.')
    assert findings and 'location' not in findings[0]


def test_report_findings_carry_the_nearest_anchor(study):
    report = study / 'reports' / 'study.html'
    page = report.read_text(encoding='utf-8')
    injected = ('<section id="injected-note">\n<h2>Note</h2>\n<p>Reached 97.3% of members.'
                '</p>\n</section>\n')
    page = page.replace('</body>', injected + '</body>', 1)
    report.write_text(page, encoding='utf-8')
    p = check(study)
    outside = [f for f in p['findings'] if f['code'] == 'number_outside_result']
    assert len(outside) == 1, outside
    location = outside[0]['location']
    assert location['path'] == 'reports/study.html' and location['anchor'] == 'injected-note'
    line = page.splitlines()[location['line'] - 1]
    assert '97.3%' in line


def test_a_cited_value_mismatch_is_located_at_its_data_element(study):
    report = study / 'reports' / 'study.html'
    page = report.read_text(encoding='utf-8')
    rid = read.open(study).state['current']['eda.target_rate']
    marker = f'data-result-id="{rid}" data-path="rate"'
    assert marker in page
    start = page.index(marker)
    end = page.index('</data>', start)
    head = page[:start]
    shown_start = page.index('>', start) + 1
    page = page[:shown_start] + '99.9%' + page[end:]
    report.write_text(page, encoding='utf-8')
    p = check(study)
    mismatch = [f for f in p['findings'] if f['code'] == 'value_mismatch']
    assert mismatch and mismatch[0]['location']['path'] == 'reports/study.html'
    assert mismatch[0]['location']['line'] == head.count('\n') + 1
    assert mismatch[0]['location']['anchor'] is None or isinstance(
        mismatch[0]['location']['anchor'], str)


def test_notebook_and_artifact_findings(study):
    notebook = study / 'notebooks' / 'study_generated.py'
    source = notebook.read_text(encoding='utf-8')
    source += ('\n\n@app.cell\ndef _(mo):\n    mo.md("""A heading\n\nIt reached 97.3% of '
               'members.""")\n    return\n')
    notebook.write_text(source, encoding='utf-8')
    p = check(study)
    cell = [f for f in p['findings'] if f['code'] == 'number_outside_result'
            and f['where'] == 'notebooks/study_generated.py']
    assert len(cell) == 1
    location = cell[0]['location']
    assert location['path'] == 'notebooks/study_generated.py' and location['anchor'] is None
    assert '97.3%' in source.splitlines()[location['line'] - 1]
    assert cell[0]['details']['line'] == location['line'] - 2     # the cell's first line


def test_an_artifact_finding_names_its_file(rendered, study, monkeypatch):
    flow = fk.Flow(study, rendered.case_dir, prefix='la')
    monkeypatch.setenv('HYPOTRAIL_TEST_HOOKS', '1')
    monkeypatch.setenv('HYPOTRAIL_FAULT', 'render_html')
    flow.run('eda.special_values', expect=3)
    p = check(study)
    failed = next(f for f in p['findings'] if f['where'] == 'artifact:report')
    assert failed['code'] == 'artifact_not_current'
    assert failed['location'] == {'path': 'reports/study.html', 'anchor': None, 'line': None}
    assert all('location' not in f for f in p['findings'] if f['where'].startswith('result:'))
