"""Is the acceptance threshold measurable? Computed at framing time, before any model.

    python -m mlkit.mde

The holdout can only tell a gain from zero if the gain is larger than its noise. This
command estimates the smallest detectable gain (one-sided 5 %, power 80 %) from the dev
data alone — the holdout is never read — and compares it with the threshold of the frame
(mlkit.decision.min_gain). If the threshold is below what can be detected, the project
would end with « indeterminate » whatever the model: better to know before modelling.

Inputs: the size of the holdout (frame holdout.expected_size, or estimated from the monthly
volume of the last dev months), the bad rate near the cut-off (last backtest window, score
in place), and the share of accepted loans a new model would swap (frame power.swap_share,
default 0.10; shown with 0.05 and 0.20 for sensitivity).

Under acceptance.rule: margin, it also prints the TRUE gain a model needs to be accepted with 80 %
power (≈ δ + (z_ci + z_0.8)·se, mlkit.decision.required_gain) and says whether it is plausible: not
if it reaches the « too good to be true » stop (the kit would freeze such a branch), and, when
power.expected_gain is declared, not if it exceeds that expected gain.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from . import config, core, decision, reference


def inputs(spec: dict) -> dict:
    df = core.load_dev(spec)
    rate = float(spec.get("evaluation", {}).get("decision_rate", 0.9))
    name, _, start, end = list(core.windows(spec, stress=False))[-1]
    w = df[(df["_month"] >= start) & (df["_month"] <= end)]
    mod = reference.module(spec)
    score = mod.build().fit(w[mod.FEATURES]).predict_proba(w[mod.FEATURES])[:, 1]\
        if reference.settings(spec).get("kind") == "existing_score" else None
    if score is None:
        tr = df["_month"] <= list(core.windows(spec, stress=False))[-1][1]
        score = core.fit_predict(mod, df.loc[tr, mod.FEATURES], df.loc[tr, spec["target_col"]], w[mod.FEATURES])
    q_lo, q_hi = np.quantile(score, [max(rate - 0.1, 0), min(rate + 0.1, 1)])
    near = (score >= q_lo) & (score <= q_hi)
    p_cut = float(w.loc[near, spec["target_col"]].mean())
    first, last = spec["holdout"]["window"]
    months = len(pd.period_range(first, last, freq="M"))
    expected = spec["holdout"].get("expected_size")
    if not expected:
        per_month = df.groupby("_month").size().sort_index().iloc[-6:].mean()
        expected = int(per_month * months)
    return {"window": name, "rate": rate, "p_cut": p_cut, "n_holdout": int(expected),
            "estimated_size": not spec["holdout"].get("expected_size"),
            "swap_share": float(spec.get("power", {}).get("swap_share", 0.10))}


def plausibility(spec: dict, min_gain: float, se: float) -> dict:
    """Is the gain the margin rule needs (80 % power) a gain one can hope for?"""
    ci = float(spec["acceptance"].get("ci_level", 0.9))
    need = decision.required_gain(min_gain, se, ci)
    too_good = float(config.stops_config()[0]["too_good_gain"])
    expected = (spec.get("power") or {}).get("expected_gain")
    if need >= too_good:
        return {"required": need, "z": (need - min_gain) / se, "plausible": False,
                "why": f"it exceeds the suspiciously good gain ({too_good * 100:.2f} points) that freezes a branch: "
                       "no model can be accepted. Increase holdout size or revisit costs."}
    if expected is not None and need > float(expected):
        return {"required": need, "z": (need - min_gain) / se, "plausible": False,
                "why": f"it exceeds the declared expected gain (power.expected_gain = {float(expected) * 100:.3f} point)."}
    return {"required": need, "z": (need - min_gain) / se, "plausible": True,
            "why": "below the suspiciously good threshold" + (" and below the declared expected gain" if expected is not None else
                                                   " (declare power.expected_gain to compare with business expectations)") + "."}


def main(argv=None) -> int:
    argparse.ArgumentParser(prog="python -m mlkit.mde").parse_args(argv)
    spec = config.load_frame()["spec"]
    mg = decision.min_gain(spec)
    x = inputs(spec)
    alpha = (1 - float(spec["acceptance"].get("ci_level", 0.9))) / 2     # same test as the holdout reading
    rows = {s: decision.mde(x["n_holdout"], x["rate"], x["p_cut"], s, alpha=alpha) for s in sorted({0.05, x["swap_share"], 0.20})}
    main_ = rows[x["swap_share"]]
    print(f"Holdout : {x['n_holdout']:,} loans{' (estimated from recent monthly volume)' if x['estimated_size'] else ''} · "
          f"default rate near threshold {x['p_cut']:.1%} (window {x['window']}, score en place)".replace(",", " "))
    for s, r in rows.items():
        print(f"  if a model changes {s:.0%} of accepted loans: detectable gain ≥ {r['mde'] * 100:.3f} point")
    print(f"Seuil d'acceptation : {mg['min_gain'] * 100:.3f} point ({mg['text']})")
    ok = mg["min_gain"] >= main_["mde"]
    if decision.acceptance_rule(spec) == "margin":
        r = plausibility(spec, mg["min_gain"], main_["se"])
        print(f"Margin rule: acceptance in 8 of 10 repetitions requires true gain ≈ {r['required'] * 100:.3f} point "
              f"(threshold {mg['min_gain'] * 100:.3f} + {r['z']:.2f} × standard error {main_['se'] * 100:.3f}).")
        print(("PLAUSIBLE : " if r["plausible"] else "PEU PLAUSIBLE : ") + r["why"])
    print("MEASURABLE: the threshold exceeds holdout noise." if ok else
          "NOT MEASURABLE: the threshold is below the minimum detectable gain. Enlarge the holdout "
          "or accept that the decision will usually remain indeterminate.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
