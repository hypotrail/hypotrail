"""v0.3 WP-C: junior-ready payloads (remarks R15, R18, R19, R21, R30, R36, R37).

* ``next_action`` carries ``junior_digest`` (at most 200 words, in the study language),
  ``recommended`` (the engine's default with a one-line why) and ``question``;
* a French study emits no English junior text: step questions, ``junior_message``, limits,
  ``recap_junior``, the digest, the data card lines (identifiers, column names and the case's
  own statements are allowed);
* the glossary gives a canonical English term and its usual French term;
* the success criterion is a metric and a minimum, with its options, the reference value
  and a per-1,000 translation; a criterion recorded before v0.3 stays valid.

Temporary synthetic studies only (``flowkit``); scope S (the CLI code path in-process).
"""
from __future__ import annotations

import inspect
import json
import re

import pytest

from mlkit.study import audience, cmd_data, criterion, governance, junior, texts
from mlkit.study import state as st
from mlkit.study import view as view_mod

import flowkit as fk
from flowkit import Flow

OPEN_WORDS = 'Yes, I open the final test now, because the model and the rule are fixed'
# English function words: one of them in a junior text of a French study is English prose.
ENGLISH = re.compile(r"\b(the|and|of|is|are|your|you|with|to|rows|which|what|not|be|by|for|"
                     r"this|that|it|from|before|after|every|each|has|have|was|were|will|"
                     r"there|their|its|than|then|only|once|when|out)\b", re.I)


def _english(text: str, allowed: list[str]) -> list[str]:
    """The English words of ``text`` once quoted material (« ... », "...") and the allowed
    literals (case statements, column names, identifiers) are removed."""
    text = re.sub(r'«[^»]*»', ' ', str(text))
    text = re.sub(r'"[^"]*"', ' ', text)
    for a in sorted(allowed, key=len, reverse=True):
        if a:
            text = text.replace(a, ' ')
    return ENGLISH.findall(text)


class FrenchFlow(Flow):
    """A flow whose proposals carry a French restatement (the study language)."""

    def init(self):
        return self.call('init', '--case', self.case_dir, '--study', self.study, '--lang', 'fr')

    def propose(self, decision, value):
        return self.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                         '--restatement', f'You decide the {decision} as stated.',
                         '--restatement-fr', f'Tu décides {audience.decision_words(decision, "fr")} '
                                             'comme indiqué.',
                         '--rationale', 'It fits the scenario.', '--request-id', self.rid(),
                         '--expected-revision', self.rev(), '--study', self.study)

    def decide(self, decision, value, words=None):
        p = self.propose(decision, value)
        return self.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                         words or fk.default_words(decision), '--request-id', self.rid(),
                         '--expected-revision', self.rev(), '--study', self.study)


def _allowed(flow) -> list[str]:
    from mlkit.study import case as c
    case = c.load_case(flow.case_dir, verify_data=False)
    out = [v['name'] for v in case.document['variables']]
    out += [str(f.get('value')) for f in case.document.get('facts') or []]
    out += [str(case.positive_label), str(case.document['target'].get('negative_label')),
            str(case.target_unit or '')]
    return out


def _junior_texts(flow) -> list[tuple[str, str]]:
    """Every junior text of the study at its current point: the next action (message,
    digest, question, recommendation, criterion options), the limits, the summary's recap
    and limits, the deliverables, the plan's steps in French, and the data card lines."""
    v = flow.view()
    s = flow.call('status', '--summary', '--study', flow.study)
    nxt = v['next_action']
    out = [('junior_message', nxt['junior_message']), ('junior_digest', nxt['junior_digest'])]
    if nxt.get('question'):
        out.append(('question', nxt['question']))
    if nxt.get('recommended'):
        out.append(('recommended.why', nxt['recommended']['why']))
    opts = nxt.get('criterion_options')
    if opts:
        out += [('criterion.text', opts['text']), ('criterion.equivalence', opts['equivalence'] or '')]
        out += [('criterion.metric', m['explanation']) for m in opts['metrics']]
        out += [('criterion.not', m['why']) for m in opts['not_criteria']]
        out += [('criterion.candidate', c['text']) for c in opts['candidates']]
        if opts['reference']:
            out.append(('criterion.reference', opts['reference']['text']))
    out += [(f'limit:{x["id"]}', x['junior_text']) for x in v['not_yet_defensible']]
    out += [(f'summary.limit:{x["id"]}', x['junior_text']) for x in s['not_yet_defensible']['top']
            if x['junior_text']]
    out += [('recap_junior', line) for line in s['recap_junior']]
    out += [(f'artifact:{n}', i['junior_message']) for n, i in v['artifacts']['items'].items()]
    out += [(f'step:{x["id"]}', junior.step_text(x['question'], 'fr')) for x in v['plan']]
    out += [(f'step-title:{x["id"]}', junior.step_text(x['title'], 'fr')) for x in v['plan']]
    card = flow.call('data', '--study', flow.study)
    out += [('data.final_test', card['final_test']['junior_text']),
            ('data.duplicates', card['development']['duplicates']['junior_text']),
            ('data.note', card['note']['junior_text'])]
    return out


