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
