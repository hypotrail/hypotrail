"""Exploratory classical ML studies with explicit contracts and optional constraints.
Produces no acceptance decision, confirmatory interval, or production package.
"""
from pathlib import Path
import argparse, hashlib, html, json, os, pickle, sys, time, uuid
import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn import metrics
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.cluster import KMeans
from sklearn.mixture import GaussianMixture
from . import task_contract as tc

def write(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False));os.replace(tmp,path)

def dataset(root,s):
 d=s['data'];df=pd.read_csv(tc.data_path(root,s))
 required=set(d['features'])|{v for k,v in d.items() if k.endswith('_col') and v}
 if required-set(df.columns):raise ValueError('Missing columns: '+str(required-set(df.columns)))
 if df[d['id_col']].isna().any() or df[d['id_col']].duplicated().any():raise ValueError('A unique, non-empty row identifier is required')
 if len(df)<20:raise ValueError('At least 20 observations required for this exploratory study')
 for col in [d['group_col'],d['query_col'],d['time_col'],d['target_col']]:
  if col and df[col].isna().any():raise ValueError('Missing metadata/target: '+col)
 numeric=df[d['features']].select_dtypes(include='number')
 if np.isinf(numeric.to_numpy()).any():raise ValueError('Infinite feature values are not allowed')
 kind=s['task']['kind'];y=None if kind=='clustering' else df[d['target_col']]
 if kind=='binary' and (y.nunique()!=2 or s['task']['positive_label'] not in set(y)):raise ValueError('Two classes and the positive class are required')
 if kind=='multiclass' and y.nunique()<3:raise ValueError('At least three classes are required')
 if kind in {'regression','ranking'} and (not pd.api.types.is_numeric_dtype(y) or not np.isfinite(y).all()):raise ValueError('A finite numeric target is required')
 if kind=='ranking' and (y<0).any():raise ValueError('Nonnegative NDCG relevance is required')
 if kind=='clustering' and len(numeric.columns)!=len(d['features']):raise ValueError('Clustering v1 supports numeric features only; specify categorical distance separately')
 return df,y

def split(df,y,s):
 d=s['data'];p=s['split'];idx=np.arange(len(df));g=d['group_col'] or d['query_col']
 if p['kind']=='time':
  # pd.to_datetime reads integers as nanoseconds since 1970, so model years 70..82 would
  # silently become 1970-01-01. Refuse instead of producing a wrong chronology.
  if pd.api.types.is_integer_dtype(df[d['time_col']]):raise ValueError(f"Time column {d['time_col']!r} has an integer dtype; missing capability: integer-year temporal split")
  dates=pd.to_datetime(df[d['time_col']],utc=True,errors='raise');cut=pd.to_datetime(p['cutoff'],utc=True)
  tr=idx[dates<cut-pd.Timedelta(days=p['gap_days'])];va=idx[dates>=cut]
  if g and set(df.iloc[tr][g])&set(df.iloc[va][g]):raise ValueError('Groups overlap between temporal training and validation: clarify the protocol')
 elif p['kind']=='group':
  tr,va=next(GroupShuffleSplit(n_splits=1,test_size=p['test_size'],random_state=p['seed']).split(df,groups=df[g]))
 else:tr,va=train_test_split(idx,test_size=p['test_size'],random_state=p['seed'],stratify=y if s['task']['kind'] in {'binary','multiclass'} else None)
 if len(tr)<5 or len(va)<5:raise ValueError('Partition too small: at least 5 rows in each part')
 if s['task']['kind'] in {'binary','multiclass'} and (set(y.iloc[tr])!=set(y) or set(y.iloc[va])!=set(y)):raise ValueError('A partition lacks classes; no silently partial metric')
 return tr,va

def pipeline(name,X,s,seed):
 nums=list(X.select_dtypes(include='number').columns);cats=[c for c in X if c not in nums]
 prep=ColumnTransformer([('num',Pipeline([('impute',SimpleImputer(strategy='median',keep_empty_features=True)),('scale',StandardScaler())]),nums),('cat',Pipeline([('impute',SimpleImputer(strategy='most_frequent',keep_empty_features=True)),('encode',OneHotEncoder(handle_unknown='ignore',sparse_output=False))]),cats)])
 classify=s['task']['kind'] in {'binary','multiclass'};o=s['model_options']
 models={'dummy':lambda:DummyClassifier(strategy='prior') if classify else DummyRegressor(strategy='median'),
 'logistic':lambda:LogisticRegression(max_iter=1000,random_state=seed), 'ridge':lambda:Ridge(),
 'tree':lambda:(DecisionTreeClassifier if classify else DecisionTreeRegressor)(max_depth=o['tree_depth'],random_state=seed),
 'forest':lambda:(RandomForestClassifier if classify else RandomForestRegressor)(n_estimators=o['forest_trees'],random_state=seed,n_jobs=1),
 'kmeans':lambda:KMeans(n_clusters=o['n_clusters'],n_init=10,random_state=seed),
 'gaussian_mixture':lambda:GaussianMixture(n_components=o['n_clusters'],random_state=seed)}
 return Pipeline([('preprocess',prep),('model',models[name]())])

