'use strict';
// Currency on the real CLI (decision CR.1; review finding H1, reproduction e1): the
// junior's dataset changes after the walkthrough, with no new revision. A watch event (not
// the explicit Refresh) must make the panel read `evidence` again, so it never shows the
// earlier results as current. Passes with an engine that sends `summary.currency` and with
// one that does not (the controller's own digest sees the dataset-changed alert). The case
// is a copy under a temporary folder, never use-cases/. Needs framework/.venv.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { Study, panel, skip } = require('./realstudy');

let bank;

test.before(() => {
  if (skip) return;
  bank = new Study('binary', 'bank currency', { copy: true });
  bank.walk();
});

test.after(() => { if (bank) bank.dispose(); });

test('H1 (e1): a dataset edit without a new revision; the next watch-event read is not served from the cache', { skip }, async () => {
  const p = panel(bank, { stage: 'v3' });
  await p.send({ type: 'ready' });
  await p.send({ type: 'load', view: 'evidence' });
  const before = p.last('view_data');
  assert.ok(before.model.results.some(r => r.current), 'current results after the walkthrough');
  const snap = p.snapshot();
  const csv = path.join(bank.caseDir, 'data', 'bank.csv');
  const lines = fs.readFileSync(csv, 'utf8').split('\n');
  lines[5] = lines[5].replace(/\d/, d => String((Number(d) + 1) % 10));
  fs.writeFileSync(csv, lines.join('\n'));
  await p.c.refresh();   // the watcher's call, not the junior's Refresh
  const after = p.snapshot();
  assert.equal(after.revision, snap.revision, 'no new revision');
  assert.notEqual(after.currency, snap.currency, 'a new currency');
  await p.send({ type: 'load', view: 'evidence' });
  const data = p.last('view_data');
  assert.equal(data.currency, after.currency);
  const direct = bank.hyp(['evidence', '--json']);
  assert.equal(data.model.results.filter(r => r.current).length, direct.results.filter(r => r.current).length,
    'the panel agrees with the CLI');
  assert.equal(p.commands().filter(c => c === 'evidence --json').length, 2, 'evidence was read twice');
});
