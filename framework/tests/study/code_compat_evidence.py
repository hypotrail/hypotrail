"""Reproducible evidence of the library-v1 attestations of ``mlkit.study.code_compat`` (E1).

The same commands are run on the same temporary studies by two engines (the 506180a engine
and the current one), then the registry results are compared slot by slot; finally the
current engine recomputes the leaf activities inside copies of the old studies, where every
upstream result keeps its old id, and those results are compared byte for byte.

Run it from a checkout of the current engine (temporary folders only; nothing in the
repository or in a real study is touched)::

    git worktree add --detach <scratch>/old 506180a && (cd <scratch>/old/framework && uv sync --frozen)
    uv run --project framework python framework/tests/study/code_compat_evidence.py \\
        evidence <scratch>/old/framework/.venv/bin/python <scratch>/old <scratch>/work

It prints one line per result and exits 1 if any compared result differs. The opt-in test
``test_code_compat_library_v1.py::test_byte_comparison_with_the_base_engine`` runs the same
thing when ``HYPOTRAIL_COMPAT_OLD_PYTHON`` and ``HYPOTRAIL_COMPAT_OLD_ROOT`` are set.

``drive`` is executed by each engine's own Python and imports only that engine; it must
therefore use only what both engines have (``flowkit`` is unchanged between them).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OPEN = 'Yes, I open the final test now, because the model and the rule are fixed'
TUNED = {'kind': 'tuned', 'question': 'Does a tuned penalty rank the rows better?'}
HGB = {'kind': 'family', 'family': 'hgb', 'question': 'Does boosting find what the line misses?'}
STRONG = {'kind': 'regularisation', 'strength': 'strong',
          'question': 'Does a stronger penalty generalise better?'}
EBM = {'kind': 'family', 'family': 'ebm', 'question': 'Does an EBM follow the shapes?'}
BIN_POLICY = ('policy.evaluate', '--rule', 'capacity:40', '--rule', 'threshold:0.3')
BIN_INSPECT = ('policy.inspect', '--rule', 'share:0.1', '--rule', 'threshold:0.5')
# study name -> (task, case folder, split value or None for the engine's default, variants,
# per-column EDA column, grouping column)
STUDIES = {
    'bin': ('binary', 'case-bin', None, [TUNED, HGB, STRONG], 'visit_band', 'home_branch'),
    'bin-cv': ('binary', 'case-bin', {'method': 'kfold_stratified', 'folds': 5, 'seed': 7},
               [STRONG, EBM], 'visit_band', 'home_branch'),
    'reg': ('regression', 'auto-mpg', None, [TUNED, HGB], 'weight', 'model_year'),
    'reg-cv': ('regression', 'case-reg', {'method': 'kfold_quantile', 'folds': 5, 'seed': 7},
               [STRONG, EBM], 'floor_area', 'branch_type'),
}


def canon(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


# --- the shared cases (made once, by the current engine's fixture generator) ---------------

def make_cases(out: Path) -> Path:
    sys.path.insert(0, str(HERE))
    import flowkit as fk
    out.mkdir(parents=True, exist_ok=True)
    fk.make_case(out / 'case-bin', n_rows=1500)
    fk.make_case(out / 'case-reg', task='regression', n_rows=900)
    shutil.copytree(REPO / 'use-cases' / 'auto-mpg', out / 'auto-mpg')
    return out


# --- one engine runs the flows ---------------------------------------------------------------

def drive(root: Path, cases: Path, out: Path) -> list:
    """Run every study of :data:`STUDIES` with the engine of ``root`` (its own Python)."""
    import inspect
    sys.path[:0] = [str(root / 'framework'), str(root / 'framework' / 'tests' / 'study')]
    import mlkit
    assert str(root) in inspect.getfile(mlkit), inspect.getfile(mlkit)
    import flowkit as fk
    from flowkit import Flow
    from mlkit.study import state as st
    log = []

    def run(f, *args):
        out_ = f.call('run', *args, '--request-id', f.rid(), '--expected-revision', f.rev(),
                      '--study', f.study, expect=None)
        log.append([f.study.name, args[0], out_.get('ok'), (out_.get('error') or {}).get('code')])

    def decide(f, decision, value, words=None):
        p = f.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                   '--restatement', f'You decide the {decision} as stated.', '--rationale',
                   'It fits the scenario.', '--request-id', f.rid(), '--expected-revision',
                   f.rev(), '--study', f.study, expect=None)
        if not p.get('ok'):
            log.append([f.study.name, 'propose ' + decision, False, p['error']['code']])
            return
        c = f.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                   words or fk.default_words(decision), '--request-id', f.rid(),
                   '--expected-revision', f.rev(), '--study', f.study, expect=None)
        log.append([f.study.name, 'confirm ' + decision, c.get('ok'),
                    (c.get('error') or {}).get('code')])

    out.mkdir(parents=True, exist_ok=True)
    for name, (task, case, split, variants, column, by) in STUDIES.items():
        binary = task == 'binary'
        f = Flow(out / name, cases / case, prefix=name[:3])
        f.init()
        decide(f, 'prediction_time', 'when the record is created, before the outcome')
        decide(f, 'feature_availability', fk.availability(cases / case))
        decide(f, 'split', split or f.view()['next_action']['default_value'])
        f.model_decisions()
        run(f, 'split')
        for a in ('eda.target_rate' if binary else 'eda.target_summary', 'eda.special_values',
                  'eda.quality', 'eda.correlation', 'eda.single_feature_signal'):
            run(f, a)
        run(f, 'eda.rate_by' if binary else 'eda.mean_by', '--column', by)
        run(f, 'eda.distribution', '--column', column)
        run(f, 'fit.baseline')
        run(f, 'fit.logistic' if binary else 'fit.linear')
        diag = 'diag.binary' if binary else 'diag.regression'
        run(f, diag)
        decide(f, 'model_variant', {'variants': variants})
        for slot in ('fit.variant', 'fit.variant:2', 'fit.variant:3')[:len(variants)]:
            run(f, slot)
        if binary:
            run(f, diag)
            run(f, *BIN_INSPECT)
            run(f, *BIN_POLICY)
            decide(f, 'model_choice', 'fit.logistic',
                   words='Yes, I choose that model because it ranks the rows best for us')
            decide(f, 'policy', 'capacity:40',
                   words='Yes, I adopt that rule because the desk can make that many calls')
        else:
            run(f, 'evaluate.regression')
            decide(f, 'model_choice', 'fit.linear',
                   words='Yes, I choose that model because its error is smaller')
        run(f, diag)
        decide(f, 'final_test', st.b1_default_value(f.state(), 'final_test'), words=OPEN)
        run(f, 'diag.final_test')
    (out / 'log.json').write_text(json.dumps(log, indent=0))
    return log


# --- comparisons -----------------------------------------------------------------------------

def _entries(study: Path) -> dict:
    """Registry results in creation order, keyed ``activity[:variant index]#n``."""
    rows = [json.loads(p.read_text()) for p in (study / '.hypotrail' / 'registry').glob('*.json')]
    rows.sort(key=lambda e: (e['started_revision'], e['created']))
    seen, out = {}, {}
    for e in rows:
        label = e['activity']
        if label == 'fit.variant':
            label += f":{e['params'].get('variant_index', e['params'].get('index'))}"
        seen[label] = seen.get(label, 0) + 1
        out[f'{label}#{seen[label]}'] = e
    return out