def score(model,X,y,df,s):
 kind=s['task']['kind'];pred=model.predict(X);out={}
 if kind in {'binary','multiclass'}:
  prob=model.predict_proba(X);classes=model.classes_
  out={'balanced_accuracy':float(metrics.balanced_accuracy_score(y,pred)),'log_loss':float(metrics.log_loss(y,prob,labels=classes))}
  if kind=='binary':
   pos=s['task']['positive_label'];p=prob[:,list(classes).index(pos)];truth=(y==pos).astype(int)
   out.update(roc_auc=float(metrics.roc_auc_score(truth,p)),average_precision=float(metrics.average_precision_score(truth,p)))
  else:out['f1_macro']=float(metrics.f1_score(y,pred,average='macro'))
 elif kind=='regression':out={'mae':float(metrics.mean_absolute_error(y,pred)),'rmse':float(np.sqrt(metrics.mean_squared_error(y,pred))),'r2':float(metrics.r2_score(y,pred))}
 elif kind=='ranking':
  scores=[];skipped=0
  for _,positions in df.reset_index(drop=True).groupby(s['data']['query_col']).indices.items():
   truth=y.to_numpy()[positions]
   if len(positions)<2 or max(truth)<=0:skipped+=1;continue
   scores.append(metrics.ndcg_score([truth],[pred[positions]],k=s['task']['ndcg_k']))
  if not scores:raise ValueError('No evaluable query for NDCG')
  out={'ndcg':float(np.mean(scores)),'queries_evaluated':len(scores),'queries_skipped':skipped}
 else:
  z=model['preprocess'].transform(X);size=min(len(z),s['evaluation']['silhouette_sample'])
  sampled=np.random.default_rng(s['split']['seed']).choice(len(z),size=size,replace=False)
  labels=pred[sampled]
  out={'silhouette':float(metrics.silhouette_score(z[sampled],labels)) if 1<len(set(labels))<len(labels) else None,'clusters_observed':len(set(pred)),'cluster_sizes':{str(k):int(v) for k,v in zip(*np.unique(pred,return_counts=True))}}
 return out,pred

def constraints(name,s,model=None,seconds=None,batch_ms=None,size_mb=None):
 """No declared constraint means no implicit interpretability requirement."""
 rows=[];features=s['data']['features']
 for c in s['constraints']:
  k=c['kind'];ok=None;why='Evidence unavailable; review required'
  if k=='allowed_models':ok=name in c['models'];why='Explicitly authorized model catalog'
  elif k=='max_input_features':ok=len(features)<=c['maximum'];why=f'{len(features)} declared input features'
  elif k=='forbidden_features':ok=not set(features)&set(c['columns']);why='Checks declared names; does not detect proxies'
  elif k=='interpretability' and c['level']=='intrinsic':
   ok=name in {'dummy','logistic','ridge','tree'}
   if name=='tree':ok=ok and s['model_options']['tree_depth']<=c['max_depth']
   if model is not None:ok=ok and len(model['preprocess'].get_feature_names_out())<=c['max_terms']
   elif ok:ok=None
   why='Bounded structural readability; human understanding still needs confirmation'
  elif k=='interpretability':why='Post-hoc explanations are not implemented in this adapter; no equivalence with a readable model'
  elif k=='training_time' and seconds is not None:ok=seconds<=c['max_seconds'];why=f'{seconds:.4f} s on this machine'
  elif k=='latency' and batch_ms is not None:ok=batch_ms[c['batch_size']]<=c['max_batch_p95_ms'];why=f"local p95: {batch_ms[c['batch_size']]:.4f} ms / batch of {c['batch_size']}; not an SLA"
  elif k=='artifact_size' and size_mb is not None:ok=size_mb<=c['max_mb'];why=f'{size_mb:.4f} serialized MB'
  elif k=='custom':why=c['name']+' — expected evidence: '+c['evidence_required']
  rows.append({'kind':k,'hard':c['hard'],'status':'PASS' if ok is True else 'FAIL' if ok is False else 'NOT_ASSESSED','reason':why})
 return rows

