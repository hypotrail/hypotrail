"""The HTML study report ``reports/study.html`` (plan §6, WP3.1; ADR 0001 decision 2).

A deterministic, offline, stdlib-only renderer fed by :func:`mlkit.study.view.build`.

* Every number is a cited registry value: :meth:`mlkit.study.cite.Citer.num` produces a
  ``<data value data-result-id data-path title>`` element, and refuses
  (``untraceable_number``) a result that is unknown or not current. Free texts are
  templates (``{{r:<rid>.<path>}}``, ``{{slot:<slot>:<path>}}``).
* Text that is shown as recorded rather than computed (revisions, step ordinals, the
  user's words, decision values, case statements, identifiers, engine messages) is
  wrapped in an element with ``data-literal="<kind>"``; ``hypotrail check`` treats any
  other number in a text node as untraceable.
* The page holds **no decision control**: the only button is the theme toggle, and
  there is no input, form, select, or slider (plan §6, ADR 0002 rule 4).
* Offline: styles and the theme script are inline; no URL is loaded.
* ``<!--hypotrail:banner--><!--/hypotrail:banner-->`` marks where a stale banner is
  injected into the previous file when a later render fails (:func:`inject_banner`).

Teaching texts and labels come from ``mlkit/study/content/*.yaml``
(:mod:`mlkit.study.texts`). Writing the file is done by :mod:`mlkit.study.cmd_render`.
No pandas, numpy, or scikit-learn.
"""
from __future__ import annotations

import html
import json
import re
from importlib import resources
from typing import Any, Mapping

from . import cite, texts
from . import state as st

BANNER_START = '<!--hypotrail:banner-->'
BANNER_END = '<!--/hypotrail:banner-->'
TEMPLATE_VERSION = 1
LITERAL_KINDS = ('revision', 'ordinal', 'user_words', 'proposal', 'decision_value', 'case',
                 'identifier', 'parameter', 'environment', 'setting', 'message', 'category')

e = html.escape


def lit(kind: str, text: Any, tag: str = 'span') -> str:
    assert kind in LITERAL_KINDS, kind
    return f'<{tag} data-literal="{kind}">{e(str(text))}</{tag}>'


def _css() -> str:
    base = (resources.files('mlkit') / 'assets' / 'design.css').read_text(encoding='utf-8')
    return base + REPORT_CSS


REPORT_CSS = '''
.report main{max-width:1040px!important}
.report h2{scroll-margin-top:16px}
data{font-variant-numeric:tabular-nums;font-weight:650;border-bottom:1px dotted var(--muted);color:var(--ink)}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.02em;border:1px solid var(--line);border-radius:6px;padding:2px 8px;margin-right:8px;background:var(--soft);color:var(--ink)}
.badge.confirmed{border-color:var(--accent)}
.badge.proposed,.badge.reconfirm_required,.badge.stale,.badge.failed,.badge.delegated{border-style:dashed;border-color:var(--amber)}
.words.delegated{border-left-color:var(--amber);border-left-style:dashed}
.status-label{font-weight:650;color:var(--ink)}
.plan li{margin:10px 0}
.plan li.current{border-left:3px solid var(--accent);padding-left:10px}
.term{color:var(--ink)}
q[data-literal]{font-style:italic;color:var(--ink)}
.words{border-left:3px solid var(--accent);padding:8px 14px;margin:8px 0;background:var(--soft);border-radius:6px;color:var(--ink)}
.stale-banner{margin:0;border-radius:0}
.surfaces td:first-child,.metrics td:first-child{font-weight:650}
.muted{color:var(--muted)}
dl.figures{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px 18px;max-width:640px}
dl.figures dt{color:var(--muted)}dl.figures dd{margin:0;text-align:right}
.page-footer{max-width:1040px;margin:0 auto 40px;padding:20px 28px 0}
'''

