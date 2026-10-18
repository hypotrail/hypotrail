"""Marimo onboarding notebook: calculated results and pitfalls, without retraining."""
import marimo
app=marimo.App(width='medium')

@app.cell
def _():
 import marimo as mo
 import json
 from pathlib import Path
 evidence=Path(__file__).resolve().parents[1]/'reports/tutorial-results.json'
 data=json.loads(evidence.read_text()) if evidence.exists() else {}
 mo.md('# Your first ML study\nSynthetic data only. This notebook explains tutorial results without fitting new models.')
 return mo,data

@app.cell
def _(mo,data):
 mo.md(f"**{data.get('rows','Not calculated')} observations** · seed {data.get('seed','missing')}\n\nWe predict a future incident. Information obtained after the event is unavailable at decision time even if it improves validation.")
 return

@app.cell
def _(mo,data):
 rows=[{'model':k,**v} for k,v in data.get('models',{}).items()]
 mo.ui.table(rows,selection=None) if rows else mo.md('Run the tutorial to produce actual results.')
 return

@app.cell
def _(mo):
 mo.md('## Two pitfalls\n**Accuracy:** always predicting the majority class can look good while missing every incident.\n\n**Target leakage:** inspect availability when a score seems almost perfect. Even weak leakage is invalid; performance alone does not detect it.\n\n**Preprocessing:** fit imputation and standardization on training data inside a pipeline. Preprocessing before splitting can leak validation information.')
 return

@app.cell
def _(mo,data):
 mo.ui.table(data.get('thresholds',[]),selection=None)
 return

@app.cell
def _(mo):
 mo.md('## What your choice changes\nLower thresholds can detect more incidents and create more false alerts. The useful trade-off depends on capacity and error costs. Choosing on validation remains exploratory.\n\n## Optional interpretability\nThe method imposes no default requirement. Translate any actual requirement into verifiable criteria. A simple model is not automatically understood, and an explanation is not causal evidence.\n\n## Start a real project\nRevisit objective, target, split, metrics, and constraints. Never import exercise answers as real decisions.')
 return

if __name__=='__main__':app.run()
