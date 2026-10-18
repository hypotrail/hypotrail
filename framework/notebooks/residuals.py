"""Teaching notebook: examine residual reports without hidden selection."""
import marimo
app = marimo.App(width='medium')

@app.cell
def _():
    import marimo as mo
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / 'reports').glob('residuals-*.json'))
    choices = {p.stem:p for p in files}
    mo.md('# Understand remaining errors\nResiduals suggest hypotheses. Inspecting them before revising a model uses validation information: record the next trial.')
    return mo, json, choices

@app.cell
def _(mo, choices):
    selected = mo.ui.dropdown(options=list(choices), value=next(iter(choices),None), label='Calculated report')
    selected if choices else mo.md('No residual report available. The pilot calculates it after an eligible run. This page invents no analysis.')
    return (selected,)

@app.cell
def _(mo, json, choices, selected):
    result = json.loads(choices[selected.value].read_text()) if selected.value in choices else {}
    mo.plain_text(json.dumps(result,ensure_ascii=False,indent=2)) if result else mo.md('Waiting for calculated evidence.')
    return

@app.cell
def _(mo):
    mo.md('## Before turning a residual into a feature\n\n1. Is the pattern stable across periods or driven by one month?\n2. Is the variable available at decision time? Plausibility does not establish availability.\n3. How many hypotheses have been examined? Extensive search creates optimism.\n4. Could noise, drift, or a preparation error also explain the finding?\n\n| Choice | When appropriate | What to record |\n|---|---|---|\n| Change nothing | Fragile signal or insufficient gain | Rationale, period, power limitation |\n| Test a transformation | Plausible available mechanism | Hypothesis before the run, budget, stopping criterion |\n| Revise data | Confirmed provenance error | Correction, manifest, invalidated analyses |\n\n**Decide in chat.** The notebook supports understanding and discussion without modifying models.')
    return

if __name__ == '__main__':
    app.run()
