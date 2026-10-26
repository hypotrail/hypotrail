"""Owner session 2026-10-26, lot L5: recommendations that read the evidence (R5, R7, R12,
R13, R14, R15; owner decisions D5, D6, D8, D9, D10, D11).

* D5 (R5, R7): a study created by ``init`` checks the structure of its data (``eda.quality``,
  step ``structural_eda``, no target read) and decides the preparation before any look at the
  target; a study created before keeps its plan, its drafts and its next actions;
* D6 (R5): the preparation is drafted from the target-free results, rule by rule, with the
  reasons citing registered paths and the default kept as the comparison option;
* R7: the data-contingent stamp explained in the junior's words, the term first;
* D9 (R13): the EBM drafted beside the tuned penalty when the diagnostics flag a pattern and
  the budget allows;
* D10 (R14): boosting named as the family of XGBoost and LightGBM, and why no random forest;
* D11 (R15): a family outside the catalogue gets a refusal that teaches;
* D8 (R12): a declared calendar year kept under a temporal evaluation gets an advisory;
* the walkers of rounds 5 and 6 follow ``next_action`` on both generations.

Every study lives in ``tmp_path``. The data are synthetic, except the Hotel structural
steps (the committed case is only read; nothing is fitted).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

import flowkit as fk
from mlkit.study import (case as c, cite, drafts, governance, junior, read, state as st,
                         trials, view as view_mod)

sys.path.insert(0, str(Path(__file__).resolve().parent / 'libraries'))

ADOPT = 'Yes, I adopt this decision.'


# --- helpers --------------------------------------------------------------------------------

def _flow(base: Path, task='binary', language='en', n_rows=300, **case_kw) -> fk.Flow:
    case_dir = fk.make_case(base / f'case-{task}', n_rows=n_rows, task=task,
                            **case_kw)['case'].parent
    f = fk.Flow(base / f'study-{task}', case_dir, prefix=task[:3])
    f.call('init', '--case', case_dir, '--study', f.study, '--lang', language)
    return f


_strip_generation = fk.previous_generation


def _propose(f: fk.Flow, decision: str, value, expect=0):
    return f.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                  '--restatement', f'You decide the {decision} as stated.', '--rationale',
                  'It fits the scenario.', '--request-id', f.rid(), '--expected-revision',
                  f.rev(), '--study', f.study, expect=expect)


def _adopt(f: fk.Flow, decision: str, value):
    p = _propose(f, decision, value)
    f.call('decide', 'confirm', p['result']['proposal_id'], '--user-words', ADOPT,
           '--adoption-question', '--request-id', f.rid(), '--expected-revision', f.rev(),
           '--study', f.study)
    return p


def _until(f: fk.Flow, stop, limit=40) -> dict:
    """Follow ``next_action`` as given (defaults, recommended values, run options) until
    ``stop(next_action)``; return that action."""
    for _ in range(limit):
        nxt = f.view()['next_action']
        if stop(nxt):
            return nxt
        kind = nxt['kind']
        if kind == 'show_data_card':
            _adopt(f, 'prediction_time', 'when the record is created, before the outcome')
        elif kind == 'run':
            args = [nxt['activity']]
            for rule in nxt.get('rules') or []:
                args += ['--rule', rule]
            for option, value in (nxt.get('options') or {}).items():
                args += [f'--{option}', str(value)]
            out = f.run(*args, expect=None)
            assert out.get('ok'), (nxt, out)
        elif kind == 'await_user_words':
            f.call('decide', 'confirm', nxt['proposal_id'], '--user-words', ADOPT,
                   '--adoption-question', '--request-id', f.rid(), '--expected-revision',
                   f.rev(), '--study', f.study)
        else:
            assert kind == 'propose', nxt
            value = nxt.get('default_value')
            if value is None:
                value = (nxt.get('recommended') or {}).get('value')
            assert value is not None, nxt
            _adopt(f, nxt['decision'], value)
    raise AssertionError('next_action did not reach the stop')


def _at(decision):
    return lambda nxt: nxt['kind'] == 'propose' and nxt.get('decision') == decision


def _target_records(f: fk.Flow) -> list[dict]:
    target = c.load_case(f.case_dir).target_column
    return [r for r in read.open(f.study).exposure_records()
            if r.get('purpose') == 'train_eda' and target in (r.get('columns') or [])]


# --- D5: the structural-first plan ----------------------------------------------------------

def test_structural_first_plan_order(tmp_path):
    """A new study: the quality check, then the preparation (which requires it), then the
    target exploration; the preparation is proposed before any look at the target and,
    motivated by target-free results only, is not data-contingent."""
    f = _flow(tmp_path)
    state = f.state()
    assert state[st.EXPLORATION_ORDER_KEY] == st.STRUCTURAL_FIRST and st.structural_first(state)
    assert st.validate_state(state) == []
    plan = f.view()['plan']
    ids = [s['id'] for s in plan]
    assert ids == ['discover_data', 'prediction_time', 'feature_availability', 'split',
                   'success_criterion', 'structural_eda', 'preprocessing', 'train_eda',
                   'models', 'model_variant', 'model_choice', 'policy', 'final_test',
                   'conclusion']
    by_id = {s['id']: s for s in plan}
    assert by_id['structural_eda']['activities'] == ['eda.quality']
    assert 'structural_eda' in by_id['preprocessing']['requires']
    assert by_id['train_eda']['activities'] == ['eda.target_rate', 'eda.special_values']
    assert st.activity_slots(state).index('eda.quality') \
        < st.activity_slots(state).index('eda.target_rate')
    # After the success criterion the next action is the quality check.
    nxt = _until(f, lambda n: n['kind'] == 'run' and n['activity'] == 'eda.quality')
    assert nxt['step'] == 'structural_eda' and nxt['question'] is None
    nxt = _until(f, _at('preprocessing'))
    assert not _target_records(f)
    assert f.view()['eda_looks']['target_looks'] == 0
    value = nxt['default_value']
    quality = f.state()['current']['eda.quality']
    assert value['motivated_by'][0] == quality
    p = _propose(f, 'preprocessing', value)['result']
    assert p['data_contingent'] is False and p['data_contingent_reason'] is None
    recorded = f.state()['decisions']['preprocessing']['value']
    assert recorded['data_contingent'] is False and recorded['target_looks_before'] == 0
    # The target exploration follows the preparation.
    f.call('decide', 'confirm', p['proposal_id'], '--user-words', ADOPT, '--adoption-question',
           '--request-id', f.rid(), '--expected-revision', f.rev(), '--study', f.study)
    nxt = f.view()['next_action']
    assert (nxt['kind'], nxt['activity'], nxt['step']) == ('run', 'eda.target_rate', 'train_eda')


def test_the_structural_steps_are_in_french(tmp_path):
    f = _flow(tmp_path, language='fr')
    plan = {s['id']: s for s in f.view()['plan']}
    assert plan['structural_eda']['title'] == 'Vérifier la structure des données'
    assert 'sans la cible' in plan['structural_eda']['question']
    assert plan['train_eda']['title'] == "Explorer la cible sur l'échantillon de développement"
    assert 'regard sur la cible' in plan['train_eda']['question']
    assert 'contrôle de qualité' in plan['preprocessing']['question']
    for text in junior.all_step_texts():
        assert junior.step_text(text, 'fr') != text, text


def test_structural_eda_records_no_target_look(tmp_path):
    """NR-3: before the preparation is proposed, nothing read the target on the development
    rows: the quality check is a structural inspection without the target, each screened
    distribution a ``train_eda`` record of its one column."""
    f = _flow(tmp_path)
    _until(f, _at('preprocessing'))
    target = c.load_case(f.case_dir).target_column
    records = read.open(f.study).exposure_records()
    quality = [r for r in records if r.get('activity') == 'eda.quality']
    assert quality and all(r['purpose'] == 'structural_inspection'
                           and target not in r['columns'] for r in quality)
    eda = [r for r in records if r.get('purpose') == 'train_eda']
    assert all(target not in r['columns'] and len(r['columns']) == 1 for r in eda)
    assert {r['activity'] for r in eda} <= {'eda.distribution'}
    assert governance.ledger(records, target)['target_looks'] == 0


def test_an_existing_study_keeps_its_plan(tmp_path):
    """NR-18: a study created before L5 (no ``exploration_order``) keeps today's plan, the
    default preparation as its draft, the tuned penalty alone as its variant draft."""
    f = _flow(tmp_path)
    _strip_generation(f.study)
    state = f.state()
    assert st.EXPLORATION_ORDER_KEY not in state and not st.structural_first(state)
    assert st.validate_state(state) == []
    view = f.view()
    assert [s['id'] for s in view['plan']] == list(st.B2_BINARY_STEP_IDS)
    assert st.activity_slots(state) == tuple(a for s in st.B2_BINARY_STEPS
                                             for a in s['activities'])
    nxt = _until(f, lambda n: n['kind'] == 'run' and n['activity'].startswith('eda.'))
    assert nxt['activity'] == 'eda.target_rate'
    nxt = _until(f, _at('preprocessing'))
    assert nxt['default_value'] == governance.DEFAULT_PREPROCESSING
    assert 'alternatives' not in nxt
    assert nxt['recommended']['value'] == governance.DEFAULT_PREPROCESSING
    nxt = _until(f, _at('model_variant'))
    assert nxt['default_value'] == st.default_variant(f.state())
    assert len(nxt['default_value']['variants']) == 1


# --- D6: the drafted preparation ------------------------------------------------------------

class _Study:
    """A read-only study double: every listed result is current."""

    def __init__(self, values: dict):
        self.values = values

    def currency(self, rid):
        return {'current': rid in self.values, 'reason': None}

    def result(self, rid):
        return {'output': {'values': copy.deepcopy(self.values[rid])}}


def _state_for(case, availability: dict, current: dict) -> dict:
    state = st.initial_state(case)
    state[st.EXPLORATION_ORDER_KEY] = st.STRUCTURAL_FIRST
    state['decisions']['feature_availability'].update(status='confirmed', value=availability)
    state['current'] = dict(current)
    return state


def _quality(n=1000, cardinality=(), missing=(), ranges=()):
    return {'n_rows': n, 'cardinality': list(cardinality), 'missing': list(missing),
            'ranges': list(ranges), 'target_read': False}


def _rare(column, n_distinct, rare_rows):
    return {'column': column, 'type': 'category', 'n_distinct': n_distinct,
            'rare': [{'value': 'x', 'n_rows': rare_rows}] if rare_rows else [],
            'rare_rows': 30}


@pytest.fixture(scope='module')
def synthetic(tmp_path_factory):
    case_dir = fk.make_case(tmp_path_factory.mktemp('case'), n_rows=300)['case'].parent
    return c.load_case(case_dir)


def _draft(monkeypatch, case, quality, availability=None, distributions=None, lang='en'):
    availability = availability or {v['name']: 'available_at_prediction'
                                    for v in case.document['variables']
                                    if v['role'] == 'feature'}
    values = {'q': quality}
    current = {'eda.quality': 'q'}
    for column, dist in (distributions or {}).items():
        values[f'd-{column}'] = dist
        current[drafts.distribution_slot(column)] = f'd-{column}'
    monkeypatch.setattr(drafts, '_case', lambda state: case)
    study = _Study(values)
    state = _state_for(case, availability, current)
    return drafts.preprocessing_draft(study, state, lang), study, state


def _resolves(study, reason):
    values = study.result(reason['evidence']['result_id'])['output']['values']
    return cite.resolve(values, cite.parse_path(reason['evidence']['path']))


@pytest.mark.parametrize('n_distinct,rare_rows,fires', [
    (20, 10, True),        # at both thresholds: 20 distinct, rare rows 1 % of 1000
    (19, 10, False),       # one distinct value short
    (20, 9, False),        # rare rows below 1 %
])
def test_preprocessing_draft_rule_rare_categories(monkeypatch, synthetic, n_distinct,
                                                  rare_rows, fires):
    quality = _quality(cardinality=[_rare('home_branch', n_distinct, rare_rows)])
    draft, study, _ = _draft(monkeypatch, synthetic, quality)
    assert draft['drafted'] is fires
    assert draft['value']['rare_category_min_rows'] == (30 if fires else 0)
    if fires:
        (reason,) = draft['reasons']
        assert (reason['parameter'], reason['column'], reason['rule']) == (
            'rare_category_min_rows', 'home_branch', 'rare_categories')
        assert _resolves(study, reason) == quality['cardinality'][0]['rare']
        assert 'every categorical column' in reason['text']


@pytest.mark.parametrize('n_missing,fires', [(50, True), (49, False)])
def test_preprocessing_draft_rule_missing_indicator(monkeypatch, synthetic, n_missing, fires):
    quality = _quality(missing=[{'column': 'member_age', 'n_missing': n_missing,
                                 'share': n_missing / 1000}])
    draft, study, _ = _draft(monkeypatch, synthetic, quality)
    assert draft['value']['missing'] == ({'member_age': 'indicator'} if fires else 'none')
    if fires:
        assert _resolves(study, draft['reasons'][0]) == n_missing
        assert '50 of the 1000 rows' in draft['reasons'][0]['text']


@pytest.mark.parametrize('above,below,fires', [(1, 0, True), (0, 2, True), (0, 0, False),
                                               (None, None, False)])
def test_preprocessing_draft_rule_caps_only_against_a_declared_range(monkeypatch, synthetic,
                                                                     above, below, fires):
    quality = _quality(ranges=[{'column': 'membership_days', 'min': 0, 'max': 900,
                                'n_above': above, 'n_below': below,
                                'declared': None if above is None else {'min': 0, 'max': 800}}])
    draft, study, _ = _draft(monkeypatch, synthetic, quality)
    assert draft['value']['caps'] == ({'membership_days': [0.005, 0.995]} if fires else {})
    if fires:
        assert _resolves(study, draft['reasons'][0]) in (above, below)


@pytest.mark.parametrize('skewed', [True, False])
def test_preprocessing_draft_rule_signed_log(monkeypatch, synthetic, skewed):
    dist = {'column': 'membership_days', 'kind': 'numeric', 'numeric': {'skewed': skewed}}
    draft, study, _ = _draft(monkeypatch, synthetic, _quality(),
                             distributions={'membership_days': dist})
    assert draft['value']['log_transform'] == (['membership_days'] if skewed else [])
    assert draft['value']['motivated_by'] == ['q', 'd-membership_days']
    if skewed:
        assert _resolves(study, draft['reasons'][0]) is True


def test_a_rule_reads_candidates_only(monkeypatch, synthetic):
    """A column the availability excludes never enters the draft."""
    availability = {v['name']: 'available_at_prediction'
                    for v in synthetic.document['variables'] if v['role'] == 'feature'}
    availability['member_age'] = 'not_available'
    quality = _quality(missing=[{'column': 'member_age', 'n_missing': 900, 'share': 0.9}])
    draft, _, _ = _draft(monkeypatch, synthetic, quality, availability=availability)
    assert draft['drafted'] is False and draft['value']['missing'] == 'none'


def test_every_rule_together_is_accepted_and_explained(monkeypatch, synthetic):
    quality = _quality(cardinality=[_rare('home_branch', 40, 200)],
                       missing=[{'column': 'member_age', 'n_missing': 300, 'share': 0.3}],
                       ranges=[{'column': 'membership_days', 'min': 0, 'max': 9000,
                                'n_above': 3, 'n_below': 0, 'declared': {'min': 0, 'max': 5000}}])
    dist = {'numeric': {'skewed': True}}
    draft, study, state = _draft(monkeypatch, synthetic, quality, lang='fr',
                                 distributions={'days_since_last_lapse': dist})
    value = draft['value']
    governance.check_preprocessing(value, synthetic)     # the engine accepts it
    assert {r['rule'] for r in draft['reasons']} == set(drafts.RULES)
    assert all(set(r) == set(drafts.REASON_KEYS) for r in draft['reasons'])
    for reason in draft['reasons']:
        _resolves(study, reason)
    rec = drafts.preprocessing_recommended(draft, 'fr')
    assert rec['why'].startswith("Établie d'après le contrôle de qualité des données")
    (alt,) = drafts.preprocessing_alternatives(draft, 'fr')
    assert tuple(alt) == drafts.ALTERNATIVE_KEYS and alt['label'] == 'Sans transformation'
    assert governance.is_default(alt['value'])
    assert alt['value']['motivated_by'] == value['motivated_by']


def test_the_screened_distributions(synthetic):
    keep = [v['name'] for v in synthetic.document['variables'] if v['role'] == 'feature']
    quality = _quality(ranges=[
        {'column': 'member_age', 'min': 18, 'max': 90},             # below one order: no
        {'column': 'membership_days', 'min': 0, 'max': 3000},       # 3001
        {'column': 'fines_outstanding', 'min': 0, 'max': 9},        # exactly ten: yes
        {'column': 'days_since_last_lapse', 'min': -1, 'max': 99999},   # negative: no
        {'column': 'reminders_sent', 'min': 0, 'max': 40}])         # 41
    assert drafts.screened_columns(quality, keep, synthetic) == [
        'membership_days', 'reminders_sent', 'fines_outstanding']
    assert drafts.screened_columns(quality, ['member_age'], synthetic) == []


def test_the_preparation_digest_explains_the_pipeline_and_the_stamp(tmp_path):
    """R5, R7: the digest says what the fixed pipeline already does, and why the preparation
    is (not) data-contingent, the term first; the stamp's ``junior_text`` explains it."""
    f = _flow(tmp_path, language='fr')
    nxt = _until(f, _at('preprocessing'))
    digest = nxt['junior_digest']
    assert drafts.PIPELINE_SENTENCE['fr'] in digest
    assert "Regard sur la cible : une analyse qui lit la variable à prédire. Aucun n'a précédé" \
        in digest
    # A junior who looks at the target first still gets the stamp, now explained.
    f.run('eda.target_rate')
    nxt = f.view()['next_action']
    assert nxt['decision'] == 'preprocessing'
    assert 'après 1 regard(s) sur la cible' in nxt['junior_digest']
    p = _propose(f, 'preprocessing', nxt['default_value'])['result']
    assert p['data_contingent'] is True
    text = p['data_contingent_reason']['junior_text']
    assert text.startswith('Cette préparation est proposée après 1 regard(s) sur la cible')
    assert "Ce n'est pas une erreur" in text and 'un peu optimistes' in text


