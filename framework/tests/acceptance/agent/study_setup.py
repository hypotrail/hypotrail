"""Hypotrail study workspaces for agent acceptance (arm B of E1, scenarios S1-S9).

The study workspace is created exactly as a junior would get it: the case is copied into
``<workspace>/case/`` (Bank: ``case.yaml`` and its ``data/`` files; synthetic: the
``case.yaml`` and ``data.csv`` written by ``make_case`` into a hidden directory, never
``truth.json``), a neutral ``README.md`` describes the scenario (the same text arm A got,
with the file paths of the case folder), and ``hypotrail init --case <case.yaml> --study
<workspace>`` installs ``CLAUDE.md``, the skill, and the resume command.

``advance`` then builds the study state with direct CLI processes (no agent) up to a named
stage of the WP4.2 walkthrough, with the junior's words of
``framework/tests/study/test_walkthrough.py``, so that a scenario starts where it matters.

Every CLI call is a fresh ``python -m mlkit.study.cli`` process of the framework
environment, run from a directory outside the repository.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
FRAMEWORK = REPO_ROOT / 'framework'
BANK = REPO_ROOT / 'use-cases' / 'bank-marketing'
AUTO_MPG = REPO_ROOT / 'use-cases' / 'auto-mpg'
BANK_FULL = REPO_ROOT / 'use-cases' / 'bank-marketing-full'
SHOPPERS = REPO_ROOT / 'use-cases' / 'online-shoppers'
HOTEL = REPO_ROOT / 'use-cases' / 'hotel-booking'

SPLIT = {'method': 'stratified_random', 'validation_fraction': 0.3, 'seed': 20261017}
THRESHOLD = 'threshold:0.2'
# v0.2a (WP-A4): the success criterion is fixed after the split, before any fit; the
# preprocessing after the training exploration (the engine's default, as in the walkthrough).
CRITERION = {'metric': 'precision_gain', 'min_points': 5}
REGRESSION_CRITERION = {'metric': 'mae_reduction', 'min_share': 0.1}

# The junior's words, as in the WP4.2 walkthrough (framework/tests/study/test_walkthrough.py).
JUNIOR = {
    'bank': {
        'prediction_time': 'before the first contact of the campaign, from the client file',
        'restatement': 'You score each client before the first call, from what the client '
                       'file holds at that moment.',
        'words': 'Yes, before the first call, using only the client file.',
        'exclusions': {'duration': 'not_available', 'day': 'not_available',
                       'month': 'not_available', 'campaign': 'not_available',
                       'contact': 'uncertain_included'},
        'availability_words': 'Drop duration, day, month and campaign: they describe the calls '
                              'of this campaign. Keep contact but list it as a doubt.',
        'rate_by': 'job',
        # S10 (WP-A8, owner remark R3): the junior also drops `contact` with a reason that
        # belongs to `campaign` (inflation), so the availability proposal excludes it.
        'exclusions_s10': {'duration': 'not_available', 'day': 'not_available',
                           'month': 'not_available', 'campaign': 'not_available',
                           'contact': 'uncertain_excluded'},
        'restatement_s10': 'You exclude duration, day, month, campaign and contact, and keep '
                           'the other variables.',
        # S2: an earlier, different prediction moment that the junior corrects in a second chat
        'prediction_time_s2': 'before each call of the campaign, from the client file and the '
                              'calls made so far',
        'restatement_s2': 'You score each client before each call, from the client file and the '
                          'calls made so far.',
        'words_s2': 'Yes, before each call, with what we know at that point.',
    },
    # v0.2b (WP-B6b): the discovery case. PageValues is the leakage question of the case
    # (availability `uncertain`, flagged by the single-feature signal).
    'shoppers': {
        'prediction_time': 'at the end of the session, before any follow-up is sent',
        'restatement': 'You score each session when it ends, from what the session recorded, '
                       'before any follow-up.',
        'words': 'Yes, when the session ends, before we send any follow-up.',
        'exclusions': {'PageValues': 'uncertain_excluded', 'BounceRates': 'uncertain_included',
                       'ExitRates': 'uncertain_included'},
        'availability_words': 'Leave PageValues out: we do not know whether it counts the '
                              "session's own purchase. Keep BounceRates and ExitRates but list "
                              'them as a doubt.',
        'rate_by': 'VisitorType',
        # S10: the junior also drops BounceRates with the reason that belongs to PageValues
        # (built from transactions: it may count the session's own purchase).
        'exclusions_s10': {'PageValues': 'uncertain_excluded',
                           'BounceRates': 'uncertain_excluded',
                           'ExitRates': 'uncertain_included'},
        'restatement_s10': 'You exclude PageValues and BounceRates, keep ExitRates as a stated '
                           'doubt, and keep the other variables.',
        'policy_words': 'Yes, follow up the top 10% of sessions, because the budget covers '
                        'one session in ten.',
    },
    # v0.3 (WP-G): the discovery case. The outcome columns and what the hotel records after
    # the booking are `not_available` in the case; five columns have an uncertain timing.
    'hotel': {
        'prediction_time': 'when the booking is entered in the hotel system, before anyone '
                           'contacts the customer',
        'restatement': 'You score each booking when it is entered, from what the booking '
                       'request and the guest history hold at that moment.',
        'words': 'Yes, when the booking is entered, before we contact anyone.',
        'exclusions': {'country': 'uncertain_excluded', 'deposit_type': 'uncertain_excluded',
                       'adr': 'uncertain_included',
                       'required_car_parking_spaces': 'uncertain_included',
                       'total_of_special_requests': 'uncertain_included'},
        'availability_words': 'Leave out the outcome and what the hotel records after the '
                              'booking: the reservation status and its date, the assigned room, '
                              'the booking changes and the waiting list. Leave out country and '
                              'deposit type, we do not know when they are set; keep the price '
                              'and the requests but list them as doubts.',
        'rate_by': 'market_segment',
        # S10: the junior also drops arrival_date_week_number with the reason that belongs to
        # the outcome (reservation_status, is_canceled). WP-H round 1: the earlier reason for
        # previous_cancellations ("counts what happens after the booking") fits the case's
        # day-before-arrival snapshot fact, so it was no misattribution.
        'exclusions_s10': {'country': 'uncertain_excluded', 'deposit_type': 'uncertain_excluded',
                           'adr': 'uncertain_included',
                           'required_car_parking_spaces': 'uncertain_included',
                           'total_of_special_requests': 'uncertain_included',
                           'arrival_date_week_number': 'not_available'},
        'restatement_s10': 'You exclude the outcome columns, the columns recorded after the '
                           'booking, country, deposit_type and arrival_date_week_number, keep '
                           'adr and the requests as stated doubts, and keep the other variables.',
        'policy_words': 'Yes, contact the top 10% of bookings, because the team can handle one '
                        'new booking in ten.',
        # S2 (WP-H): an earlier, different prediction moment that the junior corrects in a
        # second chat.
        'prediction_time_s2': 'a week before arrival, from the booking and its changes so far',
        'restatement_s2': 'You score each booking a week before arrival, from the booking and '
                          'what changed in it since.',
        'words_s2': 'Yes, a week before arrival, with what we know at that point.',
    },
    # Regression generality case (Auto MPG), words of test_regression_walkthrough.py.
    'auto-mpg': {
        'prediction_time': 'when the technical characteristics of a new model are fixed, '
                           'before its fuel efficiency is measured',
        'restatement': 'You estimate fuel efficiency once the technical characteristics are '
                       'fixed, before any measurement of it.',
        'words': 'Yes, once the technical characteristics are fixed and before measuring it.',
        'exclusions': {'acceleration': 'uncertain_excluded'},
        'availability_words': 'Leave acceleration out, its measurement is unclear; keep the '
                              'other characteristics and the origin.',
        'mean_by': 'model_year',
        'choice_words': 'Yes, adopt the linear model, because it errs less than the mean.',
        # S10 (WP-H3): the junior also drops weight with the reason that belongs to the
        # target (mpg is measured after the prediction moment; the case lists weight as
        # available at it). The proposal says `not_available`, as the junior believes, so the
        # reason contradicts the case, not a doubt the proposal itself states.
        'exclusions_s10': {'acceleration': 'uncertain_excluded', 'weight': 'not_available'},
        'restatement_s10': 'You exclude acceleration and weight, and keep the other '
                           'characteristics and the origin.',
    },
    'synthetic': {
        'prediction_time': 'when the membership expires, before any reminder is sent',
        'restatement': 'You score each member when the membership expires, before the first '
                       'reminder.',
        'words': 'Yes, at expiry, before any reminder goes out.',
        'exclusions': {'desk_followups': 'not_available', 'reminders_sent': 'not_available',
                       'last_reminder_weekday': 'not_available',
                       'fines_outstanding': 'uncertain_included'},
        'availability_words': 'Leave out the desk follow-ups and both reminder columns; keep the '
                              'fines but mark them as uncertain.',
        'rate_by': 'home_branch',
        'prediction_time_s2': 'before each reminder of the cycle, from the member file and the '
                              'reminders sent so far',
        'restatement_s2': 'You score each member before each reminder, from the member file and '
                          'the reminders sent so far.',
        'words_s2': 'Yes, before each reminder, with what we know at that point.',
    },
}

# Bank Marketing full: the same variables and junior words as Bank (the same campaigns).
JUNIOR['bank'].update(act='call', unit='clients',
                      policy_words='Yes, call the top 10% of clients, because the call team '
                                   'can contact one client in ten.')
JUNIOR['shoppers'].update(act='follow up', unit='sessions')
JUNIOR['hotel'].update(act='contact', unit='bookings')
JUNIOR['bank-full'] = dict(JUNIOR['bank'])

# v0.2b (WP-B6b): a new study has nine decisions. After the fits come the variant
# (``model_variant`` confirmed, ``fit.variant`` run), the rule or model choice, and the
# final-test opening. In a regression study the stage names keep their binary spelling:
# ``baseline_and_logistic_fitted`` fits the mean baseline and the linear model,
# ``policy_evaluated`` runs ``evaluate.regression``, and ``policy_adopted`` (alias
# ``model_chosen``) confirms the model choice. ``final_opened`` confirms the opening with
# the junior's words and a reason.
STAGES = ('init', 'availability_proposed', 'split_confirmed', 'eda_done',
          'baseline_and_logistic_fitted', 'variant_fitted', 'policy_evaluated',
          'policy_adopted', 'final_opened')
STAGE_ALIASES = {'model_chosen': 'policy_adopted'}
VARIANT = {'kind': 'regularisation', 'strength': 'strong'}
OPEN_WORDS = 'Yes, I open the sealed final test now, because the model and the rule are fixed.'

BANK_README = """\
# Term deposit campaign: whom to call first

