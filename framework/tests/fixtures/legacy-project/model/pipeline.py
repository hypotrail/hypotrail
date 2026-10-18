"""Starting candidate. The agent changes THIS file (and adds others in model/).

Contract: FEATURES lists the columns received — each one registered in
features.yaml with available: origination. build() returns an unfitted
estimator with predict_proba. No splitting, no metrics here: the runner owns them.
"""
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OrdinalEncoder

CATEGORICAL = ["grade", "sub_grade", "home_ownership", "verification_status", "purpose", "initial_list_status"]
NUMERIC = ["loan_amnt", "int_rate", "installment", "annual_inc", "dti", "fico_range_low",
           "revol_util", "inq_last_6mths", "open_acc", "total_acc", "credit_history_months"]
FEATURES = CATEGORICAL + NUMERIC


def build():
    encode = ColumnTransformer(
        [("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1,
                                encoded_missing_value=-1), CATEGORICAL)],
        remainder="passthrough",
    )
    model = HistGradientBoostingClassifier(
        categorical_features=list(range(len(CATEGORICAL))), max_iter=200, learning_rate=0.05,
        max_depth=3, min_samples_leaf=100, l2_regularization=1.0, random_state=0,
    )
    return make_pipeline(encode, model)