# --- D9: the drafted variants ---------------------------------------------------------------

def _diag(flags):
    return {'linear_checks': {'flags': flags, 'nonlinearity': [], 'interaction': [],
                              'calibration_slope': {}, 'alpha': 0.01}}


NONLINEAR = [{'check': 'nonlinearity', 'feature': 'membership_days', 'p_value': 0.0001},
             {'check': 'interaction', 'feature': 'home_branch', 'p_value': 0.001}]


def _variant_state(case, profile=None, used=()):
    state = st.initial_state(case, reliability_profile=profile)
    state[st.EXPLORATION_ORDER_KEY] = st.STRUCTURAL_FIRST
    state['current'] = {st.DIAG_SLOT[st.task_of(state)]: 'diag'}
    for i, spec in enumerate(used, start=1):
        state['proposals'][f'p_{i}'] = {
            'proposal_id': f'p_{i}', 'decision_id': 'model_variant', 'status': 'confirmed',
            'revision': i, 'value': {'variants': [dict(spec, question='q?')]}}
    return state


def _variant_draft(monkeypatch, case, flags, document=None, **kw):
    monkeypatch.setattr(drafts, '_case', lambda state: case if document is None else
                        type('C', (), {'document': document})())
    return drafts.variant_draft(_Study({'diag': _diag(flags)}), _variant_state(case, **kw), 'en')


