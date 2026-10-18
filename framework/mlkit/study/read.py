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


READ_ATTEMPTS = 3


def _read_optional(path: Path) -> str | None:
    """Text of ``path``, or None when it is absent or disappears while being read."""
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return None


def _load_once(home: Path) -> dict:
    # The pending digest is read first: a writer creates commit.pending.json before the
    # commit point and removes it after writing state.sha256, so a reader that sees the
    # new state.json with the old digest has either seen the pending file, or retries.
    pending_text = _read_optional(home / PENDING_FILE)
    try:
        pending = json.loads(pending_text) if pending_text is not None else None
    except ValueError:
        pending = None
    data = (home / st.STATE_FILE).read_bytes()
    sha_text = _read_optional(home / st.SHA_FILE)
    st.verify_integrity(data, sha_text,
                        pending_sha256=pending.get('state_sha256')
                        if isinstance(pending, dict) else None)
    try:
        return st.loads(data)
    except StudyError as exc:
        if exc.code == 'invalid_state':
            raise StudyError('integrity_error', 'state.json does not follow the study schema.',
                             details=exc.details) from exc
        raise


def load_state(study_dir) -> dict:
    """Read and verify ``state.json`` without the lock (the store uses it too).

    A read that overlaps a commit (between the commit point and the removal of
    ``commit.pending.json``) can see the new state with the old digest; it is retried
    (:data:`READ_ATTEMPTS` reads in all, review fix M3) before ``integrity_error`` is
    reported. A file that disappears while being read is treated as absent, never as an
    exception.
    """
    import time

    home = Path(study_dir).resolve() / HOME
    path = home / st.STATE_FILE
    for attempt in range(READ_ATTEMPTS):
        if not path.is_file():
            raise StudyError('study_missing', f'No study here: {path} does not exist.',
                             details={'study': str(Path(study_dir))})
        try:
            return _load_once(home)
        except StudyError as exc:
            if exc.code != 'integrity_error' or attempt == READ_ATTEMPTS - 1:
                raise
        except FileNotFoundError:
            if attempt == READ_ATTEMPTS - 1:
                raise StudyError('study_missing', f'No study here: {path} does not exist.',
                                 details={'study': str(Path(study_dir))}) from None
        time.sleep(0.01 * (attempt + 1))
    raise AssertionError('unreachable')


class Study:
    """A read-only snapshot of one study."""

    def __init__(self, study_dir):
        self.study_dir = Path(study_dir).resolve()
        self.home = self.study_dir / HOME
        self._state = load_state(self.study_dir)
        self._entries: dict[str, dict] = {}
        self._module_shas: dict[str, str | None] = {}
        self._currency: dict[str, dict] = {}
        self._sources: list[dict] | None = None

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
        """True when ``slot`` holds a result that :meth:`currency` finds current."""
        rid = self._state['current'].get(slot)
        return rid is not None and self.currency(rid)['current']

    def source_changes(self) -> list[dict]:
        """Case and dataset files whose bytes changed since ``init``
        (:func:`mlkit.study.case.source_changes`); read once per snapshot."""
        if self._sources is None:
            from .case import source_changes
            self._sources = source_changes(self._state)
        return copy.deepcopy(self._sources)

    def code_changed(self, entry: dict) -> list[str]:
        """Modules of ``entry``'s code fingerprint whose source differs now (§3.7 row 11)."""
        return sorted(name for name, sha in entry['code']['modules'].items()
                      if self._module_sha(name) != sha)

    def currency(self, rid: str) -> dict:
        """``{"current", "reason"}`` of result ``rid``, derived, never stored.

        A result is current when it is promoted in a slot, not marked stale, its
        activity's code is unchanged since it was computed (``reason.code_changed``, plan
        §3.7 row 11), and every result it was computed from (``inputs.results``, without
        history roles) is current too (``reason.upstream_not_current``). ``reason`` is
        the stored stale record, the derived one, or None.
        """
        if rid in self._currency:
            return copy.deepcopy(self._currency[rid])
        self._currency[rid] = {'current': False, 'reason': None}     # cycle guard
        state = self._state
        if self.source_changes():
            labels = [c['label'] for c in self.source_changes()]
            out = {'current': False,
                   'reason': {'reason': 'the ' + ' and '.join(labels) + ' file changed since the '
                                        'study started (§3.7 row 12)',
                              'since': None, 'sources_changed': labels}}
        elif rid not in set(state['current'].values()):
            out = {'current': False, 'reason': {'reason': 'not promoted in any slot',
                                                'since': None}}
        elif rid in state['stale']:
            out = {'current': False, 'reason': copy.deepcopy(state['stale'][rid])}
        else:
            try:
                entry = self.result(rid)
            except StudyError as exc:
                out = {'current': False, 'reason': {'reason': exc.code, 'since': None}}
            else:
                reason: dict = {}
                changed = self.code_changed(entry)
                if changed:
                    reason['code_changed'] = changed
                parents = [p for p in rec.upstream(entry, history=False)
                           if not self.currency(p)['current']]
                if parents:
                    reason['upstream_not_current'] = parents
                if reason:
                    text = []
                    if changed:
                        text.append(f'the code of {entry["activity"]} changed since it was '
                                    'computed (§3.7 row 11)')
                    if parents:
                        text.append('it was computed from a result that is no longer current')
                    reason = {'reason': '; '.join(text), 'since': None, **reason}
                out = {'current': not reason, 'reason': reason or None}
        self._currency[rid] = out
        return copy.deepcopy(out)

    def _module_sha(self, name: str) -> str | None:
        if name not in self._module_shas:
            path = _module_path(name)
            self._module_shas[name] = (hashlib.sha256(path.read_bytes()).hexdigest()
                                       if path is not None else None)
        return self._module_shas[name]

    def stale_reason(self, rid: str) -> dict | None:
        return copy.deepcopy(self._state['stale'].get(rid))

    def predictions(self, rid: str):
        """Persisted predictions of ``rid`` as a DataFrame (``row_key``, ``y``, ``score``).

        The blob is gzip-compressed CSV (plan §3.4). pandas is imported here only.
        Scores are parsed with ``float_precision='round_trip'``: pandas' default parser
        may differ from the written value in the last bit.
        """
        entry = self.result(rid)
        sha = entry['blobs'].get('predictions')
        if sha is None:
            raise StudyError('no_predictions', f'Result {rid} has no predictions blob.',
                             details={'result_id': rid, 'blobs': sorted(entry['blobs'])})
        import pandas as pd

        data = gzip.decompress(self.blob(sha))
        return pd.read_csv(io.BytesIO(data), dtype={'row_key': str}, keep_default_na=False,
                           float_precision='round_trip')

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
            path = _module_path(name)
            if path is None:
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


def _module_path(name: str) -> Path | None:
    """The source file of module ``name`` (located, not imported), or None."""
    try:
        spec = importlib.util.find_spec(name)
    except (ImportError, ValueError):
        return None
    path = Path(spec.origin) if spec is not None and spec.origin else None
    return path if path is not None and path.is_file() else None


def open(study_dir) -> Study:   # noqa: A001 - the documented name of the read API
    """Open ``study_dir`` read-only (``integrity_error`` if its state diverges)."""
    return Study(study_dir)

