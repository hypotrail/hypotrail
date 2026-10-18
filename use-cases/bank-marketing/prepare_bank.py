"""Rebuild the public-data teaching experiment, offline from the attributed UCI CSV.

This is a separate exploratory tutorial, never the project pilot/fit registry.
Run with this folder's uv environment. All preprocessing is fitted on train only.
"""
from pathlib import Path
import hashlib
import json
import platform
import re
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, recall_score, roc_auc_score, average_precision_score

ROOT = Path(__file__).resolve().parent
SEED = 20261017
FEATURES = ['balance', 'previous', 'pdays', 'poutcome']

def experiment():
    raw = ROOT / 'data/bank.csv'
    data = pd.read_csv(raw, sep=';')
    y = (data.y == 'yes').astype(int)
    train, validation = train_test_split(np.arange(len(data)), test_size=.3, stratify=y, random_state=SEED)
    # -1 explicitly means no previous contact, not a measured negative duration.
    x = data[FEATURES + ['duration']].copy()
    x['previously_contacted'] = (x.pdays != -1).astype(int)
    x['pdays'] = x.pdays.mask(x.pdays == -1, 0)
    numeric = ['balance', 'previous', 'pdays', 'previously_contacted']
    scores = {}
    for name, cols in [('honnete', numeric), ('avec_fuite', numeric + ['duration'])]:
        preprocessing = ColumnTransformer([('numeric', StandardScaler(), cols), ('category', OneHotEncoder(handle_unknown='ignore'), ['poutcome'])])
        model = make_pipeline(preprocessing, LogisticRegression(max_iter=2000, random_state=SEED))
        model.fit(x.iloc[train], y.iloc[train])
        scores[name] = model.predict_proba(x.iloc[validation])[:, 1]
    # Constant majority-class baseline: no fitting necessary.
    scores['reference'] = np.zeros(len(validation))
    target = y.iloc[validation].to_numpy()
    models = {name: {'accuracy': accuracy_score(target, p >= .5), 'recall': recall_score(target, p >= .5),
                     'auc': roc_auc_score(target, p), 'average_precision': average_precision_score(target, p)} for name, p in scores.items()}
    thresholds = []
    for threshold in [.1, .2, .35, .5]:
        selected = scores['honnete'] >= threshold
        tp = int(((target == 1) & selected).sum()); fp = int(((target == 0) & selected).sum())
        thresholds.append(dict(threshold=threshold, recall=tp/int(target.sum()), precision=tp/max(1,int(selected.sum())),
                               false_alarms=fp, missed=int(target.sum())-tp, true_alarms=tp, alerts=int(selected.sum())))
    discovery = data.iloc[train]
    distribution = [{'label': label, 'count': int((discovery.y == value).sum())} for value, label in [('no','No subscription'),('yes','Subscription')]]
    result = dict(dataset_id='uci-bank-marketing-v1', dataset_name='Bank Marketing · UCI', seed=SEED, rows=len(data), train_rows=len(train),
                  validation_rows=len(validation), positive_validation=int(target.sum()), models=models, thresholds=thresholds,
                  source='prepare_bank.py::experiment', status='PUBLIC_DATA_EXPLORATION_ONLY', features=FEATURES,
                  leaking_feature='duration', fits=2, raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
                  discovery={'scope':'train_only', 'distribution':distribution,
                    'sample':pd.concat([discovery[discovery.y=='no'].head(3), discovery[discovery.y=='yes'].head(3)])[FEATURES+['y']].to_dict(orient='records'),
                    'unknown_outcome':int((discovery.poutcome=='unknown').sum()),
                    'no_previous_contact':int((discovery.pdays==-1).sum())},
                  provenance={'url':'https://archive.ics.uci.edu/dataset/222/bank+marketing','doi':'10.24432/C5K306',
                    'authors':'Moro, S., Rita, P., & Cortez, P. (2014)', 'license':'CC BY 4.0', 'file':'bank.csv',
                    'archive_url':'https://archive.ics.uci.edu/static/public/222/bank+marketing.zip'},
                  limitations=['Random subset of historical campaigns; no full timestamp or customer identifier in this extract.',
                    'Random stratified split is exploratory only, not proof of future campaign performance or customer independence.',
                    'Observed subscriptions are not the causal effect of calling; missed subscriptions are not proven lost sales.',
                    'No deployment, fairness assessment, causal validation or independent final test.'],
                  environment={'python':platform.python_version(),'sklearn':sklearn.__version__,'pandas':pd.__version__,'numpy':np.__version__})
    (ROOT/'data/split.json').write_text(json.dumps({'seed':SEED,'train':train.tolist(),'validation':validation.tolist()},indent=2))
    pd.DataFrame({'row':validation,'target':target,'score':scores['honnete'],'score_with_duration':scores['avec_fuite']}).to_csv(ROOT/'data/predictions.csv',index=False)
    (ROOT/'tutorial-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    page = ROOT/'bank-tutorial.html'
    page.write_text(re.sub(r'const D=.*?;const titles=', lambda _: 'const D='+json.dumps(result,ensure_ascii=False)+';const titles=', page.read_text()))
    write_contract(result)
    print(json.dumps({'rows':len(data),'models':models,'thresholds':thresholds},indent=2))

def write_contract(result):
    """hypotrail.results/1 output: explicit business names, declared protocol and scope."""
    protocol = {'id':'stratified-70-30','label':'Stratified random 70/30 split',
                'description':f"{result['train_rows']} training rows, {result['validation_rows']} rows validation, seed {result['seed']}. Standardization and encoding fitted on training data only.",
                'partition':{'train':result['train_rows'],'validation':result['validation_rows'],'validation_positives':result['positive_validation']},
                'scope':'exploratory','scope_justification':'Extract without complete dates or customer identifiers; validation is also used to select a threshold.'}
    model_labels = {'reference':('model-reference','Always no subscription','Constant majority class, no training'),
                    'honnete':('model-logistic-4','Logistic regression · 4 features','scikit-learn logistic regression'),
                    'avec_fuite':('model-logistic-4-duration','With duration · unavailable before the call','scikit-learn logistic regression with call duration')}
    results = []
    for key,(rid,label,method) in model_labels.items():
        m = result['models'][key]
        results.append({'id':rid,'label':label,'kind':'model_evaluation','protocol':protocol['id'],
                        'configuration':{'model':key,'decision_threshold':0.5,'features':result['features']+(['duration'] if key=='avec_fuite' else [])},
                        'method':method,'provenance':result['source'],'observations':result['validation_rows'],
                        'metrics':{'accuracy':m['accuracy'],'recall_subscriptions':m['recall'],'auc':m['auc'],'average_precision':m['average_precision']},
                        'status':'available','scope':'counterexample' if key=='avec_fuite' else 'exploratory',
                        'limitations':['duration is known only after the call.'] if key=='avec_fuite' else []})
    for t in result['thresholds']:
        results.append({'id':f"selection-{t['threshold']:.2f}",'label':'Seuil '+f"{t['threshold']:.2f}".replace('.',','),'kind':'selection','protocol':protocol['id'],
                        'configuration':{'model':'honnete','threshold':t['threshold']},'method':'Select contacts whose score exceeds the threshold',
                        'provenance':result['source'],'observations':result['validation_rows'],
                        'metrics':{'selected_contacts':t['alerts'],'subscriptions_found':t['true_alarms'],'selected_without_subscription':t['false_alarms'],
                                   'subscriptions_not_selected':t['missed'],'recall_subscriptions':t['recall'],'precision_selected':t['precision']},
                        'status':'available','scope':'exploratory','limitations':['Threshold chosen on validation: temporal evaluation would be needed.']})
    percent = lambda label, description: {'label':label,'unit':'proportion','format':'percent','direction':'higher_is_better','description':description}
    count = lambda label, unit, description, direction='context': {'label':label,'unit':unit,'format':'count','direction':direction,'description':description}
    contract = {'schema':'hypotrail.results/1','project_id':'uci-bank-marketing-v1',
        'dataset':{'id':'uci-bank-marketing','sha256':result['raw_sha256'],'rows':result['rows']},
        'generated_by':{'script':'prepare_bank.py','seed':result['seed'],'models_fitted':result['fits'],'environment':result['environment']},
        'protocols':[protocol],
        'metric_definitions':{
            'accuracy':percent('Accuracy','Share of correct predictions at threshold 0.50.'),
            'recall_subscriptions':percent('Retrieved subscriptions (recall)','Share of observed subscriptions retrieved.'),
            'auc':{'label':'AUC','unit':'unitless (0.5 = chance)','format':'number:3','direction':'higher_is_better','description':'Ranking quality between subscriptions and non-subscriptions.'},
            'average_precision':{'label':'Average precision','unit':'unitless','format':'number:3','direction':'higher_is_better','description':'Summary of the precision-recall curve.'},
            'selected_contacts':count('Selected contacts','contacts','Contacts whose score exceeds the threshold: the call workload.'),
            'subscriptions_found':count('Retrieved subscriptions','subscriptions','Observed subscriptions among selected contacts.','higher_is_better'),
            'selected_without_subscription':count('Selected without subscription','contacts','Selected contacts with no observed subscription.','lower_is_better'),
            'subscriptions_not_selected':count('Unselected subscriptions','subscriptions','Observed subscriptions outside the selection; not established lost sales.','lower_is_better'),
            'precision_selected':percent('Selection precision','Share of selected contacts with an observed subscription.')},
        'results':results,
        'display':{'examples':result['discovery']['sample'],'examples_scope':'train',
                   'target_distribution':result['discovery']['distribution'],
                   'special':{'no_previous_contact':result['discovery']['no_previous_contact'],'unknown_outcome':result['discovery']['unknown_outcome'],'train_rows':result['train_rows']}},
        'limitations':['Random subset of historical campaigns without complete dates or customer identifiers.',
            'The stratified split is exploratory: it establishes neither future-campaign performance nor customer independence.',
            'Observed subscriptions do not measure the causal effect of calling; an unselected subscription is not an established lost sale.',
            'No deployment, fairness assessment, causal validation, or independent final test.']}
    target = ROOT/'results.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(contract,ensure_ascii=False,indent=2)+'\n')

if __name__ == '__main__':
    experiment()