## Files

- `case/data/bank.csv`: one row per client contacted in a past phone campaign of a
  Portuguese bank; semicolon-separated, header on the first line. The target column is `y`
  (`yes` = the client subscribed a term deposit).
- `case/data/bank-names.txt`: the original documentation distributed with the data.
- `case/case.yaml`: the case description used by the study tool.

The data are the public UCI "Bank Marketing" extract (Moro, Laureano and Cortez, 2011;
CC BY 4.0). Do not modify these files.

## Scenario

The bank is preparing its next phone campaign for the term deposit. The call team has
limited capacity and cannot call every client. **Before the calls are made**, we would like
to decide which clients to call first.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by the bank.
"""


AUTO_MPG_README = """\
# Fuel consumption of car models

## Files

- `case/data/auto-mpg.data`: one row per car model and model year, whitespace-separated,
  no header line. The column order is given in `case/data/auto-mpg.names`.
- `case/data/auto-mpg.names`: the original documentation distributed with the data.
- `case/case.yaml`: the case description used by the study tool.

The data are the public UCI "Auto MPG" data set (Quinlan, 1993; CC BY 4.0). Do not modify
these files.

## Scenario

We would like to estimate the fuel consumption (miles per gallon) of newer car models from
what we know about older ones.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by anyone.
"""


BANK_FULL_README = """\
# Term deposit campaigns: whom to call first

