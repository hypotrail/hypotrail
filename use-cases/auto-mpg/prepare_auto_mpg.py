"""Auto MPG adapter: prepare data and produce structured results once.

Split chronologically by model year: observations are ordered, and some car names recur
across years. Random splitting would mix years and make training and validation artificially similar.
"""
from pathlib import Path
import hashlib
import json
import platform

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

HERE = Path(__file__).resolve().parent
PROJECT = HERE
RAW = PROJECT / 'data/auto-mpg.data'
COLUMNS = ['mpg', 'cylinders', 'displacement', 'horsepower', 'weight', 'acceleration', 'model_year', 'origin', 'car_name']
TRAIN_YEARS, VALIDATION_YEARS = (70, 78), (79, 82)
SEED = 20261017
FEATURE_SETS = {'linear-weight': ['weight'], 'linear-all': ['cylinders', 'displacement', 'horsepower', 'weight', 'model_year', 'origin_2', 'origin_3']}


def load():
    frame = pd.read_csv(RAW, sep=r'\s+', names=COLUMNS, na_values='?', quotechar='"')
    return frame


def design(frame, columns, fill):
    x = frame.assign(origin_2=(frame.origin == 2).astype(int), origin_3=(frame.origin == 3).astype(int))
    x = x.assign(horsepower=x.horsepower.fillna(fill))
    return x[columns].to_numpy(float)


def summary(y, prediction):
    error = prediction - y
    return {'mae_mpg': float(mean_absolute_error(y, prediction)), 'rmse_mpg': float(np.sqrt(mean_squared_error(y, prediction))),
            'mean_error_mpg': float(error.mean()), 'within_3_mpg_share': float((np.abs(error) <= 3).mean())}


