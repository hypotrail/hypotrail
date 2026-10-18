"""Check task boundaries, optional constraints, and isolated onboarding."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.datasets import make_classification,make_regression,make_blobs
from mlkit import classical as c,task_contract as tc,pilot,config,tutorial


def prepare(root,kind):
 root.mkdir(parents=True,exist_ok=True);contract=tc.template(kind);s=contract['spec'];seed=20261017
 if kind=='regression':X,y=make_regression(n_samples=180,n_features=4,noise=5,random_state=seed)
 elif kind=='ranking':
  X,y=make_regression(n_samples=180,n_features=4,noise=5,random_state=seed);y=np.maximum(0,np.round((y-y.min())/50))
 elif kind=='clustering':X,y=make_blobs(n_samples=180,n_features=4,centers=3,random_state=seed)
 else:X,y=make_classification(n_samples=180,n_features=4,n_informative=3,n_redundant=0,n_classes=3 if kind=='multiclass' else 2,n_clusters_per_class=1,random_state=seed)
 s['data']['features']=['x0','x1','x2','x3'];df=pd.DataFrame(X,columns=s['data']['features']);df['id']=np.arange(len(X))
 if kind!='clustering':df['target']=y
 if kind=='ranking':df['query']=np.repeat(np.arange(30),6)
 (root/'data/dev').mkdir(parents=True,exist_ok=True);df.to_csv(root/'data/dev/dataset.csv',index=False)
 (root/'project.yaml').write_text(yaml.safe_dump(contract));return contract,df

@pytest.mark.parametrize('kind',list(tc.CATALOG))
def test_every_task_has_real_metric_and_optional_interpretability(tmp_path,kind):
 contract,df=prepare(tmp_path,kind);report=c.study(tmp_path)
 assert not contract['spec']['constraints']
 assert report['suggested_candidate'] is not None
 assert report['status']=='EXPLORATORY_ONLY'
 assert all(r['status']=='MEASURED' for r in report['results'])
 assert all(np.isfinite(r['metrics'][report['primary']]) for r in report['results'])
 if kind=='ranking':
  folder=tmp_path/'.osml/classical'/report['run'];a=pd.read_csv(folder/'train-ids.csv').id;b=pd.read_csv(folder/'validation-ids.csv').id
  assert not set(df.set_index('id').loc[a,'query'])&set(df.set_index('id').loc[b,'query'])
 if kind=='clustering':assert all(-1<=r['metrics']['stability_ari']<=1 for r in report['results'])

@pytest.mark.parametrize('edit',[lambda s:s['models'].append('neural_network'),lambda s:s['evaluation'].update(primary='roc_auc'),lambda s:s['data'].update(target_col=None)])
def test_regression_rejects_incompatible_contract(edit):
 contract=tc.template('regression');edit(contract['spec'])
 with pytest.raises(ValueError):tc.validate(contract)

def test_no_silent_hard_constraint_relaxation(tmp_path):
 contract,_=prepare(tmp_path,'binary');s=contract['spec'];s['models']=['forest','logistic'];s['constraints']=[{'kind':'interpretability','hard':True,'level':'intrinsic','max_terms':5,'max_depth':3}]
 (tmp_path/'project.yaml').write_text(yaml.safe_dump(contract));report=c.study(tmp_path)
 assert report['results'][0]['status']=='EXCLUDED_BEFORE_FIT' and report['suggested_candidate']=='logistic'
 s['constraints']=[{'kind':'custom','hard':True,'name':'fairness','evidence_required':'validation externe'}]
 (tmp_path/'project.yaml').write_text(yaml.safe_dump(contract));report=c.study(tmp_path)
 assert report['suggested_candidate'] is None and all(not r['eligible'] for r in report['results'])
 s['constraints'][0]['hard']=False;(tmp_path/'project.yaml').write_text(yaml.safe_dump(contract));assert c.study(tmp_path)['suggested_candidate'] is not None

def test_preprocess_fitted_on_training_only():
 s=tc.template('regression')['spec'];train=pd.DataFrame({'x1':[1.,2.,3.],'x2':[1.,np.nan,3.]});model=c.pipeline('ridge',train,s,1).fit(train,[1.,2.,3.])
 model.predict(pd.DataFrame({'x1':[1e9],'x2':[1e9]}))
 assert list(model['preprocess'].named_transformers_['num']['scale'].mean_)==[2.,2.]

def test_time_split_respects_gap_and_refuses_subject_overlap(tmp_path):
 contract,df=prepare(tmp_path,'regression');s=contract['spec'];s['data'].update(time_col='date',group_col='person');s['split'].update(kind='time',cutoff='2026-04-01',gap_days=10)
 df['date']=pd.date_range('2026-01-01',periods=len(df));df['person']=range(len(df))
 tr,va=c.split(df,df.target,s)
 assert df.iloc[tr].date.max()<pd.Timestamp('2026-03-22') and df.iloc[va].date.min()>=pd.Timestamp('2026-04-01')
 df['person']=0
 with pytest.raises(ValueError,match='Groups overlap'):c.split(df,df.target,s)

def test_budget_cumulative_after_contract_change(tmp_path):
 contract,_=prepare(tmp_path,'clustering');s=contract['spec'];s['budget']['max_fits']=8
 (tmp_path/'project.yaml').write_text(yaml.safe_dump(contract));c.study(tmp_path)
 contract['spec']['task']['purpose']='Other description';(tmp_path/'project.yaml').write_text(yaml.safe_dump(contract))
 with pytest.raises(ValueError,match='Total budget'):c.study(tmp_path)
 ledger=[json.loads(x) for x in (tmp_path/'.osml/classical/fits.jsonl').read_text().splitlines()];assert sum(x['reserved'] for x in ledger)==8

def test_classical_pilot_revision_preserves_cycle_and_invalidates_results(tmp_path,monkeypatch):
 contract,_=prepare(tmp_path,'regression');monkeypatch.setattr(config,'ROOT',tmp_path)
 state=pilot.init('auto');assert {q['id'] for q in pilot.questions()}=={'Q-USE','Q-SPLIT','Q-METRIC','Q-CONSTRAINTS','Q-TARGET'}
 assert pilot.remaining(state)[0][0]=='discovery'
 assert pilot.remaining(state)[3][0]=='classical-run'
 state['steps']['classical-run']={'returncode':0};pilot.save(state)
 path=tmp_path/'changes.json';path.write_text(json.dumps({'question':'Q-CONSTRAINTS','answer':'No interpretability requirement; at most two features','rationale':'Reduce the number of sources to maintain','updates':{'spec.constraints':[{'kind':'max_input_features','hard':True,'maximum':2}]}}))
 pilot.revise(state,path,state['context']);assert state['revision_pending'] and state['steps']=={}
 assert (tmp_path/'.pilot/iterations/0001/project.yaml').exists()
 pilot.iterate(state,'Revisit constraints');assert state['iteration']==2
 assert c.study(tmp_path)['suggested_candidate'] is None

def test_tutorial_results_demonstrate_both_traps_and_do_not_require_interpretability(tmp_path):
 destination=tmp_path/'demo';tutorial.create(destination)
 report=json.loads((destination/'reports/tutorial-results.json').read_text());ref=report['models']['reference'];leak=report['models']['avec_fuite'];honest=report['models']['honnete']
 assert ref['accuracy']>.85 and ref['recall']==0
 assert leak['auc']>.99 and leak['auc']>honest['auc']+.05
 assert not tc.load(destination)['constraints']
 assert not (destination/'answers.yaml').exists() and not (destination/'.pilot').exists()
 assert json.loads((destination/'tutorial-manifest.json').read_text())['no_real_decisions']
 before=(destination/'tutorial.html').read_bytes()
 with pytest.raises(ValueError,match='must be new'):tutorial.create(destination)
 assert (destination/'tutorial.html').read_bytes()==before

def test_positive_label_is_not_assumed_one(tmp_path):
 contract,df=prepare(tmp_path,'binary');df.target=df.target.map({0:'incident',1:'normal'});df.to_csv(tmp_path/'data/dev/dataset.csv',index=False);contract['spec']['task']['positive_label']='incident'
 (tmp_path/'project.yaml').write_text(yaml.safe_dump(contract));report=c.study(tmp_path)
 assert report['suggested_candidate'] is not None and report['results'][1]['metrics']['roc_auc']>.7

def test_stability_does_not_recommend_collapsed_clusters(tmp_path):
 contract,df=prepare(tmp_path,'clustering');df[contract['spec']['data']['features']]=0
 df.to_csv(tmp_path/'data/dev/dataset.csv',index=False);contract['spec']['models']=['kmeans'];contract['spec']['evaluation']['primary']='stability_ari'
 (tmp_path/'project.yaml').write_text(yaml.safe_dump(contract))
 with pytest.warns(UserWarning):report=c.study(tmp_path)
 assert report['results'][0]['metrics']['stability_ari']==1.0
 assert report['results'][0]['metrics']['clusters_observed']==1
 assert report['suggested_candidate'] is None

def test_integer_time_column_refused(tmp_path):
 contract,df=prepare(tmp_path,'regression');s=contract['spec'];s['data'].update(time_col='model_year');s['split'].update(kind='time',cutoff='1979-01-01')
 df['model_year']=np.repeat(np.arange(70,82),15)
 tc.validate(contract)
 with pytest.raises(ValueError,match='missing capability: integer-year temporal split'):c.split(df,df.target,s)
 df['model_year']=pd.to_datetime((1900+df['model_year']).astype(str)+'-01-01')
 tr,va=c.split(df,df.target,s)
 assert df.iloc[tr].model_year.max()<pd.Timestamp('1979-01-01')<=df.iloc[va].model_year.min()
