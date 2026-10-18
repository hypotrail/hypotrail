"""Example: supervised selection inside build(), refitted in every backtest window.

The selector sees only the training rows of each window. Changing C is a new
comparison: do it through mlkit.tuning.TimeAwareSearch so it is counted.
"""
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

from mlkit.selection import SupervisedSelector

CATEGORICAL = ["grade", "home_ownership", "verification_status", "purpose"]
NUMERIC = ["loan_amnt", "int_rate", "installment", "annual_inc", "dti", "fico_range_low",
           "revol_util", "inq_last_6mths", "open_acc", "total_acc", "credit_history_months"]
FEATURES = CATEGORICAL + NUMERIC


def build():
    prep = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore", min_frequency=0.01, sparse_output=False), CATEGORICAL),
        ("num", SimpleImputer(strategy="median"), NUMERIC),
    ])
    model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=3,
                                           min_samples_leaf=100, l2_regularization=1.0, random_state=0)
    return make_pipeline(prep, SupervisedSelector(method="l1", C=0.05), model)
