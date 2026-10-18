"""Fake study state, registry, and manifest for the spike (no real data)."""
from __future__ import annotations

import json
from pathlib import Path

SPLIT_RID = "r_split_0001"
RATE_RID = "r_target_rate_0002"
PRED_RID = "r_predictions_0003"

FAKE_FIT_SOURCE = (
    "def fit_logistic(train, features):\n"
    "    model = make_pipeline(features)\n"
    "    model.fit(train[features], train['y'])\n"
    "    return model\n"
)


def _entry(activity: str, values: dict, source: str, partition: str) -> dict:
    return {
        "activity": activity,
        "partition": partition,
        "code": {"fingerprint": "sha256:spike", "source": source},
        "output": {"values": values},
    }


def make_study(root: Path, revision: int = 7) -> Path:
    """Create ``root/study`` with a fake ``.hypotrail`` and return it."""
    study = root / "study"
    hyp = study / ".hypotrail"
    (hyp / "registry").mkdir(parents=True)
    (study / "notebooks").mkdir()
    write_state(study, revision)
    registry = {
        SPLIT_RID: _entry("split", {"train_rows": 3164, "validation_rows": 1357},
                          "def split(data, seed):\n    ...\n", "all"),
        RATE_RID: _entry("eda.target_rate", {"rate": 0.1153, "positives": 365, "rows": 3164},
                         "def target_rate(train):\n    return train['y'].mean()\n", "train"),
        PRED_RID: _entry("fit.logistic",
                         {"y": [1, 0, 0, 1, 0, 1, 0, 0],
                          "score": [0.91, 0.12, 0.40, 0.66, 0.05, 0.40, 0.73, 0.22]},
                         FAKE_FIT_SOURCE, "validation"),
    }
    for rid, entry in registry.items():
        (hyp / "registry" / f"{rid}.json").write_text(
            json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return study


def write_state(study: Path, revision: int) -> None:
    state = {
        "schema": "hypotrail.study/1",
        "revision": revision,
        "steps": [
            {"id": "split", "title": "Split before exploring",
             "concept": "Validation partition",
             "question": "Which rows stay unseen until model evaluation?",
             "status": "done", "result_id": SPLIT_RID},
            {"id": "eda", "title": "Explore the training partition",
             "concept": "Base rate",
             "question": "How often does the positive outcome occur in training?",
             "status": "done", "result_id": RATE_RID},
            {"id": "fit", "title": "Fit a logistic model",
             "concept": "Validation-based selection",
             "question": "Does the model rank positives above negatives?",
             "status": "done", "result_id": PRED_RID},
            {"id": "policy", "title": "Choose a contact policy",
             "concept": "Decision threshold",
             "question": "Which threshold or capacity fits the campaign?",
             "status": "pending", "result_id": None},
        ],
        "decisions": {"policy": {"status": "confirmed", "value": {"threshold": 0.5},
                                 "confirmation": {"user_words": "Use 0.5 for now."}}},
        "current": {"split": SPLIT_RID, "eda.target_rate": RATE_RID,
                    "predictions": PRED_RID},
    }
    (study / ".hypotrail" / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
