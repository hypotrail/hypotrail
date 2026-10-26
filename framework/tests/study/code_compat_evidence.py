"""Reproducible evidence of the attestations of ``mlkit.study.code_compat`` (E1, round 2).

The same commands are run on the same temporary studies by two engines (an old engine, the
506180a one for the library-v1 edges and also, since review round 2, the 818995c one, and
the current one), then the registry results are compared slot by slot; finally the current
engine recomputes the leaf activities inside copies of the old studies, where every upstream
result keeps its old id, and those results are compared byte for byte.

Review round 2 (delayed labels) adds two review-v1 studies without training exclusions (an
independent synthetic case, and a future case whose outcome is known at prediction time, so
the outcome clock leaves no row out), and ``diagnostics.population`` in every study when the
old engine has it (818995c, not 506180a). Which of these an engine runs is decided once from
the old engine's files (:func:`capabilities`), so both engines run the same commands.

Owner session 2026-10-26 (lot L8) adds a seventh study, ``bin-prep``: a binary holdout study
whose preparation is not the default (missing-value indicators, an *integer* rare-category
minimum, a cap and a signed log) with a tuned variant, so the per-column grouping, the inner
grid and the bootstraps are compared on a value an existing study can hold. L8 also adds two
keys to ``eda.quality`` (``quantiles`` and ``skewness`` of each numeric range): a result of an
engine without them is compared with the new one once those keys are removed
(:data:`ADDITIVE`, the WP-F1 precedent of ADR 0007), and reported "identical but for the
additive keys".

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
# Owner session 2026-10-26 (L8): a non-default integer preparation and a tuned variant (same
# tuple); the preparation each study confirms (the default for the others).
PREPARED_STUDIES = {
    'bin-prep': ('binary', 'case-bin', None, [TUNED], 'visit_band', 'home_branch'),
}
PREPROCESSING = {
    'bin-prep': {'missing': 'indicator', 'rare_category_min_rows': 120,
                 'caps': {'fines_outstanding': [0.01, 0.99]},
                 'log_transform': ['membership_days']},
}
# L8 (R5): keys a later engine adds to the items of a list of a result's values, by activity:
# a result without them is compared once they are removed from the newer one.
ADDITIVE = {'eda.quality': ('ranges', ('quantiles', 'skewness'))}
# Review round 2: review-v1 studies without training exclusions (same tuple). A review-v1
# variant declared after scores cites the current diagnostic; the tuned and family variants
# are left out (their nested plan is not the subject here).
REVIEW_STRONG = dict(STRONG, origin='planned', diagnostic_result_id=None)
REVIEW_STUDIES = {
    'rev-ind': ('binary', 'case-rev-ind', None, [REVIEW_STRONG], 'visit_band', 'home_branch'),
    'rev-fut0': ('binary', 'case-rev-fut0', None, [REVIEW_STRONG], 'visit_band',
                 'home_branch'),
}
REVIEW_CRITERION = {'metric': 'precision_gain', 'min_points': 5,
                    'decision_rule': 'point_estimate',
                    'selection': {'metric': 'precision', 'rule': 'share:0.2',
                                  'scope': 'evaluation_window', 'batch_column': None,
                                  'aggregation': 'pooled_counts'}}
REV_POLICY = ('policy.evaluate', '--rule', 'share:0.2', '--rule', 'threshold:0.3')
POPULATION = ('diagnostics.population',)
# Run and reported, never attested: its Evidently statistics differ in the last bits between
# two runs and its snapshot blob is not reproducible, so it is not byte-identical (round 2).
UNATTESTED = ('diagnostics.population',)


def capabilities(old_root: Path) -> dict:
    """What both engines can run: review-v1 studies, and ``diagnostics.population``."""
    study = Path(old_root) / 'framework' / 'mlkit' / 'study'
    assurance = study / 'assurance.py'
    return {'review': assurance.is_file() and 'review-v1' in assurance.read_text('utf-8'),
            'population': (Path(old_root) / 'framework' / 'mlkit' / 'contracts'
                           / 'population.py').is_file()}


def studies(caps: dict) -> dict:
    return {**STUDIES, **(REVIEW_STUDIES if caps.get('review') else {}), **PREPARED_STUDIES}


def without_additive(activity: str, newer, older):
    """``newer`` values without the keys of :data:`ADDITIVE` that ``older`` lacks, and
    whether any was removed."""
    if activity not in ADDITIVE or not isinstance(newer, dict) or not isinstance(older, dict):
        return newer, False
    key, extra = ADDITIVE[activity]
    old_items, new_items = older.get(key), newer.get(key)
    if not isinstance(old_items, list) or not isinstance(new_items, list):
        return newer, False
    missing = {k for k in extra if not any(isinstance(i, dict) and k in i for i in old_items)}
    if not missing:
        return newer, False
    out = dict(newer)
    out[key] = [{k: v for k, v in i.items() if k not in missing} if isinstance(i, dict) else i
                for i in new_items]
    return out, True


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
    fk._module.make_review_case(out / 'case-rev-ind', n_rows=600)
    fk._module.make_review_case(out / 'case-rev-fut0', future=True, n_rows=600,
                                outcome_delay=0)
    return out


# --- one engine runs the flows ---------------------------------------------------------------

def drive(root: Path, cases: Path, out: Path, caps: dict | None = None) -> list:
    """Run every study of :func:`studies` with the engine of ``root`` (its own Python)."""
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

    caps = caps or {}
    out.mkdir(parents=True, exist_ok=True)
    for name, (task, case, split, variants, column, by) in studies(caps).items():
        binary = task == 'binary'
        review = name in REVIEW_STUDIES
        f = Flow(out / name, cases / case, prefix=name[:3])
        if review:
            f.call('init', '--case', cases / case / 'case.yaml', '--study', f.study,
                   '--reliability-profile', 'review-v1')
            import yaml
            contract = yaml.safe_load((cases / case / 'case.yaml').read_text('utf-8'))[
                'analysis_contract']
            decide(f, 'prediction_time', contract['prediction_statement'])
        else:
            f.init()
            decide(f, 'prediction_time', 'when the record is created, before the outcome')
        decide(f, 'feature_availability', fk.availability(cases / case))
        decide(f, 'split', split or f.view()['next_action']['default_value']
               or st.b1_default_value(f.state(), 'split'))
        if review:
            from mlkit.study import governance
            decide(f, 'success_criterion', REVIEW_CRITERION)
            decide(f, 'preprocessing', dict(governance.DEFAULT_PREPROCESSING))
        else:
            f.model_decisions(preprocessing=PREPROCESSING.get(name))
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
        if caps.get('population'):
            run(f, *POPULATION)
        if binary:
            run(f, diag)
            run(f, *BIN_INSPECT)
            run(f, *(REV_POLICY if review else BIN_POLICY))
            decide(f, 'model_choice', 'fit.logistic',
                   words='Yes, I choose that model because it ranks the rows best for us')
            decide(f, 'policy', 'share:0.2' if review else 'capacity:40',
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


def compare_runs(old_run: Path, new_run: Path, caps: dict | None = None) -> list[dict]:
    """Slot-by-slot comparison of two runs of the same flows.

    Result, execution and exposure ids hash the code fingerprint, so a value or input naming
    an upstream result is compared after mapping each old id to its counterpart; blobs,
    params, partition and row count are compared as they are.
    """
    rows = []
    for name in studies(caps or {}):
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
            values, additive = without_additive(a['activity'], b['output']['values'],
                                                a['output']['values'])
            exact = canon(a['output']['values']) == canon(b['output']['values']) \
                and a['output']['sha256'] == b['output']['sha256']
            same = (a['activity'] == b['activity'] and a['blobs'] == b['blobs']
                    and canon(a['params']) == canon(b['params'])
                    and a['partition'] == b['partition'] and a['n_rows'] == b['n_rows']
                    and mapped(a['inputs']) == canon(b['inputs'])
                    and mapped(a['output']['values']) == canon(values))
            rows.append({'study': name, 'key': k, 'activity': a['activity'], 'same': same,
                         'exact': exact and same, 'additive': additive and same,
                         'modules': _changed_modules(a, b)})
    return rows


def leaves(name: str, caps: dict | None = None) -> list[tuple]:
    """Activities no other compared result is computed from (so recomputing them keeps every
    upstream id), with the options the flow used."""
    task, _case, _split, _variants, column, by = studies(caps or {})[name]
    extra = [POPULATION] if (caps or {}).get('population') else []
    if task == 'binary':
        return [('eda.target_rate',), ('eda.special_values',), ('eda.quality',),
                ('eda.correlation',), ('eda.single_feature_signal',),
                ('eda.rate_by', '--column', by), ('eda.distribution', '--column', column),
                BIN_INSPECT, ('diag.binary',), ('diag.final_test',),
                REV_POLICY if name in REVIEW_STUDIES else BIN_POLICY] + extra
    return [('eda.target_summary',), ('eda.special_values',), ('eda.quality',),
            ('eda.correlation',), ('eda.single_feature_signal',),
            ('eda.mean_by', '--column', by), ('eda.distribution', '--column', column),
            ('evaluate.regression',), ('diag.regression',), ('diag.final_test',)] + extra


def _slot(args: tuple) -> str:
    slot = {'policy.inspect': 'policy.inspection', 'policy.evaluate': 'policy.evaluation'}.get(
        args[0], args[0])
    return f'{slot}:{args[2]}' if len(args) > 2 and args[1] == '--column' else slot


def recompute_leaves(old_run: Path, work: Path, cli: str,
                     caps: dict | None = None) -> tuple[list[dict], dict]:
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
    for name in studies(caps or {}):
        d = work / name
        shutil.copytree(old_run / name, d)
        promoted = set(json.loads((d / '.hypotrail' / 'state.json').read_text())['current']
                       .values())
        ev = h(d, 'evidence')
        currency[name] = {'promoted': len(promoted),
                          'not_current': sorted(r['slot'] for r in ev['results']
                                                if r['result_id'] in promoted
                                                and not r.get('current'))}
        for n, args in enumerate(leaves(name, caps), 1):
            state = json.loads((d / '.hypotrail' / 'state.json').read_text())
            old_rid = state['current'][_slot(args)]
            out = h(d, 'run', *args, '--request-id', f'leaf-{n}', '--expected-revision',
                    h(d, 'status')['revision'])
            if not out.get('ok'):
                rows.append({'study': name, 'key': _slot(args), 'same': False,
                             'refused': out['error']['code']})
                continue
            a, b = entry(d, old_rid), entry(d, out['result_id'])
            values, additive = without_additive(a['activity'], b['output']['values'],
                                                a['output']['values'])
            output = canon(a['output']) == canon(b['output']) or (
                additive and canon(a['output']['values']) == canon(values)
                and set(a['output']) == set(b['output']))
            same = all(canon(a[k]) == canon(b[k]) for k in ('params', 'inputs', 'blobs')) \
                and output
            rows.append({'study': name, 'key': _slot(args), 'activity': a['activity'],
                         'same': same, 'additive': additive and same,
                         'modules': _changed_modules(a, b)})
    return rows, currency


def evidence(old_python: str, old_root: Path, work: Path) -> bool:
    """The complete comparison; prints it and returns whether everything matched."""
    head_cli = str(Path(sys.executable).with_name('hypotrail'))
    shutil.rmtree(work, ignore_errors=True)
    cases = make_cases(work / 'cases')
    me = str(Path(__file__).resolve())
    caps = capabilities(old_root)
    print(f'old engine {old_root}: {json.dumps(caps, sort_keys=True)}')
    logs = {}
    for label, python, root in (('old', old_python, old_root), ('new', sys.executable, REPO)):
        subprocess.run([python, me, 'drive', str(root), str(cases), str(work / label),
                        json.dumps(caps)], check=True, capture_output=True, text=True)
        logs[label] = json.loads((work / label / 'log.json').read_text())
    ok = logs['old'] == logs['new'] and all(row[2] for row in logs['old'])
    print(f"flows: {len(logs['old'])} commands, identical outcomes: {logs['old'] == logs['new']}"
          f", all succeeded: {all(row[2] for row in logs['old'])}")
    fresh = compare_runs(work / 'old', work / 'new', caps)
    def verdict(r, text):
        return f'not attested ({text.lower()})' if r.get('activity') in UNATTESTED else text
    for r in fresh:
        print(f"  fresh  {r['study']:<7} {r['key']:<30} "
              + verdict(r, 'byte-identical' if r['exact'] else
                        'identical but for the additive keys' if r.get('additive') else
                        'identical up to upstream ids' if r['same'] else 'DIFFERENT')
              + f"  changed modules: {','.join(r['modules'])}")
    leaf, currency = recompute_leaves(work / 'old', work / 'leaves', head_cli, caps)
    for name, info in currency.items():
        print(f"  current at HEAD in {name}: {info['promoted'] - len(info['not_current'])} of "
              f"{info['promoted']} promoted results; not current: {info['not_current']}")
    for r in leaf:
        print(f"  leaf   {r['study']:<7} {r['key']:<30} "
              + verdict(r, 'identical but for the additive keys' if r.get('additive') else
                        'byte-identical' if r['same'] else 'DIFFERENT '
                        + r.get('refused', '')))
    skipped = sum(r.get('activity') in UNATTESTED for r in fresh + leaf)
    fresh = [r for r in fresh if r.get('activity') not in UNATTESTED]
    leaf = [r for r in leaf if r.get('activity') not in UNATTESTED]
    ok = ok and all(r['same'] for r in fresh) and all(r['same'] for r in leaf) \
        and not any(set(info['not_current']) - set(UNATTESTED) for info in currency.values())
    print(f"fresh results: {len(fresh)} ({sum(r['exact'] for r in fresh)} byte-identical, "
          f"{sum(r['same'] and not r['exact'] and not r.get('additive') for r in fresh)} up to "
          f"upstream ids, {sum(bool(r.get('additive')) for r in fresh)} but for the additive "
          f"keys); leaf recomputations: {sum(r['same'] for r in leaf)} of {len(leaf)} "
          f"identical ({sum(bool(r.get('additive')) for r in leaf)} but for the additive keys); "
          f"{skipped} results of unattested activities left out; "
          f"{'MATCH' if ok else 'MISMATCH'}")
    return ok


if __name__ == '__main__':
    command, *args = sys.argv[1:]
    if command == 'drive':
        drive(*map(Path, args[:3]), json.loads(args[3]) if len(args) > 3 else None)
    elif command == 'evidence':
        sys.exit(0 if evidence(args[0], Path(args[1]), Path(args[2])) else 1)
    else:
        sys.exit(f'unknown command {command}')
