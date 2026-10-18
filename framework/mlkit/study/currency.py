"""The pure currency rule of deliverables (plan §3.6; ``CLI-CONTRACT.md`` §8.3).

**An artefact is current** iff its recorded status is ``ok``, the revision it was
written for equals the state revision, and every result it consumes is still current
(promoted and not stale). The workbench (``generated: false``) is never stale: it is
created once and its experiments are not tracked.

Shared by :mod:`mlkit.study.manifest` (the writer side) and :mod:`mlkit.study.view`
(the read side, which may not import a module that writes). No I/O.
"""
from __future__ import annotations

from typing import Mapping


def consumed_current(item: Mapping, state: Mapping) -> bool:
    promoted = set(state['current'].values())
    return all(rid in promoted and rid not in state['stale'] for rid in item.get('consumed') or [])


def effective_status(item: Mapping | None, state: Mapping) -> str:
    """``ok``, ``stale``, ``failed``, or ``not_rendered`` for ``item`` against ``state``."""
    if not item:
        return 'not_rendered'
    status = item.get('status')
    if status == 'failed':
        return 'failed'
    if status != 'ok':
        return status or 'not_rendered'
    if item.get('generated') is False:
        return 'ok'
    if item.get('revision') != state['revision'] or not consumed_current(item, state):
        return 'stale'
    return 'ok'


NAMES = {'report': 'report', 'notebook': 'generated notebook', 'workbench': 'workbench'}


def message(name: str, item: Mapping | None, state: Mapping) -> str:
    """One sentence an agent can repeat to the junior about artefact ``name`` (D7).

    After a failed render it says that the previous file is kept and marked stale at the
    failed revision, and which revision its content comes from.
    """
    label = NAMES.get(name, name)
    path = (item or {}).get('path') or label
    revision = state['revision']
    status = effective_status(item, state)
    if status == 'not_rendered':
        return f'The {label} ({path}) has not been rendered yet.'
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
    if status == 'stale':
        if attempted != revision:
            return (f'The {label} ({path}) is stale: it was written at revision {attempted} and '
                    f'the study is at revision {revision}. Render again before relying on it.')
        return (f'The {label} ({path}) is stale: it cites a result that is no longer current. '
                f'Render again before relying on it.')
    return f'The {label} ({path}) is up to date at revision {revision}.'


def overall(statuses) -> str:
    statuses = list(statuses)
    if not statuses:
        return 'not_rendered'
    for s in ('failed', 'stale', 'not_rendered'):
        if s in statuses:
            return s
    return 'ok'