def _assert_french(flow, seen: dict) -> None:
    allowed = _allowed(flow)
    for where, text in _junior_texts(flow):
        found = _english(text, allowed)
        assert not found, (where, found, text)
        seen.setdefault(where.split(':')[0], 0)
        seen[where.split(':')[0]] += 1


@pytest.fixture(scope='module')
def french(tmp_path_factory):
    tmp = tmp_path_factory.mktemp('wpc_fr')
    case_dir = fk.make_case(tmp / 'case', n_rows=600)['case'].parent
    return FrenchFlow(tmp / 'study', case_dir, prefix='fr')


def test_a_french_study_emits_no_english_junior_text(french):
    flow = french
    seen: dict = {}
    flow.init()
    _assert_french(flow, seen)
    nxt = flow.view()['next_action']
    assert nxt['kind'] == 'show_data_card' and nxt['language'] == 'fr'
    flow.propose('prediction_time', 'quand la fiche est créée, avant le résultat')
    _assert_french(flow, seen)                      # await_user_words
    assert flow.view()['next_action']['question'] == 'Est-ce que tu adoptes cette décision ?'
    p = flow.view()['open_proposals'][0]
    flow.call('decide', 'confirm', p['proposal_id'], '--user-words',
              fk.default_words('prediction_time'), '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    nxt = flow.view()['next_action']
    assert nxt['decision'] == 'feature_availability' and nxt['default_value']
    _assert_french(flow, seen)
    flow.decide('feature_availability', nxt['default_value'])
    nxt = flow.view()['next_action']
    assert nxt['decision'] == 'split' and nxt['recommended']['value'] == nxt['default_value']
    _assert_french(flow, seen)
    flow.decide('split', nxt['default_value'])
    flow.run('split')
    nxt = flow.view()['next_action']
    assert nxt['decision'] == 'success_criterion' and nxt['criterion_options']
    _assert_french(flow, seen)
    flow.decide('success_criterion', {'metric': 'recall_gain', 'min_points': 5})
    flow.run('eda.target_rate')
    _assert_french(flow, seen)
    flow.run('eda.special_values')
    flow.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    _assert_french(flow, seen)
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    _assert_french(flow, seen)
    flow.decide('policy', 'capacity:40',
                words='Yes, I adopt that rule because the desk can make that many calls')
    value = st.b1_default_value(flow.state(), 'final_test')
    pid = flow.propose('final_test', value)['result']['proposal_id']
    flow.call('decide', 'confirm', pid, '--user-words', OPEN_WORDS, '--request-id', flow.rid(),
              '--expected-revision', flow.rev(), '--study', flow.study)
    _assert_french(flow, seen)
    flow.call('render', '--study', flow.study)
    _assert_french(flow, seen)
    # Every kind of junior text was checked at least once.
    for kind in ('junior_message', 'junior_digest', 'question', 'recommended.why', 'limit',
                 'summary.limit', 'recap_junior', 'artifact', 'step', 'step-title',
                 'criterion.reference', 'criterion.candidate', 'data.final_test', 'data.note'):
        assert seen.get(kind), kind


def test_every_step_text_and_limit_has_a_french_variant():
    for text in junior.all_step_texts():
        assert junior.step_text(text, 'fr') != text, text
        assert not _english(junior.step_text(text, 'fr'), []), text
    import test_contract_freeze as freeze
    emitted = set(freeze.NOT_YET_DEFENSIBLE_IDS)
    source = inspect.getsource(view_mod._case_uncertain_limit) + \
        inspect.getsource(view_mod._assumed_capacity)
    emitted |= set(re.findall(r"'id': '([a-z_]+)'", source))
    assert emitted <= set(junior.LIMIT_IDS_FR), sorted(emitted - set(junior.LIMIT_IDS_FR))
    for kind in junior.LIMIT_IDS_FR:
        text = junior.limit_fr({'id': kind, 'decisions': ['split'], 'rules': ['capacity:10'],
                                'features': ['age'], 'column': 'client', 'share': 0.1,
                                'changed': ['policy'], 'text': ''})
        assert text != junior.limit_fr({'id': 'unknown'}) and not _english(text, ['age']), kind


def test_the_digest_is_short_and_names_no_result_id(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=400)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir, prefix='dg')
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.run('split')
    view = flow.view()
    nxt = view['next_action']
    rids = [r['result_id'] for r in view['results'].values()]
    for key in junior.ENRICH_KEYS:
        assert key in nxt
    assert nxt['language'] == 'en' and nxt['question']
    assert len(nxt['junior_digest'].split()) <= junior.MAX_DIGEST_WORDS
    assert not any(rid[:8] in nxt['junior_digest'] for rid in rids)
    # The summary carries the same next action.
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['next_action']['junior_digest'] == nxt['junior_digest']