def test_draft_variant_adds_the_ebm_when_flagged(monkeypatch, synthetic):
    draft = _variant_draft(monkeypatch, synthetic, NONLINEAR)
    tuned, ebm = draft['value']['variants']
    assert tuned['kind'] == 'tuned'
    assert (ebm['kind'], ebm['family']) == ('family', 'ebm')
    assert 'membership_days' in ebm['question'] and 'home_branch' in ebm['question']
    assert trials.check_value(draft['value'], {}, 'binary') is None
    rec = drafts.variant_recommended(draft, 'en')
    assert 'one trial of the budget of three' in rec['why'] and 'optimism' in rec['why']
    # No flag: the state's draft stays (the tuned penalty alone).
    assert _variant_draft(monkeypatch, synthetic, []) is None


def test_draft_variant_needs_two_trials_left(monkeypatch, synthetic):
    used = ({'kind': 'regularisation', 'strength': 'weak'},
            {'kind': 'regularisation', 'strength': 'strong'})
    assert _variant_draft(monkeypatch, synthetic, NONLINEAR, used=used) is None
    assert _variant_draft(monkeypatch, synthetic, NONLINEAR, used=used[:1]) is not None


def test_draft_variant_keeps_the_ebm_when_interpretability_is_required(monkeypatch,
                                                                         synthetic):
    document = copy.deepcopy(synthetic.document)
    document['constraints'] = {'interpretability': {'value': 'required', 'status':
                                                    'scenario_assumption', 'source': 'test'}}
    draft = _variant_draft(monkeypatch, synthetic, NONLINEAR, document=document)
    assert [v.get('family') for v in draft['value']['variants']] == [None, 'ebm']