def _changed_modules(a: dict, b: dict) -> list[str]:
    ma, mb = a['code']['modules'], b['code']['modules']
    return sorted(m for m in set(ma) | set(mb) if ma.get(m) != mb.get(m))


def compare_runs(old_run: Path, new_run: Path) -> list[dict]:
    """Slot-by-slot comparison of two runs of the same flows.

    Result, execution and exposure ids hash the code fingerprint, so a value or input naming
    an upstream result is compared after mapping each old id to its counterpart; blobs,
    params, partition and row count are compared as they are.
    """
    rows = []
    for name in STUDIES:
        o, n = _entries(old_run / name), _entries(new_run / name)
        assert list(o) == list(n), (name, list(o), list(n))
        ids = {}
        for k in o:
            for key in ('result_id', 'execution_id', 'exposure_id'):
                ids[o[k][key]] = n[k][key]

        def mapped(value):
            text = canon(value)
            for a, b in ids.items():
                text = text.replace(a, b)
            return text
        for k in o:
            a, b = o[k], n[k]
            exact = canon(a['output']['values']) == canon(b['output']['values']) \
                and a['output']['sha256'] == b['output']['sha256']
            same = (a['activity'] == b['activity'] and a['blobs'] == b['blobs']
                    and canon(a['params']) == canon(b['params'])
                    and a['partition'] == b['partition'] and a['n_rows'] == b['n_rows']
                    and mapped(a['inputs']) == canon(b['inputs'])
                    and mapped(a['output']['values']) == canon(b['output']['values']))
            rows.append({'study': name, 'key': k, 'activity': a['activity'], 'same': same,
                         'exact': exact and same, 'modules': _changed_modules(a, b)})
    return rows


def leaves(name: str) -> list[tuple]:
    """Activities no other compared result is computed from (so recomputing them keeps every
    upstream id), with the options the flow used."""
    task, _case, _split, _variants, column, by = STUDIES[name]
    if task == 'binary':
        return [('eda.target_rate',), ('eda.special_values',), ('eda.quality',),
                ('eda.correlation',), ('eda.single_feature_signal',),
                ('eda.rate_by', '--column', by), ('eda.distribution', '--column', column),
                BIN_INSPECT, ('diag.binary',), ('diag.final_test',), BIN_POLICY]
    return [('eda.target_summary',), ('eda.special_values',), ('eda.quality',),
            ('eda.correlation',), ('eda.single_feature_signal',),
            ('eda.mean_by', '--column', by), ('eda.distribution', '--column', column),
            ('evaluate.regression',), ('diag.regression',), ('diag.final_test',)]