# --- the success criterion: metric + minimum (R18, R19) ---------------------------------------

def test_the_criterion_options_state_the_reference_and_translate_per_thousand(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=500)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir, prefix='cr')
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    # The criterion comes once the split is run, so its reference value is known.
    assert flow.view()['next_action']['kind'] == 'run'
    flow.run('split')
    opts = flow.view()['next_action']['criterion_options']
    assert tuple(opts) == criterion.OPTIONS_KEYS and opts['default_metric'] == 'precision_gain'
    ref = opts['reference']
    rate = flow.view()['results']['split']['values']['partitions']['train']['rate']
    assert ref['value'] == rate and ref['rows'] == 'development'
    assert [m['metric'] for m in opts['metrics']] == ['precision_gain', 'recall_gain']
    assert {m['metric'] for m in opts['not_criteria']} == {'expected_value', 'auc',
                                                          'average_precision'}
    assert 'rank configurations identically' in opts['equivalence']
    for cand in opts['candidates']:
        p = cand['value']['min_points']
        per = cand['per_1000']
        assert per['reference'] == round(1000 * rate) and per['extra'] == per['with_minimum'] \
            - per['reference'] and per['with_minimum'] == round(1000 * (rate + p / 100))
    assert opts['illustrative'].startswith('Illustrative, per 1,000 actions')
    digest = flow.view()['next_action']['junior_digest']
    assert f'{100 * rate:.1f}%' in digest and 'Success criterion' in digest.split(':')[0]


def test_a_recall_criterion_is_assessed_on_the_recall_gain(tmp_path):
    case_dir = fk.make_case(tmp_path / 'case', n_rows=600)['case'].parent
    flow = Flow(tmp_path / 'study', case_dir, prefix='rc')
    flow.init()
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    flow.decide('feature_availability', fk.availability(case_dir))
    flow.decide('split', flow.view()['next_action']['default_value'])
    flow.decide('success_criterion', {'metric': 'recall_gain', 'min_points': 1})
    flow.decide('preprocessing', dict(governance.DEFAULT_PREPROCESSING))
    flow.run('split')
    flow.run('fit.baseline')
    flow.run('fit.logistic')
    flow.variant()
    flow.run('policy.evaluate', '--rule', 'capacity:40')
    flow.decide('policy', 'capacity:40',
                words='Yes, I adopt that rule because the desk can make that many calls')
    view = flow.view()
    crit = view['criterion']
    rules = view['results']['policy.evaluation']['values']['rules']
    delta = rules['capacity:40']['deltas']['fit.logistic']['recall']
    assert crit['metric'] == 'recall_gain' and crit['gain'] == pytest.approx(100 * delta['point'])
    assert crit['status'] in ('met', 'uncertain', 'not_met')
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert 'recall gain over the baseline of at least 1 points' in summary['recap_junior'][1]
    # Other metrics stay refused.
    out = flow.call('decide', 'propose', 'success_criterion', '--value-json',
                    json.dumps({'metric': 'auc', 'min_points': 1}), '--restatement', 'AUC.',
                    '--rationale', 'r', '--request-id', flow.rid(), '--expected-revision',
                    flow.rev(), '--study', flow.study, expect=None)
    assert out['error']['code'] == 'invalid_value'
    assert out['error']['details']['metrics'] == ['precision_gain', 'recall_gain']