def test_draft_variant_under_review_v1_cites_the_diagnostic(monkeypatch, synthetic):
    draft = _variant_draft(monkeypatch, synthetic, NONLINEAR, profile='review-v1')
    tuned, ebm = draft['value']['variants']
    assert (tuned['origin'], tuned['diagnostic_result_id']) == ('planned', None)
    assert (ebm['origin'], ebm['diagnostic_result_id']) == ('diagnostic_informed', 'diag')


def test_the_drafted_variants_are_proposed_as_given(tmp_path):
    """End to end on the synthetic case (its diagnostics flag a pattern): ``next_action``
    proposes the tuned penalty and the EBM, the engine accepts both, the EBM is stamped
    data-contingent with a junior text."""
    f = _flow(tmp_path)
    nxt = _until(f, _at('model_variant'))
    families = f.view()['model_families']
    assert families['recommendation'] == 'compare_nonlinear'
    kinds = [v['kind'] for v in nxt['default_value']['variants']]
    assert kinds == ['tuned', 'family'] and nxt['recommended']['value'] == nxt['default_value']
    p = _propose(f, 'model_variant', nxt['default_value'])['result']
    assert p['data_contingent'] is True
    assert p['data_contingent_reason']['junior_text'].startswith('An Explainable Boosting')


# --- D10: names the junior knows ------------------------------------------------------------