def reserve(root,s,count):
 """Cooperative local log; not a control against a hostile agent."""
 import fcntl
 folder=Path(root)/'.osml/classical';folder.mkdir(parents=True,exist_ok=True)
 with (folder/'budget.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  ledger=folder/'fits.jsonl';rows=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
  spent=sum(r['reserved'] for r in rows)
  if spent+count>s['budget']['max_fits']:raise ValueError(f'Total budget exceeded: {spent}+{count}>{s["budget"]["max_fits"]}; a revision does not reset the counter')
  run=uuid.uuid4().hex[:12]
  with ledger.open('a') as f:f.write(json.dumps({'run':run,'reserved':count,'time':time.time()})+'\n')
 return run

def profile(root):
 s=tc.load(root);df,y=dataset(root,s);tr,va=split(df,y,s)
 obj={'task':s['task']['kind'],'rows':len(df),'train':len(tr),'validation':len(va),'features':s['data']['features'],'missing':{c:int(df[c].isna().sum()) for c in s['data']['features']},'constraints':s['constraints'],'interpretability_required':any(c['kind']=='interpretability' for c in s['constraints'])}
 write(Path(root)/'reports/classical-profile.json',obj);return obj

def study(root):
 root=Path(root);s=tc.load(root);df,y=dataset(root,s);tr,va=split(df,y,s);X=df[s['data']['features']]
 candidates=[];rows=[]
 for name in s['models']:
  cs=constraints(name,s)
  if any(c['hard'] and c['status']=='FAIL' for c in cs):rows.append({'model':name,'status':'EXCLUDED_BEFORE_FIT','metrics':{},'constraints':cs,'eligible':False})
  else:candidates.append(name)
 repeats=s['evaluation']['stability_repeats'] if s['task']['kind']=='clustering' else 0
 run=reserve(root,s,len(candidates)*(1+repeats));seed=s['split']['seed'];folder=root/'.osml/classical'/run;folder.mkdir()
 pd.DataFrame({'id':df.iloc[tr][s['data']['id_col']]}).to_csv(folder/'train-ids.csv',index=False)
 pd.DataFrame({'id':df.iloc[va][s['data']['id_col']]}).to_csv(folder/'validation-ids.csv',index=False)
 for name in candidates:
  start=time.monotonic()
  try:
   model=pipeline(name,X.iloc[tr],s,seed);model.fit(X.iloc[tr],None if y is None else y.iloc[tr]);seconds=time.monotonic()-start
   result,pred=score(model,X.iloc[va],None if y is None else y.iloc[va],df.iloc[va],s)
   if repeats:
    ari=[]
    for i in range(repeats):
     boot=np.random.default_rng(seed+i+1).choice(tr,size=len(tr),replace=True)
     alternate=pipeline(name,X.iloc[boot],s,seed+i+1).fit(X.iloc[boot]);ari.append(metrics.adjusted_rand_score(pred,alternate.predict(X.iloc[va])))
    result['stability_ari']=float(np.mean(ari));result['stability_ari_replicates']=[float(a) for a in ari]
   times={}
   for batch in {c['batch_size'] for c in s['constraints'] if c['kind']=='latency'}:
    sample=X.iloc[np.resize(va,batch)];model.predict(sample);measure=[]
    for _ in range(10):
     t=time.perf_counter();model.predict(sample);measure.append(1000*(time.perf_counter()-t))
    times[batch]=float(np.percentile(measure,95))
   cs=constraints(name,s,model,seconds,times,len(pickle.dumps(model))/1e6)
   primary=result[s['evaluation']['primary']];eligible=primary is not None and np.isfinite(primary) and all(c['status']=='PASS' for c in cs if c['hard'])
   if repeats:eligible=eligible and 1<result['clusters_observed']<len(va)
   rows.append({'model':name,'status':'MEASURED','metrics':result,'constraints':cs,'eligible':bool(eligible),'training_seconds':seconds})
   pd.DataFrame({'id':df.iloc[va][s['data']['id_col']].to_numpy(),'prediction':pred}).to_csv(folder/(name+'-predictions.csv'),index=False)
  except (ValueError,TypeError,RuntimeError) as exc:rows.append({'model':name,'status':'ERROR','error':str(exc),'metrics':{},'constraints':[],'eligible':False})
 hashes={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'project.yaml',tc.data_path(root,s)]}
 hashes['implementation']=hashlib.sha256(Path(__file__).read_bytes()+Path(tc.__file__).read_bytes()).hexdigest()
 metric=s['evaluation']['primary'];eligible=[r for r in rows if r['eligible']]
 best=(min if tc.DIRECTION[metric]=='min' else max)(eligible,key=lambda r:r['metrics'][metric])['model'] if eligible else None
 obj={'status':'EXPLORATORY_ONLY','run':run,'task':s['task']['kind'],'primary':metric,'direction':tc.DIRECTION[metric],'suggested_candidate':best,'contract':s,'hashes':hashes,'versions':{'python':sys.version.split()[0],'sklearn':sklearn.__version__,'numpy':np.__version__,'pandas':pd.__version__},'train_rows':len(tr),'validation_rows':len(va),'results':rows,'limitations':['Selection on development validation without confirmatory guarantees or confidence intervals.','Optional constraints: an unevaluated hard requirement prevents recommendation.','Local budgets and hashes can be changed by the owner; no sandbox.','No universal automatic detection of leakage, dependence, or bias.']}
 write(folder/'study.json',obj);write(root/'reports/classical-study.json',obj);render(root,obj);return obj

