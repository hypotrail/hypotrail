"""The reference is the score already in use, applied as is (lesson of XP1).

Declared in frame.yaml (human-only file), built by the kit — no model file to edit:

    spec:
      reference:
        kind: existing_score          # existing_score | refit
        column: sub_grade
        order: [A1, A2, ..., G5]      # categorical score, least risky first
        # riskier: higher             # numeric score instead of order: which side is riskier
      reference_secondary_pipeline: model/reference_refit.py   # optional: shown beside, never used for a gain

    kind: refit is accepted only with `pipeline:` and `justification:` (nothing in place to compare with).

Why: in XP1 the reference was a logistic regression re-fitted on Lending Club's sub_grade
with 14 538 old loans (about 415 per sub-grade). The re-fit put 13 pairs of neighbouring
sub-grades out of 33 in the wrong order, and every candidate "beat" that weakened copy by about
0.17 point. Against the grade used as is, none did.

ExistingScore never uses y. Its score is a RANK on [0, 1], not a probability: the Brier score
and the calibration of the reference are not interpretable; its ranking metrics are.
"""
from __future__ import annotations

import numbers
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, ClassifierMixin

MAX_UNKNOWN = 0.01      # share of values outside `order` tolerated at fit (typo, wrong column)


def _key(v):
    """Compare values, not their text: 1, 1.0 and "1" are the same grade; "A1" stays "A1"."""
    if isinstance(v, (numbers.Number, np.number)) and not isinstance(v, bool):
        return float(v)
    try:
        return float(str(v))
    except ValueError:
        return str(v).strip()


class ExistingScore(ClassifierMixin, BaseEstimator):

    def __init__(self, column: str, order=None, riskier: str = "higher"):
        self.column = column
        self.order = order
        self.riskier = riskier

    def _col(self, X) -> pd.Series:
        return X[self.column] if isinstance(X, pd.DataFrame) else pd.Series(np.asarray(X)[:, 0])

    def fit(self, X, y=None):   # y is never used
        if self.riskier not in ("higher", "lower"):
            raise ValueError("riskier must be 'higher' or 'lower'")
        s = self._col(X)
        self.classes_ = np.array([0, 1])
        if self.order is not None:
            if len(self.order) < 2 or len({_key(v) for v in self.order}) != len(self.order):
                raise ValueError("reference.order: at least two distinct categories without duplicates")
            self.pos_ = {_key(v): i for i, v in enumerate(self.order)}
            known = s.dropna().map(_key).isin(self.pos_.keys())
            share = 1 - known.mean() if len(known) else 0.0
            if share > MAX_UNKNOWN:
                raise ValueError(f"{self.column}: {share:.1%} values outside order "
                                 f"(ex. {s.dropna()[~known].iloc[0]!r}); wrong column or incomplete list")
        else:
            x = self._signed(s)
            if not np.isfinite(x).any():
                raise ValueError(f"{self.column}: no numeric value")
            self.lo_, self.hi_ = float(np.nanmin(x)), float(np.nanmax(x))
        return self

    def _signed(self, s: pd.Series) -> np.ndarray:
        x = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
        return -x if self.riskier == "lower" else x

    def _rank(self, X) -> np.ndarray:
        s = self._col(X)
        if self.order is not None:
            r = s.map(lambda v: self.pos_.get(_key(v), np.nan) if pd.notna(v) else np.nan).to_numpy(dtype=float)
            r = np.where(np.isnan(r), len(self.order) - 1, r)          # unknown or missing: riskiest
            return r / max(len(self.order) - 1, 1)
        x = self._signed(s)
        # Strictly increasing outside the fit range; this rank is not a probability.
        center = self.lo_ / 2 + self.hi_ / 2
        scale = max(abs(self.hi_ / 2 - self.lo_ / 2), 1.0)
        rank = 0.5 + np.arctan((x - center) / scale) / np.pi
        return np.where(np.isnan(x), 1.0, rank)

    def predict_proba(self, X) -> np.ndarray:
        r = self._rank(X)
        return np.c_[1 - r, r]

    def predict(self, X) -> np.ndarray:
        return (self._rank(X) >= 0.5).astype(int)


def settings(spec: dict) -> dict:
    """Frame declaration of the reference; the pre-lot-0 key reference_pipeline means kind: refit."""
    ref = dict(spec.get("reference") or {})
    if not ref and spec.get("reference_pipeline"):
        ref = {"kind": "refit", "pipeline": spec["reference_pipeline"]}
    return ref


def problems(spec: dict) -> list[str]:
    ref = settings(spec)
    kind = ref.get("kind")
    if kind == "existing_score":
        bad = [] if ref.get("column") else ["reference.column missing"]
        if ref.get("order") is None and ref.get("riskier") not in ("higher", "lower"):
            bad.append("reference: provide order for categorical scores or riskier: higher|lower for numeric scores")
        return bad
    if kind == "refit":
        bad = [] if ref.get("pipeline") else ["reference.pipeline missing for kind: refit"]
        if not str(ref.get("justification", "")).strip():
            bad.append("refitted reference lacks justification: allowed only when no incumbent score "
                       "or rule exists (XP1: refitting on few loans made every model appear better). "
                       "Declare reference.kind: existing_score or document reference.justification")
        return bad
    return [f"reference.kind unknown or missing: {kind!r} (existing_score | refit)"]


def module(spec: dict):
    """A pipeline-like object (FEATURES, build) for the primary reference."""
    from . import core
    ref = settings(spec)
    if ref.get("kind") == "existing_score":
        col, order, riskier = ref["column"], ref.get("order"), ref.get("riskier", "higher")
        return SimpleNamespace(FEATURES=[col], build=lambda: ExistingScore(col, order=order, riskier=riskier),
                               PATH=f"frame:reference({col})")
    mod = core.load_pipeline(ref["pipeline"])
    mod.PATH = ref["pipeline"]
    return mod


def columns(spec: dict) -> set[str]:
    """Columns of the score in place: exempt from D6 (a good score in place is not a leak)."""
    ref = settings(spec)
    return {ref["column"]} if ref.get("kind") == "existing_score" and ref.get("column") else set()
