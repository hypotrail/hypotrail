"""Human pages: a cockpit and one dossier per decision. Deterministic, generated from the records.

    python -m mlkit.render          # writes reports/index.html and every dossier that has data

Pages (lot 1):
    reports/index.html            cockpit: phases, decisions waiting, budgets, last runs, checks
    reports/questions.html        phase questionnaire: answers -> YAML block for answers.yaml
    reports/data.html             data dossier: signals per column, all columns, selection (bivariate)
    reports/stop-<id>.html        one dossier per stop: facts first, agent texts after, decision form

Rules:
- no agent writes these pages (the guard refuses it): they are a view over JSON/YAML records;
- facts come before any agent-written text, which is boxed and labelled;
- every page carries the hashes of the state it shows; the cockpit marks stale pages;
- forms never write anything: they produce the text a PERSON pastes, downloads and commits;
- one self-contained file per page: no network, inline SVG, light/dark, printable.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

from . import config, core, gate

# ============================================================== page shell
CSS = r"""
:root{color-scheme:light;--bg:#f7f6f3;--surface:#fff;--surface-2:#f0efec;--ink:#0b0b0b;--ink-2:#52514e;--muted:#7d7c77;
--line:#e2e0da;--accent:#2a78d6;--series:#2a78d6;--ref:#9a9993;--good:#0ca30c;--warn:#b77a00;--warn-bg:#fdf3dc;--serious:#c4562c;
--crit:#d03b3b;--crit-bg:#fbe9e8;--good-bg:#e6f4e6;--seq0:#cde2fb;--seq1:#104281}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--bg:#121211;--surface:#1a1a19;--surface-2:#242422;
--ink:#f0efec;--ink-2:#c3c2b7;--muted:#8f8e86;--line:#34342f;--accent:#3987e5;--series:#3987e5;--ref:#77766f;--warn:#fab219;
--warn-bg:#3a2f12;--serious:#ec835a;--crit:#e66767;--crit-bg:#3d1f1f;--good-bg:#173317;--seq0:#1c2b3d;--seq1:#86b6ef}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121211;--surface:#1a1a19;--surface-2:#242422;--ink:#f0efec;--ink-2:#c3c2b7;
--muted:#8f8e86;--line:#34342f;--accent:#3987e5;--series:#3987e5;--ref:#77766f;--warn:#fab219;--warn-bg:#3a2f12;--serious:#ec835a;
--crit:#e66767;--crit-bg:#3d1f1f;--good-bg:#173317;--seq0:#1c2b3d;--seq1:#86b6ef}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:var(--accent)}
code,.mono{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.88em}
header.top{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--line)}
header.top .in{max-width:1120px;margin:0 auto;padding:10px 20px;display:flex;gap:18px;align-items:center;flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.02em}
.brand small{font-weight:400;color:var(--muted);margin-left:6px}
nav.main{display:flex;gap:4px;flex-wrap:wrap;flex:1}
nav.main a{text-decoration:none;color:var(--ink-2);padding:5px 10px;border-radius:6px}
nav.main a.on{background:var(--surface-2);color:var(--ink);font-weight:600}
button,.btn{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:7px;padding:6px 12px}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
main{max-width:1120px;margin:0 auto;padding:24px 20px 60px}
h1{font-family:"Iowan Old Style",Charter,Georgia,serif;font-size:30px;line-height:1.2;margin:4px 0 6px;font-weight:600}
h2{font-size:19px;margin:34px 0 10px}
h3{font-size:16px;margin:0 0 6px}
.lede{color:var(--ink-2);max-width:760px;margin:0 0 18px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.grid{display:grid;gap:12px}
.g2{grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
.g4{grid-template-columns:repeat(auto-fit,minmax(170px,1fr))}
.kpi .v{font-size:26px;font-weight:650;font-variant-numeric:tabular-nums}
.kpi .l{color:var(--muted);font-size:13px}
.decision{border-left:5px solid var(--accent);background:var(--surface);border-radius:10px;padding:16px 18px;margin:8px 0 18px;border-top:1px solid var(--line);border-right:1px solid var(--line);border-bottom:1px solid var(--line)}
.decision .tag{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:700}
.decision ul{margin:8px 0;padding-left:20px}
.agent{border:1.5px dashed var(--line);border-radius:10px;padding:12px 14px;margin:10px 0;background:var(--surface-2)}
.agent .who{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:var(--serious);font-weight:700;margin-bottom:6px}
.agent pre{white-space:pre-wrap;margin:0;font:13px/1.5 ui-monospace,Menlo,monospace;color:var(--ink-2)}
.chip{display:inline-flex;gap:5px;align-items:center;font-size:12.5px;padding:2px 8px;border-radius:999px;background:var(--surface-2);color:var(--ink-2);margin:2px 4px 2px 0}
.chip.crit{background:var(--crit-bg);color:var(--crit)}
.chip.warn{background:var(--warn-bg);color:var(--warn)}
.chip.good{background:var(--good-bg);color:var(--good)}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}
.phases{display:grid;grid-template-columns:repeat(8,1fr);gap:4px;margin:10px 0 4px}
.phase{padding:8px 8px 7px;border-radius:8px;background:var(--surface);border:1px solid var(--line);font-size:12.5px;min-width:0}
.phase b{display:block;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.phase.done{border-color:var(--good);background:var(--good-bg)}
.phase.cur{border:2px solid var(--accent)}
.todo{display:flex;gap:14px;align-items:flex-start;padding:12px 0;border-bottom:1px solid var(--line)}
.todo:last-child{border-bottom:0}
.todo .ic{flex:0 0 34px;height:34px;border-radius:9px;display:grid;place-items:center;font-weight:700;background:var(--surface-2)}
.todo .ic.crit{background:var(--crit-bg);color:var(--crit)}
.todo .ic.warn{background:var(--warn-bg);color:var(--warn)}
.todo .t{flex:1}
.todo .meta{color:var(--muted);font-size:13px}
.meter{height:10px;border-radius:5px;background:var(--surface-2);overflow:hidden;margin:6px 0 2px}
.meter i{display:block;height:100%;background:var(--series);border-radius:5px}
.meter.warn i{background:var(--warn)} .meter.crit i{background:var(--crit)}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:18px 0 8px;flex-wrap:wrap}
.tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;background:none;padding:8px 12px;color:var(--ink-2)}
.tabs button.on{border-bottom-color:var(--accent);color:var(--ink);font-weight:600}
.pane{display:none}.pane.on{display:block}
.q{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:10px 0}
.q .id{font-size:12px;color:var(--muted)}
.q .why{color:var(--ink-2);font-size:13.5px;margin:6px 0 2px}
.q .cons{color:var(--muted);font-size:13px}
.q.answered{opacity:.78}
textarea,input[type=text],select{width:100%;font:inherit;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
textarea{min-height:64px;resize:vertical}
.out{min-height:140px;font:12.5px/1.45 ui-monospace,Menlo,monospace}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0}
.ex{font-size:13px;color:var(--ink-2);background:var(--surface-2);border-radius:8px;padding:8px 10px;margin:8px 0}
.hint{font-size:13px;color:var(--muted)}
svg text{fill:var(--muted);font:11px system-ui,sans-serif}
svg .ax{stroke:var(--line)} svg .s{stroke:var(--series);fill:none;stroke-width:2}
svg .dot{fill:var(--series);stroke:var(--surface);stroke-width:2}
svg .refl{stroke:var(--ref);stroke-dasharray:4 4;stroke-width:1.5}
svg .bar{fill:var(--series)} svg .bar.warn{fill:var(--warn)} svg .bar.crit{fill:var(--crit)}
svg .band{fill:var(--surface-2)} svg .tick{stroke:var(--ink);stroke-width:2}
.hbar{display:flex;align-items:center;gap:8px;font-size:12.5px;margin:2px 0}
.hbar span.lab{flex:0 0 120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink-2)}
.hbar span.trk{flex:1;height:8px;background:var(--surface-2);border-radius:4px;overflow:hidden}
.hbar span.trk i{display:block;height:100%;background:var(--series)}
.hbar span.val{flex:0 0 46px;text-align:right;font-variant-numeric:tabular-nums;color:var(--muted)}
.ok{color:var(--good);font-weight:700}.ko{color:var(--crit);font-weight:700}
footer{max-width:1120px;margin:0 auto;padding:0 20px 30px;color:var(--muted);font-size:12.5px}
.stale{background:var(--warn-bg);color:var(--warn);padding:8px 12px;border-radius:8px;margin:8px 0;font-size:13.5px}
@media (max-width:720px){.phases{grid-template-columns:repeat(4,1fr)}h1{font-size:24px}main{padding:16px}}
@media print{header.top,.noprint,form .row button{display:none}body{background:#fff}.pane{display:block}}
"""

JS = r"""
(function(){
  var root=document.documentElement;
  function get(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function set(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  var t=get('osml-theme'); if(t) root.setAttribute('data-theme',t);
  window.osmlTheme=function(){
    var dark=root.getAttribute('data-theme')==='dark'||(!root.getAttribute('data-theme')&&matchMedia('(prefers-color-scheme: dark)').matches);
    var n=dark?'light':'dark'; root.setAttribute('data-theme',n); set('osml-theme',n);
  };
  window.osmlTab=function(group,name){
    document.querySelectorAll('[data-tabs="'+group+'"] button').forEach(function(b){b.classList.toggle('on',b.dataset.t===name)});
    document.querySelectorAll('[data-pane="'+group+'"]').forEach(function(p){p.classList.toggle('on',p.dataset.t===name)});
    if(history.replaceState) history.replaceState(null,'','#'+name);
  };
  window.osmlCopy=function(id){var el=document.getElementById(id); el.select();
    if(navigator.clipboard){navigator.clipboard.writeText(el.value)} else {document.execCommand('copy')}};
  window.osmlDownload=function(id,name){var b=new Blob([document.getElementById(id).value],{type:'text/plain'});
    var a=document.createElement('a'); a.href=URL.createObjectURL(b); a.download=name; a.click();};
  window.osmlDraft=function(key){
    document.querySelectorAll('[data-draft]').forEach(function(el){
      var k=key+':'+el.dataset.draft, v=get(k); if(v!==null && !el.value) el.value=v;
      el.addEventListener('input',function(){set(k,el.value)});
    });
  };
  window.yq=function(s){return JSON.stringify(String(s).trim())};
  window.today=function(){return new Date().toISOString().slice(0,10)};
  document.addEventListener('DOMContentLoaded',function(){
    var h=location.hash.slice(1); if(h){var b=document.querySelector('[data-tabs] button[data-t="'+h+'"]'); if(b) b.click();}
  });
})();
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def fmt(x, pat="{:.3f}") -> str:
    return "—" if x is None else pat.format(x)


def state_hashes() -> dict:
    h = {"frame": config.frame_hash()}
    try:
        h["data"] = "-".join(config.sha256_file(p) for p in core.dev_files())
    except FileNotFoundError:
        h["data"] = None
    return h


def page(title: str, active: str, body: str, state: dict, extra_js: str = "") -> str:
    project = esc(config.load_frame().get("project", ""))
    links = [("index", "Cockpit", "index.html"), ("questions", "Questions", "questions.html"), ("data", "Data", "data.html")]
    stops = sorted(config.STOPS_DIR.glob("STOP-*.json")) if config.STOPS_DIR.exists() else []
    if stops:
        links.append(("stop", f"Stops ({len(stops)})", f"stop-{stops[-1].stem}.html"))
    nav = "".join(f'<a class="{"on" if k == active else ""}" href="{href}">{esc(lab)}</a>' for k, lab, href in links)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    meta = " · ".join(f"{k} <span class='mono'>{esc(v)}</span>" for k, v in state.items() if v)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><style>{CSS}</style><script>{JS}</script></head><body>
<header class="top"><div class="in"><span class="brand">Hypotrail-ML<small>{project}</small></span><nav class="main">{nav}</nav>
<button class="noprint" onclick="osmlTheme()" aria-label="Toggle light / dark">◐ Theme</button></div></header>
<main>{body}</main>
<footer>Page generated by <code>python -m mlkit.render</code> on {now} · state : {meta}.<br>
This page is a view. Repository files are authoritative; forms only produce text for you to paste and commit.</footer>
<script>{extra_js}</script></body></html>"""


def write(name: str, content: str) -> None:
    config.REPORTS_DIR.mkdir(exist_ok=True)
    from .presentation import polish
    (config.REPORTS_DIR / name).write_text(polish(content), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def next_decision_id() -> str:
    p = config.ROOT / "decisions.md"
    ids = [int(x) for x in re.findall(r"\bD-(\d{3})\b", p.read_text(encoding="utf-8"))] if p.exists() else []
    return f"D-{(max(ids) + 1 if ids else 1):03d}"


# ============================================================== small charts (inline SVG)
def line_chart(labels, values, w=720, h=210, pct=True, bands=(), vline=None, title=""):
    if not values:
        return ""
    ml, mr, mt, mb = 46, 12, 14, 26
    pw, ph = w - ml - mr, h - mt - mb
    top = max(v for v in values if v is not None) * 1.15 or 1
    n = len(values)
    x = lambda i: ml + (pw * i / max(n - 1, 1))
    y = lambda v: mt + ph - ph * v / top
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="{esc(title)}">']
    for (i0, i1, lab) in bands:
        out.append(f'<rect class="band" x="{x(i0) - 2:.1f}" y="{mt}" width="{x(i1) - x(i0) + 4:.1f}" height="{ph}"/>'
                   f'<text x="{x(i0):.1f}" y="{mt + 11}">{esc(lab)}</text>')
    for k in range(5):
        v = top * k / 4
        out.append(f'<line class="ax" x1="{ml}" x2="{w - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                   f'<text x="{ml - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{(f"{v:.0%}" if pct else f"{v:.2g}")}</text>')
    step = max(1, n // 10)
    for i, lab in enumerate(labels):
        if i % step == 0 or str(lab).endswith("-01"):
            if i % step == 0:
                out.append(f'<text x="{x(i):.1f}" y="{h - 6}" text-anchor="middle">{esc(lab)}</text>')
    if vline is not None:
        i, lab = vline
        out.append(f'<line class="refl" x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{mt}" y2="{mt + ph}"/>'
                   f'<text x="{x(i) + 4:.1f}" y="{mt + ph - 4}">{esc(lab)}</text>')
    pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(values) if v is not None)
    out.append(f'<polyline class="s" points="{pts}"/>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        if v is not None:
            out.append(f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="7" fill="transparent"><title>{esc(lab)} : {v:.2%}</title></circle>')
    return "".join(out) + "</svg>"


def hist_svg(hist: dict, w=280, h=70) -> str:
    if not hist:
        return ""
    if hist.get("kind") == "cat":
        rows = list(hist["top"].items())[:6]
        mx = max(v for _, v in rows) if rows else 1
        out = "".join(f'<div class="hbar"><span class="lab" title="{esc(k)}">{esc(k)}</span><span class="trk"><i style="width:{100 * v / mx:.0f}%"></i></span>'
                      f'<span class="val">{v:.0%}</span></div>' for k, v in rows)
        return out + (f'<div class="hint">+ {len(hist["top"]) - 6} other categories displayed in JSON</div>' if len(hist["top"]) > 6 else "")
    counts, edges = hist["counts"], hist["edges"]
    mx = max(counts) or 1
    bw = w / len(counts)
    bars = "".join(f'<rect class="bar" x="{i * bw + 1:.1f}" y="{h - 14 - (h - 18) * c / mx:.1f}" width="{max(bw - 2, 1):.1f}" '
                   f'height="{(h - 18) * c / mx:.1f}" rx="2"><title>{edges[i]:.4g} – {edges[i + 1]:.4g} : {c:,}</title></rect>'
                   for i, c in enumerate(counts))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">{bars}'
            f'<text x="0" y="{h - 2}">{edges[0]:.4g}</text><text x="{w}" y="{h - 2}" text-anchor="end">{edges[-1]:.4g}</text></svg>'
            + (f'<div class="hint">outside p1–p99 : {hist["below"]:,} under, {hist["above"]:,} au-dessus</div>' if hist.get("below") or hist.get("above") else ""))


def strip_svg(by_month: dict, months: list, w=280, h=16) -> str:
    if not by_month:
        return ""
    cw = w / max(len(months), 1)
    cells = []
    for i, m in enumerate(months):
        v = by_month.get(m)
        if v is None:
            continue
        cells.append(f'<rect x="{i * cw:.1f}" y="0" width="{max(cw - .5, .5):.1f}" height="{h}" fill="var(--crit)" '
                     f'fill-opacity="{0.06 + 0.94 * min(v, 1):.2f}"><title>{m} : {v:.1%} missing</title></rect>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">{"".join(cells)}</svg>'


def psi_bars(per_window: dict, warn: float, stop: float, w=200, h=46) -> str:
    if not per_window:
        return ""
    vals = list(per_window.items())
    top = max(max(v for _, v in vals), stop * 1.3)
    bw = w / len(vals)
    out = [f'<svg viewBox="0 0 {w} {h + 14}" width="100%" style="max-width:{w}px">']
    ys = h - h * stop / top
    out.append(f'<line class="refl" x1="0" x2="{w}" y1="{ys:.1f}" y2="{ys:.1f}"><title>stop threshold {stop}</title></line>')
    for i, (name, v) in enumerate(vals):
        cls = "crit" if v > stop else "warn" if v > warn else ""
        out.append(f'<rect class="bar {cls}" x="{i * bw + 4:.1f}" y="{h - h * v / top:.1f}" width="{bw - 8:.1f}" height="{max(h * v / top, 1):.1f}" rx="3">'
                   f'<title>{esc(name)} : PSI {v:.3f}</title></rect><text x="{i * bw + bw / 2:.1f}" y="{h + 12}" text-anchor="middle">{esc(name)}</text>')
    return "".join(out) + "</svg>"


def iv_bar(iv: float, floor: float, top: float, w=170, h=14) -> str:
    sx = lambda v: w * min(v / top, 1)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}"><rect class="band" x="0" y="2" width="{w}" height="{h - 4}" rx="3"/>'
            f'<rect class="bar" x="0" y="2" width="{max(sx(iv), 1):.1f}" height="{h - 4}" rx="3"><title>IV {iv:.3f}</title></rect>'
            f'<line class="tick" x1="{sx(floor):.1f}" x2="{sx(floor):.1f}" y1="0" y2="{h}"><title>floor du chance {floor:.3f}</title></line></svg>')


def band_svg(bands: list, overall: float, w=280, h=90) -> str:
    rows = [b for b in bands if b["bad_rate"] is not None]
    if not rows:
        return ""
    top = max(max(b["bad_rate"] for b in rows), overall) * 1.2 or 1
    n = len(rows)
    bw = w / n
    y = lambda v: h - 16 - (h - 22) * v / top
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">',
           f'<line class="refl" x1="0" x2="{w}" y1="{y(overall):.1f}" y2="{y(overall):.1f}"><title>taux moyen {overall:.1%}</title></line>']
    for i, b in enumerate(rows):
        miss = b["band"] == "missing"
        out.append(f'<rect class="bar{" warn" if miss else ""}" x="{i * bw + 1:.1f}" y="{y(b["bad_rate"]):.1f}" width="{max(bw - 2, 1):.1f}" '
                   f'height="{h - 16 - y(b["bad_rate"]):.1f}" rx="2"><title>{esc(b["band"])} : {b["bad_rate"]:.1%} default rate over {b["n"]:,} loans</title></rect>')
    out.append(f'<text x="0" y="{h - 3}">{esc(rows[0]["band"])[:18]}</text><text x="{w}" y="{h - 3}" text-anchor="end">{esc(rows[-1]["band"])[:18]}</text>')
    return "".join(out) + "</svg>"


def gain_svg(runs: list, current: str, threshold, w=720, h=230) -> str:
    pts = [(r["run_id"], r["gain"]["mean"], r["gain"]["std"], r.get("conclusive")) for r in runs if r.get("gain")]
    if not pts:
        return ""
    ml, mr, mt, mb = 56, 12, 14, 26
    pw, ph = w - ml - mr, h - mt - mb
    hi = max([m + s for _, m, s, _ in pts] + [threshold or 0, 0.001])
    lo = min([m - s for _, m, s, _ in pts] + [0])
    span = hi - lo or 1
    hi, lo = hi + .08 * span, lo - .08 * span
    n = len(pts)
    x = lambda i: ml + pw * (i + .5) / n
    y = lambda v: mt + ph * (hi - v) / (hi - lo)
    out = [f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="gain of each run over the reference">']
    for k in range(5):
        v = lo + (hi - lo) * k / 4
        out.append(f'<line class="ax" x1="{ml}" x2="{w - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}"/><text x="{ml - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{v:+.4f}</text>')
    out.append(f'<line x1="{ml}" x2="{w - mr}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="var(--ink-2)" stroke-width="1"/>')
    if threshold is not None:
        out.append(f'<line class="refl" x1="{ml}" x2="{w - mr}" y1="{y(threshold):.1f}" y2="{y(threshold):.1f}" style="stroke:var(--crit)"/>'
                   f'<text x="{w - mr}" y="{y(threshold) - 5:.1f}" text-anchor="end">threshold « too beau » {threshold:+.3f}</text>')
    step = max(1, n // 12)
    for i, (rid, m, s, concl) in enumerate(pts):
        cur = rid == current
        col = "var(--crit)" if cur else "var(--series)"
        out.append(f'<line x1="{x(i):.1f}" x2="{x(i):.1f}" y1="{y(m + s):.1f}" y2="{y(m - s):.1f}" stroke="{col}" stroke-width="1.5" opacity=".6"/>')
        out.append(f'<circle cx="{x(i):.1f}" cy="{y(m):.1f}" r="{7 if cur else 5}" fill="{col if concl else "var(--surface)"}" stroke="{col}" stroke-width="2">'
                   f'<title>{rid} : gain {m:+.4f} ± {s:.4f}{" · conclusive" if concl else ""}</title></circle>')
        if i % step == 0 or cur:
            style = ' style="fill:var(--crit);font-weight:700"' if cur else ""
            out.append(f'<text x="{x(i):.1f}" y="{h - 6}" text-anchor="middle"{style}>{esc(rid)}</text>')
    return "".join(out) + "</svg>"


# ============================================================== shared state
def load_state() -> dict:
    frame = config.load_frame()
    fhash = config.frame_hash()
    questions, answers, proposed = gate.load()
    runs = config.read_jsonl(config.REGISTRY_FILE)
    ledger = config.read_jsonl(config.LEDGER_FILE)
    stops = []
    if config.STOPS_DIR.exists():
        for p in sorted(config.STOPS_DIR.glob("STOP-*.json")):
            s = json.loads(p.read_text(encoding="utf-8"))
            d = config.STOPS_DIR / f"{p.stem}.decision.md"
            s["decided"] = d.exists()
            s["decision_text"] = d.read_text(encoding="utf-8") if d.exists() else ""
            stops.append(s)
    return {"frame": frame, "fhash": fhash, "spec": frame["spec"], "questions": questions, "answers": answers,
            "proposed": proposed, "runs": runs, "cur_runs": [r for r in runs if r["frame_hash"] == fhash],
            "ledger": [e for e in ledger if e["frame_hash"] == fhash], "stops": stops,
            "profile": read_json(config.REPORTS_DIR / "data_profile.json"),
            "bivariate": read_json(config.REPORTS_DIR / "bivariate.json"),
            "registry": config.load_features(), "hashes": state_hashes(),
            "decisions": (config.ROOT / "decisions.md").read_text(encoding="utf-8") if (config.ROOT / "decisions.md").exists() else ""}


def structural_checks() -> list[tuple[str, bool, str]]:
    from . import checks
    checks.RESULTS.clear()
    frame, registry, fhash = config.load_frame(), config.load_features(), config.frame_hash()
    runs, ledger = config.read_jsonl(config.REGISTRY_FILE), config.read_jsonl(config.LEDGER_FILE)
    for fn, args in [(checks.i1_frame_coverage, (frame,)), (checks.i2_metrics_declared, (frame, runs, fhash)),
                     (checks.i3_provenance, (runs, ledger, fhash)), (checks.i5_pipelines, (registry,)),
                     (checks.i6_budget, (frame, ledger, fhash)), (checks.i8_open_stops, ()), (checks.i9_selection, (frame,)),
                     (checks.d3_registry_semantics, (registry,)), (checks.e1_evaluation, (ledger, fhash)),
                     (checks.g1_gates, (runs, ledger, fhash))]:
        try:
            fn(*args)
        except Exception as exc:                       # a broken check must show, not hide the page
            checks.report(fn.__name__, False, f"error: {exc}")
    return list(checks.RESULTS)


def usable(registry: dict, col: str) -> bool:
    e = registry.get(col) or {}
    return e.get("available") == "origination" and not e.get("excluded_by")


def unresolved_signals(st: dict) -> list[str]:
    prof = st["profile"]
    if not prof:
        return []
    out = []
    for c, s in prof["columns"].items():
        e = st["registry"].get(c)
        if e is None or (usable(st["registry"], c) and s["flags"] and not (e.get("drift_ack") or e.get("leak_ack"))):
            out.append(c)
    return out


def selection_pending(st: dict) -> bool:
    b = st["bivariate"]
    return bool(b) and b["sel_id"] not in st["decisions"]


# ============================================================== cockpit
NOTHING = '<p class="hint">No decision pending. The agent may continue (<code>/next</code>).</p>'


def state_txt(s: dict) -> str:
    return "✓ complete" if s["complete"] else f"{len(s['missing'])} to resolve"


def render_index(st: dict) -> str:
    phases_def = config.load_yaml(gate.QUESTIONS_FILE)["phases"]
    statuses = [gate.phase_status(p, st["questions"], st["answers"], st["proposed"]) for p in gate.PHASES]
    first_open = next((s for s in statuses if not s["complete"]), None)
    cells = []
    for s in statuses:
        cls = "done" if s["complete"] else ("cur" if s is first_open else "")
        cells.append(f'<a class="phase {cls}" href="questions.html#{s["phase"]}" style="text-decoration:none;color:inherit">'
                     f'<b>{esc(s["phase"])}</b>{state_txt(s)}</a>')

    todos = []
    for s in st["stops"]:
        if not s["decided"]:
            todos.append(("crit", "!", f'Stop <code>{esc(s["stop_id"])}</code> : {esc("; ".join(s["triggers"]))}',
                          "No run is allowed until this is resolved.", "5 to 10 min", f'stop-{s["stop_id"]}.html'))
    if first_open:
        n = len(first_open["missing"])
        todos.append(("warn", "?", f'{n} question(s) blocking(s), phase <b>{esc(first_open["phase"])}</b> — {esc(phases_def[first_open["phase"]])}',
                      "Bloque : " + ", ".join(c for c in gate.PHASE_GATES if first_open["phase"] in gate.PHASE_GATES[c]),
                      f"{2 * n} to {4 * n} min", f'questions.html#{first_open["phase"]}'))
    sig = unresolved_signals(st)
    if sig:
        todos.append(("warn", "D", f"{len(sig)} usable columns with an unresolved signal: {esc(', '.join(sig[:6]))}{' …' if len(sig) > 6 else ''}",
                      "Runs remain available, but D4/D6 fail if these columns are used without justification.",
                      f"{2 * len(sig)} min", "data.html#signals"))
    if selection_pending(st):
        b = st["bivariate"]
        dropped = sum(1 for r in b["columns"].values() if r["verdict"] != "retained")
        todos.append(("warn", "S", f"Ratify selection <code>{esc(b['sel_id'])}</code> : {dropped} exclusion(s) proposed(s)",
                      "Until ratified, these exclusions remain proposals.", "10 min", "data.html#selection"))
    if not st["profile"]:
        todos.append(("", "→", "No data profile: ask the data-analyst agent to run <code>python -m mlkit.profile</code>",
                      "The data report will be generated afterwards.", "—", None))

    def todo_html(t):
        cls, ic, text, meta, dur, href = t
        link = f' <a href="{href}">open the report →</a>' if href else ""
        return (f'<div class="todo"><div class="ic {cls}">{ic}</div><div class="t">{text}{link}'
                f'<div class="meta">{esc(meta)} · estimated time: {esc(dur)}</div></div></div>')

    spec = st["spec"]
    explo = [r for r in st["cur_runs"] if r["status"] == "exploratory"]
    comps = sum(r.get("n_candidates", 1) for r in explo)
    budget = spec.get("exploration_budget") or 0
    hb = spec["holdout"]["budget"]

    def meter(v, tot, label):
        share = v / tot if tot else 0
        cls = "crit" if share >= 1 else "warn" if share >= .75 else ""
        return (f'<div class="card kpi"><div class="l">{label}</div><div class="v">{v} <span class="hint">/ {tot}</span></div>'
                f'<div class="meter {cls}"><i style="width:{min(share, 1) * 100:.0f}%"></i></div></div>')

    guard_log = config.ROOT / ".osml" / "guard.log"
    refusals = sum(1 for _ in open(guard_log, encoding="utf-8")) if guard_log.exists() else 0
    kpis = (meter(comps, budget, "Comparisons (exploration budget)") + meter(config.n_readings(config.readings_of_current_holdout(config.read_jsonl(config.LEDGER_FILE))), hb, "Readings of the current holdout") +
            f'<div class="card kpi"><div class="l">Runs exploratory · concluants</div><div class="v">{len(explo)} · {sum(1 for r in explo if r.get("conclusive"))}</div></div>'
            f'<div class="card kpi"><div class="l">Stops · refus du garde</div><div class="v">{len(st["stops"])} · {refusals}</div></div>')

    p = spec["metric_primary"]
    def run_flags(r):
        out = '<span class="chip">conclusive</span>' if r.get("conclusive") else ""
        out += '<span class="chip crit">stop</span>' if r.get("triggers") else ""
        return out + ('<span class="chip crit">refused</span>' if r["status"] == "rejected" else "")

    rows = "".join(
        f'<tr><td class="mono">{esc(r["run_id"])}</td><td>{esc(r["status"])}</td><td class="mono">{esc(r["pipeline"])}</td>'
        f'<td class="n">{fmt(r.get("summary", {}).get(p, {}).get("mean"), "{:.4f}")}</td>'
        f'<td class="n">{fmt((r.get("gain") or {}).get("mean"), "{:+.4f}")}</td><td>{run_flags(r)}</td></tr>'
        for r in reversed(st["cur_runs"][-12:]))
    runs_html = (f'<div class="card scroll"><table><tr><th>run</th><th>status</th><th>pipeline</th><th class="n">{esc(p)}</th><th class="n">gain</th><th></th></tr>{rows}</table></div>'
                 if rows else '<p class="hint">No run under this frame.</p>')

    checks_html = "".join(f'<tr><td>{"<span class=ok>✓</span>" if ok else "<span class=ko>✗</span>"}</td><td>{esc(c)}</td><td>{esc(d)}</td></tr>'
                          for c, ok, d in structural_checks())
    stale = []
    for name, obj in (("data profile (data.html)", st["profile"]), ("bivariate analysis", st["bivariate"])):
        if obj and (obj.get("frame_hash") != st["fhash"] or obj.get("data_hash") != st["hashes"].get("data")):
            stale.append(name)
    stale_html = "".join(f'<div class="stale">⚠ {esc(n)}: calculated on another state (frame or data changed); regenerate.</div>' for n in stale)

    examples = ('<div class="stale">⚠ OSML_ACCEPT_EXAMPLES=1 treats example answers as human answers. '
                'For synthetic-data rehearsal only.</div>') if gate.accept_examples() else ""
    body = f"""<h1>Cockpit</h1>{examples}<p class="lede">What the project needs from you, in order. The agent works until a gate, stop, or escalation; decisions are made here.</p>
<div class="phases">{''.join(cells)}</div>{stale_html}
<h2>Pending decisions ({sum(1 for t in todos if t[5])})</h2><div class="card">{''.join(todo_html(t) for t in todos) or NOTHING}</div>
<h2>Exploration</h2><div class="grid g4">{kpis}</div>
<h2>Derniers runs</h2>{runs_html}
<h2>Structural checks</h2><div class="card scroll"><table>{checks_html}</table>
<p class="hint">Data checks (<code>python -m mlkit.checks --data</code>) are not recalculated here.</p></div>"""
    return page("Cockpit · Hypotrail-ML", "index", body, {"frame": st["fhash"], "data": st["hashes"].get("data")})


# ============================================================== questionnaire
def render_questions(st: dict) -> str:
    phases_def = config.load_yaml(gate.QUESTIONS_FILE)["phases"]
    tabs, panes = [], []
    first_open = None
    for ph in gate.PHASES:
        s = gate.phase_status(ph, st["questions"], st["answers"], st["proposed"])
        if not s["complete"] and first_open is None:
            first_open = ph
        mark = "✓" if s["complete"] else str(len(s["missing"]))
        tabs.append(f'<button data-t="{ph}" onclick="osmlTab(\'ph\',\'{ph}\')">{esc(ph)} <span class="chip">{mark}</span></button>')
        cards = []
        for q in [q for q in st["questions"] if q["phase"] == ph]:
            a = st["answers"].get(q["id"]) or {}
            human = a.get("by") == "HUMAN" and str(a.get("answer", "")).strip()
            status = ("<span class='chip good'>human answer</span>" if human else
                      "<span class='chip warn'>example not replaced</span>" if a.get("by") == "EXAMPLE" else
                      "<span class='chip crit'>unanswered</span>" if q.get("blocking") else "<span class='chip'>facultative</span>")
            prop = st["proposed"].get(q["id"])
            ex = ""
            if a.get("by") == "EXAMPLE":
                ex = (f'<div class="ex"><b>Lending Club example</b> — {esc(a.get("answer"))} '
                      f'<button type="button" onclick="this.closest(\'.q\').querySelector(\'textarea\').value={esc(json.dumps(str(a.get("answer", ""))))};">use the example</button></div>')
            if prop and not human:
                ptxt = prop.get("answer") if isinstance(prop, dict) else prop
                ex += f'<div class="agent"><div class="who">Agent proposal (INFERRED): review required</div><pre>{esc(ptxt)}</pre></div>'
            current = f'<div class="ex"><b>Current answer</b> — {esc(a.get("answer"))}</div>' if human else ""
            refs = json.dumps(a.get("refs", []))
            cards.append(f"""<div class="q{' answered' if human else ''}" data-id="{esc(q['id'])}" data-refs='{esc(refs)}'>
<div class="id mono">{esc(q['id'])} {'· blocking' if q.get('blocking') else ''} {status}</div><h3>{esc(q['question'])}</h3>
<div class="why">Pourquoi : {esc(q['why'])}</div><div class="cons">Consequence: {esc(q['consequence'])}</div>{current}{ex}
<textarea data-draft="{esc(q['id'])}" placeholder="{'New answer (leave empty to retain the current answer)' if human else 'Your answer, or not applicable: reason'}"></textarea></div>""")
        n_ex = sum(1 for q in st["questions"] if q["phase"] == ph and (st["answers"].get(q["id"]) or {}).get("by") == "EXAMPLE")
        bulk = (f'<div class="row noprint"><button type="button" onclick="fromExamples(\'{ph}\')">Start from {n_ex} examples for this phase</button>'
                f'<span class="hint">Review every answer: accepting an unread example lets someone else make the decision.</span></div>') if n_ex else ""
        panes.append(f'<div class="pane" data-pane="ph" data-t="{ph}"><p class="lede">{esc(phases_def[ph])}</p>{bulk}{"".join(cards)}</div>')
    first_open = first_open or gate.PHASES[0]
    body = f"""<h1>Questions by phase</h1>
<div class="decision"><div class="tag">To decide</div>Answer blocking questions for the open phase. An answer counts only when a person records it as <code>by: HUMAN</code> in <code>answers.yaml</code>.
<ul><li>Not applicable: reason is a valid answer.</li><li>An example or agent proposal never counts.</li>
<li>The generated block replaces matching answer IDs; then commit.</li></ul></div>
<div class="tabs" data-tabs="ph">{''.join(tabs)}</div>{''.join(panes)}
<h2>Block to paste into answers.yaml</h2><div class="card noprint"><div class="row"><button class="primary" type="button" onclick="build()">Generate</button>
<button type="button" onclick="osmlCopy(\'out\')">Copy</button><button type="button" onclick="osmlDownload(\'out\',\'answers.patch.yaml\')">Download</button></div>
<textarea id="out" class="out" readonly placeholder="Answers in answers.yaml format."></textarea>
<p class="hint">Drafts remain in this browser until cleared; nothing is sent.</p></div>"""
    js = """osmlDraft('osml-q');
function fromExamples(ph){document.querySelectorAll('[data-pane="ph"][data-t="'+ph+'"] .q').forEach(function(q){var b=q.querySelector('.ex button');
if(b&&!q.querySelector('textarea').value)b.click();});}
function build(){var lines=[];document.querySelectorAll('.q').forEach(function(q){var v=q.querySelector('textarea').value.trim();if(!v)return;
var refs=JSON.parse(q.dataset.refs||'[]');lines.push(q.dataset.id+': {by: HUMAN, answer: '+yq(v)+(refs.length?', refs: ['+refs.join(', ')+']':'')+'}');});
document.getElementById('out').value=lines.length?'# '+today()+' — '+lines.length+' answers\\n'+lines.join('\\n')+'\\n':'# no answer entered';}
document.addEventListener('DOMContentLoaded',function(){if(!location.hash)osmlTab('ph','""" + first_open + """');});"""
    return page("Questions · Hypotrail-ML", "questions", body, {"frame": st["fhash"]}, js)


# ============================================================== data dossier
SEVERE = ("MISSING", "fuite", "contract", "individually predictive")


def flag_chip(f: str) -> str:
    cls = "crit" if any(k in f for k in SEVERE) else "warn" if ("unstable" in f or "missing" in f or "sentinel" in f) else ""
    icon = "✗" if cls == "crit" else "⚠" if cls == "warn" else "•"
    return f'<span class="chip {cls}">{icon} {esc(f)}</span>'


def render_data(st: dict) -> str:
    prof, reg, spec = st["profile"], st["registry"], st["spec"]
    q = config.load_yaml(config.FEATURES_FILE).get("quality", {})
    did = next_decision_id()
    if not prof:
        body = ('<h1>Data report</h1><div class="decision"><div class="tag">Nothing to decide yet</div>'
                'The profile has not been calculated. Ask the data-analyst agent to run <code>python -m mlkit.profile</code>.</div>')
        return page("Data · Hypotrail-ML", "data", body, st["hashes"])

    stale = prof.get("frame_hash") != st["fhash"] or prof.get("data_hash") != st["hashes"].get("data")
    cols = prof["columns"]
    months = sorted(prof["target_by_month"])
    expl = prof["exploration_period_end"]
    rates = [prof["target_by_month"][m]["rate"] if prof["target_by_month"][m]["n"] >= q.get("min_rows_month", 200) else None for m in months]
    bands = []
    for k, (name, _, start, end) in enumerate(core.windows(spec), 1):
        s, e = str(start), str(end)
        if s in months:
            bands.append((months.index(s), months.index(e) if e in months else len(months) - 1, f"V{k}"))
    vline = (months.index(expl), "end of exploration") if expl in months else None
    target_chart = line_chart(months, rates, bands=bands, vline=vline, title="default rate by origination month")

    flagged = [c for c in cols if cols[c]["flags"]]
    flagged.sort(key=lambda c: (not any(any(k in f for k in SEVERE) for f in cols[c]["flags"]), not usable(reg, c), c))
    cards = []
    for c in flagged:
        s, e = cols[c], reg.get(c) or {}
        acks = "".join(f'<span class="chip good">✓ {k} : {esc(e[k])}</span>' for k in ("drift_ack", "leak_ack") if e.get(k))
        cards.append(f"""<div class="card" data-col="{esc(c)}"><div class="row" style="justify-content:space-between"><h3 class="mono">{esc(c)}</h3>
<span class="hint">{esc(e.get('available', 'undeclared'))}{' · exclue (' + esc(e.get('excluded_by')) + ')' if e.get('excluded_by') else ''} · {esc(s['type'])}</span></div>
<div class="hint">{esc(e.get('meaning', 'undocumented meaning'))}{' · ' + esc(e['unit']) if e.get('unit') else ''}</div>
<div style="margin:6px 0">{''.join(flag_chip(f) for f in s['flags'])}{acks}</div>
<div class="grid g3"><div><div class="hint">Distribution</div>{hist_svg(s.get('hist'))}</div>
<div><div class="hint">Missingness by month ({s['missing']:.1%} in total)</div>{strip_svg(s.get('missing_by_month'), months) or '<span class="hint">none</span>'}</div>
<div><div class="hint">Drift (PSI) by window relative to exploration</div>{psi_bars(s.get('psi_by_window'), q.get('psi_warn', .1), q.get('psi_stop', .25))}
<div class="hint">Individual strength (AUC, exploration) : {fmt(s.get('strength'), '{:.2f}')}</div></div></div>
<div class="grid g2 noprint" style="margin-top:8px"><select data-draft="act-{esc(c)}"><option value="">— no decision —</option>
<option value="drift_ack">acknowledge drift (drift_ack)</option><option value="leak_ack">acknowledge individual strength (leak_ack)</option>
<option value="exclude">exclude column</option><option value="meaning">confirm meaning with the source</option>
<option value="prepare">correct preparation (script + decision)</option><option value="contract">adjust contract</option></select>
<input type="text" data-draft="why-{esc(c)}" placeholder="Justification (obligatoire)"></div></div>""")

    miss_rows = [c for c in sorted(cols) if cols[c].get("missing_by_month")]
    heat = "".join(f'<tr><td class="mono">{esc(c)}</td><td style="width:70%">{strip_svg(cols[c]["missing_by_month"], months, w=600)}</td>'
                   f'<td class="n">{cols[c]["missing"]:.1%}</td></tr>' for c in miss_rows)
    all_rows = "".join(
        f'<tr><td class="mono">{esc(c)}</td><td>{esc((reg.get(c) or {}).get("available", "—"))}</td><td>{esc(cols[c]["type"])}</td>'
        f'<td class="n">{cols[c]["missing"]:.1%}</td><td class="n">{cols[c]["distinct"]:,}</td><td class="n">{fmt(cols[c].get("psi_max"), "{:.2f}")}</td>'
        f'<td class="n">{fmt(cols[c].get("strength"), "{:.2f}")}</td><td>{len(cols[c]["flags"]) or ""}</td></tr>' for c in sorted(cols))

    sel = render_selection(st, did)
    body = f"""<h1>Dossier data</h1>
{'<div class="stale">⚠ Profile calculated on another state (frame or data changed). Rerun <code>python -m mlkit.profile</code>.</div>' if stale else ''}
<div class="decision"><div class="tag">To decide</div>For each flagged column, determine whether the concern is <b>meaning</b>, <b>quality</b>, <b>stability</b>, or <b>leakage</b>. Choose and justify an action.
<ul><li>A used feature with drift (PSI &gt; {q.get('psi_stop', .25)}) or individually predictive of the target (AUC ≥ {q.get('univariate_auc_stop', .8)}) blocks D4/D6 without justification.</li>
<li>Data corrections use the preparation script and a <code>D-xxx</code> decision.</li>
<li>Without a decision, the signal returns in subsequent checks.</li></ul></div>
<div class="grid g4"><div class="card kpi"><div class="l">Rows</div><div class="v">{prof['rows']:,}</div></div>
<div class="card kpi"><div class="l">Period</div><div class="v" style="font-size:19px">{esc(prof['months'][0])} → {esc(prof['months'][1])}</div></div>
<div class="card kpi"><div class="l">Target relationships calculated through</div><div class="v" style="font-size:19px">{esc(expl)}</div></div>
<div class="card kpi"><div class="l">Flagged columns</div><div class="v">{len(flagged)} <span class="hint">/ {len(cols)}</span></div></div></div>
<h2>Default rate by origination month</h2><div class="card">{target_chart}
<p class="hint">Shaded V1, V2… regions are backtest validation windows. Breaks concern framing, policy, and loan maturity. Hide months with fewer than {q.get('min_rows_month', 200)} loans.</p></div>
<div class="tabs" data-tabs="dt"><button data-t="signals" class="on" onclick="osmlTab(\'dt\',\'signals\')">Signals ({len(flagged)})</button>
<button data-t="columns" onclick="osmlTab(\'dt\',\'columns\')">All columns</button><button data-t="selection" onclick="osmlTab(\'dt\',\'selection\')">Selection</button></div>
<div class="pane on" data-pane="dt" data-t="signals">{''.join(cards) or '<p class="hint">No flagged column.</p>'}
<h2>Decision block</h2><div class="card noprint"><div class="row"><button class="primary" type="button" onclick="buildData()">Generate</button>
<button type="button" onclick="osmlCopy(\'dout\')">Copy</button><button type="button" onclick="osmlDownload(\'dout\',\'decisions-donnees.md\')">Download</button></div>
<textarea id="dout" class="out" readonly></textarea><p class="hint">Append these rows to <code>decisions.md</code>, numbered starting at {did}), update <code>features.yaml</code>, then commit.</p></div></div>
<div class="pane" data-pane="dt" data-t="columns"><h2>Missingness by month</h2><div class="card scroll"><table>{heat or '<tr><td class="hint">No missing values.</td></tr>'}</table></div>
<h2>All columns</h2><div class="card scroll"><table><tr><th>column</th><th>available</th><th>type</th><th class="n">missing</th><th class="n">distinct</th><th class="n">max PSI</th><th class="n">individual strength</th><th>signals</th></tr>{all_rows}</table></div></div>
<div class="pane" data-pane="dt" data-t="selection">{sel}</div>"""
    js = """osmlDraft('osml-data');
var DID=%d;
function did(i){return 'D-'+String(DID+i).padStart(3,'0')}
function buildData(){var dec=[],reg=[],i=0,missing=[];
document.querySelectorAll('[data-col]').forEach(function(card){var c=card.dataset.col,a=card.querySelector('select').value,w=card.querySelector('input').value.trim();
if(!a)return; if(!w){missing.push(c);return;} var id=did(i++);
var lab={drift_ack:'drift acknowledged',leak_ack:'individual strength acknowledged',exclude:'excluded column',meaning:'meaning to confirm',prepare:'preparation correction',contract:'adjusted contract'}[a];
dec.push('| '+id+' | '+today()+' | DATA | HUMAN | '+c+' | '+lab+' | '+w.replace(/\\|/g,'/')+' |  | O |');
if(a==='drift_ack'||a==='leak_ack') reg.push('#   '+c+' : ajouter  '+a+': '+yq(id+' — '+w));
if(a==='exclude') reg.push('#   '+c+' : ajouter  excluded_by: '+id);
if(a==='prepare') reg.push('#   '+c+' : edit scripts/prepare_*.py with comment DECISION '+id+', rerun preparation');
if(a==='contract') reg.push('#   '+c+' : modifier contract (bound, liste, max_missing) — '+id);
if(a==='meaning') reg.push('#   '+c+' : verify with source, then complete meaning — '+id);});
var out=[];if(missing.length)out.push('# MISSING JUSTIFICATION for : '+missing.join(', ')+'\\n');
if(dec.length){out.push('# decisions.md — rows to append');out=out.concat(dec);out.push('');out.push('# features.yaml / preparation — required changes');out=out.concat(reg);}
document.getElementById('dout').value=out.join('\\n')||'# no decision entered';}
""" % int(did[2:])
    js += SELECTION_JS
    return page("Data · Hypotrail-ML", "data", body, {**st["hashes"], "profil": prof.get("data_hash")}, js)


SELECTION_JS = """
function buildSel(){var keep=[],drop=[],why=document.getElementById('selwhy').value.trim(),over=[];
document.querySelectorAll('[data-sel]').forEach(function(r){var cb=r.querySelector('input[type=checkbox]');if(!cb)return;
var prop=r.dataset.prop,c=r.dataset.sel; if(cb.checked)drop.push(c); if(prop==='excluded'&&!cb.checked)over.push(c+' (retained)'); if(prop==='retained'&&cb.checked)over.push(c+' (excluded against the rule)');});
var t=document.getElementById('selout'); if(over.length&&!why){t.value='# JUSTIFICATION REQUIRED: departing from the rule for '+over.join(', ');return;}
var id=document.getElementById('selid').value, sid=document.getElementById('selsid').value, rh=document.getElementById('selrh').value;
var lines=['# decisions.md — row to append','| '+id+' | '+today()+' | DATA | HUMAN | selection | '+sid+' (selection rule '+rh+') : exclusion of '+(drop.join(', ')||'no column')+(over.length?' ; departure from the rule : '+over.join(', '):'')+' | '+(why||'application of the committed rule')+' | retain all columns | O |','','# features.yaml — for each excluded column, add  excluded_by: '+id];
drop.forEach(function(c){lines.push('#   '+c)}); t.value=lines.join('\\n');}
"""


def render_selection(st: dict, did: str) -> str:
    b, spec = st["bivariate"], st["spec"]
    rule = spec.get("selection")
    rule_html = ("<table>" + "".join(f"<tr><td class='mono'>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rule.items()) + "</table>") if rule\
        else "<p class='ko'>No rule in frame.yaml (spec.selection).</p>"
    if not b:
        return f"""<div class="decision"><div class="tag">Before inspecting IV</div>Write the selection rule (Q-MOD-06) in <code>frame.yaml</code>, <code>spec.selection</code>, and <b>commit</b> before <code>python -m mlkit.bivariate</code>.
<p class="hint">A rule chosen after inspecting IV is disguised selection. Analysis records retain the rule hash; I9 flags later changes.</p></div>
<h2>Current rule</h2><div class="card">{rule_html}</div>"""
    stale = b.get("frame_hash") != st["fhash"] or b.get("data_hash") != st["hashes"].get("data")
    cols = b["columns"]
    top = max([r["iv"] for r in cols.values()] + [r["floor"] for r in cols.values()] + [0.05])
    order = sorted(cols, key=lambda c: (cols[c]["verdict"] != "retained", -cols[c]["iv"]))
    ratified = b["sel_id"] in st["decisions"]
    rows = []
    for c in order:
        r = cols[c]
        obs = None if r["direction"] is None else ("+" if r["direction"] > 0 else "−")
        exp = {"+": "+", "-": "−"}.get(r["expected"] or "", "")
        dir_html = f'{obs or "—"}{" / expected " + exp if exp else ""}' if r["numeric"] else '<span class="hint">categorical</span>'
        sub = " ".join(f'<span class="mono">{fmt(v, "{:.3f}")}</span>' for v in r["sub_iv"])
        verdict = (f'<span class="chip good">retained</span>' if r["verdict"] == "retained"
                   else f'<span class="chip crit">excluded</span><div class="hint">{esc("; ".join(r["reasons"]))}</div>')
        rows.append(f'<tr data-sel="{esc(c)}" data-prop="{esc(r["verdict"])}"><td class="noprint"><input type="checkbox" {"checked" if r["verdict"] != "retained" else ""} aria-label="exclude {esc(c)}"></td>'
                    f'<td class="mono">{esc(c)}</td><td>{iv_bar(r["iv"], r["floor"], top)}<div class="hint">IV {r["iv"]:.3f} · floor {r["floor"]:.3f}</div></td>'
                    f'<td>{dir_html}</td><td>{sub}</td><td style="min-width:200px">{band_svg(r["bands"], b["bad_rate"], w=220, h=70)}</td>'
                    f'<td class="n">{fmt(r.get("vif"), "{:.1f}")}</td><td>{verdict}</td></tr>')
    subs = " · ".join(f"{a} → {z} ({n:,} loans)" for a, z, n in b["subperiods"])
    pairs = "".join(f"<li><code>{esc(p['a'])}</code> × <code>{esc(p['b'])}</code> : ρ = {p['rho']:+.2f}</li>" for p in b["pairs"])
    dropped = sum(1 for r in cols.values() if r["verdict"] != "retained")
    return f"""<div class="decision"><div class="tag">{'Ratified' if ratified else 'To ratify'} · {esc(b['sel_id'])}</div>
The committed rule (hash <code>{esc(b['rule_hash'])}</code>) proposes excluding <b>{dropped}</b> columns out of {len(cols)}. Checked columns will be excluded.
<ul><li>Following the rule needs no extra justification.</li><li>Departures require justification and remain visible in the log.</li>
<li>Calculated on exploration data only ({esc(subs)}); the floor is IV from a permuted target.</li></ul></div>
{'<div class="stale">⚠ Analysis calculated on another state. Rerun <code>python -m mlkit.bivariate</code>.</div>' if stale else ''}
<div class="card scroll"><table><tr><th class="noprint">exclude</th><th>column</th><th>IV vs chance floor</th><th>effect direction</th><th>IV by subperiod</th><th>default rate by bin</th><th class="n">VIF</th><th>proposal</th></tr>{''.join(rows)}</table>
<p class="hint">Bar: IV; black marker: chance floor. Subperiod IV uses fewer loans and is inflated; compare subperiod stability, not total IV. Dashed line: mean default rate ({b['bad_rate']:.1%}); orange bar: missing values. Hover for values.</p></div>
{'<h2>Correlated pairs (without the target)</h2><div class="card"><ul>' + pairs + '</ul></div>' if pairs else ''}
<h2>Applied rule</h2><div class="card">{rule_html}</div>
<h2>Bloc de ratification</h2><div class="card noprint"><input type="hidden" id="selid" value="{did}"><input type="hidden" id="selsid" value="{esc(b['sel_id'])}"><input type="hidden" id="selrh" value="{esc(b['rule_hash'])}">
<input type="text" id="selwhy" placeholder="Justification required when departing from the rule"><div class="row"><button class="primary" type="button" onclick="buildSel()">Generate</button>
<button type="button" onclick="osmlCopy(\'selout\')">Copy</button><button type="button" onclick="osmlDownload(\'selout\',\'ratification-{esc(b['sel_id'])}.md\')">Download</button></div>
<textarea id="selout" class="out" readonly></textarea></div>"""


# ============================================================== stop dossier
ADDED = '<span class="chip warn">added</span>'

def render_stop(st: dict, stop: dict) -> str:
    runs = {r["run_id"]: r for r in st["runs"]}
    run = runs.get(stop["run_id"], {})
    ref = runs.get(run.get("reference")) if run else None
    spec = st["spec"]
    p = spec["metric_primary"]
    explo = [r for r in st["runs"] if r["status"] == "exploratory" and r["frame_hash"] == run.get("frame_hash")]
    idx = next((i for i, r in enumerate(explo) if r["run_id"] == run.get("run_id")), None)
    prev = explo[idx - 1] if idx else None
    thresholds, _ = config.stops_config()
    private = bool(stop.get("thresholds_private"))   # as recorded when the stop fired, not the current shell
    stale = run.get("frame_hash") != st["fhash"]

    win_rows = ""
    for w, m in (run.get("per_window") or {}).items():
        rv = (ref or {}).get("per_window", {}).get(w, {}).get(p)
        g = core.gain(spec, rv, m[p]) if rv is not None else None
        win_rows += (f"<tr><td>{esc(w)}</td><td class='n'>{m.get('n_train', 0):,}</td><td class='n'>{m.get('n_test', 0):,}</td>"
                     f"<td class='n'>{fmt(rv, '{:.4f}')}</td><td class='n'>{m[p]:.4f}</td><td class='n'>{fmt(g, '{:+.4f}')}</td>"
                     + "".join(f"<td class='n'>{m.get(k, float('nan')):.4f}</td>" for k in spec.get("metrics_secondary", [])) + "</tr>")
    sec_head = "".join(f"<th class='n'>{esc(k)}</th>" for k in spec.get("metrics_secondary", []))
    feats = set(run.get("features", []))
    added = sorted(feats - set(prev["features"])) if prev else []
    removed = sorted(set(prev["features"]) - feats) if prev else []
    reg = st["registry"]
    feat_rows = "".join(f"<tr><td class='mono'>{esc(f)}</td><td>{esc((reg.get(f) or {}).get('available', 'UNDECLARED'))}</td>"
                        f"<td>{esc((reg.get(f) or {}).get('owner', ''))}</td><td>{esc((reg.get(f) or {}).get('meaning', ''))}</td>"
                        "<td>" + (ADDED if f in added else "") + "</td></tr>" for f in sorted(feats))

    def agent_box(path: Path, who: str) -> str:
        if not path.exists():
            return f'<p class="hint">{esc(who)}: not produced yet (<code>{esc(path.relative_to(config.ROOT))}</code>).</p>'
        txt = path.read_text(encoding="utf-8")
        verdict = re.search(r"VERDICT\s*:\s*(.+)", txt)
        v = f'<div style="margin:4px 0 8px"><span class="chip {"crit" if verdict and "PROBABLE" in verdict.group(1) else ""}">VERDICT : {esc(verdict.group(1).strip())}</span></div>' if verdict else ""
        return f'<div class="agent"><div class="who">{esc(who)} — written by an agent; review required</div>{v}<pre>{esc(txt)}</pre></div>'

    hd = config.HANDOFF_DIR
    rid = stop["run_id"]
    decided = stop["decided"]
    decision_block = (f'<div class="card"><h3>Decision recorded</h3><pre style="white-space:pre-wrap">{esc(stop["decision_text"])}</pre></div>' if decided else f"""
<h2>Your decision</h2><div class="card noprint"><div class="grid g2"><label><input type="radio" name="d" value="continue"> continue — verified explanation, no change</label>
<label><input type="radio" name="d" value="correct the pipeline"> correct the pipeline — cause identified</label>
<label><input type="radio" name="d" value="revise the frame"> revise the frame — protocol concern (commit <code>frame:</code>)</label>
<label><input type="radio" name="d" value="stop the branch"> stop the branch</label></div>
<p><input type="text" id="reason" data-draft="reason" placeholder="Reason (required)"></p><p><input type="text" id="alt" data-draft="alt" placeholder="Rejected alternative"></p>
<p><input type="text" id="verif" data-draft="verif" placeholder="Checks performed (ablation, time travel, leakage review)"></p>
<p><input type="text" id="sign" data-draft="sign" placeholder="Signed: name"></p>
<div class="row"><button class="primary" type="button" onclick="buildStop()">Generate</button><button type="button" onclick="osmlCopy(\'sout\')">Copy</button>
<button type="button" onclick="osmlDownload(\'sout\',\'{esc(stop['stop_id'])}.decision.md\')">Download {esc(stop['stop_id'])}.decision.md</button></div>
<textarea id="sout" class="out" readonly></textarea><p class="hint">Save under <code>stops/</code>, then commit. Repeatedly continuing without changes suggests a false-positive stop worth reviewing.</p></div>""")

    others = "".join(f'<a class="chip {"" if s["decided"] else "crit"}" href="stop-{esc(s["stop_id"])}.html">{esc(s["stop_id"])}{" ✓" if s["decided"] else ""}</a>'
                     for s in st["stops"])
    body = f"""<div class="row">{others}</div><h1>Stop {esc(stop['stop_id'])}</h1>
{'<div class="stale">⚠ This run used another frame: its numbers are stale (I7).</div>' if stale else ''}
<div class="decision"><div class="tag">{'Resolved' if decided else 'To decide'}</div><b>{esc('; '.join(stop['triggers']))}</b>
<ul><li><b>continue</b>: verified explanation; runs resume.</li><li><b>correct the pipeline</b>: identified cause; verify with the next run.</li>
<li><b>revise the frame</b>: protocol changes invalidate results.</li><li><b>stop the branch</b>: abandon the direction while retaining its rationale.</li></ul>
Without a decision file, no run is allowed and I8 fails. Estimated time: 5–10 minutes.</div>
<h2>1. Facts</h2><div class="grid g4"><div class="card kpi"><div class="l">Run</div><div class="v mono" style="font-size:20px">{esc(rid)}</div><div class="hint mono">{esc(run.get('pipeline'))} · {esc(run.get('code_hash'))}</div></div>
<div class="card kpi"><div class="l">Mean gain over the reference</div><div class="v">{fmt((run.get('gain') or {}).get('mean'), '{:+.4f}')}</div><div class="hint">± {fmt((run.get('gain') or {}).get('std'), '{:.4f}')} between windows</div></div>
<div class="card kpi"><div class="l">Comparisons so far</div><div class="v">{run.get('comparisons_total', '—')}</div><div class="hint">budget {spec.get('exploration_budget', '—')}</div></div>
<div class="card kpi"><div class="l">Seuils</div><div class="v" style="font-size:18px">{'private' if private else 'default'}</div><div class="hint">{'outside the repository; not displayed' if private else 'too beau ' + format(thresholds['too_good_gain'], '+.3f')}</div></div></div>
<div class="card scroll"><table><tr><th>window</th><th class="n">train</th><th class="n">test</th><th class="n">reference {esc(p)}</th><th class="n">run</th><th class="n">gain</th>{sec_head}</tr>{win_rows}</table></div>
<h2>2. This run in history</h2><div class="card">{gain_svg(explo, rid, None if private else thresholds['too_good_gain'])}
<p class="hint">One point per exploratory run under this frame; bars show window variation and filled points indicate conclusive runs. The stopped run is red. More trials increase chance optimism.</p></div>
<h2>3. Changes</h2><div class="card">{'<p>Relative to <code>' + esc(prev['run_id']) + '</code> : ' + (('added ' + ', '.join(f'<code>{esc(a)}</code>' for a in added)) if added else 'no added feature') + ('' if not removed else ' · removed ' + ', '.join(f'<code>{esc(a)}</code>' for a in removed)) + '. Code : ' + ('identical' if prev.get('code_hash') == run.get('code_hash') else 'changed') + '.</p>' if prev else '<p class="hint">First exploratory run under this frame.</p>'}
<div class="scroll"><table><tr><th>feature</th><th>available</th><th>declared by</th><th>meaning</th><th></th></tr>{feat_rows}</table></div>
<p class="hint">First inspect added features and those declared by an agent (INFERRED).</p></div>
<h2>4. Agent findings</h2><p class="hint">Read after facts: a narrative read first can bias interpretation.</p>
{agent_box(hd / f'{rid}-leak-review.md', 'Leakage reviewer (without result access)')}
{agent_box(hd / f'{rid}-dossier.md', 'Case writer (without explorer notes)')}
{f'<div class="agent"><div class="who">Note free de l’explorateur</div><pre>{esc(run.get("note"))}</pre></div>' if run.get('note') else ''}
{decision_block}"""
    js = """osmlDraft('osml-%s');
function buildStop(){var d=document.querySelector('input[name=d]:checked'),g=function(i){return document.getElementById(i).value.trim()};
var t=document.getElementById('sout'); if(!d||!g('reason')||!g('sign')){t.value='# Choose a decision and reason, then sign.';return;}
t.value='# Decision %s\\nDecision : '+d.value+'\\nReason : '+g('reason')+'\\nRejected alternative : '+g('alt')+'\\nChecks performed : '+g('verif')+'\\nSigned: '+g('sign')+', '+today()+'\\n';}
""" % (stop["stop_id"], stop["stop_id"])
    return page(f"{stop['stop_id']} · Hypotrail-ML", "stop", body, {"frame": st["fhash"], "run": run.get("frame_hash")}, js)


# ============================================================== entry points
def render_all() -> list[str]:
    st = load_state()
    written = []
    write("index.html", render_index(st)); written.append("index.html")
    write("questions.html", render_questions(st)); written.append("questions.html")
    write("data.html", render_data(st)); written.append("data.html")
    for s in st["stops"]:
        name = f"stop-{s['stop_id']}.html"
        write(name, render_stop(st, s)); written.append(name)
    return written


def safe_render() -> None:
    """Called at the end of profile, bivariate and run: a broken page must never break a command."""
    try:
        render_all()
    except Exception as exc:  # noqa: BLE001
        print(f"(HTML pages not regenerated: {exc})", file=sys.stderr)


def main(argv=None) -> int:
    written = render_all()
    print(f"pages : {', '.join('reports/' + w for w in written)}\nOuvrez reports/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