def render(root,obj):
 e=lambda v:html.escape(str(v),quote=True)
 rows=''.join('<tr><td>'+e(r['model'])+'</td><td>'+e(r['status'])+'</td><td>'+e(r['metrics'].get(obj['primary'],'—'))+'</td><td>'+('Eligible' if r['eligible'] else 'Ineligible')+'</td><td>'+('<br>'.join(e(c['kind']+': '+c['status']+' — '+c['reason']) for c in r['constraints']) or e(r.get('error','No constraint requested')))+'</td></tr>' for r in obj['results'])
 content=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Hypotrail · ML study</title><style>body{{font:16px/1.6 system-ui;background:#f1f5ef;color:#193a32;margin:0}}main{{max-width:1100px;margin:auto;padding:40px 24px}}h1{{font-size:42px}}section{{background:white;border:1px solid #d4e2d9;border-radius:18px;padding:25px;margin:22px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #ddd;vertical-align:top}}.scroll{{overflow:auto}}.tag{{color:#8b5409}}summary{{cursor:pointer}}</style><main><p>HYPOTRAIL / CLASSICAL STUDY</p><h1>{e(obj['task'])} · results and limitations</h1><p class="tag">Exploration only; no production acceptance</p><section><h2>What limits the conclusion</h2><p>No confirmatory evidence of generalization. A gain establishes neither business availability nor split validity. Keeping the reference or concluding insufficient evidence remains possible.</p><ul>{"".join("<li>"+e(x)+"</li>" for x in obj["limitations"])}</ul></section><section><h2>Pilot recommendation</h2><p>Candidate to examine: <b>{e(obj['suggested_candidate'] or 'no eligible candidate')}</b> according to {e(obj['primary'])} ({e(obj['direction'])}). Soft preferences remain trade-offs and are not added to the score.</p><p>Interpretability: {('declared requirement' if any(c['kind']=='interpretability' for c in obj['contract']['constraints']) else 'not requested (optional)')}.</p></section><section class="scroll"><table><tr><th>Model</th><th>State</th><th>{e(obj['primary'])}</th><th>Contract constraints</th><th>Evidence / limits</th></tr>{rows}</table></section><section><h2>Before deciding</h2><ul>{''.join('<li>'+e(x)+'</li>' for x in obj['limitations'])}</ul><details><summary>Contract and provenance</summary><pre style="white-space:pre-wrap">{e(json.dumps({'contract':obj['contract'],'hashes':obj['hashes'],'versions':obj['versions']},ensure_ascii=False,indent=2))}</pre></details></section></main></html>'''
 (Path(root)/'reports/classical-study.html').write_text(__import__('mlkit.presentation',fromlist=['polish']).polish(content))

def main(argv=None):
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--root',default=os.environ.get('OSML_ROOT','.'));sub=ap.add_subparsers(dest='action',required=True)
 p=sub.add_parser('init');p.add_argument('--task',choices=sorted(tc.CATALOG),required=True)
 for command in ['plan','profile','run']:sub.add_parser(command)
 args=ap.parse_args(argv);root=Path(args.root).resolve()
 try:
  if args.action=='init':
   root.mkdir(parents=True,exist_ok=True)
   with (root/'project.yaml').open('x') as f:yaml.safe_dump(tc.template(args.task),f,allow_unicode=True,sort_keys=False)
   obj={'contract':str(root/'project.yaml')}
  elif args.action=='plan':obj=tc.plan(tc.load(root))
  elif args.action=='profile':obj=profile(root)
  else:obj=study(root)
  print(json.dumps(obj,ensure_ascii=False,indent=2));return 0
 except (ValueError,FileNotFoundError,FileExistsError,KeyError) as exc:print('CLASSICAL ML: '+str(exc),file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
