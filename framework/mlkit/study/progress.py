"""Progress lines of ``hypotrail run --progress`` on stderr (owner session 2026-10-26, L4, R10
level 1).

A long run (a fit on Hotel takes minutes, its diagnostics about 4.5 minutes) printed nothing
until its one JSON document. With ``--progress`` the run writes, on **stderr** only, one line
when a phase starts, a heartbeat at least every :data:`HEARTBEAT_SECONDS` while it runs, and
one line when it ends, with the elapsed time, in plain words of the study language:

    Le modèle logistique · démarré
    Le modèle logistique · en cours · 40 s
    Le modèle logistique · terminé en 1 min 12 s

The phases of level 1 are the activity's computation and the regeneration of the
deliverables; fold-by-fold lines need calls inside the fingerprinted fit modules (lot L8).
When stderr is a terminal the heartbeat rewrites one line (carriage return); otherwise each
heartbeat is a line of its own. stdout is never touched, so the run's JSON document is the
same with or without the flag, and without the flag nothing at all is written to stderr
(CLI-CONTRACT §1). A reporter never reads or writes the study, and a failed write to stderr
(a closed pipe) is ignored: progress never changes a run's outcome.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Callable, Iterator, TextIO

from . import audience

HEARTBEAT_SECONDS = 10.0
# Test hook (``HYPOTRAIL_TEST_HOOKS=1`` only, read by ``cmd_run``): a shorter heartbeat, so a
# process test does not wait ten seconds per line.
INTERVAL_ENV = 'HYPOTRAIL_PROGRESS_INTERVAL'
STATES = {'en': ('started', 'running', 'done in', 'stopped after'),
          'fr': ('démarré', 'en cours', 'terminé en', 'arrêté après')}
DELIVERABLES = {'en': 'The report and the notebook', 'fr': 'Le rapport et le notebook'}


def elapsed_words(seconds: float) -> str:
    """``40 s``, ``1 min 12 s``, ``3 min`` (the same in English and French)."""
    total = int(seconds)
    minutes, rest = divmod(total, 60)
    if not minutes:
        return f'{rest} s'
    return f'{minutes} min {rest} s' if rest else f'{minutes} min'


def activity_label(activity: str, language: str) -> str:
    """The activity in the junior's words, capitalised: "Le modèle logistique"."""
    words = audience.activity_words(activity, language)
    return words[:1].upper() + words[1:]


class Reporter:
    """Writes the progress lines of one run to ``stream`` in ``language``."""

    def __init__(self, stream: TextIO, language: str = 'en', *,
                 interval: float = HEARTBEAT_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.stream, self.interval, self.clock = stream, float(interval), clock
        self.language = language if language in STATES else 'en'
        try:
            self.tty = bool(stream.isatty())
        except (AttributeError, ValueError, OSError):
            self.tty = False
        self._width = 0
        self._lock = threading.Lock()

    def _write(self, line: str, *, end: bool) -> None:
        with self._lock:
            try:
                if self.tty:
                    pad = ' ' * max(0, self._width - len(line))
                    self.stream.write('\r' + line + pad + ('\n' if end else ''))
                    self._width = 0 if end else len(line)
                else:
                    self.stream.write(line + '\n')
                self.stream.flush()
            except (OSError, ValueError):
                pass                     # a closed stderr never changes the run

    @contextmanager
    def phase(self, label: str) -> Iterator[None]:
        """One phase: its start line, a heartbeat every ``interval`` seconds while the
        body runs (from a daemon thread), and its end line with the elapsed time ("stopped
        after" when the body raised)."""
        started, running, done, stopped = STATES[self.language]
        start = self.clock()
        self._write(f'{label} · {started}', end=False)
        finished = threading.Event()

        def beat() -> None:
            k = 1
            while not finished.wait(max(0.0, start + k * self.interval - self.clock())):
                self._write(f'{label} · {running} · {elapsed_words(self.clock() - start)}',
                            end=False)
                k += 1

        thread = threading.Thread(target=beat, name='hypotrail-progress', daemon=True)
        thread.start()
        ok = False
        try:
            yield
            ok = True
        finally:
            finished.set()
            thread.join()
            words = elapsed_words(self.clock() - start)
            self._write(f'{label} · {done if ok else stopped} {words}', end=True)

    def activity(self, activity: str):
        return self.phase(activity_label(activity, self.language))

    def deliverables(self):
        return self.phase(DELIVERABLES[self.language])


@contextmanager
def nothing() -> Iterator[None]:
    yield


def phase_of(reporter: 'Reporter | None', which: str, *args):
    """``reporter.<which>(*args)``, or a context that does nothing without a reporter."""
    if reporter is None:
        return nothing()
    return getattr(reporter, which)(*args)
