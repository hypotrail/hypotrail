"""Structured refusals of the exported project (Hypotrail contract v1 §8).

A refusal has a stable ``code``, the ``path`` concerned, a ``message`` and a
``remediation``; ``project.py`` prints it as JSON and exits with code 2. Nothing is
written after a refusal.

:func:`from_exception` turns the errors a command can meet into refusals with the same
fields: a structured refusal of ``hypotrail_runtime`` (``ContractError``) or of the
packager keeps its code, path and remediation; an unreadable file, a CSV or pandas
parsing error, and a Hydra, OmegaConf or YAML configuration error become
``contract_invalid``. Any other exception is not a refusal (``None``): ``project.py``
reports it as ``internal_error`` with exit code 1.
"""

from __future__ import annotations

import csv
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


MAX_TEXT = 500
CONFIG_MODULES = ("hydra", "omegaconf", "yaml")


def _text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:MAX_TEXT]


def from_exception(error: BaseException) -> ProjectError | None:
    """Return the refusal an exception stands for, or ``None`` for an internal error."""
    if isinstance(error, ProjectError):
        return error
    code, message = getattr(error, "code", None), getattr(error, "message", None)
    if isinstance(code, str) and isinstance(message, str):
        details = getattr(error, "details", None)
        return ProjectError(
            code,
            message,
            path=getattr(error, "path", None) or None,
            remediation=getattr(error, "remediation", None) or None,
            details={"source": type(error).__module__.split(".")[0], **(details if isinstance(details, dict) else {})},
        )
    return _classified(error)


def _classified(error: BaseException) -> ProjectError | None:
    """Return the refusal of a configuration, parsing or file error, or ``None``."""
    module = type(error).__module__.split(".")[0]
    if module in CONFIG_MODULES:
        return ProjectError(
            "contract_invalid",
            "The project configuration cannot be composed or resolved.",
            path="src/conf",
            remediation="Restore the exported configuration files (git diff src/conf).",
            details={"error": _text(error)},
        )
    if module == "pandas" or isinstance(error, csv.Error):
        return ProjectError(
            "contract_invalid",
            "The file cannot be read as the CSV this command expects.",
            remediation="Give a CSV file with a header row and one record per line.",
            details={"error": _text(error)},
        )
    if isinstance(error, UnicodeDecodeError):
        return ProjectError(
            "contract_invalid",
            f"A file is not text in the expected encoding ({error.encoding}).",
            remediation="Give the file in the encoding of the data contract.",
            details={"error": _text(error)},
        )
    if isinstance(error, OSError):
        return ProjectError(
            "invalid_arguments",
            "A file cannot be read or written.",
            path=error.filename if isinstance(error.filename, str) else None,
            remediation="Check the path and its permissions.",
            details={"error": _text(error)},
        )
    return None


def internal_error(error: BaseException) -> dict:
    """Return the JSON document of an unexpected exception (exit code 1)."""
    return {
        "ok": False,
        "error": {
            "code": "internal_error",
            "path": None,
            "message": "Unexpected error; this is a defect of the exported project, not a refusal.",
            "remediation": "Report it with the details below.",
            "details": {"error": _text(error)},
        },
    }