@pytest.mark.parametrize('language,boosting,forest', [
    ('en', 'tree boosting (the same family as XGBoost and LightGBM)', 'a random forest'),
    ('fr', "boosting d'arbres (même famille que XGBoost et LightGBM)", 'une forêt aléatoire')])
def test_model_families_junior_words(language, boosting, forest):
    families = drafts.with_junior_words(trials.shortlist(None, None, 'binary', language),
                                        language)
    words = {f['family']: f['junior_words'] for f in families['families']}
    assert words['hgb'] == boosting
    assert 'EBM' in words['ebm']
    (item,) = families['not_offered']
    assert tuple(item) == drafts.NOT_OFFERED_KEYS
    assert item['name'] == 'random forest' and item['words'] == forest
    assert ('tuned boosting' if language == 'en' else 'boosting réglé') in item['why']
    sentence = drafts.families_sentence(language)
    assert 'XGBoost' in sentence and forest.split()[-1] in sentence


def test_the_view_names_the_families_as_the_junior_knows_them(tmp_path):
    f = _flow(tmp_path, language='fr')
    families = f.view()['model_families']
    assert {x['family']: x['junior_words'] for x in families['families']}['hgb'] \
        .startswith("boosting d'arbres")
    assert families['not_offered'][0]['words'] == 'une forêt aléatoire'


