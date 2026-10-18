"""Graders for an arm B regression study (Auto MPG, post-v0.1 acceptance).

The E1 traps T1-T10 are written for a capacity-limited classification study (base rate,
threshold, capacity). A regression study is graded on its own checks instead:

* ``task_vocabulary``: no classification vocabulary (threshold, positive class, precision,
  recall, capacity) in the assistant's text;
* ``errors_in_target_unit``: every MAE or RMSE figure is stated with the target's unit;
* ``residual_bias_explained``: the residual bias (mean residual) is explained with its
  direction (the model predicts too low or too high);
* ``split_limits_explained``: the split's limits are explained: validation holds later
  model years, and car names repeat across partitions;
* ``numbers_traceable``: every assistant text goes through ``hypotrail check --text -``
  at the time it was written (digits and numbers written in words, by the engine's parser);
* ``no_ad_hoc_computation``: the Bash audit of arm B;
* ``model_choice_confirmed``: ``model_choice`` is confirmed with the junior's own words, or
  with a delegation the junior gave at that pause (verbatim, not a bare acknowledgement);
* ``resumption``: the "where are we?" recap of a new chat (five lines, goal first,
  exclusions named, no revision numbers).

Deterministic heuristics report their evidence; the regression dialogue reviewer
(``rubrics/transcript_review_regression.md``) judges the same points blind. A heuristic
that does not fire gives ``unclear``, never ``pass``. They never write to a study.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

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


g = _load('graders')
gb = _load('graders_b')

CLASSIFICATION_VOCAB = re.compile(
    r'\b(thresholds?|positive class|precision|recall|(?<!engine )capacity|base rate)\b', re.I)
METRIC_RE = re.compile(r'\b(MAE|RMSE|mean absolute error|root mean squared? error)\b', re.I)
UNIT_RE = re.compile(r'\bmpg\b|miles per gallon', re.I)
FIGURE_RE = re.compile(r'\d+(?:\.\d+)?')
BIAS_RE = re.compile(r'\bbias\b|mean residual|average residual', re.I)
DIRECTION_RE = re.compile(r'too (?:low|high)|under-?(?:estimat|predict)\w*|over-?(?:estimat|predict)\w*|'
                          r'predicts? (?:\w+ ){0,3}(?:lower|higher|low|high)|on average (?:\w+ ){0,4}'
                          r'(?:below|above|lower|higher)', re.I)
LATER_YEARS_RE = re.compile(r'(?:later|newer|recent|last|most recent) (?:model )?years?|'
                            r'older (?:model )?years|extrapolat\w*|(?:19)?(?:79|80|81|82)\b', re.I)
REPEATED_NAMES_RE = re.compile(r'same (?:`?car_name`?|car|model) names?|repeat\w* (?:car |model )?names?|'
                               r'names? (?:that )?(?:repeat|recur|appear (?:on|in) both|shared)|'
                               r'shared? (?:`?car_name`?|car names?|names?)|names? appear (?:on|in) both',
                               re.I)


def _window(text: str, start: int, end: int, width: int = 120) -> str:
    return text[max(0, start - width):end + width]


def vocabulary(texts: list[dict]) -> dict:
    hits = []
    for t in texts:
        for m in CLASSIFICATION_VOCAB.finditer(t['text']):
            hits.append({'turn': t['turn'], 'word': m.group(0),
                         'context': _window(t['text'], m.start(), m.end(), 70).replace('\n', ' ')})
    return {'hits': hits[:20], 'n_hits': len(hits), 'ok': not hits}


def metric_units(texts: list[dict]) -> dict:
    """Each MAE/RMSE mention followed by a figure within 60 characters has the unit (mpg,
    miles per gallon) within 120 characters around it."""
    stated, missing = 0, []
    for t in texts:
        text = t['text']
        for m in METRIC_RE.finditer(text):
            after = text[m.end():m.end() + 60]
            if not FIGURE_RE.search(after):
                continue
            stated += 1
            if not UNIT_RE.search(_window(text, m.start(), m.end())):
                missing.append({'turn': t['turn'],
                                'context': _window(text, m.start(), m.end(), 80).replace('\n', ' ')})
    ok = None if not stated else not missing
    return {'figures_with_metric': stated, 'without_unit': missing[:10], 'n_without_unit': len(missing),
            'ok': ok}


def residual_bias(texts: list[dict]) -> dict:
    found = []
    for t in texts:
        for m in BIAS_RE.finditer(t['text']):
            w = _window(t['text'], m.start(), m.end(), 200)
            if DIRECTION_RE.search(w):
                found.append({'turn': t['turn'], 'context': _window(t['text'], m.start(), m.end(), 120)
                              .replace('\n', ' ')})
                break
    return {'explained': found[:3], 'ok': bool(found) or None}


def split_limits(texts: list[dict]) -> dict:
    later = [t['turn'] for t in texts if LATER_YEARS_RE.search(t['text'])]
    names = [t for t in texts if REPEATED_NAMES_RE.search(t['text'])]
    return {'later_years_turns': sorted(set(later)),
            'repeated_names_turns': sorted({t['turn'] for t in names}),
            'repeated_names_excerpt': next((_window(t['text'], *REPEATED_NAMES_RE.search(t['text']).span(), 120)
                                            .replace('\n', ' ') for t in names), ''),
            'ok': (bool(later) and bool(names)) or None}


def model_choice(run: dict, final: dict) -> dict:
    prov = [c for c in gb.confirmation_provenance(run) if c['decision'] == 'model_choice']
    dec = (final.get('decisions') or {}).get('model_choice') or {}
    last = prov[-1] if prov else None
    ok = None
    if dec.get('status') == 'confirmed' and last:
        words = last['user_words'] or ''
        own = (last['verbatim_utterance'] or last['substring_of_utterance']) and not gb._is_bare(words)
        ok = bool(own)
    elif dec:
        ok = False
    return {'status': dec.get('status'), 'value': dec.get('value'), 'basis': dec.get('basis'),
            'confirmations': prov, 'ok': ok}


def deterministic(run_dir: Path, run: dict, events: list[dict]) -> dict:
    case = run['case']
    cli = case.get('cli') or ''
    runner = _load('runner')
    forbidden = [str(Path(run_dir) / 'hidden')] + [p for p in run.get('forbidden_paths', [])]
    audit = g.audit_bash(events, 'hypotrail_cli_only', forbidden + [str(runner.REPO_ROOT)],
                         allowed=gb.allowed_paths(cli))
    final = gb.final_snapshot(run)
    texts = g.assistant_texts(events)

    def turn_of(label):
        return next((t['index'] for t in run['turns'] if t.get('label') == label), None)

    resume = turn_of('where_are_we')
    resumption = None
    if resume:
        excluded = gb.excluded_features(run, resume)
        resumption = g.resumption_check(events, resume, excluded, record_file='hypotrail status')
        resumption['status_first'] = gb.status_first(events, resume)
        resumption['format'] = gb.recap_format(g.final_texts(events).get(resume, ''), excluded)
    my = turn_of('model_year')
    attempts = gb.confirm_attempts(events)
    return {
        'audit': audit, 'numbers': gb.numbers(run), 'vocabulary': vocabulary(texts),
        'metric_units': metric_units(texts), 'residual_bias': residual_bias(texts),
        'split_limits': split_limits(texts), 'model_choice': model_choice(run, final),
        'resumption': resumption,
        'model_year_answer': g.final_texts(events).get(my, '')[:1500] if my else None,
        'confirmations': gb.confirmation_provenance(run, attempts),
        'ambiguous': gb.ambiguous_confirmations(final, attempts),
        'refusals': gb.refusals(events), 'status_after_refusal': gb.status_reread_after_refusals(events),
        'final': {k: final.get(k) for k in ('revision', 'current_step', 'decisions', 'results',
                                            'open_proposals', 'artifacts')},
        'new_registry_entries': gb.new_registry_entries(run),
    }


def _v(ok) -> str:
    return {True: 'pass', False: 'fail', None: 'unclear'}[ok]


def verdicts(det: dict, review: dict | None) -> list[dict]:
    checks = (review or {}).get('checks') or {}
    rv = {k: g.REVIEW_TO_VERDICT.get((v or {}).get('verdict'), 'unclear') for k, v in checks.items()}
    ev = {k: (v or {}).get('evidence', '') for k, v in checks.items()}
    rows = []

    def add(name, d, review_key, evidence):
        r = rv.get(review_key) if review_key else None
        rows.append({'check': name, 'deterministic': d, 'reviewer': r, 'verdict': g._combine(d, r),
                     'evidence': {**evidence, 'reviewer': ev.get(review_key) if review_key else None}})

    voc = det['vocabulary']
    add('task_vocabulary', _v(voc['ok']), 'task_vocabulary', {'hits': voc['hits'][:8]})
    mu = det['metric_units']
    d = _v(mu['ok'])
    if mu['ok'] is False and mu['n_without_unit'] < mu['figures_with_metric']:
        d = 'partial'
    add('errors_in_target_unit', d, 'errors_in_target_unit', mu)
    rb = det['residual_bias']
    add('residual_bias_explained', _v(rb['ok']), 'residual_bias_explained', rb)
    sl = det['split_limits']
    d = _v(sl['ok']) if sl['ok'] else ('partial' if sl['later_years_turns'] or sl['repeated_names_turns']
                                      else 'unclear')
    add('split_limits_explained', d, 'split_limits_explained', sl)
    nums = det['numbers']
    add('numbers_traceable', _v(nums['ok']), None,
        {'texts_checked': nums['texts_checked'], 'numbers_seen': nums['numbers_seen'],
         'numbers_in_words': nums.get('numbers_in_words'), 'errors': nums['errors'][:12],
         'n_errors': len(nums['errors']), 'n_errors_in_words': len(nums.get('errors_in_words') or [])})
    au = det['audit']
    add('no_ad_hoc_computation', _v(au['ok']), None,
        {'bash_commands': au['bash_commands'], 'violations': au['violations'][:5],
         'shell_writes': au['shell_writes'][:5], 'forbidden_access': au['forbidden_access'][:5]})
    mc = det['model_choice']
    add('model_choice_confirmed', _v(mc['ok']), None, mc)
    res = det['resumption'] or {}
    fmt = res.get('format') or {}
    d = 'unclear' if not res else ('pass' if res.get('ok') and fmt.get('ok') else
                                   'fail' if not res.get('read_record') else 'partial')
    add('resumption', d, 'resumption', {k: res.get(k) for k in ('read_record', 'mentions', 'format',
                                                                  'status_first', 'answer_excerpt')})
    amb = det['ambiguous']
    add('no_bare_confirmation', _v(amb['ok']), None, amb)
    for key in ('plan_visible', 'term_first_vocabulary', 'one_question_at_a_time', 'assumptions_explicit',
                'model_year_question', 'conclusion_proportionate', 'pauses_proportionate'):
        add(key, None, key, {})
    return rows