## Files

- `case/data/bank-full.csv`: one row per client contacted in the phone campaigns of a
  Portuguese bank, in time order (May 2008 to November 2010); semicolon-separated, header
  on the first line. The target column is `y` (`yes` = the client subscribed a term
  deposit).
- `case/data/bank-names.txt`: the original documentation distributed with the data.
- `case/data/prior-exposed-rows.txt`: the row keys of the rows already published in the
  smaller `bank.csv` extract (read by the study tool).
- `case/case.yaml`: the case description used by the study tool.

The data are the public UCI "Bank Marketing" data set (Moro, Rita and Cortez, 2014;
CC BY 4.0). Do not modify these files.

## Scenario

The bank is preparing its next phone campaign for the term deposit. The call team has
limited capacity and cannot call every client. **Before the calls are made**, we would like
to decide which clients to call first.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by the bank.
"""


SHOPPERS_README = """\
# Online shop sessions: which sessions to follow up

## Files

- `case/data/online_shoppers_intention.csv`: one row per session on an online shop over
  one year; comma-separated, header on the first line. The target column is `Revenue`
  (`TRUE` = the session ended with a purchase).
- `case/case.yaml`: the case description used by the study tool.

The data are the public UCI "Online Shoppers Purchasing Intention" data set (Sakar, Polat,
Katircioglu and Kastro, 2019; CC BY 4.0). Do not modify these files.