# --- D11: a family outside the catalogue ----------------------------------------------------

@pytest.mark.parametrize('asked,closest', [('svm', 'ebm'), ('random_forest', 'hgb'),
                                           ('XGBoost', 'hgb'), ('knn', 'ebm'),
                                           ('neural network', 'ebm'), ('catboost', 'hgb')])
@pytest.mark.parametrize('language', ['en', 'fr'])
def test_family_refusal_teaches(tmp_path, asked, closest, language):
    f = _flow(tmp_path, language=language)
    before = f.state()
    budget = trials.budget(before)
    value = {'variants': [{'kind': 'family', 'family': asked, 'question': 'Does it rank better?'}]}
    out = _propose(f, 'model_variant', value, expect=2)
    error = out['error']
    assert error['code'] == 'invalid_value'
    details = error['details']
    assert details['reason'] == 'family_not_in_catalogue' and details['asked'] == asked
    assert details['closest_family'] == closest
    assert details['workbench'] == 'notebooks/workbench.py'
    assert details['families'] == ['ebm', 'hgb']          # the existing details are kept
    message = details['junior_message']
    assert 'notebooks/workbench.py' in message and 'XGBoost' in message
    if language == 'fr':
        assert 'catalogue' in message and "Rien n'a été enregistré" in message
        assert ('EBM' if closest == 'ebm' else "boosting d'arbres") in message
    else:
        assert 'closed on purpose' in message and 'not study evidence' in message
    after = f.state()
    assert after['revision'] == before['revision'] and after['proposals'] == {}
    assert trials.budget(after) == budget


