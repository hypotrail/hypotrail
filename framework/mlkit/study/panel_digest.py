"""The digest additions of the one-page study panel (contract P1, CLI-CONTRACT §17.2).

``status --summary --digest`` appends, after ``texts`` (:data:`view.DIGEST_SUMMARY_KEYS`):
``panel_contract``, ``automation``, ``review_queue``, ``defensibility``, ``ledger``,
``sample``, ``headlines`` and ``criterion_configurations``; inside existing structures it adds
``results.<slot>.channel``, ``open_proposals[].data_contingent`` and the ``texts.{en,fr}``
keys of §17.2.3. Every key is read from the view the summary was made from and from the
study's own records (revisions, exposure ledger); no clock is read, nothing is written, and
nothing here is computed by the panel. The plain summary (without ``--digest``) is unchanged.

Pure apart from reading the study through :class:`mlkit.study.read.Study`; it imports neither
pandas nor scikit-learn.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import audience, cite, companion_env, criterion as criterion_mod, exposure, junior
from . import records as rec
from . import state as st

SUMMARY_AUTOMATION_KEYS = ('variant', 'active', 'started_revision', 'ended')
AUTOMATION_ENDED_KEYS = ('revision', 'reason')
SUMMARY_REVIEW_KEYS = ('items', 'done', 'total')
SUMMARY_DEFENSIBILITY_KEYS = ('kind', 'count', 'items')
DEFENSIBILITY_ITEM_KEYS = ('id', 'severity')
DEFENSIBILITY_KINDS = ('warn', 'limits', 'pending')
SUMMARY_LEDGER_KEYS = ('final_test', 'target_looks', 'configurations')
LEDGER_FINAL_TEST_KEYS = ('openings', 'max')
LEDGER_LOOK_KEYS = ('eda', 'sample', 'total')
LEDGER_CONFIGURATION_KEYS = ('tried', 'reference')
SUMMARY_SAMPLE_KEYS = ('seed', 'row_keys', 'recorded')
HEADLINE_KEYS = ('decision_id', 'basis', 'results')
SUMMARY_CRITERION_CONFIG_KEYS = ('metric', 'unit', 'bound', 'configurations')
CRITERION_BOUND_KEYS = ('value', 'reference', 'minimum', 'result_id', 'path')
CRITERION_CONFIGURATION_KEYS = ('slot', 'value', 'result_id', 'path', 'point_meets_bound',
                                'gain', 'low', 'high', 'status', 'judged_on')
CHANNEL_DEFAULT = 'chat'
BASELINE = 'fit.baseline'
TOLERANCE = 1e-12
_RESERVE = 'run.reserve'


# --- automation and the review queue (§17.2.1) ----------------------------------------------

def automation(state: Mapping) -> dict | None:
    """``automation``: null for a study created without ``init --automation``."""
    record = st.automation_of(state)
    if record is None:
        return None
    ended = record.get('ended')
    return {'variant': record.get('mode'),
            'active': record.get('status') == st.AUTOMATION_RUNNING,
            'started_revision': record.get('started_revision'),
            'ended': ({'revision': ended.get('revision'), 'reason': ended.get('reason')}
                      if isinstance(ended, Mapping) else None)}


def automatic_decisions(records: Iterable[Mapping]) -> list[str]:
    """The distinct decisions a confirmation with basis ``automatic`` was recorded for, in the
    order of the revisions (the opening of a demonstration included)."""
    out: list[str] = []
    for record in records:
        if record.get('action') != 'decide.confirm':
            continue
        params, result = record.get('params') or {}, record.get('result') or {}
        if (result.get('basis') or params.get('basis')) != st.AUTOMATIC:
            continue
        decision = result.get('decision_id') or params.get('decision_id')
        if decision and decision not in out:
            out.append(decision)
    return out


def review_queue(state: Mapping, built: Mapping, records: list[Mapping]) -> dict | None:
    """``review_queue``: null without automation; else the decisions still confirmed
    automatically (``view.review_queue``), how many the automatic mode confirmed in all, and
    how many the junior has reviewed."""
    if st.automation_of(state) is None:
        return None
    items = [dict(item) for item in built.get('review_queue') or []]
    total = len(automatic_decisions(records))
    return {'items': items, 'done': max(total - len(items), 0), 'total': total}


# --- defensibility (§17.2.2) -----------------------------------------------------------------

def _severity(item: Mapping, decisions: Mapping) -> str:
    severity = audience.LIMIT_SEVERITY.get(item.get('id'), audience.CAVEAT)
    if item.get('id') == 'unconfirmed_decisions':
        reopened = any((decisions.get(d) or {}).get('status') == 'reconfirm_required'
                       for d in item.get('decisions') or [])
        return audience.BLOCKING if reopened else severity
    if item.get('id') == 'stale_results':
        return audience.BLOCKING if item.get('cited_by') else audience.CAVEAT
    return severity


def defensibility(built: Mapping, summary_out: Mapping) -> dict:
    """``defensibility``: every ``not_yet_defensible`` id of the summary (``top`` then
    ``more``) with its severity (``audience.LIMIT_SEVERITY``), the pill's kind and count."""
    by_id = {}
    for item in built.get('not_yet_defensible') or []:
        by_id.setdefault(item['id'], item)
    limits = summary_out.get('not_yet_defensible') or {}
    ids = [x['id'] for x in limits.get('top') or []] + list(limits.get('more') or [])
    decisions = built.get('decisions') or {}
    items = [{'id': i, 'severity': _severity(by_id.get(i, {'id': i}), decisions)} for i in ids]
    severities = [x['severity'] for x in items]
    done = (built.get('next_action') or {}).get('kind') == 'done'
    if audience.BLOCKING in severities:
        kind = 'warn'
    elif done:
        kind = 'limits'
    else:
        kind = 'pending'
    count = (severities.count(audience.CAVEAT) if kind == 'limits'
             else sum(s != audience.CONTEXT for s in severities))
    return {'kind': kind, 'count': count, 'items': items}