def test_a_criterion_recorded_before_v03_stays_valid_and_is_labelled():
    criterion.check({'metric': 'precision_gain', 'min_points': 5}, 'binary')
    criterion.check({'metric': 'mae_reduction', 'min_share': 0.1}, 'regression')
    assert criterion.value_words({'metric': 'precision_gain', 'min_points': 5}) == \
        'precision gain over the baseline of at least 5 points'
    assert criterion.value_words({'metric': 'precision_gain', 'min_points': 5}, 'fr') == \
        "gain de précision sur le modèle de référence d'au moins 5 points"
    with pytest.raises(governance.ValueProblem):
        criterion.check({'metric': 'recall_gain', 'min_points': 500}, 'binary')
    with pytest.raises(governance.ValueProblem):
        criterion.check({'metric': 'recall_gain', 'min_share': 0.1}, 'regression')


def test_the_threshold_action_lets_the_junior_weigh_precision_and_recall():
    view = {'task': 'binary', 'decisions': {'split': {'value': {'method': 'kfold_stratified'}},
                                            'policy': {'value': 'threshold:0.3'}},
            'results': {}, 'open_proposals': []}
    opts = criterion.options(view, 'en')
    assert opts['action'] == 'threshold' and 'choose precision' in opts['text']
    recall = next(m for m in opts['metrics'] if m['metric'] == 'recall_gain')
    assert 'differs from precision' in recall['explanation']
    view['decisions']['policy']['value'] = None
    view['scenario_defaults'] = {'capacity_share': {'value': 0.1}}
    assert criterion.options(view, 'en')['action'] == 'share'


def test_regression_options_speak_in_the_unit():
    view = {'task': 'regression', 'decisions': {'split': {'value': {'method': 'kfold_quantile'}}},
            'results': {}, 'open_proposals': []}
    opts = criterion.options(view, 'fr', unit='mpg')
    assert opts['default_metric'] == 'mae_reduction' and opts['reference'] is None
    assert all('mpg' in c['text'] for c in opts['candidates'])
    assert not _english(opts['text'], ['mpg'])


# --- the glossary (R15) ------------------------------------------------------------------------

CANONICAL = {'training_set': ('Training set', "jeu d'entraînement"),
             'validation_partition': ('Validation set', 'jeu de validation'),
             'fold': ('Fold', 'pli'),
             'cross_validation': ('k-fold cross-validation', 'validation croisée à k plis'),
             'out_of_fold': ('Out-of-fold predictions', 'prédictions hors pli'),
             'final_test': ('Holdout (final test)', 'échantillon de test final (holdout)'),
             'confidence_interval': ('Confidence interval', 'intervalle de confiance'),
             'average_precision': ('Average precision (AP)',
                                   'average precision (AP, aire sous la courbe précision-rappel)'),
             'sample': ('Sample', 'échantillon'),
             'development_rows': ('Development set (development rows)',
                                  'échantillon de développement')}


def test_the_glossary_gives_the_canonical_english_and_the_usual_french_term():
    terms = texts.load('glossary')['terms']
    for key, (en, fr) in CANONICAL.items():
        assert (terms[key]['term'], terms[key]['term_fr']) == (en, fr), key
    data = texts.load('glossary')
    for section in ('terms', 'regression_terms'):
        assert all(v.get('term_fr') for v in data[section].values()), section
    # Fold spread is not a confidence interval, and the definition says so.
    assert 'not a confidence interval' in terms['fold_spread']['definition']
    # No raw result id in an example the agent relays.
    assert '<result_id>' not in json.dumps(data)


def test_the_cross_validation_words_name_training_and_validation_folds():
    question = st.CV_STEP_TEXTS['split']['question']
    assert 'validation fold' in question and 'training folds' in question
    assert 'k-fold cross-validation' in question
    assert audience.CV_METHOD_WORDS['temporal_folds'] == 'folds in time order'


def test_the_data_card_lines_follow_the_study_language(french):
    card = french.call('data', '--study', french.study)
    assert card['note']['junior_text'] == junior.DATA_NOTE_FR
    assert card['note']['text'] == cmd_data.NOTE