def _slot(args: tuple) -> str:
    slot = {'policy.inspect': 'policy.inspection', 'policy.evaluate': 'policy.evaluation'}.get(
        args[0], args[0])
    return f'{slot}:{args[2]}' if len(args) > 2 and args[1] == '--column' else slot


def recompute_leaves(old_run: Path, work: Path, cli: str) -> tuple[list[dict], dict]:
    """With the current engine (``cli``), check currency in copies of the old studies, then
    recompute their leaf activities and compare each with the old result byte for byte."""
    def h(study, *args):
        p = subprocess.run([cli, *map(str, args), '--study', str(study)], capture_output=True,
                           text=True)
        assert 'Traceback' not in p.stderr, p.stderr
        return json.loads(p.stdout)

    def entry(study, rid):
        return json.loads((study / '.hypotrail' / 'registry' / f'{rid}.json').read_text())
    shutil.rmtree(work, ignore_errors=True)
    rows, currency = [], {}
    for name in STUDIES:
        d = work / name
        shutil.copytree(old_run / name, d)
        promoted = set(json.loads((d / '.hypotrail' / 'state.json').read_text())['current']
                       .values())
        ev = h(d, 'evidence')
        currency[name] = {'promoted': len(promoted),
                          'not_current': sorted(r['slot'] for r in ev['results']
                                                if r['result_id'] in promoted
                                                and not r.get('current'))}
        for n, args in enumerate(leaves(name), 1):
            state = json.loads((d / '.hypotrail' / 'state.json').read_text())
            old_rid = state['current'][_slot(args)]
            out = h(d, 'run', *args, '--request-id', f'leaf-{n}', '--expected-revision',
                    h(d, 'status')['revision'])
            if not out.get('ok'):
                rows.append({'study': name, 'key': _slot(args), 'same': False,
                             'refused': out['error']['code']})
                continue
            a, b = entry(d, old_rid), entry(d, out['result_id'])
            same = all(canon(a[k]) == canon(b[k]) for k in ('params', 'inputs', 'blobs')) \
                and canon(a['output']) == canon(b['output'])
            rows.append({'study': name, 'key': _slot(args), 'activity': a['activity'],
                         'same': same, 'modules': _changed_modules(a, b)})
    return rows, currency


def evidence(old_python: str, old_root: Path, work: Path) -> bool:
    """The complete comparison; prints it and returns whether everything matched."""
    head_cli = str(Path(sys.executable).with_name('hypotrail'))
    shutil.rmtree(work, ignore_errors=True)
    cases = make_cases(work / 'cases')
    me = str(Path(__file__).resolve())
    logs = {}
    for label, python, root in (('old', old_python, old_root), ('new', sys.executable, REPO)):
        subprocess.run([python, me, 'drive', str(root), str(cases), str(work / label)],
                       check=True, capture_output=True, text=True)
        logs[label] = json.loads((work / label / 'log.json').read_text())
    ok = logs['old'] == logs['new'] and all(row[2] for row in logs['old'])
    print(f"flows: {len(logs['old'])} commands, identical outcomes: {logs['old'] == logs['new']}"
          f", all succeeded: {all(row[2] for row in logs['old'])}")
    fresh = compare_runs(work / 'old', work / 'new')
    for r in fresh:
        print(f"  fresh  {r['study']:<7} {r['key']:<30} "
              f"{'byte-identical' if r['exact'] else 'identical up to upstream ids' if r['same'] else 'DIFFERENT'}"
              f"  changed modules: {','.join(r['modules'])}")
    leaf, currency = recompute_leaves(work / 'old', work / 'leaves', head_cli)
    for name, info in currency.items():
        print(f"  current at HEAD in {name}: {info['promoted'] - len(info['not_current'])} of "
              f"{info['promoted']} promoted results; not current: {info['not_current']}")
    for r in leaf:
        print(f"  leaf   {r['study']:<7} {r['key']:<30} "
              f"{'byte-identical' if r['same'] else 'DIFFERENT ' + r.get('refused', '')}")
    ok = ok and all(r['same'] for r in fresh) and all(r['same'] for r in leaf) \
        and not any(info['not_current'] for info in currency.values())
    print(f"fresh results: {len(fresh)} ({sum(r['exact'] for r in fresh)} byte-identical, "
          f"{sum(r['same'] and not r['exact'] for r in fresh)} up to upstream ids); leaf "
          f"recomputations: {sum(r['same'] for r in leaf)} of {len(leaf)} byte-identical; "
          f"{'MATCH' if ok else 'MISMATCH'}")
    return ok


if __name__ == '__main__':
    command, *args = sys.argv[1:]
    if command == 'drive':
        drive(*map(Path, args))
    elif command == 'evidence':
        sys.exit(0 if evidence(args[0], Path(args[1]), Path(args[2])) else 1)
    else:
        sys.exit(f'unknown command {command}')
