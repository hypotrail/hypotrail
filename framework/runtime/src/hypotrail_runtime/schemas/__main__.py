"""Regenerate (``python -m hypotrail_runtime.schemas``) or check (``--check``) the schemas."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from hypotrail_runtime.contracts import MODELS

HERE = Path(__file__).resolve().parent


def render() -> dict[str, bytes]:
    out = {}
    for version, model in MODELS.items():
        name = version.split('.', 1)[1].replace('/', '-v') + '.schema.json'
        schema = model.model_json_schema(mode='validation')
        schema['$id'] = f'https://hypotrail.invalid/schemas/{name}'
        schema['$comment'] = ('Generated from hypotrail_runtime.contracts; do not edit. '
                              'Validation semantics are those of the Pydantic model (strict).')
        out[name] = (json.dumps(schema, indent=1, sort_keys=True, ensure_ascii=False)
                     + '\n').encode('utf-8')
    return out


def main(argv: list[str]) -> int:
    rendered = render()
    if '--check' in argv:
        stale = [n for n, data in rendered.items()
                 if not (HERE / n).is_file() or (HERE / n).read_bytes() != data]
        extra = [p.name for p in HERE.glob('*.schema.json') if p.name not in rendered]
        if stale or extra:
            print(json.dumps({'stale': stale, 'extra': extra}))
            return 1
        return 0
    for name, data in rendered.items():
        (HERE / name).write_bytes(data)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