# --- the ledger line and the sample (§17.2.2, §17.3) ------------------------------------------

def sample(study, state: Mapping, entries: list[Mapping]) -> dict | None:
    """``sample``: ``{seed, row_keys, recorded}`` of the step-1 sample, or null when none can
    be drawn. The values are read with ``data --json``."""
    drawn = exposure.current_sample(study, state, entries)
    if drawn is None:
        return None
    return {'seed': drawn['seed'], 'row_keys': list(drawn['row_keys']),
            'recorded': bool(exposure.sample_records(entries, drawn['seed']))}


def ledger(built: Mapping, entries: list[Mapping]) -> dict:
    """``ledger``: the counts of the path's ledger line: the final test's openings, the looks
    at the target (the exploration's and the step-1 sample's), the configurations tried."""
    final = built.get('final_test') or {}
    status = final.get('status')
    looks = (built.get('eda_looks') or {}).get('target_looks') or 0
    samples = len(exposure.sample_records(entries))
    return {'final_test': (None if status in (None, 'absent')
                           else {'openings': 1 if status == 'opened' else 0, 'max': 1}),
            'target_looks': {'eda': looks, 'sample': samples, 'total': looks + samples},
            'configurations': {'tried': (built.get('trials') or {}).get('count') or 0,
                               'reference': BASELINE in (built.get('results') or {})}}


# --- a result's channel (§17.2.5) ------------------------------------------------------------

def run_channels(records: Iterable[Mapping]) -> dict[str, str]:
    """``{execution_id: channel}`` recorded on each run's reservation (WP-J, R35); a run
    started from the chat records no channel."""
    out = {}
    for record in records:
        if record.get('action') != _RESERVE:
            continue
        params = record.get('params') or {}
        eid = params.get('execution_id') or (record.get('result') or {}).get('execution_id')
        if eid:
            out[eid] = params.get('channel') or CHANNEL_DEFAULT
    return out


def with_channels(results: Mapping, built: Mapping, channels: Mapping) -> dict:
    """The summary's ``results`` with ``channel`` as each slot's last key."""
    out = {}
    for slot, item in results.items():
        eid = ((built.get('results') or {}).get(slot) or {}).get('execution_id')
        out[slot] = {**item, 'channel': channels.get(eid, CHANNEL_DEFAULT)}
    return out


