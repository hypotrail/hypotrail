import json
from pathlib import Path
import pandas as pd
from playwright.sync_api import expect
from test_webview_ui import ui

ROOT=Path(__file__).resolve().parents[1]

def test_aggregates_use_training_rows_only():
    bank=pd.read_csv(ROOT/'data/bank.csv',sep=';')
    split=json.loads((ROOT/'data/split.json').read_text())
    eda=json.loads((ROOT/'projects/bank-marketing/results.json').read_text())['display']['eda']
    assert eda['row_indices']==split['train']
    assert not set(eda['row_indices']) & set(split['validation'])
    train=bank.iloc[split['train']]
    assert eda['charts'][0]['items'][1]['value']==int((train.y=='yes').sum())
    assert sum(i['n'] for i in eda['charts'][1]['items'])==len(train)
    mpg=json.loads((ROOT/'projects/auto-mpg/results.json').read_text())['display']['eda']
    assert mpg['rows']==280 and len(mpg['charts'][1]['points'])==280
    assert all(int(p['label'][-4:])<=1978 for p in mpg['charts'][1]['points'])
    assert sum(i['n'] for i in mpg['charts'][0]['items'])==280

def test_interactive_exploration_and_question_preserves_choices(ui):
    page,context,url,control=ui
    expect(page.locator('.explorer')).to_be_visible()
    before=page.evaluate('window.osml.state().answers')
    page.locator('[data-chart="2"]').click()
    page.locator('[data-mark="0"]').click()
    expect(page.locator('#eda-detail')).to_contain_text('effectif')
    page.locator('#eda-ask').click()
    expect(page.locator('#question')).to_have_value(__import__('re').compile('.*Calculated summary.*'))
    assert page.evaluate('window.osml.state().answers')==before
    page.locator('#project-switch select').select_option('uci-auto-mpg-v1')
    expect(page.locator('.explorer')).to_contain_text('280 observations')
    page.locator('[data-chart="1"]').click()
    expect(page.locator('.eda-scatter circle')).to_have_count(280)
    page.locator('.eda-scatter circle').first.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#eda-detail')).to_contain_text('Weight (lb)')
    page.evaluate('window.osml.render()')
    expect(page.locator('.eda-scatter circle')).to_have_count(280)
    expect(page.locator('#eda-detail')).to_contain_text('Weight (lb)')
    output=ROOT.parent/'artifacts/verification-discovery';output.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(output/'auto-mpg.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(output/'mobile.png'),full_page=True)