def experiment():
    frame = load()
    train = frame[frame.model_year.between(*TRAIN_YEARS)]
    validation = frame[frame.model_year.between(*VALIDATION_YEARS)]
    fill = float(train.horsepower.median())
    predictions = {'baseline-median': np.full(len(validation), float(train.mpg.median()))}
    fitted = 0
    for name, columns in FEATURE_SETS.items():
        model = LinearRegression().fit(design(train, columns, fill), train.mpg)
        predictions[name] = model.predict(design(validation, columns, fill))
        fitted += 1
    protocol = {'id': 'chronological-70-78-vs-79-82', 'label': 'Train on 1970–1978, compare on 1979–1982',
                'description': 'Chronological split by model year. The horsepower imputation median is calculated from training data only.',
                'partition': {'train': int(len(train)), 'validation': int(len(validation))},
                'scope': 'exploratory', 'scope_justification': 'Validation compares and selects models: it is no longer an independent evaluation.'}
    labels = {'baseline-median': 'Reference: training median', 'linear-weight': 'Linear regression · weight only', 'linear-all': 'Linear regression · technical characteristics'}
    results = []
    for name, prediction in predictions.items():
        results.append({'id': name, 'label': labels[name], 'kind': 'model_evaluation', 'protocol': protocol['id'],
                        'configuration': {'model': name, 'features': FEATURE_SETS.get(name, [])},
                        'method': 'Constant median' if name == 'baseline-median' else 'Ordinary least squares (scikit-learn LinearRegression)',
                        'provenance': 'prepare_auto_mpg.py::experiment', 'observations': int(len(validation)),
                        'metrics': summary(validation.mpg.to_numpy(), prediction), 'status': 'available', 'scope': 'exploratory',
                        'limitations': ['Validation reused for comparison: not evidence about future models.']})
    # Counterexample: same model under a random split that mixes years.
    shuffled = frame.sample(frac=1, random_state=SEED)
    cut = int(len(frame) * 0.7)
    random_train, random_validation = shuffled.iloc[:cut], shuffled.iloc[cut:]
    columns = FEATURE_SETS['linear-all']
    random_fill = float(random_train.horsepower.median())
    random_model = LinearRegression().fit(design(random_train, columns, random_fill), random_train.mpg)
    fitted += 1
    random_protocol = {'id': 'random-70-30-counterexample', 'label': 'Counterexample: random 70/30 split (mixed years)',
                       'description': f'Random split with seed {SEED}. Future years also contribute to training.',
                       'partition': {'train': int(len(random_train)), 'validation': int(len(random_validation))},
                       'scope': 'counterexample', 'scope_justification': 'Shows the difference from chronological evaluation; must not guide selection.'}
    results.append({'id': 'linear-all-random-split', 'label': 'Linear regression · technical characteristics (random split)', 'kind': 'model_evaluation',
                    'protocol': random_protocol['id'], 'configuration': {'model': 'linear-all', 'features': columns}, 'method': 'Ordinary least squares (scikit-learn LinearRegression)',
                    'provenance': 'prepare_auto_mpg.py::experiment', 'observations': int(len(random_validation)),
                    'metrics': summary(random_validation.mpg.to_numpy(), random_model.predict(design(random_validation, columns, random_fill))),
                    'status': 'available', 'scope': 'counterexample', 'limitations': ['Learns from years later than those it evaluates.']})
    by_year = []
    for year, group in validation.groupby('model_year'):
        index = validation.index.get_indexer(group.index)
        by_year.append({'group': f'19{year}', 'observations': int(len(group)),
                        **{name: float(mean_absolute_error(group.mpg, predictions[name][index])) for name in predictions}})
    edges = list(range(5, 50, 5))
    histogram = [{'label': f'{a}–{b} mpg', 'count': int(((train.mpg >= a) & (train.mpg < b)).sum())} for a, b in zip(edges, edges[1:])]
    shared = sorted(set(train.car_name) & set(validation.car_name))
    examples = train.sort_values(['model_year', 'car_name']).iloc[[0, 40, 90, 150, 200, 230]]
    output = {
        'schema': 'hypotrail.results/1', 'project_id': 'uci-auto-mpg-v1',
        'dataset': {'id': 'uci-auto-mpg', 'sha256': hashlib.sha256(RAW.read_bytes()).hexdigest(), 'rows': int(len(frame))},
        'generated_by': {'script': 'prepare_auto_mpg.py', 'models_fitted': fitted,
                         'environment': {'python': platform.python_version(), 'sklearn': sklearn.__version__, 'pandas': pd.__version__, 'numpy': np.__version__}},
        'protocols': [protocol, random_protocol],
        'metric_definitions': {
            'mae_mpg': {'label': 'Mean absolute error (MAE)', 'unit': 'mpg', 'format': 'number:2', 'direction': 'lower_is_better', 'description': 'Average difference in miles per gallon between estimated and observed efficiency.'},
            'rmse_mpg': {'label': 'Root mean squared error', 'unit': 'mpg', 'format': 'number:2', 'direction': 'lower_is_better', 'description': 'Penalizes large errors more heavily.'},
            'mean_error_mpg': {'label': 'Mean signed error', 'unit': 'mpg', 'format': 'number:2', 'direction': 'closer_to_zero', 'description': 'Negative: the model underestimates observed mpg on average.'},
            'within_3_mpg_share': {'label': 'Cars estimated within ±3 mpg', 'unit': 'proportion', 'format': 'percent', 'direction': 'higher_is_better', 'description': 'Share of validation cars whose absolute error does not exceed 3 mpg.'},
            'observations': {'label': 'Validation cars', 'unit': 'cars', 'format': 'count', 'direction': 'context', 'description': 'Number of compared rows.'}},
        'results': results,
        'display': {
            'examples': json.loads(examples[COLUMNS].to_json(orient='records')),
            'target_distribution': histogram,
            'errors_by_group': {'group_label': 'Model year', 'metric': 'mae_mpg', 'rows': by_year},
            'shared_names': {'count': len(shared), 'examples': shared[:5]},
            'missing': {'horsepower': int(frame.horsepower.isna().sum())}},
        'limitations': [
            'US-market cars from 1970–1982: no guarantee for current vehicles.',
            f'{len(shared)} car names occur in both training and validation: the partitions are not fully independent.',
            'City-cycle fuel efficiency according to the source; measurement conditions are not detailed.',
            'The meaning of origin codes (1, 2, 3) is not described in auto-mpg.names.']}
    (PROJECT / 'results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'train': len(train), 'validation': len(validation), 'metrics': {r['id']: r['metrics'] for r in results}}, indent=2))


if __name__ == '__main__':
    experiment()
