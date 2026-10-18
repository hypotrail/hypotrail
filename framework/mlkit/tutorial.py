"""Reproducible synthetic-data onboarding; no real decision."""
from pathlib import Path
import json, shutil
import numpy as np
import pandas as pd
import yaml
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, recall_score, precision_score, roc_auc_score, confusion_matrix
from . import task_contract as tc
from .classical import write

SEED=20261017

def experiment():
 """Leakage is deliberately and explicitly constructed after the target."""
 # Known teaching generator, not selection of the best random draw:
 # logit P(incident|X) = -3.5 + 1.6*x1 + 0.8*x2 + 0.3*x3.
 rng=np.random.default_rng(SEED);X=rng.normal(size=(1200,4))
 probability=1/(1+np.exp(-(-3.5+1.6*X[:,0]+.8*X[:,1]+.3*X[:,2])))
 y=rng.binomial(1,probability);cols=['signal_a','signal_b','signal_c','noise']
 df=pd.DataFrame(X,columns=cols);df.insert(0,'id',np.arange(len(df)));df['incident']=y
 df['incident_confirme_apres_decision']=y+rng.normal(0,.08,len(y))
 tr,va=train_test_split(np.arange(len(y)),test_size=.3,stratify=y,random_state=SEED)
 models={};predictions={}
 for name,features in [('reference',cols),('honnete',cols),('avec_fuite',cols+['incident_confirme_apres_decision'])]:
  m=make_pipeline(SimpleImputer(),StandardScaler(),DummyClassifier(strategy='prior') if name=='reference' else LogisticRegression(max_iter=1000,random_state=SEED))
  m.fit(df.iloc[tr][features],y[tr]);p=m.predict_proba(df.iloc[va][features])[:,1];predictions[name]=p
  lab=(p>=.5).astype(int);models[name]={'accuracy':float(accuracy_score(y[va],lab)),'recall':float(recall_score(y[va],lab,zero_division=0)),'auc':float(roc_auc_score(y[va],p))}
 thresholds=[]
 for threshold in [.1,.2,.35,.5]:
  lab=(predictions['honnete']>=threshold).astype(int);tn,fp,fn,tp=confusion_matrix(y[va],lab,labels=[0,1]).ravel()
  thresholds.append({'threshold':threshold,'recall':float(recall_score(y[va],lab,zero_division=0)),'precision':float(precision_score(y[va],lab,zero_division=0)),'false_alarms':int(fp),'missed':int(fn),'true_alarms':int(tp),'alerts':int(sum(lab))})
 info={'seed':SEED,'rows':len(df),'train_rows':len(tr),'validation_rows':len(va),'positive_validation':int(y[va].sum()),'models':models,'thresholds':thresholds,'source':'mlkit/tutorial.py::experiment','status':'SYNTHETIC_TUTORIAL_ONLY','features':cols,'leaking_feature':'incident_confirme_apres_decision','fits':3}
 return df,info

def create(destination):
 destination=Path(destination)
 if destination.exists():raise ValueError('Tutorial directory must be new; existing data will not be overwritten')
 df,info=experiment();destination.mkdir(parents=True)
 (destination/'data/dev').mkdir(parents=True);df.to_csv(destination/'data/dev/dataset.csv',index=False)
 contract=tc.template('binary');s=contract['spec'];s['data'].update(target_col='incident',features=info['features']);s['task']['purpose']='Synthetic exercise: detect incidents before they occur';s['split']['test_size']=.3
 (destination/'project.yaml').write_text(yaml.safe_dump(contract,allow_unicode=True,sort_keys=False))
 write(destination/'reports/tutorial-results.json',info)
 write(destination/'tutorial-manifest.json',{'purpose':'onboarding_only','seed':SEED,'no_real_decisions':True,'no_holdout':True})
 template=(Path(__file__).resolve().parents[1]/'templates/tutorial.html').read_text()
 (destination/'tutorial.html').write_text(template.replace('__TUTORIAL_DATA__',json.dumps(info,ensure_ascii=False).replace('<','\\u003c')))
 (destination/'notebooks').mkdir();shutil.copy2(Path(__file__).resolve().parents[1]/'notebooks/tutorial.py',destination/'notebooks/tutorial.py')
 return {'tutorial':str(destination/'tutorial.html'),'notebook':str(destination/'notebooks/tutorial.py'),'dataset':str(destination/'data/dev/dataset.csv'),'status':'SYNTHETIC_TUTORIAL_ONLY','next':'The pilot opens the workflow, asks one question at a time, and explains choices; tutorial answers ratify no real project.'}