# --- data-contingent proposals (§17.2.6) -----------------------------------------------------

def proposal_contingency(records: Iterable[Mapping]) -> dict[str, tuple]:
    """``{proposal_id: (data_contingent, data_contingent_reason)}`` as each ``decide
    propose`` returned them (its receipt); a proposal recorded before a decision was assessed
    reads ``(None, None)``."""
    out = {}
    for record in records:
        if record.get('action') != 'decide.propose':
            continue
        result = record.get('result') or {}
        pid = result.get('proposal_id')
        if pid:
            out[pid] = (result.get('data_contingent'), result.get('data_contingent_reason'))
    return out


def decision_marks(study, built: Mapping) -> dict[str, bool]:
    """``{decision_id: True}`` for a rule or a model choice whose current proposal (the one
    the decision holds, confirmed or proposed) was changed after an evaluation of the earlier
    value was seen (contract P1.13): the report and the notebook show the mark next to the
    decision, as they show a data-contingent preparation."""
    found = proposal_contingency(study.revisions(0))
    out = {}
    for decision_id in ('policy', 'model_choice'):
        pid = ((built.get('decisions') or {}).get(decision_id) or {}).get('proposal_id')
        flag, reason = found.get(pid, (None, None))
        if flag is True and isinstance(reason, Mapping) \
                and reason.get('kind') == junior.CHANGED_AFTER_VALIDATION:
            out[decision_id] = True
    return out


def contingency_text(decision_id: str | None, reason: Mapping | None, lang: str) -> str | None:
    """The junior's sentence of a data-contingent proposal in ``lang`` (the receipt holds it
    in the study language only): rebuilt from the recorded reason."""
    if not isinstance(reason, Mapping):
        return None
    from . import drafts
    if reason.get('kind') == junior.CHANGED_AFTER_VALIDATION:
        return junior.changed_after_validation_text(decision_id, lang)
    if decision_id == st.PREPROCESSING:
        return drafts.contingency_text(reason.get('target_looks_before') or 0,
                                       reason.get('looks_by_activity') or {},
                                       len(reason.get('motivating_results_reading_target') or []),
                                       lang)
    if decision_id == st.MODEL_VARIANT and reason.get('families') is not None:
        return drafts.variant_contingency_text(list(reason.get('families') or []), lang)
    return reason.get('junior_text')


# --- headlines (§17.2.2, §17.2.3) -----------------------------------------------------------

def _citable(built: Mapping, slot: str) -> Mapping | None:
    item = (built.get('results') or {}).get(slot)
    if item and item.get('current') and item.get('integrity') == 'ok' \
            and isinstance(item.get('values'), Mapping):
        return item
    return None


def _num(value: Any, kind: str, lang: str) -> str | None:
    return cite.format_value(value, kind, lang) if cite.is_number(value) else None


def _model_figures(built: Mapping, lang: str, slot: str, model: str | None, metric: str,
                   kind: str, path) -> tuple[str | None, list[str]]:
    """``(words, [result_id])``: ``model``'s ``metric`` against the baseline's in the result
    of ``slot`` (``path(values, model)`` reads one model's metric)."""
    item = _citable(built, slot)
    if item is None or not model:
        return None, []
    values = item['values']
    mine, base = path(values, model), path(values, BASELINE)
    words = junior.HEADLINES[lang]
    mine, base = _num(mine, kind, lang), _num(base, kind, lang)
    if mine is None or base is None or model == BASELINE:
        return None, []
    unit = values.get('unit')
    unit = f' {unit}' if unit and kind != 'fraction' else ''
    return words['against'].format(metric=words[metric], value=f'{mine}{unit}',
                                   baseline=f'{base}{unit}'), [item['result_id']]


def _rule_metric(rule: str | None):
    def read(values, model):
        rules = values.get('rules') or {}
        raw = next((r for r in rules if rule and rec.canonical_rule(r) == rule), None)
        if raw is None:
            return None
        return (((rules[raw].get('models') or {}).get(model) or {}).get('precision'))
    return read