THEME_SCRIPT = '''(function(){var b=document.body,k="hypotrail-theme",t=document.querySelector("[data-theme-toggle]");
function set(d){b.classList.toggle("dark",d);if(t){t.setAttribute("aria-pressed",d?"true":"false");}}
var s=null;try{s=window.localStorage.getItem(k);}catch(x){}
set(s?s==="dark":!!(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches));
if(t){t.addEventListener("click",function(){var d=!b.classList.contains("dark");set(d);try{window.localStorage.setItem(k,d?"dark":"light");}catch(x){}});}})();'''


# --- helpers ----------------------------------------------------------------------------

def _labels() -> dict:
    return texts.report()


def _badge(kind: str, label: str) -> str:
    return f'<span class="badge {e(kind)}">{e(label)}</span>'


def _value_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _concept(term_id: str | None) -> str:
    entry = texts.glossary(term_id) if term_id else None
    if not entry:
        return ''
    return f'<p><strong class="term">{e(entry["term"])}.</strong> {e(entry["definition"])}</p>'


def slots_of_step(step_id: str, results: Mapping) -> list[str]:
    """Result slots shown with a step: its activities, plus extra slots of the same family."""
    step = next(s for s in st.STEPS if s['id'] == step_id)
    slots = list(step['activities'])
    family = {'train_eda': 'eda.', 'models': 'fit.', 'policy': 'policy.'}.get(step_id)
    if family:
        slots += sorted(s for s in results if s.startswith(family) and s not in slots)
    return slots


# --- sections ---------------------------------------------------------------------------

def _surfaces(view: Mapping, surfaces: Mapping) -> str:
    labels = _labels()
    rows = []
    for name in ('report', 'notebook', 'workbench'):
        info = surfaces.get(name) or {'status': 'not_rendered'}
        status = info.get('status', 'not_rendered')
        key = 'not_tracked' if info.get('tracked') is False and status == 'ok' else status
        text = labels['surface_status'].get(key, key)
        extra = ''
        if info.get('revision') is not None and status != 'ok':
            extra = f' (last written for revision {lit("revision", info["revision"])})'
        if info.get('error'):
            extra += f' {lit("message", info["error"].get("message", ""))}'
        rows.append(f'<tr data-surface="{name}" data-status="{e(status)}"><td>'
                    f'{e(labels["surfaces"][name])}</td><td>{_badge(status, text)}{extra}</td></tr>')
    return (f'<section class="card" id="revision"><h2>{e(labels["sections"]["revision"])}</h2>'
            f'<p class="lead">Generated for study revision {lit("revision", view["revision"])}. '
            f'{e(labels["authority"])}</p>'
            f'<table class="surfaces"><tbody>{"".join(rows)}</tbody></table>'
            f'<p class="small">{e(labels["no_controls"])}</p></section>')


def _plan(view: Mapping) -> str:
    labels = _labels()
    items = []
    for step in view['plan']:
        cls = ' class="current"' if step['current'] else ''
        marker = f' <span class="pill">{e(labels["current_marker"])}</span>' if step['current'] else ''
        status = labels['step_status'].get(step['status'], step['status'])
        items.append(f'<li{cls} data-step="{e(step["id"])}" data-status="{e(step["status"])}">'
                     f'<strong>{e(step["title"])}</strong> {_badge(step["status"], status)}{marker}'
                     f'<br><span class="muted">{e(step["question"])}</span></li>')
    na = view['next_action']
    return (f'<section class="card" id="plan"><h2>{e(labels["sections"]["plan"])}</h2>'
            f'<ol class="plan">{"".join(items)}</ol>'
            f'<p><strong>{e(labels["next_action"])}:</strong> '
            f'{lit("message", na.get("message", ""))}</p></section>')


