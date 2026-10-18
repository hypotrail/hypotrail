"""Descriptive charts from existing training partitions only; no model fitting."""
from pathlib import Path
import json, hashlib
import numpy as np
import pandas as pd
from prepare_auto_mpg import load
ROOT=Path(__file__).resolve().parent

def histogram(s,label,unit):
 values=s.dropna();counts,edges=np.histogram(values,bins=12)
 return {'kind':'bars','title':label,'unit':'observations','note':'Equal-width bins; extreme values retained. The last boundary is inclusive.', 'items':[{'label':f'{a:.1f}–{b:.1f} {unit}','value':int(n),'n':int(n)} for a,b,n in zip(edges[:-1],edges[1:],counts)]}

def build(name):
 folder=ROOT/'projects'/name;project=json.loads((folder/'project.json').read_text());results=json.loads((folder/'results.json').read_text())
 if name=='bank-marketing':
  raw=ROOT/'data/bank.csv';all_rows=pd.read_csv(raw,sep=';');indices=json.loads((ROOT/'data/split.json').read_text())['train'];train=all_rows.iloc[indices].copy();target='subscribed';train[target]=(train.y=='yes').astype(int)
  charts=[{'kind':'bars','title':'Are subscriptions rare?','unit':'observations','note':'Complete target distribution in training data.', 'items':[{'label':k,'value':int((train.y==v).sum()),'n':int((train.y==v).sum())} for k,v in [('No','no'),('Yes','yes')]]},histogram(train.balance,'Which balances are observed?','€')]
  for col,title in [('poutcome','What does the previous campaign show?'),('previous','How does previous contact relate to subscriptions?')]:
   groups=train.groupby(col)[target].agg(['mean','size']);charts.append({'kind':'bars','title':title,'unit':'% de subscriptions','note':'Observed association, not a causal effect. Read rates with sample sizes; small groups are fragile.', 'items':[{'label':str(k),'value':round(float(v['mean'])*100,2),'n':int(v['size'])} for k,v in groups.iterrows()]})
  cols=['balance','previous','pdays','poutcome','duration','y'];special=[f"{int((train.pdays==-1).sum())} pdays = −1 values: no previous contact, not a negative duration.",f"{int((train.poutcome=='unknown').sum())} unknown previous outcomes: explicit categories, not empty cells.",'duration is known after the call and excluded from pre-call selection.']
 else:
  raw=folder/'data/auto-mpg.data';all_rows=load();train=all_rows[all_rows.model_year.between(70,78)].copy();indices=train.index.tolist();cols=['mpg','weight','horsepower','cylinders','model_year'];special=['Higher mpg means more distance per gallon and therefore better fuel efficiency.','1970–1978 only. Validation years 1979–1982 are not explored here.','Missing values are counted before imputation.']
  charts=[histogram(train.mpg,'Quels niveaux de mpg observe-t-on ?','mpg'),{'kind':'scatter','title':'Do heavier cars have lower mpg?','x_label':'Weight (lb)','y_label':'Efficiency (mpg)','unit':'mpg','note':'Each point is a training car. Click or use the keyboard to inspect values. Association does not establish causality.','points':[{'x':float(row.weight),'y':float(row.mpg),'label':str(row.car_name)+' · '+str(int(row.model_year)+1900)} for _,row in train.iterrows()]}]
  for col,title in [('cylinders','How does mpg vary by cylinder count?'),('model_year','How does mpg change within training years?')]:
   items=[]
   for k,g in train.groupby(col):
    items.append({'label':str(int(k)+(1900 if col=='model_year' else 0)),'value':round(float(g.mpg.median()),2),'n':len(g),'q1':round(float(g.mpg.quantile(.25)),2),'q3':round(float(g.mpg.quantile(.75)),2)})
   charts.append({'kind':'bars','title':title,'unit':'mpg (median)','note':'Median by group. The table also includes the first and third quartiles and sample sizes.', 'items':items})
 summaries=[]
 for col in cols:
  s=train[col];v={'column':col,'missing':int(s.isna().sum()),'unique':int(s.nunique())}
  if pd.api.types.is_numeric_dtype(s):
   q=s.quantile([.25,.75]);iqr=q.iloc[1]-q.iloc[0];v.update(min=float(s.min()),median=float(s.median()),max=float(s.max()),outliers=int(((s<q.iloc[0]-1.5*iqr)|(s>q.iloc[1]+1.5*iqr)).sum()))
  summaries.append(v)
 eda={'scope':'train_only','rows':len(train),'dataset_sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'row_indices':list(map(int,indices)),'duplicates':int(train[cols].duplicated().sum()),'columns':summaries,'notes':special,'charts':charts}
 results['display']['eda']=eda;(folder/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 first=next(iter(project['activities'].values()));first['blocks']=[b for b in first['blocks'] if b['component'] not in ['distribution','data_explorer']];first['blocks'].insert(1,{'component':'data_explorer','title':'Explore the training data','source':'eda'})
 journey_path=ROOT/'journeys'/(project['journey']['id']+'.json');journey=json.loads(journey_path.read_text())
 journey['activities'][0]['components']=[c for c in journey['activities'][0]['components'] if c not in ['distribution','data_explorer']]+['data_explorer']
 journey_path.write_text(json.dumps(journey,ensure_ascii=False,indent=2)+'\n')
 (folder/'project.json').write_text(json.dumps(project,ensure_ascii=False,indent=2)+'\n')
 print(name,len(train))
if __name__=='__main__':
 for name in ['bank-marketing','auto-mpg']:build(name)
