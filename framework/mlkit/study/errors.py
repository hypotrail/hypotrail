"""Structured refusals of the study engine.

Every refusal has a stable ``code`` that clients (the chat agent, the CLI, and later
a webview) can branch on, a human ``message``, and optional ``details``. Command
refusals raised by :func:`mlkit.reliability.apply_command` use the same shape
(:class:`mlkit.reliability.CommandRefused`).
"""
from __future__ import annotations


class StudyError(ValueError):
    """A refusal without effect. ``to_dict()`` is the machine-readable form."""

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        out = {'code': self.code, 'message': self.message}
        if self.details:
            out['details'] = self.details
        return out


# Advanced companion (CLI-CONTRACT-COMPANION §13). A command, option, or ``preview`` kind
# that is registered but not implemented yet is refused with ``unsupported_capability``,
# ``details.command`` naming it and ``details.reason`` this value. Each engine work
# package replaces its own stubs. A refused stub reads and writes nothing.
NOT_IMPLEMENTED = 'not_implemented'


def not_implemented(command: str) -> StudyError:
    """The refusal of a reserved, not yet implemented companion command (CC §13)."""
    return StudyError('unsupported_capability',
                      f'{command} is reserved for the advanced companion and is not '
                      'implemented in this version. Nothing was read or written.',
                      details={'command': command, 'reason': NOT_IMPLEMENTED})
