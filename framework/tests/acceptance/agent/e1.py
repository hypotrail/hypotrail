"""E1 steelman driver (plan WP0.8; protocol in docs/research/E1-STEELMAN.md).

    uv run --project framework python framework/tests/acceptance/agent/e1.py run \\
        --case bank --out RUN_DIR
    uv run --project framework python framework/tests/acceptance/agent/e1.py review --run RUN_DIR
    uv run --project framework python framework/tests/acceptance/agent/e1.py grade --run RUN_DIR
    uv run --project framework python framework/tests/acceptance/agent/e1.py summary RUN_DIR...

RUN_DIR must be outside the repository (raw transcripts are never committed). For the
synthetic case, truth.json is written to ``RUN_DIR/hidden`` and never copied into the
agent workspace, which is a separate temporary directory.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def _load(name: str):
    key = f'hypotrail_agent_{name}'
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, HERE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


runner, graders, cases = _load('runner'), _load('graders'), _load('cases')

CHECK_VERDICT = {'type': 'object', 'additionalProperties': False,
                 'properties': {'verdict': {'enum': ['handled', 'partially', 'not_handled',
                                                     'not_applicable', 'unclear']},
                                'evidence': {'type': 'string'}},
                 'required': ['verdict', 'evidence']}
BLIND_CHECKS = ['leakage_post_outcome', 'availability_at_prediction_time', 'special_values',
                'class_imbalance_metrics', 'split_before_eda', 'eda_on_training_only',
                'preprocessing_fit_on_train', 'baseline_comparison', 'threshold_selection_caveat',
                'capacity_change_handling', 'causal_language', 'uncertainty_reported',
                'decisions_recorded', 'numbers_traceable', 'conclusion_proportionate']
TRANSCRIPT_CHECKS = ['plan_visible', 'term_first_vocabulary', 'one_question_at_a_time',
                     'ambiguous_reply_handling', 'assumptions_explicit', 'resumption',
                     'capacity_change_explained', 'conclusion_proportionate', 'pauses_proportionate']


def _checks_schema(names):
    return {'type': 'object', 'additionalProperties': False,
            'properties': {n: CHECK_VERDICT for n in names}, 'required': list(names)}


BLIND_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'final_model': {'type': 'object', 'additionalProperties': False, 'properties': {
            'description': {'type': 'string'},
            'features_used': {'type': 'array', 'items': {'type': 'string'}},
            'features_excluded': {'type': 'array', 'items': {
                'type': 'object', 'additionalProperties': False,
                'properties': {'name': {'type': 'string'}, 'reason': {'type': 'string'}},
                'required': ['name', 'reason']}}},
            'required': ['description', 'features_used', 'features_excluded']},
        'checks': _checks_schema(BLIND_CHECKS),
        'overall_validity': {'enum': ['sound', 'minor_issues', 'major_issues', 'invalid']},
        'summary': {'type': 'string'}},
    'required': ['final_model', 'checks', 'overall_validity', 'summary']}
TRANSCRIPT_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'checks': _checks_schema(TRANSCRIPT_CHECKS),
                   'overall': {'enum': ['excellent', 'good', 'weak', 'poor']},
                   'summary': {'type': 'string'}},
    'required': ['checks', 'overall', 'summary']}


def persona_chats(path: Path = HERE / 'e1_persona.yaml') -> list[list[dict]]:
    doc = yaml.safe_load(path.read_text(encoding='utf-8'))
    return doc['chats']


def _assert_outside_repo(path: Path) -> Path:
    path = Path(path).resolve()
    if path == runner.REPO_ROOT or runner.REPO_ROOT in path.parents:
        sys.exit(f'{path} is inside the repository; raw runs must stay outside it')
    return path


# --------------------------------------------------------------------------- run

def cmd_run(a) -> None:
    run_dir = _assert_outside_repo(a.out)
    arm = runner.Arm.load(Path(a.arm))
    if a.model:
        arm.model = a.model
    hidden = run_dir / 'hidden'
    prepare = cases.preparer(a.case, hidden, a.seed)
    caps = runner.Caps(max_agent_turns=a.max_agent_turns, max_budget_usd_per_chat=a.chat_budget,
                       max_budget_usd_total=a.total_budget, timeout_s_per_turn=a.turn_timeout)
    chats = persona_chats()
    if a.only_first:
        chats = [chats[0][:a.only_first]]
    log_file = (run_dir / 'progress.log')
    run_dir.mkdir(parents=True, exist_ok=True)

    def log(msg):
        print(msg, flush=True)
        with log_file.open('a', encoding='utf-8') as fh:
            fh.write(msg + '\n')

    record = runner.run_conversation(
        arm=arm, chats=chats, run_dir=run_dir, prepare_workspace=prepare, caps=caps,
        workspace_base=Path(a.workspace_base) if a.workspace_base else None,
        forbidden_paths=[hidden], meta={'case': a.case, 'repeat': a.repeat, 'persona': 'e1-junior'},
        log=log)
    log(json.dumps({k: record[k] for k in ('total_cost_usd', 'wall_s', 'stopped', 'repo_guard')}))


# --------------------------------------------------------------------------- review

def dialogue_markdown(run: dict) -> str:
    lines = ['# Dialogue', '']
    chat = None
    for t in run['turns']:
        if t['chat'] != chat:
            chat = t['chat']
            lines += [f'## Chat {chat}' + (' (new conversation, no memory of chat 1)' if chat > 1 else ''), '']
        lines += [f'### Turn {t["index"]}: analyst', '', t['utterance'], '',
                  f'### Turn {t["index"]}: assistant', '', (t.get('final_text') or '(no reply)'), '']
    return '\n'.join(lines)


def cmd_review(a) -> None:
    run_dir = _assert_outside_repo(a.run)
    run = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
    out = run_dir / 'review'
    replace = {run['workspace']: '<study>', str(run_dir): '<run>'}
    blind_dir = runner.make_workspace(a.workspace_base, prefix='hypotrail-review-')
    graders.anonymise_study(run_dir / 'workspace', blind_dir / 'study', replace=replace)
    prompt = (HERE / 'rubrics/blind_review.md').read_text(encoding='utf-8')
    blind = graders.fresh_agent_grade(blind_dir / 'study', prompt, BLIND_SCHEMA, out / 'blind',
                                      model=a.model, max_budget_usd=a.budget)
    print('blind review', blind['subtype'], blind['cost_usd'])
    dlg_dir = runner.make_workspace(a.workspace_base, prefix='hypotrail-dialogue-')
    text = dialogue_markdown(run)
    for k, v in replace.items():
        text = text.replace(k, v)
    (dlg_dir / 'dialogue.md').write_text(text, encoding='utf-8')
    prompt = (HERE / 'rubrics/transcript_review.md').read_text(encoding='utf-8')
    dialogue = graders.fresh_agent_grade(dlg_dir, prompt, TRANSCRIPT_SCHEMA, out / 'transcript',
                                         model=a.model, max_budget_usd=a.budget)
    print('transcript review', dialogue['subtype'], dialogue['cost_usd'])


# --------------------------------------------------------------------------- grade

def _turn_index(run: dict, label: str) -> int | None:
    return next((t['index'] for t in run['turns'] if t.get('label') == label), None)


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8', errors='replace') if path.is_file() else ''


def deterministic_grades(run_dir: Path) -> dict:
    run = json.loads((run_dir / 'run.json').read_text(encoding='utf-8'))
    events = runner.load_transcript(run_dir)
    case = run['case']
    ws = run_dir / 'workspace'
    truth = json.loads(Path(case['truth_path']).read_text()) if case.get('truth_path') else None
    tc = graders.case_traps(case['case'], truth)
    arm_policy = runner.Arm.load(HERE / 'arms' / run['arm']).bash_policy
    audit = graders.audit_bash(events, arm_policy, [str(run_dir / 'hidden'), str(runner.REPO_ROOT)])

    facts = graders.recompute_facts(ws / case['data'], case['sep'], case['target'], case['positive'])
    results = graders.tool_results(events)
    uses = graders.tool_uses(events)
    docs = [t['utterance'] for t in run['turns']] + [_read(ws / f) for f in case['files'] if f != case['data']]
    exported = [_read(f) for f in (ws / 'reports').glob('*.html')] if (ws / 'reports').is_dir() else []
    sources = {
        'data_facts': facts['values'],
        'tool_output': graders.ValueSet(graders.numbers_in(results.values())),
        'agent_code': graders.ValueSet(graders.numbers_in(json.dumps(u['input']) for u in uses)),
        'user_and_docs': graders.ValueSet(graders.numbers_in(docs)),
        'exported_notebook_only': graders.ValueSet(graders.numbers_in(exported)),
    }
    texts = graders.assistant_texts(events)
    numbers = graders.trace_numbers(texts, sources)
    study_md = _read(ws / 'STUDY.md')
    notebook = _read(ws / 'notebooks/study.py')
    record_numbers = graders.trace_numbers([{'text': study_md, 'turn': None}], sources)

    cap_turn = _turn_index(run, 'capacity_100')
    refit = graders.detect_refit(events, {cap_turn} if cap_turn else set(), ws) if cap_turn else None
    resume_turn = _turn_index(run, 'where_are_we')
    resumption = graders.resumption_check(events, resume_turn, tc['leak']) if resume_turn else None
    lost = graders.lost_sales_mentions(texts + [{'text': study_md, 'turn': 'STUDY.md'}])
    eda = graders.eda_before_split(events, case['target'])
    amb = graders.ambiguous_confirmations_recorded(study_md)
    cols = list(tc['sentinel'])
    pair = next((p for p in facts['named']['sentinel_pairs'] if sorted(p['columns']) == sorted(cols)), None)
    return {'run': run, 'truth': truth, 'case': case['case'], 'audit': audit,
            'sentinel_both': pair['both'] if pair else None,
            'facts': facts['named'], 'numbers': numbers, 'record_numbers': record_numbers,
            'refit': refit, 'resumption': resumption, 'lost_sales': lost, 'eda_order': eda,
            'ambiguous': amb, 'study_text': study_md + '\n' + notebook,
            'artifacts': {'STUDY.md': bool(study_md), 'notebook_bytes': len(notebook),
                          'files': sorted(str(p.relative_to(ws)) for p in ws.rglob('*')
                                          if p.is_file() and '.claude' not in p.parts)}}


def cmd_grade(a) -> None:
    run_dir = _assert_outside_repo(a.run)
    det = deterministic_grades(run_dir)
    review_path = run_dir / 'review/blind/reviewer.json'
    transcript_path = run_dir / 'review/transcript/reviewer.json'
    review = json.loads(review_path.read_text())['structured_output'] if review_path.is_file() else None
    treview = json.loads(transcript_path.read_text())['structured_output'] if transcript_path.is_file() else None
    det['transcript_review'] = treview
    traps = graders.grade_traps(case=det['case'], truth=det['truth'], review=review, deterministic=det)
    run = det.pop('run')
    det.pop('truth')
    det.pop('study_text')
    costs = runner.recompute_turn_costs(run['turns'])
    for t, c in zip(run['turns'], costs):
        t['cost_usd'] = c
    out = {'case': det['case'], 'arm': run['arm'], 'repeat': run['meta'].get('repeat'),
           'cost_usd': round(sum(costs), 4), 'wall_s': run['wall_s'], 'stopped': run['stopped'],
           'turns': [{k: t[k] for k in ('index', 'chat', 'label', 'wall_s', 'cost_usd', 'agent_turns',
                                        'result_subtype', 'tool_calls', 'models', 'cli_version')}
                     for t in run['turns']],
           'repo_guard': run['repo_guard'], 'traps': traps, 'blind_review': review,
           'transcript_review': treview, 'deterministic': det}
    (run_dir / 'grade.json').write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
    for t in traps:
        print(f"{t['trap']:4} {t['key']:24} det={t['deterministic']!s:8} rev={t['reviewer']!s:8} -> {t['verdict']}")


# --------------------------------------------------------------------------- summary

def cmd_summary(a) -> None:
    grades = [json.loads((_assert_outside_repo(r) / 'grade.json').read_text()) for r in a.runs]
    cols = [f"{g['case']} {g.get('repeat') or ''}".strip() for g in grades]
    print('| Trap | ' + ' | '.join(cols) + ' |')
    print('|---|' + '---|' * len(cols))
    for i, (tid, key, title) in enumerate(graders.TRAPS):
        cells = []
        for g in grades:
            row = next(t for t in g['traps'] if t['trap'] == tid)
            cells.append(f"{row['verdict']} (d:{row['deterministic'] or '-'}, r:{row['reviewer'] or '-'})")
        print(f'| {tid} {title} | ' + ' | '.join(cells) + ' |')
    print()
    for g, c in zip(grades, cols):
        print(f"- {c}: ${g['cost_usd']:.2f}, {g['wall_s'] / 60:.0f} min, {len(g['turns'])} turns, "
              f"stopped={g['stopped']}, blind={((g.get('blind_review') or {}).get('overall_validity'))}, "
              f"dialogue={((g.get('transcript_review') or {}).get('overall'))}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--case', choices=['bank', 'synthetic'], required=True)
    r.add_argument('--arm', default=str(HERE / 'arms/arm_a'))
    r.add_argument('--out', required=True)
    r.add_argument('--model')
    r.add_argument('--seed', type=int, default=20261018)
    r.add_argument('--repeat', default='r1')
    r.add_argument('--workspace-base')
    r.add_argument('--max-agent-turns', type=int, default=80)
    r.add_argument('--chat-budget', type=float, default=15.0, help='cumulative dollars per chat session')
    r.add_argument('--total-budget', type=float, default=40.0)
    r.add_argument('--turn-timeout', type=int, default=1800)
    r.add_argument('--only-first', type=int, default=0, help='smoke test: first N utterances of chat 1')
    r.set_defaults(func=cmd_run)
    v = sub.add_parser('review')
    v.add_argument('--run', required=True)
    v.add_argument('--model', default='opus')
    v.add_argument('--budget', type=float, default=6.0)
    v.add_argument('--workspace-base')
    v.set_defaults(func=cmd_review)
    g = sub.add_parser('grade')
    g.add_argument('--run', required=True)
    g.set_defaults(func=cmd_grade)
    s = sub.add_parser('summary')
    s.add_argument('runs', nargs='+')
    s.set_defaults(func=cmd_summary)
    a = p.parse_args(argv)
    a.func(a)


if __name__ == '__main__':
    main()