def _mae(values, model):
    return ((values.get('models') or {}).get(model) or {}).get('mae')


def _final_precision(values, model):
    return ((values.get('models') or {}).get(model) or {}).get('precision')


def _figures(step_id: str, built: Mapping, lang: str) -> tuple[str | None, list[str]]:
    """The figures a step's headline quotes, from current results only."""
    words = junior.HEADLINES[lang]
    decisions = built.get('decisions') or {}
    task = built.get('task')
    if step_id == 'structural_eda':
        item = _citable(built, 'eda.quality')
        if item is None:
            return None, []
        values = item['values']
        rows = _num(values.get('n_rows'), 'integer', lang)
        dup = _num((values.get('duplicates') or {}).get('n_rows'), 'integer', lang)
        if rows is None or dup is None:
            return None, []
        return words['quality'].format(rows=rows, duplicates=dup), [item['result_id']]
    if step_id == 'train_eda':
        item = _citable(built, 'eda.target_rate' if task != 'regression'
                        else 'eda.target_summary')
        if item is None:
            return None, []
        values = item['values']
        if task == 'regression':
            mean = _num(values.get('mean'), 'auto', lang)
            unit = f' {values["unit"]}' if values.get('unit') else ''
            return ((words['target_mean'].format(value=f'{mean}{unit}'), [item['result_id']])
                    if mean else (None, []))
        rate = _num(values.get('rate'), 'fraction', lang)
        return (words['target_rate'].format(value=rate), [item['result_id']]) if rate \
            else (None, [])
    if step_id == 'model_choice' and task == 'regression':
        return _model_figures(built, lang, 'evaluate.regression',
                              (decisions.get('model_choice') or {}).get('value'), 'error',
                              'auto', _mae)
    if step_id == 'policy':
        value = (decisions.get('policy') or {}).get('value')
        rule, _, model = str(value or '').partition('@')
        model = model or (decisions.get('model_choice') or {}).get('value') or 'fit.logistic'
        return _model_figures(built, lang, 'policy.evaluation', model, 'precision',
                              'fraction', _rule_metric(rec.canonical_rule(rule)))
    if step_id == 'final_test':
        item = _citable(built, 'final_test.evaluation')
        if item is None:
            return None, []
        model = item['values'].get('model')
        if task == 'regression':
            return _model_figures(built, lang, 'final_test.evaluation', model, 'error', 'auto',
                                  _mae)
        return _model_figures(built, lang, 'final_test.evaluation', model, 'precision',
                              'fraction', _final_precision)
    return None, []


def _decision_words(built: Mapping, decision_id: str) -> str | None:
    from . import automation_words
    value = ((built.get('decisions') or {}).get(decision_id) or {}).get('value')
    if value is None:
        return None
    if decision_id == 'conclusion' and isinstance(value, Mapping):
        return audience.verdict_words(value.get('verdict'), built.get('language') or 'en')
    return automation_words.value_words(built, decision_id, value)


def headlines(built: Mapping, summary_out: Mapping, lang: str | None = None
              ) -> tuple[dict, dict]:
    """``(headlines, texts)``: for each done plan step, in plan order, ``{decision_id, basis,
    results}`` and its one line in ``lang`` (the study language when not given). A line holds
    the decision's value in words and the figures of current results only (``cite`` formats
    them); a step whose figures are not current keeps its value only, and a step with
    neither has no entry."""
    lang = lang or built.get('language') or 'en'
    words = junior.HEADLINES[lang]
    decisions = summary_out.get('decisions') or {}
    out, lines = {}, {}
    for step in built.get('plan') or []:
        if step.get('status') != 'done':
            continue
        decision_id = step.get('decision')
        value = _decision_words(built, decision_id) if decision_id else None
        figures, results = _figures(step['id'], built, lang)
        if value is None and figures is None:
            continue
        name = companion_env.step_label(step['id'], lang)
        parts = [p for p in (value, figures) if p]
        lines[step['id']] = words['line'].format(step=name, text=words['join'].join(parts))
        out[step['id']] = {'decision_id': decision_id,
                           'basis': (decisions.get(decision_id) or {}).get('basis')
                           if decision_id else None,
                           'results': results}
    return out, lines


