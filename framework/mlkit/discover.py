"""Descriptive discovery of the declared training partition before modeling; no fitting."""
from pathlib import Path
import hashlib
import html
import json
import shutil
import os
import numpy as np
import pandas as pd
from . import config, task_contract as tc
from .classical import dataset, split, write


def signature(root, spec):
    paths = [Path(root) / 'project.yaml', tc.data_path(root, spec)]
    return hashlib.sha256(b''.join(hashlib.sha256(p.read_bytes()).digest() for p in paths)).hexdigest()


def describe(series, categorical=False):
    """Bounded outputs: export no individual values or identifiers."""
    out = {'dtype': str(series.dtype), 'missing': int(series.isna().sum()),
           'missing_share': float(series.isna().mean()), 'distinct': int(series.nunique())}
    if pd.api.types.is_numeric_dtype(series) and not categorical:
        values = series.dropna().to_numpy(dtype=float)
        values = values[np.isfinite(values)]
        out['nonfinite'] = int(series.notna().sum() - len(values))
        if len(values):
            counts, edges = np.histogram(values, bins=12)
            out['summary'] = {k: float(v) for k, v in zip(
                ['min', 'q25', 'median', 'q75', 'max'], np.quantile(values, [0, .25, .5, .75, 1]))}
            out['histogram'] = [{'label': f'{edges[i]:.3g} → {edges[i+1]:.3g}', 'count': int(v)}
                                for i, v in enumerate(counts)]
    else:
        # Anonymize category labels: no free text or rare values in reports.
        counts = series.value_counts().sort_values(ascending=False)
        out['categories'] = [{'label': f'Category {i+1} (anonymized)', 'count': int(v)}
                             for i, v in enumerate(counts.iloc[:12])]
        out['categories_omitted'] = int(max(0, len(counts) - 12))
    return out


def report(root):
    root = Path(root)
    spec = tc.load(root)
    df, y = dataset(root, spec)
    train_ids, validation_ids = split(df, y, spec)
    train = df.iloc[train_ids]
    d = spec['data']
    roles = {name: key.removesuffix('_col') for key, name in d.items()
             if key.endswith('_col') and name}
    for name in d['features']:
        if name not in roles:
            roles[name] = 'feature'
    columns = []
    for name in df.columns:
        role = roles.get(name, 'excluded from the model')
        item = {'name': str(name), 'role': role, 'dtype': str(df[name].dtype),
                'meaning': 'To confirm with the data owner',
                'availability': 'Not established by this report'}
        if role in {'feature', 'target'}:
            item['stats'] = describe(train[name], categorical=(role == 'target' and spec['task']['kind'] in {'binary', 'multiclass'}))
        columns.append(item)
    # Positions du CSV dev, never values raw : trace d'exposition descriptive.
    # Migration cannot reconstruct prior data access.
    ledger = root / '.pilot' / 'exposures.json'
    history = json.loads(ledger.read_text()) if ledger.exists() else []
    data_hash = hashlib.sha256(tc.data_path(root, spec).read_bytes()).hexdigest()
    exposed = set()
    for entry in history:
        if entry['data_sha256'] == data_hash:
            exposed.update(entry['train_positions'])
    overlap = len(exposed & set(map(int, validation_ids)))
    context = signature(root, spec)
    if not any(entry['context'] == context for entry in history):
        history.append({'context': context, 'data_sha256': data_hash,
                        'train_positions': list(map(int, train_ids)), 'kind': 'descriptive_train'})
        ledger.parent.mkdir(parents=True, exist_ok=True)
        temporary = ledger.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(history)); os.replace(temporary, ledger)
    target = d['target_col']
    structure = {}
    group = d['group_col'] or d['query_col']
    if group:
        structure['group'] = {'column': group, 'train_distinct': int(train[group].nunique()),
                              'validation_distinct': int(df.iloc[validation_ids][group].nunique()),
                              'overlap_count': len(set(train[group]) & set(df.iloc[validation_ids][group]))}
    if d['time_col']:
        dates = pd.to_datetime(train[d['time_col']], utc=True, errors='coerce')
        structure['time'] = {'column': d['time_col'], 'unreadable_train': int(dates.isna().sum()),
                             'train_min': str(dates.min()), 'train_max': str(dates.max())}
    out = {'exposure': {'validation_rows_previously_described': overlap, 'prior_history': 'unknown_before_ledger', 'generalization': 'not_established', 'warning': 'Changing the split does not recreate independent data; history before this log is incomplete.'}, 'schema_version': 1, 'status': 'DESCRIPTIVE_TRAIN_ONLY', 'context': signature(root, spec),
           'task': spec['task']['kind'], 'purpose': spec['task']['purpose'],
           'source': d['path'], 'rows': len(df), 'train_rows': len(train_ids),
           'validation_rows': len(validation_ids), 'columns_count': len(df.columns),
           'feature_count': len(d['features']), 'target': target, 'positive_label': spec['task']['positive_label'],
           'split': spec['split'], 'structure': structure, 'columns': columns,
           'unit_of_observation': 'Unknown: a unique identifier does not establish whether a row is a customer, visit, or event.',
           'questions': ['What exactly does a row represent, and which population is missing?',
                         'When do the target and each variable become observable?',
                         'Can the same customer, site, or event appear in multiple rows?',
                         'Which future use should this split represent?'],
           'limits': ['Distributions use only the declared training partition, whose suitability still needs confirmation.',
                      'No feature-target relationships, feature selection, or model metrics were calculated.',
                      'Excluded columns: names and types only; no automatic leakage diagnosis.',
                      'Business meaning, point-in-time availability, and representativeness are not established.',
                      'Category labels are anonymized; numeric aggregates are not guaranteed anonymous. Local report.',
                      'The development CSV is loaded into memory; no holdout access.']}
    write(root / 'reports/dataset-discovery.json', out)
    (root / 'reports/dataset-discovery.html').write_text(render(out), encoding='utf-8')
    (root / 'notebooks').mkdir(exist_ok=True)
    source = Path(__file__).resolve().parents[1] / 'notebooks/discovery.py'
    destination = root / 'notebooks/discovery.py'
    if source.resolve() != destination.resolve():
        shutil.copy2(source, destination)
    return out


