"""Teaching notebook: profile facts, hypotheses, and decisions; no new training."""
import marimo
app = marimo.App(width='medium')

@app.cell
def _():
    import marimo as mo
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    profile_path = root / 'reports/data_profile.json'
    profile = json.loads(profile_path.read_text()) if profile_path.exists() else {}
    mo.md('# Understand the data\nA profile describes what is present. It does not establish that information was available at decision time.')
    return mo, json, root, profile

@app.cell
def _(mo, profile):
    mo.md(f"**{profile.get('rows', 'Not calculated')} development rows** · Period: {profile.get('months', 'unavailable')}\n\nTarget relationships use the exploration period. Strong signal needs provenance explanation; weak signal does not rule out leakage.")
    return

@app.cell
def _(mo):
    missing_limit = mo.ui.slider(start=0, stop=100, step=5, value=20, label='Highlight columns above this missingness percentage (display only)')
    missing_limit
    return (missing_limit,)

@app.cell
def _(mo, profile, missing_limit):
    rows = [{'column':k, 'missing (%)':round(v.get('missing',0)*100,2), 'to examine': v.get('missing',0)*100>=missing_limit.value, 'meaning':v.get('type','?'), 'alerts':'; '.join(v.get('flags',[]))} for k,v in profile.get('columns',{}).items()]
    mo.ui.table(rows, selection=None) if rows else mo.md('No profile: the pilot must first run `mlkit.profile`. No fictional result is substituted.')
    return

@app.cell
def _(mo):
    mo.md('## Which decision follows?\n\n| Option | Benefit | Cost or risk | Required evidence |\n|---|---|---|---|\n| Keep with imputation | Preserve records | May hide a collection break | Fit imputation inside temporal validation |\n| Exclude feature | Reduce uncertain-source dependence | Potential signal loss | Availability rationale or preregistered trial |\n| Correct preparation | Address the cause | Recompute with a new manifest | Tracked script, source, and decision |\n\n**Recommendation:** understand missingness before choosing. Do not delete rows merely to improve a score.\n\n**Be able to explain:** what was known, when, by which system, and why the calculation respects it.')
    return

@app.cell
def _(mo, root, json):
    brief_path = root / 'reports/pilot-brief.json'
    brief = json.loads(brief_path.read_text()) if brief_path.exists() else {}
    answer_rows = [{'question':k,'status':v['status'],'choice':str(v['value']),'reason':v['rationale']} for k,v in brief.get('answers',{}).items()]
    mo.ui.table(answer_rows, selection=None) if answer_rows else mo.md('No decision recorded by the pilot.')
    return

if __name__ == '__main__':
    app.run()
