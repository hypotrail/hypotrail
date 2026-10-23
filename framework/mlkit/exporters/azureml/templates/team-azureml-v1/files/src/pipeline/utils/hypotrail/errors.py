"""Structured refusals of the exported project (Hypotrail contract v1 §8).

A refusal has a stable ``code``, the ``path`` concerned, a ``message`` and a
``remediation``; ``project.py`` prints it as JSON and exits with code 2. Nothing is
written after a refusal.
"""

from __future__ import annotations

import json


class ProjectError(RuntimeError):
    """A refusal without effect."""

    def __init__(
        self: ProjectError,
        code: str,
        message: str,
        *,
        path: str | None = None,
        remediation: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Record the refusal fields."""
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.path = path
        self.remediation = remediation
        self.details = details or {}

    def to_dict(self: ProjectError) -> dict:
        """Return the JSON form of the refusal."""
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "remediation": self.remediation,
            "details": self.details,
        }

    def to_json(self: ProjectError) -> str:
        """Return the refusal as one JSON line."""
        return json.dumps({"ok": False, "error": self.to_dict()}, ensure_ascii=False, sort_keys=True)