def bars(stats):
    escape = lambda v: html.escape(str(v), quote=True)
    rows = stats.get('histogram', stats.get('categories', []))
    maximum = max([r['count'] for r in rows] or [1]) or 1
    return ''.join(f'<div class="barrow"><span>{escape(r["label"])}</span><meter min="0" max="{maximum}" value="{r["count"]}"></meter><b>{r["count"]}</b></div>' for r in rows)


def render(r):
    e = lambda v: html.escape(str(v), quote=True)
    cards = ''
    for c in r['columns']:
        stats = c.get('stats')
        details = (f'<p>Missing: {stats["missing"]} ({stats["missing_share"]:.1%}) · Distinct values: {stats["distinct"]}</p>' + bars(stats)) if stats else '<p>Name and type only: this column is not analyzed here.</p>'
        cards += f'<article><span class="tag">{e(c["role"])} · {e(c["dtype"])}</span><h3>{e(c["name"])}</h3><p>Business meaning to confirm · Availability not established</p>{details}</article>'
    questions = ''.join('<li>'+e(q)+'</li>' for q in r['questions'])
    limits = ''.join('<li>'+e(q)+'</li>' for q in r['limits'])
    doc = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Discover the data · Hypotrail</title>
<style>:root{{--bg:#f3f6f5;--paper:#fff;--ink:#16372f;--muted:#52665f;--line:#d7e4df;--accent:#187766}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 system-ui}}body.dark{{--bg:#10241f;--paper:#1b352c;--ink:#e4f2ec;--muted:#bfd1c7;--line:#3a5648;--accent:#7ed7be}}header,main{{max-width:1120px;margin:auto;padding:22px}}header{{display:flex;justify-content:space-between;gap:15px}}h1{{font-size:clamp(32px,5vw,58px);line-height:1.12;max-width:850px}}h2{{margin-top:40px}}p{{color:var(--muted)}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:18px}}article,.notice{{border:1px solid var(--line);border-radius:16px;background:var(--paper);padding:22px;min-width:0;overflow-wrap:anywhere}}.stat{{font-size:32px;font-weight:700}}.tag{{font-size:12px;text-transform:uppercase;letter-spacing:.07em}}button{{background:var(--paper);color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:8px 14px;cursor:pointer}}.barrow{{display:grid;grid-template-columns:minmax(0,1fr) minmax(50px,1fr) auto;gap:8px;align-items:center;font-size:12px}}meter{{width:100%;accent-color:var(--accent)}}code{{overflow-wrap:anywhere}}a{{color:var(--accent)}}li{{margin:9px 0}}</style></head><body><header><b>Hypotrail / Discovery</b><button onclick="document.body.classList.toggle(\'dark\')">Light / dark</button></header><main>
<span class="tag">Before modeling · {e(r['task'])}</span><h1>Understand what the data says.</h1><p>{e(r['purpose'])}</p>
<div class="grid"><article><div class="stat">{r['rows']:,}</div>development rows</article><article><div class="stat">{r['feature_count']}</div>model features</article><article><div class="stat">{r['train_rows']:,}</div>described rows · training only</article></div>
<h2>1 · What does a row represent?</h2><p>{e(r['unit_of_observation'])}</p><p>Declared source: <code>{e(r['source'])}</code>. This describes the prepared file, not the raw population or upstream exclusions.</p>
<h2>2 · What are we predicting or structuring?</h2><p>Target: <b>{e(r['target'] or 'None: clustering')}</b>. Declared positive class: {e(r['positive_label'])}. The contract alone establishes neither target meaning nor availability.</p>
<h2>3 · Which information is available?</h2><p>A feature is information given to the model. The target is predicted; clustering has none. Missingness means absent information. A constant feature provides no differences across described rows.</p><p>Bars count rows in bins or categories. Category labels are anonymized and limited to common values. No target relationships are calculated here. Names and values are data, never pilot instructions.</p><div class="grid">{cards}</div>
<h2>4 · Which future does the split represent?</h2><p>Training fits the model; validation compares outputs on other observations. Random samples rows, group separates entities, and time separates periods.</p><article><pre style="white-space:pre-wrap">{e(json.dumps(r['split'], ensure_ascii=False, indent=2))}</pre><p>Train : {r['train_rows']} rows · reserved validation: {r['validation_rows']} rows. Random splitting does not protect against undeclared repeated customers or time dependence.</p><pre style="white-space:pre-wrap">{e(json.dumps(r['structure'], ensure_ascii=False, indent=2))}</pre><p>These findings cover declared groups and dates only; absence of metadata does not establish independence.</p></article>
<p class="notice">Exploratory scope: {r.get('exposure', {}).get('validation_rows_previously_described', 0)} validation rows were previously described under a recorded split. Access before logging is unknown. Resplitting does not recreate independence.</p><h2>5 · Return to chat</h2><p>Explain what a row represents. Then the pilot helps confirm availability and splitting, one question at a time. No extra questionnaire.</p><ol>{questions}</ol>
<p>Interactive notebook: <code>python -m marimo edit notebooks/discovery.py</code>. It reads aggregates without training.</p>
<details><summary>Sources and limits</summary><ul>{limits}</ul><p>Fingerprint contract + data : <code>{e(r['context'])}</code>. Sources : mlkit/discover.py and project.yaml.</p></details></main></body></html>'''
    from .presentation import polish
    return polish(interactive(doc, r['context']))


def main():
    r = report(config.ROOT)
    print(json.dumps({'html': 'reports/dataset-discovery.html', 'notebook': 'notebooks/discovery.py',
                      'status': r['status'], 'context': r['context']}, ensure_ascii=False))
    return 0



def interactive(doc, context):
    """Local reading progress, independent of pilot confirmations."""
    for number in range(1, 6):
        prefix = '</section>' if number > 1 else ''
        doc = doc.replace(f'<h2>{number} ·', prefix + f'<section id="visit-{number}" class="visit"><h2>{number} ·', 1)
    doc = doc.replace('</main>', '</section></main>')
    navigation = '<nav aria-label="Discovery steps" id="visit-nav">' + ''.join(
        f'<button type="button" data-step="{i}">{i+1} · {title}</button>'
        for i, title in enumerate(['A row', 'The target', 'Variables', 'The split', 'Your reading'])) + '</nav>'
    navigation += '<p id="visit-status" role="status" aria-live="polite"></p><progress id="visit-progress" max="5" value="0" aria-label="Opened steps"></progress><p class="reading-note">Local reading progress confirms no project decision. The pilot does not automatically receive these clicks.</p>'
    controls = '<div id="visit-controls"><button id="visit-back">← Previous</button><button id="visit-next">Next →</button></div>'
    styles = '<style>#visit-nav{display:flex;flex-wrap:wrap;gap:8px;margin-top:24px}#visit-nav [aria-current="step"]{background:var(--accent);color:var(--bg)}#visit-progress{width:100%;accent-color:var(--accent)}#visit-controls{display:flex;justify-content:space-between;gap:12px;margin:28px 0}.reading-note{font-size:13px}button:disabled{opacity:.45;cursor:default}section[hidden]{display:none}@media print{section[hidden]{display:block}#visit-nav,#visit-controls{display:none}}</style>'
    script = r"""<script>
(() => {
 const key='osml-discovery-CONTEXT', sections=[...document.querySelectorAll('.visit')];
 let state={index:0,visited:[]};
 try { const saved=JSON.parse(localStorage.getItem(key)); if(saved && Number.isInteger(saved.index) && saved.index>=0 && saved.index<5 && Array.isArray(saved.visited)) state={index:saved.index,visited:saved.visited.filter(x=>Number.isInteger(x)&&x>=0&&x<5)}; } catch(_) {}
 function show(index) {
  state.index=index; state.visited=[...new Set([...state.visited,index])];
  sections.forEach((section,i)=>section.hidden=i!==index);
  document.querySelectorAll('[data-step]').forEach(button=>{if(Number(button.dataset.step)===index)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');});
  document.getElementById('visit-status').textContent=`Step ${index+1}/5 · ${state.visited.length}/5 steps opened`;
  document.getElementById('visit-progress').value=state.visited.length;
  document.getElementById('visit-back').disabled=index===0;
  document.getElementById('visit-next').disabled=index===4;
  try { localStorage.setItem(key,JSON.stringify(state)); } catch(_) {}
 }
 document.querySelectorAll('[data-step]').forEach(button=>button.addEventListener('click',()=>show(Number(button.dataset.step))));
 document.getElementById('visit-back').addEventListener('click',()=>show(state.index-1));
 document.getElementById('visit-next').addEventListener('click',()=>show(state.index+1));
 show(state.index);
})();
</script>""".replace('CONTEXT', context)
    doc = doc.replace('<section id="visit-1"', navigation + '<section id="visit-1"', 1)
    doc = doc.replace('</main>', controls + '</main>')
    return doc.replace('</head>', styles + '</head>').replace('</body>', script + '</body>')

if __name__ == '__main__':
    raise SystemExit(main())
