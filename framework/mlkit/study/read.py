"""Strictly read-only access to a study (plan WP1.3, §6).

This is the API that the generated notebook, the workbench, the HTML renderer, and a
future webview use. It never writes, never takes the writer lock, and never repairs
anything: an inconsistent study is refused with ``integrity_error`` rather than
fixed. ``framework/tests/study/test_read_view.py`` checks by AST scan that this
module calls no write primitive and imports no writer module (``store``, ``lock``,
``registry``, ``exposure``, ``dependencies``, ``commands``, ``cli``, ``migrate``).

Usage::

    from mlkit.study import read
    study = read.open(study_dir)
    study.revision                    # revision of the snapshot
    study.current('fit.logistic')     # verified registry entry, or None
    study.result(rid)                 # verified registry entry
    study.predictions(rid)            # pandas DataFrame (row_key, y, score); lazy pandas
    study.source('fit.logistic')      # {modules: {name: text}, fingerprint_matches}

The state is read once, when the study is opened: every call answers from that
snapshot, so a renderer sees one consistent revision. pandas is imported only by
:meth:`Study.predictions`.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path

from . import records as rec
from . import state as st
from .errors import StudyError

HOME = '.hypotrail'
PENDING_FILE = 'commit.pending.json'
REVISIONS_FILE = 'revisions.jsonl'
EXPOSURE_FILE = 'exposure.jsonl'
ARTIFACTS_FILE = 'artifacts.json'
REGISTRY_DIR = 'registry'
BLOBS_DIR = 'blobs'


def _jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def load_state(study_dir) -> dict:
    """Read and verify ``state.json`` without the lock (same rules as the store)."""
    home = Path(study_dir).resolve() / HOME
    path = home / st.STATE_FILE
    if not path.is_file():
        raise StudyError('study_missing', f'No study here: {path} does not exist.',
                         details={'study': str(Path(study_dir))})
    data = path.read_bytes()
    sha_path = home / st.SHA_FILE
    sha_text = sha_path.read_text(encoding='utf-8') if sha_path.is_file() else None
    pending = None
    if (home / PENDING_FILE).is_file():
        try:
            pending = json.loads((home / PENDING_FILE).read_text(encoding='utf-8'))
        except ValueError:
            pending = None
    st.verify_integrity(data, sha_text,
                        pending_sha256=pending.get('state_sha256') if pending else None)
    try:
        return st.loads(data)
    except StudyError as exc:
        if exc.code == 'invalid_state':
            raise StudyError('integrity_error', 'state.json does not follow the study schema.',
                             details=exc.details) from exc
        raise


class Study:
    """A read-only snapshot of one study."""

    def __init__(self, study_dir):
        self.study_dir = Path(study_dir).resolve()
        self.home = self.study_dir / HOME
        self._state = load_state(self.study_dir)
        self._entries: dict[str, dict] = {}

    # state

    @property
    def state(self) -> dict:
        """A deep copy of the snapshot state; mutating it changes nothing on disk."""
        return copy.deepcopy(self._state)

    @property
    def revision(self) -> int:
        return self._state['revision']

    def revisions(self, since: int = 0) -> list[dict]:
        """Committed revision records after ``since`` (``status --since``)."""
        return [r for r in _jsonl(self.home / REVISIONS_FILE)
                if r.get('revision', 0) > since and r['revision'] <= self.revision]

    # blobs and results

    def blob(self, sha: str) -> bytes:
        path = self.home / BLOBS_DIR / sha
        if not sha or '/' in sha or not path.is_file():
            raise StudyError('integrity_error', f'Blob {sha} is missing.', details={'sha256': sha})
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            raise StudyError('integrity_error', f'Blob {sha} does not match its digest.',
                             details={'sha256': sha})
        return data

    def result(self, rid: str) -> dict:
        """The registry entry ``rid``, with identity and blobs verified."""
        if rid in self._entries:
            return copy.deepcopy(self._entries[rid])
        path = self.home / REGISTRY_DIR / f'{rid}.json'
        if not isinstance(rid, str) or not rid or '/' in rid or rid.startswith('.') \
                or not path.is_file():
            raise StudyError('unknown_result', f'No result {rid} in the registry.',
                             details={'result_id': rid})
        try:
            entry = json.loads(path.read_text(encoding='utf-8'))
        except ValueError as exc:
            raise StudyError('integrity_error', f'Registry entry {rid} is not valid JSON.',
                             details={'result_id': rid}) from exc
        rec.verify_entry(rid, entry)
        for sha in entry['blobs'].values():
            self.blob(sha)
        self._entries[rid] = entry
        return copy.deepcopy(entry)

    def current(self, slot: str) -> dict | None:
        """The verified entry promoted in ``slot``, or None. A stale one is returned
        too; check :meth:`is_current`."""
        rid = self._state['current'].get(slot)
        return self.result(rid) if rid else None

    def is_current(self, slot: str) -> bool:
        return st.is_current(self._state, slot)

    def stale_reason(self, rid: str) -> dict | None:
        return copy.deepcopy(self._state['stale'].get(rid))

    def predictions(self, rid: str):
        """Persisted predictions of ``rid`` as a DataFrame (``row_key``, ``y``, ``score``).

        The blob is gzip-compressed CSV (plan §3.4). pandas is imported here only.
        """
        entry = self.result(rid)
        sha = entry['blobs'].get('predictions')
        if sha is None:
            raise StudyError('no_predictions', f'Result {rid} has no predictions blob.',
                             details={'result_id': rid, 'blobs': sorted(entry['blobs'])})
        import pandas as pd

        data = gzip.decompress(self.blob(sha))
        return pd.read_csv(io.BytesIO(data), dtype={'row_key': str}, keep_default_na=False)

    def source(self, activity: str) -> dict:
        """Source code of the modules an activity's current result was computed with.

        Returns ``{"activity", "result_id", "modules": {name: text}, "fingerprint",
        "fingerprint_matches"}``. ``fingerprint_matches`` is False when a module changed
        after the result was computed (the displayed code is then not what ran).
        Modules are located with ``importlib.util.find_spec`` and read, not imported.
        """
        entry = self.current(activity)
        if entry is None:
            raise StudyError('unknown_result', f'No current result for {activity}.',
                             details={'slot': activity})
        texts, shas = {}, {}
        for name in sorted(entry['code']['modules']):
            spec = importlib.util.find_spec(name)
            path = Path(spec.origin) if spec is not None and spec.origin else None
            if path is None or not path.is_file():
                texts[name], shas[name] = None, None
                continue
            raw = path.read_bytes()
            texts[name] = raw.decode('utf-8')
            shas[name] = hashlib.sha256(raw).hexdigest()
        return {'activity': activity, 'result_id': entry['result_id'], 'modules': texts,
                'fingerprint': entry['code']['fingerprint'],
                'fingerprint_matches': shas == entry['code']['modules']}

    # exposure and artifacts

    def exposure_records(self) -> list[dict]:
        return _jsonl(self.home / EXPOSURE_FILE)

    def exposure_summary(self) -> dict:
        entries = self.exposure_records()
        keys = {e['exposure_id']: rec.parse_row_keys(self.blob(e['row_keys'])) for e in entries}
        return rec.summarize(entries, keys, self._state['prior_exposure'])

    def artifacts(self) -> dict | None:
        """The artefact manifest (``artifacts.json``, plan §3.6), or None before any render."""
        path = self.home / ARTIFACTS_FILE
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except ValueError:
            return {'status': 'unreadable'}


def open(study_dir) -> Study:   # noqa: A001 - the documented name of the read API
    """Open ``study_dir`` read-only (``integrity_error`` if its state diverges)."""
    return Study(study_dir)

