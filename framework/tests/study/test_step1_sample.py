"""Contract P1.9 and P1.10 (CLI-CONTRACT §17.3, §17.4; COMPANION-ADVANCED SAMPLE-1 to
SAMPLE-5, HON-6): the seeded step-1 sample and the special-value rows.

The data card, the report and the generated notebook show the same eight development rows,
drawn at random from a seed fixed for the study, target included. Showing those target values
is a look at the target before the split: the engine records it once per seed in the exposure
ledger (``development_target_sample``), at ``init`` for a new study and at the first write of
a study created before; a read never records it. The rows holding a declared special value
are listed without the target. Studies live in temporary directories.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import flowkit as fk
from mlkit.study import cmd_data, exposure, partition, read
from mlkit.study import records as rec
from mlkit.study.store import StudyStore

SPLIT_HOLDOUT = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}
SPLIT_OTHER = {'method': 'stratified_random', 'validation_fraction': 0.25, 'seed': 7}


def test_the_seed_and_the_draw_are_fixed_by_the_contract():
    """The seed is the first 16 hex characters of a SHA-256 of the case id, the creation
    stamp and the dataset digest (never the path); the draw ranks the keys by a SHA-256 of the
    seed and the key and shows the first eight in row-key order."""
    state = {'case': {'id': 'bank-marketing'}, 'created': '2026-10-27T09:00:00+00:00',
             'dataset': {'sha256': '0' * 64}}
    text = 'hypotrail.sample/1\nbank-marketing\n2026-10-27T09:00:00+00:00\n' + '0' * 64
    assert partition.sample_seed(state) == hashlib.sha256(text.encode()).hexdigest()[:16] \
        == '13dda4990ecbd358'
    moved = {**state, 'path': '/elsewhere'}
    assert partition.sample_seed(moved) == partition.sample_seed(state)
    assert partition.sample_seed({**state, 'dataset': {'sha256': '1' * 64}}) != '13dda4990ecbd358'
    keys = [f'L{i}' for i in range(2, 40)]
    assert partition.draw('0123456789abcdef', keys) == \
        ['L3', 'L15', 'L16', 'L19', 'L29', 'L30', 'L31', 'L36']
    assert partition.draw('0123456789abcdef', ['L5', 'L3']) == ['L3', 'L5']   # fewer rows
    assert partition.SAMPLE_ROWS == 8


def _sample_records(study: Path) -> list[dict]:
    return exposure.sample_records(exposure.records(StudyStore(study)))


def _keys(study: Path, name: str) -> set[str]:
    state = read.open(study).state
    return set(rec.parse_row_keys(StudyStore(study).read_blob(
        state['partition'][name]['row_keys'])))


def _report_keys(study: Path) -> list[str]:
    html = (study / 'reports/study.html').read_text(encoding='utf-8')
    table = html.split('<table class="rows">', 1)[1].split('</table>', 1)[0]
    return re.findall(r'<tr data-row-key="(L\d+)">', table)


def _notebook_sample(study: Path) -> list[str]:
    """Run the generated notebook headless and read the sample cell's rows."""
    script = (
        'import importlib.util, json\n'
        f'spec = importlib.util.spec_from_file_location("nb", '
        f'{str(study / "notebooks/study_generated.py")!r})\n'
        'nb = importlib.util.module_from_spec(spec); spec.loader.exec_module(nb)\n'
        'outputs, defs = nb.app.run()\n'
        'print(json.dumps({"keys": list(defs["sample"].index), '
        '"columns": list(defs["sample"].columns)}))\n')
    proc = subprocess.run([sys.executable, '-c', script], cwd=study,
                          env=fk.env(HYPOTRAIL_NOTEBOOK_RECOMPUTE='1'),
                          capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_the_same_eight_rows_everywhere_recorded_once(tmp_path):
    """A new study: ``init`` records the look once; ``data --json``, the report and the
    notebook's cell show the same eight development keys, target first; never a final-test
    key; reads record nothing and later writes add no second record; a later split reports
    the rows as already exposed; ``special_rows`` lists the special-value rows without the
    target."""
    case_dir = fk.make_case(tmp_path / 'case', n_rows=300, task='binary')['case'].parent
    f = fk.Flow(tmp_path / 'study', case_dir)
    f.init()
    state = read.open(f.study).state
    [record] = _sample_records(f.study)
    seed = partition.sample_seed(state)
    assert record['sample_seed'] == seed and record['activity'] == 'data.sample'
    assert record['partition'] == 'development' and record['result_id'] is None
    assert record['purpose'] not in ('train_eda', 'structural_inspection')
    assert not [r for r in exposure.records(StudyStore(f.study))
                if r['purpose'] == 'labelled_preview_available']     # replaced for new studies
    keys = sorted(rec.parse_row_keys(StudyStore(f.study).read_blob(record['row_keys'])),
                  key=lambda k: int(k[1:]))                    # displayed in row-key order
    assert len(keys) == 8
    assert set(keys) <= _keys(f.study, 'development')
    assert not set(keys) & _keys(f.study, 'final_test')

    card = f.call('data', '--study', f.study)
    rows = card['rows']
    assert tuple(rows) == cmd_data.ROWS_KEYS and rows['order'] == 'seeded sample'
    assert [i['row_key'] for i in rows['items']] == keys and rows['n_rows'] == 8
    target = card['target']['column']
    assert rows['columns'][0] == target and rows['target_shown'] is True
    assert all(list(i['values'])[0] == target for i in rows['items'])
    assert rows['seed'] == seed
    assert rows['exposure'] == {'exposure_id': record['exposure_id'],
                                'purpose': 'development_target_sample', 'recorded': True,
                                'withheld': None}
    # check --text traces a sample cell as data.rows.<row key>
    special = card['special_rows']
    assert tuple(card) == cmd_data.PAYLOAD_KEYS and tuple(special) == cmd_data.SPECIAL_ROW_KEYS
    assert target not in special['columns'] and special['n_rows'] > cmd_data.SPECIAL_ROWS_MAX
    assert special['truncated'] is True and len(special['items']) == cmd_data.SPECIAL_ROWS_MAX
    for item in special['items']:
        assert target not in item['values'] and item['specials']
        assert item['row_key'] in _keys(f.study, 'development')
    declared = {v['name']: v['special_values'] for g in card['groups'] for v in g['variables']}
    assert special['n_rows'] <= sum(s['n_rows'] for name, items in declared.items()
                                    if name != target for s in items)

    for read_args in (('status', '--summary', '--digest'), ('data',), ('check',),
                      ('evidence',), ('plan',)):
        f.call(*read_args, '--study', f.study, expect=None)
    assert len(_sample_records(f.study)) == 1

    assert f.call('render', '--study', f.study, expect=None)['ok']
    assert _report_keys(f.study) == keys
    shown = _notebook_sample(f.study)
    assert shown['keys'] == keys and shown['columns'][0] == target

    f.pauses(split=False)
    f.decide('split', SPLIT_HOLDOUT)
    f.call('run', 'split', '--request-id', f.rid(), '--expected-revision', f.rev(),
           '--study', f.study)
    f.decide('split', SPLIT_OTHER)
    f.call('run', 'split', '--request-id', f.rid(), '--expected-revision', f.rev(),
           '--study', f.study)
    assert len(_sample_records(f.study)) == 1                       # once per seed
    overlap = f.view()['results']['split']['values']['overlap']['previously_exposed']
    assert sum(p.get('development_target_sample', 0) for p in overlap.values()) == 8
    ledger = f.call('evidence', '--study', f.study)['exposure']['ledger']
    [entry] = [x for x in ledger if x['purpose'] == 'development_target_sample']
    assert entry['rows'] == 8 and entry['note'] == exposure.SAMPLE_NOTE['en']
    assert all(x['note'] is None for x in ledger if x is not entry)


def test_an_older_study_records_the_look_on_its_first_write(tmp_path):
    """A study created before the sample (no record) shows the sample without its target, and
    no read records it; its first write records it once, before its own work; a changed
    dataset digest is a new seed and a new record."""
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200, task='binary')['case'].parent
    f = fk.Flow(tmp_path / 'study', case_dir)
    f.init()
    path = f.study / '.hypotrail' / exposure.EXPOSURE_FILE
    lines = [line for line in path.read_text(encoding='utf-8').splitlines()
             if json.loads(line)['purpose'] != exposure.SAMPLE_PURPOSE]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')          # as before P1.9
    assert _sample_records(f.study) == []
    rows = f.call('data', '--study', f.study)['rows']
    target = f.call('data', '--study', f.study)['target']['column']
    assert rows['target_shown'] is False and target not in rows['columns']
    assert all(target not in i['values'] for i in rows['items']) and rows['n_rows'] == 8
    assert rows['exposure'] == {'exposure_id': None, 'purpose': 'development_target_sample',
                                'recorded': False, 'withheld': None}
    for read_args in (('status', '--summary', '--digest'), ('check',), ('evidence',)):
        f.call(*read_args, '--study', f.study, expect=None)
    assert _sample_records(f.study) == []
    revision = f.rev()
    proposal = f.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
                      '--restatement', 'You predict before the call.', '--rationale', 'r',
                      '--request-id', f.rid(), '--expected-revision', revision,
                      '--study', f.study)
    [record] = _sample_records(f.study)
    # Recorded with the write that committed, under its lock (integrator decision 2026-10-28).
    assert record['revision'] == revision + 1 == proposal['revision']
    assert record['partition'] == 'development'
    assert set(rec.parse_row_keys(StudyStore(f.study).read_blob(record['row_keys']))) == \
        {i['row_key'] for i in rows['items']}
    assert f.call('data', '--study', f.study)['rows']['target_shown'] is True
    f.call('decide', 'withdraw', proposal['result']['proposal_id'], '--reason', 'r',
           '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    assert len(_sample_records(f.study)) == 1
    store = StudyStore(f.study)
    state = store.load_state()
    changed = {**state, 'dataset': {**state['dataset'], 'sha256': '1' * 64}}
    added = exposure.ensure_sample(store, changed)
    assert added is not None and added['sample_seed'] != record['sample_seed']
    assert exposure.ensure_sample(store, changed) is None
    assert len(_sample_records(f.study)) == 2


def _strip_sample(study: Path) -> None:
    """The exposure ledger as a study created before P1.9 holds it: no sample record."""
    path = study / '.hypotrail' / exposure.EXPOSURE_FILE
    lines = [line for line in path.read_text(encoding='utf-8').splitlines()
             if json.loads(line)['purpose'] != exposure.SAMPLE_PURPOSE]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def test_a_refused_write_records_no_look(tmp_path):
    """Integrator decision 2026-10-28 (§17.3): an older study's look is recorded only with a
    write that commits: a ``decide`` refused for a stale revision or for its arguments, a
    ``run`` refused for a stale revision, and a replay record nothing; the next committed
    write records it once, with the true note (before the split)."""
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200, task='binary')['case'].parent
    f = fk.Flow(tmp_path / 'study', case_dir)
    f.init()
    _strip_sample(f.study)
    revision = f.rev()
    stale = f.call('decide', 'propose', 'prediction_time', '--value', 'x', '--restatement', 'y',
                   '--rationale', 'r', '--request-id', f.rid(), '--expected-revision',
                   revision + 5, '--study', f.study, expect=None)
    assert stale['ok'] is False and stale['error']['code'] == 'stale_revision'
    invalid = f.call('decide', 'propose', 'no_such_decision', '--value', 'x', '--restatement',
                     'y', '--rationale', 'r', '--request-id', f.rid(), '--expected-revision',
                     revision, '--study', f.study, expect=None)
    assert invalid['ok'] is False
    run = f.call('run', 'eda.quality', '--request-id', f.rid(), '--expected-revision',
                 revision + 3, '--study', f.study, expect=None)
    assert run['ok'] is False
    assert _sample_records(f.study) == [] and f.rev() == revision
    assert f.call('data', '--study', f.study)['rows']['target_shown'] is False
    rid = f.rid()
    f.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
           '--restatement', 'You predict before the call.', '--rationale', 'r',
           '--request-id', rid, '--expected-revision', revision, '--study', f.study)
    [record] = _sample_records(f.study)
    assert record['revision'] == revision + 1
    # a replay of the same request writes nothing more
    f.call('decide', 'propose', 'prediction_time', '--value', 'before the call',
           '--restatement', 'You predict before the call.', '--rationale', 'r',
           '--request-id', rid, '--expected-revision', revision, '--study', f.study)
    assert len(_sample_records(f.study)) == 1
    rows = f.call('data', '--study', f.study)['rows']
    assert rows['target_shown'] is True and rows['exposure']['withheld'] is None
    [entry] = [x for x in f.call('evidence', '--study', f.study)['exposure']['ledger']
               if x['purpose'] == exposure.SAMPLE_PURPOSE]
    assert entry['note'] == exposure.SAMPLE_NOTE['en'] and 'before the split' in entry['note']