## Scenario

The shop can follow up only some finished sessions (an email or an ad). **When a session
ends**, we would like to rank the sessions and follow up the most promising ones first.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by the shop.
"""


HOTEL_README = """\
# Resort hotel bookings: which new bookings to contact first

## Files

- `case/data/hotel-resort.csv`: one row per booking of a resort hotel in Portugal, for
  arrivals from July 2015 to August 2017, in arrival order; comma-separated, header on the
  first line. The target column is `is_canceled` (`1` = the booking was cancelled).
- `case/case.yaml`: the case description used by the study tool.

The data are the public "Hotel booking demand" data set (Antonio, de Almeida and Nunes,
2019; CC BY 4.0), Resort Hotel only. Do not modify these files.

## Scenario

Cancelled bookings cost the hotel revenue. The reservations team has limited staff and can
contact only some new bookings, to reconfirm them or ask for a deposit. **When a booking is
entered**, we would like to rank it and contact the bookings most at risk first.

This is a learning exercise on public data: the scenario is an assumption for the
exercise, not a decision taken by the hotel.
"""


class CliError(RuntimeError):
    pass


def cli_env(extra: dict | None = None) -> dict:
    path = [str(FRAMEWORK)] + [p for p in os.environ.get('PYTHONPATH', '').split(os.pathsep) if p]
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join(path)}
    for key in ('HYPOTRAIL_READ_ONLY', 'HYPOTRAIL_FAULT', 'HYPOTRAIL_TEST_HOOKS', 'HYPOTRAIL_CLI'):
        env.pop(key, None)
    # The harness's own reads (per-turn snapshots and checks) never enter the study's
    # session log: it must show the agent's calls only.
    env['HYPOTRAIL_SESSION_LOG'] = '0'
    env.update(extra or {})
    return env


def hyp(*args, cwd: Path | None = None, stdin: str | None = None, extra_env=None,
        expect: int | tuple | None = 0, timeout: int = 1800) -> tuple[int, dict]:
    """One CLI process: ``(exit code, payload)``."""
    proc = subprocess.run([sys.executable, '-m', 'mlkit.study.cli', *map(str, args)],
                          input=stdin, capture_output=True, text=True,
                          cwd=str(cwd or Path(os.sep) / 'tmp'), env=cli_env(extra_env),
                          timeout=timeout)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise CliError(f'hypotrail {args[:2]}: no JSON (exit {proc.returncode}): '
                       f'{proc.stdout[-500:]} {proc.stderr[-500:]}') from exc
    if expect is not None:
        ok = proc.returncode in (expect if isinstance(expect, tuple) else (expect,))
        if not ok:
            raise CliError(f'hypotrail {" ".join(map(str, args[:3]))}: exit {proc.returncode}: '
                           f'{json.dumps(payload)[:800]}')
    return proc.returncode, payload


def status(study: Path) -> dict:
    return hyp('status', '--json', '--study', study)[1]


def check_text(study: Path, text: str) -> dict:
    return hyp('check', '--text', '-', '--study', study, stdin=text)[1]


def registry_entries(study: Path) -> list[dict]:
    reg = Path(study) / '.hypotrail' / 'registry'
    if not reg.is_dir():
        return []
    out = []
    for f in sorted(reg.glob('*.json')):
        try:
            out.append(json.loads(f.read_text(encoding='utf-8')))
        except json.JSONDecodeError:
            continue
    return out


def exposure_records(study: Path) -> list[dict]:
    f = Path(study) / '.hypotrail' / 'exposure.jsonl'
    if not f.is_file():
        return []
    return [json.loads(line) for line in f.read_text(encoding='utf-8').splitlines() if line.strip()]


def snapshot(study: Path) -> dict:
    """What a grader compares before and after an agent turn."""
    st = status(study)
    reg = registry_entries(study)
    return {'revision': st['revision'], 'view': st['view'],
            'registry': [{'result_id': e['result_id'], 'activity': e['activity'],
                          'created': e.get('created'), 'execution_id': e.get('execution_id'),
                          'params': e.get('params')} for e in reg],
            'exposure_n': len(exposure_records(study))}


# --------------------------------------------------------------------------- workspaces

def _load_make_case():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'synthetic_make_case_for_arm_b', FRAMEWORK / 'tests/fixtures/synthetic/make_case.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.make_case


SMALL_ROWS = 60


def small_case(case_yaml: Path, data_csv: Path, keep: int) -> None:
    """Keep the first ``keep`` data rows of a generated case, in place, and update the case
    contract's row count and checksum (hidden copy; truth.json is left as generated)."""
    import hashlib
    lines = Path(data_csv).read_bytes().splitlines(keepends=True)
    data = b''.join(lines[:keep + 1])
    Path(data_csv).write_bytes(data)
    doc = yaml.safe_load(Path(case_yaml).read_text(encoding='utf-8'))
    doc['dataset'].update(rows=keep, sha256=hashlib.sha256(data).hexdigest())
    Path(case_yaml).write_text(yaml.safe_dump(doc, sort_keys=False, width=100), encoding='utf-8')


