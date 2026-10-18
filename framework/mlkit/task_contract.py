"""Classical ML task contract: strict validation and adapted questions."""
from pathlib import Path
import copy,json
import yaml

CATALOG={
 'binary':{'models':['dummy','logistic','tree','forest'],'metrics':['roc_auc','average_precision','balanced_accuracy','log_loss'],'default':'roc_auc'},
 'multiclass':{'models':['dummy','logistic','tree','forest'],'metrics':['f1_macro','balanced_accuracy','log_loss'],'default':'f1_macro'},
 'regression':{'models':['dummy','ridge','tree','forest'],'metrics':['mae','rmse','r2'],'default':'mae'},
 'ranking':{'models':['dummy','ridge','tree','forest'],'metrics':['ndcg'],'default':'ndcg'},
 'clustering':{'models':['kmeans','gaussian_mixture'],'metrics':['silhouette','stability_ari'],'default':'silhouette'},
}
DIRECTION={'log_loss':'min','mae':'min','rmse':'min',**{k:'max' for k in ['roc_auc','average_precision','balanced_accuracy','f1_macro','r2','ndcg','silhouette','stability_ari']}}
CONSTRAINTS={
 'interpretability':{'kind','hard','level','max_terms','max_depth'},
 'max_input_features':{'kind','hard','maximum'},
 'allowed_models':{'kind','hard','models'},
 'forbidden_features':{'kind','hard','columns'},
 'latency':{'kind','hard','max_batch_p95_ms','batch_size'},
 'artifact_size':{'kind','hard','max_mb'},
 'training_time':{'kind','hard','max_seconds'},
 'custom':{'kind','hard','name','evidence_required'},
}

def template(kind):
 if kind not in CATALOG:raise ValueError('Unsupported task: '+str(kind))
 return {'schema_version':1,'spec':{
  'task':{'kind':kind,'purpose':'To clarify: decision or intended result use','positive_label':1 if kind=='binary' else None,'ndcg_k':10},
  'data':{'path':'data/dev/dataset.csv','id_col':'id','target_col':None if kind=='clustering' else 'target','features':['x1','x2'],'group_col':None,'time_col':None,'query_col':'query' if kind=='ranking' else None},
  'split':{'kind':'group' if kind=='ranking' else 'random','test_size':0.25,'seed':20261017,'gap_days':0,'cutoff':None},
  'models': ['kmeans','gaussian_mixture'] if kind=='clustering' else ['dummy','logistic' if kind in {'binary','multiclass'} else 'ridge','tree'],
  'model_options':{'tree_depth':4,'n_clusters':3,'forest_trees':100},
  'evaluation':{'primary':CATALOG[kind]['default'],'stability_repeats':3,'silhouette_sample':1500},
  'constraints':[], 'budget':{'max_fits':30},
  'confirmation':{'status':'exploratory_only','independent_review_required':True},
 }}