def _confirmation(conf: Mapping) -> str:
    labels = _labels()
    if conf.get('basis') == 'delegated_default':
        return (f'<div class="words delegated" data-basis="delegated_default">'
                f'{_badge("delegated", labels["delegated"])}'
                f'<strong>{e(labels["delegated_words"])}:</strong> '
                f'<q data-literal="user_words">{e(conf["user_words"])}</q>'
                f'<br><span class="small">{e(labels["delegated_note"])}</span>'
                f'<br><span class="small">Channel {lit("identifier", conf.get("channel"))}, actor '
                f'{lit("identifier", conf.get("actor"))}, at revision '
                f'{lit("revision", conf.get("revision"))}. {e(labels["not_authenticated"])}</span>'
                f'<br><span class="small">{e(labels["delegated_restatement"])}: '
                f'{lit("proposal", conf.get("restatement", ""))}</span></div>')
    return (f'<div class="words" data-basis="explicit"><strong>{e(labels["user_words"])}:</strong> '
            f'<q data-literal="user_words">{e(conf["user_words"])}</q>'
            f'<br><span class="small">Channel {lit("identifier", conf.get("channel"))}, actor '
            f'{lit("identifier", conf.get("actor"))}, at revision '
            f'{lit("revision", conf.get("revision"))}. {e(labels["not_authenticated"])}</span>'
            f'<br><span class="small">{e(labels["restatement"])}: '
            f'{lit("proposal", conf.get("restatement", ""))}</span></div>')


def _availability_table(view: Mapping, variables: list[dict]) -> str:
    labels = _labels()
    decision = view['decisions']['feature_availability']
    value = decision['value'] if isinstance(decision['value'], dict) else {}
    features = [v for v in variables if v.get('role') == 'feature']
    if not features:
        return ''
    confirmed = decision['status'] == 'confirmed'
    rows = []
    for v in features:
        status = value.get(v['name'])
        shown = labels['availability'].get(status or 'missing', status)
        kind = 'confirmed' if confirmed and status else ('proposed' if status else 'stale')
        stmt = v.get('availability') or {}
        case_label = labels['fact_status'].get(stmt.get('status'), stmt.get('status') or '')
        rows.append(f'<tr data-feature="{e(v["name"])}"><td>{lit("identifier", v["name"], "code")}</td>'
                    f'<td>{_badge(kind, shown)}</td><td>{_badge(stmt.get("status") or "unknown", case_label)} '
                    f'{lit("case", stmt.get("value", ""))}</td></tr>')
    head = 'Your decision' if confirmed else 'Proposed, not confirmed'
    return ('<div class="scroll"><table class="availability"><thead><tr><th>Variable</th>'
            f'<th>{e(head)}</th><th>What the case states</th></tr></thead><tbody>'
            f'{"".join(rows)}</tbody></table></div>')


def _decisions(view: Mapping, variables: list[dict]) -> str:
    labels = _labels()
    titles = {s['decision']: s['title'] for s in st.STEPS if s['decision']}
    cards = []
    for did, d in view['decisions'].items():
        status = d['status']
        parts = [f'<h3>{e(titles.get(did, did))} {_badge(status, labels["decision_status"][status])}</h3>']
        if d['value'] is not None and did != 'feature_availability':
            if did == 'conclusion' and isinstance(d['value'], dict):
                verdict = labels['verdict'].get(d['value'].get('verdict'), d['value'].get('verdict'))
                parts.append(f'<p><strong>{e(verdict)}.</strong> '
                             f'{lit("decision_value", d["value"].get("text", ""), "q")}</p>')
            else:
                parts.append(f'<p>Value: {lit("decision_value", _value_text(d["value"]), "code")}</p>')
        if did == 'feature_availability':
            parts.append(_availability_table(view, variables))
        if d['confirmation'] and status in ('confirmed', 'reconfirm_required'):
            parts.append(_confirmation(d['confirmation']))
        if d['reason']:
            parts.append(f'<p class="notice">{lit("message", d["reason"])}</p>')
        for p in view['open_proposals']:
            if p['decision_id'] == did:
                parts.append(f'<div class="feedback">{_badge("proposed", labels["proposal_waiting"])}'
                             f'Proposal {lit("identifier", p["proposal_id"], "code")}: '
                             f'{lit("proposal", p["restatement"])}<br><span class="small">'
                             f'{lit("proposal", p["rationale"])}</span></div>')
        cards.append(f'<article data-decision="{e(did)}" data-status="{e(status)}">'
                     f'{"".join(parts)}</article>')
    return (f'<section id="decisions"><h2>{e(labels["sections"]["decisions"])}</h2>'
            f'{_concept("confirmed_decision")}{_concept("proposal")}{"".join(cards)}</section>')


