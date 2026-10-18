"""Artefact manifest ``.hypotrail/artifacts.json`` (plan §3.6, WP3.1).

The manifest records, for every deliverable, what was written and from what::

    {"schema": "hypotrail.artifacts/1", "revision": 12, "status": "ok|stale|failed",
     "artifacts": {
        "report":    {path, kind, revision, status, consumed, sha256, generated,
                      template_version, error, last_ok_revision, user_edits_preserved,
                      candidate},
        "notebook":  {... same keys, plus edit_check_sha256},
        "workbench": {... same keys, plus sha256_at_creation}}}

``revision`` is the study revision the artefact was last written for (or attempted
at, when it failed); ``consumed`` lists the result ids whose numbers it cites.

**An artefact is current** iff its status is ``ok``, its revision equals the state
revision, and every result it consumes is still current (promoted and not stale).
:func:`effective_status` computes this against a state; the stored ``status`` only
says how the last render went. The workbench is not generated (``generated: false``):
it is created once, never overwritten, and its experiments are not tracked, so it is
never stale.

The status logic is pure; :func:`save` imports the store's atomic writer lazily, so
this module can be read by the read side without importing a writer.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Mapping

from .currency import consumed_current, effective_status, message, overall  # noqa: F401

SCHEMA = 'hypotrail.artifacts/1'
FILE = 'artifacts.json'
HOME = '.hypotrail'
ARTIFACTS = {'report': 'reports/study.html',
             'notebook': 'notebooks/study_generated.py',
             'workbench': 'notebooks/workbench.py'}
ITEM_KEYS = ('path', 'kind', 'revision', 'status', 'consumed', 'sha256', 'generated',
             'template_version', 'error', 'last_ok_revision', 'user_edits_preserved',
             'candidate')
STATUSES = ('ok', 'stale', 'failed')


def path_of(study_dir) -> Path:
    return Path(study_dir) / HOME / FILE


def empty() -> dict:
    return {'schema': SCHEMA, 'revision': None, 'status': 'not_rendered', 'artifacts': {}}


def load(study_dir) -> dict:
    """The manifest, or an empty one before the first render (or if unreadable)."""
    path = path_of(study_dir)
    if not path.is_file():
        return empty()
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        return empty()
    if not isinstance(data, dict) or not isinstance(data.get('artifacts'), dict):
        return empty()
    return data


def new_item(name: str, *, kind: str, generated: bool = True) -> dict:
    item = {k: None for k in ITEM_KEYS}
    item.update(path=ARTIFACTS[name], kind=kind, consumed=[], generated=generated,
                user_edits_preserved=[])
    return item


def item(manifest: Mapping, name: str, *, kind: str, generated: bool = True) -> dict:
    """A copy of the manifest item ``name``, completed with every key."""
    base = new_item(name, kind=kind, generated=generated)
    base.update(copy.deepcopy(manifest.get('artifacts', {}).get(name) or {}))
    return base


def summary(manifest: Mapping, state: Mapping) -> dict:
    """``{name: {status, path, revision, last_ok_revision, error, ..., message}}`` per
    artefact; ``message`` is one human sentence (:func:`currency.message`)."""
    out = {}
    for name in ARTIFACTS:
        raw = manifest.get('artifacts', {}).get(name)
        if raw is None:
            continue
        entry = {'status': effective_status(raw, state), 'path': raw.get('path'),
                 'revision': raw.get('revision'), 'last_ok_revision': raw.get('last_ok_revision'),
                 'error': raw.get('error')}
        if raw.get('generated') is False:
            entry['tracked'] = False
        if raw.get('candidate'):
            entry['candidate'] = raw['candidate']
        if raw.get('user_edits_preserved'):
            entry['user_edits_preserved'] = list(raw['user_edits_preserved'])
        entry['message'] = message(name, raw, state)
        out[name] = entry
    return out


def save(study_dir, manifest: Mapping) -> None:
    """Write the manifest atomically (call under the writer lock)."""
    from .store import atomic_write_json   # writer side, imported only to write

    atomic_write_json(path_of(study_dir), dict(manifest))
