"""Cross-check of ``media/format.js`` against ``mlkit.study.cite.fmt_number`` (scope U).

The webview formats engine values with a port of the engine's formatter, so a number reads
the same in the panel and in the report (COMPANION-ADVANCED §9). 200 values, every format,
including ties (Python rounds the exact binary value half to even), negative zero, and
thousands separators. Needs Node.js.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from mlkit.study import cite

CLIENT = Path(__file__).resolve().parents[1]
NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(NODE is None, reason='Node.js is not installed')

EDGES = [0.0, -0.0, 0.5, 1.5, 2.5, -2.5, 0.125, 0.375, 0.0005, 0.00049, 0.115, 0.11534, 0.2450405,
         1234.5, 1235.5, -1234.56, 99.995, 100.0, 100.05, 999999.5, 3164.0, 1357.0, 0.36,
         0.23076923076923078, 6.308647265230509, -3.7959532190309977, 1e-7, 123456789.125,
         0.9995, 0.0049999, 12.345, 0.1, 0.7, 0.3447315770081061]


def _values() -> list[float]:
    rng = random.Random(20261018)
    values = list(EDGES)
    while len(values) < 200:
        kind = len(values) % 4
        if kind == 0:
            values.append(rng.random())
        elif kind == 1:
            values.append(round(rng.uniform(-50, 50), rng.randint(0, 4)))
        elif kind == 2:
            values.append(rng.randint(-10 ** 7, 10 ** 7) / 8)
        else:
            values.append(rng.uniform(-2000, 2000))
    return values


def test_format_matches_the_engine_on_200_values_in_every_format():
    values = _values()
    assert len(values) == 200
    script = ("require('./media/format.js');"
              "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
              "const {values,formats}=JSON.parse(s);"
              "process.stdout.write(JSON.stringify(values.map(v=>formats.map(f=>"
              "globalThis.Hypotrail.format.number(v,f)))))});")
    payload = json.dumps({'values': values, 'formats': list(cite.FORMATS)})
    out = subprocess.run([NODE, '-e', script], input=payload, capture_output=True, text=True,
                         check=True, cwd=CLIENT, timeout=60).stdout
    got = json.loads(out)
    mismatches = [(v, f, got[i][j], cite.fmt_number(v, f))
                  for i, v in enumerate(values) for j, f in enumerate(cite.FORMATS)
                  if got[i][j] != cite.fmt_number(v, f)]
    assert not mismatches, mismatches[:10]


def test_format_list_is_the_engine_list():
    script = "require('./media/format.js');process.stdout.write(JSON.stringify(globalThis.Hypotrail.format.FORMATS))"
    out = subprocess.run([NODE, '-e', script], capture_output=True, text=True, check=True,
                         cwd=CLIENT, timeout=60).stdout
    assert tuple(json.loads(out)) == cite.FORMATS


def test_french_format_matches_the_report_with_decimal_commas_and_grouping():
    values = [0.259, 0.886, 5353, 32049, 12.345]
    formats = ['pct1', 'pct1', 'int', 'int', 'f2']
    script = ("globalThis.Hypotrail={language:()=> 'fr'};require('./media/format.js');"
              "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
              "const {values,formats}=JSON.parse(s);process.stdout.write(JSON.stringify("
              "values.map((v,i)=>globalThis.Hypotrail.format.number(v,formats[i]))))});")
    out = subprocess.run([NODE, '-e', script], input=json.dumps({'values': values,
                         'formats': formats}), capture_output=True, text=True, check=True,
                         cwd=CLIENT, timeout=60).stdout
    assert json.loads(out) == [cite.format_value(v, f, 'fr')
                               for v, f in zip(values, formats)]
