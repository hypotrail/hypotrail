"""The pure currency rule of deliverables (plan §3.6; ``CLI-CONTRACT.md`` §8.3).

**An artefact is current** iff its recorded status is ``ok``, the revision it was
written for equals the state revision, and every result it consumes is still current
(promoted and not stale), **and** (review fix M4) its file exists with the bytes the
manifest records. The editable copy and workbench (``generated: false``) are never stale:
their experiments are not tracked as evidence.

Shared by :mod:`mlkit.study.manifest` (the writer side) and :mod:`mlkit.study.view`
(the read side, which may not import a module that writes). The rule itself is pure;
:func:`file_check` is the one function that reads (never writes) a deliverable's bytes, and
its result is passed to the rule as ``file``.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Mapping

# Why a recorded ``ok`` deliverable is not current (``stale_reason``; M4 adds the two
# file reasons, which take precedence: the file on disk is what a reader opens).
FILE_MISSING = 'file_missing'
FILE_CHANGED = 'file_changed'
REVISION_CHANGED = 'revision_changed'
RESULT_NOT_CURRENT = 'result_not_current'
STALE_REASONS = (FILE_MISSING, FILE_CHANGED, REVISION_CHANGED, RESULT_NOT_CURRENT)

# Marimo rewrites this stamp when it saves; it is not an edit (render_notebook uses it too).
GENERATED_WITH = re.compile(rb'^__generated_with = "[^"\n]*"$', re.MULTILINE)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def edit_check_sha256(data: bytes) -> str:
    """Hash used to detect user edits; only the ``__generated_with`` stamp is ignored."""
    return sha256(GENERATED_WITH.sub(b'__generated_with = ""', data))


def file_fingerprint(study_dir, item: Mapping | None) -> str | None:
    """The hash :func:`file_check` compares for ``item``'s file now (``edit_check_sha256``
    when the item records one, else ``sha256``), or None when the file cannot be read."""
    if study_dir is None or not item or not isinstance(item.get('path'), str):
        return None
    try:
        data = (Path(study_dir) / item['path']).read_bytes()
    except OSError:
        return None
    return edit_check_sha256(data) if item.get('edit_check_sha256') else sha256(data)


def file_check(study_dir, item: Mapping | None) -> str | None:
    """``file_missing``, ``file_changed``, or None (the file is the one recorded, or the
    item is not a recorded ``ok`` generated deliverable, so its file is not checked).

    The bytes are compared with ``edit_check_sha256`` when the item records one (the
    generated notebook: Marimo's ``__generated_with`` stamp is ignored), else with
    ``sha256``. Reads the file; writes nothing."""
    if study_dir is None or not item or item.get('status') != 'ok' \
            or item.get('generated') is False or not isinstance(item.get('path'), str):
        return None
    path = Path(study_dir) / item['path']
    try:
        data = path.read_bytes()
    except OSError:
        return FILE_MISSING
    if item.get('edit_check_sha256'):
        return None if edit_check_sha256(data) == item['edit_check_sha256'] else FILE_CHANGED
    if item.get('sha256'):
        return None if sha256(data) == item['sha256'] else FILE_CHANGED
    return None


def consumed_current(item: Mapping, state: Mapping, is_current=None) -> bool:
    """Every result ``item`` consumes is current: promoted and not stale, and, with
    ``is_current`` (``read.Study.currency``), current by lineage and code as well."""
    promoted = set(state['current'].values())
    return all(rid in promoted and rid not in state['stale']
               and (is_current is None or is_current(rid))
               for rid in item.get('consumed') or [])


def stale_reason(item: Mapping | None, state: Mapping, is_current=None,
                 file: str | None = None) -> str | None:
    """Why a recorded ``ok`` generated deliverable is ``stale`` (:data:`STALE_REASONS`), or
    None. ``file`` is the result of :func:`file_check` for that item."""
    if not item or item.get('status') != 'ok' or item.get('generated') is False:
        return None
    if file in (FILE_MISSING, FILE_CHANGED):
        return file
    if item.get('revision') != state['revision']:
        return REVISION_CHANGED
    if not consumed_current(item, state, is_current):
        return RESULT_NOT_CURRENT
    return None


def effective_status(item: Mapping | None, state: Mapping, is_current=None,
                     file: str | None = None) -> str:
    """``ok``, ``stale``, ``failed``, or ``not_rendered`` for ``item`` against ``state``.

    ``file`` is :func:`file_check` of the item: a deleted or changed file is ``stale``."""
    if not item:
        return 'not_rendered'
    status = item.get('status')
    if status == 'failed':
        return 'failed'
    if status != 'ok':
        return status or 'not_rendered'
    if item.get('generated') is False:
        return 'ok'
    return 'stale' if stale_reason(item, state, is_current, file) else 'ok'


NAMES = {'report': 'report', 'notebook': 'generated notebook',
         'editable': 'editable study notebook', 'workbench': 'workbench'}


def message(name: str, item: Mapping | None, state: Mapping, is_current=None,
            file: str | None = None) -> str:
    """One sentence an agent can repeat to the junior about artefact ``name`` (D7).

    After a failed render it says that the previous file is kept and marked stale at the
    failed revision, and which revision its content comes from.
    """
    label = NAMES.get(name, name)
    path = (item or {}).get('path') or label
    revision = state['revision']
    status = effective_status(item, state, is_current, file)
    if status == 'not_rendered':
        return f'The {label} ({path}) has not been rendered yet.'
    if (item or {}).get('generated') is False and name == 'editable':
        return (f'The editable study notebook ({path}) follows the generated notebook until '
                f'you edit it; after that it is never overwritten and does not count as '
                f'official evidence.')
    if (item or {}).get('generated') is False:
        return (f'The {label} ({path}) is the junior\'s free space: created once, never '
                f'overwritten, and not tracked by the study.')
    attempted = item.get('revision')
    last_ok = item.get('last_ok_revision')
    if status == 'failed':
        what = 'render' if name == 'report' else 'generation'
        if last_ok is None:
            return (f'The {label} {what} failed at revision {attempted}; there was no previous '
                    f'{label} to keep, so nothing in {path} is current.')
        return (f'The {label} {what} failed at revision {attempted}: previous {label} kept and '
                f'marked stale at revision {attempted}. Its content is from revision {last_ok}; '
                f'do not rely on it until a render succeeds.')
    # P3 (post-v0.1): an up-to-date or stale message holds no revision number, so a resume
    # recap that repeats it holds none either; the item's ``revision`` fields keep them.
    if status == 'stale':
        if file == FILE_MISSING:
            return (f'The {label} ({path}) is stale: the file was deleted or moved after it was '
                    f'written. Render again before relying on it.')
        if file == FILE_CHANGED:
            return (f'The {label} ({path}) is stale: the file was changed after it was '
                    f'written, so it is not what the study wrote. Render again before relying '
                    f'on it.')
        if attempted != revision:
            return (f'The {label} ({path}) is stale: the study changed after it was written. '
                    f'Render again before relying on it.')
        return (f'The {label} ({path}) is stale: it cites a result that is no longer current. '
                f'Render again before relying on it.')
    return f'The {label} ({path}) is up to date.'


def overall(statuses) -> str:
    statuses = list(statuses)
    if not statuses:
        return 'not_rendered'
    for s in ('failed', 'stale', 'not_rendered'):
        if s in statuses:
            return s
    return 'ok'
