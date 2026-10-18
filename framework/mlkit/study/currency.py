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


def overall(statuses) -> str:
    statuses = list(statuses)
    if not statuses:
        return 'not_rendered'
    for s in ('failed', 'stale', 'not_rendered'):
        if s in statuses:
            return s
    return 'ok'
