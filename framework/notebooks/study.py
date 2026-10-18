"""Read an existing multitask study without fitting or holdout access."""
import marimo
app=marimo.App(width='medium')

@app.cell
def _():
 import marimo as mo
 import json,os
 from pathlib import Path
 root=Path(os.environ.get('OSML_ROOT',Path.cwd()))
 path=root/'reports/classical-study.json'
 study=json.loads(path.read_text()) if path.exists() else {}
 mo.md('# Understand this ML study\nCalculations remain exploratory. A recommendation is not production acceptance.')
 return mo,study

@app.cell
def _(mo,study):
 mo.md(f"**Task:** {study.get('task','not calculated')} · **Criterion:** {study.get('primary','not calculated')} · **Proposal :** {study.get('suggested_candidate') or 'none'}\n\nComparisons share a split and training-fitted preprocessing. Selecting the best validation result creates selection bias and requires independent confirmation.")
 return

@app.cell
def _(mo,study):
 rows=[{'model':r['model'],'state':r['status'],'criterion':str(r['metrics'].get(study.get('primary'))),'proposable':r['eligible'],'constraints':'; '.join(c['kind']+' '+c['status'] for c in r['constraints']) or 'No declared requirement'} for r in study.get('results',[])]
 mo.ui.table(rows,selection=None) if rows else mo.md('No calculation available; no substitute result.')
 return

@app.cell
def _(mo,study):
 explanations={'binary':'AUC measures ordering between two classes, not error costs or threshold quality. Check the positive class and false-positive/negative costs.',
 'multiclass':'Macro F1 weights classes equally; also inspect rare classes and business-relevant confusions.',
 'regression':'MAE uses the target unit; RMSE penalizes large errors more heavily. Inspect residuals across levels, time, and groups.',
 'ranking':'NDCG is calculated per query. Here scores come from pointwise regression; training and validation queries are disjoint.',
 'clustering':'Silhouette describes geometric separation; ARI measures stability under training resampling. Neither establishes business utility.'}
 mo.md('## Why this criterion?\n'+explanations.get(study.get('task'),'Define the task first.')+'\n\n## Optional interpretability\nNo default constraint. If requested, distinguish intrinsic readability, post-hoc explanation, and external evidence. Feature importance does not establish causality. An unevaluated hard requirement makes a candidate ineligible.')
 return

@app.cell
def _(mo,study):
 mo.md('## Explain before rerunning\nWhat changed, why, and which results become stale? The pilot archives the previous cycle. Training budgets stay cumulative; a new result does not ratify an earlier one.\n\n'+'\n'.join('- '+x for x in study.get('limitations',[])))
 return

if __name__=='__main__':app.run()
