"""WP-E2: ``hypotrail explain`` (CLI-CONTRACT-COMPANION §6, C6) and its content files.

The glossary's ``cited_example`` (decision CA.2), the step texts, and the "predict before
you look" questions of ``learn.yaml``: shown only from current, verified results, every
number a cited segment, ``check --text`` clean on the joined texts, and a regression study
without the binary-only terms or the vocabulary of a decision rule.
"""
from __future__ import annotations

import json
import re
from importlib import resources

import pytest
import yaml

import flowkit as fk
from mlkit.study import cite, cli, read, state as st, texts

AUTO = fk.REPO / 'use-cases' / 'auto-mpg'
RULE_VOCABULARY = re.compile(r'\b(threshold|capacity|precision|recall|positive class|policy|'
                             r'calling rule|selected)\b', re.IGNORECASE)
# A digit outside a {{...}} template (format names such as pct1 and f2 aside).
DIGIT = re.compile(r'(?<![\w.])\d')


def explain(study, *args):
    outcome = cli.run(['explain', *map(str, args), '--study', str(study)])
    assert outcome.exit_code == 0, outcome.payload
    return outcome.payload


def segments_of(payload):
    """Every ``{segments}`` text of an explain payload, with where it came from."""
    out = []
    for t in payload['terms']:
        if t['example']:
            out.append((f'term:{t["id"]}', t['example']['segments']))
    for step, item in payload['steps'].items():
        for key, text in item.items():
            if isinstance(text, dict):
                out.append((f'step:{step}.{key}', text['segments']))
    for q in payload['predictions']:
        if q['reveal']:
            out.append((f'prediction:{q["id"]}', q['reveal']['segments']))
    return out


def joined(payload) -> str:
    lines = [''.join(s['text'] for s in segs) for _, segs in segments_of(payload)]
    lines += [q['question'] for q in payload['predictions']]
    return '\n'.join(lines) + '\n'


@pytest.fixture(scope='module')
def binary(tmp_path_factory, synthetic_case_dir):
    flow = fk.Flow(tmp_path_factory.mktemp('ex-bin') / 'study', synthetic_case_dir, prefix='x')
    flow.init()
    flow.pauses()
    flow.run('split')
    before = explain(flow.study)
    for activity in ('eda.target_rate', 'eda.special_values', 'fit.baseline', 'fit.logistic'):
        flow.run(activity)
    flow.run('policy.evaluate', '--rule', 'capacity:20')
    return flow, before, explain(flow.study)


@pytest.fixture(scope='module')
def regression(tmp_path_factory):
    flow = fk.Flow(tmp_path_factory.mktemp('ex-auto') / 'study', AUTO, prefix='xa')
    flow.init()
    flow.decide('prediction_time', 'when the technical characteristics of a new model are fixed')
    flow.decide('feature_availability', fk.availability(AUTO))
    flow.decide('split', {'method': 'ordinal_cutoff', 'column': 'model_year', 'cutoff': 79})
    for activity in ('split', 'eda.target_summary', 'eda.special_values', 'fit.baseline',
                     'fit.linear', 'evaluate.regression'):
        flow.run(activity)
    return flow, explain(flow.study)


def _terms(payload):
    return {t['id']: t for t in payload['terms']}


def test_base_rate_needs_results_before_the_target_rate_then_cites_it(binary):
    flow, before, after = binary
    assert _terms(before)['base_rate']['example_status'] == 'needs_results'
    assert _terms(before)['base_rate']['example'] is None
    assert before['steps']['train_eda']['text_status'] == 'needs_results'
    assert before['steps']['train_eda']['interpretation'] is None
    assert before['steps']['split']['text_status'] == 'shown'
    base = _terms(after)['base_rate']
    assert base['example_status'] == 'shown' and base['steps'] == ['train_eda']
    rid = read.open(flow.study).state['current']['eda.target_rate']
    cited = [s for s in base['example']['segments'] if 'result_id' in s]
    assert [(s['result_id'], s['path'], s['format']) for s in cited] == [(rid, 'rate', 'pct1')]
    assert _terms(after)['leakage']['example_status'] == 'none'


