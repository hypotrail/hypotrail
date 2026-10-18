"""Verify published results against source rows and saved out-of-sample scores."""
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[1]

def test_offline_page_embeds_current_results():
    embedded = re.search(r'const D=(.*?);const titles=', (ROOT/'bank-tutorial.html').read_text()).group(1)
    assert json.loads(embedded) == json.loads((ROOT/'tutorial-results.json').read_text())

def test_provenance_partition_and_counts():
    d = json.loads((ROOT/'tutorial-results.json').read_text())
    raw = ROOT/'data/bank.csv'
    frame = pd.read_csv(raw, sep=';')
    split = json.loads((ROOT/'data/split.json').read_text())
    assert len(frame) == d['rows'] == 4521
    assert d['raw_sha256'] == hashlib.sha256(raw.read_bytes()).hexdigest()
    assert not set(split['train']) & set(split['validation'])
    assert sorted(split['train'] + split['validation']) == list(range(4521))
    assert len(split['train']) == d['train_rows'] == 3164
    assert len(split['validation']) == d['validation_rows'] == 1357
    assert d['discovery']['sample'] == pd.concat([frame.iloc[split['train']].loc[lambda x:x.y=='no'].head(3), frame.iloc[split['train']].loc[lambda x:x.y=='yes'].head(3)])[d['features']+['y']].to_dict(orient='records')
    assert 'duration' not in d['features'] and 'y' not in d['features']

def test_metrics_reconcile_with_observed_targets_and_predictions():
    d = json.loads((ROOT/'tutorial-results.json').read_text())
    raw = pd.read_csv(ROOT/'data/bank.csv', sep=';')
    p = pd.read_csv(ROOT/'data/predictions.csv')
    assert np.array_equal(p.target, (raw.iloc[p.row].y == 'yes').astype(int))
    assert int(p.target.sum()) == d['positive_validation'] == 156
    assert abs(roc_auc_score(p.target, p.score) - d['models']['honnete']['auc']) < 1e-12
    for t in d['thresholds']:
        selected = p.score >= t['threshold']
        assert int(selected.sum()) == t['alerts']
        assert int(((p.target == 1) & selected).sum()) == t['true_alarms']
        assert t['true_alarms'] + t['false_alarms'] == t['alerts']
        assert t['true_alarms'] + t['missed'] == d['positive_validation']