def _facts(view: Mapping) -> str:
    labels = _labels()
    groups = []
    for status, items in view['facts']['by_status'].items():
        if not items:
            continue
        label = labels['fact_status'][status]
        lis = ''.join(f'<li data-fact="{e(f["id"])}" data-status="{e(status)}">{_badge(status, label)}'
                      f'{lit("case", _value_text(f["value"]), "q")} <span class="small">Source: '
                      f'{lit("case", f["source"])}</span></li>' for f in items)
        groups.append(f'<h3>{e(label)}</h3>{_concept(status) if texts.glossary(status) else ""}'
                      f'<ul>{lis}</ul>')
    structure = []
    for key, stmt in view['structure'].items():
        if isinstance(stmt, Mapping):
            status = stmt.get('status', 'unknown')
            label = labels['fact_status'].get(status, status)
            shown = 'not available' if stmt.get('value') is None else _value_text(stmt.get('value'))
            structure.append(f'<li data-structure="{e(key)}">{_badge(status, label)}'
                             f'{lit("identifier", key, "code")}: {lit("case", shown)} '
                             f'<span class="small">Source: {lit("case", stmt.get("source", ""))}</span></li>')
    return (f'<section class="card" id="facts"><h2>{e(labels["sections"]["facts"])}</h2>'
            f'<p>Statements of the case are never decisions: each one keeps its status and source.</p>'
            f'{"".join(groups)}<h3>Structure</h3><ul>{"".join(structure)}</ul></section>')


def _figures(citer: cite.Citer, rid: str, spec: Mapping) -> str:
    rows = []
    for h in spec.get('highlights', []):
        if citer.has(rid, h['path']):
            rows.append(f'<dt>{e(h["label"])}</dt><dd>{citer.num(rid, h["path"], h.get("fmt", "auto"))}</dd>')
    out = f'<dl class="figures">{"".join(rows)}</dl>' if rows else ''
    entry = citer.results[rid]
    for table in spec.get('tables', []):
        items = entry.values.get(table['rows']) if isinstance(entry.values, Mapping) else None
        if isinstance(items, list) and items:
            out += _table(citer, rid, table, items)
    return out


