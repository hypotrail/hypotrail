"""spec.training_sample: training-row cap while preserving the complete minority class."""
import numpy as np
import pandas as pd
import pytest

from mlkit import core


def data(n=10_000, rate=0.02, seed=0):
    rng = np.random.default_rng(seed)
    X = pd.DataFrame({"x": rng.normal(size=n)})
    y = pd.Series((rng.random(n) < rate).astype(int))
    return X, y


def test_no_cap_returns_everything():
    X, y = data()
    Xs, ys = core.training_sample(X, y, {})
    assert len(Xs) == len(X) and ys is y


def test_cap_keeps_all_minority_and_is_deterministic():
    X, y = data()
    spec = {"training_sample": {"max_rows": 2000, "seed": 3}}
    Xs, ys = core.training_sample(X, y, spec)
    assert len(Xs) == 2000 and ys.sum() == y.sum()
    Xs2, _ = core.training_sample(X, y, spec)
    assert Xs.index.equals(Xs2.index)


def test_minority_larger_than_cap_is_refused():
    X, y = data(rate=0.5)
    with pytest.raises(ValueError, match="max_rows"):
        core.training_sample(X, y, {"training_sample": {"max_rows": 100}})


def test_probability_use_refuses_rebalancing():
    X, y = data()
    with pytest.raises(SystemExit):
        core.training_sample(X, y, {"training_sample": {"max_rows": 2000}, "evaluation": {"decision_use": "probability"}})
    Xs, ys = core.training_sample(X, y, {"training_sample": {"max_rows": 2000, "keep_minority": False},
                                         "evaluation": {"decision_use": "probability"}})
    assert len(Xs) == 2000
