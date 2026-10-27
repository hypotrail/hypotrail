"""Hand-built payloads of contract P1 (CLI-CONTRACT §17) for the one-page panel.

The engine side of ADR 0004 decision 13 (PANEL-ONE-PAGE-PLAN E-1 to E-7) lands in
parallel. Until E-8 recaptures the companion's payloads with the P1 keys, the panel is built
and tested on these five states of the approved mockup (docs/plans/mockups/
panel-synthesis-fr.html), on the captured Auto MPG study (``../captured/summary.regression``
and ``../captured/data.regression``):

    summary.step1     step 1, the data card and its seeded sample (`show_data_card`)
    summary.choice    the model choice asked as a choice (R16), the criterion per configuration
    summary.reopened  the preparation to confirm again, the models stale, a variant run interrupted
    summary.review    the review of an `init --automation until_final_test` study
    summary.done      the end: the final test opened once, the conclusion confirmed
    data.regression   `data --json` with the sample (§17.3) and the special-value rows (§17.4)

Every P1 key follows §17.2 to §17.4 in its order; the numbers are the captured study's
where it has them (the mean baseline 10.27 mpg, the linear model 6.48, the variant 6.51)
and illustrative elsewhere (the sample's rows are the mockup's real draw). Run

    python3 clients/vscode-companion/test/fixtures/p1/build.py

to rewrite the JSON files. E-8 replaces this folder by captures; delete it then.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAPTURED = HERE.parent / 'captured'
NOTE = 'Hand-built for contract P1 (CLI-CONTRACT §17) until the engine recapture (PANEL-ONE-PAGE-PLAN E-8).'

BASE = json.loads((CAPTURED / 'summary.regression.json').read_text(encoding='utf-8'))['payload']
DATA = json.loads((CAPTURED / 'data.regression.json').read_text(encoding='utf-8'))['payload']
PLAN = [s['id'] for s in BASE['plan']]
RID = {slot: r['result_id'] for slot, r in BASE['results'].items()}

SAMPLE_NOTE = {
    'en': ("These eight rows' target values were shown at step 1, before the split. They stay counted as seen: "
           'with cross-validation they later fall in validation folds; with a holdout split, those in the '
           'validation rows were seen before.'),
    'fr': ("Les valeurs de la cible de ces huit lignes ont été montrées à l'étape 1, avant le découpage. Elles "
           'restent comptées comme vues : avec la validation croisée, elles tombent ensuite dans des blocs de '
           'validation ; avec un échantillon réservé, celles qui sont dans la validation ont été vues avant.'),
}
SEED = '5f0c2a9e41d7b3a6'
SAMPLE_KEYS = ['L34', 'L69', 'L85', 'L100', 'L122', 'L123', 'L267', 'L384']

HEADLINES = {
    'en': {
        'discover_data': '318 development rows and 9 columns; 80 rows set aside as the final test.',
        'prediction_time': 'When the technical characteristics of a new model are fixed.',
        'feature_availability': 'Every column except acceleration, whose availability is uncertain.',
        'split': 'Validation from model year 79: 239 rows to train, 79 to validate.',
        'success_criterion': 'At least 10% less error than the mean baseline.',
        'structural_eda': '6 rows of horsepower hold "?", read as missing.',
        'preprocessing': 'The default: no indicator, every category kept, no cap, no transform.',
        'train_eda': '4 charts on the target, on the training rows.',
        'models': 'Linear model 6.48 mpg of average error, against 10.27 for the mean baseline.',
        'model_variant': 'A stronger regularisation: 6.51 mpg of average error.',
        'model_choice': 'The linear model.',
        'final_test': 'Opened once: 3.82 mpg of average error on the 80 rows set aside.',
        'conclusion': 'Adopt the linear model, within the limits of the study.',
    },
    'fr': {
        'discover_data': '318 lignes de développement et 9 colonnes ; 80 lignes mises de côté pour le test final.',
        'prediction_time': 'Quand les caractéristiques techniques d’un nouveau modèle sont fixées.',
        'feature_availability': 'Toutes les colonnes sauf acceleration, dont la disponibilité est incertaine.',
        'split': 'Validation à partir de l’année 79 : 239 lignes pour entraîner, 79 pour valider.',
        'success_criterion': 'Au moins 10 % d’erreur en moins que la moyenne de référence.',
        'structural_eda': '6 lignes de horsepower contiennent « ? », lu comme manquant.',
        'preprocessing': 'Par défaut : pas d’indicateur, toutes les catégories gardées, pas de plafond, pas de transformation.',
        'train_eda': '4 graphiques sur la cible, sur les lignes d’entraînement.',
        'models': 'Modèle linéaire : 6,48 mpg d’erreur moyenne, contre 10,27 pour la moyenne de référence.',
        'model_variant': 'Une régularisation plus forte : 6,51 mpg d’erreur moyenne.',
        'model_choice': 'Le modèle linéaire.',
        'final_test': 'Ouvert une fois : 3,82 mpg d’erreur moyenne sur les 80 lignes mises de côté.',
        'conclusion': 'Adopter le modèle linéaire, dans les limites de l’étude.',
    },
}
HEADLINE_RESULTS = {
    'split': ['split'], 'structural_eda': ['eda.quality'],
    'train_eda': ['eda.target_summary', 'eda.mean_by:model_year', 'eda.distribution:weight', 'eda.correlation'],
    'models': ['evaluate.regression'], 'model_variant': ['evaluate.regression'],
}


def texts_base(summary: dict) -> dict:
    out = copy.deepcopy(summary['texts'])
    for lang in ('en', 'fr'):
        for key in ('question', 'options', 'options_note', 'junior_digest', 'headlines', 'data_contingent', 'sample_note'):
            out[lang].pop(key, None)
    return out


def set_texts(s: dict, *, question, options, note, digest, done_steps, contingent=None, sample=True):
    texts = texts_base(BASE)
    for lang in ('en', 'fr'):
        t = texts[lang]
        t['question'] = question[lang] if question else None
        t['options'] = dict(options[lang]) if options else {}
        t['options_note'] = note[lang] if note else None
        t['junior_digest'] = digest[lang] if digest else None
        t['headlines'] = {k: HEADLINES[lang][k] for k in PLAN if k in done_steps}
        t['data_contingent'] = {pid: text[lang] for pid, text in (contingent or {}).items()}
        t['sample_note'] = SAMPLE_NOTE[lang] if sample else None
    s['texts'] = texts


def headlines(done_steps, basis):
    out = {}
    for step in PLAN:
        if step not in done_steps:
            continue
        decision = step if step in BASE['decisions'] else None
        results = [RID[x] for x in HEADLINE_RESULTS.get(step, []) if x in RID]
        out[step] = {'decision_id': decision, 'basis': basis.get(step) if decision else None, 'results': results}
    return out


def plan_status(done_upto: int, statuses: dict | None = None) -> list:
    out = []
    for i, s in enumerate(BASE['plan']):
        status = 'done' if i < done_upto else ('ready' if i == done_upto else 'blocked')
        out.append({'id': s['id'], 'title': s['title'], 'status': (statuses or {}).get(s['id'], status)})
    return out


def append_p1(s: dict, **keys) -> dict:
    """The P1 keys after `texts`, in the order of §17.2."""
    order = ['panel_contract', 'automation', 'review_queue', 'defensibility', 'ledger', 'sample', 'headlines',
             'criterion_configurations']
    for k in order:
        s[k] = keys.get(k)
    return s


def results_with_channel(results: dict, channel='chat', stale=(), stale_reason=None) -> dict:
    out = {}
    for slot, r in results.items():
        r = dict(r)
        if slot in stale:
            r['current'] = False
            r['stale_reason'] = stale_reason
        r['channel'] = channel(slot) if callable(channel) else channel
        out[slot] = r
    return out


def proposals_with_contingent(props, value=False):
    out = []
    for p in props:
        q = {}
        for k, v in p.items():
            q[k] = v
            if k == 'origin':
                q['data_contingent'] = value
        out.append(q)
    return out


def defensibility(kind, items):
    count = sum(1 for _, sev in items if sev == 'caveat') if kind == 'limits' else sum(1 for _, sev in items if sev != 'context')
    return {'kind': kind, 'count': count, 'items': [{'id': i, 'severity': s} for i, s in items]}


def ledger(openings=0, eda=4, sample=1, tried=2, reference=True):
    return {'final_test': {'openings': openings, 'max': 1}, 'target_looks': {'eda': eda, 'sample': sample, 'total': eda + sample},
            'configurations': {'tried': tried, 'reference': reference}}


SAMPLE = {'seed': SEED, 'row_keys': SAMPLE_KEYS, 'recorded': True}


def criterion_configs(judged_final=False):
    base_mae = 10.27
    bound = round(0.9 * base_mae, 4)
    linear = {'slot': 'fit.linear', 'value': 6.48, 'result_id': RID['evaluate.regression'], 'path': 'models.[fit.linear].mae',
              'point_meets_bound': True, 'gain': 0.3693, 'low': 0.3077, 'high': 0.4261, 'status': 'met',
              'judged_on': 'development'}
    variant = {'slot': 'fit.variant', 'value': 6.51, 'result_id': RID['evaluate.regression'], 'path': 'models.[fit.variant].mae',
               'point_meets_bound': True, 'gain': None, 'low': None, 'high': None, 'status': 'not_assessed',
               'judged_on': 'development'}
    baseline = {'slot': 'fit.baseline', 'value': base_mae, 'result_id': RID['evaluate.regression'],
                'path': 'models.[fit.baseline].mae', 'point_meets_bound': False, 'gain': None, 'low': None, 'high': None,
                'status': 'not_assessed', 'judged_on': 'development'}
    if judged_final:
        linear = dict(linear, value=3.82, gain=0.4845, low=0.3910, high=0.5702, status='met', judged_on='final_test',
                      result_id='9' * 64, path='models.[fit.linear].mae')
    return {'metric': 'mae_reduction', 'unit': 'mpg',
            'bound': {'value': bound, 'reference': base_mae, 'minimum': 0.1, 'result_id': RID['evaluate.regression'],
                      'path': 'models.[fit.baseline].mae'},
            'configurations': [linear, variant, baseline]}


def pause(kind, step, revision, options, labels, question, recommended=None, proposal=None):
    return {'schema': 'hypotrail.pause/1', 'kind': kind, 'language': 'en', 'revision': revision,
            'position': {'step_id': step, 'completed': PLAN.index(step), 'total': len(PLAN)}, 'learned': [], 'limitations': [],
            'proposal_id': proposal['proposal_id'] if proposal else None,
            'proposal_text': proposal['restatement'] if proposal else None, 'recommended_option': recommended,
            'options': list(options), 'option_labels': dict(labels), 'question': question, 'evidence_refs': [],
            'detail_topics': []}


def next_action(**fields):
    keys = ['kind', 'step', 'proposal_id', 'decision', 'message', 'audience', 'junior_message', 'language', 'recommended',
            'question', 'junior_digest', 'choice_options', 'review', 'after_study', 'pause']
    return {k: fields[k] for k in keys if k in fields}


def summary(revision: int, plan_done: int, **over) -> dict:
    s = copy.deepcopy(BASE)
    s['revision'] = revision
    s['plan'] = plan_status(plan_done, over.pop('statuses', None))
    s['current_step'] = over.pop('current_step', PLAN[min(plan_done, len(PLAN) - 1)])
    for k, v in over.items():
        s[k] = v
    s['currency'] = f'{revision:016x}'
    return s


def nyd(ids_texts, more=('no_causality', 'workbench_not_tracked')):
    return {'top': [{'id': i, 'text': t, 'audience': 'junior', 'junior_text': None} for i, t in ids_texts], 'more': list(more)}


LIMIT_TEXTS = {
    'unconfirmed_decisions': ('Not confirmed by you yet: the framing decisions, the model choice, the opening of the final test '
                              'and the conclusion.', 'Pas encore confirmées par vous : les décisions de cadrage, le choix du modèle, '
                              'l’ouverture du test final et la conclusion.'),
    'final_test_sealed': ('The final test is still sealed: every figure so far is development evidence.',
                          'Le test final est encore scellé : tout chiffre jusqu’ici est une preuve de développement.'),
    'validation_is_not_independent': ('Validation rows are used to compare the models and to choose one, so validation errors '
                                      'are not independent evidence of future error.',
                                      'Les lignes de validation servent à comparer les modèles et à en choisir un : leurs erreurs '
                                      'ne sont pas une preuve indépendante de l’erreur future.'),
    'public_data_already_explored': ('The data were explored or published before this study; its rows are not unseen.',
                                     'Les données ont été explorées ou publiées avant cette étude ; leurs lignes ne sont pas inédites.'),
    'stale_results': ('Some results are out of date and are computed again before they are cited.',
                      'Certains résultats sont périmés et sont recalculés avant d’être cités.'),
    'interrupted_executions': ('A run of the variants stopped before it finished; its outcome is unknown.',
                               'Un calcul des variantes s’est arrêté avant la fin ; son issue est inconnue.'),
    'automatic_decisions_to_review': ('7 decisions were recorded by the automatic mode: review each one in the chat.',
                                      '7 décisions ont été enregistrées par le mode automatique : relisez chacune dans le chat.'),
    'no_causality': ('Associations in observational data do not show that acting on a variable would change the outcome.',
                     'Une association dans des données d’observation ne montre pas qu’agir sur une variable changerait le résultat.'),
    'workbench_not_tracked': ('Experiments in the notebook workbench are not recorded and are not decisions.',
                              'Les essais de l’atelier ne sont pas enregistrés et ne sont pas des décisions.'),
    'grouped_split_unsupported': ('Rows that share a value of car_name can fall in both partitions.',
                                  'Des lignes qui partagent une valeur de car_name peuvent tomber dans les deux parties.'),
    'reopened_decision': ('The preparation must be confirmed again: the declared range of horsepower changed.',
                          'La préparation est à confirmer de nouveau : la plage déclarée de horsepower a changé.'),
}


def limits_texts(s: dict, ids):
    for lang, n in (('en', 0), ('fr', 1)):
        s['texts'][lang]['limits'] = {i: LIMIT_TEXTS[i][n] for i in ids if i in LIMIT_TEXTS}


def artifacts(status='ok', revision=38):
    items = copy.deepcopy(BASE['artifacts']['items'])
    for name in ('report', 'notebook'):
        items[name]['status'] = status
        items[name]['revision'] = revision
        if status == 'stale':
            items[name]['junior_message'] = ('The report is out of date: it dates from an earlier revision.' if name == 'report'
                                             else 'The generated notebook is out of date.')
    return {'status': 'stale' if status == 'stale' else 'ok', 'items': items}


def decisions_upto(step_ids, basis='restated'):
    d = copy.deepcopy(BASE['decisions'])
    for k, v in d.items():
        if k in step_ids:
            v['status'] = 'confirmed'
            v['basis'] = basis
            if basis == 'automatic':
                v['user_words'] = None
            if k == 'model_choice':
                v['value'] = 'fit.linear'
                v['open_proposals'] = []
        else:
            v.update({'status': 'open', 'value': None, 'basis': None, 'user_words': None, 'open_proposals': []})
    return d


def wrap(payload, argv, note=NOTE):
    return {'about': {'schema': payload['schema'], 'task': 'regression', 'exit_code': 0, 'source': 'hand-authored',
                      'argv': argv, 'note': note}, 'payload': payload}


ARGV = ['status', '--summary', '--digest', '--json']


def step1():
    s = summary(1, 0, current_step='discover_data', open_proposals=[], results={}, notes=[], holds=[],
                decisions=decisions_upto([]), criterion=None, eda_looks={'target_looks': 0, 'results': []},
                trials={'count': 0}, artifacts=artifacts('ok', 1))
    q = {'en': 'Do these data describe what you want to predict, the fuel efficiency of a car in mpg?',
         'fr': 'Ces données décrivent-elles ce que vous voulez prédire, la consommation d’une voiture en mpg ?'}
    opts = {'en': [('continue', 'Yes, continue'), ('surprised', 'A column surprises me')],
            'fr': [('continue', 'Oui, on continue'), ('surprised', 'Une colonne m’étonne')]}
    s['next_action'] = next_action(kind='show_data_card', step='discover_data', message='Show the data card.', audience='agent',
                                   junior_message='Read the data card: what one row is, the columns, and a sample of rows.',
                                   language='en', recommended=None, question=q['en'], junior_digest=None,
                                   pause=pause('data_card', 'discover_data', 1, [k for k, _ in opts['en']], dict(opts['en']), q['en']))
    s['digest'] = {'since': 1, 'until': 1, 'items': [], 'truncated': False, 'counts': {}}
    s['last_session'] = {'boundary_revision': 1, 'boundary_time': '2026-10-27T09:00:00+00:00', 'gap_minutes': None}
    s['not_yet_defensible'] = nyd([(i, LIMIT_TEXTS[i][0]) for i in ('unconfirmed_decisions', 'final_test_sealed',
                                                                    'public_data_already_explored', 'grouped_split_unsupported')])
    set_texts(s, question=q, options=opts, note=None, digest=None, done_steps=[])
    limits_texts(s, ['unconfirmed_decisions', 'final_test_sealed', 'public_data_already_explored', 'grouped_split_unsupported',
                     'no_causality', 'workbench_not_tracked'])
    s['texts']['en']['next_action'] = s['next_action']['junior_message']
    s['texts']['fr']['next_action'] = 'Lisez la fiche des données : ce qu’est une ligne, les colonnes et un échantillon de lignes.'
    append_p1(s, panel_contract=2, automation=None, review_queue=None,
              defensibility=defensibility('pending', [('unconfirmed_decisions', 'not_final'), ('final_test_sealed', 'not_final'),
                                                      ('public_data_already_explored', 'context'),
                                                      ('grouped_split_unsupported', 'caveat'), ('no_causality', 'context'),
                                                      ('workbench_not_tracked', 'context')]),
              ledger=ledger(eda=0, sample=1, tried=0, reference=False), sample=SAMPLE, headlines={},
              criterion_configurations=None)
    return wrap(s, ARGV, NOTE + ' Step 1: the data card and its seeded sample.')


DONE_TO_CHOICE = PLAN[:10]


def choice():
    s = summary(38, 10, current_step='model_choice', open_proposals=[], decisions=decisions_upto(DONE_TO_CHOICE),
                results=results_with_channel(BASE['results'],
                                             channel=lambda slot: 'webview' if slot == 'eda.mean_by:model_year' else 'chat'))
    q = {'en': 'Which configuration do you keep?', 'fr': 'Quelle configuration gardez-vous ?'}
    opts = {'en': [('fit.linear', 'the linear model'), ('fit.variant', 'the variant with a stronger regularisation')],
            'fr': [('fit.linear', 'le modèle linéaire'), ('fit.variant', 'la variante avec une régularisation plus forte')]}
    note = {'en': 'From the simplest to the most flexible; the order is not a recommendation.',
            'fr': 'Du plus simple au plus souple ; l’ordre n’est pas une recommandation.'}
    choice_options = [{'id': k, 'value': k, 'label': v} for k, v in opts['en']]
    s['next_action'] = next_action(kind='propose', step='model_choice', decision='model_choice',
                                   message='Ask which configuration to keep.', audience='agent',
                                   junior_message='Choose the model in the chat: say which configuration you keep and why.',
                                   language='en', recommended=None, question=q['en'],
                                   junior_digest=None, choice_options=choice_options,
                                   pause=pause('choice', 'model_choice', 38, [k for k, _ in opts['en']], dict(opts['en']), q['en']))
    s['not_yet_defensible'] = nyd([(i, LIMIT_TEXTS[i][0]) for i in ('unconfirmed_decisions', 'validation_is_not_independent',
                                                                    'final_test_sealed', 'public_data_already_explored')])
    set_texts(s, question=q, options=opts, note=note, digest=None, done_steps=DONE_TO_CHOICE)
    for lang, ch in (('en', opts['en']), ('fr', opts['fr'])):
        s['texts'][lang]['choice_options'] = dict(ch)
    limits_texts(s, ['unconfirmed_decisions', 'validation_is_not_independent', 'final_test_sealed',
                     'public_data_already_explored', 'no_causality', 'workbench_not_tracked'])
    s['texts']['en']['next_action'] = s['next_action']['junior_message']
    s['texts']['fr']['next_action'] = 'Choisissez le modèle dans le chat : dites quelle configuration vous gardez et pourquoi.'
    s['texts']['en']['recap'][4] = ('Limit: Validation rows are used to compare the models and to choose one, so validation '
                                    'errors are not independent evidence of future error.')
    s['texts']['fr']['recap'] = list(s['texts']['fr']['recap'])
    if len(s['texts']['fr']['recap']) >= 5:
        s['texts']['fr']['recap'][4] = ('Limite : les lignes de validation servent à comparer les modèles et à en choisir un ; '
                                        'leurs erreurs ne sont pas une preuve indépendante de l’erreur future.')
    append_p1(s, panel_contract=2, automation=None, review_queue=None,
              defensibility=defensibility('pending', [('unconfirmed_decisions', 'not_final'),
                                                      ('validation_is_not_independent', 'caveat'),
                                                      ('final_test_sealed', 'not_final'),
                                                      ('public_data_already_explored', 'context'),
                                                      ('no_causality', 'context'), ('workbench_not_tracked', 'context')]),
              ledger=ledger(), sample=SAMPLE,
              headlines=headlines(DONE_TO_CHOICE, {k: 'restated' for k in PLAN}),
              criterion_configurations=criterion_configs())
    return wrap(s, ARGV, NOTE + ' The model choice asked as a choice; a chart requested from the panel.')


def reopened():
    statuses = {'preprocessing': 'needs_reconfirmation', 'train_eda': 'done', 'models': 'done', 'model_variant': 'done'}
    stale = ('fit.baseline', 'fit.linear', 'fit.variant', 'evaluate.regression')
    decisions = decisions_upto(DONE_TO_CHOICE)
    decisions['preprocessing']['status'] = 'reconfirm_required'
    proposal = {'proposal_id': 'p_8', 'decision_id': 'preprocessing', 'value': BASE['decisions']['preprocessing']['value'],
                'restatement': 'Keep the default preparation: no indicator, every category kept, no cap, no transform.',
                'revision': 40, 'origin': {'channel': 'chat'}}
    decisions['preprocessing']['open_proposals'] = ['p_8']
    s = summary(40, 10, statuses=statuses, current_step='preprocessing', open_proposals=proposals_with_contingent([proposal]),
                decisions=decisions, artifacts=artifacts('stale', 38),
                results=results_with_channel(BASE['results'], stale=stale, stale_reason='computed with the earlier preparation'))
    s['executions'] = {'active': [], 'interrupted': [{'execution_id': 'e_12', 'activity': 'fit.variant',
                                                      'reason': 'The process stopped before it wrote its result.',
                                                      'liveness': 'dead', 'result_id': None}],
                       'late': [], 'suspected_interrupted': []}
    q = {'en': 'Preparation: do you confirm again "keep the default preparation", or do you change it?',
         'fr': 'Préparation : confirmez-vous de nouveau « garder la préparation par défaut », ou la changez-vous ?'}
    opts = {'en': [('confirm', 'I confirm it again'), ('change', 'Change something')],
            'fr': [('confirm', 'Je confirme de nouveau'), ('change', 'Je change')]}
    s['next_action'] = next_action(kind='reconfirm', proposal_id='p_8', decision='preprocessing',
                                   message='The preparation needs the junior\'s words again.', audience='agent',
                                   junior_message='The declared range of horsepower changed and the preparation depended on it: '
                                                  'confirm it again or change it, in the chat.',
                                   language='en', recommended=None, question=q['en'], junior_digest=None,
                                   pause=pause('decision', 'preprocessing', 40, [k for k, _ in opts['en']], dict(opts['en']),
                                               q['en'], proposal=proposal))
    s['not_yet_defensible'] = nyd([(i, LIMIT_TEXTS[i][0]) for i in ('reopened_decision', 'stale_results', 'interrupted_executions',
                                                                    'unconfirmed_decisions', 'final_test_sealed')])
    set_texts(s, question=q, options=opts, note=None, digest=None,
              done_steps=[p for p in DONE_TO_CHOICE if p not in ('preprocessing',)])
    for lang in ('en', 'fr'):
        s['texts'][lang]['headlines'].pop('models', None)
        s['texts'][lang]['headlines'].pop('model_variant', None)
        s['texts'][lang]['headlines']['models'] = {'en': 'Linear model and mean baseline (figures stale).',
                                                   'fr': 'Modèle linéaire et moyenne de référence (chiffres périmés).'}[lang]
        s['texts'][lang]['proposals'] = {'p_8': {'en': proposal['restatement'],
                                                 'fr': 'Garder la préparation par défaut : pas d’indicateur, toutes les catégories '
                                                       'gardées, pas de plafond, pas de transformation.'}[lang]}
    s['texts']['en']['next_action'] = s['next_action']['junior_message']
    s['texts']['fr']['next_action'] = ('La plage déclarée de horsepower a changé et la préparation en dépendait : confirmez-la de '
                                       'nouveau ou changez-la, dans le chat.')
    limits_texts(s, ['reopened_decision', 'stale_results', 'interrupted_executions', 'unconfirmed_decisions', 'final_test_sealed',
                     'no_causality', 'workbench_not_tracked'])
    hl = headlines([p for p in DONE_TO_CHOICE if p != 'preprocessing'], {k: 'restated' for k in PLAN})
    hl['models']['results'] = []
    hl.pop('model_variant', None)
    for lang in ('en', 'fr'):
        s['texts'][lang]['headlines'].pop('model_variant', None)
    append_p1(s, panel_contract=2, automation=None, review_queue=None,
              defensibility=defensibility('warn', [('reopened_decision', 'blocking'), ('stale_results', 'blocking'),
                                                   ('interrupted_executions', 'blocking'), ('unconfirmed_decisions', 'not_final'),
                                                   ('final_test_sealed', 'not_final'), ('no_causality', 'context'),
                                                   ('workbench_not_tracked', 'context')]),
              ledger=ledger(), sample=SAMPLE, headlines=hl, criterion_configurations=None)
    return wrap(s, ARGV, NOTE + ' The preparation reopened; models and variants stale; a variant run interrupted.')


AUTO_DECISIONS = ['prediction_time', 'feature_availability', 'split', 'success_criterion', 'preprocessing', 'model_variant',
                  'model_choice']


def review():
    decisions = decisions_upto(AUTO_DECISIONS, basis='automatic')
    s = summary(31, 11, current_step='final_test', open_proposals=[], decisions=decisions,
                results=results_with_channel(BASE['results'], channel='cli'))
    s['plan'][PLAN.index('final_test')]['status'] = 'blocked'
    q = {'en': 'Prediction moment: do you adopt "when the technical characteristics of a new model are fixed", or do you change it?',
         'fr': 'Moment de la prédiction : adoptez-vous « quand les caractéristiques techniques d’un nouveau modèle sont fixées », '
               'ou le changez-vous ?'}
    opts = {'en': [('adopt', 'I adopt it'), ('change', 'I change it'), ('explain', 'Explain first')],
            'fr': [('adopt', 'J’adopte'), ('change', 'Je change'), ('explain', 'Expliquer d’abord')]}
    note = {'en': 'No recommendation.', 'fr': 'Sans recommandation.'}
    digest = {'en': ('Prediction moment: when will the prediction be used? A column known only after that moment cannot be used. '
                     'Here, the fuel efficiency is measured on the road, after the characteristics are fixed.'),
              'fr': ('Moment de la prédiction : à quel moment la prédiction servira-t-elle ? Une colonne connue seulement après ce '
                     'moment ne pourra pas servir. Ici, la consommation se mesure sur route, après que les caractéristiques sont '
                     'fixées.')}
    s['next_action'] = next_action(kind='reconfirm', decision='prediction_time', message='Review the automatic decision.',
                                   audience='agent', junior_message='Review the decisions of the automatic mode, one by one.',
                                   language='en', recommended=None, question=q['en'], junior_digest=digest['en'], review=True,
                                   pause=pause('decision', 'prediction_time', 31, [k for k, _ in opts['en']], dict(opts['en']),
                                               q['en']))
    s['not_yet_defensible'] = nyd([(i, LIMIT_TEXTS[i][0]) for i in ('automatic_decisions_to_review', 'unconfirmed_decisions',
                                                                    'final_test_sealed', 'public_data_already_explored')])
    set_texts(s, question=q, options=opts, note=note, digest=digest, done_steps=PLAN[:11])
    s['texts']['en']['next_action'] = s['next_action']['junior_message']
    s['texts']['fr']['next_action'] = 'Relisez les décisions du mode automatique, une par une.'
    limits_texts(s, ['automatic_decisions_to_review', 'unconfirmed_decisions', 'final_test_sealed', 'public_data_already_explored',
                     'no_causality', 'workbench_not_tracked'])
    append_p1(s, panel_contract=2,
              automation={'variant': 'until_final_test', 'active': False, 'started_revision': 1,
                          'ended': {'revision': 30, 'reason': 'reached_end'}},
              review_queue={'items': [{'decision_id': d, 'status': 'confirmed',
                                       'value': decisions[d]['value'], 'proposal_id': None, 'revision': 2 + i}
                                      for i, d in enumerate(AUTO_DECISIONS)], 'done': 0, 'total': 7},
              defensibility=defensibility('warn', [('automatic_decisions_to_review', 'blocking'),
                                                   ('unconfirmed_decisions', 'not_final'), ('final_test_sealed', 'not_final'),
                                                   ('public_data_already_explored', 'context'), ('no_causality', 'context'),
                                                   ('workbench_not_tracked', 'context')]),
              ledger=ledger(), sample=SAMPLE, headlines=headlines(PLAN[:11], {k: 'automatic' for k in PLAN}),
              criterion_configurations=criterion_configs())
    return wrap(s, ARGV, NOTE + ' The review of an automatic study (until the final test): 7 decisions, 0 adopted.')


def done():
    decisions = decisions_upto(PLAN, basis='restated')
    decisions['final_test'].update({'value': {'model': 'fit.linear'}, 'user_words': 'Yes, I open the final test now.'})
    decisions['conclusion'].update({'value': {'verdict': 'adopt_model',
                                              'text': 'The linear model errs by about 3.8 mpg on average on 80 cars of the same '
                                                      'period, set aside before any look.'}})
    results = results_with_channel(BASE['results'])
    results['final_test.evaluation'] = {'result_id': '9' * 64, 'current': True, 'stale_reason': None, 'integrity': 'ok',
                                        'channel': 'chat'}
    s = summary(52, 13, current_step='conclusion', open_proposals=[], decisions=decisions, results=results)
    s['final_test'] = dict(BASE['final_test'], status='opened',
                           opening={'revision': 47, 'model': 'fit.linear', 'rule': None, 'result_id': '9' * 64,
                                    'user_words': 'Yes, I open the final test now.', 'time': '2026-10-27T10:12:00+00:00'})
    s['criterion'] = dict(BASE['criterion'], final_test={'status': 'met', 'gain': 0.4845, 'low': 0.3910, 'high': 0.5702,
                                                         'minimum': 0.1, 'unit': 'share', 'interval_includes_zero': False,
                                                         'result_id': '9' * 64})
    s['next_action'] = next_action(kind='done', message='Every step is done.', audience='agent',
                                   junior_message='Every step of the plan is done.', language='en', recommended=None,
                                   question=None, junior_digest=None,
                                   after_study={'handoff': {'command': 'hypotrail export handoff'},
                                                'azureml': {'supported': True, 'reason_id': None, 'reason': None},
                                                'cloud_status': 'not_qualified',
                                                'junior_text': 'What comes next: the handoff pack collects your decisions, '
                                                               'the cited results and the limits for a reviewer.'})
    q = {'en': 'What do you want to do with this result?', 'fr': 'Que voulez-vous faire de ce résultat ?'}
    opts = {'en': [('present', 'Present the conclusion to your partner, in three sentences'),
                   ('handoff', 'Prepare the handoff pack'), ('azureml', 'Prepare the Azure ML export of the model')],
            'fr': [('present', 'Présenter la conclusion à votre binôme, en trois phrases'),
                   ('handoff', 'Préparer le dossier de passation'), ('azureml', 'Préparer l’export Azure ML du modèle')]}
    s['not_yet_defensible'] = nyd([(i, LIMIT_TEXTS[i][0]) for i in ('validation_is_not_independent', 'public_data_already_explored',
                                                                    'grouped_split_unsupported')])
    set_texts(s, question=q, options=opts, note=None, digest=None, done_steps=PLAN)
    limits_texts(s, ['validation_is_not_independent', 'public_data_already_explored', 'grouped_split_unsupported',
                     'no_causality', 'workbench_not_tracked'])
    s['texts']['en']['next_action'] = s['next_action']['junior_message']
    s['texts']['fr']['next_action'] = 'Toutes les étapes du plan sont faites.'
    hl = headlines(PLAN, {k: 'restated' for k in PLAN})
    hl['final_test']['results'] = ['9' * 64]
    append_p1(s, panel_contract=2, automation=None, review_queue=None,
              defensibility=defensibility('limits', [('validation_is_not_independent', 'caveat'),
                                                     ('grouped_split_unsupported', 'caveat'),
                                                     ('public_data_already_explored', 'caveat'),
                                                     ('no_causality', 'context'), ('workbench_not_tracked', 'context')]),
              ledger=ledger(openings=1), sample=SAMPLE, headlines=hl, criterion_configurations=criterion_configs(True))
    return wrap(s, ARGV, NOTE + ' The end: the final test opened once, the conclusion confirmed.')


SAMPLE_ROWS = [
    ('L34', 19.0, 6, 232, 100, 2634, 13.0, 71, 1, 'amc gremlin'),
    ('L69', 13.0, 8, 350, 155, 4502, 13.5, 72, 1, 'buick lesabre custom'),
    ('L85', 27.0, 4, 97, 88, 2100, 16.5, 72, 3, 'toyota corolla 1600 (sw)'),
    ('L100', 18.0, 6, 232, 100, 2945, 16.0, 73, 1, 'amc hornet'),
    ('L122', 15.0, 8, 318, 150, 3399, 11.0, 73, 1, 'dodge dart custom'),
    ('L123', 24.0, 4, 121, 110, 2660, 14.0, 73, 2, 'saab 99le'),
    ('L267', 30.0, 4, 98, 68, 2155, 16.5, 78, 1, 'chevrolet chevette'),
    ('L384', 38.0, 4, 91, 67, 1965, 15.0, 82, 3, 'honda civic'),
]
SPECIAL_ROWS = [
    ('L33', 4, 98, '?', 2046, 19.0, 71, 1, 'ford pinto'), ('L127', 6, 200, '?', 2875, 17.0, 74, 1, 'ford maverick'),
    ('L331', 4, 85, '?', 1835, 17.3, 80, 2, 'renault lecar deluxe'), ('L337', 4, 140, '?', 2905, 14.3, 80, 1, 'ford mustang cobra'),
    ('L355', 4, 100, '?', 2320, 15.8, 81, 2, 'renault 18i'), ('L375', 4, 151, '?', 3035, 20.5, 82, 1, 'amc concord dl'),
]


def data():
    d = copy.deepcopy(DATA)
    d['revision'] = 1
    cols = d['rows']['columns']
    features = [c for c in cols if c != 'mpg']
    d['rows'] = {'columns': cols, 'n_rows': 8, 'order': 'seeded sample',
                 'items': [{'row_key': r[0], 'values': dict(zip(cols, r[1:]))} for r in SAMPLE_ROWS],
                 'seed': SEED, 'target_shown': True,
                 'exposure': {'exposure_id': 'x_1', 'purpose': 'development_target_sample', 'recorded': True}}
    note = d.pop('note')
    d['note'] = note
    d['special_rows'] = {'columns': features, 'n_rows': 6,
                         'items': [{'row_key': r[0], 'values': dict(zip(features, r[1:])),
                                    'specials': [{'column': 'horsepower', 'value': '?'}]} for r in SPECIAL_ROWS],
                         'truncated': False}
    return wrap(d, ['data', '--json'], NOTE + ' The seeded sample (the mockup\'s draw) and the six "?" rows.')


def main():
    for name, build in [('summary.step1', step1), ('summary.choice', choice), ('summary.reopened', reopened),
                        ('summary.review', review), ('summary.done', done), ('data.regression', data)]:
        (HERE / f'{name}.json').write_text(json.dumps(build(), indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
