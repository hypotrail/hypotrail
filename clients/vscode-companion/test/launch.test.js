'use strict';
// The two Marimo launches (WP-A5, ADR 0004 amendment "local launch"): scope U.

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');
const { launchFor, isMarimoLaunch, prefixFromAgent } = require('../lib/launch');

const STUDY = '/home/j/studies/bank';
const NB = path.join(STUDY, 'notebooks', 'study_generated.py');
const WB = path.join(STUDY, 'notebooks', 'workbench.py');
const UV = { studyDir: STUDY, argv: ['uv', 'run', '--project', '/opt/hypotrail/framework', 'hypotrail'] };
const PY = { studyDir: STUDY, argv: ['/opt/hypotrail/framework/.venv/bin/python', '-m', 'mlkit.study.cli'] };

test('the engine argv is used when it has exactly the expected form', () => {
  const engine = { mode: 'run', path: 'notebooks/study_generated.py',
    argv: ['uv', 'run', '--project', '/elsewhere/framework', 'marimo', 'run', NB] };
  const l = launchFor(UV, 'notebook', engine);
  assert.equal(l.source, 'engine');
  assert.deepEqual(l.argv, engine.argv);
  assert.equal(l.terminalName, 'Hypotrail · marimo run study_generated.py');
});

test('without an engine launch, the argv is built from agent.json: uv project or python -m', () => {
  assert.deepEqual(launchFor(UV, 'notebook').argv, ['uv', 'run', '--project', '/opt/hypotrail/framework', 'marimo', 'run', NB]);
  assert.deepEqual(launchFor(UV, 'workbench').argv, ['uv', 'run', '--project', '/opt/hypotrail/framework', 'marimo', 'edit', WB]);
  assert.deepEqual(launchFor(PY, 'workbench').argv, ['/opt/hypotrail/framework/.venv/bin/python', '-m', 'marimo', 'edit', WB]);
  assert.equal(launchFor(PY, 'notebook').source, 'agent');
});

test('only marimo run of the generated notebook and marimo edit of the workbench are accepted', () => {
  const bad = [
    ['uv', 'run', '--project', '/x', 'marimo', 'edit', NB],          // the generated notebook is never edited
    ['uv', 'run', '--project', '/x', 'marimo', 'run', WB],           // the workbench opens for editing
    ['uv', 'run', '--project', '/x', 'python', 'run', NB],           // not marimo
    ['uv', 'run', '--project', '/x', 'marimo', 'run', '/tmp/other.py'],
    ['sh', '-c', 'marimo', 'run', NB],                                // a shell
    ['uv', 'run', '--with', 'evil', '--project', '/x', 'marimo', 'run', NB],
    ['uv', 'run', '--project', 'relative', 'marimo', 'run', NB],
    ['/usr/bin/bash', '-m', 'marimo', 'run', NB],
    ['uv', 'run', '--project', '/x', 'marimo', 'run', `${NB}\0`],
  ];
  for (const argv of bad) assert.equal(isMarimoLaunch(argv, STUDY, 'notebook') && isMarimoLaunch(argv, STUDY, 'workbench'), false, argv.join(' '));
  for (const argv of bad.slice(0, 6)) {
    const l = launchFor(UV, 'notebook', { argv });
    assert.equal(l.source, 'agent', `an unexpected engine argv is not used: ${argv.join(' ')}`);
  }
  assert.equal(launchFor(UV, 'report'), null, 'no launch for the report');
});

test('an agent argv of no known form gives no launch', () => {
  assert.equal(prefixFromAgent(['hypotrail']), null);
  assert.equal(launchFor({ studyDir: STUDY, argv: ['/usr/local/bin/hypotrail'] }, 'notebook'), null);
  assert.equal(launchFor({ studyDir: STUDY, argv: ['bash', '-m', 'x'] }, 'notebook'), null);
});
