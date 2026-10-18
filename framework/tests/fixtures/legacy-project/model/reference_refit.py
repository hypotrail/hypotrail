"""Secondary reference: logistic regression re-fitted on sub_grade (the kit's reference before XP1).
Reported beside the existing score, never alone: with few old loans per grade it inverts the order
of neighbouring grades and makes every candidate look better than it is."""
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder

FEATURES = ["sub_grade"]


def build():
    return make_pipeline(OneHotEncoder(handle_unknown="ignore"), LogisticRegression(max_iter=1000))
