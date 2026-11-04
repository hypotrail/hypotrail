"""Onboarding Lots 2 and 3 (``docs/plans/ONBOARDING-SPEC.md``): from one data file to a sealed
study. Real ``hypotrail`` processes on synthetic CSV files written in ``tmp_path``:

* ``new --data`` copies the file into ``NAME.case/`` with its sha256 and structural profile,
  and leaves ``NAME/`` preparing (agent files, no state, no partition, no case, no data link);
* the six questions are recorded in the user's words, exposure first; a proposal is not an
  answer; the final test is accepted by its plan digest;
* the final test is deduced from the facts: a future use with documented clocks is temporal
  (delayed labels kept out of training), recurring entities are grouped, a regression without
  time or entities is quantile-stratified, and a dataset too small for the minimums is
  refused with its reason;
* the feasibility check reports counts without the target: no proportion of a label.

Nothing here touches ``use-cases/`` or an existing study.
"""
from __future__ import annotations

import json
import random

import pytest
import yaml

from mlkit.study import case as c, partition

from flowkit import hyp


def binary_time_csv(path, n=1500, seed=1, customers=400):
    rng = random.Random(seed)
    lines = ['booking_id,customer_id,booking_day,outcome_day,lead_time,country,price,canceled']
    for i in range(n):
        day = 18000 + i // 3
        lead = rng.randint(1, 60)
        canceled = 'yes' if rng.random() < 0.3 + lead / 300 else 'no'
        lines.append(f'B{i:05d},C{rng.randint(1, customers)},{day},{day + lead},{lead},'
                     f'{rng.choice(["FR", "DE", "PT"])},{rng.uniform(50, 300):.2f},{canceled}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def regression_csv(path, n=800, seed=2):
    rng = random.Random(seed)
    lines = ['weight,cylinders,origin,mpg']
    for _ in range(n):
        w = rng.uniform(1500, 5000)
        lines.append(f'{w:.0f},{rng.choice([4, 6, 8])},{rng.choice(["us", "eu", "jp"])},'
                     f'{45 - w / 150 + rng.gauss(0, 2):.1f}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return path


def answer(study, question, value, words, rev, *, basis=None, expect=0, cwd=None):
    args = ['prepare', 'answer', question, '--value-json', json.dumps(value),
            '--user-words', words, '--expected-revision', rev, '--study', study]
    if basis:
        args += ['--basis', basis]
    code, out = hyp(*args, cwd=cwd or study.parent)
    assert code == expect, out
    return out


def prepare(study, answers, cwd):
    """Answer the five questions before the final test; returns the last status."""
    code, out = hyp('prepare', 'status', '--study', study, cwd=cwd)
    assert code == 0, out
    for question, value, words, basis in answers:
        out = answer(study, question, value, words, out['revision'], basis=basis, cwd=cwd)
    return out


def accept_and_seal(study, out, cwd):
    final = out['final_test']
    assert final['status'] == 'pass', final
    out = answer(study, 'final_test', {'accept': True, 'plan': final['plan']},
                 "D'accord, je l'accepte.", out['revision'], cwd=cwd)
    code, sealed = hyp('seal', '--expected-revision', out['revision'], '--study', study,
                       cwd=cwd)
    assert code == 0, sealed
    return final, sealed


FUTURE = [('exposure', {'explored': 'not_explored'}, 'Non, jamais ouvert.', None),
          ('target', {'column': 'canceled', 'positive_label': 'yes'}, 'La cible est canceled, '
           'yes veut dire annulé.', 'known'),
          ('row_unit', {'row_unit': 'one booking'}, 'Une ligne est une réservation.', 'known'),
          ('timing', {'use': 'future', 'statement': 'At booking, before the stay.',
                      'prediction_clock': 'booking_day', 'outcome_clock': 'outcome_day'},
           'On prédit à la réservation ; on sait à l\'arrivée.', 'known'),
          ('entities', {'recurring': 'no'}, 'Chaque réservation est indépendante.', 'assumed')]


def test_new_data_prepares_without_reading_the_target(tmp_path):
    data = binary_time_csv(tmp_path / 'bookings.csv')
    code, out = hyp('new', tmp_path / 'hotel', '--data', data, '--context',
                    'Hotel bookings; predict cancellations at booking time.', cwd=tmp_path)
    assert code == 0, out
    study, case_dir = tmp_path / 'hotel', tmp_path / 'hotel.case'
    assert out['state'] == 'preparing' and out['next_question'] == 'exposure'
    copy = case_dir / 'data' / 'bookings.csv'
    assert copy.read_bytes() == data.read_bytes()
    profile = json.loads((case_dir / 'profile.json').read_text(encoding='utf-8'))
    assert profile['sha256'] == c.sha256_file(copy) and profile['rows'] == 1500
    draft = yaml.safe_load((case_dir / 'case.draft.yaml').read_text(encoding='utf-8'))
    assert [t['question'] for t in draft['todo'][:6]] == ['exposure', 'target', 'row_unit',
                                                           'timing', 'entities', 'final_test']
    # The study folder: preparation instructions, the context as a brief, no state, no
    # partition, no case, and no link to the data.
    assert (study / 'CLAUDE.md').is_file()
    assert (study / '.claude/skills/hypotrail-prepare/SKILL.md').is_file()
    assert (study / '.github/skills/hypotrail-prepare/SKILL.md').is_file()
    assert not (study / '.hypotrail' / 'state.json').exists()
    assert not (case_dir / 'case.yaml').exists() and not (study / 'data').exists()
    source = json.loads((study / 'brief' / 'source.json').read_text(encoding='utf-8'))
    assert source['kind'] == 'context' and 'cancellations' in source['pages'][0]['text']
    assert out['brief']['kind'] == 'context'
    # Structural only: suspicious columns flagged from names and structure.
    flagged = {s['column'] for s in out['suspicious']}
    assert {'booking_id', 'outcome_day'} <= flagged
    # The data file never enters the study folder.
    assert not list(study.rglob('bookings.csv'))


def test_answers_are_words_exposure_first_and_proposals_stay_proposals(tmp_path):
    data = binary_time_csv(tmp_path / 'bookings.csv')
    code, out = hyp('new', tmp_path / 'hotel', '--data', data, cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / 'hotel'
    rev = out['revision']
    # The target before the exposure question: refused.
    out = answer(study, 'target', {'column': 'canceled', 'positive_label': 'yes'}, 'canceled',
                 rev, expect=2)
    assert out['error']['details']['reason'] == 'exposure_first'
    # A proposal with its source is recorded as proposed, not answered.
    code, out = hyp('prepare', 'answer', 'target', '--propose', '--source',
                    'column names and structural profile', '--value-json',
                    json.dumps({'column': 'canceled', 'positive_label': 'yes'}),
                    '--expected-revision', rev, '--study', study, cwd=tmp_path)
    assert code == 0, out
    target = next(q for q in out['questions'] if q['id'] == 'target')
    assert target['status'] == 'proposed' and target['user_words'] is None
    # A stale revision is refused; words that are a question are refused.
    answer(study, 'exposure', {'explored': 'not_explored'}, 'Non.', rev, expect=2)
    answer(study, 'exposure', {'explored': 'not_explored'}, 'Explorer ?', out['revision'],
           expect=2)
    out = answer(study, 'exposure', {'explored': 'looked_at_rows'}, "J'ai regardé des lignes.",
                 out['revision'])
    out = answer(study, 'target', {'column': 'canceled', 'positive_label': 'yes'},
                 'Oui, canceled.', out['revision'])
    target = next(q for q in out['questions'] if q['id'] == 'target')
    assert target['status'] == 'answered'
    assert target['source'] == 'column names and structural profile'
    # Once named, the target shows only its label set and missing count (no examples).
    column = next(col for col in out['columns'] if col['name'] == 'canceled')
    assert column == {'name': 'canceled', 'type': 'binary', 'missing': 0, 'distinct': 2,
                      'role': 'target', 'labels': ['no', 'yes']}
    # A target with several categories is refused as an unsupported task.
    out = answer(study, 'target', {'column': 'country', 'positive_label': 'FR'}, 'country',
                 out['revision'], expect=2)
    assert out['error']['details']['reason'] == 'unsupported_task'


def test_future_use_with_documented_clocks_is_temporal(tmp_path):
    data = binary_time_csv(tmp_path / 'bookings.csv')
    code, out = hyp('new', tmp_path / 'hotel', '--data', data, '--lang', 'fr', cwd=tmp_path)
    assert code == 0, out
    study, case_dir = tmp_path / 'hotel', tmp_path / 'hotel.case'
    out = prepare(study, FUTURE, tmp_path)
    final = out['final_test']
    assert final['rule'] == 'future_temporal' and final['method'] == 'temporal'
    # Counts without the target: no proportion of a label, the minority check as pass/fail.
    text = json.dumps(final)
    assert 'positive' not in text and 'rate' not in text
    minority = next(ch for ch in final['checks'] if ch['check'] == 'min_minority_events')
    assert minority['actual'] is None and minority['status'] == 'pass'
    assert final['counts']['period']['final'][1] == 18499
    assert final['counts']['delayed_label_rows'] > 0
    code, feas = hyp('case', 'check', '--feasibility', '--study', study, cwd=tmp_path)
    assert code == 0 and feas['plan'] == final['plan'], feas
    # A plan digest that is not the current one is refused.
    answer(study, 'final_test', {'accept': True, 'plan': 'deadbeef'}, 'Oui.', out['revision'],
           expect=2)
    final, sealed = accept_and_seal(study, out, tmp_path)
    assert sealed['final_test']['status'] == 'sealed'
    assert sealed['final_test']['method'] == 'temporal'
    assert sealed['final_test']['rows'] == final['counts']['final_rows']
    assert not (study / 'data').exists() and not (study / '.hypotrail/preparing.json').exists()
    case = c.load_case(case_dir)
    contract = case.document['analysis_contract']
    assert contract['intended_use'] == 'future_prediction'
    assert 'future_predictive_performance' in contract['permitted_claims']
    assert [p['status'] for p in case.document['prior_exposure']] == \
        ['observed', 'scenario_assumption']
    state = json.loads((study / '.hypotrail' / 'state.json').read_text(encoding='utf-8'))
    part = state['partition']
    assert state['settings']['reliability_profile'] == 'review-v1'
    assert part['analysis_protocol']['deduction']['rule'] == 'future_temporal'
    assert part['analysis_protocol']['deduction']['accepted']['user_words'] == \
        "D'accord, je l'accepte."
    assert part['training_exclusions']['n_rows'] == final['counts']['delayed_label_rows']
    # The study's own instructions replaced the preparation's.
    assert not (study / '.claude/skills/hypotrail-prepare').exists()
    assert (study / '.claude/skills/hypotrail-study/SKILL.md').is_file()
    # The report's first chapter says how the final test was set aside.
    code, out = hyp('render', '--study', study, cwd=tmp_path)
    assert code == 0, out
    html = (study / 'reports' / 'study.html').read_text(encoding='utf-8')
    assert 'id="final-test-set-aside"' in html and 'data-deduction="future_temporal"' in html
    # Preparation is over.
    code, out = hyp('prepare', 'status', '--study', study, cwd=tmp_path)
    assert code == 2 and out['error']['details']['reason'] == 'already_sealed', out


def test_recurring_entities_are_grouped(tmp_path):
    data = binary_time_csv(tmp_path / 'bookings.csv', customers=300)
    code, out = hyp('new', tmp_path / 'hotel', '--data', data, cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / 'hotel'
    answers = [
        FUTURE[0], FUTURE[1], FUTURE[2],
        ('timing', {'use': 'retrospective', 'statement': 'Compare past bookings.'},
         'Rétrospectif.', 'assumed'),
        ('entities', {'recurring': 'yes', 'column': 'customer_id'},
         'Un client revient souvent.', 'known')]
    out = prepare(study, answers, tmp_path)
    final = out['final_test']
    assert final['rule'] == 'grouped' and final['method'] == 'stratified', final
    groups = final['counts']['groups']
    assert groups['final'] + groups['development'] == groups['total']   # disjoint entities
    final, sealed = accept_and_seal(study, out, tmp_path)
    contract = c.load_case(tmp_path / 'hotel.case').document['analysis_contract']
    assert contract['dependencies']['kind'] == 'grouped'
    assert contract['permitted_claims'] == ['retrospective_association']


def test_regression_without_time_is_quantile_stratified(tmp_path):
    data = regression_csv(tmp_path / 'cars.csv')
    code, out = hyp('new', tmp_path / 'mpg', '--data', data, cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / 'mpg'
    answers = [('exposure', {'explored': 'analysed_with_target'}, "Je l'ai déjà analysé.", None),
               ('target', {'column': 'mpg', 'unit': 'mpg'}, 'mpg, en miles par gallon.',
                'known'),
               ('row_unit', {'row_unit': 'one car model'}, 'Un modèle de voiture.', 'assumed'),
               ('timing', {'use': 'unknown', 'statement': 'Not stated.'}, 'Je ne sais pas.',
                'unknown'),
               ('entities', {'recurring': 'unknown'}, 'Je ne sais pas.', 'unknown')]
    out = prepare(study, answers, tmp_path)
    final = out['final_test']
    assert final['rule'] == 'unknown_stratified' and final['method'] == 'quantile_stratified'
    final, sealed = accept_and_seal(study, out, tmp_path)
    case = c.load_case(tmp_path / 'mpg.case')
    assert case.task == 'regression' and case.target_unit == 'mpg'
    assert case.document['analysis_contract']['permitted_claims'] == \
        ['retrospective_association']
    assert 'not unseen' in case.document['prior_exposure'][1]['value']


def test_too_small_datasets_are_refused_with_their_reason(tmp_path):
    tiny = regression_csv(tmp_path / 'tiny.csv', n=200)
    code, out = hyp('new', tmp_path / 'tiny', '--data', tiny, cwd=tmp_path, expect=2)
    assert out['error']['details']['reason'] == 'too_few_rows'
    assert not (tmp_path / 'tiny').exists() and not (tmp_path / 'tiny.case').exists()
    # Enough rows for a final test in principle, not at the default share: the seal refuses.
    small = binary_time_csv(tmp_path / 'small.csv', n=400)
    code, out = hyp('new', tmp_path / 'small', '--data', small, cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / 'small'
    out = prepare(study, FUTURE, tmp_path)
    final = out['final_test']
    assert final['status'] == 'fail'
    assert [ch['check'] for ch in final['checks'] if ch['status'] == 'fail'] == \
        ['min_final_rows']
    rev = out['revision']
    out = answer(study, 'final_test', {'accept': True, 'plan': final['plan']}, 'Oui.', rev,
                 expect=2)
    assert out['error']['details']['reason'] == 'feasibility_failed'
    code, out = hyp('seal', '--expected-revision', rev, '--study', study, cwd=tmp_path)
    assert code == 2 and out['error']['details']['reason'] == 'questions_missing', out
    assert not (tmp_path / 'small.case' / 'case.yaml').exists()


@pytest.mark.parametrize('content, reason', [
    ('a,b\n"x\ny",1\n"z",2\n', 'multi_line_records'),
    ('a,b\n1,2\n3\n', 'inconsistent_fields'),
])
def test_unreadable_files_are_refused_before_any_write(tmp_path, content, reason):
    path = tmp_path / 'bad.csv'
    path.write_text(content, encoding='utf-8')
    code, out = hyp('new', tmp_path / 'bad', '--data', path, cwd=tmp_path, expect=2)
    assert out['error']['details']['reason'] == reason
    assert not (tmp_path / 'bad.case').exists()


def test_non_utf8_is_refused(tmp_path):
    path = tmp_path / 'latin.csv'
    path.write_bytes('ville,prix\nSète,1\n'.encode('latin-1'))
    code, out = hyp('new', tmp_path / 'latin', '--data', path, cwd=tmp_path, expect=2)
    assert out['error']['details']['reason'] == 'not_utf8'


def test_deduction_mirrors_the_review_planner():
    """The rules of §2.4, on contracts alone (no data read)."""
    def contract(use, kind, clock=None, group=None):
        clock_spec = {'by': clock, 'status': 'documented_fact', 'source': 's'} if clock else None
        return {'intended_use': use, 'timing': {'prediction_order': clock_spec},
                'dependencies': {'kind': kind, 'group_column': group}}
    assert partition.deduce(contract('future_prediction', 'temporal', 'd'), 'binary')['rule'] \
        == 'future_temporal'
    assert partition.deduce(contract('future_prediction', 'grouped_temporal', 'd', 'g'),
                            'binary')['rule'] == 'grouped_temporal'
    assert partition.deduce(contract('retrospective_comparison', 'grouped', None, 'g'),
                            'binary')['method'] == 'stratified'
    assert partition.deduce(contract('retrospective_comparison', 'temporal', 'd'),
                            'regression')['rule'] == 'assumed_temporal'
    assert partition.deduce(contract('retrospective_comparison', 'independent'),
                            'regression')['method'] == 'quantile_stratified'
    assert partition.deduce(contract('retrospective_comparison', 'unknown'),
                            'binary')['rule'] == 'unknown_stratified'


def test_a_date_clock_is_refused_with_the_way_forward(tmp_path):
    rng = random.Random(3)
    lines = ['booked_on,amount,late']
    for i in range(600):
        lines.append(f'2024-{1 + i % 12:02d}-{1 + i % 28:02d},{rng.randint(1, 99)},'
                     f'{rng.choice(["y", "n"])}')
    path = tmp_path / 'loans.csv'
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    code, out = hyp('new', tmp_path / 'loans', '--data', path, cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / 'loans'
    out = answer(study, 'exposure', {'explored': 'not_explored'}, 'Non.', out['revision'])
    out = answer(study, 'timing', {'use': 'future', 'statement': 'At the loan request.',
                                   'prediction_clock': 'booked_on'}, 'À la demande.',
                 out['revision'], expect=2)
    assert out['error']['details']['reason'] == 'date_clock'
    assert 'derived from the date' in out['error']['message']


def _docx(path, paragraphs):
    import zipfile
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    body = ''.join(
        f'<w:p>{"<w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr>" if heading else ""}'
        f'<w:r><w:t>{text}</w:t></w:r></w:p>' for heading, text in paragraphs)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml',
                         f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>')
    return path


def test_briefs_in_word_and_markdown_are_read_by_section(tmp_path):
    from mlkit.study import cmd_brief
    docx = _docx(tmp_path / 'fiche.docx', [(True, 'Problème'), (False, 'Les annulations.'),
                                           (True, 'Objectif'), (False, 'Appeler à temps.')])
    data, pages, kind = cmd_brief.extract_document(docx)
    assert kind == 'docx' and [p['n'] for p in pages] == [1, 2]
    assert pages[1]['text'] == 'Objectif\nAppeler à temps.'
    md = tmp_path / 'fiche.md'
    md.write_text('# Problem\nCancellations.\n\n# Goal\nCall in time.\n', encoding='utf-8')
    assert [p['text'].splitlines()[0] for p in cmd_brief.extract_document(md)[1]] == \
        ['# Problem', '# Goal']
    other = tmp_path / 'fiche.odt'
    other.write_bytes(b'x')
    with pytest.raises(Exception) as caught:
        cmd_brief.extract_document(other)
    assert caught.value.details['reason'] == 'unsupported_brief_format'
    # new --data with a Word brief: the brief is in the study folder, then imported at seal.
    data = binary_time_csv(tmp_path / 'bookings.csv')
    code, out = hyp('new', tmp_path / 'hotel', '--data', data, '--brief', docx, cwd=tmp_path)
    assert code == 0, out
    assert out['brief']['kind'] == 'docx' and out['brief']['units'] == 2
    study = tmp_path / 'hotel'
    out = prepare(study, FUTURE, tmp_path)
    final, sealed = accept_and_seal(study, out, tmp_path)
    assert sealed['brief']['result']['pdf'] == 'fiche.docx'
    state = json.loads((study / '.hypotrail' / 'state.json').read_text(encoding='utf-8'))
    assert state['brief']['source']['pages'] == 2


def test_the_preparation_templates_are_not_loaded_in_this_repository():
    from mlkit.study import agent_files as af, cmd_prepare
    stored = [p.relative_to(cmd_prepare.AGENT_SOURCE) for p in cmd_prepare.AGENT_SOURCE.rglob('*')]
    assert not [p for p in stored if set(p.parts) & set(af.LOADED_NAMES)]
    assert {p.as_posix() for p in stored if (cmd_prepare.AGENT_SOURCE / p).is_file()} == \
        set(cmd_prepare.AGENT_TARGETS)


def test_the_hook_refuses_the_raw_file_while_the_study_is_prepared(tmp_path):
    """Before ``seal`` the study has no state: the hook reads ``.hypotrail/preparing.json``
    and ``NAME.case/``, and denies a call naming the copied file, the original file or the
    case's data folder; after ``seal`` it still denies the file (from the state)."""
    from mlkit.study import cmd_hook
    data = binary_time_csv(tmp_path / 'bookings.csv')
    code, out = hyp('new', tmp_path / 'hotel', '--data', data, '--context',
                    'Hotel bookings; predict cancellations at booking time.', cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / 'hotel'
    assert (study / cmd_hook.HOOK_FILE).is_file()               # installed while preparing
    prefixes, files, language = cmd_hook.study_rule(study)
    assert prefixes and 'bookings.csv' in files and language == 'en'
    assert {'hotel.case/data', 'hotel.case\\data'} <= set(files)

    def decided(tool, args):
        return cmd_hook.decide({'tool_name': tool, 'tool_input': args}, prefixes, files)[0]
    assert decided('read_file', {'filePath': str(tmp_path / 'hotel.case' / 'data' /
                                                 'bookings.csv')}) == 'deny'
    assert decided('run_in_terminal', {'command': 'head -5 ../bookings.csv'}) == 'deny'
    assert decided('run_in_terminal', {'command': 'ls ../hotel.case/data'}) == 'deny'
    assert decided('run_in_terminal', {'command': 'ls'}) is None
    out = prepare(study, FUTURE, tmp_path)
    accept_and_seal(study, out, tmp_path)
    _, after, _ = cmd_hook.study_rule(study)
    assert after == ['bookings.csv']                              # from the sealed state


def test_the_hook_command_is_written_for_each_shell():
    """``powershell`` runs on Windows and ``bash`` elsewhere (hooks reference): each line is
    quoted for its shell, so a path with spaces works under both."""
    from mlkit.study import agent_files as af, cmd_hook
    exe = r'C:\Users\Ana Lima\AppData\Roaming\uv\tools\hypotrail\Scripts\hypotrail.exe'
    config = cmd_hook.hook_config([exe], r'C:\Users\Ana Lima\Études\hotel')
    [entry] = config['hooks']['PreToolUse']
    assert config['version'] == 1 and entry['type'] == 'command'
    assert entry['powershell'].startswith("& 'C:\\Users\\Ana Lima\\AppData\\")
    assert "--study 'C:\\Users\\Ana Lima\\Études\\hotel'" in entry['powershell']
    words = cmd_hook.tokens(entry['powershell'], windows=True)
    assert words[:4] == [exe, 'hook', 'pretool', '--study']
    import shlex
    assert shlex.split(entry['bash'])[:3] == [exe, 'hook', 'pretool']
    assert entry['command'] in (entry['bash'], entry['powershell'])
    assert entry['command'] == af.display_command(shlex.split(entry['bash']))


def _prepared(tmp_path, name='hotel'):
    data = binary_time_csv(tmp_path / f'{name}.csv')
    code, out = hyp('new', tmp_path / name, '--data', data, '--context',
                    'Hotel bookings; predict cancellations at booking time.', cwd=tmp_path)
    assert code == 0, out
    study = tmp_path / name
    out = prepare(study, FUTURE, tmp_path)
    final = out['final_test']
    out = answer(study, 'final_test', {'accept': True, 'plan': final['plan']},
                 "D'accord, je l'accepte.", out['revision'], cwd=tmp_path)
    return study, out


def test_the_automatic_mode_is_chosen_at_seal_the_launch_of_a_prepared_study(tmp_path):
    """ADR 0005: the automatic mode is chosen when the study is created; with ``--data``
    that is ``seal``. ``new --data --automation`` names it; ``seal --automation`` records the
    mode as ``init --automation`` does; a study sealed without it has none."""
    data = binary_time_csv(tmp_path / 'x.csv')
    code, out = hyp('new', tmp_path / 'early', '--data', data, '--automation',
                    'until_final_test', cwd=tmp_path)
    assert code == 2 and out['error']['code'] == 'invalid_arguments', out
    assert 'seal --automation' in out['error']['message']
    assert not (tmp_path / 'early').exists() and not (tmp_path / 'early.case').exists()

    study, out = _prepared(tmp_path)
    code, bad = hyp('seal', '--expected-revision', out['revision'], '--automation', 'always',
                    '--study', study, cwd=tmp_path)
    assert code == 2 and bad['error']['code'] == 'invalid_arguments'
    code, sealed = hyp('seal', '--expected-revision', out['revision'], '--automation',
                       'until_final_test', '--study', study, cwd=tmp_path)
    assert code == 0, sealed
    state = json.loads((study / '.hypotrail' / 'state.json').read_text(encoding='utf-8'))
    assert state['automation'] == {'mode': 'until_final_test', 'status': 'running',
                                   'started_revision': 1, 'ended': None}
    assert sealed['deduction']['accepted']['user_words'] == "D'accord, je l'accepte."
    # The prepared case documents no availability: the automatic mode records the framing
    # it can, then stops at the columns and asks the junior, instead of excluding them all.
    code, run = hyp('automation', 'run', '--json', '--request-id', 'a1', '--expected-revision',
                    sealed['revision'], '--study', study, cwd=tmp_path)
    assert code == 0, run
    assert (run['status'], run['reason']) == ('stopped', 'no_automatic_value'), run
    assert run['stopped_at']['decision'] == 'feature_availability' and run['refusal'] is None
    assert [s['decision'] for s in run['steps'] if s['decision']][:1] == ['prediction_time']

    plain, out = _prepared(tmp_path, 'plain')
    code, sealed = hyp('seal', '--expected-revision', out['revision'], '--study', plain,
                       cwd=tmp_path)
    assert code == 0, sealed
    state = json.loads((plain / '.hypotrail' / 'state.json').read_text(encoding='utf-8'))
    assert state.get('automation') is None