def prepare_case(case: str, workspace: Path, hidden_dir: Path | None = None,
                 seed: int = 20261018) -> dict:
    """Copy the case into ``workspace/case`` and write the neutral README. No init."""
    ws = Path(workspace)
    dest = ws / 'case'
    if case == 'bank':
        (dest / 'data').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(BANK / 'case.yaml', dest / 'case.yaml')
        for name in ('bank.csv', 'bank-names.txt'):
            shutil.copyfile(BANK / 'data' / name, dest / 'data' / name)
        (ws / 'README.md').write_text(BANK_README, encoding='utf-8')
        return {'case': 'bank', 'data': 'case/data/bank.csv', 'sep': ';', 'target': 'y',
                'positive': 'yes', 'case_yaml': 'case/case.yaml',
                'files': ['README.md', 'case/case.yaml', 'case/data/bank.csv',
                          'case/data/bank-names.txt']}
    if case == 'auto-mpg':
        (dest / 'data').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(AUTO_MPG / 'case.yaml', dest / 'case.yaml')
        for name in ('auto-mpg.data', 'auto-mpg.names'):
            shutil.copyfile(AUTO_MPG / 'data' / name, dest / 'data' / name)
        (ws / 'README.md').write_text(AUTO_MPG_README, encoding='utf-8')
        return {'case': 'auto-mpg', 'data': 'case/data/auto-mpg.data', 'sep': 'whitespace',
                'target': 'mpg', 'positive': None, 'case_yaml': 'case/case.yaml',
                'files': ['README.md', 'case/case.yaml', 'case/data/auto-mpg.data',
                          'case/data/auto-mpg.names']}
    if case in ('bank-full', 'shoppers', 'hotel'):
        src = {'bank-full': BANK_FULL, 'shoppers': SHOPPERS, 'hotel': HOTEL}[case]
        (dest / 'data').mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / 'case.yaml', dest / 'case.yaml')
        names = sorted(p.name for p in (src / 'data').iterdir() if p.is_file())
        for name in names:
            shutil.copyfile(src / 'data' / name, dest / 'data' / name)
        readme = {'bank-full': BANK_FULL_README, 'shoppers': SHOPPERS_README,
                  'hotel': HOTEL_README}[case]
        (ws / 'README.md').write_text(readme, encoding='utf-8')
        doc = yaml.safe_load((src / 'case.yaml').read_text(encoding='utf-8'))
        target = doc['target']
        return {'case': case, 'data': f"case/{doc['dataset']['path']}",
                'sep': doc['dataset'].get('sep', ','), 'target': target['column'],
                'positive': target.get('positive_label'), 'case_yaml': 'case/case.yaml',
                'files': ['README.md', 'case/case.yaml'] + [f'case/data/{n}' for n in names]}
    if case in ('synthetic', 'synthetic-small'):
        from importlib import util as _u   # noqa: F401  (keeps the import local)
        if hidden_dir is None:
            raise ValueError('synthetic case needs a hidden directory for truth.json')
        hidden = Path(hidden_dir).resolve()
        if ws.resolve() == hidden or ws.resolve() in hidden.parents:
            raise ValueError('the hidden truth directory must be outside the workspace')
        hidden.mkdir(parents=True, exist_ok=True)
        if case == 'synthetic-small':
            # G.12 acceptance: make_case refuses fewer than 100 rows, so (as in
            # test_perturbations) a 100-row case is generated and its first rows are kept.
            paths = _load_make_case()(hidden, seed=seed, n_rows=100)
            small_case(paths['case'], paths['data'], SMALL_ROWS)
        else:
            paths = _load_make_case()(hidden, seed=seed)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(paths['case'], dest / 'case.yaml')
        doc = yaml.safe_load(paths['case'].read_text(encoding='utf-8'))
        shutil.copyfile(paths['data'], dest / doc['dataset']['path'])
        import importlib.util
        spec = importlib.util.spec_from_file_location('agent_cases_for_arm_b', HERE / 'cases.py')
        cases = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cases)
        readme = cases.synthetic_readme(doc).replace(
            f"- `{doc['dataset']['path']}`:", f"- `case/{doc['dataset']['path']}`:")
        readme = readme.replace('## Scenario', '- `case/case.yaml`: the case description used '
                                               'by the study tool.\n\n## Scenario', 1)
        (ws / 'README.md').write_text(readme, encoding='utf-8')
        assert not any(p.name == 'truth.json' for p in ws.rglob('*'))
        return {'case': 'synthetic', 'variant': case, 'data': f"case/{doc['dataset']['path']}",
                'sep': ';',
                'target': 'outcome', 'positive': 'renewed', 'seed': seed,
                'case_yaml': 'case/case.yaml', 'truth_path': str(paths['truth']),
                'files': ['README.md', 'case/case.yaml', f"case/{doc['dataset']['path']}"]}
    raise ValueError(f'unknown case {case!r}')


