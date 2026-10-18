"""Paths, frame and feature-registry loading. Shared by every mlkit command."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("OSML_ROOT", Path.cwd())).resolve()

FRAME_FILE = ROOT / "frame.yaml"
FEATURES_FILE = ROOT / "features.yaml"
DEV_DIR = ROOT / "data" / "dev"
REGISTRY_FILE = ROOT / "experiments" / "registry.jsonl"
LEDGER_FILE = ROOT / "holdout" / "ledger.jsonl"
STOPS_DIR = ROOT / "stops"
PREREG_DIR = ROOT / "preregistrations"
REPORTS_DIR = ROOT / "reports"
HANDOFF_DIR = ROOT / "handoff"
PREDS_DIR = ROOT / ".osml" / "preds"
MODELS_DIR = ROOT / "models"
LOGS_DIR = ROOT / "logs"

KNOWN_CHECKS = {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "E1", "E3", "E4", "G1"}

# Defaults for stop thresholds. The real values should live OUTSIDE the
# repository (OSML_STOPS_FILE), so the agent cannot tune itself just under them.
DEFAULT_STOPS = {
    "too_good_gain": 0.015,      # gain on the primary metric that freezes the branch
    "stagnation_runs": 15,       # exploratory runs in a row without a conclusive gain
    "null_auc_band": [0.45, 0.55],
}


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_frame() -> dict:
    return load_yaml(FRAME_FILE)


def frame_hash() -> str:
    """Hash of the whole frame file content, normalised through YAML.

    Statement texts are included on purpose: rewording a statement may change
    its meaning, so it must invalidate earlier results like any other change.
    """
    canonical = json.dumps(load_frame(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def load_features() -> dict:
    return load_yaml(FEATURES_FILE)["features"]


def holdout_dir() -> Path:
    value = os.environ.get("OSML_HOLDOUT_DIR")
    if not value:
        raise SystemExit(
            "OSML_HOLDOUT_DIR is not set. The holdout is read only by a person or "
            "by the CI holdout workflow, never from an agent session."
        )
    return Path(value).expanduser().resolve()


def stops_config() -> tuple[dict, bool]:
    """Return (thresholds, private). private is False when the defaults are used."""
    value = os.environ.get("OSML_STOPS_FILE")
    if value and Path(value).expanduser().exists():
        cfg = dict(DEFAULT_STOPS)
        cfg.update(load_yaml(Path(value).expanduser()) or {})
        return cfg, True
    return dict(DEFAULT_STOPS), False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def readings_of_current_holdout(ledger: list[dict]) -> list[dict]:
    """Holdout readings that share the last reading's holdout (budget follows the holdout, not the frame).
    Entries written before lot 2 carry no fingerprint: counted with the current holdout, conservatively."""
    if not ledger:
        return []
    last = next((e["holdout_hash"] for e in reversed(ledger) if e.get("holdout_hash")), None)
    return [e for e in ledger if e.get("holdout_hash", last) == last]


def n_readings(entries: list[dict]) -> int:
    """An adoption entry (legacy readings, lot 2) stands for `count` readings."""
    return sum(int(e.get("count", 1)) for e in entries)


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
