"""Owner session 2026-10-26, lot L8: a study made before L8 loads unchanged and stays current,
except its predictor capture (risk K3, accepted by the owner, D19).

The study is made with the pre-L8 fingerprints: while it is built, the engine reports for the
modules L8 changed the digests the 10c1e70 engine recorded (``ENGINES['10c1e70']`` of
``test_code_compat_l8.py``, and the capture's recipe and runtime files), and the quality check
leaves out its two L8 keys, as that engine did. The values themselves are those of that engine
(the byte comparison of ``code_compat_evidence.py``). Then the L8 engine reads it:

* nothing is reset or migrated, and every promoted result is current under the L8 edges,
  except ``predictor.capture`` (never attested: its ids hash the code fingerprint, and the
  recipe and runtime changed);
* before the opening, ``next_action`` names the re-capture (``run predictor.capture``), and
  the run captures again, after which the opening proceeds;
* after the opening, the final evaluation read that capture: it is not current and is never
  recomputed; ``next_action`` proposes the conclusion with the not-recomputable notice
  (R5E-8), and the export source is the recipe of the configuration (recipe-only, artifact
  missing) instead of the captured bundle.

``test_a_study_of_the_pre_l8_engine_itself`` repeats the first point with a study built by
the pre-L8 engine itself when one is supplied (``HYPOTRAIL_COMPAT_OLD_PYTHON``,
``HYPOTRAIL_COMPAT_OLD_ROOT``), where the old bundle also fails to load at the L8 runtime.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mlkit.study import activities as act, eda, read, records as rec, registry, state as st

import flowkit as fk

sys.path.insert(0, str(Path(__file__).resolve().parent / 'libraries'))
import test_capture_final as tcf  # noqa: E402
from test_code_compat_l8 import ENGINES  # noqa: E402

PRE_L8 = {**ENGINES['10c1e70'],
          'mlkit.contracts.recipe':
          '4a84fcc9a7dda214764ebb5af6208eb50bec402dd9bd5c2d3e38815816e29f98',
          'hypotrail_runtime.preprocess':
          '34c2cfb4cb3a0c866bd7ccf1a4cb092c12aca60c20b95b6a46d9edeefb16822b'}


def _pre_l8(monkeypatch) -> None:
    """The engine records and reads the pre-L8 digests, and its quality check has no
    quantiles or skewness (an engine before L8)."""
    original = read.Study._module_sha
    monkeypatch.setattr(read.Study, '_module_sha',
                        lambda self, name: PRE_L8.get(name) or original(self, name))
    fingerprint = registry.code_fingerprint

    def fp(modules):
        out = fingerprint(modules)
        shas = {m: PRE_L8.get(m, d) for m, d in out['modules'].items()}
        return {'fingerprint': rec.code_digest(shas), 'modules': shas}
    monkeypatch.setattr(registry, 'code_fingerprint', fp)
    monkeypatch.setattr(eda, '_shape', lambda ordinary: {})


def _not_current(flow) -> list[str]:
    ev = flow.call('evidence', '--study', flow.study)
    promoted = set(flow.state()['current'].values())
    return sorted(r['slot'] for r in ev['results']
                  if r['result_id'] in promoted and not r.get('current'))


def _run(flow, *args, expect=None):
    return flow.call('run', *args, '--request-id', flow.rid(), '--expected-revision',
                     flow.rev(), '--study', flow.study, expect=expect)


def _to_opening(flow, limit=8):
    for _ in range(limit):
        nxt = flow.view()['next_action']
        if nxt.get('decision') == 'final_test' or nxt.get('activity') == act.CAPTURE:
            return nxt
        assert nxt['kind'] == 'run', nxt
        _run(flow, nxt['activity'], *[a for r in nxt.get('rules') or []
                                      for a in ('--rule', r)], expect=0)
    raise AssertionError('the opening was not reached')


def _pre_l8_study(base: Path, monkeypatch, *, opened: bool):
    with monkeypatch.context() as m:
        _pre_l8(m)
        flow = tcf._chosen(base)
        for activity in ('eda.target_rate', 'eda.special_values', 'eda.quality', 'diag.binary'):
            flow.run(activity)
        flow.run('predictor.capture')
        if opened:
            assert tcf._open(flow)['result']['opening']['status'] == 'promoted'
            flow.run('diag.final_test')
        state_before = (flow.study / '.hypotrail' / 'state.json').read_bytes()
        assert _not_current(flow) == []
        quality = read.open(flow.study).current('eda.quality')['output']['values']
        assert all('quantiles' not in r for r in quality['ranges'])
    return flow, state_before


def test_a_sealed_pre_l8_study_is_current_but_its_capture(tmp_path, monkeypatch):
    flow, state_before = _pre_l8_study(tmp_path, monkeypatch, opened=False)
    # Loaded unchanged: reading writes nothing.
    flow.view()
    assert (flow.study / '.hypotrail' / 'state.json').read_bytes() == state_before
    assert _not_current(flow) == [act.CAPTURE]
    # The quality check of the old engine stays current without the new keys.
    s = read.open(flow.study)
    assert s.is_current('eda.quality') and s.is_current('fit.logistic')
    nxt = _to_opening(flow)
    assert (nxt['kind'], nxt['activity'], nxt['not_current']) == (
        'run', act.CAPTURE, [act.CAPTURE])
    out = _run(flow, 'predictor.capture', expect=0)
    assert out['status'] == 'promoted'
    assert _not_current(flow) == []
    nxt = _to_opening(flow)
    assert (nxt['kind'], nxt.get('decision')) == ('propose', 'final_test')
    assert tcf._open(flow)['result']['opening']['status'] == 'promoted'


def test_an_opened_pre_l8_study_keeps_its_figures_and_exports_recipe_only(tmp_path,
                                                                          monkeypatch):
    from mlkit.contracts.export_source import read_export_source
    flow, _ = _pre_l8_study(tmp_path, monkeypatch, opened=True)
    assert _not_current(flow) == sorted([act.CAPTURE, act.FINAL, 'diag.final_test'])
    nxt = flow.view()['next_action']
    assert (nxt['kind'], nxt['decision']) == ('propose', 'conclusion')
    assert nxt['not_recomputable'] == [act.FINAL]
    assert nxt['junior_message'].startswith('The final test was opened once, and its '
                                            'evaluation cannot be computed again')
    # The recorded final figures are kept (shown as not current); they are never recomputed.
    s = read.open(flow.study)
    assert s.current(act.FINAL)['output']['values']
    capture = flow.state()['current'][act.CAPTURE]
    out = _run(flow, 'final_test.evaluation', expect=2)['error']
    assert out['code'] == 'final_test_already_opened'
    # Not a code change of the final evaluation itself (attested): its capture input.
    assert out['details']['code_changed'] == []
    assert out['details']['upstream_not_current'] == [capture]
    # The Azure ML export falls back to the recipe of the configuration (K3).
    source = read_export_source(flow.study, flow.rev())
    assert source.predictor.status != 'captured'
    assert source.scientific_contracts['source'] == 'configuration'


BUILD = '''
import json, sys
from pathlib import Path
old, base = Path(sys.argv[1]), Path(sys.argv[2])
sys.path[:0] = [str(old / 'framework/tests/study/libraries'), str(old / 'framework/tests/study')]
import mlkit, hypotrail_runtime
assert str(old) in mlkit.__file__ and str(old) in hypotrail_runtime.__file__
import test_capture_final as tcf
flow = tcf._chosen(base)
flow.run('eda.quality')
flow.run('predictor.capture')
print(json.dumps({'study': str(flow.study), 'case': str(flow.case_dir)}))
'''


@pytest.mark.skipif(not (os.environ.get('HYPOTRAIL_COMPAT_OLD_PYTHON')
                         and os.environ.get('HYPOTRAIL_COMPAT_OLD_ROOT')),
                    reason='needs the pre-L8 engine (10c1e70) and a Python with its '
                           'dependencies (HYPOTRAIL_COMPAT_OLD_PYTHON, HYPOTRAIL_COMPAT_OLD_ROOT)')
def test_a_study_of_the_pre_l8_engine_itself(tmp_path):
    old = Path(os.environ['HYPOTRAIL_COMPAT_OLD_ROOT'])
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    env['PYTHONPATH'] = f'{old}/framework{os.pathsep}{old}/framework/runtime/src'
    proc = subprocess.run([os.environ['HYPOTRAIL_COMPAT_OLD_PYTHON'], '-c', BUILD, str(old),
                           str(tmp_path / 'old')], capture_output=True, text=True, env=env,
                          timeout=1800)
    assert proc.returncode == 0, proc.stderr[-4000:]
    built = json.loads(proc.stdout.strip().splitlines()[-1])
    flow = fk.Flow(Path(built['study']), Path(built['case']), prefix='l8')
    assert _not_current(flow) == [act.CAPTURE]
    quality = read.open(flow.study).current('eda.quality')['output']['values']
    assert all('quantiles' not in r for r in quality['ranges'])
    nxt = _to_opening(flow)
    assert (nxt['kind'], nxt['activity']) == ('run', act.CAPTURE)
    assert _run(flow, 'predictor.capture', expect=0)['status'] == 'promoted'
    assert _not_current(flow) == []
    assert st.b1_default_value(flow.state(), 'final_test') is not None
