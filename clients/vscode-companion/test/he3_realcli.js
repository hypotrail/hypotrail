'use strict';
// HE-3 on the real CLI (review finding; driven by test_he3_real_cli.py). A Bank Marketing
// study is walked by the chat agent to the fits and rendered, then two copies are changed
// behind the engine's back:
//   edited:  one cited number of reports/study.html is changed (a stale citation);
//   deleted: reports/study.html is removed.
// For each, the real controller (lib/controller.js) reads the study after the junior's
// Refresh, loads the checks, and opens the finding's location. Prints one JSON document.
// Not a VS Code session. Needs framework/.venv.

const fs = require('fs');
const path = require('path');
const { Study, panel } = require('./realstudy');

async function probe(study, change) {
  const opened = [];
  const p = panel(study, { stage: 'v3' }, { openArtifact: async (name, target, options) => { opened.push({ name, target, options }); } });
  await p.send({ type: 'ready' });
  await p.send({ type: 'load', view: 'check' });
  const before = { check: p.last('view_data').model, snapshot: p.snapshot() };
  const report = path.join(study.studyDir, 'reports', 'study.html');
  const detail = change(report);
  await p.send({ type: 'refresh' });
  await p.send({ type: 'load', view: 'check' });
  const check = p.last('view_data').model;
  const snapshot = p.snapshot();
  // The finding's "Open" (the Overview's button): the deliverable at its report anchor.
  const finding = (check.findings || []).find(f => f.severity === 'error' && f.deliverable) || null;
  if (finding) {
    const msg = { type: 'open_artifact', artifact: finding.deliverable };
    if (finding.resultId) msg.resultId = finding.resultId;
    else if (finding.location && finding.location.line && finding.deliverable !== 'report') msg.line = finding.location.line;
    await p.send(msg);
  }
  const raw = study.hyp(['status', '--summary', '--digest', '--json']);
  return {
    detail,
    engineCurrency: typeof raw.currency === 'string',
    before: { clean: before.check.clean, report: (before.snapshot.artifacts.find(a => a.name === 'report') || {}).status },
    after: {
      codes: (check.findings || []).map(f => f.code),
      finding,
      report: (snapshot.artifacts.find(a => a.name === 'report') || {}).status || null,
      regenerate: snapshot.regenerate,
      currencyMoved: snapshot.currency !== before.snapshot.currency,
    },
    opened: opened.map(o => ({ name: o.name, rel: path.relative(study.studyDir, o.target), options: o.options })),
    checkReads: p.commands().filter(c => c === 'check --json').length,
  };
}

(async () => {
  const bank = new Study('binary', 'bank he3');
  try {
    bank.walk();
    const rendered = bank.hyp(['render', '--json']);
    if (!rendered.ok) throw new Error(JSON.stringify(rendered).slice(0, 500));
    const edited = bank.clone('bank he3 edited');
    const deleted = bank.clone('bank he3 deleted');
    const out = {};
    out.edited = await probe(edited, report => {
      const html = fs.readFileSync(report, 'utf8');
      const m = /(<data\b[^>]*data-result-id="[0-9a-f]{64}"[^>]*>)([^<]*[0-9][^<]*)(<\/data>)/.exec(html);
      if (!m) throw new Error('no cited number in the report');
      const changed = m[2].replace(/[0-9]/, d => String((Number(d) + 1) % 10));
      fs.writeFileSync(report, html.slice(0, m.index) + m[1] + changed + m[3] + html.slice(m.index + m[0].length));
      return { from: m[2], to: changed };
    });
    out.deleted = await probe(deleted, report => { fs.rmSync(report); return { removed: 'reports/study.html' }; });
    for (const s of [edited, deleted]) s.dispose();
    process.stdout.write(JSON.stringify(out));
  } finally {
    bank.dispose();
  }
})().catch(e => { process.stderr.write(String((e && e.stack) || e)); process.exit(1); });
