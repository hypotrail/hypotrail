import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'understanding'))
import ukit
from mlkit.study.understanding import canonical, export as ex, schemas


def test_real_export_validates_against_schema(tmp_path):
    jsonschema = pytest.importorskip('jsonschema')
    from referencing import Registry, Resource
    u = ukit.U(tmp_path)
    sid = ukit.full_flow(u)
    ukit.approve_all(u, sid)
    w = u.m('export', 'write', '--session', sid, '--repo', u.repo)
    doc = canonical.loads((u.repo / ex.EXPORT_DIR / w['review_id'] / ex.JSON_FILE).read_bytes())
    docs = schemas.render()
    reg = Registry().with_resources([(k, Resource.from_contents(v)) for k, v in docs.items()])
    v = jsonschema.Draft202012Validator(docs['understanding-review-1.schema.json'], registry=reg)
    errs = [f'{list(e.path)}: {e.message[:120]}' for e in v.iter_errors(doc)]
    print('ERRORS', errs)
    assert not errs
