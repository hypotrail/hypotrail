"""L3, one language per study (owner session 2026-10-26, remark R4; plan §3 L3, §5.3 J-LANG).

What a French study shows the junior is French, and an English study English, wherever the
text comes from:

* the engine's step titles and questions, now in ``init`` and ``plan`` too (T2);
* the EDA questions, notes and warnings, stored in English, given a French form at read
  time (``l10n.eda_text``; ``eda.py`` is fingerprinted and not edited, plan §2.3) (T7);
* the case's statements (facts, special values' meanings, group names, availability sources)
  through the case's translation sidecar ``case.l10n.yaml`` (decision D4 A), recorded with its
  sha256 at ``init``, verified, optional, and never a source of ``sources_changed`` (T4-T6);
* both languages for the study panel (decision D4b): ``status --summary --digest`` ``texts``,
  ``evidence`` ``texts`` and ``question_junior``, the data card's ``texts``;
* the report, the notebook headings and the "Learn" tab (``explain``) in the study language;
  the glossary's examples of another case (bank clients in a Hotel study) are not shown.

J-LANG (automated part): a scripted walkthrough of a French study (the synthetic case with a
French sidecar, Auto MPG) and of an English one scans every junior-facing field of every
payload, the report and the notebook headings with ``graders_v03.foreign_sentences``. This is
not a Copilot session: the agent's and the junior's words are a test script and are left out.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

import flowkit as fk
import test_journey_walkthrough as jw
from mlkit.study import (case as c, correlation, diagnostics, eda, junior, l10n,
                         l10n_report, read, state as st, texts, view as view_mod)

REPO = Path(__file__).resolve().parents[3]
CASES = REPO / 'use-cases'
WORKSHOP_CASES = ('hotel-booking', 'bank-marketing-full', 'auto-mpg', 'online-shoppers',
                  'bank-marketing')
BUILT_CASES = ('hotel-booking', 'bank-marketing-full', 'online-shoppers')
sys.path.insert(0, str(REPO / 'framework' / 'tests' / 'acceptance' / 'agent'))
import graders_v03 as g  # noqa: E402
from test_v03_french_register import tu_forms  # noqa: E402


def _english_sentences(text: str, min_words: int = 4) -> list[str]:
    return g.foreign_sentences(text, 'fr', min_words=min_words)


# --- T7: the EDA sentences ---------------------------------------------------------------

def _eda_sentences() -> list[str]:
    """Every question and fixed note the EDA activities store, in both row wordings."""
    out = list(eda.QUESTIONS.values()) + list(eda.REGRESSION_QUESTIONS.values())
    for activity in ('eda.rate_by', 'eda.mean_by', 'eda.distribution'):
        out.append(eda.question(activity, 'lead_time'))
    out += [eda.DISTRIBUTION_NOTE, eda.NULL_BAND_NOTE, correlation.QUESTION, correlation.NOTE,
            eda.binning_words(10), eda.binning_words(4), eda.binning_words(10, 'development')]
    out += list(diagnostics.QUESTIONS.values())
    developed = [eda.development_words(t, 'question') for t in out]
    developed += [eda.development_words(t, 'note') for t in out]
    return list(dict.fromkeys(out + developed))


def test_every_eda_question_has_a_french_form():
    for text in _eda_sentences():
        french = l10n.eda_text(text, 'fr')
        assert french and french != text, text
        assert not _english_sentences(french), (text, french)
        assert not tu_forms(french), french
        assert l10n.eda_text(text, 'en') == text
    # A column name is kept as written, and an unknown sentence has no form (shown English).
    assert 'lead_time' in l10n.eda_text(eda.question('eda.rate_by', 'lead_time'), 'fr')
    assert l10n.eda_text('Something the engine never wrote.', 'fr') is None


def test_the_eda_warnings_and_the_signal_question_have_a_french_form():
    warnings = ['market_segment = Groups: only 12 training rows; its rate is too noisy to read '
                'on its own.',
                "agent has 200 values: the 20 largest groups are shown and the other 180 values "
                "are grouped as '(other values)' (1500 training rows)."]
    signal = ('deposit_type ranks the training rows with an out-of-fold AUC of 0.81 on its own, '
              'far above the other features (median 0.55). Is its value really known at the '
              'prediction moment, or is it recorded at or after the outcome? (availability '
              'decided: uncertain_excluded)')
    for text in warnings + [signal, eda.development_words(signal, 'text')]:
        french = l10n.eda_text(text, 'fr')
        assert french and not _english_sentences(french), (text, french)
    assert '0,81' in l10n.eda_text(signal, 'fr') and 'deposit_type' in l10n.eda_text(signal, 'fr')


# --- T2: the plan of init -------------------------------------------------------------------

def test_init_plan_is_in_the_study_language(tmp_path, synthetic_case_dir):
    english = fk.Flow(tmp_path / 'en', synthetic_case_dir).call(
        'init', '--case', synthetic_case_dir, '--study', tmp_path / 'en')
    french = fk.Flow(tmp_path / 'fr', synthetic_case_dir).call(
        'init', '--case', synthetic_case_dir, '--study', tmp_path / 'fr', '--lang', 'fr')
    # English: the plan is the state's, unchanged.
    assert english['plan'] == st.derive_plan(read.open(tmp_path / 'en').state)
    for en, fr in zip(english['plan'], french['plan']):
        assert fr['id'] == en['id']
        assert fr['title'] == junior.step_text(en['title'], 'fr') != en['title']
        assert fr['question'] == junior.step_text(en['question'], 'fr') != en['question']
    # ``plan`` and ``status`` give the same localized texts.
    plan = fk.Flow(tmp_path / 'fr', synthetic_case_dir).call('plan', '--study', tmp_path / 'fr')
    status = fk.Flow(tmp_path / 'fr', synthetic_case_dir).call('status', '--study', tmp_path / 'fr')
    assert [s['title'] for s in plan['steps']] == [s['title'] for s in french['plan']] \
        == [s['title'] for s in status['view']['plan']]


# --- D4 A: the case's translation sidecar ----------------------------------------------------

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_sidecar(case_dir: Path) -> Path:
    """A French sidecar of the synthetic case (a test fixture, not a committed case)."""
    case_file = case_dir / 'case.yaml'
    doc = yaml.safe_load(case_file.read_text(encoding='utf-8'))
    facts = {'observation_unit': "Un cycle de renouvellement d'une adhésion expirée",
             'intended_use': "Prioriser les appels des bénévoles quand la capacité est limitée",
             'prediction_time': "Non précisé par le bureau des adhésions",
             'causal_effect': "L'effet d'un appel sur le renouvellement n'est pas mesuré"}
    meanings = {('days_since_last_lapse', '-1'): "Le membre n'a jamais laissé expirer une "
                                                 "adhésion précédente",
                ('last_lapse_reason', 'unknown'): "Non documenté par le bureau des adhésions"}
    sources = {}
    for v in doc['variables']:
        sources[v['name']] = {'availability': {'source': {
            'fr': f"Source de la disponibilité de {v['name']}, traduite pour le test"}}}
    sidecar = {'schema': l10n.SCHEMA, 'case': {'id': doc['id'], 'sha256': _sha(case_file)},
               'facts': {f['id']: {'fr': facts[f['id']]} for f in doc['facts']
                         if f['id'] in facts},
               'structure': {'row_unit': {'fr': 'cycle de renouvellement'}},
               'special_values': [{'column': s['column'], 'value': s['value'],
                                   'meaning': {'fr': meanings[(s['column'], str(s['value']))]}}
                                  for s in doc['special_values']],
               'variables': sources}
    path = case_dir / l10n.FILE
    path.write_text(yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True),
                    encoding='utf-8')
    return path


def _copy_case(src: Path, dst: Path) -> Path:
    import shutil
    shutil.copytree(src, dst)
    return dst


def test_case_l10n_is_verified_and_optional(tmp_path, synthetic_case_dir):
    # A case without a sidecar: nothing recorded, the case's English, as before L3.
    flow = fk.Flow(tmp_path / 'plain', synthetic_case_dir)
    flow.call('init', '--case', synthetic_case_dir, '--study', flow.study, '--lang', 'fr')
    assert l10n.STATE_KEY not in read.open(flow.study).state
    card = flow.call('data', '--study', flow.study)
    assert card['observation_unit']['texts'] == {'en': card['observation_unit']['value'],
                                                 'fr': None}
    assert flow.view()['case_texts'] is None
    # A case with a valid sidecar: recorded with its sha256, shown in French.
    case_dir = _copy_case(synthetic_case_dir, tmp_path / 'case')
    sidecar = synthetic_sidecar(case_dir)
    flow = fk.Flow(tmp_path / 'fr', case_dir)
    flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', 'fr')
    state = read.open(flow.study).state
    assert state[l10n.STATE_KEY] == {'path': str(sidecar.resolve()), 'sha256': _sha(sidecar)}
    assert st.validate_state(state) == []
    card = flow.call('data', '--study', flow.study)
    assert card['observation_unit']['texts']['fr'].startswith('Un cycle')
    specials = {s['value']: s['texts'] for g_ in card['groups'] for v in g_['variables']
                for s in v['special_values']}
    assert specials[-1]['fr'].startswith("Le membre n'a jamais")
    summary = flow.call('status', '--summary', '--study', flow.study)
    assert summary['goal']['intended_use']['value'].startswith('Prioriser')
    # The English study of the same case quotes the case in English.
    flow_en = fk.Flow(tmp_path / 'en', case_dir)
    flow_en.call('init', '--case', case_dir, '--study', flow_en.study)
    assert flow_en.call('status', '--summary', '--study', flow_en.study)['goal'][
        'intended_use']['value'].startswith('Prioritise')
    # A sidecar changed after init is not used (English again) and changes nothing else:
    # no ``sources_changed``, decisions still accepted.
    sidecar.write_text(sidecar.read_text(encoding='utf-8').replace('Prioriser', 'Classer'),
                       encoding='utf-8')
    assert l10n.status(read.open(flow.study).state) == 'changed'
    view = flow.view()
    assert view['case_texts'] is None
    assert 'sources_changed' not in {x['id'] for x in view['not_yet_defensible']}
    assert flow.call('status', '--summary', '--study', flow.study)['goal']['intended_use'][
        'value'].startswith('Prioritise')
    flow.decide('prediction_time', 'when the record is created, before the outcome')
    # A sidecar written for other bytes of the case file (the case edited, its translation
    # not regenerated) is not used: nothing recorded, the case's English.
    stale = _copy_case(synthetic_case_dir, tmp_path / 'stale')
    synthetic_sidecar(stale)
    case_file = stale / 'case.yaml'
    case_file.write_text(case_file.read_text(encoding='utf-8') + '\n# edited\n',
                         encoding='utf-8')
    flow_stale = fk.Flow(tmp_path / 'stale-study', stale)
    flow_stale.call('init', '--case', stale, '--study', flow_stale.study, '--lang', 'fr')
    assert l10n.STATE_KEY not in read.open(flow_stale.study).state
    assert flow_stale.view()['case_texts'] is None
    with pytest.raises(l10n.L10nError):
        l10n.load(c.load_case(stale), required=True)
    # A sidecar of the right case bytes that states something the case does not is refused
    # at init, before any data is read.
    bad = _copy_case(synthetic_case_dir, tmp_path / 'bad')
    synthetic_sidecar(bad)
    doc = yaml.safe_load((bad / l10n.FILE).read_text(encoding='utf-8'))
    doc['facts']['no_such_fact'] = {'fr': 'x'}
    (bad / l10n.FILE).write_text(yaml.safe_dump(doc), encoding='utf-8')
    refused = fk.Flow(tmp_path / 'refused', bad).call(
        'init', '--case', bad, '--study', tmp_path / 'refused', expect=2)
    assert refused['error']['code'] == 'invalid_case'
    paths = {p['path'] for p in refused['error']['problems']}
    assert 'facts.no_such_fact' in paths
    assert not (tmp_path / 'refused').exists()


def test_a_study_created_before_l3_keeps_its_english_case_texts(tmp_path, synthetic_case_dir):
    """NR-18: a study without ``case_l10n`` (every study created before L3) loads and runs
    unchanged even when its case gains a sidecar later."""
    case_dir = _copy_case(synthetic_case_dir, tmp_path / 'case')
    flow = fk.Flow(tmp_path / 'old', case_dir)
    flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', 'fr')
    synthetic_sidecar(case_dir)                        # added after the study was created
    state = read.open(flow.study).state
    assert l10n.STATE_KEY not in state and st.validate_state(state) == []
    view = flow.view()
    assert view['case_texts'] is None
    assert not {'sources_changed', 'code_changed'} & {x['id'] for x in view['not_yet_defensible']}


@pytest.mark.parametrize('name', WORKSHOP_CASES)
def test_every_case_text_shown_to_the_junior_has_a_french_form(name):
    case = c.load_case(CASES / name / 'case.yaml', verify_data=False)
    loaded = l10n.load(case, required=True)            # valid, for this exact case file
    assert loaded['document']['case'] == {'id': case.id, 'sha256': _sha(case.path)}
    tr = l10n.translations({l10n.STATE_KEY: {'path': loaded['path'],
                                             'sha256': loaded['sha256']}}, case.document)
    doc = case.document
    french = []
    for f in doc['facts']:
        assert tr.fact(f['id'], 'fr'), (name, f['id'])
        french.append(tr.fact(f['id'], 'fr'))
    assert tr.row_unit('fr'), name
    for v in doc['variables']:
        if v.get('group'):
            assert tr.group(v['group'], 'fr'), (name, v['name'])
            french.append(tr.group(v['group'], 'fr'))
        assert tr.availability_source(v['name'], 'fr'), (name, v['name'])
        french.append(tr.availability_source(v['name'], 'fr'))
        for s in v.get('special_values') or []:
            assert tr.meaning(v['name'], s['value'], 'fr'), (name, v['name'], s['value'])
            french.append(tr.meaning(v['name'], s['value'], 'fr'))
    for text in french:
        # The quotations of the article or the dictionary stay in English, between « ».
        assert not _english_sentences(g.strip_quoted(text), 6), (name, text)
        assert not tu_forms(text), (name, text)


def _build_module(name: str):
    spec = importlib.util.spec_from_file_location(f'build_{name}'.replace('-', '_'),
                                                  CASES / name / 'build_case.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', BUILT_CASES)
def test_the_generated_sidecars_are_up_to_date(name, capsys):
    """``build_case.py --check`` covers the sidecar it generates; the case file is unchanged
    (a byte change would make every study on it ``sources_changed``, plan §2.2 rule 3)."""
    assert _build_module(name).main(['--check']) == 0, capsys.readouterr().out


# --- the report, the notebook, the Learn tab: content in French ------------------------------

def _placeholders(text: str) -> list[str]:
    """The citations and placeholders of a template (a fact's fallback words aside)."""
    text = re.sub(r'(\{\{fact:[^|}]*)\|[^}]*\}\}', r'\1}}', text or '')
    return sorted(re.findall(r'\{\{[^}]*\}\}|<[a-z_]+>', text))


def test_every_step_text_has_a_french_form_with_the_same_citations():
    english, french = texts.load('steps'), texts.load('steps_fr')
    for section in ('steps', 'regression_steps', 'cv_steps', 'regression_cv_steps',
                    'forward_steps', 'regression_forward_steps'):
        for step_id, content in english[section].items():
            for key, text in content.items():
                if key == 'concept':
                    continue
                fr = french[section][step_id][key]
                assert fr and fr != text, (section, step_id, key)
                assert _placeholders(fr) == _placeholders(text), (section, step_id, key)
                assert not _english_sentences(fr) and not tu_forms(fr), fr
    assert french['pending'] and french['stale']


def test_every_glossary_definition_and_example_has_a_french_form():
    data = texts.load('glossary')
    for section in ('terms', 'regression_terms', 'cv_terms', 'regression_cv_terms'):
        for term_id, entry in data[section].items():
            if 'definition' in entry:
                assert entry.get('definition_fr'), (section, term_id)
                assert not _english_sentences(entry['definition_fr']), (section, term_id)
                assert not tu_forms(entry['definition_fr']), (section, term_id)
            if 'cited_example' in entry:
                fr = entry.get('cited_example_fr')
                assert fr and _placeholders(fr) == _placeholders(entry['cited_example']), \
                    (section, term_id)


def test_every_activity_label_has_a_french_form():
    data = texts.load('activities')
    labels = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == 'label' and isinstance(v, str):
                    labels.add(v)
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    for section, node in data.items():
        if section not in ('fr_labels', 'cv_labels', 'schema'):
            walk(node)
    labels |= set(data['cv_labels'].values())
    assert sorted(labels - set(data['fr_labels'])) == []


def test_the_glossary_examples_speak_only_of_their_own_case():
    """R4: "glossary examples about bank clients in a Hotel study". The glossary's examples
    speak of the canonical case of each task; a study of another case reads the definition
    without them (its own figures give the example)."""
    for case_id, task, kept in (('uci-bank-marketing-full-v1', 'binary', True),
                                ('hotel-booking-resort-v1', 'binary', False),
                                ('uci-online-shoppers-v1', 'binary', False),
                                ('uci-auto-mpg-v1', 'regression', True),
                                ('synthetic-regression', 'regression', False)):
        with texts.study_context({'task': task, 'case': {'id': case_id}}):
            for lang in ('en', 'fr'):
                with texts.report_language_context(lang):
                    _, definition, _ = texts.concept('auc' if task == 'binary' else 'leakage')
                    assert (('For example' in definition or 'Par exemple' in definition)
                            == kept), (case_id, lang, definition)
                    assert 'client' not in definition or kept, definition
    # Outside a study the glossary is as written (the agent's copy, the tests of WP-A9).
    assert 'For example' in texts.glossary('auc')['definition']


# --- D4b: both languages for the panel -------------------------------------------------------

def test_the_digest_summary_gives_every_junior_text_in_both_languages(tmp_path):
    flow, task, _ = jw.journey_flow(tmp_path, 'synthetic', 'fr')
    flow.call('data', '--study', flow.study)
    out = flow.call('status', '--summary', '--digest', '--since', '0', '--study', flow.study)
    assert list(out)[-1] == 'texts' and list(out['texts']) == ['en', 'fr']
    for lang in ('en', 'fr'):
        table = out['texts'][lang]
        assert tuple(table) == view_mod.LANGUAGE_TEXT_KEYS
        assert set(table['plan']) == {s['id'] for s in out['plan']}
        assert set(table['moments']) == {m['id'] for m in out['moments']}
    # The study language's table is the summary's own; the other one is the same study read
    # in English.
    fr, en = out['texts']['fr'], out['texts']['en']
    assert fr['plan'] == {s['id']: s['title'] for s in out['plan']}
    assert en['plan']['discover_data'] == 'Discover the data'
    assert fr['moments']['frame'] == 'Cadrer le changement' and en['moments']['frame'] == \
        'Frame the change'
    assert fr['next_action'] == out['next_action']['junior_message']
    assert en['next_action'] and not g.foreign_sentences(en['next_action'], 'en', 4)
    assert fr['recap'] == out['recap_junior']
    assert all(not g.foreign_sentences(t, 'en', 4) for t in en['recap'])
    # The digest of a French study speaks French to the junior; ``text`` stays English.
    items = out['digest']['items']
    assert items and set(en['digest']) == set(fr['digest']) == {str(i['revision'])
                                                                 for i in items}
    for item in items:
        assert item['junior_text'] and not _english_sentences(item['junior_text'], 3), item
        assert fr['digest'][str(item['revision'])] == item['junior_text']
        assert not g.foreign_sentences(en['digest'][str(item['revision'])], 'en', 3)
    # Without ``--digest`` the summary has no ``texts`` (the agent's read stays compact).
    assert 'texts' not in flow.call('status', '--summary', '--study', flow.study)


# --- J-LANG: a walk through a French study and an English one --------------------------------

# Junior-facing fields of a payload (plan §3 L3 tests, §5.3 J-LANG). Values the junior or the
# agent wrote (restatements, user words, decision values, the conclusion's text) and the
# case's own words are not the engine's and are left out.
JUNIOR_KEYS = {'junior_message', 'junior_text', 'junior_digest', 'question_junior', 'why',
               'question', 'label', 'title', 'recap_junior', 'lead', 'line'}
SKIP_KEYS = {'restatement', 'user_words', 'labels', 'value', 'values', 'text', 'message',
             'recap', 'rationale', 'proposal_text', 'source', 'description', 'expected_output',
             'completion', 'agent_instructions', 'note', 'notices', 'en', 'params',
             'reason', 'details', 'stale_reason', 'invalidations', 'exposure', 'view_text',
             'model_selection', 'model_families', 'presentation', 'case_texts', 'facts'}


def _junior_strings(node, path='', inside=False):
    """``(path, text)`` of the junior-facing strings of a payload."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in SKIP_KEYS and not (k == 'question' or k == 'title'):
                continue
            if k == 'line' and 'junior_text' in node:
                continue                    # the English source; ``junior_text`` is shown
            yield from _junior_strings(v, f'{path}.{k}', inside or k in JUNIOR_KEYS
                                       or k in ('pause', 'texts', 'choice_options', 'plan',
                                                'moments', 'steps', 'recommended'))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _junior_strings(v, f'{path}[{i}]', inside)
    elif isinstance(node, str) and inside:
        yield path, node


def _scan(payload, lang: str, label: str, where: list) -> None:
    # The confirmed prediction moment is the junior's value, not the engine's text.
    decided = isinstance(payload, dict) and \
        ((payload.get('goal') or {}).get('prediction_time') or {}).get('source') == 'decision'
    for path, text in _junior_strings(payload):
        if lang == 'fr' and '.texts.en' in path:
            continue                                   # the other language, on purpose
        if lang == 'en' and '.texts.fr' in path:
            continue
        if decided and path.endswith('.goal.prediction_time'):
            continue
        for s in g.foreign_sentences(text, lang, min_words=5):
            where.append((label, path, s))


def _walk_and_scan(tmp_path, case: str, lang: str, monkeypatch) -> tuple[list, fk.Flow]:
    from mlkit.study import companion_env as ce
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    if case == 'synthetic':
        case_dir = fk.make_case(tmp_path / 'case', n_rows=300, task='binary')['case'].parent
        synthetic_sidecar(case_dir)
        flow = fk.Flow(tmp_path / f'study-{lang}', case_dir, prefix='j')
        init = flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', lang)
        task = 'binary'
    else:
        flow, task, init = jw.journey_flow(tmp_path, case, lang)
    found: list = []
    _scan(init, lang, 'init', found)
    reads = ['data', 'evidence', 'explain', 'plan']
    count = [0]

    def on_write(label, payload):
        _scan(payload, lang, label, found)
        count[0] += 1
        if count[0] % 3 == 0:
            for name in reads:
                _scan(flow.call(name, '--study', flow.study), lang, f'{label}/{name}', found)
            _scan(flow.call('status', '--summary', '--digest', '--study', flow.study), lang,
                  f'{label}/summary', found)
    jw.walk(flow, task, on_write=on_write, restatement_fr=lang == 'fr')
    for name in reads:
        _scan(flow.call(name, '--study', flow.study), lang, f'done/{name}', found)
    _scan(flow.call('status', '--summary', '--digest', '--since', '0', '--study', flow.study),
          lang, 'done/summary', found)
    return found, flow


# Text of the report that is not the engine's own wording: the case's and the junior's words
# (``q`` and recorded literals) and bibliographic references.
REFERENCES = ('Hastie, Tibshirani', 'Tibshirani & Tibshirani')


def _report_sentences(flow: fk.Flow, lang: str) -> list[str]:
    from html.parser import HTMLParser

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.out, self.skip = [], [], 0

        def handle_starttag(self, tag, attrs):
            a = dict(attrs)
            if tag in ('script', 'style', 'title'):
                self.skip += 1
            if tag in ('br', 'meta', 'link', 'img', 'hr', 'input', 'wbr', 'source', 'col'):
                return
            exempt = tag in ('q', 'code', 'data') or a.get('data-literal') in (
                'case', 'identifier', 'user_words', 'category', 'decision_value', 'data_row',
                'parameter', 'environment') or (a.get('lang') not in (None, lang))
            self.stack.append((tag, exempt))

        def handle_endtag(self, tag):
            if tag in ('script', 'style', 'title'):
                self.skip -= 1
            while self.stack:
                t, _ = self.stack.pop()
                if t == tag:
                    break

        def handle_data(self, data):
            if self.skip or any(e for _, e in self.stack):
                return
            text = ' '.join(data.split())
            if text and not any(r in text for r in REFERENCES):
                self.out.append(text)
    flow.call('render', '--study', flow.study)
    parser = Parser()
    parser.feed((flow.study / 'reports' / 'study.html').read_text(encoding='utf-8'))
    return [s for t in parser.out for s in g.foreign_sentences(t, lang, min_words=5)]


def _notebook_headings(flow: fk.Flow, lang: str) -> list[str]:
    text = (flow.study / 'notebooks' / 'study_generated.py').read_text(encoding='utf-8')
    found = []
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(?:## \d+\. (.+)|\*\*([^*]+)\.\*\* .*|mo\.md\('\*\*([^*]+)\.\*\*)", line)
        if m:
            heading = next(x for x in m.groups() if x)
            found.append(heading)
            found.extend(g.foreign_sentences(line.lstrip('#*0123456789. '), lang, 5))
    return found


@pytest.mark.parametrize('case', ['synthetic', 'auto-mpg'])
def test_j_lang_a_french_study_shows_no_english(tmp_path, monkeypatch, case):
    """J-LANG (French): no English sentence in the junior-facing fields of the payloads, the
    report or the notebook headings of a French study walked from ``init`` to ``done``."""
    found, flow = _walk_and_scan(tmp_path, case, 'fr', monkeypatch)
    assert found == [], found[:12]
    assert _report_sentences(flow, 'fr') == []
    headings = _notebook_headings(flow, 'fr')
    english = {'Method', 'Consequence', 'Interpretation', 'Decision'}
    assert not english & set(headings), headings
    assert not [h for h in headings if g.foreign_sentences(h, 'fr', 5)]


def test_j_lang_an_english_study_shows_no_french(tmp_path, monkeypatch):
    """J-LANG (English): the reverse, on Auto MPG."""
    found, flow = _walk_and_scan(tmp_path, 'auto-mpg', 'en', monkeypatch)
    assert found == [], found[:12]
    assert _report_sentences(flow, 'en') == []


@pytest.mark.skipif(not (CASES / 'hotel-booking' / 'data' / 'hotel-resort.csv').is_file(),
                    reason='the Hotel data file is not present')
def test_j_lang_hotel_french_structural_steps(tmp_path, monkeypatch):
    """J-LANG on Hotel (French), the structural steps (fast enough for the gate): the data card
    with the case's French statements, the framing pauses, the split, the quality overview,
    and the panel's reads, with no English in a junior-facing field."""
    from mlkit.study import companion_env as ce
    monkeypatch.setenv(ce.ENV_VAR, '1')
    monkeypatch.setenv(ce.STAGE_ENV, 'v3')
    case_dir = CASES / 'hotel-booking'
    flow = fk.Flow(tmp_path / 'hotel', case_dir, prefix='h')
    found: list = []
    _scan(flow.call('init', '--case', case_dir, '--study', flow.study, '--lang', 'fr'), 'fr',
          'init', found)
    card = flow.call('data', '--study', flow.study)
    shown = [card['observation_unit']['texts']['fr']]
    for group in card['groups']:
        shown.append(group['texts']['fr'])
        for v in group['variables']:
            shown.append(v['availability']['texts']['fr'])
            shown += [s['texts']['fr'] for s in v['special_values']]
    assert all(shown), 'every case statement of the card has its French form'
    for text in shown:
        found += [('data', 'texts.fr', s) for s in
                  g.foreign_sentences(g.strip_quoted(text), 'fr', 6)]
    for decision in ('prediction_time', 'feature_availability', 'split'):
        nxt = flow.call('status', '--summary', '--study', flow.study)['next_action']
        _scan(nxt, 'fr', f'status:{decision}', found)
        if decision == 'prediction_time':
            # Step 0 shows the data card until a proposal exists; the moment the agent then
            # proposes is the case's, in French (the view's ``case_texts``).
            assert nxt['kind'] == 'show_data_card', nxt['kind']
            view = flow.call('status', '--study', flow.study)['view']
            value = view['case_texts']['facts']['prediction_time']['fr']
        else:
            value = nxt.get('default_value')
        if decision == 'prediction_time':
            assert value.startswith('Quand la réservation est saisie'), value
        p = flow.call('decide', 'propose', decision, '--value-json', json.dumps(value),
                      '--restatement', f'You decide the {decision}.', '--restatement-fr',
                      f'Vous décidez : {decision}.', '--rationale', 'Test.',
                      '--request-id', flow.rid(), '--expected-revision', flow.rev(),
                      '--study', flow.study)
        _scan(p, 'fr', f'propose:{decision}', found)
        out = flow.call('decide', 'confirm', p['result']['proposal_id'], '--user-words',
                        'oui', '--adoption-question', '--request-id', flow.rid(),
                        '--expected-revision', flow.rev(), '--study', flow.study)
        _scan(out, 'fr', f'confirm:{decision}', found)
    for activity in ('split', 'eda.quality'):
        run = flow.call('run', activity, '--request-id', flow.rid(), '--expected-revision',
                        flow.rev(), '--study', flow.study)
        _scan(run, 'fr', f'run:{activity}', found)
    for name in ('evidence', 'explain'):
        _scan(flow.call(name, '--study', flow.study), 'fr', name, found)
    _scan(flow.call('status', '--summary', '--digest', '--since', '0', '--study', flow.study),
          'fr', 'summary', found)
    assert found == [], found[:12]
    # The panel's EDA card of the quality overview: its question in French, and in English.
    results = flow.call('evidence', '--study', flow.study)['results']
    quality = next(r for r in results if r['activity'] == 'eda.quality' and r['current'])
    assert quality['question_junior'].startswith('Y a-t-il des cellules manquantes')
    assert quality['texts']['en']['question'] == quality['values']['question']
    assert quality['texts']['fr']['question'] == quality['question_junior']


def test_the_report_phrases_are_french_and_say_vous():
    for english, french in l10n_report.EXACT.items():
        assert french, english
        assert not tu_forms(french), french
    sample = ('<figure><figcaption>Question. How far from the observed value are the '
              'predictions of each model on the out-of-fold predictions?</figcaption>'
              '<svg aria-label="Mean residual by model_year"><text>Predicted value</text>'
              '</svg><p>Points: rows (<data value="3">3</data> shown of <data>9</data>); '
              'line: the mean residual of each bin of predictions. Rank correlation of the '
              'size of the residual with the prediction: <data>0.1</data>.</p>'
              '<q data-literal="case">Mean</q></figure>')
    out = l10n_report.french(sample)
    assert 'Résidu moyen par model_year' in out and 'Valeur prédite' in out
    assert 'affichées sur' in out and '<data value="3">3</data>' in out
    assert '<q data-literal="case">Mean</q>' in out          # the case's words are kept
    assert l10n_report.french('<p>Something new.</p>') == '<p>Something new.</p>'
