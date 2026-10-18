// Shared companion: render a project and journey from engine-validated contracts.
// No business columns, numbers, or text are hardcoded: use configuration and results.
(() => {
  'use strict';
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const COMPONENTS = new Set(['objective', 'examples_table', 'variable_dictionary', 'distribution', 'choice_question', 'numeric_selection', 'model_comparison',
    'metrics', 'error_view', 'limits', 'choice_summary', 'clarifications', 'text', 'details', 'data_explorer']);
  const STATUS = { confirmed: 'confirmed', proposed: 'proposed', unknown: 'unknown' };
  const AVAILABLE = { yes: 'yes', no: 'no', unknown: 'unknown' };
  const ROLE = { identifier: 'identifier', feature: 'feature', target: 'target', time: 'time', group: 'group', excluded: 'excluded' };
  let B = null, state = { activity: null, answers: {} }, snap = null, storageKey = '';
  const $ = id => document.getElementById(id);

  function number(value, digits) { return Number(value).toFixed(digits); }
  function formatMetric(value, definition) {
    if (value === null || value === undefined) return 'unavailable';
    const kind = definition?.format || 'number:2';
    if (kind === 'percent') return number(100 * value, 1) + ' %';
    if (kind === 'count') return String(Math.round(value));
    const unit = definition?.unit || '';
    return number(value, Number(kind.split(':')[1] || 2)) + (unit && !unit.startsWith('unitless') ? ' ' + unit : '');
  }
  const activities = () => B.journey.activities;
  const index = id => activities().findIndex(a => a.id === id);
  const content = id => B.project.activities[id];
  const choiceFor = id => Object.values(B.choices).find(c => c.activity === id) || null;
  const result = id => B.results.results.find(r => r.id === id);
  const definition = name => B.results.metric_definitions[name];
  const applied = key => snap?.application?.answers?.[key];
  const blocked = id => snap?.blocked?.[id] || null;
  function label(key, value) {
    const spec = B.choices[key];
    if (!spec || value === undefined || value === null) return '';
    if (spec.kind === 'choice_question') return spec.options[value]?.label ?? String(value);
    return spec.domain.find(o => o.value === value)?.label ?? String(value);
  }
  function previewValue(key) {
    const spec = B.choices[key];
    if (state.answers[key] !== undefined) return state.answers[key];
    if (spec?.kind === 'numeric_selection') return content(spec.activity).blocks.find(b => b.key === key)?.default ?? spec.domain[0].value;
    return undefined;
  }
  function boundResult(key, value) {
    const option = B.choices[key]?.domain?.find(o => o.value === value);
    return option && B.choices[key].compute === 'precomputed' ? result(option.result) : null;
  }

  const explorationViews = new Map();
  function explorer(b) {
    const e=B.results.display[b.source];
    return `<section class="card explorer"><div class="eda-heading"><div><span class="label">Discover · compare · question</span><h2>${esc(b.title)}</h2></div><span class="pill">Training only · ${e.rows} observations</span></div><div class="eda-tabs" role="group" aria-label="Choose an analysis">${e.charts.map((c,i)=>`<button data-chart="${i}" aria-pressed="${i===0}">${esc(c.title)}</button>`).join('')}</div><div id="eda-chart"></div><div class="eda-detail" id="eda-detail" role="status">Select a bar or point to inspect its values.</div><button type="button" id="eda-ask">Prepare a question about this chart</button><details><summary>Data quality and descriptive statistics</summary><p>${e.duplicates} duplicate rows across described columns (not necessarily duplicate people). No rows removed.</p><div class="scroll"><table><thead><tr><th>Variable</th><th>Missing</th><th>Distinct values</th><th>Min</th><th>Median</th><th>Max</th><th>Outliers*</th></tr></thead><tbody>${e.columns.map(c=>`<tr>${[c.column,c.missing,c.unique,c.min??'—',c.median??'—',c.max??'—',c.outliers??'—'].map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="small">* Outside Q1 − 1.5 × IQR and Q3 + 1.5 × IQR. A flag to examine, not an error to delete automatically.</p><ul>${e.notes.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details><p class="small">Visual exploration only: controls change neither dataset, protocol, nor applied choices.</p></section>`;
  }
  function bindExplorer(){
    if(!document.querySelector('.explorer'))return;
    const e=B.results.display.eda;const viewKey=B.project.id+':'+B.context_hash;let selected=explorationViews.get(viewKey)?.chart??0,detail='';
    const fmt=x=>Number(x).toLocaleString('en-US',{maximumFractionDigits:2});
    function select(i){
      const remembered=explorationViews.get(viewKey);const markIndex=remembered?.chart===i?remembered.mark:null;
      selected=i;detail='';explorationViews.set(viewKey,{chart:i,mark:markIndex});const c=e.charts[i];
      document.querySelectorAll('[data-chart]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.chart)===i)));
      const details=c.kind==='scatter'?c.points.map(p=>`${p.label} : ${c.x_label} ${fmt(p.x)} ; ${c.y_label} ${fmt(p.y)}`):c.items.map(p=>`${p.label} : ${fmt(p.value)} ${c.unit} ; effectif ${p.n}${p.q1!==undefined?` ; Q1 ${p.q1}, Q3 ${p.q3}`:''}`);
      let chart='';
      if(c.kind==='scatter'){
        const xs=c.points.map(p=>p.x),ys=c.points.map(p=>p.y),xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);
        const x=v=>65+(v-xmin)/(xmax-xmin||1)*590,y=v=>290-(v-ymin)/(ymax-ymin||1)*245;
        chart=`<svg class="eda-scatter" viewBox="0 0 720 350" role="group" aria-label="${esc(c.title)}"><line x1="65" y1="290" x2="655" y2="290"/><line x1="65" y1="45" x2="65" y2="290"/>${[0,.25,.5,.75,1].map(t=>`<text x="${65+590*t}" y="311" text-anchor="middle">${fmt(xmin+(xmax-xmin)*t)}</text><text x="55" y="${294-245*t}" text-anchor="end">${fmt(ymin+(ymax-ymin)*t)}</text>`).join('')}<text x="360" y="341" text-anchor="middle">${esc(c.x_label)}</text><text x="65" y="25">${esc(c.y_label)}</text>${c.points.map((p,j)=>`<circle cx="${x(p.x)}" cy="${y(p.y)}" r="4.5" tabindex="0" role="button" data-mark="${j}" aria-label="${esc(details[j])}"><title>${esc(details[j])}</title></circle>`).join('')}</svg>`;
      }else{
        const max=Math.max(1,...c.items.map(p=>p.value));chart=`<div class="eda-bars">${c.items.map((p,j)=>`<button class="eda-bar" data-mark="${j}" aria-label="${esc(details[j])}"><span>${esc(p.label)}</span><span class="eda-track"><i style="width:${p.value/max*100}%"></i></span><strong>${fmt(p.value)}</strong><small>n = ${p.n}</small></button>`).join('')}</div>`;
      }
      $('eda-chart').innerHTML=`<h3>${esc(c.title)}</h3><p class="small">${esc(c.note)} · ${esc(c.unit)}</p>${chart}<details><summary>View values in a table</summary><div class="scroll"><table><tbody>${details.map(v=>`<tr><td>${esc(v)}</td></tr>`).join('')}</tbody></table></div></details>`;
      $('eda-detail').textContent='Select a bar or point to inspect its values.';
      document.querySelectorAll('[data-mark]').forEach(mark=>{const action=()=>{explorationViews.set(viewKey,{chart:i,mark:Number(mark.dataset.mark)});detail=details[Number(mark.dataset.mark)];$('eda-detail').textContent=detail;document.querySelectorAll('[data-mark]').forEach(m=>m.classList.toggle('selected',m===mark));};mark.onclick=action;mark.onkeydown=ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();action();}};});
      if(markIndex!==null&&markIndex!==undefined)document.querySelector(`[data-mark="${markIndex}"]`)?.dispatchEvent(new MouseEvent("click",{bubbles:true}));
      $('eda-ask').onclick=()=>{
        const question=`Explain chart « ${c.title} » for the ${e.rows} training observations in project ${B.project.title}. ${detail?`Selection: ${detail}.`:''} Calculated summary: ${JSON.stringify(c.kind==='scatter'?{x:c.x_label,y:c.y_label,n:c.points.length}:c.items)}. ${c.note} What should I examine, and which limitation matters?`;
        const input=document.getElementById('question');if(input){if(input.value.trim()){ $('eda-detail').textContent='A question is already drafted: send or clear it before preparing this one.';return;}input.value=question;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();input.scrollIntoView({behavior:'smooth',block:'center'});}else{$('eda-detail').textContent=question;}
      };
    }
    document.querySelectorAll('[data-chart]').forEach(b=>b.onclick=()=>select(Number(b.dataset.chart)));select(selected);
  }

  // ---- composants ----
  const render = {
    data_explorer: explorer,
    objective: b => b.highlights ? `<div class="grid">${b.highlights.map(h => `<div class="stat"><b>${esc(h.value)}</b>${esc(h.label)}</div>`).join('')}</div>` : '',
    text: b => b.variant === 'notice' ? `<p class="notice">${esc(b.text)}</p>` : `<div class="chat"><span class="label">${esc(b.label || 'Guide')} · texte fixe du parcours</span><p>${esc(b.text)}</p></div>`,
    details: b => `<details><summary>${esc(b.summary)}</summary><p>${esc(b.text)}</p></details>`,
    examples_table(b) {
      const vars = Object.fromEntries(B.project.variables.map(v => [v.name, v]));
      const cell = (name, value) => {
        const v = vars[name] || {};
        const special = (v.special_values || []).find(s => String(s.value) === String(value));
        if (special) return special.meaning;
        if (value === null || value === undefined) return 'missing';
        return v.value_labels?.[value] ?? value;
      };
      const rows = B.results.display.examples || [];
      return `<section class="card"><h2>${esc(b.title)}</h2>${b.intro ? `<p>${esc(b.intro)}</p>` : ''}<div class="scroll"><table aria-label="Example data"><thead><tr>${b.columns.map(c => `<th scope="col">${esc(vars[c]?.label || c)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${b.columns.map(c => `<td>${esc(cell(c, r[c]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`;
    },
    distribution(b) {
      const items = B.results.display[b.source] || [], total = items.reduce((s, x) => s + x.count, 0) || 1;
      return `<section class="card"><h3>${esc(b.title)}</h3>${items.map(x => `<div class="distribution"><span>${esc(x.label)} · ${x.count} ${esc(b.unit || '')} (${number(100 * x.count / total, 1)} %)</span><div class="bar" role="img" aria-label="${esc(x.label)} : ${number(100 * x.count / total, 1)} %"><span style="width:${100 * x.count / total}%"></span></div></div>`).join('')}</section>`;
    },
    variable_dictionary: b => `<details class="dictionary"><summary>${esc(b.title || 'Variable dictionary')}</summary><ul>${B.project.variables.map(v => `<li><b>${esc(v.label)}</b> <code>${esc(v.name)}</code> : ${esc(v.description || '')}${v.unit ? ` · unit: ${esc(v.unit)}` : ''} · role: ${esc(ROLE[v.role])} · available at prediction time: ${esc(AVAILABLE[v.available_at_prediction])} · information ${esc(STATUS[v.status])}${(v.special_values || []).map(s => ` · « ${esc(s.value)} » : ${esc(s.meaning)}`).join('')}</li>`).join('')}</ul>${b.note ? `<p>${esc(b.note)}</p>` : ''}</details>`,
    clarifications(b) {
      const facts = snap?.facts || B.project.facts.map(f => ({ ...f, declared_status: f.status }));
      const open = facts.filter(f => (f.status !== 'confirmed' || f.needs_review) && (!b.only || b.only.includes(f.id))), done = b.only ? [] : facts.filter(f => f.status === 'confirmed' && !f.needs_review);
      const item = f => `<li class="fact" data-fact="${esc(f.id)}"><span class="fact-status" data-status="${esc(f.status)}">${esc(STATUS[f.status])}</span> <b>${esc(f.label)}</b> : ${esc(f.value)} <span class="small">· source : ${esc(f.source)}</span>${f.needs_review ? '<p class="small warning">Your previous confirmation depends on changed data: review required.</p>' : ''}<div class="fact-actions">${f.status === 'proposed' || f.needs_review ? `<button data-confirm="${esc(f.id)}" data-decision="confirm">Confirm this proposal</button><button data-confirm="${esc(f.id)}" data-decision="reject">This is not correct</button>` : ''}${window.osml.canAsk ? `<button data-clarify="${esc(f.id)}">Ask what needs checking</button>` : ''}</div></li>`;
      return `<section class="card clarifications"><h2>${esc(b.title || 'What still needs clarification')}</h2>${open.length ? `<ul class="facts">${open.map(item).join('')}</ul>` : '<p>No information pending.</p>'}<p class="small">A proposal, including an AI proposal, is confirmed only by your action.</p>${done.length ? `<details><summary>Confirmed facts (${done.length})</summary><ul>${done.map(f => `<li><b>${esc(f.label)}</b> : ${esc(f.value)} <span class="small">· ${esc(f.source)}</span></li>`).join('')}</ul></details>` : ''}</section>`;
    },
    choice_question(b, ctx) {
      const v = state.answers[b.key], lock = ctx.blocked;
      return `<section class="card"><span class="label">Optional short experiment</span><h2>${esc(b.question)}</h2><div class="options">${b.options.map((o, i) => `<button data-quiz="${esc(b.key)}" data-value="${i}" class="${v === i ? 'selected' : ''}" aria-pressed="${v === i}" ${lock ? 'disabled' : ''}>${esc(o.label)}</button>`).join('')}</div>${Number.isInteger(v) && b.options[v] ? `<div class="feedback">${esc(b.options[v].feedback || '')}</div>` : '<p class="small">Choose an answer; you can change it later.</p>'}</section>`;
    },
    numeric_selection(b, ctx) {
      const v = previewValue(b.key), spec = B.choices[b.key];
      return `<section class="card"><label for="${esc(b.key)}"><b>${esc(b.label)}</b></label><p><select id="${esc(b.key)}" data-numeric="${esc(b.key)}" ${ctx.blocked ? 'disabled' : ''}>${spec.domain.map(o => `<option value="${o.value}" ${o.value === v ? 'selected' : ''}>${esc(number(o.value, Number((b.format || 'number:2').split(':')[1] || 2)))}</option>`).join('')}</select> <span class="small">${esc(b.hint || '')}</span></p></section>`;
    },
    metrics(b) {
      const spec = B.choices[b.for_choice], v = previewValue(b.for_choice), r = boundResult(b.for_choice, v);
      if (!r) return `<p class="notice">${spec?.compute === 'not_available' ? 'Calculation unavailable in this version: no result for this choice.' : 'No result available for this choice.'}</p>`;
      const stale = r.status !== 'available' ? `<p class="notice">Result ${r.status === 'stale' ? 'stale: data changed since calculation' : r.status}.</p>` : '';
      return `<section class="card metrics-card"><span class="label">Precomputed result · ${esc(label(b.for_choice, v))}</span><div class="grid">${b.metrics.map(m => `<div class="stat"><b>${esc(r.display[m])}</b>${esc(definition(m).label)}</div>`).join('')}</div>${b.summary?.length ? `<p>${b.summary.map(m => `${esc(definition(m).label)} : ${esc(r.display[m])}`).join(' · ')}</p>` : ''}${b.note ? `<p class="small">${esc(b.note)}</p>` : ''}${stale}</section>`;
    },
    model_comparison(b, ctx) {
      const choice = b.choice ? B.choices[b.choice.key] : null, v = choice ? previewValue(choice.key) : undefined;
      const protocols = Object.fromEntries(B.results.protocols.map(p => [p.id, p]));
      const rows = b.results.map(item => {
        const r = result(item.id), scope = r.scope === 'counterexample' ? ' <span class="pill">counterexample</span>' : '';
        const status = r.status !== 'available' ? ` <span class="pill">${esc(r.status === 'stale' ? 'stale' : r.status)}</span>` : '';
        const pick = choice ? `<td><button data-pick="${esc(choice.key)}" data-value="${esc(item.id)}" aria-pressed="${v === item.id}" class="${v === item.id ? 'selected' : ''}" ${ctx.blocked ? 'disabled' : ''}>${v === item.id ? 'Retenu en preview' : 'Examiner'}</button></td>` : '';
        return `<tr><th scope="row">${esc(item.label || r.label)}${scope}${status}<br><span class="small">${esc(protocols[r.protocol]?.label || r.protocol)} · ${r.observations} obs.</span></th>${b.metrics.map(m => `<td>${esc(r.display[m])}</td>`).join('')}${pick}</tr>`;
      }).join('');
      return `<section class="card"><div class="scroll"><table><thead><tr><th scope="col">Model</th>${b.metrics.map(m => `<th scope="col" title="${esc(definition(m).description || '')}">${esc(definition(m).label)}<br><span class="small">${esc(definition(m).unit)}</span></th>`).join('')}${choice ? `<th scope="col">${esc(choice.label)}</th>` : ''}</tr></thead><tbody>${rows}</tbody></table></div>${b.note ? `<p>${esc(b.note)}</p>` : ''}</section>`;
    },
    error_view(b) {
      const data = B.results.display[b.source], def = definition(b.metric);
      const chosen = state.answers[b.for_choice] ?? applied(b.for_choice) ?? B.choices[b.for_choice]?.domain?.[0]?.value;
      const models = B.choices[b.for_choice]?.domain || [];
      const max = Math.max(...data.rows.map(r => r[chosen] || 0), 1);
      return `<section class="card"><h2>${esc(b.title)}</h2><p class="small">Displayed model: ${esc(label(b.for_choice, chosen))}${applied(b.for_choice) === chosen ? ' (applied)' : ' (preview, not applied)'} · ${esc(def.label)} en ${esc(def.unit)}.</p>${data.rows.map(r => `<div class="distribution"><span>${esc(data.group_label)} ${esc(r.group)} · ${r.observations} obs. · ${esc(formatMetric(r[chosen], def))}</span><div class="bar" role="img" aria-label="${esc(r.group)} : ${esc(formatMetric(r[chosen], def))}"><span style="width:${100 * (r[chosen] || 0) / max}%"></span></div></div>`).join('')}<details><summary>All models</summary><div class="scroll"><table><thead><tr><th scope="col">${esc(data.group_label)}</th>${models.map(m => `<th scope="col">${esc(m.label)}</th>`).join('')}</tr></thead><tbody>${data.rows.map(r => `<tr><th scope="row">${esc(r.group)}</th>${models.map(m => `<td>${esc(formatMetric(r[m.value], def))}</td>`).join('')}</tr>`).join('')}</tbody></table></div></details></section>`;
    },
    limits(b) {
      const items = [...(B.project.limitations || []), ...(B.results.limitations || [])];
      for (const r of snap?.application?.results || []) for (const l of result(r.result_id)?.limitations || []) items.push(l);
      return `<section class="card"><h2>${esc(b.title || 'Limites')}</h2><ul>${[...new Set(items)].map(l => `<li>${esc(l)}</li>`).join('')}</ul></section>`;
    },
    choice_summary(b) {
      const lines = Object.values(B.choices).map(spec => {
        const a = applied(spec.key), d = state.answers[spec.key];
        const name = spec.kind === 'choice_question' ? content(spec.activity).title : spec.label;
        return `- ${name} : ${d !== undefined ? label(spec.key, d) : 'not chosen yet'}${d !== undefined ? (a === d ? ' (applied)' : ' (not applied)') : ''}`;
      });
      const text = (b.handoff || '').replace('{{choices}}', lines.join('\n'));
      return `<section class="card"><h2>${esc(b.title)}</h2><textarea id="handoff" readonly aria-label="Summary for the pilot">${esc(text)}</textarea><p><button id="copy">Copy for my chat</button> <button id="download">Export exercise choices</button></p><p id="copyState" class="small" role="status"></p></section>`;
    }
  };

  function body() {
    const a = activities()[index(state.activity)], c = content(a.id), moment = B.journey.moments.find(m => m.id === a.moment);
    const lock = blocked(a.id), ctx = { blocked: lock };
    const unsupported = c.blocks.map(b => b.component).filter(k => !COMPONENTS.has(k));
    if (unsupported.length) return `<p class="notice" role="alert">Configuration incompatible : unsupported component (${esc(unsupported.join(', '))}). Nothing is substituted for it.</p>`;
    const head = `<span class="label">${esc(moment?.label || '')} · ${esc(B.project.title)} · ${index(a.id) + 1} / ${activities().length}</span><h1>${esc(c.title)}</h1><p class="lead">${esc(c.lead || '')}</p><p class="objective"><b>Objectif :</b> ${esc(c.objective)}</p>`;
    const warn = lock ? `<p class="notice" role="note">Choice blocked until these facts are confirmed: ${lock.map(esc).join(', ')}. The activity remains readable; confirm them under What still needs clarification.</p>${render.clarifications({ title: 'Confirm to continue', only: a.requires })}` : '';
    const stale = B.dataset_changed ? '<p class="notice" role="note">Data changed since results were calculated: they are stale and applied choices need review.</p>' : '';
    return head + stale + warn + c.blocks.map(b => render[b.component](b, ctx)).join('');
  }

  function draw() {
    if (!B) return;
    const list = activities(), i = index(state.activity);
    $('content').innerHTML = body();
    $('position').textContent = 'Activity ' + (i + 1) + ' of ' + list.length + ' · free navigation';
    $('progress').style.width = ((i + 1) / list.length * 100) + '%';
    let html = '', moment = null;
    list.forEach((a, n) => {
      if (a.moment !== moment) { moment = a.moment; html += `<p class="label nav-moment">${esc(B.journey.moments.find(m => m.id === moment)?.label || '')}</p>`; }
      html += `<button data-step="${n}" data-activity="${esc(a.id)}" class="${n === i ? 'active' : ''}" ${n === i ? 'aria-current="step"' : ''}>${n + 1}. ${esc(content(a.id).title)}${blocked(a.id) ? ' <span aria-label="blocked">·</span>' : ''}</button>`;
    });
    $('nav').innerHTML = html;
    $('prev').disabled = i === 0; $('next').disabled = i === list.length - 1;
    document.querySelectorAll('[data-step]').forEach(b => b.onclick = () => go(list[Number(b.dataset.step)].id));
    document.querySelectorAll('[data-quiz]').forEach(b => b.onclick = () => { state.answers[b.dataset.quiz] = Number(b.dataset.value); save(); draw(); });
    document.querySelectorAll('[data-numeric]').forEach(s => s.onchange = () => { state.answers[s.dataset.numeric] = Number(s.value); save(); draw(); });
    document.querySelectorAll('[data-pick]').forEach(b => b.onclick = () => { state.answers[b.dataset.pick] = b.dataset.value; save(); draw(); });
    document.querySelectorAll('[data-confirm]').forEach(b => b.onclick = () => api.onConfirm?.(b.dataset.confirm, b.dataset.decision));
    document.querySelectorAll('[data-clarify]').forEach(b => b.onclick = () => { const f = (snap?.facts || B.project.facts).find(x => x.id === b.dataset.clarify); api.onClarify?.(`What should be checked to clarify « ${f.label} » ? (information ${STATUS[f.status]} : ${f.value})`); });
    const handoff = $('handoff');
    if (handoff) {
      $('copy').onclick = async () => { try { await navigator.clipboard.writeText(handoff.value); $('copyState').textContent = 'Summary copied. Paste it into the pilot chat.'; } catch (_) { handoff.select(); $('copyState').textContent = 'Text selected: copy it manually.'; } };
      $('download').onclick = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify({ purpose: 'tutorial_only', project_id: B.project.id, dataset_id: B.project.dataset.id, answers: state.answers }, null, 2)], { type: 'application/json' })); a.download = 'mes-choice-' + B.project.session_name + '.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000); };
    }
    save();
    api.afterRender?.();
    bindExplorer();
  }

  function save() {
    try { localStorage.setItem(storageKey, JSON.stringify(state)); } catch (_) { /* stockage indisponible */ }
    if (window.bridgeQueue) window.bridgeQueue({ activity: state.activity, answers: state.answers });
  }
  function go(id) { state.activity = id; draw(); window.scrollTo({ top: 0, behavior: 'smooth' }); }

  function start(bundle) {
    B = bundle; storageKey = 'hypotrail-companion-' + B.project.id;
    state = { activity: activities()[0].id, answers: {} };
    try { const saved = JSON.parse(localStorage.getItem(storageKey)); if (saved && index(saved.activity) >= 0 && saved.answers && typeof saved.answers === 'object') state = saved; } catch (_) { /* brouillon illisible */ }
    document.title = 'Hypotrail · ' + B.project.title;
    $('project-pill').textContent = B.project.title + ' · ' + B.journey.title;
    $('aside-note').textContent = B.project.description;
    const p = B.project.dataset.provenance;
    $('footer').textContent = `Public data: ${p.authors}, ${B.project.dataset.name} · ${p.license}${p.doi ? ' · DOI ' + p.doi : ''}. Results precomputed by ${B.results.generated_by?.script || 'the project adapter'}. Choices belong to this exercise only. In VS Code, Apply and explain and your questions request a model through GitHub Copilot; other clicks send no request.`;
    draw();
  }

  const api = {
    start, render: draw, go, label, choiceFor, content, formatMetric, boundResult, previewValue,
    bundle: () => B, state: () => state,
    setState(next) { if (B && next && index(next.activity) >= 0) state = { activity: next.activity, answers: { ...next.answers } }; },
    setSnapshot(next) { snap = next; },
    canAsk: false, onConfirm: null, onClarify: null, afterRender: null
  };
  window.osml = api;
  document.getElementById('prev').onclick = () => B && go(activities()[Math.max(0, index(state.activity) - 1)].id);
  document.getElementById('next').onclick = () => B && go(activities()[Math.min(activities().length - 1, index(state.activity) + 1)].id);
  try { document.body.classList.toggle('dark', localStorage.getItem('osml-theme') === 'dark'); } catch (_) { /* default theme */ }
  document.getElementById('theme').onclick = () => { document.body.classList.toggle('dark'); try { localStorage.setItem('osml-theme', document.body.classList.contains('dark') ? 'dark' : 'light'); } catch (_) { /* no storage */ } };
  const reset = document.getElementById('reset'); let armed = 0;
  reset.onclick = () => {
    if (!B) return;
    if (Date.now() - armed > 6000) { armed = Date.now(); reset.textContent = 'Confirm: clear choices for this exercise (retain conversation, confirmations, and other projects)'; return; }
    armed = 0; reset.textContent = 'Reset exercise'; state = { activity: activities()[0].id, answers: {} }; draw();
  };
})();
