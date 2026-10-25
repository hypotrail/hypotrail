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

from . import audience, cite, render_charts, render_diagnostics, render_trials, texts
from . import state as st

BANNER_START = '<!--hypotrail:banner-->'
BANNER_END = '<!--/hypotrail:banner-->'
TEMPLATE_VERSION = 2
# ``structure``: a count recorded in the study state rather than computed by an activity
# (the sealed final test, the dataset rows); ``data_row``: a cell of the five development
# rows shown as recorded in the file; ``axis``: a chart tick, exempt only inside an SVG
# (WP-A6, :mod:`mlkit.study.render_charts`).
LITERAL_KINDS = ('revision', 'ordinal', 'user_words', 'proposal', 'decision_value', 'case',
                 'identifier', 'parameter', 'environment', 'setting', 'message', 'category',
                 'structure', 'data_row', 'axis')

e = html.escape


def lit(kind: str, text: Any, tag: str = 'span') -> str:
    assert kind in LITERAL_KINDS, kind
    return f'<{tag} data-literal="{kind}">{e(str(text))}</{tag}>'


def _css() -> str:
    base = (resources.files('mlkit') / 'assets' / 'design.css').read_text(encoding='utf-8')
    return base + REPORT_CSS + render_charts.CHART_CSS + render_diagnostics.CSS


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
.card.verdict{border-left:4px solid var(--accent)!important}
dl.facts{display:grid;grid-template-columns:minmax(0,200px) minmax(0,1fr);gap:4px 18px;max-width:none}
dl.facts dt{color:var(--muted)}dl.facts dd{margin:0;color:var(--ink)}
.dictionary td:first-child,.availability td:first-child{white-space:nowrap}
.verdict .conclusion{font-size:18px;color:var(--ink);margin:4px 0 10px}
.verdict q{display:block;margin:6px 0 12px;color:var(--ink)}
.verdict .limits li{margin:4px 0}
.badge.met{border-color:var(--accent);color:var(--accent)}
.badge.uncertain,.badge.not_met,.badge.not_assessed{border-style:dashed;border-color:var(--amber);color:var(--amber)}
.chip{display:inline-block;font-size:11px;font-weight:650;border-radius:999px;padding:1px 9px;margin-right:6px;background:var(--soft);color:var(--ink);border:1px solid var(--line)}
.chip.delegated_default{border-style:dashed;border-color:var(--amber)}
.dictionary td:nth-child(2){min-width:220px}
.rows td,.rows th{white-space:nowrap;font-size:12px}
details.ledger{margin:12px 0}
details.annex{margin:28px 0}
details.annex>summary{font-size:20px;font-weight:700;color:var(--ink)}
details>summary{cursor:pointer}
@media (max-width:640px){dl.facts{grid-template-columns:minmax(0,1fr)}dl.facts dd{margin-bottom:8px}}
.scroll-hint{display:none}
.report main section,.report main details{overflow-wrap:anywhere;min-width:0}
.report main table{overflow-wrap:normal}
@media (max-width:640px){.scroll-hint{display:block}.dictionary th,.dictionary td{padding:10px}.dictionary td:nth-child(2){min-width:150px}.dictionary td{overflow-wrap:anywhere}}
'''

THEME_SCRIPT = '''(function(){var b=document.body,k="hypotrail-theme",t=document.querySelector("[data-theme-toggle]");
function set(d){b.classList.toggle("dark",d);if(t){t.setAttribute("aria-pressed",d?"true":"false");}}
var s=null;try{s=window.localStorage.getItem(k);}catch(x){}
set(s?s==="dark":!!(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches));
if(t){t.addEventListener("click",function(){var d=!b.classList.contains("dark");set(d);try{window.localStorage.setItem(k,d?"dark":"light");}catch(x){}});}})();'''
# C9: shown on an open proposal whose stored origin is ``{channel: webview}``.
# C10: opening the report at ``#r-<result_id>`` unfolds that annex row (an anchor only).
ANCHOR_SCRIPT = '''(function(){function o(){var h=window.location.hash;if(h.indexOf("#r-")!==0){return;}
var n=document.getElementById(h.slice(1));if(n&&n.tagName==="DETAILS"){var p=n;while(p){if(p.tagName==="DETAILS"){p.open=true;}p=p.parentElement;}n.scrollIntoView();}}
o();window.addEventListener("hashchange",o);})();'''


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
    found = texts.concept(term_id)
    if not found:
        return ''
    term, definition, lang = found
    attr = ' lang="fr"' if lang == 'fr' else ''
    return f'<p{attr}><strong class="term">{e(term)}.</strong> {e(definition)}</p>'


def slots_of_step(step_id: str, results: Mapping, task: str | None = None) -> list[str]:
    """Result slots shown with a step: its activities, plus extra slots of the same family."""
    step = next(s for s in st.steps(task) if s['id'] == step_id)
    slots = list(step['activities'])
    family = {'train_eda': 'eda.', 'models': 'fit.', 'policy': 'policy.',
              'model_variant': 'fit.variant',      # v0.3 (WP-F1): every variant
              'model_choice': 'evaluate.'}.get(step_id)
    if family:
        slots += sorted(s for s in results if s.startswith(family) and s not in slots)
    return slots


# --- sections ---------------------------------------------------------------------------

def _surfaces(view: Mapping, surfaces: Mapping) -> str:
    labels = _labels()
    rows = []
    for name in ('report', 'notebook', 'editable', 'workbench'):
        info = surfaces.get(name) or {'status': 'not_rendered'}
        status = info.get('status', 'not_rendered')
        key = 'not_tracked' if info.get('tracked') is False and status == 'ok' else status
        text = labels['surface_status'].get(key, key)
        extra = ''
        if info.get('revision') is not None and status != 'ok':
            extra = (f' ({e(labels["last_written_for_revision"])} '
                     f'{lit("revision", info["revision"])})')
        if info.get('error'):
            extra += f' {lit("message", info["error"].get("message", ""))}'
        rows.append(f'<tr data-surface="{name}" data-status="{e(status)}"><td>'
                    f'{e(labels["surfaces"][name])}</td><td>{_badge(status, text)}{extra}</td></tr>')
    return (f'<section class="card" id="revision"><h2>{e(labels["sections"]["revision"])}</h2>'
            f'<p class="lead">{e(labels["generated_for_revision"])} '
            f'{lit("revision", view["revision"])}. '
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
            # v0.2a (WP-A1): the junior reads the report, never the agent's instruction.
            f'{lit("message", na.get("junior_message") or na.get("message", ""))}</p></section>')


def _concern(conf: Mapping) -> str:
    """R3 (ADR 0005): the point the agent raised before the junior confirmed, kept by them.
    Minimal; the report is redesigned by a later work package."""
    concern = conf.get('agent_concern')
    if not concern:
        return ''
    labels = _labels()
    return (f'<br><span class="small" data-concern="agent"><strong>'
            f'{e(labels["agent_concern"])}</strong> ({e(labels["agent_concern_kept"])}): '
            f'{lit("message", concern)}</span>')


def _warnings(conf: Mapping) -> str:
    """WP-A9 (H3): the ``words_contradict_value`` warnings the junior kept, in words."""
    items = [w for w in conf.get('warnings') or [] if isinstance(w, Mapping)]
    if not items:
        return ''
    labels = _labels()['contradiction']
    lines = []
    for w in items:
        text = labels['exclude' if w.get('said') == 'exclude' else 'keep'].format(
            variable=w.get('variable', ''))
        lines.append(f'<br><span class="small" data-warning="{e(str(w.get("code", "")))}" '
                     f'data-variable="{e(str(w.get("variable", "")))}"><strong>'
                     f'{e(labels["title"])}</strong>: {e(text)}</span>')
    return ''.join(lines)


def _reason_note(conf: Mapping) -> str:
    """v0.3 (WP-B, R27): "no reason given" for a trade-off confirmed without a reason, and
    the interactive-choice channel (R16) in words."""
    labels = _labels()
    out = ''
    if conf.get('channel') == 'choice':
        out += (f' <span class="small" data-channel-words="choice">'
                f'({e(labels["adoption_option"])})</span>')
    if conf.get('reason_given') is False:
        out += (f'<br><span class="small muted" data-reason-given="false">'
                f'{e(labels["no_reason_given"])}</span>')
    return out


def _chip(conf: Mapping) -> str:
    """The basis of a confirmation as a chip (v0.2a, WP-A6; ADR 0005)."""
    basis = conf.get('basis') or 'explicit'
    label = _labels().get('basis', {}).get(basis, basis)
    return f'<span class="chip {e(basis)}" data-basis-chip="{e(basis)}">{e(label)}</span>'


def _recorded(conf: Mapping) -> str:
    labels = _labels()
    return (f'<span class="small" data-channel="{e(str(conf.get("channel")))}" '
            f'data-actor="{e(str(conf.get("actor")))}">{e(labels["recorded_at"])} '
            f'{lit("revision", conf.get("revision"))}. {e(labels["not_authenticated"])}</span>')


def _confirmation(conf: Mapping) -> str:
    labels = _labels()
    if conf.get('basis') == 'delegated_default':
        return (f'<div class="words delegated" data-basis="delegated_default">'
                f'{_chip(conf)}{_badge("delegated", labels["delegated"])}'
                f'<strong>{e(labels["delegated_words"])}:</strong> '
                f'<q data-literal="user_words">{e(conf["user_words"])}</q>'
                f'<br><span class="small">{e(labels["delegated_note"])}</span>'
                f'<br>{_recorded(conf)}'
                f'<br><span class="small">{e(labels["delegated_restatement"])}: '
                f'{lit("proposal", conf.get("restatement", ""))}</span>{_concern(conf)}'
                f'{_warnings(conf)}</div>')
    return (f'<div class="words" data-basis="explicit">{_chip(conf)}'
            f'<strong>{e(labels["user_words"])}:</strong> '
            f'<q data-literal="user_words">{e(conf["user_words"])}</q>{_reason_note(conf)}'
            f'<br>{_recorded(conf)}'
            f'<br><span class="small">{e(labels["restatement"])}: '
            f'{lit("proposal", conf.get("restatement", ""))}</span>{_concern(conf)}'
            f'{_warnings(conf)}</div>')


def _credit(view: Mapping, titles: Mapping) -> str:
    """Who decided what, next to the conclusion (P7): a delegated decision is the
    assistant's recommended default, delegated by the analyst, never the analyst's choice."""
    labels = _labels()
    delegated, explicit = [], []
    for did, d in view['decisions'].items():
        conf = d['confirmation']
        if did == 'conclusion' or d['status'] not in ('confirmed', 'reconfirm_required') \
                or not conf:
            continue
        (delegated if conf.get('basis') == 'delegated_default' else explicit).append(
            titles.get(did, did))
    if not delegated and not explicit:
        return ''
    rows = []
    if delegated:
        rows.append(f'<li data-basis="delegated_default">{e(labels["credit_delegated"])} '
                    f'{e("; ".join(delegated))}.</li>')
    if explicit:
        rows.append(f'<li data-basis="explicit">{e(labels["credit_explicit"])} '
                    f'{e("; ".join(explicit))}.</li>')
    return (f'<div class="credit"><strong>{e(labels["credit_heading"])}</strong>'
            f'<ul>{"".join(rows)}</ul></div>')


def _note(n: Mapping) -> str:
    """A condition the junior stated on a decision (P2), open or resolved, verbatim."""
    labels = _labels()
    if n.get('kind') == 'correction':             # R3 (ADR 0005): a later correction
        return (f'<div class="words" data-note="{e(n["note_id"])}" data-status="recorded" '
                f'data-kind="correction"><strong>{e(labels["correction"])}:</strong> '
                f'<q data-literal="user_words">{e(n["user_words"])}</q>'
                f'<br><span class="small">{e(labels["correction_note"])}</span></div>')
    if n['status'] == 'open':
        return (f'<div class="words delegated" data-note="{e(n["note_id"])}" data-status="open">'
                f'{_badge("proposed", labels["hold_open"])}'
                f'<q data-literal="user_words">{e(n["user_words"])}</q>'
                f'<br><span class="small">{e(labels["hold_open_note"])}</span></div>')
    resolution = n.get('resolution') or {}
    withdrawn = n['status'] == 'withdrawn'          # D5: a hold the junior dropped
    return (f'<div class="words" data-note="{e(n["note_id"])}" data-status="{e(n["status"])}">'
            f'{_badge("confirmed", labels["hold_withdrawn" if withdrawn else "hold_resolved"])}'
            f'<q data-literal="user_words">{e(n["user_words"])}</q>'
            f'<br><span class="small">'
            f'{e(labels["hold_withdrawn_by" if withdrawn else "hold_resolved_by"])}: </span>'
            f'<q data-literal="user_words">{e(resolution.get("user_words", ""))}</q></div>')


def _availability_table(view: Mapping, variables: list[dict]) -> str:
    labels = _labels()
    decision = view['decisions']['feature_availability']
    value = decision['value'] if isinstance(decision['value'], dict) else {}
    features = [v for v in variables if v.get('role') == 'feature']
    if not features:
        return ''
    confirmed = decision['status'] == 'confirmed'
    # v0.2a (WP-A1): each feature says whether the junior discussed it (named in their words
    # or in the restatement they answered); an undiscussed one is never "your decision".
    bases = decision.get('feature_basis') or {}
    conf = decision.get('confirmation') or {}
    delegated = conf.get('basis') == 'delegated_default'
    basis_labels = labels['availability_basis']
    rows = []
    for v in features:
        status = value.get(v['name'])
        shown = labels['availability'].get(status or 'missing', status)
        kind = 'confirmed' if confirmed and status else ('proposed' if status else 'stale')
        stmt = v.get('availability') or {}
        case_label = labels['fact_status'].get(stmt.get('status'), stmt.get('status') or '')
        case_value = stmt.get('value')
        case_words = (labels['availability'].get(case_value)
                      if case_value not in (None, '', 'unknown', 'missing')
                      else labels['availability_not_stated'])
        basis = bases.get(v['name'])
        if not confirmed or not status:
            who, cls = labels['availability_basis_open'], 'proposed'
        elif delegated:
            who, cls = labels['delegated'], 'delegated'
        else:
            who = basis_labels.get(basis or 'default_from_case')
            cls = 'confirmed' if basis == 'discussed' else 'stale'
        rows.append(f'<tr data-feature="{e(v["name"])}" data-feature-basis="{e(basis or "")}">'
                    f'<td>{lit("identifier", v["name"], "code")}</td>'
                    f'<td>{_badge(kind, shown)}</td><td>{_badge(cls, who)}</td>'
                    f'<td>{_badge(stmt.get("status") or "unknown", case_label)} '
                    f'{lit("case", case_words or case_value or "")}</td></tr>')
    return ('<div class="scroll"><table class="availability"><thead><tr><th>Variable</th>'
            f'<th>{e(labels["availability_head"]["status"])}</th>'
            f'<th>{e(labels["availability_head"]["basis"])}</th>'
            f'<th>{e(labels["availability_head"]["case"])}</th></tr></thead><tbody>'
            f'{"".join(rows)}</tbody></table></div>')


def _decisions(view: Mapping, variables: list[dict]) -> str:
    labels = _labels()
    titles = {s['decision']: s['title'] for s in st.steps(view.get('task')) if s['decision']}
    cards = []
    for did, d in view['decisions'].items():
        status = d['status']
        parts = [f'<h3>{e(titles.get(did, did))} {_badge(status, labels["decision_status"][status])}</h3>']
        if d['value'] is not None and did != 'feature_availability':
            if did == 'conclusion' and isinstance(d['value'], dict):
                verdict = labels['verdict'].get(d['value'].get('verdict'), d['value'].get('verdict'))
                parts.append(f'<p><strong>{e(verdict)}.</strong> '
                             f'{lit("decision_value", d["value"].get("text", ""), "q")}</p>')
                parts.append(_credit(view, titles))
            else:
                parts.append(f'<p data-value="{e(_value_text(d["value"]))}">'
                             f'{lit("decision_value", value_words(did, d["value"], view.get("task")))}'
                             f'</p>')
        if did == 'feature_availability':
            parts.append(_availability_table(view, variables))
        if did == 'preprocessing' and isinstance(d['value'], Mapping):
            parts.append(_motivation(view, d['value']))
        if d['confirmation'] and status in ('confirmed', 'reconfirm_required'):
            parts.append(_confirmation(d['confirmation']))
        if d['reason']:
            parts.append(f'<p class="notice">'
                         f'{lit("message", audience.reason_words(d["reason"]))}</p>')
        for n in view.get('notes') or []:
            if n['decision_id'] == did:
                parts.append(_note(n))
        for p in view['open_proposals']:
            if p['decision_id'] == did:
                # C9: a proposal started in the companion says so (its stored origin).
                origin = p.get('origin') if isinstance(p.get('origin'), Mapping) else {}
                companion = (f'<span class="small" data-origin="webview">'
                             f'{e(labels["companion_origin"])}'
                             f'</span> ' if origin.get('channel') == 'webview' else '')
                parts.append(f'<div class="feedback" data-proposal="{e(p["proposal_id"])}">'
                             f'{_badge("proposed", labels["proposal_waiting"])}'
                             f'{companion}{lit("proposal", p["restatement"])}<br><span class="small">'
                             f'{lit("proposal", p["rationale"])}</span></div>')
        cards.append(f'<article data-decision="{e(did)}" data-status="{e(status)}">'
                     f'{"".join(parts)}</article>')
    return (f'<section id="decisions"><h2>{e(labels["sections"]["decisions"])}</h2>'
            f'{_concept("confirmed_decision")}{_concept("proposal")}{"".join(cards)}</section>')


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _motivation(view: Mapping, value: Mapping) -> str:
    """WP-A9 (M1): the questions that motivated a preparation, and whether it was chosen
    after looking at the outcome, in words."""
    labels = _labels()['motivation']
    by_rid = {item.get('result_id'): item for item in view['results'].values()}
    questions = []
    for rid in value.get('motivated_by') or []:
        item = by_rid.get(rid) or {}
        values = item.get('values') if isinstance(item.get('values'), Mapping) else {}
        question = values.get('question')
        if isinstance(question, str) and question:
            questions.append(f'<li data-motivated-by="{e(rid)}">{lit("message", question)}</li>')
        else:
            questions.append(f'<li data-motivated-by="{e(rid)}">'
                             f'{lit("message", labels["not_current"])}</li>')
    parts = []
    if questions:
        parts.append(f'<p class="small"><strong>{e(labels["questions"])}</strong></p>'
                     f'<ul class="small">{"".join(questions)}</ul>')
    looks = value.get('target_looks_before')
    if value.get('data_contingent'):
        text = labels['contingent']
        if isinstance(looks, int) and looks > 0:
            text += ' ' + labels['looks'].format(n=looks, s='' if looks == 1 else 's')
        parts.append(f'<p class="notice" data-contingent="true">{lit("structure", text)}</p>')
    elif value.get('motivated_by') is not None:
        parts.append(f'<p class="small" data-contingent="false">'
                     f'{lit("message", labels["not_contingent"])}</p>')
    return ''.join(parts)


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
            name = (labels.get('structure_words') or {}).get(key, key)
            structure.append(f'<li data-structure="{e(key)}">{_badge(status, label)}'
                             f'{lit("message", _capital(name))}: {lit("case", shown)} '
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
        # ``rows`` may be a dotted path (``numeric.bins`` of a distribution, C8).
        try:
            items = cite.resolve(entry.values, table['rows'].split('.'))
        except KeyError:
            items = None
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
            path = cite.format_path(table['rows'].split('.') + [str(i)] + keys)
            if c.get('kind') == 'text':
                try:
                    raw = cite.resolve(row, keys)
                except KeyError:
                    raw = None
                if isinstance(raw, bool):
                    # WP-A9 (M6): a flag reads in words, and only when it is set.
                    raw = 'yes' if raw else None
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
    title = spec.get('label') or labels.get('slot_labels', {}).get(slot, slot)
    item = view['results'].get(slot)
    if item is None:
        return (f'<div data-slot="{e(slot)}" data-state="pending"><h4>{e(title)}</h4>'
                f'<p class="muted">{e(texts.load("steps")["pending"])}</p></div>')
    if not citer.citable(item['result_id']):
        reason = (item['stale_reason'] or {}).get('reason') if item['stale_reason'] else item['integrity']
        return (f'<div data-slot="{e(slot)}" data-state="stale"><h4>{e(title)} '
                f'{_badge("stale", texts.load("steps")["stale"])}</h4>'
                f'<p class="small">{lit("message", audience.reason_words(reason))}</p></div>')
    question = item['values'].get('question') if isinstance(item['values'], Mapping) else None
    asked = f'<p><strong>Question.</strong> {lit("message", question)}</p>' if question else ''
    return (f'<div data-slot="{e(slot)}" data-state="current">'
            f'<h4 data-result="{e(item["result_id"])}" '
            f'data-partition="{e(str(item["partition"]))}">{e(title)}</h4>{asked}'
            f'{_concept(spec.get("glossary")) if spec.get("glossary") else ""}'
            f'<p class="small">Rows read: {e(_rows_words(item["partition"]))}.</p>'
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
        slots = slots_of_step(step['id'], view['results'], view.get('task'))
        parts += [_result_block(view, citer, slot) for slot in slots]
        if step['id'] == 'train_eda':
            parts.append(_looks(view))
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
        if adopted['status'] == 'confirmed' and str(adopted['value']).partition('@')[0] == key:
            tag = _badge('confirmed', labels['adopted'])
        elif key in {str(p).partition('@')[0] for p in proposed}:
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
                        f'<td>{lit("decision_value", rule_words(key))} {tag}</td>'
                        f'<td>{e(_model_name(str(model)))}</td>{"".join(cells)}'
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
                              f'<td>{lit("decision_value", rule_words(key))}</td>'
                              f'<td>{e(_model_name(str(model)))}</td><td>{e(m["label"])}</td>'
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
    comparisons = _comparison_rows(citer, rid, rules, metrics)
    population = ''
    if any(key.startswith('capacity:') for key in rules) and citer.has(rid, 'n'):
        # F2: a capacity is a count on these rows; say which population, and its rate.
        pop = labels['capacity_population']
        population = (f'<p class="notice" data-note="capacity_population">{e(pop["before"])} '
                      f'{citer.num(rid, "n", "int")} {e(pop["after"])}</p>')
    note = labels['policy_note_oof'] if values.get('evaluation') == 'out_of_fold' \
        else labels['policy_note']
    return (head + f'<p class="notice">{e(note)}{level}</p>{population}'
            f'{table}{pair_table}{comparisons}'
            f'{_figures(citer, rid, texts.activity("policy.evaluation"))}</section>')


def _comparison_rows(citer: cite.Citer, rid: str, rules: Mapping | None, metrics) -> str:
    """WP-B1: the variant against the candidate, paired on the same rows (cited)."""
    labels = _labels()
    rows = []
    # v0.3 (WP-F1): with several variants, each row names its model.
    named = set()
    for key, item in (rules or {'': None}).items():
        source = item if rules else citer.results[rid].values
        if isinstance(source, Mapping) and isinstance(source.get('comparisons'), Mapping):
            named |= set(source['comparisons'])
    several = len(named) > 1
    for key, item in (rules or {'': None}).items():
        prefix = ['rules', key] if rules else []
        source = item if rules else citer.results[rid].values
        comparisons = source.get('comparisons') if isinstance(source, Mapping) else None
        if not isinstance(comparisons, Mapping):
            continue
        for model in sorted(comparisons):
            for m in metrics:
                base = prefix + ['comparisons', str(model), m['key']]
                point = cite.format_path(base + ['point'])
                if not citer.has(rid, point):
                    continue
                fmt = m.get('fmt', 'auto')
                rule = (f'<td>{lit("decision_value", rule_words(key))}</td>' if rules else '')
                if several:
                    rule += f'<td>{e(_model_name(str(model)))}</td>'
                rows.append(f'<tr data-model="{e(model)}" data-metric="{e(m["key"])}">{rule}'
                            f'<td>{e(m["label"])}</td><td>{citer.num(rid, point, fmt)}</td>'
                            f'<td>{_interval(citer, rid, base, fmt)}</td></tr>')
    if not rows:
        return ''
    rule_head = ('<th>Rule</th>' if rules else '') + ('<th>Model</th>' if several else '')
    return (f'<h3>{e(labels["comparison_heading"])}</h3><div class="scroll">'
            f'<table class="paired" id="variant-comparison"><thead><tr>{rule_head}'
            '<th>Metric</th><th>Difference</th><th>Interval</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')


def _model_comparison(view: Mapping, citer: cite.Citer) -> str:
    """Regression model comparison from the canonical ``evaluate.regression`` values
    (``models``, ``intervals``, ``deltas``, ``residuals``, ``residuals_by``;
    CLI-CONTRACT.md section 8.5). Every number is cited."""
    labels = _labels()
    head = (f'<section class="card" id="model-comparison"><h2>{e(labels["sections"]["policy"])}</h2>'
            f'{_concept("mae")}{_concept("rmse")}{_concept("residual")}{_concept("bias")}'
            f'{_concept("paired_bootstrap")}')
    rid = citer.slot_rid('evaluate.regression')
    if rid is None:
        return head + f'<p class="muted">{e(labels["model_missing"])}</p></section>'
    values = citer.results[rid].values
    values = values if isinstance(values, Mapping) else {}
    choice = view['decisions'].get('model_choice') or {}
    proposed = {p['value'] for p in view['open_proposals'] if p['decision_id'] == 'model_choice'}
    metrics = texts.regression_metrics()
    level = ''
    if citer.has(rid, 'bootstrap.level'):
        level = f' Intervals: {citer.num(rid, "bootstrap.level", "pct0")} percentile intervals.'
    unit = values.get('unit')
    unit_note = f' Unit: {lit("case", unit)}.' if unit else ''
    rows, paired = [], []
    models = values.get('models') if isinstance(values.get('models'), Mapping) else {}
    for model in models:
        tag = ''
        if choice.get('status') == 'confirmed' and choice.get('value') == model:
            tag = _badge('confirmed', labels['chosen_model'])
        elif model in proposed:
            tag = _badge('proposed', labels['proposed_model'])
        cells = []
        for m in metrics:
            path = cite.format_path(['models', str(model), m['key']])
            fmt = m.get('fmt', 'auto')
            shown = citer.num(rid, path, fmt) if citer.has(rid, path) else ''
            interval = _interval(citer, rid, ['intervals', str(model), m['key']], fmt)
            extra = f' <span class="small">{interval}</span>' if interval else ''
            cells.append(f'<td>{shown}{extra}</td>')
        rows.append(f'<tr data-model="{e(model)}"><td>{e(_model_name(str(model)))} {tag}</td>'
                    f'{"".join(cells)}</tr>')
    deltas = values.get('deltas') if isinstance(values.get('deltas'), Mapping) else {}
    for model, by_metric in sorted(deltas.items()):
        if not isinstance(by_metric, Mapping):
            continue
        for m in metrics:
            base = ['deltas', str(model), m['key']]
            point = cite.format_path(base + ['point'])
            if not citer.has(rid, point):
                continue
            fmt = m.get('fmt', 'auto')
            paired.append(f'<tr data-model="{e(model)}" data-metric="{e(m["key"])}">'
                          f'<td>{e(_model_name(str(model)))}</td><td>{e(m["label"])}</td>'
                          f'<td>{citer.num(rid, point, fmt)}</td>'
                          f'<td>{_interval(citer, rid, base, fmt)}</td></tr>')
    table = ''
    if rows:
        th = ''.join(f'<th>{e(m["label"])}</th>' for m in metrics)
        table = (f'<div class="scroll"><table class="metrics"><thead><tr><th>Model</th>{th}</tr>'
                 f'</thead><tbody>{"".join(rows)}</tbody></table></div>')
    pair_table = ''
    if paired:
        pair_table = (f'<h3>{e(labels["model_paired_heading"])}</h3><div class="scroll">'
                      '<table class="paired"><thead><tr><th>Model</th><th>Metric</th>'
                      '<th>Difference</th><th>Interval</th></tr></thead>'
                      f'<tbody>{"".join(paired)}</tbody></table></div>')
    note = labels['model_note_oof'] if values.get('evaluation') == 'out_of_fold' \
        else labels['model_note']
    return (head + f'<p class="notice">{e(note)}{level}{unit_note}</p>'
            f'{table}{pair_table}{_comparison_rows(citer, rid, None, metrics)}'
            f'{_residuals(citer, rid, values)}'
            f'{_figures(citer, rid, texts.activity("evaluate.regression"))}</section>')


RESIDUAL_COLUMNS = (('mean', 'Mean (bias)'), ('sd', 'Standard deviation'), ('q05', '5th percentile'),
                    ('q25', 'First quartile'), ('median', 'Median'), ('q75', 'Third quartile'),
                    ('q95', '95th percentile'))


def _residuals(citer: cite.Citer, rid: str, values: Mapping) -> str:
    """Residual distribution per model, then residuals by period (cited tables)."""
    labels = _labels()
    out = ''
    residuals = values.get('residuals') if isinstance(values.get('residuals'), Mapping) else {}
    rows = []
    for model in residuals:
        cells = []
        for key, _ in RESIDUAL_COLUMNS:
            path = cite.format_path(['residuals', str(model), key])
            cells.append(f'<td>{citer.num(rid, path, "f2") if citer.has(rid, path) else ""}</td>')
        rows.append(f'<tr data-model="{e(model)}"><td>{e(_model_name(str(model)))}</td>'
                    f'{"".join(cells)}</tr>')
    if rows:
        th = ''.join(f'<th>{e(label)}</th>' for _, label in RESIDUAL_COLUMNS)
        out += (f'<h3>{e(labels["residuals_heading"])}</h3><div class="scroll">'
                f'<table class="residuals"><thead><tr><th>Model</th>{th}</tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table></div>')
    for i, block in enumerate(values.get('residuals_by') or []):
        if not isinstance(block, Mapping):
            continue
        models = list(residuals) or sorted({m for g in block.get('groups', [])
                                            for m in (g.get('models') or {})})
        th = ''.join(f'<th>{e(_model_name(m))}: mean residual</th><th>{e(_model_name(m))}: MAE</th>'
                     for m in models)
        body = []
        for j, group in enumerate(block.get('groups') or []):
            prefix = ['residuals_by', str(i), 'groups', str(j)]
            cells = [f'<td>{lit("category", group.get("value", ""))}</td>',
                     f'<td>{citer.num(rid, cite.format_path(prefix + ["n_rows"]), "int")}</td>']
            for m in models:
                for key in ('mean_residual', 'mae'):
                    path = cite.format_path(prefix + ['models', m, key])
                    cells.append(f'<td>{citer.num(rid, path, "f2") if citer.has(rid, path) else ""}</td>')
            small = 'yes' if group.get('small_count') else ''
            cells.append(f'<td>{lit("category", small)}</td>')
            body.append(f'<tr data-group="{e(str(group.get("value", "")))}">{"".join(cells)}</tr>')
        out += (f'<h3>{e(labels["residuals_by_heading"])}: '
                f'{lit("identifier", block.get("column", ""), "code")}</h3><div class="scroll">'
                f'<table class="residuals-by" data-column="{e(str(block.get("column", "")))}">'
                f'<thead><tr><th>Value</th><th>Rows</th>{th}<th>Too few rows to read alone</th>'
                f'</tr></thead><tbody>{"".join(body)}</tbody></table></div>')
    return out


def _not_yet_defensible(view: Mapping) -> str:
    labels = _labels()
    extra = labels['not_yet_defensible_extra']
    items = []
    for item in view['not_yet_defensible']:
        if item.get('junior') is False:
            # v0.3 (WP-A, R34): stale results no junior surface cites are the agent's to
            # recompute, not a limit of the study.
            continue
        details = []
        titles = {s['decision']: s['title'] for s in st.steps(view.get('task')) if s['decision']}
        if item.get('decisions'):
            details.append(', '.join(e(titles.get(x, x)) for x in item['decisions']))
        if item.get('rules'):
            details.append(', '.join(lit('decision_value', rule_words(x)) for x in item['rules']))
        if item.get('features'):
            details.append(', '.join(lit('identifier', x, 'code') for x in item['features']))
        if item.get('missing'):
            # WP-A9 (M6): structure keys in words, never as raw ids.
            words = labels.get('structure_words') or {}
            details.append(', '.join(lit('message', words.get(x, x)) for x in item['missing']))
        ids = [str(x) for key in ('results', 'executions', 'slots') for x in item.get(key) or []]
        for source in item.get('sources') or []:
            details.append(lit('case', source))
        if isinstance(item.get('column'), str):
            details.append(lit('identifier', item['column'], 'code'))
        more = f' {e(extra[item["id"]])}' if item['id'] in extra else ''
        text = item.get('junior_text') or item['text']      # v0.2a (WP-A1): for the junior
        refs = f' data-refs="{e(" ".join(ids))}"' if ids else ''
        items.append(f'<li data-nyd="{e(item["id"])}"{refs}><strong>{lit("message", text)}</strong>'
                     f'{more}{"<br>" + "; ".join(details) if details else ""}</li>')
    return (f'<section class="card" id="not-yet-defensible">'
            f'<h2>{e(labels["sections"]["not_yet_defensible"])}</h2>'
            f'{_concept("selection_on_validation")}<ul>{"".join(items)}</ul></section>')


# WP-B4: the capped points of a diagnostic scatter plot are drawn, never shown as figures; the
# annex leaves them out (they stay in the registry and in ``hypotrail evidence``).
ANNEX_SKIPPED = 'scatter'


def _annex(view: Mapping, citer: cite.Citer) -> str:
    labels = _labels()
    blocks = []
    anchored: set[str] = set()
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
            if ANNEX_SKIPPED in segments:
                continue        # WP-B4: chart points are drawn, not shown as figures
            path = cite.format_path(segments)
            rows.append(f'<tr><td>{lit("identifier", path, "code")}</td>'
                        f'<td>{citer.num(rid, path, "auto")}</td></tr>')
        env = item['environment'] or {}
        meta = (f'<p class="small">Full id {lit("identifier", rid, "code")}; partition '
                f'{lit("identifier", item["partition"] or "not recorded")}; parameters '
                f'{lit("parameter", _value_text(item["params"]), "code")}; code fingerprint '
                f'{lit("identifier", (item["code_fingerprint"] or "")[:12], "code")}; environment '
                f'{lit("environment", "Python " + str(env.get("python", "unknown")))}.</p>')
        # C10: one anchor per cited result (``#r-<result_id>``); an anchor only, never a
        # link to an editor or a control (CLI-CONTRACT-COMPANION §10, §11).
        anchor = f' id="r-{e(rid)}"' if rid not in anchored else ''
        anchored.add(rid)
        blocks.append(f'<details{anchor} data-slot="{e(slot)}" data-state="current">{head}{meta}'
                      f'<div class="scroll"><table><thead><tr><th>Value path</th><th>Value</th></tr>'
                      f'</thead><tbody>{"".join(rows)}</tbody></table></div></details>')
    exposure = view['exposure']
    purposes = sorted(p for p, n in (exposure.get('by_purpose') or {}).items() if n)
    used = bool(exposure.get('validation_rows_used_for_selection'))
    exp = (f'<h3>{e(texts.glossary("exposure")["term"])}</h3>{_concept("exposure")}'
           f'<p>Purposes recorded: {", ".join(lit("identifier", p, "code") for p in purposes) or "none"}. '
           f'Validation rows used for selection: {"yes" if used else "no"}.</p>')
    return (f'<section class="annex-section"><details class="annex" id="annex"><summary>'
            f'{e(labels["sections"]["annex"])}</summary>'
            f'<p class="small">{e(labels["annex_note"])}</p>{"".join(blocks)}{exp}</details>'
            f'</section>')


def _history(view: Mapping) -> str:
    """Explicitly separate historical IDs from the current evidence narrative."""
    historical = (view.get('presentation') or {}).get('historical') or {}
    ids = historical.get('stale_result_ids') or []
    drift = historical.get('changed_after_opening')
    if not ids and not drift:
        return ''
    items = ''.join(f'<li>{lit("identifier", rid, "code")}</li>' for rid in ids)
    drift_text = ('<p><strong>Final-test drift:</strong> decisions or results changed after '
                  'the final test was opened; current development evidence is kept separate '
                  'from that historical final measurement.</p>' if drift else '')
    return (f'<section class="card" id="history"><h2>Historical record</h2>{drift_text}'
            f'<p>Historical results remain inspectable and are not current adoption evidence.'
            f'</p><ul>{items}</ul></section>')


# --- v0.2a (WP-A6): words for recorded values ------------------------------------------------

def rule_words(rule: Any) -> str:
    """A policy rule in business words (``capacity:100`` -> "Select the 100 highest-scored
    rows"). The number is the recorded decision value."""
    text = str(rule)
    kind, _, param = text.partition(':')
    if kind == 'capacity' and param:
        return f'Select the {param} highest-scored rows'
    if kind == 'threshold' and param:
        return f'Select every row scored {param} or more'
    if kind == 'share' and param:
        from .audience import share_percent
        return f'Select the {share_percent(param)} highest-scored rows'
    return text


def _share_words(share: Any) -> str:
    if isinstance(share, (int, float)) and not isinstance(share, bool):
        pct = 100 * share
        return f'{pct:.0f}%' if abs(pct - round(pct)) < 1e-9 else f'{pct:g}%'
    return str(share)


def value_words(decision_id: str, value: Any, task: str | None) -> str:
    """A decision value as the junior reads it; the raw value stays in ``data-value``."""
    if value is None:
        return ''
    if decision_id == 'policy':
        # WP-B1: a rule applied to the variant says so.
        rule, sep, model = str(value).partition('@')
        words = rule_words(rule)
        # v0.3 (WP-F1): the second and third variants are named as such.
        return f'{words}, with {audience.model_words(model)}' if sep and model else words
    if decision_id == 'model_choice':
        return {'fit.linear': 'Use the linear model',
                'fit.variant': 'Use the variant of the linear model',
                'fit.variant:2': 'Use the second variant',
                'fit.variant:3': 'Use the third variant',
                'fit.baseline': 'Keep predicting the training mean (the baseline)'}.get(
                    value, str(value))
    if isinstance(value, Mapping):
        if decision_id == 'model_variant':
            from .audience import variant_words
            from . import trials
            if trials.is_list_value(value):
                return 'Compare the model with: ' + variant_words(value)
            return 'Compare the model with a variant: ' + variant_words(value)
        if decision_id == 'final_test':
            model = _model_name(str(value.get('model')))
            rule = value.get('rule')
            return (f'Open the final test once for {model}'
                    + (f', rule: {rule_words(rule)}' if rule else ''))
        if decision_id == 'split' and value.get('method') in ('kfold_stratified', 'kfold_quantile',
                                                               'temporal_folds'):
            kind = {'kfold_stratified': 'stratified on the outcome',
                    'kfold_quantile': 'stratified on target quantiles',
                    'temporal_folds': 'blocks in time order'}[value['method']]
            seed = (f' (seed {value["seed"]})' if value['method'] != 'temporal_folds'
                    and 'seed' in value else '')
            return (f'Cross-validation on the development rows: {value.get("folds")} folds, '
                    f'{kind}{seed}; every row is predicted once by a model that did not see it')
        if decision_id == 'split' and value.get('method') in texts.FORWARD_METHODS:
            # Review round 4 (E4-5): a review-v1 plan that chains forward in time.
            gap = value.get('gap')
            gap_words = (f', a gap of {gap} on the clock between the rows fitted and the '
                         f'window scored' if gap else '')
            return (f'Forward-chaining cross-validation on the development rows: '
                    f'{value.get("folds")} folds in the order of prediction time{gap_words}; '
                    f'each later window is scored once by a model fitted on earlier rows only, '
                    f'and the earliest rows (the warm-up) train but are never scored')
        if decision_id == 'split' and value.get('method') == 'group_disjoint':
            return (f'Cross-validation on the development rows: {value.get("folds")} folds that '
                    f'never share a group; every row is predicted once by a model that did not '
                    f'see its group')
        if decision_id == 'split':
            method = value.get('method')
            if method == 'ordinal_cutoff':
                return (f'Rows with {value.get("column")} at {value.get("cutoff")} or later are '
                        f'validation rows; earlier rows train the models')
            share = _share_words(value.get('validation_fraction'))
            kind = 'Stratified random split' if method == 'stratified_random' else 'Random split'
            seed = f' (seed {value["seed"]})' if 'seed' in value else ''
            return f'{kind}: {share} of the development rows for validation{seed}'
        if decision_id == 'success_criterion':
            if value.get('metric') == 'precision_gain':
                return (f'Adopt only if the precision beats the baseline by at least '
                        f'{value.get("min_points")} percentage points at the adopted rule')
            if value.get('metric') == 'recall_gain':
                # v0.3 (WP-C, R18): the junior may fix the criterion on recall.
                return (f'Adopt only if the recall beats the baseline by at least '
                        f'{value.get("min_points")} percentage points at the adopted rule')
            if value.get('metric') == 'mae_reduction':
                return (f'Adopt only if the model\'s mean absolute error is at least '
                        f'{_share_words(value.get("min_share"))} below the mean baseline\'s')
        if decision_id == 'preprocessing':
            parts = []
            missing = value.get('missing')
            if missing == 'indicator':
                parts.append('a missing-value indicator for every feature with missing cells')
            elif isinstance(missing, Mapping) and missing:
                parts.append('missing-value indicators for ' + ', '.join(sorted(missing)))
            k = value.get('rare_category_min_rows')
            if isinstance(k, int) and k > 0:
                # B6c (M3): under cross-validation, the rows each fold's model is fitted on.
                rows = ('rows a model is fitted on' if texts.is_cv() else 'training rows')
                parts.append(f'categories with fewer than {k} {rows} grouped')
            if value.get('caps'):
                parts.append('values capped for ' + ', '.join(sorted(value['caps'])))
            if value.get('log_transform'):
                parts.append('log transform of ' + ', '.join(value['log_transform']))
            if not parts:
                return 'Default preparation: nothing added, grouped, capped, or transformed'
            return 'Preparation: ' + '; '.join(parts)
    return _value_text(value)


# v0.3 (WP-F1): the second and third variants (no digit in the teaching texts).
MODEL_NAMES_EXTRA = {'fit.variant:2': 'Second variant', 'fit.variant:3': 'Third variant'}


def _model_name(model: str) -> str:
    return _labels().get('model_names', {}).get(model, MODEL_NAMES_EXTRA.get(model, model))


def _rows_words(partition: Any) -> str:
    return _labels().get('rows_label', {}).get(partition, str(partition or 'not recorded'))


# --- v0.2a (WP-A6): verdict card -----------------------------------------------------------

def _limits(view: Mapping, n: int = 3) -> list[str]:
    out = []
    for item in view['not_yet_defensible'][:n]:
        out.append(item.get('junior_text') or item['text'])
    return out


def _binary_figures(view: Mapping, citer: cite.Citer, rule: str | None,
                    model: str = 'fit.logistic') -> list[tuple[str, str]]:
    rid = citer.slot_rid('policy.evaluation')
    if rid is None or rule is None:
        return []
    m = cite.format_path(['rules', rule, 'models', model])
    b = cite.format_path(['rules', rule, 'models', 'fit.baseline'])
    d = cite.format_path(['rules', rule, 'deltas', model, 'precision'])
    iv = cite.format_path(['rules', rule, 'intervals', model, 'precision'])
    rows = []

    def opt(path: str, fmt: str, before: str = '', after: str = '') -> str:
        # an undefined value (no row selected: no precision) is left out, never cited
        return f'{before}{citer.num(rid, path, fmt)}{after}' if citer.has(rid, path) else ''

    def interval(base: str, fmt: str) -> str:
        if citer.has(rid, base + '.low') and citer.has(rid, base + '.high'):
            return (f', interval {citer.num(rid, base + ".low", fmt)} to '
                    f'{citer.num(rid, base + ".high", fmt)}')
        return ''

    if not (citer.has(rid, f'{m}.true_positives') and citer.has(rid, f'{m}.selected')):
        return []
    precision = opt(m + '.precision', 'pct1', ' (precision ', interval(iv, 'pct1') + ')') \
        if citer.has(rid, m + '.precision') else ''
    rows.append(('Positive rows found by the model',
                 f'{citer.num(rid, m + ".true_positives", "auto")} among '
                 f'{citer.num(rid, m + ".selected", "auto")} selected rows{precision}'))
    if citer.has(rid, f'{b}.true_positives'):
        rows.append(('Baseline at the same rule',
                     f'{citer.num(rid, b + ".true_positives", "auto")} on average without '
                     f'ranking{opt(b + ".precision", "pct1", " (precision ", ")")}'))
    if citer.has(rid, f'{d}.point'):
        interval = ''
        if citer.has(rid, f'{d}.low') and citer.has(rid, f'{d}.high'):
            interval = (f', interval {citer.num(rid, d + ".low", "pts1")} to '
                        f'{citer.num(rid, d + ".high", "pts1")}')
        rows.append(('Precision gain over the baseline',
                     f'{citer.num(rid, d + ".point", "pts1")} percentage points{interval}'))
    return rows


def _regression_figures(citer: cite.Citer, chosen: str = 'fit.linear') -> list[tuple[str, str]]:
    rid = citer.slot_rid('evaluate.regression')
    if rid is None:
        return []
    rows = []
    for model in ('fit.linear', 'fit.variant', 'fit.variant:2', 'fit.variant:3', 'fit.baseline'):
        path = cite.format_path(['models', model, 'mae'])
        if not citer.has(rid, path):
            continue
        iv = cite.format_path(['intervals', model, 'mae'])
        interval = (f' (interval {citer.num(rid, iv + ".low", "f2")} to '
                    f'{citer.num(rid, iv + ".high", "f2")})' if citer.has(rid, iv + '.low')
                    else '')
        rows.append((f'Mean absolute error, {_model_name(model).lower()}',
                     f'{citer.num(rid, path, "f2")}{interval}'))
    d = cite.format_path(['deltas', chosen, 'mae'])
    if citer.has(rid, d + '.point'):
        interval = (f' (interval {citer.num(rid, d + ".low", "f2")} to '
                    f'{citer.num(rid, d + ".high", "f2")})' if citer.has(rid, d + '.low')
                    else '')
        rows.append(('Difference, linear minus baseline' if chosen == 'fit.linear' else
                     'Difference, variant minus baseline',
                     f'{citer.num(rid, d + ".point", "f2")}{interval}; negative means a '
                     f'smaller error'))
    return rows


def _verdict(view: Mapping, citer: cite.Citer) -> str:
    labels = _labels()
    card = labels['verdict_card']
    task = view.get('task') or 'binary'
    conclusion = view['decisions']['conclusion']
    parts = [f'<h2>{e(labels["sections"]["verdict"])}</h2>']
    value = conclusion.get('value') if isinstance(conclusion.get('value'), Mapping) else None
    if conclusion['status'] == 'confirmed' and value:
        verdict = labels['verdict'].get(value.get('verdict'), value.get('verdict'))
        parts.append(f'<p class="conclusion" data-verdict="{e(str(value.get("verdict")))}">'
                     f'<strong>{e(verdict)}.</strong></p>'
                     f'{lit("decision_value", value.get("text", ""), "q")}')
    else:
        waiting = any(p['decision_id'] == 'conclusion' for p in view['open_proposals'])
        parts.append(f'<p class="conclusion" data-verdict="none"><strong>'
                     f'{e(card["not_concluded"])}</strong>'
                     f'{" " + e(card["proposed"]) if waiting else ""}</p>')
    rows = []
    criterion = view.get('criterion')
    if criterion is not None:
        sc = view['decisions'].get('success_criterion') or {}
        if sc.get('status') == 'confirmed':
            status = criterion.get('status') or 'not_assessed'
            words = value_words('success_criterion', sc['value'], task)
            if criterion.get('judged_on') == 'final_test':
                # B6c (H4): one judged criterion, on the final test once it is opened; the
                # development status is context, explained when the two differ.
                judged = criterion.get('judged_status') or 'not_assessed'
                text = (f'{lit("decision_value", words)}. '
                        f'{_badge(judged, card["status"].get(judged, judged))} '
                        f'{e(card["judged_final"])}'
                        f'<br><span class="small" data-development-status="{e(status)}">'
                        f'{e(card["development_status"])} '
                        f'{e(card["status"].get(status, status))}.')
                if judged != status:
                    text += f' {e(card["status_differ"])}'
                rows.append((card['criterion'], text + '</span>'))
            else:
                rows.append((card['criterion'],
                             f'{lit("decision_value", words)}. '
                             f'{_badge(status, card["status"].get(status, status))}'))
        else:
            rows.append((card['criterion'], e(card['criterion_none'])))
    decision = 'model_choice' if task == 'regression' else 'policy'
    adopted = view['decisions'].get(decision) or {}
    if adopted.get('status') == 'confirmed':
        rows.append((card['rule'], lit('decision_value',
                                       value_words(decision, adopted['value'], task))))
    else:
        rows.append((card['rule'], e(card['rule_none'])))
    if task == 'regression':
        chosen = (criterion or {}).get('model') or 'fit.linear'
        figures = _regression_figures(citer, chosen if chosen != 'fit.baseline'
                                      else 'fit.linear')
    else:
        rule = (criterion or {}).get('rule')
        model = (criterion or {}).get('model') or 'fit.logistic'
        if rule is None and adopted.get('status') == 'confirmed':
            rule = str(adopted.get('value')).partition('@')[0]
            from .records import policy_model
            model = policy_model(adopted.get('value'))
        figures = _binary_figures(view, citer, rule, model)
        if figures and rule and not (adopted.get('status') == 'confirmed'
                                     and str(adopted.get('value')).partition('@')[0] == rule):
            figures.insert(0, ('Rule of these figures', lit('decision_value', rule_words(rule))))
    b1 = 'final_test' in view['decisions']
    if figures and b1:
        # WP-B1: the figures above are development evidence; the final test is apart.
        figures.insert(0, (card['development'], e(card['development_note']
                                                   if _out_of_fold(citer, task)
                                                   else card['validation_note'])))
    development = figures or [(card['figures'], e(card['figures_none']))]
    if b1 and (view.get('final_test') or {}).get('status') == 'opened':
        # WP-B6a: once the final test is opened, its evidence comes first and the
        # development evidence second, still labelled as such.
        rows += _final_rows(view, citer, task) + development
    else:
        rows += development
        if b1:
            rows += _final_rows(view, citer, task)
    parts.append('<dl class="facts">' + ''.join(f'<dt>{e(k)}</dt><dd>{v}</dd>'
                                                  for k, v in rows) + '</dl>')
    limits = _limits(view)
    if limits:
        parts.append(f'<h3>{e(card["limits"])}</h3><ul class="limits">'
                     + ''.join(f'<li>{lit("message", t)}</li>' for t in limits)
                     + f'</ul><p class="small"><a href="#not-yet-defensible">'
                       f'{e(card["all_limits"])}</a></p>')
    return f'<section class="card verdict" id="verdict">{"".join(parts)}</section>'


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text else text


def _out_of_fold(citer: cite.Citer, task: str) -> bool:
    rid = citer.slot_rid('evaluate.regression' if task == 'regression' else 'policy.evaluation')
    if rid is None:
        return False
    values = citer.results[rid].values
    return isinstance(values, Mapping) and values.get('evaluation') == 'out_of_fold'


def _final_rows(view: Mapping, citer: cite.Citer, task: str) -> list[tuple[str, str]]:
    """WP-B1: the final-test part of the verdict card, apart from the development evidence:
    sealed, or the one evaluation of the chosen configuration (cited), with the success
    criterion judged on it, and a warning when something changed after the opening."""
    card = _labels()['verdict_card']
    final = view.get('final_test') or {}
    status = final.get('status')
    if status in (None, 'absent'):
        return [(card['final'], e(card['final_absent']))]
    if status == 'sealed':
        rows = [(card['final'], e(card['final_sealed']))]
    else:
        rid = citer.slot_rid('final_test.evaluation')
        if rid is None:
            return [(card['final'], e(card['final_missing']))]
        values = citer.results[rid].values
        model = str(values.get('model'))
        rows = [(card['final'], f'{e(card["final_opened"])} '
                                f'{citer.num(rid, "n", "int")} {e(card["final_rows"])}')]
        if task == 'regression':
            for slot in (model, 'fit.baseline') if model != 'fit.baseline' else (model,):
                path = cite.format_path(['models', slot, 'mae'])
                if citer.has(rid, path):
                    # B6c (Low): the error is in the target's unit; say which.
                    unit = values.get('unit')
                    rows.append((f'{card["final_mae"]}, {_model_name(slot).lower()}',
                                 citer.num(rid, path, 'f2')
                                 + (f' {lit("case", unit)}' if unit else '')))
        else:
            rule = values.get('rule_final')
            m = cite.format_path(['models', model])
            if rule and citer.has(rid, f'{m}.true_positives') and citer.has(rid, f'{m}.selected'):
                precision = (f' (precision {citer.num(rid, m + ".precision", "pct1")})'
                             if citer.has(rid, m + '.precision') else '')
                rows.append((card['final_found'],
                             f'{citer.num(rid, m + ".true_positives", "auto")} among '
                             f'{citer.num(rid, m + ".selected", "auto")} selected rows'
                             f'{precision}; {lit("decision_value", _lower_first(rule_words(rule)))}'))
        crit = values.get('criterion') if isinstance(values.get('criterion'), Mapping) else {}
        # B6c (B1): the binary final criterion is stored in percentage points already
        # (``fit.final_evaluation``); the regression one is a share shown as a percentage.
        fmt = 'f1' if task != 'regression' else 'pct1'
        if crit.get('gain') is not None and citer.has(rid, 'criterion.gain'):
            interval = ''
            if citer.has(rid, 'criterion.low') and citer.has(rid, 'criterion.high'):
                interval = (f', interval {citer.num(rid, "criterion.low", fmt)} to '
                            f'{citer.num(rid, "criterion.high", fmt)}')
            unit = ' percentage points' if task != 'regression' else ''
            state = crit.get('status') or 'not_assessed'
            judged_here = (view.get('criterion') or {}).get('judged_on') == 'final_test'
            # B6c (H4): the badge is shown once, on the success-criterion row, when the
            # criterion is judged on this evaluation.
            badge = '' if judged_here else \
                f' {_badge(state, card["status"].get(state, state))}'
            gain_words = card['final_gain'] if task != 'regression' else card['final_reduction']
            rows.append((card['final_criterion'],
                         f'{e(gain_words)} {citer.num(rid, "criterion.gain", fmt)}{unit}'
                         f'{interval}.{badge}'))
    if final.get('post_final_test'):
        rows.append((card['final_after'], e(card['final_after_note'])))
    trials = (view.get('trials') or {}).get('count')
    if isinstance(trials, int) and trials:
        rows.append((card['trials'], f'{lit("structure", trials)} {e(card["trials_note"])}'))
    return rows


# --- v0.2a (WP-A6): the objective and the data -----------------------------------------------

def _fact_value(view: Mapping, fact_id: str):
    for items in view['facts']['by_status'].values():
        for f in items:
            if f['id'] == fact_id:
                return f
    return None


def _objective(view: Mapping) -> str:
    labels = _labels()
    items = []
    for fid, name in (('decision', 'Decision the study supports'),
                      ('intended_use', 'Intended use')):
        f = _fact_value(view, fid)
        if f:
            items.append(f'<dt>{e(name)}</dt><dd>{lit("case", f["value"])}</dd>')
    pt = view['decisions'].get('prediction_time') or {}
    if pt.get('status') == 'confirmed':
        items.append(f'<dt>Prediction moment</dt><dd>'
                     f'{lit("decision_value", value_words("prediction_time", pt["value"], view.get("task")))}'
                     f'</dd>')
    if not items:
        return ''
    return (f'<section class="card" id="objective"><h2>{e(labels["sections"]["objective"])}</h2>'
            f'<dl class="facts">{"".join(items)}</dl></section>')


def _who_decided(view: Mapping, name: str) -> tuple[str, str, str]:
    """``(status shown, who decided, css class)`` of one feature's availability."""
    labels = _labels()
    decision = view['decisions']['feature_availability']
    value = decision['value'] if isinstance(decision['value'], dict) else {}
    status = value.get(name)
    shown = labels['availability'].get(status or 'missing', status)
    conf = decision.get('confirmation') or {}
    confirmed = decision['status'] == 'confirmed'
    if not confirmed or not status:
        return shown, labels['availability_basis_open'], 'proposed'
    if conf.get('basis') == 'delegated_default':
        return shown, labels['delegated'], 'delegated'
    basis = (decision.get('feature_basis') or {}).get(name)
    who = labels['availability_basis'].get(basis or 'default_from_case')
    return shown, who, 'confirmed' if basis == 'discussed' else 'stale'


def _data(view: Mapping, citer: cite.Citer, variables: list[dict],
          sample: Mapping | None) -> str:
    labels = _labels()
    ds = labels['data_section']
    parts = [f'<h2>{e(labels["sections"]["data"])}</h2>']
    facts = []
    unit = _fact_value(view, 'observation_unit')
    if unit:
        facts.append((ds['unit'], lit('case', unit['value'])))
    split_rid = citer.slot_rid('split')
    final = view.get('final_test') or {}
    language = view.get('language')
    left_out = split_rid and citer.has(split_rid, 'training_exclusions.n_rows')
    if split_rid and citer.has(split_rid, 'n_rows') and not left_out:
        dev = citer.num(split_rid, 'n_rows', 'int')
    elif final.get('development_rows') is not None:
        dev = lit('structure', cite.format_value(final['development_rows'], 'int', language))
    else:
        dev = lit('structure', cite.format_value(view['dataset']['rows'], 'int', language)
                  if isinstance(view['dataset'].get('rows'), int) else '')
    facts.append((ds['development'], dev))
    if left_out:
        # Review round 4 (E4-5): every development row, then the delayed-label rows left
        # out, then the rows the split, the fits and the selection use, each shown apart.
        facts.append((ds['development_left_out'],
                      citer.num(split_rid, 'training_exclusions.n_rows', 'int')))
        facts.append((ds['development_used'], citer.num(split_rid, 'n_rows', 'int')))
    if variables:
        facts.append((ds['columns'], lit('structure', len(variables))))
    final_rows = (cite.format_value(final['rows'], 'int', language)
                  if isinstance(final.get('rows'), int) else '')
    if final.get('status') == 'sealed':
        sealed = f'{lit("structure", final_rows)} {e(ds["final_test_sealed"])}'
    elif final.get('status') == 'opened':
        # B6c (H1): once opened, the final test is no longer sealed: say so, and say when
        # something changed after the opening.
        sealed = f'{lit("structure", final_rows)} {e(ds["final_test_opened"])}'
        if final.get('post_final_test') or final.get('changed_after'):
            sealed += f' {e(ds["final_test_changed_after"])}'
    else:
        sealed = e(ds['final_test_absent'])
    facts.append((ds.get('final_test', 'Final test'), sealed))
    target = next((v for v in variables if v.get('role') == 'target'), None)
    if target:
        facts.append((ds['target'], f'{lit("identifier", target["name"], "code")}: '
                                    f'{lit("case", target.get("description", ""))}'))
    parts.append('<dl class="facts">' + ''.join(f'<dt>{e(k)}</dt><dd>{v}</dd>'
                                                  for k, v in facts) + '</dl>')
    # the grouped dictionary
    quality = citer.slot_rid('eda.quality')
    missing_index = {}
    if quality:
        for i, m in enumerate(citer.results[quality].values.get('missing') or []):
            if isinstance(m, Mapping):
                missing_index[m.get('column')] = i
    groups: dict[str, list[dict]] = {}
    for v in variables:
        groups.setdefault(v.get('group') or ds['ungrouped'], []).append(v)
    head = ds['head']
    # WP-A9 (M6): a narrow screen scrolls the tables sideways; say so where it shows.
    parts.append(f'<p class="small scroll-hint" data-scroll-hint>{e(ds["scroll_hint"])}</p>')
    for group, items in groups.items():
        rows = []
        for v in items:
            unit_text = v.get('unit') or ''
            kind = f'{v.get("type", "")}{", " + unit_text if unit_text else ""}'
            if v.get('role') == 'feature':
                shown, who, cls = _who_decided(view, v['name'])
                stmt = v.get('availability') or {}
                case_label = labels['fact_status'].get(stmt.get('status'), stmt.get('status') or '')
                # B6c (M1): the case's own doubt stays visible when the decision overrides it.
                case_value = stmt.get('value') or 'unknown'
                decided = (view['decisions']['feature_availability'].get('value') or {})
                doubt = ''
                if isinstance(decided, dict) and \
                        decided.get(v['name']) == 'available_at_prediction' and \
                        case_value in ('uncertain', 'unknown'):
                    doubt = (f' <span class="case-doubt" data-case-availability='
                             f'"{e(case_value)}">{e(ds["case_" + case_value])}</span>')
                avail = (f'{_badge(cls, shown)}'
                         f'<br><span class="small">{e(who)}. Case: {e(case_label)}.{doubt}'
                         f'</span>')
            else:
                role = v.get('role', '')
                avail = f'<span class="small">{e(labels.get("roles", {}).get(role, role))}</span>'
            if v['name'] in missing_index:
                miss = citer.num(quality, f'missing.{missing_index[v["name"]]}.n_missing', 'int')
            else:
                miss = ''
            rows.append(f'<tr data-variable="{e(v["name"])}" '
                        f'data-feature-basis="{e(str((view["decisions"]["feature_availability"].get("feature_basis") or {}).get(v["name"], "")))}">'
                        f'<td>{lit("identifier", v["name"], "code")}</td>'
                        f'<td>{lit("case", v.get("description", ""))}</td>'
                        f'<td>{lit("case", kind)}</td><td>{miss}</td><td>{avail}</td></tr>')
        parts.append(f'<h3>{lit("case", group)}</h3><div class="scroll"><table class="dictionary">'
                     f'<thead><tr><th>{e(head["name"])}</th><th>{e(head["meaning"])}</th>'
                     f'<th>{e(head["type"])}</th><th>{e(ds["missing"])}</th>'
                     f'<th>{e(labels["availability_head"]["status"])}</th></tr></thead>'
                     f'<tbody>{"".join(rows)}</tbody></table></div>')
    # five fixed development rows
    parts.append(f'<h3>{e(ds["rows"])}</h3>')
    if sample and sample.get('rows'):
        cols = sample['columns']
        head_html = ''.join(f'<th>{lit("identifier", c)}</th>' for c in cols)
        body = ''.join('<tr>' + ''.join(f'<td>{lit("data_row", r["values"].get(c, ""))}</td>'
                                        for c in cols) + '</tr>' for r in sample['rows'])
        parts.append(f'<div class="scroll"><table class="rows"><thead><tr>{head_html}</tr>'
                     f'</thead><tbody>{body}</tbody></table></div>'
                     f'<p class="small">{e(ds["rows_note"])}</p>')
    else:
        parts.append(f'<p class="muted">{e(ds["rows_missing"])}</p>')
    return f'<section class="card" id="data">{"".join(parts)}</section>'


# --- v0.2a (WP-A6): charts -----------------------------------------------------------------

MAX_CHARTS = 7          # v0.3 (WP-J): with a distribution and the correlation matrix


def _charts(view: Mapping, citer: cite.Citer) -> str:
    labels = _labels()
    task = view.get('task') or 'binary'
    out = []

    def values(slot):
        rid = citer.slot_rid(slot)
        return (rid, citer.results[rid].values) if rid else (None, None)

    if task == 'regression':
        rid, v = values('eda.target_summary')
        if rid:
            out.append(render_charts.target_distribution(citer, rid, v))
        group_slots = sorted(s for s in view['results'] if s.startswith('eda.mean_by:'))
    else:
        rid, v = values('eda.target_rate')
        if rid:
            out.append(render_charts.target_balance(citer, rid, v))
        group_slots = sorted(s for s in view['results'] if s.startswith('eda.rate_by:'))
    for slot in group_slots[:1]:
        rid, v = values(slot)
        if rid:
            out.append(render_charts.by_group(citer, rid, v, rate=task != 'regression'))
    # v0.3 (WP-J, R17): one column's distribution, a skewed one first (its zeros apart, log
    # bins), as the study panel draws it.
    dist = []
    for slot in sorted(s for s in view['results'] if s.startswith('eda.distribution:')):
        rid, v = values(slot)
        if rid and isinstance(v, Mapping):
            dist.append((not (v.get('numeric') or {}).get('skewed'), slot, rid, v))
    for _, _, rid, v in sorted(dist, key=lambda d: d[:2])[:1]:
        out.append(render_charts.distribution(citer, rid, v))
    # v0.3 (WP-J, R28): the predictor correlation matrix with its collinearity flags.
    rid, v = values('eda.correlation')
    if rid:
        out.append(render_charts.correlation(citer, rid, v))
    rid, v = values('eda.single_feature_signal')
    if rid:
        out.append(render_charts.signal(citer, rid, v))
    if task == 'regression':
        rid, v = values('evaluate.regression')
        if rid:
            out.append(render_charts.residuals(citer, rid, v))
            out.append(render_charts.residuals_by(citer, rid, v))
    else:
        rid, v = values('policy.evaluation')
        if rid:
            model = (view.get('criterion') or {}).get('model') or 'fit.logistic'
            out.append(render_charts.selection(citer, rid, v, rule_words, model))
    figures = [f for f in out if f][:MAX_CHARTS]
    body = ''.join(figures) if figures else f'<p class="muted">{e(labels["charts_none"])}</p>'
    return (f'<section class="card charts" id="charts"><h2>{e(labels["sections"]["charts"])}'
            f'</h2><p>{e(labels["charts_intro"])}</p>{body}</section>')


def _looks(view: Mapping) -> str:
    looks = view.get('eda_looks') or {}
    if not looks:
        return ''
    labels = _labels()['looks']
    count = looks.get('target_looks') or 0
    by = looks.get('by_activity') or {}
    items = ''.join(f'<li>{lit("identifier", texts.activity(a).get("label", a))}: '
                    f'{lit("structure", n)}</li>' for a, n in sorted(by.items()))
    return (f'<details class="ledger" data-looks="{e(str(count))}"><summary>'
            f'{e(labels["summary"])}: {lit("structure", count)} {e(labels["count"])}</summary>'
            f'<p class="small">{e(labels["note"])}</p><ul>{items}</ul></details>')


# --- page -------------------------------------------------------------------------------

def build(view: Mapping, *, surfaces: Mapping | None = None,
          variables: list[dict] | None = None,
          sample: Mapping | None = None,
          understanding: str = '') -> tuple[str, list[str]]:
    """``(html, consumed result ids)`` of the report for ``view``.

    ``surfaces`` gives the status of each deliverable for the revision banner; the
    report itself is described as written at this revision. ``variables`` is the case
    variable dictionary (for the data section and the availability table). ``sample``
    holds the five fixed development rows of the data section (``{columns, rows}``, read
    by :mod:`mlkit.study.cmd_render`). Raises ``untraceable_number`` when a cited number
    cannot be traced.

    Order (v0.2a, WP-A6): the verdict card, the objective, the data, the charts, the
    plan, the decisions, the evidence by step, the comparison, the limits, the case
    statements, the surfaces, and the annex (collapsed). ``understanding`` (ADR 0008) is the
    separate section of the understanding review, already escaped
    (:func:`mlkit.study.understanding.render.section`); empty when the review was never
    enabled, so such a report is unchanged.
    """
    with texts.study_context(view), texts.report_language_context(view.get('language')):
        return _build(view, surfaces=surfaces, variables=variables, sample=sample,
                      understanding=understanding)


def _build(view: Mapping, *, surfaces: Mapping | None, variables: list[dict] | None,
           sample: Mapping | None = None, understanding: str = '') -> tuple[str, list[str]]:
    labels = _labels()
    citer = cite.Citer.from_view(view)
    surfaces = dict(surfaces or {})
    surfaces.setdefault('report', {'status': 'ok', 'revision': view['revision']})
    comparison = (_model_comparison(view, citer) if view.get('task') == 'regression'
                  else _policy(view, citer))
    body = ''.join([
        _verdict(view, citer), _objective(view), _data(view, citer, variables or [], sample),
        _charts(view, citer), _plan(view), _decisions(view, variables or []),
        _evidence(view, citer), comparison, render_trials.section(view, citer),
        render_diagnostics.section(view, citer),
        _not_yet_defensible(view), understanding, _facts(view), _history(view),
        _surfaces(view, surfaces), _annex(view, citer)])

    consumed = sorted({c['result_id'] for c in citer.cited})
    snapshot_json = json.dumps(view.get('presentation'), sort_keys=True,
                               separators=(',', ':'), ensure_ascii=False).replace('<', '\\u003c')
    case = view['case']
    page = (
        f'<!doctype html>\n<html lang="{e(view.get("language", "en"))}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta name="hypotrail-revision" content="{view["revision"]}">'
        f'<meta name="hypotrail-template-version" content="{TEMPLATE_VERSION}">'
        f'<title>{e(labels["title"])}</title><style>{_css()}</style></head>\n'
        f'<body class="report" data-revision="{view["revision"]}">{BANNER_START}{BANNER_END}\n'
        f'<header><span class="brand">Hypotrail</span>'
        f'<span>{e(labels["title"])} · {lit("case", case.get("id", ""))}</span>'
        f'<button type="button" data-theme-toggle aria-pressed="false">{e(labels["theme_toggle"])}</button>'
        f'</header>\n<main><p class="lead">{e(labels["subtitle"])}</p>{body}</main>\n'
        f'<footer class="page-footer">{e(labels["generated_by_for_revision"])} '
        f'{lit("revision", view["revision"])}. {e(labels["no_controls"])}</footer>\n'
        f'<script type="application/json" id="hypotrail-presentation">{snapshot_json}</script>'
        f'<script>{THEME_SCRIPT}\n{ANCHOR_SCRIPT}</script></body></html>\n')
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
