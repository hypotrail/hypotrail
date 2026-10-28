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
deliverables. Level 2 (lot L8) adds where the computation is: the fingerprinted modules call
:func:`step` at each outer fold of a cross-validated fit (``fit``), each value of an inner
tuning grid (``families.choose``) and each bootstrap replicate (``policy``, ``regression``,
``objective``), and the activity's phase writes it into its lines:

    Le modèle logistique · pli 2/5 · pénalité 3/5 · 14 s

:func:`step` does nothing unless a reporter listens (a ``ContextVar`` set only by the phase
of ``run --progress``), so the computed values never depend on it. A fold line is written at
each new fold; the finer steps (a grid value, a replicate) at most once per
:data:`DETAIL_SECONDS`, and every heartbeat repeats the current position.
When stderr is a terminal the heartbeat rewrites one line (carriage return); otherwise each
heartbeat is a line of its own. stdout is never touched, so the run's JSON document is the
same with or without the flag, and without the flag nothing at all is written to stderr
(CLI-CONTRACT §1). A reporter never reads or writes the study, and a failed write to stderr
(a closed pipe) is ignored: progress never changes a run's outcome.
"""
from __future__ import annotations

import contextvars
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
# Level 2 (L8): the steps of a computation, outermost first, and their words. A grid of a
# penalty (``C``, ``alpha``) says so; any other grid is a "grid value".
STEP_KINDS = ('fold', 'grid', 'replicate')
STEP_WORDS = {'en': {'fold': 'fold', 'grid': 'grid value', 'penalty': 'penalty',
                     'replicate': 'bootstrap replicate'},
              'fr': {'fold': 'pli', 'grid': 'valeur de la grille', 'penalty': 'pénalité',
                     'replicate': 'réplication bootstrap'}}
PENALTY_PARAMETERS = ('C', 'alpha')
# A finer step than a fold writes a line at most this often (seconds).
DETAIL_SECONDS = 1.0
_LISTENER: contextvars.ContextVar = contextvars.ContextVar('hypotrail_progress_step',
                                                           default=None)


def step(kind: str, index: int, total: int, parameter: str | None = None) -> None:
    """Level 2 (L8): the computation reached step ``index`` of ``total`` of ``kind`` (a
    fold, a grid value, a bootstrap replicate). Called from the fingerprinted modules; it
    does nothing unless the phase of ``run --progress`` listens, and it never raises."""
    listener = _LISTENER.get()
    if listener is not None:
        try:
            listener(kind, index, total, parameter)
        except Exception:                 # progress never changes a run's outcome
            pass


def step_words(kind: str, index: int, total: int, parameter: str | None,
               language: str = 'en') -> str:
    """``pli 2/5``, ``pénalité 3/5``, ``bootstrap replicate 120/200``."""
    words = STEP_WORDS.get(language, STEP_WORDS['en'])
    name = 'penalty' if kind == 'grid' and parameter in PENALTY_PARAMETERS else kind
    return f'{words.get(name, name)} {index}/{total}'


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
        self._steps: dict = {}            # level 2: kind -> (index, total, parameter)
        self._detail_at: float | None = None

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

    def _detail(self) -> str:
        """The current position (level 2), outermost first: ``pli 2/5 · pénalité 3/5``."""
        steps = self._steps               # replaced, never mutated: safe from the heartbeat
        return ' · '.join(step_words(kind, *steps[kind], language=self.language)
                          for kind in STEP_KINDS if kind in steps)

    def _running(self, label: str, start: float) -> str:
        _, running, _, _ = STATES[self.language]
        detail = self._detail()
        where = f' · {detail}' if detail else ''
        return f'{label} · {running}{where} · {elapsed_words(self.clock() - start)}'

    def _step(self, label: str, start: float, kind: str, index: int, total: int,
              parameter: str | None) -> None:
        """Level 2 (L8): record the step (a coarser step clears the finer ones) and write a
        line at each new fold, at most every :data:`DETAIL_SECONDS` for a finer step."""
        if kind not in STEP_KINDS:
            return
        level = STEP_KINDS.index(kind)
        steps = {k: v for k, v in self._steps.items() if STEP_KINDS.index(k) < level}
        steps[kind] = (int(index), int(total), parameter)
        self._steps = steps
        now = self.clock()
        if level > 0 and self._detail_at is not None \
                and now - self._detail_at < DETAIL_SECONDS:
            return
        self._detail_at = now
        self._write(self._running(label, start), end=False)

    @contextmanager
    def phase(self, label: str, *, steps: bool = False) -> Iterator[None]:
        """One phase: its start line, a heartbeat every ``interval`` seconds while the
        body runs (from a daemon thread), and its end line with the elapsed time ("stopped
        after" when the body raised). With ``steps`` (the activity's computation, L8) the
        body's :func:`step` calls are written into its lines."""
        started, running, done, stopped = STATES[self.language]
        start = self.clock()
        self._steps, self._detail_at = {}, None
        self._write(f'{label} · {started}', end=False)
        finished = threading.Event()

        def beat() -> None:
            k = 1
            while not finished.wait(max(0.0, start + k * self.interval - self.clock())):
                self._write(self._running(label, start), end=False)
                k += 1

        thread = threading.Thread(target=beat, name='hypotrail-progress', daemon=True)
        thread.start()
        token = _LISTENER.set(
            (lambda kind, index, total, parameter: self._step(label, start, kind, index,
                                                              total, parameter))
            if steps else None)
        ok = False
        try:
            yield
            ok = True
        finally:
            _LISTENER.reset(token)
            finished.set()
            thread.join()
            self._steps = {}
            words = elapsed_words(self.clock() - start)
            self._write(f'{label} · {done if ok else stopped} {words}', end=True)

    def activity(self, activity: str):
        return self.phase(activity_label(activity, self.language), steps=True)

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