def validate(contract):
 if set(contract)!={'schema_version','spec'} or contract['schema_version']!=1:raise ValueError('Unknown contract version/schema')
 s=contract['spec'];base=template(s.get('task',{}).get('kind'))['spec']
 if set(s)!=set(base):raise ValueError('Missing/unknown spec fields: '+str(set(s)^set(base)))
 for key in ['task','data','split','model_options','evaluation','budget','confirmation']:
  if not isinstance(s[key],dict) or set(s[key])!=set(base[key]):raise ValueError('Invalid schema: '+key)
 kind=s['task']['kind'];d=s['data'];sp=s['split']
 if not isinstance(d['features'],list) or not d['features'] or len(set(d['features']))!=len(d['features']) or not all(isinstance(x,str) for x in d['features']):raise ValueError('Features explicites distinctes required')
 reserved={d[k] for k in ['target_col','id_col','time_col','group_col','query_col'] if d[k] is not None}
 if reserved & set(d['features']):raise ValueError('Target/id/time/group/query must not appear among features')
 if kind!='clustering' and not d['target_col']:raise ValueError('Cible required')
 if kind=='clustering' and d['target_col'] is not None:raise ValueError('Clustering: target_col must be null; no implicit pseudo-target')
 if sp['kind'] not in {'random','group','time'}:raise ValueError('Unknown split')
 if not isinstance(sp['test_size'],(int,float)) or not 0<sp['test_size']<1:raise ValueError('test_size must be between 0 and 1')
 if type(sp['seed']) is not int or type(sp['gap_days']) is not int or sp['gap_days']<0:raise ValueError('Graine et gap invalides')
 if sp['kind']=='random' and (d['group_col'] or d['time_col'] or d['query_col']):raise ValueError('Declared dependence: use group or time, not random')
 if sp['kind']=='group' and not (d['group_col'] or d['query_col']):raise ValueError('Group column required')
 if sp['kind']=='time' and (not d['time_col'] or not sp['cutoff']):raise ValueError('Temporal split requires explicit time column and cutoff')
 if kind=='ranking' and (not d['query_col'] or sp['kind']!='group' or (d['group_col'] and d['group_col']!=d['query_col'])):raise ValueError('Ranking v1 requires disjoint query groups; other structures are unsupported')
 if kind=='binary' and s['task']['positive_label'] is None:raise ValueError('Classe positive explicite required')
 if type(s['task']['ndcg_k']) is not int or s['task']['ndcg_k']<1:raise ValueError('ndcg_k invalid')
 if not isinstance(s['models'],list) or not s['models'] or len(set(s['models']))!=len(s['models']) or set(s['models'])-set(CATALOG[kind]['models']):raise ValueError('Unknown, duplicate, or incompatible model; deep learning excluded')
 if s['evaluation']['primary'] not in CATALOG[kind]['metrics']:raise ValueError('Metric incompatible with the task')
 for key in ['tree_depth','n_clusters','forest_trees']:
  if type(s['model_options'][key]) is not int or s['model_options'][key]<1:raise ValueError('Invalid model option: '+key)
 if s['model_options']['n_clusters']<2:raise ValueError('Au less deux clusters')
 for k in ['stability_repeats','silhouette_sample']:
  if type(s['evaluation'][k]) is not int or s['evaluation'][k]<2:raise ValueError('Invalid evaluation parameter: '+k)
 if type(s['budget']['max_fits']) is not int or s['budget']['max_fits']<1:raise ValueError('Budget invalid')
 if s['confirmation']!={'status':'exploratory_only','independent_review_required':True}:raise ValueError('This version does not automatically certify models')
 if not isinstance(s['constraints'],list):raise ValueError('constraints must be a list')
 for c in s['constraints']:
  kindc=c.get('kind');expected=CONSTRAINTS.get(kindc)
  if expected is None or set(c)!=expected or type(c['hard']) is not bool:raise ValueError('Unknown constraint or incomplete schema: '+str(kindc))
  if kindc=='interpretability' and c['level'] not in {'intrinsic','posthoc'}:raise ValueError('Interpretability: intrinsic or posthoc')
  for key in ['max_terms','max_depth','maximum','batch_size']:
   if key in c and (type(c[key]) is not int or c[key]<1):raise ValueError('Plafond entier positif required')
  for key in ['max_batch_p95_ms','max_mb','max_seconds']:
   if key in c and (type(c[key]) not in [int,float] or not 0<c[key]<float('inf')):raise ValueError('Plafond fini positif required')
  if kindc in {'allowed_models','forbidden_features'}:
   vals=c['models' if kindc=='allowed_models' else 'columns']
   if not isinstance(vals,list) or not all(isinstance(v,str) for v in vals):raise ValueError('Liste de names required')
  if kindc=='custom' and (not str(c['name']).strip() or not str(c['evidence_required']).strip()):raise ValueError('Constraint externe : nom et evidence attendue required')
 return s

def load(root):return validate(yaml.safe_load((Path(root)/'project.yaml').read_text()))
def data_path(root,s):
 p=(Path(root)/s['data']['path']).resolve()
 if not p.is_relative_to(Path(root).resolve()):raise ValueError('Development data outside the project: prepare an explicitly authorized copy')
 return p

def questions(s):
 kind=s['task']['kind']
 out=[('Q-USE','cadrage','How will the result actually be used?','A metric alone does not define business value.'),
      ('Q-SPLIT','donnees','Are observations linked by time, person, site, or query?','The split must represent the intended generalization.'),
      ('Q-METRIC','evaluation','Which criterion and reference represent a useful improvement?','The best number can correspond to the wrong policy.'),
      ('Q-CONSTRAINTS','cadrage','Which constraints are mandatory, and which are preferences?','A high score does not compensate for violating a hard requirement.')]
 if kind=='clustering':out += [('Q-CLUSTER','cible','What action will each group enable, and how stable must it be?','Silhouette establishes neither group utility nor their real-world existence.')]
 else:out += [('Q-TARGET','cible','How is the target constructed, and when is it observable?','Provenance and maturity determine learning validity.')]
 return [{'id':id_,'phase':phase,'blocking':True,'question':q,'why':why,'consequence':'Task-adapted project.yaml contract and validation report.'} for id_,phase,q,why in out]

def plan(s):
 return {'task':s['task']['kind'],'primary':s['evaluation']['primary'],'direction':DIRECTION[s['evaluation']['primary']],
 'models':s['models'],'constraints':s['constraints'],'questions':questions(s),'protocol':'exploratory development; independent confirmation not implemented',
 'warning':'A stable partition is not necessarily useful.' if s['task']['kind']=='clustering' else 'Selection on this validation remains exploratory.'}