# --- the criterion per configuration (§17.2.4) -------------------------------------------------

def _regression_configurations(built: Mapping, value: Mapping) -> dict | None:
    item = _citable(built, 'evaluate.regression')
    if item is None or not isinstance(value.get('min_share'), (int, float)):
        return None
    values = item['values']
    models = list((item.get('params') or {}).get('models') or (values.get('models') or {}))
    reference = _mae(values, BASELINE)
    if not cite.is_number(reference):
        return None
    minimum = value['min_share']
    bound = (1 - minimum) * reference
    candidate = (item.get('params') or {}).get('candidate')
    order = _ordered(models, candidate)
    configurations = []
    for slot in order:
        mae = _mae(values, slot)
        if not cite.is_number(mae):
            continue
        delta = ((values.get('deltas') or {}).get(slot) or {}).get('mae')
        gain = low = high = None
        if slot != BASELINE and isinstance(delta, Mapping) and cite.is_number(delta.get('point')):
            gain = -delta['point'] / reference
            if cite.is_number(delta.get('low')) and cite.is_number(delta.get('high')):
                low, high = -delta['high'] / reference, -delta['low'] / reference
        configurations.append(_configuration(
            slot, mae, item['result_id'], cite.format_path(['models', slot, 'mae']),
            mae <= bound + TOLERANCE, gain, low, high, minimum))
    return {'metric': 'mae_reduction', 'unit': values.get('unit'),
            'bound': {'value': bound, 'reference': reference, 'minimum': minimum,
                      'result_id': item['result_id'],
                      'path': cite.format_path(['models', BASELINE, 'mae'])},
            'configurations': configurations}


def _ordered(models: list[str], candidate: str | None) -> list[str]:
    """The candidate first, then each variant and family in slot order, then the baseline."""
    rest = sorted((m for m in models if m not in (candidate, BASELINE)),
                  key=lambda s: (s.partition(':')[0], int(s.partition(':')[2] or 1)))
    head = [candidate] if candidate in models else []
    return head + rest + ([BASELINE] if BASELINE in models else [])


def _binary_configurations(built: Mapping, value: Mapping, crit: Mapping) -> dict | None:
    item = _citable(built, 'policy.evaluation')
    if item is None or not isinstance(value.get('min_points'), (int, float)):
        return None
    rule = crit.get('rule')
    if not rule:
        return None
    values = item['values']
    rules = values.get('rules') or {}
    raw = next((r for r in rules if rec.canonical_rule(r) == rule), None)
    if raw is None:
        return None
    metric = criterion_mod.DELTA_METRIC.get(value.get('metric'), 'precision')
    at_rule = rules[raw]
    reference = ((at_rule.get('models') or {}).get(BASELINE) or {}).get(metric)
    if not cite.is_number(reference):
        return None
    minimum = value['min_points']
    bound = reference + minimum / 100
    params = item.get('params') or {}
    models = list(params.get('models') or (at_rule.get('models') or {}))
    candidate = next((m for m in models if m in ('fit.logistic', 'fit.linear')), None)
    configurations = []
    for slot in _ordered(models, candidate):
        point = ((at_rule.get('models') or {}).get(slot) or {}).get(metric)
        if not cite.is_number(point):
            continue
        delta = ((at_rule.get('deltas') or {}).get(slot) or {}).get(metric)
        gain = low = high = None
        if slot != BASELINE and isinstance(delta, Mapping) and cite.is_number(delta.get('point')):
            gain = 100 * delta['point']
            if cite.is_number(delta.get('low')) and cite.is_number(delta.get('high')):
                low, high = 100 * delta['low'], 100 * delta['high']
        configurations.append(_configuration(
            slot, point, item['result_id'],
            cite.format_path(['rules', raw, 'models', slot, metric]),
            point >= bound - TOLERANCE, gain, low, high, minimum))
    return {'metric': value.get('metric'), 'unit': 'share',
            'bound': {'value': bound, 'reference': reference, 'minimum': minimum,
                      'result_id': item['result_id'],
                      'path': cite.format_path(['rules', raw, 'models', BASELINE, metric])},
            'configurations': configurations}