def _table(citer: cite.Citer, rid: str, table: Mapping, items: list) -> str:
    """A list of rows of a result; a column ``key`` may be a dotted path inside the row."""
    head = ''.join(f'<th>{e(c["label"])}</th>' for c in table['columns'])
    body = []
    for i, row in enumerate(items):
        cells = []
        for c in table['columns']:
            keys = c['key'].split('.')
            path = cite.format_path([table['rows'], str(i)] + keys)
            if c.get('kind') == 'text':
                try:
                    raw = cite.resolve(row, keys)
                except KeyError:
                    raw = None
                cells.append(f'<td>{lit("category", "" if raw is None else _value_text(raw))}</td>')
            elif citer.has(rid, path):
                cells.append(f'<td>{citer.num(rid, path, c.get("fmt", "auto"))}</td>')
            else:
                cells.append('<td></td>')
        body.append(f'<tr>{"".join(cells)}</tr>')
    return (f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')


def _result_block(view: Mapping, citer: cite.Citer, slot: str) -> str:
    labels = _labels()
    spec = texts.activity(slot)
    title = spec.get('label', slot)
    item = view['results'].get(slot)
    if item is None:
        return (f'<div data-slot="{e(slot)}" data-state="pending"><h4>{e(title)}</h4>'
                f'<p class="muted">{e(texts.load("steps")["pending"])}</p></div>')
    if not citer.citable(item['result_id']):
        reason = (item['stale_reason'] or {}).get('reason') if item['stale_reason'] else item['integrity']
        return (f'<div data-slot="{e(slot)}" data-state="stale"><h4>{e(title)} '
                f'{_badge("stale", texts.load("steps")["stale"])}</h4>'
                f'<p class="small">{lit("message", reason or "")}</p></div>')
    partition = item['partition'] or 'not recorded'
    return (f'<div data-slot="{e(slot)}" data-state="current"><h4>{e(title)}</h4>'
            f'{_concept(spec.get("glossary")) if spec.get("glossary") else ""}'
            f'<p class="small">Partition: {lit("identifier", partition)}. Result '
            f'{lit("identifier", item["result_id"][:12], "code")}.</p>'
            f'{_figures(citer, item["result_id"], spec)}</div>')


def _evidence(view: Mapping, citer: cite.Citer) -> str:
    labels = _labels()
    articles = []
    for index, step in enumerate(view['plan'], start=1):
        content = texts.step(step['id'])
        status = labels['step_status'].get(step['status'], step['status'])
        parts = [f'<h3>{lit("ordinal", index)}. {e(step["title"])} {_badge(step["status"], status)}</h3>',
                 f'<p><strong>Question.</strong> {e(step["question"])}</p>',
                 _concept(content.get('concept')),
                 f'<p>{citer.expand(content["context"])}</p>'
                 if content.get('context') and citer.ready(content['context']) else '',
                 f'<p><strong>Method.</strong> {e(content.get("method", ""))}</p>']
        slots = slots_of_step(step['id'], view['results'])
        parts += [_result_block(view, citer, slot) for slot in slots]
        if step['decision']:
            d = view['decisions'][step['decision']]
            parts.append(f'<p><strong>Decision.</strong> '
                         f'{_badge(d["status"], labels["decision_status"][d["status"]])}</p>')
        interp = content.get('interpretation')
        if interp and citer.ready(interp) and (not slots or any(
                citer.slot_rid(s) for s in slots)):
            parts.append(f'<p><strong>Interpretation.</strong> {citer.expand(interp)}</p>')
        elif interp:
            parts.append(f'<p class="muted"><strong>Interpretation.</strong> '
                         f'{e(texts.load("steps")["pending"])}</p>')
        if content.get('consequence'):
            parts.append(f'<p><strong>Consequence.</strong> {e(content["consequence"])}</p>')
        articles.append(f'<article id="step-{e(step["id"])}" data-step="{e(step["id"])}">'
                        f'{"".join(parts)}</article>')
    return (f'<section id="evidence"><h2>{e(labels["sections"]["evidence"])}</h2>'
            f'{"".join(articles)}</section>')


def _tied(citer: cite.Citer, rid: str, prefix: list[str], model: Mapping) -> str:
    """The tie group at the cut of one model under one rule (``tied_at_cut``, ``cut``)."""
    labels = _labels()
    tied = model.get('tied_at_cut')
    if not cite.is_number(tied) or tied == 0:
        return e(labels['tied_none'])
    bits = [f'{citer.num(rid, cite.format_path(prefix + ["tied_at_cut"]), "int")} tied rows']
    fraction = cite.format_path(prefix + ['cut', 'fraction_selected'])
    if citer.has(rid, fraction):
        bits.append(f'{citer.num(rid, fraction, "pct1")} of them selected')
    return f'{e(labels["tied_yes"])}: ' + ', '.join(bits)


def _interval(citer: cite.Citer, rid: str, path: list[str], fmt: str) -> str:
    lo, hi = cite.format_path(path + ['low']), cite.format_path(path + ['high'])
    if citer.has(rid, lo) and citer.has(rid, hi):
        return f'[{citer.num(rid, lo, fmt)}, {citer.num(rid, hi, fmt)}]'
    return ''


def _policy(view: Mapping, citer: cite.Citer) -> str:
    """Policy comparison from the canonical ``policy.evaluation`` values
    (``rules.<rule>.{models, intervals, deltas}``, CLI-CONTRACT.md section 8.5)."""
    labels = _labels()
    head = (f'<section class="card" id="policy"><h2>{e(labels["sections"]["policy"])}</h2>'
            f'{_concept("policy")}{_concept("tie_at_cut")}{_concept("paired_bootstrap")}')
    rid = citer.slot_rid('policy.evaluation')
    if rid is None:
        return head + f'<p class="muted">{e(labels["policy_missing"])}</p></section>'
    values = citer.results[rid].values
    adopted = view['decisions']['policy']
    proposed = {p['value'] for p in view['open_proposals'] if p['decision_id'] == 'policy'}
    metrics = texts.policy_metrics()
    rules = values.get('rules') if isinstance(values, Mapping) else None
    rules = {str(k): v for k, v in (rules or {}).items() if isinstance(v, Mapping)}
    level = ''
    if citer.has(rid, 'bootstrap.level'):
        level = f' Intervals: {citer.num(rid, "bootstrap.level", "pct0")} percentile intervals.'
    rows, paired = [], []
    for key, item in rules.items():
        prefix = ['rules', key]
        tag = ''
        if adopted['status'] == 'confirmed' and adopted['value'] == key:
            tag = _badge('confirmed', labels['adopted'])
        elif key in proposed:
            tag = _badge('proposed', labels['proposed_rule'])
        models = item.get('models') if isinstance(item.get('models'), Mapping) else {}
        for model, mv in models.items():
            if not isinstance(mv, Mapping):
                continue
            mprefix = prefix + ['models', str(model)]
            cells = []
            for m in metrics:
                path = cite.format_path(mprefix + [m['key']])
                fmt = m.get('fmt', 'auto')
                shown = citer.num(rid, path, fmt) if citer.has(rid, path) else ''
                interval = _interval(citer, rid, prefix + ['intervals', str(model), m['key']], fmt)
                extra = f' <span class="small">{interval}</span>' if interval else ''
                cells.append(f'<td>{shown}{extra}</td>')
            rows.append(f'<tr data-rule="{e(key)}" data-model="{e(model)}">'
                        f'<td>{lit("decision_value", key, "code")} {tag}</td>'
                        f'<td>{lit("identifier", model)}</td>{"".join(cells)}'
                        f'<td>{_tied(citer, rid, mprefix, mv)}</td></tr>')
        deltas = item.get('deltas') if isinstance(item.get('deltas'), Mapping) else {}
        for model, by_metric in sorted(deltas.items()):
            if not isinstance(by_metric, Mapping):
                continue
            for m in metrics:
                base = prefix + ['deltas', str(model), m['key']]
                point = cite.format_path(base + ['point'])
                if not citer.has(rid, point):
                    continue
                fmt = m.get('fmt', 'auto')
                paired.append(f'<tr data-rule="{e(key)}" data-model="{e(model)}" '
                              f'data-metric="{e(m["key"])}">'
                              f'<td>{lit("decision_value", key, "code")}</td>'
                              f'<td>{lit("identifier", model)}</td><td>{e(m["label"])}</td>'
                              f'<td>{citer.num(rid, point, fmt)}</td>'
                              f'<td>{_interval(citer, rid, base, fmt)}</td></tr>')
    table = ''
    if rows:
        th = ''.join(f'<th>{e(m["label"])}</th>' for m in metrics)
        table = (f'<div class="scroll"><table class="metrics"><thead><tr><th>Rule</th><th>Model</th>'
                 f'{th}<th>Tie at the cut</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')
    pair_table = ''
    if paired:
        pair_table = (f'<h3>{e(labels["paired_heading"])}</h3><div class="scroll"><table class="paired">'
                      '<thead><tr><th>Rule</th><th>Model</th><th>Metric</th><th>Difference</th>'
                      f'<th>Interval</th></tr></thead><tbody>{"".join(paired)}</tbody></table></div>')
    return (head + f'<p class="notice">{e(labels["policy_note"])}{level}</p>{table}{pair_table}'
            f'{_figures(citer, rid, texts.activity("policy.evaluation"))}</section>')


def _not_yet_defensible(view: Mapping) -> str:
    labels = _labels()
    extra = labels['not_yet_defensible_extra']
    items = []
    for item in view['not_yet_defensible']:
        details = []
        for key in ('decisions', 'features', 'results', 'executions', 'slots', 'missing'):
            if item.get(key):
                details.append(', '.join(lit('identifier', x, 'code') for x in item[key]))
        for source in item.get('sources') or []:
            details.append(lit('case', source))
        more = f' {e(extra[item["id"]])}' if item['id'] in extra else ''
        items.append(f'<li data-nyd="{e(item["id"])}"><strong>{lit("message", item["text"])}</strong>'
                     f'{more}{"<br>" + "; ".join(details) if details else ""}</li>')
    return (f'<section class="card" id="not-yet-defensible">'
            f'<h2>{e(labels["sections"]["not_yet_defensible"])}</h2>'
            f'{_concept("selection_on_validation")}<ul>{"".join(items)}</ul></section>')


def _annex(view: Mapping, citer: cite.Citer) -> str:
    labels = _labels()
    blocks = []
    for slot in sorted(view['results']):
        item = view['results'][slot]
        rid = item['result_id']
        head = (f'<summary>{lit("identifier", slot, "code")} · {lit("identifier", item["activity"] or "")}'
                f' · result {lit("identifier", rid[:12], "code")}</summary>')
        if not citer.citable(rid):
            state = 'stale' if item['integrity'] == 'ok' else item['integrity']
            blocks.append(f'<details data-slot="{e(slot)}" data-state="stale">{head}<p>'
                          f'{_badge("stale", labels["not_cited"])}{lit("message", state)}</p></details>')
            continue
        rows = []
        if item['n_rows'] is not None and cite.is_number(item['n_rows']):
            rows.append(f'<tr><td>{lit("identifier", "n_rows", "code")}</td>'
                        f'<td>{citer.num(rid, "@n_rows", "int")}</td></tr>')
        for segments, _ in cite.leaves(item['values']):
            path = cite.format_path(segments)
            rows.append(f'<tr><td>{lit("identifier", path, "code")}</td>'
                        f'<td>{citer.num(rid, path, "auto")}</td></tr>')
        env = item['environment'] or {}
        meta = (f'<p class="small">Full id {lit("identifier", rid, "code")}; partition '
                f'{lit("identifier", item["partition"] or "not recorded")}; parameters '
                f'{lit("parameter", _value_text(item["params"]), "code")}; code fingerprint '
                f'{lit("identifier", (item["code_fingerprint"] or "")[:12], "code")}; environment '
                f'{lit("environment", "Python " + str(env.get("python", "unknown")))}.</p>')
        blocks.append(f'<details data-slot="{e(slot)}" data-state="current">{head}{meta}'
                      f'<div class="scroll"><table><thead><tr><th>Value path</th><th>Value</th></tr>'
                      f'</thead><tbody>{"".join(rows)}</tbody></table></div></details>')
    exposure = view['exposure']
    purposes = sorted(p for p, n in (exposure.get('by_purpose') or {}).items() if n)
    used = bool(exposure.get('validation_rows_used_for_selection'))
    exp = (f'<h3>{e(texts.glossary("exposure")["term"])}</h3>{_concept("exposure")}'
           f'<p>Purposes recorded: {", ".join(lit("identifier", p, "code") for p in purposes) or "none"}. '
           f'Validation rows used for selection: {"yes" if used else "no"}.</p>')
    return (f'<section id="annex"><h2>{e(labels["sections"]["annex"])}</h2>'
            f'<p class="small">{e(labels["annex_note"])}</p>{"".join(blocks)}{exp}</section>')


# --- page -------------------------------------------------------------------------------

def build(view: Mapping, *, surfaces: Mapping | None = None,
          variables: list[dict] | None = None) -> tuple[str, list[str]]:
    """``(html, consumed result ids)`` of the report for ``view``.

    ``surfaces`` gives the status of each deliverable for the revision banner; the
    report itself is described as written at this revision. ``variables`` is the case
    variable dictionary (for the availability table). Raises ``untraceable_number``
    when a cited number cannot be traced.
    """
    labels = _labels()
    citer = cite.Citer.from_view(view)
    surfaces = dict(surfaces or {})
    surfaces.setdefault('report', {'status': 'ok', 'revision': view['revision']})
    body = ''.join([
        _surfaces(view, surfaces), _plan(view), _decisions(view, variables or []), _facts(view),
        _evidence(view, citer), _policy(view, citer), _not_yet_defensible(view),
        _annex(view, citer)])
    consumed = sorted({c['result_id'] for c in citer.cited})
    case = view['case']
    page = (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="hypotrail-revision" content="{view["revision"]}">'
        f'<meta name="hypotrail-template-version" content="{TEMPLATE_VERSION}">'
        f'<title>{e(labels["title"])}</title><style>{_css()}</style></head>\n'
        f'<body class="report" data-revision="{view["revision"]}">{BANNER_START}{BANNER_END}\n'
        f'<header><span class="brand">Hypotrail</span>'
        f'<span>{e(labels["title"])} · {lit("case", case.get("id", ""))}</span>'
        f'<button type="button" data-theme-toggle aria-pressed="false">{e(labels["theme_toggle"])}</button>'
        f'</header>\n<main><p class="lead">{e(labels["subtitle"])}</p>{body}</main>\n'
        f'<footer class="page-footer">Generated by Hypotrail for study revision '
        f'{lit("revision", view["revision"])}. {e(labels["no_controls"])}</footer>\n'
        f'<script>{THEME_SCRIPT}</script></body></html>\n')
    return page, consumed


def banner_html(*, report_revision: int | None, failed_revision: int, error: Mapping) -> str:
    """The stale banner injected into a previous report when rendering fails."""
    shown = (f'revision {lit("revision", report_revision)}' if report_revision is not None
             else 'an earlier revision')
    return (f'<div class="notice stale-banner" role="alert" data-hypotrail-banner="stale">'
            f'<strong>Stale report.</strong> This page describes {shown}. Rendering revision '
            f'{lit("revision", failed_revision)} failed ({lit("identifier", error.get("code", "error"), "code")}: '
            f'{lit("message", error.get("message", ""))}). Do not rely on it; read the study state with '
            f'hypotrail status.</div>')


_BANNER_RE = re.compile(re.escape(BANNER_START) + '.*?' + re.escape(BANNER_END), re.DOTALL)


def inject_banner(page: str, banner: str) -> str:
    """``page`` with its banner region replaced by ``banner`` (added after ``<body>``
    when the page has no banner region)."""
    region = BANNER_START + banner + BANNER_END
    if _BANNER_RE.search(page):
        return _BANNER_RE.sub(lambda _: region, page, count=1)
    m = re.search(r'<body[^>]*>', page)
    if m:
        return page[:m.end()] + region + page[m.end():]
    return region + page


def failure_page(*, failed_revision: int, error: Mapping) -> str:
    """A minimal page when the first render fails: no number, only the failure."""
    labels = _labels()
    return ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(labels["title"])}</title><style>{_css()}</style></head>\n'
            f'<body class="report">{BANNER_START}'
            f'{banner_html(report_revision=None, failed_revision=failed_revision, error=error)}'
            f'{BANNER_END}\n<main><p class="lead">{e(labels["authority"])}</p></main></body></html>\n')