def test_a_model_name_given_as_a_kind_is_taught_too(tmp_path):
    f = _flow(tmp_path)
    out = _propose(f, 'model_variant', {'variants': [{'kind': 'svm', 'question': 'x?'}]},
                   expect=2)
    assert out['error']['details']['closest_family'] == 'ebm'
    # A typo in a known kind is not a model: the refusal stays the plain one.
    out = _propose(f, 'model_variant', {'variants': [{'kind': 'regularization',
                                                      'strength': 'weak', 'question': 'x?'}]},
                   expect=2)
    assert 'reason' not in out['error']['details']


# --- D8: a calendar year under a temporal evaluation -----------------------------------------

def _declare(case_dir: Path, column: str, value: str) -> Path:
    import yaml
    path = case_dir / 'case.yaml'
    doc = yaml.safe_load(path.read_text())
    for v in doc['variables']:
        if v['name'] == column:
            v['calendar'] = value
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return case_dir


def _calendar_case(base: Path, column='member_age', value='year') -> Path:
    case_dir = fk.make_case(base / 'case', n_rows=300)['case'].parent
    return _declare(case_dir, column, value)


AUTO = fk.REPO / 'use-cases' / 'auto-mpg'


@pytest.mark.parametrize('temporal', [True, False])
def test_a_calendar_year_under_a_temporal_evaluation_is_questioned(tmp_path, temporal):
    """D8 (a): a feature the case declares ``calendar: year``, kept while the evaluation
    follows time (Auto MPG's folds follow ``model_year``; the declaration is a test's), is
    questioned in the availability's ``recommended.why``; under random folds it is not."""
    import shutil
    if temporal:
        case_dir = _declare(Path(shutil.copytree(AUTO, tmp_path / 'auto')), 'cylinders', 'year')
        column = 'cylinders'
    else:
        case_dir, column = _calendar_case(tmp_path), 'member_age'
    f = fk.Flow(tmp_path / 'study', case_dir, prefix='cal')
    f.call('init', '--case', case_dir, '--study', f.study)
    nxt = _until(f, _at('feature_availability'))
    why = nxt['recommended']['why']
    assert (f'{column} holds a calendar year' in why) is temporal
    if temporal:
        assert 'Keep the month and the week; question the year.' in why


def test_the_calendar_declaration_is_checked(tmp_path):
    for column, value, problem in (('member_age', 'month', 'must be one of year'),
                                   ('home_branch', 'year', 'numeric or integer feature')):
        case_dir = _calendar_case(tmp_path / f'{column}-{value}', column, value)
        with pytest.raises(c.CaseError) as err:
            c.load_case(case_dir)
        assert problem in json.dumps(err.value.problems)


def test_the_calendar_advisory_reads_the_kept_columns(synthetic):
    doc = copy.deepcopy(synthetic.document)
    for v in doc['variables']:
        if v['name'] == 'member_age':
            v['calendar'] = 'year'
    case = type('C', (), {'document': doc})()
    state = {'decisions': {'split': {'value': {'method': 'temporal_folds', 'folds': 5,
                                                'gap': 0}}}, 'proposals': {}}
    assert drafts.calendar_advisory(case, state, {'member_age': 'available_at_prediction'},
                                    'fr').startswith('member_age contient une année civile')
    assert drafts.calendar_advisory(case, state, {'member_age': 'uncertain_excluded'},
                                    'en') is None
    state['decisions']['split']['value']['method'] = 'kfold_stratified'
    assert drafts.calendar_advisory(case, state, {'member_age': 'available_at_prediction'},
                                    'en') is None


# --- the walkers on both generations --------------------------------------------------------