def _configuration(slot, value, result_id, path, meets, gain, low, high, minimum) -> dict:
    status = (criterion_mod._status(gain, low, high, minimum)[0] if gain is not None
              else 'not_assessed')
    return {'slot': slot, 'value': value, 'result_id': result_id, 'path': path,
            'point_meets_bound': bool(meets), 'gain': gain, 'low': low, 'high': high,
            'status': status, 'judged_on': 'development'}


def criterion_configurations(built: Mapping) -> dict | None:
    """``criterion_configurations``: null when the success criterion is not confirmed or no
    current evaluation compares configurations; else the absolute bound a configuration must
    reach (from registered values) and each configuration's status against it. The
    configuration the opened final test measured is judged on the final test."""
    crit = built.get('criterion') or {}
    value = crit.get('value')
    if crit.get('decision_status') not in ('confirmed', 'reconfirm_required') \
            or not isinstance(value, Mapping):
        return None
    if built.get('task') == 'regression':
        out = _regression_configurations(built, value)
    else:
        out = _binary_configurations(built, value, crit)
    if out is None:
        return None
    final = crit.get('final_test')
    if crit.get('judged_on') == 'final_test' and isinstance(final, Mapping):
        for item in out['configurations']:
            if item['slot'] == crit.get('model'):
                item.update(judged_on='final_test', status=final.get('status') or item['status'])
    return {k: out[k] for k in SUMMARY_CRITERION_CONFIG_KEYS}


# --- the texts of §17.2.3 ------------------------------------------------------------------

def question(action: Mapping) -> str | None:
    """The one question the chat asks now, or null for a run, a blocked step, an unknown
    outcome or the end."""
    if action.get('kind') in ('run', 'blocked', 'done', 'outcome_unknown'):
        return None
    pause = action.get('pause') or {}
    return action.get('question') or pause.get('question')


def options(action: Mapping) -> dict:
    """``{option_id: label}`` in the order the chat offers them, or ``{}`` without a
    question."""
    if question(action) is None:
        return {}
    pause = action.get('pause') or {}
    labels = pause.get('option_labels') or {}
    return {o: labels.get(o) for o in pause.get('options') or []}


def texts(built: Mapping, lang: str, *, contingency: Mapping, has_sample: bool,
          headline_lines: Mapping) -> dict:
    """The keys §17.2.3 adds to ``texts.<lang>``, from the view read in that language."""
    action = built.get('next_action') or {}
    open_ids = {p['proposal_id']: p['decision_id'] for p in built.get('open_proposals') or []}
    return {
        'question': question(action),
        'options': options(action),
        'options_note': junior.options_note(built, action, lang),
        'junior_digest': action.get('junior_digest'),
        'headlines': dict(headline_lines),
        'data_contingent': {pid: contingency_text(open_ids[pid], reason, lang)
                            for pid, (flag, reason) in contingency.items()
                            if pid in open_ids and flag is True},
        'sample_note': exposure.sample_note(lang) if has_sample else None,
    }


def additions(study, built: Mapping, summary_out: Mapping) -> dict:
    """The digest keys of §17.2, in :data:`view.DIGEST_SUMMARY_KEYS` order after ``texts``."""
    state = study.state
    records = study.revisions(0)
    entries = study.exposure_records()
    found, _ = headlines(built, summary_out)
    return {'panel_contract': companion_env.PANEL_CONTRACT,
            'automation': automation(state),
            'review_queue': review_queue(state, built, records),
            'defensibility': defensibility(built, summary_out),
            'ledger': ledger(built, entries),
            'sample': sample(study, state, entries),
            'headlines': found,
            'criterion_configurations': criterion_configurations(built)}


__all__ = ['additions', 'automation', 'review_queue', 'defensibility', 'ledger', 'sample',
           'headlines', 'criterion_configurations', 'run_channels', 'with_channels',
           'proposal_contingency', 'contingency_text', 'texts']