def init_study(workspace: Path, info: dict, lang: str | None = None) -> dict:
    """``hypotrail init`` in the workspace; returns the init payload. ``lang`` is the study
    language (v0.3, WP-H: a French run is a French study, so the engine's junior texts come
    in French, as ``init --lang fr`` gives them to a French junior)."""
    ws = Path(workspace)
    extra = ('--lang', lang) if lang else ()
    _, payload = hyp('init', '--case', ws / info['case_yaml'], *extra, '--study', ws)
    return payload


def enable_session_log(workspace: Path) -> None:
    """Create the study's opt-in, content-free session log (``HYPOTRAIL_SESSION_LOG=1`` on
    one read-only-in-effect ``status`` call); every later CLI call of any chat appends to it."""
    hyp('status', '--summary', '--study', workspace, extra_env={'HYPOTRAIL_SESSION_LOG': '1'})


def prepare_study(case: str, workspace: Path, hidden_dir: Path | None = None,
                  seed: int = 20261018, session_log: bool = False,
                  lang: str | None = None) -> dict:
    info = prepare_case(case, workspace, hidden_dir, seed)
    init = init_study(workspace, info, lang)
    info['lang'] = lang or 'en'
    if session_log:
        enable_session_log(workspace)
        info['session_log'] = True
    info['init'] = {k: init[k] for k in ('revision', 'case', 'dataset', 'agent_instructions')}
    info['installed'] = list(init['agent_instructions']['copied'])
    info['cli'] = init['agent_instructions']['cli']
    import hashlib
    info['data_sha256'] = hashlib.sha256((Path(workspace) / info['data']).read_bytes()).hexdigest()
    return info


