"""The ``understanding`` extension of the study state, identifiers and input limits.

The extension is optional (``state['understanding']``); a state without it reads as
``off``. It holds an index of small records whose large parts (policy documents, plans,
snapshots, answers, proposals, handover content, export projections) are immutable
content-addressed blobs of the study (``.hypotrail/blobs/``), never written into
``revisions.jsonl``, ``events.jsonl`` or a command output: a request names a blob by its
SHA-256, and only that digest and its size enter the revision log.

Schema ``hypotrail.understanding-state/1``; a future version is refused for writing
(:func:`require_writable`) and read as ``unsupported`` by ``status``.
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any, Mapping

from . import STATE_SCHEMA, canonical, refuse

COLLECTIONS = ('policy_events', 'sessions', 'attempts', 'assistance_events', 'proposals',
               'decisions', 'reservations', 'arbitrations', 'handovers', 'transfers',
               'selections', 'waivers', 'approvals', 'exports', 'milestones', 'receipts')
SESSION_STATUSES = ('planned', 'active', 'awaiting_review', 'completed', 'abandoned')
TRANSITIONS = {'planned': ('active', 'abandoned'),
               'active': ('awaiting_review', 'completed', 'abandoned'),
               'awaiting_review': ('active', 'completed', 'abandoned'),
               'completed': (), 'abandoned': ()}
DIMENSION_STATUSES = ('not_evaluated', 'demonstrated', 'to_consolidate', 'needs_review')
CRITERION_RESULTS = ('met', 'not_met', 'not_applicable', 'uncertain')
DECLARATION_SOURCES = ('reviewer_cli', 'reviewer_file', 'chat_relay')
ACTOR = re.compile(r'[a-z][a-z0-9_-]{1,31}')
MAX_RESPONSE_BYTES = 64 * 1024
MAX_JSON_BYTES = 256 * 1024
MAX_LIST = 64
MAX_TEXT = 8000
MAX_DEPTH = 12


def empty(salt: str | None = None) -> dict:
    return {'schema': STATE_SCHEMA, 'salt': salt or secrets.token_hex(16), 'policy': None,
            **{k: ([] if k in ('policy_events', 'assistance_events') else {})
               for k in COLLECTIONS}}


def of(state: Mapping) -> dict | None:
    return state.get('understanding')


def require_writable(state: dict) -> dict:
    """The extension of ``state`` for a write, created when absent; a future or unknown
    schema is refused."""
    ext = state.get('understanding')
    if ext is None:
        ext = state['understanding'] = empty()
        return ext
    if not isinstance(ext, dict) or ext.get('schema') != STATE_SCHEMA:
        raise refuse('policy_invalid', 'This study holds an understanding state of an unknown '
                     'or newer version; this engine does not write it.',
                     'Use the engine version that wrote it.',
                     found=ext.get('schema') if isinstance(ext, dict) else None)
    for k in COLLECTIONS:
        ext.setdefault(k, [] if k in ('policy_events', 'assistance_events') else {})
    return ext


def check(ext: Any) -> list[dict]:
    """Schema problems of the extension (the study state check calls it)."""
    if not isinstance(ext, dict):
        return [{'path': 'understanding', 'problem': 'must be a mapping'}]
    if ext.get('schema') != STATE_SCHEMA:
        return []          # a newer version: readable as unsupported, never written
    problems = []
    if not isinstance(ext.get('salt'), str):
        problems.append({'path': 'understanding.salt', 'problem': 'must be text'})
    for k in COLLECTIONS:
        want = list if k in ('policy_events', 'assistance_events') else dict
        if k in ext and not isinstance(ext[k], want):
            problems.append({'path': f'understanding.{k}', 'problem': f'must be a {want.__name__}'})
    return problems


def new_id(prefix: str, request_id: str, *parts: str) -> str:
    """An opaque identifier derived from the request (a replay gets the same one)."""
    return f'{prefix}-' + canonical.sha256_hex(
        '\0'.join((prefix, request_id) + parts).encode())[:16]


def actor(value: Any, field: str) -> str:
    if not isinstance(value, str) or not ACTOR.fullmatch(value):
        raise refuse('evidence_invalid', f'{field} must be a declared alias: 2 to 32 '
                     'lowercase letters, digits, - or _ (no e-mail, no full name).',
                     'Use a stable project alias.', field=field)
    return value


def text(value: Any, field: str, *, limit: int = MAX_TEXT, empty_ok: bool = False) -> str:
    if not isinstance(value, str) or (not empty_ok and not value.strip()) or len(value) > limit:
        raise refuse('evidence_invalid', f'{field} must be a text of at most {limit} '
                     'characters.', 'Shorten or complete the field.', field=field)
    return value


def str_list(value: Any, field: str, *, limit: int = MAX_LIST) -> list:
    if not isinstance(value, list) or len(value) > limit \
            or any(not isinstance(v, str) or not v or len(v) > 400 for v in value):
        raise refuse('evidence_invalid', f'{field} must be a list of at most {limit} short '
                     'texts.', 'Correct the list.', field=field)
    return value


def _depth(value: Any, depth: int = 0) -> int:
    if depth > MAX_DEPTH:
        return depth
    if isinstance(value, dict):
        return max([_depth(v, depth + 1) for v in value.values()] or [depth])
    if isinstance(value, list):
        return max([_depth(v, depth + 1) for v in value] or [depth])
    return depth


def read_input_bytes(path, field: str, limit: int) -> bytes:
    """The bytes of an input file named explicitly on the command line (size limited).
    The content is never echoed in a refusal."""
    p = Path(path)
    try:
        if not p.is_file():
            raise refuse('evidence_invalid', f'{field} is not a readable file.',
                         'Give the path of a regular file.', field=field)
        if p.stat().st_size > limit:
            raise refuse('evidence_invalid', f'{field} is larger than {limit} bytes.',
                         'Shorten it.', field=field, limit=limit)
        return p.read_bytes()
    except OSError as exc:
        raise refuse('evidence_invalid', f'{field} cannot be read ({exc.__class__.__name__}).',
                     'Give a readable file.', field=field) from None


def read_json_input(path, field: str) -> Any:
    data = read_input_bytes(path, field, MAX_JSON_BYTES)
    try:
        value = json.loads(data.decode('utf-8'),
                           object_pairs_hook=canonical._pairs,
                           parse_constant=canonical._no_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise refuse('evidence_invalid', f'{field} is not valid JSON (duplicate keys and '
                     'NaN are refused).', 'Correct the file.', field=field,
                     reason=exc.__class__.__name__) from None
    if _depth(value) > MAX_DEPTH:
        raise refuse('evidence_invalid', f'{field} is nested deeper than {MAX_DEPTH} levels.',
                     'Flatten the document.', field=field)
    return value


def read_text_input(path, field: str) -> str:
    data = read_input_bytes(path, field, MAX_RESPONSE_BYTES)
    try:
        text_ = data.decode('utf-8')
    except UnicodeDecodeError:
        raise refuse('evidence_invalid', f'{field} is not UTF-8 text.', 'Save it as UTF-8.',
                     field=field) from None
    if not text_.strip():
        raise refuse('evidence_invalid', f'{field} is empty. "I do not know" is an acceptable '
                     'answer; an empty file is not.', 'Write the answer in your own words.',
                     field=field)
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in text_):
        raise refuse('evidence_invalid', f'{field} holds an invalid character.',
                     'Save it as UTF-8.', field=field)
    return text_
