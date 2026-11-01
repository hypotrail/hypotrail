"""``hypotrail case``: the structural profile and the feasibility of the final test, before
sealing (onboarding Lots 2 and 3; CLI-CONTRACT §20).

    hypotrail case profile --study DIR
    hypotrail case check --feasibility --study DIR

``profile`` shows the structural profile of every row recorded by ``hypotrail new``: per
column its type, missing cells, distinct values and a few examples; the target, once named,
only by its label set or range and its missing count; the suspicious columns.

``check --feasibility`` (:func:`feasibility`) builds the case the answers describe, in
memory, runs the review-v1 planner on it exactly as ``init`` will, and reports **counts
without the target**: rows, final-test and development rows, the effective fraction, the
period covered by the prediction clock, the ties at the cut, the groups, the delayed-label
rows; then a pass or fail per documented minimum (:func:`mlkit.study.partition.guard_checks`).
No proportion of a target value and no count per stratum is returned, so the final test
cannot be shopped for. The plan is also given in words and counts, with a digest that the
``final_test`` answer must name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping

from . import case_draft as cd
from . import commands as cmd
from .errors import StudyError

SCHEMA = 'hypotrail.case-check/1'
PROFILE_SCHEMA = 'hypotrail.case-profile-view/1'


def case_document(case_dir: Path, record: Mapping, prof: Mapping) -> dict:
    """The ``hypotrail.case/1`` document the answers describe (not written)."""
    return cd.build_case(prof, record['answers'], case_id=record['case_id'],
                         title=record['title'], data_path=record['data']['path'],
                         profile_sha256=record['profile_sha256'],
                         original_name=Path(record['data']['original']).name)


def _number(value):
    value = float(value)
    return int(value) if value.is_integer() else value


def _fmt(n: int, lang: str) -> str:
    text = f'{n:,}'
    return text.replace(',', ' ') if lang == 'fr' else text


def _pct(x: float, lang: str) -> str:
    text = f'{x * 100:.0f} %' if lang == 'fr' else f'{x * 100:.0f}%'
    return text


def plan_words(deduction: Mapping, counts: Mapping, task: str) -> dict:
    """The final test in words and counts, in both languages."""
    out = {}
    for lang in ('en', 'fr'):
        n, pct = _fmt(counts['final_rows'], lang), _pct(counts['fraction'], lang)
        clock, group = deduction['clock'], deduction['group_column']
        period = counts.get('period')
        if deduction['method'] == 'temporal':
            span = (f', {clock} from {period["final"][0]} to {period["final"][1]}' if lang == 'en'
                    else f', {clock} de {period["final"][0]} à {period["final"][1]}')
            text = (f'the latest {pct} of the rows by {clock}: {n} rows{span}' if lang == 'en'
                    else f'les {pct} des lignes les plus récentes selon {clock} : {n} lignes'
                         f'{span}')
            if group:
                text += (f', every row of one {group} on one side' if lang == 'en' else
                         f', toutes les lignes d\'un même {group} du même côté')
        elif group:
            g = _fmt(counts['groups']['final'], lang)
            text = (f'{pct} of the rows, drawn as whole {group} groups: {n} rows from {g} '
                    f'groups' if lang == 'en' else
                    f'{pct} des lignes, tirées par {group} entiers : {n} lignes de {g} groupes')
        elif task == 'binary':
            text = (f'a random {pct} of the rows, in the same proportion for each value of the '
                    f'target: {n} rows' if lang == 'en' else
                    f'{pct} des lignes tirées au hasard, dans la même proportion pour chaque '
                    f'valeur de la cible : {n} lignes')
        else:
            text = (f'a random {pct} of the rows, in the same proportion from each fifth of the '
                    f'target\'s range: {n} rows' if lang == 'en' else
                    f'{pct} des lignes tirées au hasard, dans la même proportion dans chaque '
                    f'cinquième de l\'étendue de la cible : {n} lignes')
        delayed = counts.get('delayed_label_rows')
        if delayed:
            text += (f'; {_fmt(delayed, lang)} development rows whose outcome is known only '
                     f'after the cut are kept out of training' if lang == 'en' else
                     f' ; {_fmt(delayed, lang)} lignes de développement dont l\'issue n\'est '
                     f'connue qu\'après la coupure sont écartées de l\'apprentissage')
        out[lang] = text[:1].upper() + text[1:] + '.'
    return out


def feasibility(case_dir: Path, record: Mapping, prof: Mapping) -> dict:
    """``{status: pass|fail|incomplete|refused, ...}``: the final test the answers lead to,
    as counts without the target (see the module docstring)."""
    from . import case as c
    from . import data as dt
    from . import partition
    missing = [q for q in cd.QUESTIONS[:-1] if q not in record['answers']]
    if missing:
        return {'schema': SCHEMA, 'status': 'incomplete', 'missing': missing,
                'problems': [f'answer {", ".join(missing)} first']}
    document = case_document(case_dir, record, prof)
    try:
        c.check_document(document)
        case = c.require_supported(c.Case(path=(case_dir / c.CASE_FILE).resolve(),
                                          document=document))
        index = dt.row_index(case)
        frame = dt.read_frame(case, index)
        assigned = partition.assign(case, index, frame, reliability_profile='review-v1')
    except (c.CaseError, StudyError) as exc:
        error = exc.to_dict()
        return {'schema': SCHEMA, 'status': 'refused', 'error': error,
                'problems': [error['message']]
                + [p.get('problem', '') for p in error.get('problems') or []]
                + [r.get('reason', '') for r in (error.get('details') or {}).get('reasons') or []]}
    contract = document['analysis_contract']
    deduction = partition.deduce(contract, case.task)
    checks = partition.guard_checks(case, frame, assigned)
    rec = assigned['record']
    final = list(assigned['final_test'])
    development = list(assigned['development'])
    counts = {'rows': rec['n_rows'], 'final_rows': len(final),
              'development_rows': len(development),
              'fraction': round(len(final) / rec['n_rows'], 4),
              'delayed_label_rows': len(assigned.get('training_excluded') or [])}
    if deduction['method'] == 'temporal':
        clock = deduction['clock']
        import pandas as pd
        values = pd.to_numeric(frame[clock], errors='coerce')
        counts['ties_at_cut'] = rec['order'].get('ties_at_cut')
        counts['period'] = {
            'clock': clock,
            'development': [_number(values.loc[development].min()),
                            _number(values.loc[development].max())],
            'final': [_number(values.loc[final].min()), _number(values.loc[final].max())]}
    group = contract['dependencies'].get('group_column')
    if group:
        names = frame[group].astype(str)
        counts['groups'] = {'column': group, 'total': int(names.nunique()),
                            'final': int(names.loc[final].nunique()),
                            'development': int(names.loc[development].nunique())}
    if (rec.get('groups') or {}).get('n_groups'):
        counts['duplicate_groups'] = rec['groups']['n_groups']
    failed = [ch for ch in checks if ch['status'] == 'fail']
    digest = hashlib.sha256(json.dumps(
        {'case': document, 'final': sorted(final)}, sort_keys=True,
        ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
    deduction = dict(deduction, guards=[{k: ch[k] for k in ('check', 'status', 'required')}
                                        for ch in checks])
    return {'schema': SCHEMA, 'status': 'fail' if failed else 'pass', 'plan': digest,
            'method': deduction['method'], 'rule': deduction['rule'], 'deduction': deduction,
            'counts': counts, 'checks': checks,
            'words': plan_words(deduction, counts, case.task),
            'problems': [ch['reason'] for ch in failed],
            'reveals': 'counts without the target; each minimum as pass or fail only'}


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('verb', choices=('profile', 'check'),
                        help='profile: the structural profile of every row; check '
                             '--feasibility: the final test the answers lead to, as counts')
    parser.add_argument('--feasibility', action='store_true',
                        help='with check: counts without the target and pass or fail on the '
                             'minimums')


def main(args: argparse.Namespace) -> cmd.Outcome:
    from . import cmd_prepare as prep
    study, case_dir = prep.locate(args.study)
    record = prep.load(case_dir)
    prof = prep.load_profile(case_dir)
    if args.verb == 'profile':
        if args.feasibility:
            raise StudyError('invalid_arguments', '--feasibility goes with check.')
        target = ((record['answers'].get('target') or {}).get('value') or {}).get('column')
        return cmd.Outcome({'schema': PROFILE_SCHEMA, 'ok': True, 'study': str(study),
                            'case': str(case_dir), 'file': prof['file'],
                            'sha256': prof['sha256'], 'rows': prof['rows'],
                            'columns': cd.column_view(prof, target),
                            'duplicates': prof['duplicates'],
                            'suspicious': cd.suspicious(prof, target),
                            'reveals': prof['reveals']})
    if not args.feasibility:
        raise StudyError('invalid_arguments', 'case check takes --feasibility.')
    out = feasibility(case_dir, record, prof)
    payload = {'ok': True, 'study': str(study), 'case': str(case_dir), **out}
    return cmd.Outcome(payload)
