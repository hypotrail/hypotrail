"""Interactive tour of training aggregates; no raw-data reads or training."""
import marimo

app = marimo.App(width='medium')


@app.cell
def _():
    import json
    import os
    from pathlib import Path
    import marimo as mo
    root = Path(os.environ.get('OSML_ROOT', Path.cwd()))
    path = root / 'reports/dataset-discovery.json'
    mo.stop(not path.exists(), mo.md('First run `python -m mlkit.discover` at the project root.'))
    data = json.loads(path.read_text())
    mo.md('# Discover the data\nA guided first look before modeling. These aggregates describe only the training partition of the contract at generation time. Regenerate the report after changes.')
    return data, mo


@app.cell
def _(data, mo):
    mo.vstack([mo.md('## 1 · A row, a population, a use'),
               mo.ui.table([{'development rows': data['rows'], 'described rows': data['train_rows'], 'model features': data['feature_count']}], selection=None),
               mo.md(data['unit_of_observation']), mo.md('Declared use: '+data['purpose']),
               mo.md('Declared target: '+str(data['target'])+' — construction and availability time still need confirmation.')])
    return


@app.cell
def _(data, mo):
    variable = mo.ui.dropdown(options=[c['name'] for c in data['columns']], value=data['columns'][0]['name'], label='Explore a column')
    mo.vstack([mo.md('## 2 · Understand the columns'), variable])
    return (variable,)


@app.cell
def _(data, mo, variable):
    column = next(c for c in data['columns'] if c['name'] == variable.value)
    distribution = column.get('stats', {}).get('histogram', column.get('stats', {}).get('categories', []))
    # mo.json renders content as data, without column-derived HTML.
    mo.vstack([mo.json(column), mo.ui.table(distribution, selection=None) if distribution else mo.md('No distribution exported for this column.'), mo.md('**Discuss:** what does this variable mean, in which unit, and when is it known? Its name alone is insufficient.')])
    return


@app.cell
def _(data, mo):
    mo.vstack([mo.md('## 3 · Choose the situation the test should represent'), mo.json(data['split']),
               mo.md('The split is provisional. Rows linked to the same customer or time may require another protocol.'),
               mo.md('## 4 · Return to the pilot\nExplain what a row represents in your own words. Then discuss feature availability and splitting. Decisions remain in chat and its persistent log.'),
               mo.ui.table([{'limite': x} for x in data['limits']], selection=None)])
    return


if __name__ == '__main__':
    app.run()
