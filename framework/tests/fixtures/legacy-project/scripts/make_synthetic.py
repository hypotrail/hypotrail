"""Synthetic Lending-Club-shaped data, to try the kit end to end in five minutes
before downloading anything. Same columns, same months, a known truth.

    python scripts/make_synthetic.py --private ~/.hypotrail-ml/synthetic [--n 60000]

Includes two natural leaks written after origination, like the real data:
total_pymnt (lower for defaulted loans) and recoveries (non-zero almost only for them).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


def generate(n: int, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    months = pd.period_range("2007-06", "2015-12", freq="M")
    weights = np.linspace(0.05, 1.0, len(months)) ** 2.5          # volume grows like LC
    m = rng.choice(len(months), size=n, p=weights / weights.sum())
    fico = rng.normal(700, 30, n).clip(620, 850)
    dti = rng.gamma(4, 4.5, n).clip(0, 45)
    inc = np.exp(rng.normal(11.0, 0.5, n))
    inq = rng.poisson(0.8, n)
    revol = rng.uniform(0, 100, n).round(1)
    # what the lender's own grade sees (with its own error) ...
    graded = -0.025 * (fico - 700) + 0.05 * (dti - 18) - 0.5 * (np.log(inc) - 11)
    # ... and what it does not: a model using inq and revol_util can do better than sub_grade
    unseen = 0.45 * (inq - 0.8) + 0.02 * (revol - 50)
    risk = -2.3 + graded + unseen + rng.normal(0, 0.4, n)
    p = 1 / (1 + np.exp(-risk))
    default = (rng.random(n) < p).astype(int)
    grade_idx = np.clip(((graded + rng.normal(0, 0.3, n) + 2.6) / 0.16).astype(int), 0, 34)
    sub_grade = [f"{'ABCDEFG'[i // 5]}{i % 5 + 1}" for i in grade_idx]
    loan = rng.integers(10, 351, n) * 100
    rate = 6 + grade_idx * 0.6 + rng.normal(0, 0.3, n)
    installment = loan * (rate / 1200) / (1 - (1 + rate / 1200) ** -36)
    paid_share = np.where(default == 1, rng.uniform(0.2, 0.8, n), 1.0)
    df = pd.DataFrame({
        "id": rng.permutation(n) + 1_000_000,
        "issue_d": months[m].astype(str),
        "loan_amnt": loan, "int_rate": rate.round(2), "installment": installment.round(2),
        "grade": [s[0] for s in sub_grade], "sub_grade": sub_grade,
        "emp_length": rng.integers(0, 11, n),
        "home_ownership": rng.choice(["RENT", "MORTGAGE", "OWN"], n, p=[0.4, 0.5, 0.1]),
        "annual_inc": inc.round(0),
        "verification_status": rng.choice(["Verified", "Source Verified", "Not Verified"], n),
        "purpose": rng.choice(["debt_consolidation", "credit_card", "home_improvement", "other"], n, p=[0.6, 0.2, 0.1, 0.1]),
        "dti": dti.round(2), "fico_range_low": (fico // 5 * 5).astype(int),
        "fico_range_high": (fico // 5 * 5 + 4).astype(int),
        "revol_util": revol, "inq_last_6mths": inq,
        "open_acc": rng.poisson(11, n), "total_acc": rng.poisson(24, n),
        "initial_list_status": rng.choice(["w", "f"], n), "credit_history_months": rng.integers(36, 400, n),
        "total_pymnt": (installment * 36 * paid_share).round(2),        # natural leak: written after origination
        "recoveries": np.where((default == 1) & (rng.random(n) > 0.15),
                               loan * (1 - paid_share) * rng.uniform(0, 0.3, n), 0.0).round(2),  # idem, stronger
        "default": default,
    })
    return df.sort_values("issue_d").reset_index(drop=True)


def write(df: pd.DataFrame, root: Path, private: Path, holdout_window=("2015-07", "2015-12")) -> None:
    month = pd.PeriodIndex(df["issue_d"], freq="M")
    first, last = (pd.Period(x, "M") for x in holdout_window)
    dev, hold = df[month < first], df[(month >= first) & (month <= last)]
    for frame_, d in ((dev, root / "data" / "dev"), (hold, private / "holdout")):
        d.mkdir(parents=True, exist_ok=True)
        frame_.drop(columns=["default"]).to_csv(d / "features.csv.gz", index=False)
        frame_[["id", "default"]].to_csv(d / "labels.csv.gz", index=False)
    script = Path(__file__).resolve()
    manifest = {"script": "scripts/make_synthetic.py",
                "script_hash": hashlib.sha256(script.read_bytes()).hexdigest()[:12],
                "source_hash": "synthetic", "as_of": "2018-12", "steps": [],
                "outputs": {f: hashlib.sha256((root / "data" / "dev" / f).read_bytes()).hexdigest()[:12]
                            for f in ("features.csv.gz", "labels.csv.gz")}}
    (root / "data" / "dev" / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"dev {len(dev):,} loans · holdout {len(hold):,} loans → {private / 'holdout'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", required=True)
    ap.add_argument("--n", type=int, default=60_000)
    ap.add_argument("--root", default=".")
    a = ap.parse_args()
    write(generate(a.n), Path(a.root).resolve(), Path(a.private).expanduser().resolve())