def test_predictions_reveal_only_from_current_results(binary):
    _, before, after = binary
    for payload in (before, after):
        for q in payload['predictions']:
            assert q['available'] is (q['reveal'] is not None)
            assert [c['id'] for c in q['choices']][-1] == 'not_sure'
            assert not DIGIT.search(q['question'])
    assert [q['available'] for q in before['predictions']] == [False, False]
    rare, beats = after['predictions']
    assert (rare['step'], beats['step']) == ('train_eda', 'policy')
    assert rare['available'] and beats['available']
    paths = [s['path'] for s in beats['reveal']['segments'] if 'path' in s]
    assert 'rules.[capacity:20].deltas.[fit.logistic].precision.point' in paths


def test_every_number_of_every_segment_is_cited(binary, regression):
    for payload in (binary[2], regression[1]):
        facts = {str(f['value']) for f in read.open(payload['study']).state['facts'].values()}
        for where, segs in segments_of(payload):
            for s in segs:
                if 'result_id' in s:
                    assert s['text'] == cite.fmt_number(s['value'], s['format']), where
                    continue
                text = re.sub(r'\b(?:threshold|capacity):\d+(?:\.\d+)?', '', s['text'])
                for fact in facts:          # a case statement is quoted as recorded
                    text = text.replace(str(fact), '')
                assert not DIGIT.search(text), (where, s['text'])


def test_check_text_is_clean_on_the_joined_texts(binary, regression, tmp_path):
    for name, (study, payload) in {'binary': (binary[0].study, binary[2]),
                                   'regression': (regression[0].study, regression[1])}.items():
        note = tmp_path / f'{name}.md'
        note.write_text(joined(payload), encoding='utf-8')
        result = cli.run(['check', '--text', str(note), '--study', str(study)]).payload
        errors = [f for f in result['findings'] if f['severity'] == 'error']
        assert result['clean'] and errors == [], errors


def test_regression_terms_and_texts_hold_no_rule_vocabulary(regression):
    flow, payload = regression
    hidden = set(texts.load('glossary')['binary_only'])
    ids = {t['id'] for t in payload['terms']}
    assert payload['task'] == 'regression' and not ids & hidden
    assert {'mae', 'bias', 'target_distribution'} <= ids
    found = sorted({m.group(0).lower() for m in RULE_VOCABULARY.finditer(json.dumps(payload))})
    assert found == [], found
    terms = _terms(payload)
    assert terms['mae']['example_status'] == 'shown'
    assert list(payload['steps']) == [s['id'] for s in st.steps(read.open(flow.study).state)]
    bias, choice = payload['predictions']
    assert bias['available'] and 'too low' in ''.join(s['text'] for s in bias['reveal']['segments'])
    assert choice['step'] == 'model_choice' and choice['available']


def test_term_filter_and_its_refusal(binary):
    study = binary[0].study
    one = explain(study, '--term', 'precision')
    assert [t['id'] for t in one['terms']] == ['precision']
    assert one['steps'] == binary[2]['steps']
    refused = cli.run(['explain', '--term', 'mae', '--study', str(study)])
    assert refused.exit_code == 2
    error = refused.payload['error']
    assert error['code'] == 'invalid_arguments' and 'precision' in error['details']['terms']


def test_explain_is_deterministic_and_writes_nothing(binary):
    study = binary[0].study
    before = fk.tree_digest(study)
    assert explain(study) == explain(study) == binary[2]
    assert fk.tree_digest(study) == before


def test_learn_and_glossary_content_hold_no_digit_outside_templates():
    for name in ('learn', 'glossary', 'evidence'):
        raw = (resources.files('mlkit.study') / 'content' / f'{name}.yaml').read_text()
        data = yaml.safe_load(raw)
        for line in raw.splitlines():
            if line.lstrip().startswith('#') or 'schema:' in line:
                continue
            stripped = re.sub(r'\{\{[^}]*\}\}', '', line)
            assert not DIGIT.search(stripped), (name, line)
        assert data
    for q in texts.load('learn')['predictions']:
        assert q['task'] in ('binary', 'regression') and 2 <= len(q['choices']) <= 4
        assert 'not_sure' in [c['id'] for c in q['choices']]
    for task in ('binary', 'regression'):
        for term_id, entry in texts.glossary_terms(task).items():
            example = entry.get('cited_example')
            if example:
                assert cite.TEMPLATE.search(example), term_id
                if task == 'regression':
                    assert not RULE_VOCABULARY.search(example), term_id
