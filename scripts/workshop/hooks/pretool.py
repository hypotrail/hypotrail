"""Workshop PreToolUse hook for a study's Copilot agent (VS Code agent hooks, preview).

Legacy entry point: the hook now lives in the engine, ``hypotrail hook pretool`` (module
``mlkit.study.cmd_hook``), and ``hypotrail new`` installs that one. This script delegates to
it with its historical flags, for studies created by an earlier
``scripts/workshop/new-mpg-study.sh``:

    python pretool.py --repo REPO [--study STUDY] [--data-file NAME ...] [--log FILE]

* allow: one plain engine command, ``uv run [--quiet] --project <repo>/framework hypotrail
  ...`` (or the study's own invocation from ``.hypotrail/agent.json`` with ``--study``), with
  no shell operator (no ``; & | ` $ < >`` and no newline);
* deny: any call that names the case's raw data file (``--data-file``, repeatable, and the
  study's data file with ``--study``);
* no decision (``{}``) for everything else: VS Code asks the junior as usual.

Each decision is appended to ``--log``. The hook is a convenience, not a security boundary.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _engine_on_path(argv) -> None:
    """Make ``mlkit`` importable from ``--repo``'s framework when this interpreter lacks it."""
    try:
        import mlkit.study.cmd_hook  # noqa: F401
        return
    except ImportError:
        pass
    repo = None
    for i, arg in enumerate(argv):
        if arg == '--repo' and i + 1 < len(argv):
            repo = argv[i + 1]
        elif arg.startswith('--repo='):
            repo = arg.split('=', 1)[1]
    root = Path(repo) if repo else Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / 'framework'))


if __name__ == '__main__':
    _engine_on_path(sys.argv[1:])
    from mlkit.study.cmd_hook import legacy_main
    sys.exit(legacy_main())