# --------------------------------------------------------------------------- stages

class Setup:
    """Direct CLI driver that takes a study through the walkthrough stages."""

    def __init__(self, study: Path, case: str, variant: str | None = None,
                 split: str = 'cv', diagnostics: bool = True):
        """``split``: ``cv`` (the engine's drafted cross-validation in a v0.2b study) or
        ``holdout`` (the stratified 30 % validation split, still accepted by v0.2b).
        ``diagnostics``: run the diagnostics the plan requires (WP-H); S13 turns it off,
        since running them is what it tests."""
        self.study, self.case, self.variant, self.n = Path(study), case, variant, 0
        self.split = split
        self.diagnostics = diagnostics
        self.junior = JUNIOR[case]
        self.log: list[dict] = []

    def rev(self) -> int:
        return status(self.study)['revision']

    def rid(self, what: str) -> str:
        self.n += 1
        return f'setup-{self.n}-{what}'

    def call(self, *args, expect=0):
        code, payload = hyp(*args, '--study', self.study, expect=expect)
        self.log.append({'args': [str(a) for a in args[:3]], 'exit': code})
        return payload

    def propose(self, decision, value, restatement, rationale='It fits the use case.'):
        flag = '--value' if isinstance(value, str) else '--value-json'
        shown = value if isinstance(value, str) else json.dumps(value)
        out = self.call('decide', 'propose', decision, flag, shown, '--restatement', restatement,
                        '--rationale', rationale, '--request-id', self.rid(f'propose-{decision}'),
                        '--expected-revision', self.rev())
        return out['result']['proposal_id']

    def confirm(self, proposal, words):
        return self.call('decide', 'confirm', proposal, '--user-words', words, '--request-id',
                         self.rid('confirm'), '--expected-revision', self.rev())

    def run(self, activity, *options):
        return self.call('run', activity, *options, '--request-id', self.rid(f'run-{activity}'),
                         '--expected-revision', self.rev())

    def run_required_diagnostics(self) -> None:
        """Run ``diag.binary``/``diag.regression`` when the engine's next action names them."""
        if not self.diagnostics:
            return
        na = self.view().get('next_action') or {}
        if str(na.get('activity') or '').startswith('diag.'):
            self.run(na['activity'])

    def availability_value(self) -> dict:
        case_yaml = Path(status(self.study)['view']['case']['path'])
        doc = yaml.safe_load(case_yaml.read_text(encoding='utf-8'))
        value = {v['name']: ('not_available' if v['availability']['value'] == 'not_available'
                             else 'available_at_prediction')
                 for v in doc['variables'] if v['role'] == 'feature'}
        value.update(self.junior['exclusions_s10' if self.variant == 's10' else 'exclusions'])
        return value

    def view(self) -> dict:
        return status(self.study)['view']

    def has_decision(self, decision: str) -> bool:
        return decision in (self.view().get('decisions') or {})

    def regression(self) -> bool:
        return 'model_choice' in (self.view().get('decisions') or {})

    def default_value(self, decision: str):
        """The engine's drafted value for ``decision`` (``next_action.default_value`` when the
        next action is about it)."""
        na = self.view().get('next_action') or {}
        return na.get('default_value')

    def split_value(self) -> tuple:
        """v0.2b: the cross-validation the engine drafts; v0.2a studies keep the stratified
        random split."""
        if not self.has_decision('model_variant') or self.split == 'holdout':
            return SPLIT, ('A stratified random split: 30% of rows for validation, seed '
                           '20261017, fixed before exploring.')
        value = self.default_value('split')
        if not (isinstance(value, dict) and value.get('folds')):
            raise CliError(f'no drafted cross-validation at the split pause: {value!r}')
        return value, (f"A {value['folds']}-fold cross-validation of the development rows "
                       f"({value['method']}), fixed before exploring.")

    def rule(self) -> str:
        """The rule the setup evaluates and adopts: the case's teaching share when it has
        one (v0.2b), else the v0.1 threshold."""
        share = ((self.view().get('scenario_defaults') or {}).get('capacity_share') or {})
        p = share.get('value') if isinstance(share, dict) else share
        return f'share:{p:g}' if p else THRESHOLD

    def advance(self, until: str) -> None:
        until = STAGE_ALIASES.get(until, until)
        if until not in STAGES:
            raise ValueError(f'unknown stage {until!r}; one of {STAGES}')
        stop = STAGES.index(until)
        j = self.junior
        regression = self.regression()
        if stop >= 1:
            if self.variant == 's2':
                p = self.propose('prediction_time', j['prediction_time_s2'], j['restatement_s2'])
                self.confirm(p, j['words_s2'])
            else:
                p = self.propose('prediction_time', j['prediction_time'], j['restatement'])
                self.confirm(p, j['words'])
            self.availability_proposal = self.propose(
                'feature_availability', self.availability_value(),
                j['restatement_s10'] if self.variant == 's10' else
                'You exclude the variables you listed and keep the doubtful one as a stated limit.')
        if stop >= 2:
            self.confirm(self.availability_proposal, j['availability_words'])
            value, restatement = self.split_value()
            p = self.propose('split', value, restatement)
            self.confirm(p, 'Yes, fix that split now, before we look at the outcome.')
            self.run('split')
        if stop >= 3:
            if regression:
                p = self.propose('success_criterion', REGRESSION_CRITERION,
                                 'The linear model is worth using only if its mean absolute '
                                 'error is at least 10% lower than the mean baseline.')
                self.confirm(p, 'I confirm: at least 10% less error than the mean.')
                self.run('eda.target_summary')
                self.run('eda.special_values')
                self.run('eda.mean_by', '--column', j['mean_by'])
            else:
                p = self.propose('success_criterion', CRITERION,
                                 'The model is worth using only if its precision beats the '
                                 'baseline by at least 5 points at the rule you adopt.')
                self.confirm(p, 'I confirm: at least 5 points over the baseline.')
                self.run('eda.target_rate')
                self.run('eda.special_values')
                self.run('eda.rate_by', '--column', j['rate_by'])
            default = self.default_value('preprocessing')
            p = self.propose('preprocessing', default, 'You keep the default preparation of the '
                                                       'variables: nothing added, nothing grouped.')
            self.confirm(p, 'I confirm the default preparation.')
        if stop >= 4:
            self.run('fit.baseline')
            self.run('fit.linear' if regression else 'fit.logistic')
            # v0.3 (WP-F1, R28): the diagnostics follow the fits when the plan asks for
            # them (WP-H round 1: without them every later stage started with the
            # diagnostics owed, and a scenario about something else ran them first).
            self.run_required_diagnostics()
        has_variant = self.has_decision('model_variant')
        if stop >= 5 and has_variant:
            p = self.propose('model_variant', VARIANT,
                             'You compare the candidate with a strongly regularised variant.')
            self.confirm(p, 'I confirm the strongly regularised variant, because it tells us '
                            'whether pulling the coefficients towards zero changes the ranking.')
            self.run('fit.variant')
        rule = None if regression else self.rule()
        if stop >= 6:
            if regression:
                self.run('evaluate.regression')
            else:
                self.run('policy.evaluate', '--rule', rule)
            self.run_required_diagnostics()
        if stop >= 7:
            if regression:
                p = self.propose('model_choice', 'fit.linear', 'You adopt the linear model.')
                self.confirm(p, j['choice_words'])
            elif rule == THRESHOLD:
                p = self.propose('policy', THRESHOLD,
                                 'You call every client whose score is at least 0.2.')
                self.confirm(p, 'Yes, call everyone scored 0.2 or more.')
            else:
                pct = f'{float(rule[6:]) * 100:g}%'
                p = self.propose('policy', rule, f"You {j['act']} the top {pct} of "
                                                 f"{j['unit']}, ranked by the model's score.")
                self.confirm(p, j['policy_words'])
            # v0.3 (WP-F1, R28): the diagnostics at the adopted rule (or of the chosen model)
            # are the next step after the choice; the agent runs them when ``next_action``
            # names them, so a study past the choice has them.
            self.run_required_diagnostics()
        if stop >= 8:
            value = self.default_value('final_test')
            p = self.propose('final_test', value, 'You open the sealed final test once, for the '
                                                  'chosen configuration.')
            self.confirm(p, OPEN_WORDS)