@pytest.mark.parametrize('task,language', [('binary', 'en'), ('regression', 'fr')])
def test_a_study_of_the_previous_generation_runs_as_given_to_done(tmp_path, task, language):
    """NR-6, NR-18: a study created before L5 loads, shows its status, and follows
    ``next_action`` as given from ``init`` to ``done`` (round 5's walker), never in the
    structural-first order."""
    from test_review_round5_engine import _follow
    f = _flow(tmp_path, task=task, language=language)
    _strip_generation(f.study)
    assert f.call('status', '--summary', '--study', f.study)['ok']
    log, last = _follow(f, task, False)
    assert last['kind'] == 'done', log[-5:]
    assert ('run', 'eda.quality') not in log
    target = ('run', 'eda.target_rate' if task == 'binary' else 'eda.target_summary')
    assert log.index(target) < log.index(('propose', 'preprocessing'))
    assert not st.structural_first(f.state())


@pytest.mark.parametrize('task,language', [('binary', 'fr'), ('regression', 'en')])
def test_a_structural_first_study_runs_as_given_to_done(tmp_path, task, language):
    """NR-6 on the new generation: round 5's walker takes the drafted preparation and the
    drafted variants as given; the quality check comes before the preparation, the target
    exploration after it."""
    from test_review_round5_engine import _follow
    f = _flow(tmp_path, task=task, language=language)
    log, last = _follow(f, task, False)
    assert last['kind'] == 'done', log[-5:]
    target = ('run', 'eda.target_rate' if task == 'binary' else 'eda.target_summary')
    assert log.index(('run', 'eda.quality')) < log.index(('propose', 'preprocessing')) \
        < log.index(target)
    assert f.state()['decisions']['preprocessing']['value']['data_contingent'] is False


# --- J-REC: the Hotel structural steps --------------------------------------------------------

HOTEL = fk.REPO / 'use-cases' / 'hotel-booking'


@pytest.mark.skipif(not (HOTEL / 'data').is_dir(), reason='Hotel data not present')
def test_hotel_quality_before_any_target_look_and_a_drafted_preparation(tmp_path):
    """J-REC (automated part): in a new Hotel study the quality check runs before any look at
    the target, the preparation is drafted from it with its reasons (the rare codes of
    ``agent`` and ``company``), and, motivated only by target-free results, is not
    data-contingent. Nothing is fitted."""
    f = fk.Flow(tmp_path / 'study', HOTEL, prefix='h')
    f.call('init', '--case', HOTEL, '--study', f.study, '--lang', 'fr')
    seen = []

    def stop(nxt):
        seen.append((nxt['kind'], nxt.get('activity') or nxt.get('decision')))
        return _at('preprocessing')(nxt)
    nxt = _until(f, stop)
    runs = [a for k, a in seen if k == 'run']
    assert runs[:2] == ['split', 'eda.quality']
    assert set(runs[2:]) <= {'eda.distribution'}
    assert not _target_records(f) and f.view()['eda_looks']['target_looks'] == 0
    value = nxt['default_value']
    assert value['rare_category_min_rows'] == 30
    reasons = nxt['recommended']['reasons']
    assert {'agent', 'company'} <= {r['column'] for r in reasons
                                    if r['rule'] == 'rare_categories'}
    assert nxt['alternatives'][0]['label'] == 'Sans transformation'
    # Wave W2 key order (CLI-CONTRACT §3.1): ``alternatives`` before the junior-ready keys.
    keys = list(nxt)
    assert (keys.index('junior_message') < keys.index('alternatives')
            < keys.index('language') < keys.index('recommended')
            < keys.index('question') < keys.index('junior_digest'))
    assert nxt['recommended']['why'].startswith("Établie d'après le contrôle de qualité")
    assert drafts.PIPELINE_SENTENCE['fr'] in nxt['junior_digest']
    study = read.open(f.study)
    for reason in reasons:
        values = study.result(reason['evidence']['result_id'])['output']['values']
        cite.resolve(values, cite.parse_path(reason['evidence']['path']))
    p = _propose(f, 'preprocessing', value)['result']
    assert p['data_contingent'] is False
    view = f.view()
    assert view_mod.SCHEMA and view['decisions']['preprocessing']['value'] \
        ['target_looks_before'] == 0
