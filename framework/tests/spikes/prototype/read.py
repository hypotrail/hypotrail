"""Prototype read API: one view of the study for notebooks and HTML.

Strictly read-only: it opens files for reading only and installs the
read-only guard when ``HYPOTRAIL_READ_ONLY=1``. It imports neither pandas nor
scikit-learn.
"""
from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import guard


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build(study_dir: Path) -> dict[str, Any]:
    """Return the single read view consumed by every renderer."""
    root = Path(study_dir) / ".hypotrail"
    state = _load(root / "state.json")
    registry = {
        path.stem: _load(path) for path in sorted((root / "registry").glob("*.json"))
    }
    manifest_path = root / "artifacts.json"
    manifest = _load(manifest_path) if manifest_path.exists() else {"artifacts": {}}
    return {
        "schema": "hypotrail.view/0-spike",
        "revision": state["revision"],
        "steps": state["steps"],
        "decisions": state["decisions"],
        "current": state["current"],
        "results": registry,
        "artifacts": manifest["artifacts"],
    }


@dataclass(frozen=True)
class View:
    data: dict[str, Any]

    @property
    def revision(self) -> int:
        return self.data["revision"]

    def entry(self, result_id: str) -> dict[str, Any]:
        return self.data["results"][result_id]

    def value(self, result_id: str, key: str) -> Any:
        return self.entry(result_id)["output"]["values"][key]

    def source(self, result_id: str) -> str:
        """Activity source, displayed and never executed."""
        return self.entry(result_id)["code"]["source"]


def banner(view: View, generated_revision: int) -> str:
    if view.revision == generated_revision:
        status = "current"
    else:
        status = f"stale: the study is now at revision {view.revision}; run the render again"
    return (f"**Generated at revision {generated_revision}** ({status}). "
            "Do not edit this notebook; write your notes in `workbench.py`.")


def numbers_html(view: View, result_id: str) -> str:
    """Scalar outputs as ``<data data-result-id>`` elements."""
    items = []
    for key, value in sorted(view.entry(result_id)["output"]["values"].items()):
        if isinstance(value, (int, float)):
            items.append(
                f'<li>{html.escape(key)}: <data data-result-id="{html.escape(result_id)}" '
                f'data-key="{html.escape(key)}" value="{value!r}">{value:g}</data></li>')
        else:
            items.append(f"<li>{html.escape(key)}: {len(value)} values (persisted)</li>")
    return "<ul>" + "".join(items) + "</ul>"


def source_block(view: View, result_id: str) -> str:
    return "Activity source (displayed, not executed):\n\n```python\n" + view.source(result_id) + "```"


def compare_md(experiment: dict[str, Any], adopted: dict[str, Any]) -> str:
    def row(label: str, item: dict[str, Any]) -> str:
        return (f"| {label} | {item['threshold']:.2f} | {item['selected']} | "
                f"{item['precision']:.2f} | {item['recall']:.2f} |")
    return "\n".join([
        "| Policy | Threshold | Selected | Precision | Recall |",
        "|---|---|---|---|---|",
        row("Experiment, not adopted", experiment),
        row("Adopted (from state)", adopted),
    ])


def open_study(study_dir: Path) -> View:
    guard.install(study_dir)
    return View(build(study_dir))


open = open_study  # noqa: A001 - mirrors the planned ``read.open`` name