def test_an_older_study_past_its_split_records_no_look(tmp_path):
    """Integrator decision 2026-10-28 (§17.3): an older study whose split is already confirmed
    never records the sample (the note "shown at step 1, before the split" would be false):
    no write records it, the target stays hidden for good with the reason, in ``data --json``,
    its text card, the digest, the ledger and the report."""
    case_dir = fk.make_case(tmp_path / 'case', n_rows=200, task='binary')['case'].parent
    f = fk.Flow(tmp_path / 'study', case_dir)
    f.init()
    f.pauses(split=False)
    f.decide('split', SPLIT_HOLDOUT)
    _strip_sample(f.study)                                   # as before P1.9
    assert exposure.split_confirmed(f.state())
    f.call('run', 'split', '--request-id', f.rid(), '--expected-revision', f.rev(),
           '--study', f.study)
    f.call('decide', 'propose', 'prediction_time', '--value', 'one day before the call',
           '--restatement', 'You predict a day before.', '--rationale', 'r',
           '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    assert f.call('render', '--study', f.study, expect=None)['ok']
    assert _sample_records(f.study) == []
    card = f.call('data', '--study', f.study)
    rows, target = card['rows'], card['target']['column']
    assert rows['target_shown'] is False and target not in rows['columns']
    assert all(target not in i['values'] for i in rows['items']) and rows['n_rows'] == 8
    assert rows['exposure'] == {'exposure_id': None, 'purpose': 'development_target_sample',
                                'recorded': False, 'withheld': 'split_confirmed'}
    assert 'the split was confirmed before this study recorded a look' in cmd_data.text(card)
    digest = f.call('status', '--summary', '--digest', '--study', f.study)
    assert digest['sample']['recorded'] is False
    assert digest['ledger']['target_looks']['sample'] == 0
    html = (f.study / 'reports/study.html').read_text(encoding='utf-8')
    assert 'the split was confirmed before this study recorded a look' in html
    assert 'once a write records that look' not in html
    assert exposure.ensure_sample(StudyStore(f.study)) is None
    assert _sample_records(f.study) == []
